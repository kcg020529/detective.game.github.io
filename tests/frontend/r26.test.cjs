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
const flush = () => new Promise(resolve => setImmediate(resolve));
const DAY_START = 860;

function dayContext() {
  let keyCounter = 0;
  let advanceImpl = async () => ({ game_state: { current_day: 2 } });
  let getSaveImpl = async () => ({ save_id: 1, current_day: 1 });
  const live = { value: true };
  const advanceCalls = [];
  const getSaveCalls = [];
  const errors = [];
  const toasts = [];
  const renders = [];
  const confirm = { disabled: false, textContent: '넘어가기', isConnected: true, setAttribute() {}, removeAttribute() {}, focus() {} };
  const dialogText = { textContent: '' };
  const dialog = { hidden: true, querySelector: sel => (sel === '[data-day-confirm]' ? confirm : dialogText) };
  const memo = { value: '' };
  const notebook = { querySelector: sel => (sel === '[data-memo]' ? memo : null) };
  const curtain = { hidden: true, classList: { add() {}, remove() {} }, querySelector: () => ({ textContent: '' }) };
  const map = {
    '[data-day-dialog]': dialog,
    '[data-start-menu]': { hidden: false },
    '[data-day-next]': { focus() {} },
    '[data-day-curtain]': curtain,
    '[data-day-confirm]': confirm,
    '[data-toast]': { textContent: '', classList: { add() {}, remove() {} } },
  };
  const state = {
    save: { save_id: 1, current_day: 1 },
    root: { querySelector: sel => map[sel] || null },
    windows: new Map([['notebook', notebook]]),
    timers: new Set(),
    unread: new Set(),
    dayChanging: false,
    clockMinutes: 999,
  };
  const context = vm.createContext({
    window: { Api: {
      advanceDay: (saveId, key) => { advanceCalls.push(key); return advanceImpl(saveId, key); },
      getSave: saveId => { getSaveCalls.push(saveId); return getSaveImpl(saveId); },
    } },
    data: { maxDay: 6 },
    requestId: () => `key-${++keyCounter}`,
    isLiveState: () => live.value,
    addTimer: () => {},
    reduceMotion: true,
    DAY_START_MINUTES: DAY_START,
    setTimeout: () => 1,
    clearTimeout: () => {},
    renderTaskbar: () => renders.push('taskbar'),
    renderAccuse: () => renders.push('accuse'),
    renderLaunchers: () => renders.push('launchers'),
    handleError: (s, error) => errors.push(error),
    showToast: (s, message) => toasts.push(message),
  });
  vm.runInContext(extract('currentDay', 'roleLabel') + extract('openDayDialog', 'showToast'), context);
  return { context, state, live, advanceCalls, getSaveCalls, errors, toasts, renders,
    dom: { dialog, confirm, memo }, keys: () => keyCounter,
    setAdvance: fn => { advanceImpl = fn; }, setGetSave: fn => { getSaveImpl = fn; } };
}

test('J: timeout -> cancel -> open -> confirm resends the same client_request_id', async () => {
  const h = dayContext();
  let fail = true;
  h.setAdvance(() => (fail ? Promise.reject({ code: 'TIMEOUT', message: 'timeout' }) : Promise.resolve({ game_state: { current_day: 2 } })));
  await h.context.openDayDialog(h.state);
  assert.equal(h.state.advanceRequestId, 'key-1');
  await h.context.advanceDay(h.state);
  await flush();
  h.context.closeDayDialog(h.state);
  assert.equal(h.state.advanceRequestId, 'key-1');
  assert.equal(h.state.advanceUnresolved, true);
  await h.context.openDayDialog(h.state);
  assert.equal(h.state.advanceRequestId, 'key-1');
  fail = false;
  await h.context.advanceDay(h.state);
  assert.deepEqual(h.advanceCalls, ['key-1', 'key-1']);
  assert.equal(h.keys(), 1);
  assert.equal(h.state.advanceRequestId, null);
  assert.equal(h.state.advanceUnresolved, false);
  assert.equal(h.state.save.current_day, 2);
  assert.equal(h.getSaveCalls.length, 2);
  assert.equal(h.state.dayDialogOpening, false);
});

