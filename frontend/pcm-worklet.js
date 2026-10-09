class PCM16kProcessor extends AudioWorkletProcessor {
  constructor(){
    super();this.ratio=sampleRate/16000;this.sum=0;this.weight=0;this.packet=[];this.energy=0;
    this.port.onmessage=e=>{if(e.data==='flush'){this.emit();this.port.postMessage({flushed:true});}};
  }
  emit(){
    if(!this.packet.length)return;
    const buffer=new ArrayBuffer(this.packet.length*2),view=new DataView(buffer);
    this.packet.forEach((sample,i)=>view.setInt16(i*2,Math.round(Math.max(-1,Math.min(1,sample))*(sample<0?32768:32767)),true));
    this.port.postMessage({pcm:buffer,rms:Math.sqrt(this.energy/this.packet.length)},[buffer]);
    this.packet=[];this.energy=0;
  }
  process(inputs,outputs){
    for(const output of outputs)for(const channel of output)channel.fill(0);
    const channels=inputs[0];if(!channels||!channels.length)return true;
    for(let i=0;i<channels[0].length;i++){
      let value=0;for(const channel of channels)value+=channel[i];value/=channels.length;
      let remaining=1;
      while(remaining>1e-9){
        const take=Math.min(remaining,this.ratio-this.weight);
        this.sum+=value*take;this.weight+=take;remaining-=take;
        if(this.weight>=this.ratio-1e-9){
          const sample=this.sum/this.ratio;this.packet.push(sample);this.energy+=sample*sample;
          this.sum=0;this.weight=0;if(this.packet.length>=320)this.emit();
        }
      }
    }
    return true;
  }
}
registerProcessor('pcm16k',PCM16kProcessor);
