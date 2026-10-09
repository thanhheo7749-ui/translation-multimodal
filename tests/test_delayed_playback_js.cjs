const assert=require('node:assert/strict');
const {DelayedPlayer}=require('../frontend/delayed-playback.js');
class Video{
  constructor(){this.currentTime=0;this.duration=60;this.paused=true;this.ended=false;this.readyState=4;this.playbackRate=1;this.listeners={};}
  addEventListener(n,f){(this.listeners[n]??=[]).push(f);}
  removeEventListener(n,f){this.listeners[n]=(this.listeners[n]||[]).filter(x=>x!==f);}
  event(n){for(const f of [...this.listeners[n]||[]])f();}
  async play(){if(this.paused){this.paused=false;this.event('play');}}
  pause(){if(!this.paused){this.paused=true;this.event('pause');}}
}
(async()=>{
  const input=new Video(),output=new Video();let drained=0,seeks=0;
  const p=new DelayedPlayer({input,output,delaySec:4,autoTick:false,onInputEnded:()=>drained++,onSeek:()=>seeks++});
  await p.start();assert.equal(input.paused,false);assert.equal(output.paused,true);
  input.currentTime=3.9;await p.tick();assert.equal(output.paused,true);
  input.currentTime=4.1;await p.tick();assert.equal(output.paused,false);assert.equal(p.phase,'playing');
  output.pause();assert.equal(input.paused,true);assert.equal(p.phase,'paused');
  await output.play();await Promise.resolve();assert.equal(input.paused,false);
  input.currentTime=20;output.currentTime=10;await p.tick();assert.equal(input.paused,true,'source must not run arbitrarily ahead of viewer');
  output.currentTime=16;await p.tick();assert.equal(input.paused,false);
  input.currentTime=60;input.ended=true;input.event('ended');assert.equal(drained,1);assert.equal(output.paused,false,'drain must keep viewer AV playing');
  output.currentTime=60;output.ended=true;output.event('ended');assert.equal(p.phase,'ended');
  p.destroy();assert.equal(input.paused,true);assert.equal(output.paused,true);
  const a=new Video(),b=new Video();b.currentTime=30;
  const q=new DelayedPlayer({input:a,output:b,delaySec:6,autoTick:false,onSeek:()=>seeks++});
  await q.start();assert.equal(a.currentTime,30);assert.equal(b.currentTime,30);
  b.event('seeking');assert.equal(seeks,1);assert.equal(a.paused,true);assert.equal(b.paused,true);
  q.destroy();
  console.log('Delayed playback: buffering, independent clocks, pause/resume, bounded lead, tail drain and seek passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
