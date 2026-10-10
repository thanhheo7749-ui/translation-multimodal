const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const {Segmenter,BoundedQueue,RollingAudio,StableWords,captionAt,CaptionPresenter}=require('../frontend/live-core.js');
function packet(value=0){return new Int16Array(320).fill(value);}
const quiet=new Segmenter();for(let i=0;i<150;i++)assert.equal(quiet.push(packet(),0,i*20),null);
assert.ok(quiet.preSize<=1600);assert.equal(quiet.flush(),null);
const continuous=new Segmenter({targetMs:2500});let jobs=[];
for(let i=0;i<250;i++){const job=continuous.push(packet(4000),.1,i*20);if(job){assert.ok(job.endSec<=(i+1)*.02+1e-9);jobs.push(job);}}
assert.ok(jobs.length>=2);assert.equal(jobs[0].pcm.length,40000);assert.ok(jobs[1].overlapSec>0);
const pauses=new Segmenter({targetMs:4000,pauseMs:500,minMs:800});let cut=null;
for(let i=0;i<30;i++)cut=pauses.push(packet(4000),.1,i*20)||cut;
for(let i=0;i<25;i++)cut=pauses.push(packet(),0,(30+i)*20)||cut;
assert.ok(cut);assert.equal(cut.pcm.length,17600);
const tail=new Segmenter();for(let i=0;i<30;i++)tail.push(packet(4000),.1,i*20);
assert.equal(tail.flush().pcm.length,9600);
// Short pauses inside a phrase must not split the default quality mode.
const phrase=new Segmenter();let phraseCut=null;
for(let i=0;i<100;i++)assert.equal(phrase.push(packet(4000),.1,i*20),null);
for(let i=0;i<25;i++)assert.equal(phrase.push(packet(),0,(100+i)*20),null);
for(let i=0;i<100;i++)assert.equal(phrase.push(packet(4000),.1,(125+i)*20),null);
for(let i=0;i<40;i++)phraseCut=phrase.push(packet(),0,(225+i)*20)||phraseCut;
assert.ok(phraseCut);assert.equal(phraseCut.endSec,5.3);
const longPhrase=new Segmenter();let longCut=null;
for(let i=0;i<400;i++)longCut=longPhrase.push(packet(4000),.1,i*20)||longCut;
assert.equal(longCut.endSec,8);
const queue=new BoundedQueue(3);queue.push(1);queue.push(2);queue.push(3);assert.equal(queue.push(4),1);assert.deepEqual(queue.items,[2,3,4]);
function checkWorklet(rate){
  let Processor;const messages=[];
  class Base{constructor(){this.port={postMessage:message=>messages.push(message)};}}
  const context={AudioWorkletProcessor:Base,sampleRate:rate,registerProcessor:(_,type)=>Processor=type,ArrayBuffer,DataView,Math};
  vm.runInNewContext(fs.readFileSync(require.resolve('../frontend/pcm-worklet.js'),'utf8'),context);
  const processor=new Processor();
  for(let offset=0;offset<rate;offset+=128){const length=Math.min(128,rate-offset);const output=new Float32Array(length).fill(1);processor.process([[new Float32Array(length).fill(.25)]],[[output]]);assert.ok(output.every(value=>value===0));}
  processor.port.onmessage({data:'flush'});
  const pcm=messages.filter(m=>m.pcm);assert.equal(pcm.reduce((n,m)=>n+m.pcm.byteLength/2,0),16000);
  for(const message of pcm){assert.ok(Math.abs(message.rms-.25)<1e-8);assert.equal(new DataView(message.pcm).getInt16(0,true),8192);}
}
checkWorklet(16000);checkWorklet(44100);checkWorklet(48000);
const rolling=new RollingAudio();const snapshots=[];
for(let i=0;i<1000;i++){const r=rolling.push(packet(4000),.1,i*20);if(r){assert.ok(r.endSec<=(i+1)*.02+1e-9);assert.ok(r.pcm.length<=192000);snapshots.push(r);}}
assert.ok(snapshots.length>=8);assert.equal(snapshots[0].endSec,2.5);assert.ok(snapshots[1].startSec<snapshots[0].endSec);assert.equal(rolling.flush().final,true);
rolling.trimBefore(18);assert.equal(rolling.size,32000);assert.equal(rolling.flush().startSec,18);
const stable=new StableWords();
const words=[{text:'My',start:0,end:.3},{text:'release',start:.3,end:.8}];
assert.equal(stable.update(words).committed.length,0);
const revised=[words[0],{text:'relationship',start:.3,end:1}];
assert.deepEqual(stable.update(revised).committed.map(w=>w.text),['My']);
assert.deepEqual(stable.update(revised).committed.map(w=>w.text),['relationship']);
assert.equal(stable.update(revised,true).committed.length,0);
assert.equal(stable.update([{text:'relationship',start:.31,end:1.2}],true).committed.length,0,'timestamp jitter must not repeat a committed word');
assert.equal(stable.update([{text:'relationship',start:1.3,end:1.9}],true).committed.length,1,'a genuinely repeated word must survive');
const rows=[{id:1,status:'ok',vi:'old',mediaStart:1,mediaEnd:3},{id:2,status:'ok',vi:'new',mediaStart:7,mediaEnd:9}];
assert.equal(captionAt(rows,0),null);assert.equal(captionAt(rows,4).vi,'old');assert.equal(captionAt(rows,6),null);assert.equal(captionAt(rows,8).vi,'new');assert.equal(captionAt(rows,12),null);
const presenter=new CaptionPresenter();rows[0].displayedAt=10000;rows[1].displayedAt=10100;
assert.equal(presenter.select([rows[0]],12,10000).id,1);
assert.equal(presenter.select(rows,12,10100).id,1,'minimum reading time prevents flicker');
assert.equal(presenter.select(rows,12,10900).id,2);
rows[0].displayedAt=12000;
assert.equal(presenter.select(rows,12,12000).id,2,'late old response must not roll back');
assert.equal(presenter.select(rows,12,17000),null,'old caption expires and does not reappear');
console.log('Live audio JS checks passed: causal chunks, silence, flush, bounded queue, PCM rates and no audio replay.');
