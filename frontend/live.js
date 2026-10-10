/* Live audio capture; every ASR input is only PCM already captured by the browser. */
const el=id=>document.getElementById(id);
const state={ready:false,capturing:false,stopping:false,processing:false,session:0,rows:[],history:[],queue:new LiveAudioCore.BoundedQueue(3),dropped:0,stream:null,ctx:null,node:null,sourceNode:null,segmenter:null,pip:null,model:'gemini-2.5-flash',engineMode:'local',lastAsr:null,lastMt:null,lastLag:null};
const labels={queued:'Chờ xử lý',asr:'Đang nhận dạng',mt:'Đang dịch',ok:'Đã dịch',silence:'Không nhận được lời nói',error:'Lỗi xử lý',skipped:'Bỏ qua để bắt kịp'};
Object.assign(state,{activeRow:null,translating:0,mtQueue:[],pendingWords:[],pendingSince:0,asrDraft:'',stabilizer:new LiveAudioCore.StableWords(),captionInvalid:false,presenter:new LiveAudioCore.CaptionPresenter()});
state.pair=new LiveAudioCore.TranscriptPair();
function error(message){el('error').textContent=message||'';}
function seconds(value){return Number(value).toFixed(1).replace('.',',');}

function getCardBadge(row) {
  if (row.status === 'mt') {
    const isAi = state.engineMode === 'gemini';
    return {
      tag: isAi ? '🧠 Đang dịch AI…' : '⚡ Đang dịch…',
      cardClass: isAi ? 'is-translating' : 'is-draft',
      badgeClass: isAi ? 'is-translating' : 'is-draft'
    };
  }
  if (row.status === 'error') {
    return {
      tag: '⚠️ Lỗi dịch',
      cardClass: 'is-error',
      badgeClass: 'is-error'
    };
  }
  if (row.status === 'skipped') {
    return {
      tag: '⏭️ Bỏ qua',
      cardClass: 'is-draft',
      badgeClass: 'is-draft'
    };
  }
  if (row.provider === 'gemini' || row.provider?.includes('gemini')) {
    return {
      tag: '✨ AI Gemini',
      cardClass: 'is-ai',
      badgeClass: 'badge-ai'
    };
  }
  if (row.provider === 'local-fallback') {
    return {
      tag: '⚡ Dự phòng GPU',
      cardClass: 'is-draft',
      badgeClass: 'is-draft'
    };
  }
  if (row.isDraft) {
    return {
      tag: row.isFinal ? '⚡ Nháp GPU' : '⚡ Đang nghe…',
      cardClass: 'is-draft',
      badgeClass: 'is-draft'
    };
  }
  return {
    tag: labels[row.status] || '✨ Đã dịch',
    cardClass: '',
    badgeClass: 'badge-ok'
  };
}

