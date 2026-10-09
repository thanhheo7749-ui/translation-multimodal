(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.CaptionTiming = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // Every input must use seconds on the SAME client clock. Media timestamps
  // must first be mapped through the current playback epoch by the caller.
  function measureCue({sourceStart, sourceEnd, readyAt, shownAt, viewerDelay}) {
    if (![sourceStart, sourceEnd, readyAt, shownAt, viewerDelay].every(Number.isFinite))
      throw new Error('Missing cue clock');
    if (sourceEnd < sourceStart || shownAt < readyAt || viewerDelay < 0)
      throw new Error('Invalid cue order');
    return {
      readyFromStart: readyAt - sourceStart,
      readyFromEnd: readyAt - sourceEnd,
      displayFromEnd: shownAt - sourceEnd,
      visibleStartOffset: shownAt - (sourceStart + viewerDelay)
    };
  }

  class Trace {
    constructor(sessionId, now = () => performance.now()) {
      this.sessionId = sessionId;
      this.now = now;
      this.events = [];
    }

    // Client timestamps use milliseconds; sourceStart/sourceEnd remain media
    // seconds. Backend durations are separate fields, never client timestamps.
    record(type, fields = {}) {
      const event = {...fields, type, sessionId:this.sessionId, clientNowMs:this.now()};
      this.events.push(event);
      return event;
    }
  }

  return {measureCue, Trace};
}));
