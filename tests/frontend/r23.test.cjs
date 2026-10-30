const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('frontend/play/c.js', 'utf8');
function extract(name, next) {
  const start = source.search(new RegExp(`  (?:async )?function ${name}\\(`));
  assert.ok(start >= 0, name);
  return source.slice(start, source.indexOf(`\n  function ${next}`, start));
}
function chatContext() {
  let resolve, reject;
  const response = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  const rendered = [];
  const timers = new Map();
  const context = vm.createContext({
    window: { Api: { sendChat: () => response }, matchMedia: () => ({ matches: false }) },
    data: { ybs: [{ id: 'YB-1' }, { id: 'YB-2' }] },
    requestId: () => 'request-1', isLiveState: () => true,
    renderMessenger: state => rendered.push(state.activeYb), renderTaskbar: () => {},
    updateChatControls: state => { state.controlsPending = state.chatPending; },
    handleError: () => {},
    setTimeout: fn => { const id = timers.size + 1; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id),
    rowsToEntries: (rows, id) => [{ message_id: rows[0].message_id, answer: { text: 'answer', from: id }, typed: 0 }],
  });
  vm.runInContext(extract('sendQuestion', 'requestId') + extract('retryChat', 'typeAnswer') + extract('typeAnswer', 'renderAccuse'), context);
  const state = { activeYb: 0, histories: [[], []], chatRows: [[], []], save: { save_id: 1 }, timers: new Set() };
  return { context, state, resolve, reject, rendered, timers };
}

test('H: delayed reply stays with original YB and does not redraw another tab', async () => {
  const h = chatContext();
  const pending = h.context.sendQuestion(h.state, 'question');
  h.state.activeYb = 1;
  h.resolve({ messages: [{ message_id: 1, sender: 'user' }, { message_id: 2, sender: 'ai' }] });
  await pending;
  assert.equal(h.state.chatRows[0].length, 2);
  assert.equal(h.state.chatRows[1].length, 0);
  assert.equal(h.state.histories[0][0].answer.from, 'YB-1');
  assert.equal(h.state.chatPending, false);
  assert.deepEqual(h.rendered, [0]);
  assert.equal(h.state.controlsPending, false);
});

test('F/H: rate-limited reply remains retryable on its original YB', async () => {
  const h = chatContext();
  const pending = h.context.sendQuestion(h.state, 'question');
  h.state.activeYb = 1;
  h.reject({ code: 'RATE_LIMITED' });
  await pending;
  assert.equal(h.state.histories[0][0].failed, true);
  assert.equal(h.state.histories[1].length, 0);
  assert.deepEqual(h.rendered, [0]);
  h.context.retryChat(h.state, 'request-1');
  assert.equal(h.state.activeYb, 0);
  await Promise.resolve();
});

test('H: validation failure removes only original pending entry after switching tabs', async () => {
  const h = chatContext();
  const pending = h.context.sendQuestion(h.state, 'question');
  h.state.activeYb = 1;
  h.reject({ code: 'VALIDATION_ERROR', message: 'invalid' });
  await pending;
  assert.equal(h.state.histories[0].length, 0);
  assert.equal(h.state.histories[1].length, 0);
});

test('H: typing finishes without redrawing a newly selected YB', () => {
  const h = chatContext();
  h.state.activeYb = 1;
  h.state.chatPending = true;
  const entry = { typed: 0, typing: true, answer: { text: 'answer' } };
  h.context.typeAnswer(h.state, entry, 0);
  assert.equal(entry.typed, 6);
  assert.equal(entry.typing, false);
  assert.equal(h.state.chatPending, false);
  assert.deepEqual(h.rendered, []);
});

function memoContext() {
  const calls = [];
  const listeners = [];
  const state = { memoTimer: 1, memoValue: 'new memo', save: { save_id: 7 }, root: { removeEventListener() {}, replaceChildren() {} }, timers: new Set() };
  const context = vm.createContext({
    window: { Api: { saveMemo: (...args) => { calls.push(args); return Promise.resolve({ memo: args[1] }); } }, removeEventListener: (...args) => listeners.push(args) },
    document: { removeEventListener() {} }, clearTimeout() {}, clearInterval() {},
    isLiveState: () => true, handleError: () => {}, instance: { state },
  });
  vm.runInContext(extract('flushMemo', 'unmount') + extract('unmount', 'createWindows'), context);
  return { state, context, calls, listeners };
}

test('I: unmount flushes pending memo once', async () => {
  const h = memoContext();
  h.context.unmount(h.state);
  await Promise.resolve();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0][1], 'new memo');
  assert.equal(h.state.memoTimer, null);
  assert.equal(h.state.save.memo, 'new memo');
});

test('I: pagehide flush uses keepalive and subsequent unmount does not duplicate it', async () => {
  const h = memoContext();
  const pagehide = source.match(/state.pagehide = (.+);/)[1];
  h.context.state = h.state;
  vm.runInContext(`(${pagehide})()`, h.context);
  h.context.unmount(h.state);
  await Promise.resolve();
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0][2].keepalive, true);
  assert.ok(source.includes("window.addEventListener('pagehide', state.pagehide)"));
});

test('F/G/I: HTTP adapter handles rate limits, chat timeout, and memo keepalive', async () => {
  const timeouts = [];
  const calls = [];
  const context = vm.createContext({
    window: { KERVION_API_BASE: '/api/v1', dispatchEvent() {} }, AbortController,
    setTimeout: (_fn, delay) => { timeouts.push(delay); return 1; }, clearTimeout() {},
    fetch: async (...args) => { calls.push(args); return { ok: true, status: 200, text: async () => JSON.stringify({ saves: [], game_state: { current_day: 1 }, messages: [{ message_id: 1, ai_id: 'YB-1', sender: 'user', content: 'question', response_type: null }, { message_id: 2, ai_id: 'YB-1', sender: 'ai', content: 'answer', response_type: 'normal' }] }) }; },
  });
  vm.runInContext(fs.readFileSync('frontend/play/api.js', 'utf8'), context);
  const api = context.window.Api;
  await api.sendChat(1, 'YB-1', 'question', 'request');
  await api.listSaves();
  await api.saveMemo(1, 'memo', { keepalive: true });
  assert.deepEqual(timeouts, [60000, 15000, 15000]);
  assert.equal(calls[2][1].keepalive, true);
  context.fetch = async () => ({ ok: false, status: 429, text: async () => '{"error":{"code":"RATE_LIMITED","message":"slow down"}}' });
  await assert.rejects(api.sendChat(1, 'YB-1', 'question', 'retry'), error => error.code === 'RATE_LIMITED');
  assert.notEqual(api.messageFor('RATE_LIMITED'), api.messageFor('unknown'));
});


test('H: inactive response re-enables composer without replacing conversation DOM', () => {
  const buttons = [{ disabled: true }, { disabled: true }];
  const send = { disabled: true, setAttribute(_name, value) { this.busy = value; } };
  const context = vm.createContext({});
  vm.runInContext(extract('updateChatControls', 'selectYb'), context);
  context.updateChatControls({ chatPending: false, chatWaitVisible: false,
    windows: new Map([['messenger', { querySelectorAll: () => buttons, querySelector: () => send }]]) });
  assert.equal(send.disabled, false);
  assert.equal(send.busy, 'false');
  assert.ok(buttons.every(button => !button.disabled));
});
