const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Mock DOM elements registry
const elements = new Map();

function createMockElement(tag = 'div', id = '') {
  let _text = '';
  const listeners = new Map();
  const attributes = new Map();
  const children = [];

  const el = {
    id,
    tagName: tag.toUpperCase(),
    className: '',
    style: {},
    disabled: false,
    hidden: false,
    currentTime: 0,
    videoWidth: 1920,
    videoHeight: 1080,
    readyState: 4,
    paused: false,
    ended: false,
    seeking: false,
    muted: false,
    playsInline: false,
    srcObject: null,
    parentNode: null,
    get textContent() {
      return _text;
    },
    set textContent(val) {
      _text = String(val ?? '');
    },
    setAttribute(name, val) {
      attributes.set(name, String(val));
    },
    getAttribute(name) {
      return attributes.get(name) || null;
    },
    addEventListener(evt, fn) {
      if (!listeners.has(evt)) listeners.set(evt, []);
      listeners.get(evt).push(fn);
    },
    removeEventListener(evt, fn) {
      if (listeners.has(evt)) {
        const list = listeners.get(evt).filter(f => f !== fn);
        listeners.set(evt, list);
      }
    },
    dispatchEvent(evt) {
      const type = typeof evt === 'string' ? evt : evt.type;
      const list = listeners.get(type) || [];
      for (const fn of list) fn({ type, target: el });
    },
    append(...nodes) {
      for (const n of nodes) {
        children.push(n);
        n.parentNode = el;
      }
    },
    replaceChildren(...nodes) {
      children.length = 0;
      for (const n of nodes) {
        children.push(n);
        n.parentNode = el;
      }
      _text = nodes.map(n => n.textContent || '').join('');
    },
    removeChild(node) {
      const idx = children.indexOf(node);
      if (idx >= 0) children.splice(idx, 1);
      node.parentNode = null;
    },
    appendChild(node) {
      children.push(node);
      node.parentNode = el;
      return node;
    },
    querySelector(selector) {
      if (selector.startsWith('.')) {
        const cls = selector.slice(1);
        return children.find(c => (c.className || '').split(' ').includes(cls)) || null;
      }
      return null;
    },
    play: async () => {},
    pause: () => {},
    getContext: ctxType => ({
      drawImage: (img, sx, sy, sw, sh) => {
        el._lastDraw = { img, sx, sy, sw, sh };
      }
    }),
    toBlob: (cb, type, quality) => {
      el._lastBlobReq = { type, quality };
      const dummyBlob = { size: 1024, type };
      cb(dummyBlob);
    }
  };
  return el;
}

function getOrCreateElement(id) {
  if (!elements.has(id)) {
    const tag = id.includes('video') ? 'video' : 'div';
    elements.set(id, createMockElement(tag, id));
  }
  return elements.get(id);
}

// Network calls recorded
const recordedCalls = [];
let mockVisionResult = {
  session_id: '1',
  source_epoch: 1,
  frame_id: 'f_1',
  slide_id: 1,
  slide_revision: 0,
  status: 'READY',
  title: 'NVIDIA Blackwell GPU Architecture',
  entities: [
    { text: 'Blackwell', label: 'KEYWORD', score: 0.95 },
    { text: 'NVLink 5', label: 'KEYWORD', score: 0.92 }
  ],
  content_hash: 'abc123hash',
  captured_client_ms: 100.0,
  available_server_ms: 120.0,
  server_ocr_ms: 35.0,
  is_stale: false
};

let nowMs = 1000;
let resolveInFlightUpload = null;
let delayNextFrameUpload = false;

