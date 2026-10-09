/* Live audio capture; every ASR input is only PCM already captured by the browser. */
const el=id=>document.getElementById(id);
const state={ready:false,capturing:false,stopping:false,processing:false,session:0,rows:[],history:[],queue:new LiveAudioCore.BoundedQueue(3),dropped:0,stream:null,ctx:null,node:null,sourceNode:null,segmenter:null,pip:null,model:'gemini-3.5-flash-lite',lastAsr:null,lastMt:null,lastLag:null};
const labels={queued:'Chờ xử lý',asr:'Đang nhận dạng',mt:'Đang dịch',ok:'Đã dịch',silence:'Không nhận được lời nói',error:'Lỗi xử lý',skipped:'Bỏ qua để bắt kịp'};
Object.assign(state,{translating:0,mtQueue:[],pendingWords:[],pendingSince:0,asrDraft:'',stabilizer:new LiveAudioCore.StableWords(),captionInvalid:false,presenter:new LiveAudioCore.CaptionPresenter()});
function error(message){el('error').textContent=message||'';}
function seconds(value){return Number(value).toFixed(1).replace('.',',');}
function renderVideoCaption(){
  const mediaTime=el('demo-video').currentTime;
  const latest=state.presenter.select(state.rows,mediaTime,performance.now());
  const visible=state.kind==='video'&&!state.captionInvalid&&latest;
  el('video-captions').hidden=!visible;
  el('caption-vi').textContent=visible?latest.vi:'';
  el('caption-note').textContent=visible?`Sau lời nói ${seconds(Math.max(0,mediaTime-latest.mediaEnd))} giây`:'Đang nghe và dịch…';
  const late=state.rows.filter(row=>row.lateForVideo).length;
  el('caption-health').textContent=late?`${late} bản dịch trễ hơn 2,5 giây. Phụ đề có ghi độ trễ; kết quả về sau không làm quay lại câu cũ.`:'Phụ đề xuất hiện khi có kết quả, giữ tối thiểu 0,9 giây để đọc; độ trễ ghi ngay trên phụ đề.';
  if(state.kind==='video'&&state.pip&&!state.pip.closed){const doc=state.pip.document,vi=doc.getElementById('vi'),en=doc.getElementById('en');if(vi)vi.textContent=visible?latest.vi:'Đang chờ phụ đề khớp thời điểm video…';if(en)en.textContent=visible?latest.en:'';}
}
function updateControls(){
  const busy=state.capturing||state.stopping||state.processing||state.translating||state.queue.length>0||state.mtQueue.length>0;
  el('share').disabled=!state.ready||busy;el('mic').disabled=!state.ready||busy;
  el('demo-start').disabled=!state.ready||busy;
  el('stop').disabled=!state.capturing||state.stopping;el('chunk').disabled=busy;
  el('export').disabled=!state.rows.length;
}
function render(){
  updateControls();
  renderVideoCaption();
  el('queue').textContent=`ASR ${state.queue.length}${state.processing?'+1':''} · Dịch ${state.mtQueue.length} chờ + ${state.translating} chạy`;
  el('dropped').textContent=state.dropped;
  el('asr').textContent=state.lastAsr===null?'Chưa đo':`${Math.round(state.lastAsr)} ms`;
  el('mt').textContent=state.lastMt===null?'Chưa đo':`${Math.round(state.lastMt)} ms`;
  el('lag').textContent=state.lastLag===null?'Chưa đo':`${seconds(state.lastLag/1000)} giây`;
  const current=[...state.rows].reverse().find(row=>row.en);
  const source=current?.en||'Chưa có lời nói.';
  el('asr-draft').textContent='Nhận dạng nháp (có thể sửa): '+(state.asrDraft||'đang nghe tiếp…');
  const target=current?(current.vi||(current.status==='mt'?'Đang dịch đoạn này…':current.message||'Chưa có bản dịch.')):'Bản dịch sẽ xuất hiện tại đây.';
  el('current-en').textContent=source;el('current-vi').textContent=target;
  el('current-status').textContent=current?`Đoạn ${current.id} · ${labels[current.status]} · mốc thu ${seconds(current.startSec)}–${seconds(current.endSec)}s`:'';
  const timeline=el('timeline');timeline.replaceChildren();
  for(const row of state.rows.slice(-80).reverse()){
    const card=document.createElement('article');card.className='card';
    const top=document.createElement('div');top.className='card-top';
    const time=document.createElement('span');time.textContent=`#${row.id} · ${seconds(row.startSec)}–${seconds(row.endSec)}s thu âm`;
    const badge=document.createElement('span');badge.textContent=labels[row.status];top.append(time,badge);card.append(top);
    const en=document.createElement('p');en.textContent=row.en||'…';card.append(en);
    const vi=document.createElement('p');vi.className=row.status==='error'?'error':'vi';vi.textContent=row.vi||row.message||(row.status==='mt'?'Đang chờ bản dịch…':'');card.append(vi);
    const timing=document.createElement('div');timing.className='timing';
    timing.textContent=`Đoạn thu ${seconds(row.durationSec)}s${row.asrMs!==undefined?' · ASR '+Math.round(row.asrMs)+'ms':''}${row.mtMs!==undefined?' · MT '+Math.round(row.mtMs)+'ms':''}${row.lagMs!==undefined?' · Sau gói ASR '+seconds(row.lagMs/1000)+'s':''}${row.lateForVideo?' · Dịch trễ hơn 2,5 giây':''}`;
    card.append(timing);timeline.append(card);
  }
  if(!state.rows.length){const empty=document.createElement('p');empty.className='muted';empty.textContent='Chia sẻ tab có âm thanh hoặc thử bằng micro, nói tiếng Anh để quan sát kết quả.';timeline.append(empty);}
  if(state.pip&&!state.pip.closed){const doc=state.pip.document;if(state.kind!=='video'){doc.getElementById('en').textContent=source;doc.getElementById('vi').textContent=target;}doc.getElementById('state').textContent=el('state').textContent;doc.getElementById('stop').disabled=!state.capturing;}
}
async function requestJSON(path,options={}){
  const response=await fetch(path,options);let data;
  try{data=await response.json();}catch{throw new Error('Server trả dữ liệu không hợp lệ. Dừng server cũ và mở lại run_studio.cmd.');}
  if(!response.ok||data.status==='error'){const e=new Error(data.message||'Request không thành công.');e.code=data.error_code;e.diagnostic=data.diagnostic;throw e;}
  return data;
}
function enqueue(job){
  if(!job)return;
  job.session=state.session;job.queuedAt=performance.now();
  job.mediaOffset=state.kind==='video'?el('demo-video').currentTime-job.endSec:null;
  // Pending snapshots overlap: retain the freshest audio, not stale ASR work.
  state.queue.items=[job];
  render();processQueue();
}
function flushStable(){
  if(!state.pendingWords.length)return;
  const words=state.pendingWords;state.pendingWords=[];state.pendingSince=0;
  const first=words[0],last=words[words.length-1];
  const waiting=state.mtQueue[state.mtQueue.length-1];
  const row=waiting||{id:state.rows.length+1,session:state.session,startSec:first.start,mediaStart:first.mediaStart,status:'queued',en:'',vi:'',asrMs:state.lastAsr};
  row.en=(row.en+' '+words.map(w=>w.text).join(' ')).trim();row.endSec=last.end;row.mediaEnd=last.mediaEnd;row.durationSec=row.endSec-row.startSec;row.receivedAt=last.receivedAt;
  if(!waiting){state.rows.push(row);state.mtQueue.push(row);}
  if(row.en.length>1600){state.mtQueue.pop();row.status='skipped';row.message='Provider dịch không theo kịp; bộ đệm văn bản đã đầy.';state.dropped++;}
  render();processTranslations();
}
async function processTranslations(){
  if(state.translating>=2||!state.mtQueue.length)return;state.translating++;
  try{
    while(state.mtQueue.length){
      const row=state.mtQueue.shift();
      if(row.session!==state.session)continue;
      row.status='mt';render();
      try{
        const context=state.rows.filter(r=>r.id<row.id&&r.en).slice(-3).map(r=>r.en).join(' ').slice(-6000);
        const translation=await requestJSON('/api/translate-test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:row.en,previous_context:context,model:state.model,mode:'stream'})});
        if(row.session!==state.session)continue;
        Object.assign(row,{vi:translation.translated_text,status:'ok',displayedAt:performance.now(),mtMs:translation.latency_ms,model:translation.model,provider:translation.provider,mtTiming:translation.diagnostic});
        row.lagMs=performance.now()-row.receivedAt;state.lastMt=row.mtMs;state.lastLag=row.lagMs;
        row.lateForVideo=state.kind==='video'&&el('demo-video').currentTime>row.mediaEnd+2.5;
        state.history.push(row.en);if(state.history.length>4)state.history.shift();
      }catch(e){row.status='error';row.message=e.message;row.errorCode=e.code;error(`Đoạn ${row.id}: ${e.message}`);}
      render();
    }
  }finally{state.translating--;finishStatus();render();}
}
function finishStatus(){if(!state.capturing&&!state.stopping&&!state.processing&&!state.translating&&!state.queue.length&&!state.mtQueue.length)el('state').textContent='Đã dừng thu · xử lý xong';}
async function processQueue(){
  if(state.processing)return;state.processing=true;
  try{
    while(state.queue.length){
      const job=state.queue.shift();
      if(job.session!==state.session)continue;
      try{
        const asr=await requestJSON('/api/live/asr',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Sample-Rate':'16000'},body:job.pcm.buffer});
        if(job.session!==state.session)continue;
        if(!Array.isArray(asr.words))throw new Error('Server ASR cũ chưa trả timestamp từ. Dừng và mở lại run_studio.cmd.');
        state.lastAsr=asr.asr_latency_ms;
        if(state.stabilizer.previous.some(w=>w.end<job.startSec)){
          state.dropped++;state.rows.push({id:state.rows.length+1,status:'skipped',startSec:state.stabilizer.previous[0].start,endSec:job.startSec,durationSec:0,en:'',vi:'',message:'ASR không theo kịp: âm thanh chưa chốt đã ra khỏi bộ đệm 12 giây.'});
        }
        const words=asr.words.map(w=>({...w,start:w.start+job.startSec,end:w.end+job.startSec,mediaStart:job.mediaOffset===null?null:w.start+job.startSec+job.mediaOffset,mediaEnd:job.mediaOffset===null?null:w.end+job.startSec+job.mediaOffset,receivedAt:job.receivedAt}));
        const result=state.stabilizer.update(words,job.final);
        state.segmenter?.trimBefore(Math.max(0,state.stabilizer.committedEnd-1.5));
        state.asrDraft=result.draft.map(w=>w.text).join(' ');
        if(result.committed.length){if(!state.pendingWords.length)state.pendingSince=performance.now();state.pendingWords.push(...result.committed);}
        if(job.final||state.pendingWords.length>=4||state.pendingWords.some(w=>/[.!?]$/.test(w.text)))flushStable();
      }catch(e){error(e.message);}
      render();
    }
  }finally{
    state.processing=false;
    if(!state.capturing&&!state.stopping)flushStable();finishStatus();
    render();
  }
}
async function startCapture(kind){
  if(!state.ready||state.capturing||state.processing||state.translating||state.queue.length||state.mtQueue.length)return;
  error('');const session=++state.session;state.rows=[];state.history=[];state.dropped=0;state.lastAsr=null;state.lastMt=null;state.lastLag=null;renderVideoCaption();
  state.stabilizer=new LiveAudioCore.StableWords();state.presenter=new LiveAudioCore.CaptionPresenter();state.pendingWords=[];state.asrDraft='';state.captionInvalid=false;
  el('share').disabled=true;el('mic').disabled=true;el('demo-start').disabled=true;el('state').textContent='Đang chọn nguồn…';
  let stream,ctx;
  try{
    // Invoke the browser picker directly from the click gesture.
    const mediaPromise=kind==='video'?(async()=>{
      const video=el('demo-video');
      if(!video.captureStream)throw new Error('Trình duyệt chưa hỗ trợ thu âm từ video. Hãy mở trang bằng Chrome.');
      await video.play();
      return video.captureStream();
    })():kind==='tab'?navigator.mediaDevices.getDisplayMedia({video:{displaySurface:'browser'},audio:true,selfBrowserSurface:'exclude',systemAudio:'exclude'}):navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
    try{ctx=new AudioContext({sampleRate:16000});}catch{ctx=new AudioContext();}
    const resume=ctx.resume();stream=await mediaPromise;await resume;
    if(!stream.getAudioTracks().length)throw new Error(kind==='video'?'Không thu được âm thanh video. Thử tải lại trang bằng Chrome.':'Nguồn không có audio track. Chọn Chrome Tab và bật Share tab audio.');
    await ctx.audioWorklet.addModule('/pcm-worklet.js');
    const source=ctx.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));
    const node=new AudioWorkletNode(ctx,'pcm16k',{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1]});
    state.stream=stream;state.ctx=ctx;state.node=node;state.sourceNode=source;state.segmenter=new LiveAudioCore.RollingAudio({hopSec:Number(el('chunk').value)/1000});
    state.capturing=true;state.stopping=false;state.kind=kind;
    node.port.onmessage=e=>{
      if(session!==state.session)return;
      if(e.data.flushed){state.flushResolve?.();return;}
      if(!state.segmenter||!e.data.pcm)return;
      if(kind==='video'&&el('demo-video').paused&&!state.stopping)return;
      const pcm=new Int16Array(e.data.pcm),receivedAt=performance.now();
      enqueue(state.segmenter.push(pcm,e.data.rms,receivedAt));
      el('level').style.width=`${Math.min(100,e.data.rms*500)}%`;
      el('capture-clock').textContent=`Đã thu ${seconds(state.segmenter.total/16000)} giây`;
    };
    source.connect(node);node.connect(ctx.destination); // Worklet outputs zeros, so shared audio is not replayed.
    for(const track of stream.getTracks())track.addEventListener('ended',()=>stopCapture(),{once:true});
    el('source').textContent=kind==='video'?'Nguồn: âm thanh video NVIDIA đang phát':kind==='tab'?`Nguồn: ${stream.getVideoTracks()[0]?.label||'tab đang chia sẻ'}`:'Nguồn: micro · nói tiếng Anh';
    el('state').textContent='Đang thu âm thanh trực tiếp';render();
  }catch(e){
    if(kind==='video')el('demo-video').pause();
    stream?.getTracks().forEach(track=>track.stop());await ctx?.close().catch(()=>{});
    state.capturing=false;state.stream=null;state.ctx=null;state.node=null;state.segmenter=null;
    error(e.name==='NotAllowedError'?'Bạn chưa cấp quyền chia sẻ/thu âm. Bấm lại và chọn nguồn để thử.':e.message);
    el('state').textContent='Chưa bắt đầu thu';render();
  }
}
async function stopCapture(){
  if(!state.stream||state.stopping)return;
  state.stopping=true;state.capturing=false;el('state').textContent='Đang dừng thu và xử lý đoạn cuối…';render();
  if(state.kind==='video')el('demo-video').pause();
  try{
    state.sourceNode?.disconnect();
    if(state.node){await new Promise(resolve=>{const timeout=setTimeout(resolve,600);state.flushResolve=()=>{clearTimeout(timeout);resolve();};state.node.port.postMessage('flush');});}
    enqueue(state.segmenter?.flush());
    state.stream.getTracks().forEach(track=>track.stop());
    if(state.node){state.node.port.onmessage=null;state.node.disconnect();}
    await state.ctx?.close();
  }finally{
    state.flushResolve=null;state.stream=null;state.ctx=null;state.node=null;state.sourceNode=null;state.segmenter=null;state.stopping=false;
    el('level').style.width='0%';el('state').textContent=state.processing||state.queue.length?'Đã dừng thu · đang xử lý hàng đợi':'Đã dừng thu';render();
  }
}
async function openPip(){
  if(state.pip&&!state.pip.closed){state.pip.focus();return;}
  try{
    if('documentPictureInPicture' in window){state.pip=await window.documentPictureInPicture.requestWindow({width:620,height:350});}
    else{state.pip=window.open('','live_subtitles','width=620,height=350');if(!state.pip)throw new Error('Trình duyệt chặn cửa sổ. Cho phép popup hoặc dùng Chrome hỗ trợ PiP.');error('Trình duyệt không hỗ trợ Document PiP; cửa sổ thường không bảo đảm luôn nổi.');}
    const doc=state.pip.document;doc.head.replaceChildren();doc.body.replaceChildren();
    const style=doc.createElement('style');style.textContent='body{font:17px system-ui;background:#101827;color:#eef4ff;margin:0;padding:18px}header{display:flex;gap:15px;align-items:center;justify-content:space-between}button{background:#8c3151;color:white;padding:8px 13px;border:0;border-radius:7px;cursor:pointer}p{white-space:pre-wrap;line-height:1.5}#vi{font-size:24px;color:#82efd0}#en{color:#aabbd5}#state{font-size:12px;color:#7de1bf}';doc.head.append(style);
    const header=doc.createElement('header'),title=doc.createElement('strong'),stop=doc.createElement('button');title.textContent='Anh → Việt · phụ đề trực tiếp';stop.id='stop';stop.textContent='Dừng thu';stop.onclick=()=>stopCapture();header.append(title,stop);doc.body.append(header);
    for(const id of ['state','en','vi']){const node=doc.createElement('p');node.id=id;doc.body.append(node);}
    const pipWindow=state.pip;
    pipWindow.addEventListener('pagehide',()=>{if(state.pip===pipWindow)state.pip=null;},{once:true});render();
  }catch(e){error(e.message);}
}
el('share').onclick=()=>startCapture('tab');el('mic').onclick=()=>startCapture('mic');el('stop').onclick=()=>stopCapture();el('pip').onclick=()=>openPip();
el('demo-start').onclick=()=>startCapture('video');
el('video-fullscreen').onclick=async()=>{
  try{
    if(document.fullscreenElement)await document.exitFullscreen();
    else await el('video-stage').requestFullscreen();
  }catch(e){error('Không mở được toàn màn hình: '+e.message);}
};
setInterval(()=>{renderVideoCaption();if(state.pendingWords.length&&performance.now()-state.pendingSince>=1200)flushStable();},250);
el('demo-video').addEventListener('ended',()=>{if(state.kind==='video')stopCapture();});
el('demo-video').addEventListener('seeking',()=>{
  if(state.kind==='video'){state.captionInvalid=true;renderVideoCaption();if(state.capturing){stopCapture();error('Đã tua video. Chờ xử lý xong rồi bấm Phát video NVIDIA và dịch để bắt đầu phiên mới tại vị trí này.');}}
});
el('export').onclick=()=>{
  const content={version:2,exportedAt:new Date().toISOString(),model:state.model,asrHopMs:Number(el('chunk').value),asrWindowSec:12,dropped:state.dropped,latencyDefinition:'client receipt of ASR snapshot final PCM packet to translation result; not utterance-end latency',ocrEnabled:false,segments:state.rows};
  const url=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='live-session-'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
window.addEventListener('pagehide',()=>{state.stream?.getTracks().forEach(track=>track.stop());state.ctx?.close();state.pip?.close();});
(async()=>{
  try{
    if(!navigator.mediaDevices||!window.AudioWorkletNode)throw new Error('Cần trình duyệt hỗ trợ thu âm và AudioWorklet; mở bằng Chrome trên localhost.');
    const info=await requestJSON('/api/translation-status');
    if(!info.live_audio_enabled)throw new Error('Server đang chạy bản cũ. Nhấn Ctrl+C ở cửa sổ server rồi mở lại run_studio.cmd.');
    if(!info.incremental_asr_enabled)throw new Error('Cần khởi động lại server để bật ASR tăng dần: Ctrl+C rồi mở run_studio.cmd.');
    if(!info.configured)throw new Error('Server chưa cấu hình provider/khóa dịch. Mở run_studio.cmd và nhập khóa trên máy.');
    state.model=info.model||state.model;el('config').textContent=`Provider: ${info.provider} · Model: ${info.model||'text demo'} · ASR local · OCR chưa bật`;
    el('state').textContent='Đang nạp ASR local…';
    await requestJSON('/api/live/warmup',{method:'POST'});
    state.ready=true;el('state').textContent='Sẵn sàng chia sẻ tab';render();
  }catch(e){error(e.message);el('state').textContent='Chưa sẵn sàng';render();}
})();
