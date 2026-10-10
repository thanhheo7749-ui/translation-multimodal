const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
let lastFetchPayload = null;
let lastFetchUrl = null;
let renderCalls = 0;
let renderTimelineCalls = 0;

function createElement(id = '') {
  let _text = '';
  const children = [];
  return {
    id,
    style: {},
    disabled: false,
    hidden: false,
    currentTime: 2.0,
    videoWidth: 1280,
    videoHeight: 720,
    value: 'local',
    className: '',
    get textContent() {
      return _text;
    },
    set textContent(val) {
      _text = String(val);
    },
    append(...nodes) {
      children.push(...nodes);
    },
    prepend(...nodes) {
      children.unshift(...nodes);
    },
    insertBefore(node, ref) {
      children.unshift(node);
    },
    replaceChildren(...args) {
      children.length = 0;
      if (args.length > 0) children.push(...args);
    },
    remove() {},
    addEventListener() {},
    querySelector() { return null; }
  };
}

const context = vm.createContext({
  assert,
  LiveAudioCore: require('../frontend/live-core.js'),
  document: {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, createElement(id));
      return elements.get(id);
    },
    createElement(tag) {
      return createElement();
    }
  },
  window: { addEventListener() {} },
  navigator: {},
  performance: { now: () => 1500 },
  setInterval() {},
  setTimeout,
  clearTimeout,
  console,
  fetch: async (url, options) => {
    lastFetchUrl = url;
    if (options && options.body) {
      try {
        lastFetchPayload = JSON.parse(options.body);
      } catch (e) {
        lastFetchPayload = null;
      }
    }
    return {
      ok: true,
      json: async () => ({
        status: 'ok',
        translated_text: 'Bản dịch thử nghiệm có ngữ cảnh slide.',
        latency_ms: 110,
        visual_context_available: true,
        visual_context_used: true,
        visual_context_id: 'ctx_test_1',
        visual_context_reason: 'context_selected',
        matched_entities: ['Blackwell']
      })
    };
  }
});

vm.runInContext(fs.readFileSync(require.resolve('../frontend/live.js'), 'utf8'), context);
const run = code => vm.runInContext(code, context);

async function runTests() {
  // Test 1: executeRowTranslation transmits source_epoch, segment_audio_start_ms, and segment_audio_end_ms
  await run(`(async () => {
    state.ready = true;
    state.session = 'sess_fe_test';
    state.vision = { active: true, sourceEpoch: 3 };
    state.engineMode = 'local';
    
    const row = {
      id: 1,
      session: state.session,
      en: 'This is Blackwell.',
      startSec: 1.25,
      endSec: 3.50,
      status: 'pending',
      isFinal: true
    };
    state.rows = [row];
    await executeRowTranslation(row);
  })()`);

  assert.ok(lastFetchPayload, 'Fetch payload must be recorded');
  assert.equal(lastFetchPayload.source_epoch, 3, 'source_epoch must match state.vision.sourceEpoch');
  assert.equal(lastFetchPayload.segment_audio_start_ms, 1250, 'segment_audio_start_ms must be startSec in ms');
  assert.equal(lastFetchPayload.segment_audio_end_ms, 3500, 'segment_audio_end_ms must be endSec in ms');
  console.log('✓ Test 1: executeRowTranslation payload contains source_epoch and segment timestamps.');

  // Test 2: polishRowWithGemini transmits source_epoch, segment timestamps, and initial translation
  lastFetchPayload = null;
  await run(`(async () => {
    const row = {
      id: 2,
      session: state.session,
      en: 'We accelerate computing.',
      vi: 'Chúng tôi tăng tốc tính toán.',
      startSec: 4.0,
      endSec: 6.2,
      status: 'ok',
      isFinal: true,
      isPolished: false
    };
    state.rows.push(row);
    await polishRowWithGemini(row);
  })()`);

  assert.ok(lastFetchPayload, 'Fetch payload must be recorded for polish');
  assert.equal(lastFetchPayload.source_epoch, 3);
  assert.equal(lastFetchPayload.segment_audio_start_ms, 4000);
  assert.equal(lastFetchPayload.segment_audio_end_ms, 6200);
  assert.equal(lastFetchPayload.provider, 'gemini');
  assert.equal(lastFetchPayload.initial_translation, 'Chúng tôi tăng tốc tính toán.');
  console.log('✓ Test 2: polishRowWithGemini payload contains source_epoch, timestamps, and initial_translation.');

  // Test 3: Anti-rollback - When row.id < state.activeRow.id, polish does not pull video caption back to old row
  await run(`(async () => {
    state.kind = 'video';
    const oldRow = {
      id: 10,
      session: state.session,
      en: 'First old sentence.',
      vi: 'Câu cũ thứ nhất.',
      startSec: 10.0,
      endSec: 12.0,
      mediaStart: 10.0,
      mediaEnd: 12.0,
      status: 'ok',
      isFinal: true,
      isPolished: false,
      displayedAt: 1000
    };
    
    // User has advanced to row 11!
    state.activeRow = {
      id: 11,
      session: state.session,
      en: 'Second newer sentence in progress.',
      vi: 'Câu mới đang dịch...',
      startSec: 12.5,
      endSec: 15.0,
      mediaStart: 12.5,
      mediaEnd: 15.0,
      status: 'mt',
      isFinal: false,
      words: []
    };
    state.rows = [oldRow, state.activeRow];

    // Setup presenter and caption elements
    const captionViEl = document.getElementById('caption-vi');
    captionViEl.textContent = 'Câu mới đang hiển thị';

    // Hook render to detect if full render was triggered
    let fullRenderTriggered = false;
    const originalRender = render;
    render = () => { fullRenderTriggered = true; originalRender(); };

    // Execute polish on older row 10
    await polishRowWithGemini(oldRow);

    // Assert: oldRow.vi was updated in memory
    assert.equal(oldRow.vi, 'Bản dịch thử nghiệm có ngữ cảnh slide.');
    // Assert: full render was NOT called, preventing caption rollback
    assert.equal(fullRenderTriggered, false, 'render() must NOT be called when row.id < state.activeRow.id');
    // Assert: caption-vi was NOT rolled back to oldRow
    assert.equal(captionViEl.textContent, 'Câu mới đang hiển thị');
  })()`);
  console.log('✓ Test 3: Anti-rollback gate passed (older row polish does not roll back video caption display).');

  console.log('\nAll Phase 5 Frontend Integration tests passed successfully!');
}

runTests().catch(err => {
  console.error('Test failure:', err);
  process.exit(1);
});