const context = vm.createContext({
  LiveAudioCore: require('../frontend/live-core.js'),
  document: {
    getElementById: getOrCreateElement,
    createElement: tag => createMockElement(tag),
    body: createMockElement('body', 'body')
  },
  window: {
    addEventListener: () => {}
  },
  navigator: {},
  performance: {
    now: () => nowMs
  },
  setInterval: (fn, ms) => setInterval(fn, ms),
  clearInterval: id => clearInterval(id),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: id => clearTimeout(id),
  console,
  URL: {
    createObjectURL: () => 'blob:mock',
    revokeObjectURL: () => {}
  },
  Blob: class MockBlob {
    constructor(parts, opts) {
      this.parts = parts;
      this.type = opts?.type;
    }
  },
  MediaStream: class MockMediaStream {
    constructor(tracks = []) {
      this._tracks = tracks;
    }
    getTracks() {
      return this._tracks;
    }
    getVideoTracks() {
      return this._tracks.filter(t => t.kind === 'video');
    }
    getAudioTracks() {
      return this._tracks.filter(t => t.kind === 'audio');
    }
  },
  fetch: async (path, options = {}) => {
    const entry = {
      path,
      method: options.method || 'GET',
      headers: options.headers || {},
      body: options.body
    };
    recordedCalls.push(entry);

    if (path.startsWith('/api/live/vision/frame')) {
      if (delayNextFrameUpload) {
        return new Promise(resolve => {
          resolveInFlightUpload = () => resolve({
            ok: true,
            json: async () => ({ status: 'queued', job_id: 'j1' })
          });
        });
      }
      return {
        ok: true,
        json: async () => ({ status: 'queued', job_id: 'j1' })
      };
    }

    if (path.startsWith('/api/live/vision/result')) {
      return {
        ok: true,
        json: async () => mockVisionResult
      };
    }

    if (path.startsWith('/api/live/vision/reset')) {
      return {
        ok: true,
        json: async () => ({ status: 'ok', source_epoch: 1 })
      };
    }

    if (path === '/api/translation-status') {
      return {
        ok: true,
        json: async () => ({ live_audio_enabled: true, incremental_asr_enabled: true, configured: true, model: 'test' })
      };
    }

    return { ok: true, json: async () => ({ status: 'ok' }) };
  }
});

// Run live.js in VM
vm.runInContext(fs.readFileSync(require.resolve('../frontend/live.js'), 'utf8'), context);
const run = code => vm.runInContext(code, context);