test('J: reopen while unresolved applies a higher server day without a new advance', async () => {
  const h = dayContext();
  let serverDay = 1;
  h.setAdvance(() => Promise.reject({ code: 'TIMEOUT', message: 'timeout' }));
  h.setGetSave(() => Promise.resolve({ save_id: 1, current_day: serverDay, memo: 'server memo' }));
  await h.context.openDayDialog(h.state);
  await h.context.advanceDay(h.state);
  await flush();
  h.context.closeDayDialog(h.state);
  serverDay = 2;
  await h.context.openDayDialog(h.state);
  assert.equal(h.state.save.current_day, 2);
  assert.equal(h.state.save.memo, 'server memo');
  assert.equal(h.state.advanceRequestId, null);
  assert.equal(h.state.advanceUnresolved, false);
  assert.equal(h.dom.dialog.hidden, true);
  assert.equal(h.dom.memo.value, 'server memo');
  assert.equal(h.advanceCalls.length, 1);
  assert.deepEqual(h.renders.slice(-3), ['launchers', 'accuse', 'taskbar']);
  assert.deepEqual(h.errors, []);
});

test('J: a second open while a re-sync is pending is ignored', async () => {
  const h = dayContext();
  h.state.advanceUnresolved = true;
  h.state.advanceRequestId = 'key-1';
  let resolveRead;
  h.setGetSave(() => new Promise(resolve => { resolveRead = resolve; }));
  const first = h.context.openDayDialog(h.state);
  await h.context.openDayDialog(h.state);
  assert.equal(h.getSaveCalls.length, 1);
  resolveRead({ save_id: 1, current_day: 2, memo: '' });
  await first;
  assert.equal(h.state.save.current_day, 2);
  assert.equal(h.state.advanceRequestId, null);
  assert.equal(h.dom.dialog.hidden, true);
  assert.equal(h.advanceCalls.length, 0);
  assert.equal(h.state.dayDialogOpening, false);
});

test('J: a stale read does not reopen the confirm after the day moved on', async () => {
  const h = dayContext();
  h.state.advanceUnresolved = true;
  h.state.advanceRequestId = 'key-1';
  let resolveRead;
  h.setGetSave(() => new Promise(resolve => { resolveRead = resolve; }));
  const pending = h.context.openDayDialog(h.state);
  h.state.save.current_day = 2;
  resolveRead({ save_id: 1, current_day: 1 });
  await pending;
  assert.equal(h.state.advanceRequestId, 'key-1');
  assert.equal(h.state.advanceUnresolved, true);
  assert.equal(h.dom.dialog.hidden, true);
  assert.equal(h.keys(), 0);
  assert.equal(h.state.dayDialogOpening, false);
});

test('J: a read that resolves after unmount writes nothing and does not reject', async () => {
  const h = dayContext();
  h.state.advanceUnresolved = true;
  h.state.advanceRequestId = 'key-1';
  let resolveRead;
  h.setGetSave(() => new Promise(resolve => { resolveRead = resolve; }));
  const pending = h.context.openDayDialog(h.state);
  h.live.value = false;
  resolveRead({ save_id: 1, current_day: 2, memo: 'x' });
  await pending;
  assert.equal(h.state.save.current_day, 1);
  assert.equal(h.state.advanceRequestId, 'key-1');
  assert.equal(h.dom.dialog.hidden, true);
  assert.deepEqual(h.toasts, []);
  assert.deepEqual(h.renders, []);
  assert.equal(h.state.dayDialogOpening, false);
});

test('J: a failed read after unmount writes nothing and does not reject', async () => {
  const h = dayContext();
  h.state.advanceUnresolved = true;
  h.state.advanceRequestId = 'key-1';
  let rejectRead;
  h.setGetSave(() => new Promise((resolve, reject) => { rejectRead = reject; }));
  const pending = h.context.openDayDialog(h.state);
  h.live.value = false;
  rejectRead({ code: 'NETWORK_ERROR', message: 'down' });
  await pending;
  assert.equal(h.state.advanceRequestId, 'key-1');
  assert.equal(h.dom.dialog.hidden, true);
  assert.deepEqual(h.errors, []);
  assert.deepEqual(h.renders, []);
});

test('J: Day 5->6 re-sync applies the normal day-change effects', async () => {
  const h = dayContext();
  h.state.save = { save_id: 1, current_day: 5 };
  h.state.advanceUnresolved = true;
  h.state.advanceRequestId = 'key-1';
  h.setGetSave(() => Promise.resolve({ save_id: 1, current_day: 6, memo: 'm6' }));
  await h.context.openDayDialog(h.state);
  assert.equal(h.state.save.current_day, 6);
  assert.equal(h.state.clockMinutes, DAY_START);
  assert.ok(h.state.unread.has('accuse'));
  assert.deepEqual(h.renders, ['launchers', 'accuse', 'taskbar']);
  assert.equal(h.dom.memo.value, 'm6');
  assert.equal(h.state.advanceRequestId, null);
  assert.equal(h.state.advanceUnresolved, false);
  assert.equal(h.dom.dialog.hidden, true);
  assert.equal(h.advanceCalls.length, 0);
});

