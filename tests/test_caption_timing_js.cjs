const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {measureCue, Trace} = require('../frontend/caption-timing.js');

const cue = {sourceStart:10, sourceEnd:12, readyAt:13, shownAt:13, viewerDelay:3};
assert.deepEqual(measureCue(cue), {readyFromStart:3, readyFromEnd:1, displayFromEnd:1, visibleStartOffset:0});
assert.equal(measureCue({...cue, shownAt:15}).visibleStartOffset, 2);
assert.throws(() => measureCue({...cue, shownAt:11}), /Invalid cue order/);
assert.throws(() => measureCue({...cue, sourceEnd:9}), /Invalid cue order/);
assert.throws(() => measureCue({...cue, viewerDelay:-1}), /Invalid cue order/);
for (const field of Object.keys(cue)) {
  for (const invalid of [undefined, null, NaN, Infinity, '10']) {
    assert.throws(() => measureCue({...cue, [field]:invalid}), /Missing cue clock/);
  }
}
let now = 250;
const trace = new Trace('session-a', () => now++);
const event = trace.record('mt_returned', {segmentId:2, sourceStart:10, sourceEnd:12,
  type:'forged', sessionId:'forged', clientNowMs:-1});
assert.deepEqual(event, {segmentId:2, sourceStart:10, sourceEnd:12,
  type:'mt_returned', sessionId:'session-a', clientNowMs:250});
trace.record('cue_selected', {segmentId:2});
assert.equal(trace.events[1].clientNowMs, 251);
assert.equal(trace.events.length, 2);
const browser = vm.createContext({performance:{now:() => 100}});
vm.runInContext(fs.readFileSync(require.resolve('../frontend/caption-timing.js'), 'utf8'), browser);
assert.equal(new browser.CaptionTiming.Trace('browser').record('audio_received').clientNowMs, 100);
console.log('caption timing tests passed');
