const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
let textContentSets = 0;
let replaceChildrenCalls = 0;

function createElement(id = '') {
  let _text = '';
  return {
    id,
    style: {},
    disabled: false,
    hidden: false,
    currentTime: 0,
    value: '1500',
    get textContent() {
      return _text;
    },
    set textContent(val) {
      textContentSets++;
      _text = val;
    },
    append() {},
    prepend() {},
    insertBefore() {},
    replaceChildren(...args) {
      replaceChildrenCalls++;
      if (args.length === 0) _text = '';
      else _text = args.map(a => a.textContent || '').join('');
    },
    addEventListener() {}
  };
}

const context = vm.createContext({
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
  performance: { now: () => 1000 },
  setInterval() {},
  setTimeout,
  clearTimeout,
  console,
  fetch: async () => ({ ok: true, json: async () => ({}) })
});

vm.runInContext(fs.readFileSync(require.resolve('../frontend/live.js'), 'utf8'), context);
const run = code => vm.runInContext(code, context);

// 1. Initial render with some active rows
run(`
  state.ready = true;
  state.capturing = true;
  state.kind = 'video';
  state.rows = [
    { id: 1, status: 'ok', en: 'Hello Jensen', vi: 'Xin chào Jensen', startSec: 0, endSec: 1, mediaStart: 0, mediaEnd: 1, displayedAt: 500 }
  ];
  render();
`);

const initialTextSets = textContentSets;
const initialReplaceChildren = replaceChildrenCalls;

// 2. Perform 100 render() calls with identical state
for (let i = 0; i < 100; i++) {
  run('render();');
}

// In 100 renders with identical state:
// textContentSets should be 0 because values did not change!
const repeatedTextSets = textContentSets - initialTextSets;
assert.equal(repeatedTextSets, 0, `Expected 0 textContent mutations on 100 identical renders, got ${repeatedTextSets}`);

// replaceChildren should NOT be called every tick on timeline!
const repeatedReplaceChildren = replaceChildrenCalls - initialReplaceChildren;
assert.equal(repeatedReplaceChildren, 0, `Expected 0 replaceChildren calls on 100 identical renders, got ${repeatedReplaceChildren}`);

// 3. Test that updating row 1 only mutates row 1 without rebuilding whole timeline
run(`
  state.rows[0].vi = 'Xin chào Jensen (cập nhật)';
  render();
`);
assert.ok(textContentSets > initialTextSets, 'Should update changed text');
assert.equal(replaceChildrenCalls, initialReplaceChildren, 'Should not replaceChildren when updating existing row');

console.log('Phase 1 UI Stability Gate tests passed: 0 DOM thrashing across 100 renders, selective ID-based updates.');