function renderVideoCaption(){
  const mediaTime=el('demo-video').currentTime;
  const latest=state.presenter.select(state.rows,mediaTime,performance.now());
  const visible=state.kind==='video'&&!state.captionInvalid&&latest;
  el('video-captions').hidden=!visible;
  el('caption-vi').textContent=visible?latest.vi:'';
  el('caption-note').textContent=visible?`Sau lời nói ${seconds(Math.max(0,mediaTime-latest.mediaEnd))} giây`:'Đang nghe và dịch…';
  const late=state.rows.filter(row=>row.lateForVideo).length;
  el('caption-health').textContent=late?`${late} bản dịch trễ hơn 2,5 giây. Phụ đề có ghi độ trễ; kết quả về sau không làm quay lại câu cũ.`:'Phụ đề xuất hiện khi có kết quả, giữ tối thiểu 0,9 giây để đọc; độ trễ ghi ngay trên phụ đề.';
  renderFloating();
}
function renderFloating(){
  if(!state.pip||state.pip.closed)return;
  const doc=state.pip.document;
  const put=(id,value)=>{const node=doc.getElementById(id);if(node&&node.textContent!==value)node.textContent=value;};
  put('state',el('state').textContent);
  const stop=doc.getElementById('stop'),share=doc.getElementById('pip-share');
  if(stop)stop.disabled=!state.capturing||state.stopping;
  if(share){share.hidden=state.capturing;share.disabled=!state.ready||state.processing||!!state.translating||state.stopping;}
  put('pip-error',el('error').textContent);

  const hearing=state.asrDraft||state.pendingWords.map(w=>w.text).join(' ')||'';
  put('draft-bar',hearing?`🎙️ Đang nghe: ${hearing}`:'');

  const matched=state.pair.select(state.rows,performance.now());
  if(matched){
    put('en',matched.en||'');
    put('vi',matched.vi||'');
  }else{
    put('en','');
    put('vi','');
  }
}
function updateControls(){
  const isCapturing = state.capturing;
  el('share').disabled = !state.ready || state.stopping || (isCapturing && state.kind !== 'tab');
  el('mic').disabled = !state.ready || state.stopping || (isCapturing && state.kind !== 'mic');
  el('demo-start').disabled = !state.ready || state.stopping || (isCapturing && state.kind !== 'video');
  el('stop').disabled = !isCapturing || state.stopping;
  el('chunk').disabled = isCapturing;
  el('export').disabled = !state.rows.length;
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
  if(el('log-count')) el('log-count').textContent=`${state.rows.filter(r=>r.en).length} đoạn`;
  const timeline=el('timeline');timeline.replaceChildren();
  for(const row of state.rows.slice(-80).reverse()){
    const badgeInfo=getCardBadge(row);
    const card=document.createElement('article');card.className='card '+(badgeInfo.cardClass||'');
    const top=document.createElement('div');top.className='card-top';
    const time=document.createElement('span');time.textContent=`#${row.id} · ${seconds(row.startSec)}s`;
    const badge=document.createElement('span');badge.className='badge '+(badgeInfo.badgeClass||'');badge.textContent=badgeInfo.tag;
    top.append(time,badge);card.append(top);
    const en=document.createElement('p');en.className='en';en.textContent=row.en||'…';card.append(en);
    const vi=document.createElement('p');vi.className=row.status==='error'?'error':'vi';vi.textContent=row.vi||row.message||(row.status==='mt'?'Đang dịch…':'');card.append(vi);
    const timing=document.createElement('div');timing.className='timing';
    timing.textContent=`Thu ${seconds(row.durationSec)}s${row.asrMs!==undefined?' · ASR '+Math.round(row.asrMs)+'ms':''}${row.mtMs!==undefined?' · MT '+Math.round(row.mtMs)+'ms':''}${row.lagMs!==undefined?' · Sau ASR '+seconds(row.lagMs/1000)+'s':''}`;
    card.append(timing);timeline.append(card);
  }
  if(!state.rows.length){const empty=document.createElement('p');empty.className='muted empty-note';empty.textContent='Chưa có lịch sử. Phát âm thanh hoặc nói để xem nhật ký dịch tại đây.';timeline.append(empty);}
}
async function requestJSON(path,options={}){
  const response=await fetch(path,options);let data;
  try{data=await response.json();}catch{throw new Error('Server trả dữ liệu không hợp lệ. Dừng server cũ và mở lại studio.cmd.');}
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
function consumePendingWords(final = false) {
  if (!state.pendingWords.length) {
    if (final && state.activeRow && !state.activeRow.isFinal) {
      state.activeRow.isFinal = true;
      const finishedRow = state.activeRow;
      state.activeRow = null;
      triggerRowTranslation(finishedRow);
    }
    return;
  }

  while (state.pendingWords.length > 0) {
    if (!state.activeRow) {
      const first = state.pendingWords[0];
      state.activeRow = {
        id: state.rows.length + 1,
        session: state.session,
        startSec: first.start,
        mediaStart: first.mediaStart,
        status: 'mt',
        en: '',
        vi: '',
        isDraft: true,
        isFinal: false,
        isPolished: false,
        words: [],
        asrMs: state.lastAsr,
        updatedAt: performance.now()
      };
      state.rows.push(state.activeRow);
    }

    const cutIdx = LiveAudioCore.findSentenceBoundary(state.pendingWords, final);
    if (cutIdx >= 0) {
      const chunk = state.pendingWords.splice(0, cutIdx + 1);
      state.activeRow.words.push(...chunk);
      state.activeRow.en = state.activeRow.words.map(w => w.text).join(' ').trim();
      const last = state.activeRow.words[state.activeRow.words.length - 1];
      state.activeRow.endSec = last.end;
      state.activeRow.mediaEnd = last.mediaEnd;
      state.activeRow.durationSec = state.activeRow.endSec - state.activeRow.startSec;
      state.activeRow.receivedAt = last.receivedAt;
      state.activeRow.updatedAt = performance.now();
      state.activeRow.isFinal = true;

      const finishedRow = state.activeRow;
      state.activeRow = null;
      triggerRowTranslation(finishedRow);
    } else {
      const chunk = state.pendingWords.splice(0, state.pendingWords.length);
      state.activeRow.words.push(...chunk);
      state.activeRow.en = state.activeRow.words.map(w => w.text).join(' ').trim();
      const last = state.activeRow.words[state.activeRow.words.length - 1];
      state.activeRow.endSec = last.end;
      state.activeRow.mediaEnd = last.mediaEnd;
      state.activeRow.durationSec = state.activeRow.endSec - state.activeRow.startSec;
      state.activeRow.receivedAt = last.receivedAt;
      state.activeRow.updatedAt = performance.now();

      const ageMs = performance.now() - (state.activeRow.updatedAt || performance.now());
      if (LiveAudioCore.phraseReady(state.activeRow.words, final, ageMs)) {
        triggerRowTranslation(state.activeRow);
      }
      break;
    }
  }
  state.pendingSince = 0;
  render();
}

function triggerRowTranslation(row) {
  if (!row || row.session !== state.session) return;
  if (row.isTranslating) {
    row.needsRetranslate = true;
    return;
  }
  const text = row.en;
  if (!text) return;
  if (text === row.lastTranslatedEn && row.status === 'ok') {
    return;
  }

  // Bounded MT concurrency: limit max 2 concurrent translation requests
  if (state.translating >= 2) {
    if (!state.mtQueue.includes(row)) {
      state.mtQueue.push(row);
    }
    render();
    return;
  }

  executeRowTranslation(row);
}

async function executeRowTranslation(row) {
  if (!row || row.session !== state.session) return;
  const text = row.en;
  if (!text) return;

  state.translating++;
  row.isTranslating = true;
  row.needsRetranslate = false;
  row.status = 'mt';
  render();

  const rawMode = el('engine-mode')?.value;
  const mode = ['local', 'hybrid', 'gemini'].includes(rawMode) ? rawMode : (state.engineMode || 'local');
  const context = state.rows.filter(r => r.id < row.id && r.en).slice(-2).map(r => r.en).join(' ').slice(-3000);

  try {
    // -------------------------------------------------------------
    // CHẾ ĐỘ 1: LOCAL (⚡ Local NLLB siêu tốc 150ms)
    // -------------------------------------------------------------
    if (mode === 'local') {
      const translation = await requestJSON('/api/translate-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: text,
          previous_context: context,
          provider: 'local',
          model: state.model,
          mode: 'stream'
        })
      });
      if (row.session !== state.session) return;
      row.lastTranslatedEn = text;
      row.vi = translation.translated_text;
      row.status = 'ok';
      row.provider = 'local';
      row.isDraft = !row.isFinal;
      row.mtMs = translation.latency_ms;
      row.displayedAt = performance.now();
      row.lagMs = performance.now() - (row.receivedAt || performance.now());
      state.lastMt = row.mtMs;
      state.lastLag = row.lagMs;
      row.lateForVideo = state.kind === 'video' && el('demo-video').currentTime > row.mediaEnd + 2.5;
      render();
    }
    // -------------------------------------------------------------
    // CHẾ ĐỘ 2: HYBRID (🚀 Local trước 150ms + Gemini hiệu chỉnh bất đồng bộ ở nền)
    // -------------------------------------------------------------
    else if (mode === 'hybrid') {
      const translation = await requestJSON('/api/translate-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: text,
          previous_context: context,
          provider: 'local',
          model: state.model,
          mode: 'stream'
        })
      });
      if (row.session !== state.session) return;
      row.lastTranslatedEn = text;
      row.vi = translation.translated_text;
      row.status = 'ok';
      row.provider = 'local';
      row.isDraft = !row.isFinal;
      row.mtMs = translation.latency_ms;
      row.displayedAt = performance.now();
      row.lagMs = performance.now() - (row.receivedAt || performance.now());
      state.lastMt = row.mtMs;
      state.lastLag = row.lagMs;
      row.lateForVideo = state.kind === 'video' && el('demo-video').currentTime > row.mediaEnd + 2.5;
      render();

      if (row.isFinal && !row.isPolished) {
        polishRowWithGemini(row);
      }
    }
    // -------------------------------------------------------------
    // CHẾ ĐỘ 3: GEMINI (🧠 Gemini Cloud trực tiếp)
    // -------------------------------------------------------------
    else if (mode === 'gemini') {
      row.isDraft = false;
      const translation = await requestJSON('/api/translate-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: text,
          previous_context: context,
          provider: 'gemini',
          model: state.model,
          mode: 'stream'
        })
      });
      if (row.session !== state.session) return;
      row.lastTranslatedEn = text;
      row.vi = translation.translated_text;
      row.status = 'ok';
      row.provider = 'gemini';
      row.isDraft = false;
      row.mtMs = translation.latency_ms;
      row.displayedAt = performance.now();
      row.lagMs = performance.now() - (row.receivedAt || performance.now());
      state.lastMt = row.mtMs;
      state.lastLag = row.lagMs;
      row.lateForVideo = state.kind === 'video' && el('demo-video').currentTime > row.mediaEnd + 2.5;
      render();
    }
  } catch (err) {
    console.error('Translation error:', err);
    if (!row.vi) {
      row.status = 'error';
      row.message = err.message;
      error('Đoạn ' + row.id + ': ' + err.message);
    }
  } finally {
    row.isTranslating = false;
    state.translating = Math.max(0, state.translating - 1);

    while (state.mtQueue.length > 0 && state.translating < 2) {
      const nextRow = state.mtQueue.shift();
      triggerRowTranslation(nextRow);
    }

    if (row.en !== row.lastTranslatedEn || row.needsRetranslate) {
      triggerRowTranslation(row);
    } else {
      finishStatus();
      render();
    }
  }
}

