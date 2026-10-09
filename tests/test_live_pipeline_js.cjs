const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const elements=new Map();
function element(){return {textContent:'',style:{},disabled:false,hidden:false,currentTime:0,value:'1500',append(){},replaceChildren(){},addEventListener(){}};}
const calls=[],translations=[];
let now=5000;
const context=vm.createContext({
  LiveAudioCore:require('../frontend/live-core.js'),
  document:{getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},createElement:element},
  window:{addEventListener(){}},navigator:{},performance:{now:()=>now},
  setInterval(){},setTimeout,clearTimeout,console,
  fetch:async(path,options)=>{
    calls.push(path);
    if(path==='/api/live/asr')return {ok:true,json:async()=>({asr_latency_ms:20,words:[{text:'Hello.',start:0,end:.6}],text:'Hello.'})};
    return new Promise(resolve=>translations.push(()=>resolve({ok:true,json:async()=>({translated_text:'Xin chào.',latency_ms:500,model:'test',provider:'test'})})));
  }
});
vm.runInContext(fs.readFileSync(require.resolve('../frontend/live.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  run("state.ready=true;state.capturing=true;state.kind='mic';");
  run("enqueue({pcm:new Int16Array(16000),startSec:0,endSec:1,receivedAt:1000,final:true});");
  await tick();await tick();
  assert.equal(translations.length,1);
  run("enqueue({pcm:new Int16Array(16000),startSec:2,endSec:3,receivedAt:3000,final:true});");
  await tick();await tick();
  assert.equal(calls.filter(p=>p==='/api/live/asr').length,2,'ASR must continue while MT is unresolved');
  assert.equal(translations.length,2,'two MT requests should overlap');
  run("enqueue({pcm:new Int16Array(16000),startSec:4,endSec:5,receivedAt:5000,final:true});");
  await tick();await tick();
  assert.equal(translations.length,2,'MT concurrency must be bounded');
  assert.equal(run('state.mtQueue.length'),1);
  translations.splice(1,1)[0]();await tick();await tick();
  assert.equal(translations.length,2,'a released slot should process the queued translation');
  translations.shift()();await tick();await tick();
  translations.shift()();await tick();await tick();
  assert.equal(run("state.rows.filter(r=>r.status==='ok').length"),3);
  assert.equal(run('state.translating'),0);
  run("state.kind='video';state.rows=[{id:1,status:'ok',vi:'Câu cũ',mediaStart:1,mediaEnd:3,displayedAt:5000}];document.getElementById('demo-video').currentTime=10;renderVideoCaption();");
  assert.equal(elements.get('video-captions').hidden,false,'a late result should still be readable, with explicit lag');
  assert.equal(elements.get('caption-vi').textContent,'Câu cũ');
  assert.match(elements.get('caption-note').textContent,/7,0/);
  now=6000;
  run("state.rows.push({id:2,status:'ok',vi:'Câu mới',mediaStart:6,mediaEnd:8,displayedAt:6000});renderVideoCaption();");
  assert.equal(elements.get('caption-vi').textContent,'Câu mới');
  now=7000;
  run("state.rows[0].displayedAt=7000;renderVideoCaption();");
  assert.equal(elements.get('caption-vi').textContent,'Câu mới','old replies must not move captions backwards');
  run('state.captionInvalid=true;renderVideoCaption();');
  assert.equal(elements.get('video-captions').hidden,true,'seeking must invalidate captions');
  console.log('Pipeline checks passed: bounded parallel MT, ASR overlap, readable late captions, no rollback and seek invalidation.');
})().catch(error=>{console.error(error);process.exitCode=1;});