test('J: STATE_CONFLICT read resolving after unmount writes nothing', async () => {
  const h = dayContext();
  h.state.save = { save_id: 1, current_day: 5 };
  let resolveRead;
  h.setGetSave(() => new Promise(resolve => { resolveRead = resolve; }));
  h.setAdvance(() => Promise.reject({ code: 'STATE_CONFLICT', message: 'conflict' }));
  await h.context.openDayDialog(h.state);
  const pending = h.context.advanceDay(h.state);
  await flush();
  const renderedBefore = h.renders.length;
  h.live.value = false;
  resolveRead({ save_id: 1, current_day: 6, memo: 'x' });
  await pending;
  assert.equal(h.state.save.current_day, 5);
  assert.equal(h.state.clockMinutes, 999);
  assert.ok(!h.state.unread.has('accuse'));
  assert.equal(h.renders.length, renderedBefore);
  assert.deepEqual(h.toasts, []);
  assert.equal(h.dom.memo.value, '');
});

test('J: same-day STATE_CONFLICT refresh preserves the clock and unread state', async () => {
  const h = dayContext();
  h.state.save = { save_id: 1, current_day: 3, memo: 'old' };
  h.setAdvance(() => Promise.reject({ code: 'STATE_CONFLICT', message: 'conflict' }));
  h.setGetSave(() => Promise.resolve({ save_id: 1, current_day: 3, memo: 'server memo' }));
  await h.context.openDayDialog(h.state);
  await h.context.advanceDay(h.state);
  assert.equal(h.state.save.current_day, 3);
  assert.equal(h.state.save.memo, 'server memo');
  assert.equal(h.state.clockMinutes, 999);
  assert.equal(h.state.unread.size, 0);
  assert.ok(h.renders.includes('launchers'));
  assert.equal(h.dom.memo.value, 'server memo');
});

test('J: malformed accusation ids fail http validation with INVALID_RESPONSE', async () => {
  const responses = [];
  const context = vm.createContext({
    window: { KERVION_API_BASE: '/api/v1', dispatchEvent() {} }, AbortController,
    setTimeout: () => 1, clearTimeout() {},
    fetch: async () => ({ ok: true, status: 200, text: async () => JSON.stringify(responses[0]) }),
  });
  vm.runInContext(fs.readFileSync('frontend/play/api.js', 'utf8'), context);
  const api = context.window.Api;
  responses[0] = { accusation: { character_id: 'YB-1', verdict: { hit: true, culprit_id: 'YB-9', truth: 't', evidence: [] } } };
  await assert.rejects(api.submitAccusation(1, 'YB-1', 'req'), error => error.code === 'INVALID_RESPONSE');
  responses[0] = { save_id: 1, role: 'grad', current_day: 6, accusation: { character_id: 'XX-1', verdict: { hit: true, culprit_id: 'YB-1', truth: 't', evidence: [] } } };
  await assert.rejects(api.getSave(1), error => error.code === 'INVALID_RESPONSE');
  responses[0] = { save_id: 1, role: 'grad', current_day: 6, accusation: { character_id: 'YB-2' } };
  await assert.rejects(api.getSave(1), error => error.code === 'INVALID_RESPONSE');
  responses[0] = { save_id: 1, role: 'grad', current_day: 3, accusation: null };
  const clean = await api.getSave(1);
  assert.equal(clean.accusation, null);
});

test('J: showVerdict with unknown YB ids shows an error toast instead of throwing', () => {
  const toasts = [];
  const context = vm.createContext({
    window: { Api: { messageFor: () => '응답 오류' } },
    data: { ybs: [{ id: 'YB-1' }, { id: 'YB-2' }] },
    showToast: (s, message) => toasts.push(message),
  });
  vm.runInContext(extract('showVerdict', 'closeVerdict'), context);
  const state = {
    save: { accusation: { character_id: 'YB-9', verdict: { culprit_id: 'XX', hit: false, truth: 't', evidence: [] } } },
    root: { querySelector: () => null },
  };
  assert.doesNotThrow(() => context.showVerdict(state));
  assert.deepEqual(toasts, ['응답 오류']);
});

test('J: cancel still drops the key when no advance is unresolved', async () => {
  const h = dayContext();
  await h.context.openDayDialog(h.state);
  h.context.closeDayDialog(h.state);
  assert.equal(h.state.advanceRequestId, null);
  assert.equal(h.getSaveCalls.length, 0);
});