async function polishRowWithGemini(row) {
  if (!row || row.session !== state.session || row.isPolished || !row.isFinal) return;
  row.isPolished = true;
  try {
    const context = state.rows.filter(r => r.id < row.id && r.en).slice(-2).map(r => r.en).join(' ').slice(-3000);
    const polished = await requestJSON('/api/translate-test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: row.en,
        previous_context: context,
        provider: 'gemini',
        model: state.model,
        mode: 'stream'
      })
    });
    if (row.session !== state.session) return;
    row.vi = polished.translated_text;
    row.isDraft = false;
    row.polishedMs = polished.latency_ms;
    row.provider = 'gemini';
    render();
  } catch (err) {
    console.warn('Gemini polish fallback:', err);
    row.isDraft = false;
    render();
  } finally {
    finishStatus();
    render();
  }
}

function finishStatus(){
  if(!state.capturing&&!state.stopping&&!state.processing&&!state.translating&&!state.queue.length&&!state.pendingWords.length&&(!state.activeRow||state.activeRow.isFinal)){
    el('state').textContent='Đã dừng thu · xử lý xong';
  }
}

async function processQueue(){
  if(state.processing)return;state.processing=true;
  try{
    while(state.queue.length){
      const job=state.queue.shift();
      if(job.session!==state.session)continue;
      try{
        const asr=await requestJSON('/api/live/asr',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Sample-Rate':'16000'},body:job.pcm.buffer});
        if(job.session!==state.session)continue;
        if(!Array.isArray(asr.words))throw new Error('Server ASR cũ chưa trả timestamp từ. Dừng và mở lại studio.cmd.');
        state.lastAsr=asr.asr_latency_ms;
        if(state.stabilizer.previous.some(w=>w.end<job.startSec)){
          state.dropped++;state.rows.push({id:state.rows.length+1,status:'skipped',startSec:state.stabilizer.previous[0].start,endSec:job.startSec,durationSec:0,en:'',vi:'',message:'ASR không theo kịp: âm thanh chưa chốt đã ra khỏi bộ đệm 12 giây.'});
        }
        const words=asr.words.map(w=>({...w,start:w.start+job.startSec,end:w.end+job.startSec,mediaStart:job.mediaOffset===null?null:w.start+job.startSec+job.mediaOffset,mediaEnd:job.mediaOffset===null?null:w.end+job.startSec+job.mediaOffset,receivedAt:job.receivedAt}));
        const result=state.stabilizer.update(words,job.final);
        state.segmenter?.trimBefore(Math.max(0,state.stabilizer.committedEnd-1.5));
        state.asrDraft=result.draft.map(w=>w.text).join(' ');
        if(result.committed.length){if(!state.pendingWords.length)state.pendingSince=performance.now();state.pendingWords.push(...result.committed);}
        consumePendingWords(job.final);
      }catch(e){error(e.message);}
      render();
    }
  }finally{
    state.processing=false;
    if(!state.capturing&&!state.stopping)consumePendingWords(true);
    finishStatus();
    render();
  }
}
async function startCapture(kind,captureWindow=window){
  if(!state.ready){error('Hệ thống đang khởi động model, vui lòng đợi 1–2 giây rồi bấm lại...');return;}
  if(state.stopping)return;
  if(state.capturing)await stopCapture();
  state.processing=false;state.translating=0;state.mtQueue=[];state.queue.items=[];
  error('');const session=++state.session;state.rows=[];state.pair=new LiveAudioCore.TranscriptPair();state.presenter=new LiveAudioCore.CaptionPresenter();state.asrDraft='';state.pendingWords=[];state.history=[];state.dropped=0;state.activeRow=null;state.lastAsr=null;state.lastMt=null;state.lastLag=null;renderVideoCaption();
  state.stabilizer=new LiveAudioCore.StableWords();state.presenter=new LiveAudioCore.CaptionPresenter();state.pair=new LiveAudioCore.TranscriptPair();state.pendingWords=[];state.asrDraft='';state.captionInvalid=false;
  el('share').disabled=true;el('mic').disabled=true;el('demo-start').disabled=true;el('state').textContent='Đang chọn nguồn…';
  let stream,ctx;
  try{
    // Invoke the browser picker directly from the click gesture.
    const mediaPromise=kind==='video'?(async()=>{
      const video=el('demo-video');
      const capture=video.captureStream||video.mozCaptureStream;
      if(!capture)throw new Error('Trình duyệt chưa hỗ trợ captureStream. Hãy mở trang bằng Chrome.');
      if(video.ended)video.currentTime=0;
      await video.play();
      let stream=capture.call(video);
      let retries=6;
      while(!stream.getAudioTracks().length&&retries-->0){
        await new Promise(r=>setTimeout(r,80));
        stream=capture.call(video);
      }
      return stream;
    })():kind==='tab'?((window.navigator&&window.navigator.mediaDevices)||navigator.mediaDevices).getDisplayMedia({video:{displaySurface:'browser'},audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false},selfBrowserSurface:'exclude',systemAudio:'include'}):navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
    try{ctx=new AudioContext({sampleRate:16000});}catch{ctx=new AudioContext();}
    const resume=ctx.resume();stream=await mediaPromise;await resume;
    if(!stream.getAudioTracks().length)throw new Error(kind==='video'?'Không thu được âm thanh video. Thử bấm lại Phát video NVIDIA.':'Nguồn chia sẻ không có âm thanh. Hãy chọn "Thẻ Chrome" (Chrome Tab) và BẬT tùy chọn "Chia sẻ âm thanh của thẻ" (Share tab audio) ở góc dưới bên trái.');
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
  if(state.activeRow&&!state.activeRow.isFinal){
    state.activeRow.isFinal=true;
    const fin=state.activeRow;state.activeRow=null;
    triggerRowTranslation(fin);
  }
  try{
    state.sourceNode?.disconnect();
    if(state.node){await new Promise(resolve=>{const timeout=setTimeout(resolve,600);state.flushResolve=()=>{clearTimeout(timeout);resolve();};state.node.port.postMessage('flush');});}
    enqueue(state.segmenter?.flush());
    state.stream.getTracks().forEach(track=>track.stop());
    if(state.node){state.node.port.onmessage=null;state.node.disconnect();}
    await state.ctx?.close().catch(()=>{});
  }finally{
    state.flushResolve=null;state.stream=null;state.ctx=null;state.node=null;state.sourceNode=null;state.segmenter=null;state.stopping=false;
    el('level').style.width='0%';el('state').textContent=state.processing||state.queue.length||state.translating||state.mtQueue.length?'Đã dừng thu · đang xử lý hàng đợi':'Đã dừng thu';render();
  }
}
let floatingCssCache = '';

async function openPip(){
  if(state.pip&&!state.pip.closed){state.pip.focus();return;}
  try{
    if('documentPictureInPicture' in window){state.pip=await window.documentPictureInPicture.requestWindow({width:480,height:360});}
    else{state.pip=window.open('','live_subtitles','width=620,height=350');if(!state.pip)throw new Error('Trình duyệt chặn cửa sổ. Cho phép popup hoặc dùng Chrome hỗ trợ PiP.');error('Trình duyệt không hỗ trợ Document PiP; cửa sổ thường không bảo đảm luôn nổi.');}
    const doc=state.pip.document;doc.head.replaceChildren();doc.body.replaceChildren();
    doc.documentElement.lang='vi';doc.title='Phụ đề nổi · Anh → Việt';

    const link=doc.createElement('link');link.rel='stylesheet';link.href='/floating.css';
    const style=doc.createElement('style');
    if(floatingCssCache)style.textContent=floatingCssCache;
    doc.head.append(link,style);
    fetch('/floating.css').then(r=>r.text()).then(t=>{floatingCssCache=t;style.textContent=t;}).catch(()=>{});

    doc.body.innerHTML='<header><strong><span class="live-dot"></span>Phiên dịch trực tiếp · EN → VI</strong><button id="stop" type="button">Dừng thu</button></header><div id="state" role="status"></div><button id="pip-share" type="button">Chọn tab có âm thanh</button><main class="pip-stage"><p id="en"></p><p id="vi"></p><p id="draft-bar" class="draft-bar"></p></main><p id="pip-error" role="alert"></p><footer><button id="return" type="button">Về trang dịch</button></footer>';
    doc.getElementById('stop').onclick=()=>stopCapture();
    doc.getElementById('pip-share').onclick=()=>startCapture('tab');
    doc.getElementById('return').onclick=()=>window.focus();
    const pipWindow=state.pip;
    pipWindow.addEventListener('pagehide',()=>{if(state.pip===pipWindow){state.pip=null;el('pip').textContent='Mở lại phụ đề nổi';el('pip-hint').textContent='Cửa sổ nổi đã đóng. Âm thanh vẫn tiếp tục được xử lý; bấm Mở lại phụ đề nổi để xem.';}},{once:true});
    el('pip').textContent='Đưa phụ đề nổi lên trước';
    el('pip-hint').textContent='Chọn tab có âm thanh trong cửa sổ nổi và bật Chia sẻ âm thanh tab. Có thể kéo cửa sổ tới góc màn hình, đổi kích thước hoặc cỡ chữ.';
    render();
  }catch(e){error(e.message);}
}
el('share').onclick=()=>startCapture('tab');el('mic').onclick=()=>startCapture('mic');el('stop').onclick=()=>stopCapture();el('pip').onclick=()=>openPip();
el('engine-mode')?.addEventListener('change',e=>{state.engineMode=e.target.value;render();});
el('demo-start').onclick=async()=>{
  const video=el('demo-video');
  if(video.ended)video.currentTime=0;
  if(state.capturing&&state.kind==='video'){
    if(video.paused)await video.play().catch(e=>error('Không phát được video: '+e.message));
    return;
  }
  startCapture('video');
};
el('video-fullscreen').onclick=async()=>{
  try{
    if(document.fullscreenElement)await document.exitFullscreen();
    else await el('video-stage').requestFullscreen();
  }catch(e){error('Không mở được toàn màn hình: '+e.message);}
};
setInterval(()=>{
  renderVideoCaption();
  if(state.activeRow&&!state.activeRow.isFinal){
    const ageMs=performance.now()-(state.activeRow.updatedAt||0);
    if(LiveAudioCore.phraseReady(state.activeRow.words,false,ageMs)){
      state.activeRow.isFinal=true;
      const fin=state.activeRow;state.activeRow=null;
      triggerRowTranslation(fin);
    }
  }
  if(state.pendingWords.length&&(performance.now()-state.pendingSince>=400)){
    consumePendingWords(false);
  }
},250);
el('demo-video').addEventListener('ended',()=>{if(state.kind==='video')stopCapture();});
el('demo-video').addEventListener('play',()=>{if(state.ready&&!state.capturing&&!state.stopping)startCapture('video');});
el('demo-video').addEventListener('pause',()=>{if(state.capturing&&state.kind==='video'&&!state.stopping)stopCapture();});
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
    if(!info.live_audio_enabled)throw new Error('Server đang chạy bản cũ. Nhấn Ctrl+C ở cửa sổ server rồi mở lại studio.cmd.');
    if(!info.incremental_asr_enabled)throw new Error('Cần khởi động lại server để bật ASR tăng dần: Ctrl+C rồi mở studio.cmd.');
    if(!info.configured)throw new Error('Server chưa cấu hình provider/khóa dịch. Chạy studio.cmd để dùng local hoặc studio.cmd gemini để nhập khóa.');
    state.model=info.model||state.model;el('config').textContent=`Provider: ${info.provider} · Model: ${info.model||'text demo'} · ASR local · OCR chưa bật`;
    el('state').textContent='Đang khởi động ASR local…';render();
    try{await requestJSON('/api/live/warmup',{method:'POST'});}catch(wErr){console.warn('Warmup non-blocking:',wErr);}
    state.ready=true;el('state').textContent='Sẵn sàng phát video hoặc chia sẻ tab';render();
  }catch(e){error(e.message);el('state').textContent='Chưa sẵn sàng: '+e.message;render();}
})();