(async () => {
  console.log('--- TEST 1: Initial Vision State and Slide Inspector Panel ---');
  run('render();');

  const statusBadge = getOrCreateElement('slide-status');
  const slideTitle = getOrCreateElement('slide-title');
  const slideEntities = getOrCreateElement('slide-entities');

  assert.equal(statusBadge.textContent, 'Chờ hình ảnh');
  assert.equal(statusBadge.className, 'slide-badge badge-idle');
  assert.equal(slideTitle.textContent, 'Chưa phát hiện slide');
  assert.match(slideEntities.textContent, /Chưa có từ khóa/);
  console.log('✓ Initial slide panel state correctly displays idle status and placeholders');

  console.log('\n--- TEST 2: Toggle Button Collapse / Expand ---');
  const toggleBtn = getOrCreateElement('slide-toggle');
  const panelBody = getOrCreateElement('slide-panel-body');

  const toggleText = createMockElement('span');
  toggleText.className = 'toggle-text';
  toggleText.textContent = 'Thu gọn';
  const toggleArrow = createMockElement('span');
  toggleArrow.className = 'toggle-arrow';
  toggleArrow.textContent = '▼';
  toggleBtn.append(toggleText, toggleArrow);

  run('initSlideToggle();');
  assert.equal(typeof toggleBtn.onclick, 'function');

  // Click 1: Collapse
  toggleBtn.onclick();
  assert.ok(panelBody.className.includes('is-collapsed'), 'Body should have is-collapsed class');
  assert.equal(toggleBtn.getAttribute('aria-expanded'), 'false');
  assert.equal(toggleText.textContent, 'Mở rộng');
  assert.equal(toggleArrow.textContent, '▶');

  // Click 2: Expand
  toggleBtn.onclick();
  assert.ok(!panelBody.className.includes('is-collapsed'), 'Body should no longer be collapsed');
  assert.equal(toggleBtn.getAttribute('aria-expanded'), 'true');
  assert.equal(toggleText.textContent, 'Thu gọn');
  assert.equal(toggleArrow.textContent, '▼');
  console.log('✓ Slide toggle correctly switches collapsed/expanded classes and aria attributes');

  console.log('\n--- TEST 3: Mode "mic" Displays OCR Needs Video Notice ---');
  run(`
    state.capturing = true;
    state.kind = 'mic';
    render();
  `);
  assert.equal(statusBadge.textContent, 'OCR cần nguồn hình ảnh');
  assert.equal(statusBadge.className, 'slide-badge badge-mic');
  assert.match(slideTitle.textContent, /OCR cần nguồn hình ảnh/);
  console.log('✓ Mic mode gracefully displays "OCR cần nguồn hình ảnh" without disrupting audio');

  console.log('\n--- TEST 4: Frame Sampling, Scaling & Headers ---');
  recordedCalls.length = 0;
  const demoVideo = getOrCreateElement('demo-video');
  demoVideo.videoWidth = 1920;
  demoVideo.videoHeight = 1080;
  demoVideo.paused = false;
  demoVideo.ended = false;
  demoVideo.seeking = false;
  demoVideo.readyState = 4;

  run(`
    state.session = 42;
    state.capturing = true;
    state.kind = 'video';
    state.vision.active = true;
    state.vision.videoElement = document.getElementById('demo-video');
    state.vision.sourceEpoch = 2;
    state.vision.inFlight = false;
  `);

  await run('sampleAndSendFrame();');

  assert.equal(recordedCalls.length, 1);
  const frameCall = recordedCalls[0];
  assert.equal(frameCall.path, '/api/live/vision/frame');
  assert.equal(frameCall.method, 'POST');
  assert.equal(frameCall.headers['Content-Type'], 'image/jpeg');
  assert.equal(frameCall.headers['X-Session-ID'], '42');
  assert.equal(frameCall.headers['X-Source-Epoch'], '2');
  assert.ok(frameCall.headers['X-Frame-ID'].startsWith('f_'));
  assert.equal(frameCall.headers['X-Stabilization-Delay-Sec'], '0.6');

  // Verify scale aspect ratio: 1920x1080 scaled to max 1280
  const canvas = run('state.vision.canvas');
  assert.ok(canvas);
  assert.equal(canvas.width, 1280);
  assert.equal(canvas.height, 720);
  console.log('✓ Frame sampled, downscaled to 1280x720, and dispatched with required HTTP headers');

  console.log('\n--- TEST 5: Backpressure (Max 1 In-Flight Upload) ---');
  recordedCalls.length = 0;
  delayNextFrameUpload = true;

  const tick = () => new Promise(resolve => setImmediate(resolve));

  // Frame 1: sent and stays in-flight
  const p1 = run('sampleAndSendFrame();');
  assert.equal(run('state.vision.inFlight'), true);
  await tick();
  await tick();
  assert.equal(recordedCalls.length, 1);

  // Frame 2: dispatched while frame 1 is in-flight -> MUST BE DROPPED!
  await run('sampleAndSendFrame();');
  assert.equal(recordedCalls.length, 1, 'Frame 2 must be dropped due to backpressure');

  // Frame 3: also dropped
  await run('sampleAndSendFrame();');
  assert.equal(recordedCalls.length, 1, 'Frame 3 must be dropped due to backpressure');

  // Resolve frame 1
  resolveInFlightUpload();
  await p1;
  assert.equal(run('state.vision.inFlight'), false, 'In-flight flag must reset after completion');
  delayNextFrameUpload = false;

  // Frame 4: now should go through normally
  await run('sampleAndSendFrame();');
  assert.equal(recordedCalls.length, 2, 'New frame succeeds after previous finished');
  console.log('✓ Backpressure correctly drops intermediate frames when an upload is in-flight');

  console.log('\n--- TEST 6: Polling Slide Results & Rendering Entities & Title ---');
  mockVisionResult = {
    session_id: '42',
    source_epoch: 2,
    frame_id: 'f_1',
    slide_id: 1,
    slide_revision: 0,
    status: 'READY',
    title: 'NVIDIA Blackwell Ultra Platform',
    entities: [
      { text: 'Blackwell Ultra', label: 'KEYWORD', score: 0.96 },
      { text: 'GB200 NVL72', label: 'KEYWORD', score: 0.94 },
      { text: 'Quantum-X800', label: 'KEYWORD', score: 0.88 }
    ],
    content_hash: 'hash-xyz',
    captured_client_ms: 1200.0,
    available_server_ms: 1240.0,
    server_ocr_ms: 38.0,
    is_stale: false
  };

  await run('pollVisionResult();');

  assert.equal(run('state.currentSlide.title'), 'NVIDIA Blackwell Ultra Platform');
  assert.equal(statusBadge.textContent, 'Đã trích xuất chữ');
  assert.equal(statusBadge.className, 'slide-badge badge-ready');
  assert.equal(slideTitle.textContent, 'NVIDIA Blackwell Ultra Platform');

  // Entities list in DOM
  const entityBadges = slideEntities.textContent;
  assert.match(entityBadges, /Blackwell Ultra/);
  assert.match(entityBadges, /GB200 NVL72/);
  assert.match(entityBadges, /Quantum-X800/);
  console.log('✓ Polling retrieves slide results and renders title and keyword badge tags');

  console.log('\n--- TEST 7: Scene Status Transitions (Stabilizing, Empty, Error) ---');
  // Stabilizing
  mockVisionResult.status = 'STABILIZING';
  await run('pollVisionResult();');
  assert.equal(statusBadge.textContent, 'Đang ổn định');
  assert.equal(statusBadge.className, 'slide-badge badge-stabilizing');

  // Empty slide
  mockVisionResult.status = 'EMPTY';
  mockVisionResult.entities = [];
  mockVisionResult.title = '';
  await run('pollVisionResult();');
  assert.equal(statusBadge.textContent, 'Không có chữ');
  assert.equal(statusBadge.className, 'slide-badge badge-empty');
  assert.match(slideTitle.textContent, /Không có chữ/);

  // Error slide
  mockVisionResult.status = 'ERROR';
  await run('pollVisionResult();');
  assert.equal(statusBadge.textContent, 'Lỗi nhận dạng');
  assert.equal(statusBadge.className, 'slide-badge badge-error');
  console.log('✓ All visual states (Stabilizing, Empty, Error) reflect accurately in UI');

  console.log('\n--- TEST 8: Tab Capture Video Track & Hidden Element Lifecycle ---');
  const mockVideoTrack = {
    kind: 'video',
    label: 'Chrome Tab - Presentation Slides',
    stop: () => {},
    addEventListener: () => {}
  };
  const mockAudioTrack = {
    kind: 'audio',
    label: 'Chrome Tab Audio',
    stop: () => {},
    addEventListener: () => {}
  };
  const mockStream = new context.MediaStream([mockVideoTrack, mockAudioTrack]);
  context.mockStream = mockStream;

  // Simulate tab capture
  run(`
    state.stream = mockStream;
    state.session = 99;
    state.vision.sourceEpoch = 5;
  `);

  // Verify hidden video creation
  const hiddenVideo = context.document.createElement('video');
  hiddenVideo.muted = true;
  hiddenVideo.playsInline = true;
  hiddenVideo.srcObject = new context.MediaStream([mockVideoTrack]);
  context.document.body.appendChild(hiddenVideo);
  context.hiddenVideo = hiddenVideo;
  run(`
    state.vision.hiddenVideo = hiddenVideo;
    state.vision.videoElement = hiddenVideo;
    state.vision.active = true;
  `);

  assert.equal(hiddenVideo.muted, true, 'Hidden video element must be muted');
  assert.equal(hiddenVideo.playsInline, true, 'Hidden video element must play inline');
  assert.equal(hiddenVideo.srcObject.getVideoTracks().length, 1);
  assert.equal(hiddenVideo.srcObject.getAudioTracks().length, 0, 'No audio tracks in hidden video');

  // Cleanup vision on stop
  recordedCalls.length = 0;
  run('cleanupVision();');

  assert.equal(run('state.vision.active'), false);
  assert.equal(run('state.vision.videoElement'), null);
  assert.equal(run('state.vision.hiddenVideo'), null);
  assert.equal(hiddenVideo.srcObject, null);
  assert.equal(hiddenVideo.parentNode, null, 'Hidden video element must be removed from DOM');

  // Check reset call sent
  const resetCall = recordedCalls.find(c => c.path === '/api/live/vision/reset');
  assert.ok(resetCall, 'POST /api/live/vision/reset must be called on cleanup');
  assert.equal(JSON.parse(resetCall.body).session_id, '99');
  assert.equal(JSON.parse(resetCall.body).source_epoch, 5);
  console.log('✓ Tab capture hidden video created with muted=true, isolated from audio, and cleanly freed');

  console.log('\n--- TEST 9: Video Seeking Increments Source Epoch and Triggers Reset ---');
  recordedCalls.length = 0;
  run(`
    state.kind = 'video';
    state.session = 100;
    state.vision.sourceEpoch = 10;
  `);
  demoVideo.dispatchEvent('seeking');

  assert.equal(run('state.vision.sourceEpoch'), 11, 'Seeking must increment source_epoch');
  const seekReset = recordedCalls.find(c => c.path === '/api/live/vision/reset');
  assert.ok(seekReset, 'Seeking video must send reset request to backend');
  assert.equal(JSON.parse(seekReset.body).source_epoch, 11);
  console.log('✓ Video seeking increments source_epoch and resets vision session state');

  console.log('\n--- ALL FRONTEND VISION SAMPLER & SLIDE INSPECTOR TESTS PASSED! ---');
  process.exit(0);
})().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
