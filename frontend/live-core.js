(function (root) {
  class Segmenter {
    constructor({targetMs = 8000, pauseMs = 800, minMs = 2000, rate = 16000, threshold = 0.006} = {}) {
      this.targetMs=targetMs;this.pauseMs=pauseMs;this.minMs=minMs;this.rate=rate;this.threshold=threshold;
      this.total=0;this.pre=[];this.preSize=0;this.parts=[];this.size=0;this.silence=0;this.active=false;this.lastEnd=0;this.receivedAt=0;
    }
    push(pcm, rms, receivedAt) {
      this.total+=pcm.length;this.receivedAt=receivedAt;
      if(!this.active){
        if(rms<this.threshold){this.keepPre(pcm);return null;}
        this.parts=this.pre.slice();this.size=this.preSize;this.start=this.total-pcm.length-this.preSize;
        this.pre=[];this.preSize=0;this.active=true;this.silence=0;
      }
      this.parts.push(pcm);this.size+=pcm.length;
      this.silence=rms<this.threshold?this.silence+pcm.length:0;
      const duration=this.size/this.rate*1000;
      if((duration>=this.minMs&&this.silence/this.rate*1000>=this.pauseMs)||duration>=this.targetMs)return this.finish();
      return null;
    }
    keepPre(pcm){
      this.pre.push(pcm);this.preSize+=pcm.length;
      while(this.pre.length>1&&this.preSize>this.rate*.1){this.preSize-=this.pre.shift().length;}
    }
    finish(){
      if(!this.active)return null;
      const pcm=new Int16Array(this.size);let at=0;
      for(const part of this.parts){pcm.set(part,at);at+=part.length;}
      const row={pcm,startSec:this.start/this.rate,endSec:this.total/this.rate,receivedAt:this.receivedAt,
        overlapSec:Math.max(0,this.lastEnd-this.start)/this.rate};
      this.lastEnd=this.total;this.active=false;this.parts=[];this.size=0;this.silence=0;
      // Keep 100ms at boundaries to reduce clipped words; record overlap explicitly.
      this.keepPre(pcm.slice(-Math.round(this.rate*.1)));
      return row;
    }
    flush(){return this.size>=this.rate*.1?this.finish():null;}
  }
  class BoundedQueue{
    constructor(limit=3){this.items=[];this.limit=limit;}
    push(item){const dropped=this.items.length>=this.limit?this.items.shift():null;this.items.push(item);return dropped;}
    shift(){return this.items.shift();}
    get length(){return this.items.length;}
  }
  // Overlapping snapshots contain only audio received so far. Replacing a queued
  // snapshot does not discard its audio if the newer window still contains it.
  class RollingAudio {
    constructor({rate=16000,windowSec=12,hopSec=1.5,pauseSec=.8,threshold=.006}={}){
      Object.assign(this,{rate,windowSec,hopSec,pauseSec,threshold});
      this.total=0;this.parts=[];this.size=0;this.lastEmit=0;this.silence=0;this.active=false;this.receivedAt=0;
    }
    push(pcm,rms,receivedAt){
      this.total+=pcm.length;this.parts.push(pcm);this.size+=pcm.length;this.receivedAt=receivedAt;
      while(this.size>this.rate*this.windowSec){const excess=this.size-this.rate*this.windowSec,first=this.parts[0];if(first.length<=excess){this.size-=this.parts.shift().length;}else{this.parts[0]=first.slice(excess);this.size-=excess;}}
      if(rms>=this.threshold){this.active=true;this.silence=0;}else this.silence+=pcm.length;
      if(!this.active)return null;
      const final=this.silence>=this.pauseSec*this.rate;
      if(final){this.active=false;return this.snapshot(true);}
      if(this.total-this.lastEmit>=this.hopSec*this.rate&&this.size>=this.rate*2.5)return this.snapshot(false);
      return null;
    }
    snapshot(final){
      if(!this.size)return null;
      const pcm=new Int16Array(this.size);let at=0;for(const part of this.parts){pcm.set(part,at);at+=part.length;}
      this.lastEmit=this.total;
      return {pcm,startSec:(this.total-this.size)/this.rate,endSec:this.total/this.rate,receivedAt:this.receivedAt,final,overlapSec:0};
    }
    trimBefore(seconds){
      const keep=Math.max(0,this.total-Math.floor(seconds*this.rate));
      while(this.size>keep&&this.parts.length){const excess=this.size-keep,first=this.parts[0];if(first.length<=excess)this.size-=this.parts.shift().length;else{this.parts[0]=first.slice(excess);this.size-=excess;}}
    }
    flush(){return this.snapshot(true);}
  }
  class StableWords {
    constructor(){this.previous=[];this.committedEnd=-1;this.tail=[];}
    update(words,final=false){
      const normalized=w=>w.text.toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');
      let fresh=words.filter(w=>w.end>this.committedEnd+.04);
      // Word alignments can move between overlapping decodes. Remove only a
      // matching committed suffix whose time still overlaps the committed word.
      for(let n=Math.min(this.tail.length,fresh.length);n>0;n--){
        const suffix=this.tail.slice(-n);
        if(suffix.every((w,i)=>normalized(w)===normalized(fresh[i])&&Math.abs(w.end-fresh[i].end)<.5&&fresh[i].start<w.end-.04)){fresh=fresh.slice(n);break;}
      }
      let count=0;
      if(final)count=fresh.length;
      else while(count<fresh.length&&count<this.previous.length&&normalized(fresh[count])===normalized(this.previous[count])&&Math.abs(fresh[count].start-this.previous[count].start)<1){count++;}
      const committed=fresh.slice(0,count);this.previous=fresh.slice(count);
      if(committed.length){this.committedEnd=committed[committed.length-1].end;this.tail=this.tail.concat(committed).slice(-12);}
      return {committed,draft:this.previous};
    }
  }
  function captionAt(rows,mediaTime,graceSec=2.5){
    return rows.filter(r=>r.status==='ok'&&r.vi&&Number.isFinite(r.mediaStart)&&Number.isFinite(r.mediaEnd)&&mediaTime>=r.mediaStart&&mediaTime<=r.mediaEnd+graceSec).sort((a,b)=>b.mediaEnd-a.mediaEnd||b.id-a.id)[0]||null;
  }
  class CaptionPresenter {
    constructor(){this.current=null;this.since=0;this.lastId=0;}
    select(rows,mediaTime,now){
      const candidate=rows.filter(r=>r.status==='ok'&&r.vi&&r.id>this.lastId&&Number.isFinite(r.mediaStart)&&mediaTime>=r.mediaStart&&Number.isFinite(r.displayedAt)&&now-r.displayedAt<6000).sort((a,b)=>b.id-a.id)[0];
      // Hold a readable caption briefly, then advance directly to the latest
      // result. Never replay an older response arriving out of order.
      if(candidate&&(!this.current||now-this.since>=900)){
        this.current=candidate;this.lastId=candidate.id;this.since=now;
      }
      if(this.current&&now-this.since>=6000)this.current=null;
      return this.current;
    }
  }
  const api={Segmenter,BoundedQueue,RollingAudio,StableWords,captionAt,CaptionPresenter};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LiveAudioCore=api;
})(typeof globalThis!=='undefined'?globalThis:this);
