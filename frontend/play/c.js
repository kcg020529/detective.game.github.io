// C안: 단말기에 접속한 뒤의 연구소 전용 레트로 데스크톱 OS입니다.
(function () {
  const data = window.Play.data;
  const pixel = window.Play.pixel;
  let instance = null;
  let entryState = null;
  let sessionContext = null;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const appInfo = {
    messenger: { label: 'YB 메신저', icon: 'chat' },
    archive: { label: '기록 보관함', icon: 'folder' },
    notebook: { label: '단서 수첩', icon: 'note' },
    accuse: { label: '지목', icon: 'scale' },
  };

  function roleLabel(role) {
    return data.roles[role]?.label || '대학원생';
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function rankFor(role) {
    return data.roles[role]?.rank || 1;
  }

  function iconMarkup(type) {
    return `<span class="c-icon-art c-icon-${type}" aria-hidden="true"><i></i><i></i><i></i><i></i></span>`;
  }

  function buildMarkup(state) {
    const label = roleLabel(state.role);
    return `<div class="c-shell">
      <div class="c-desktop" data-desktop>
        <div class="c-system-line"><span>YB-LAB OS 2.0</span><span>단말기 07 · 조사 세션</span></div>
        <div class="c-desktop-pattern" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>
        <div class="c-desktop-icons" aria-label="프로그램">
          ${Object.entries(appInfo).map(([key, info]) => `<button type="button" class="c-desktop-icon" data-open="${key}">${iconMarkup(info.icon)}<span>${info.label}</span></button>`).join('')}
        </div>
        <div class="c-window-layer" data-window-layer></div>
        <div class="c-start-menu" data-start-menu hidden>
          <div class="c-start-head">연구소 단말기</div>
          ${Object.entries(appInfo).map(([key, info]) => `<button type="button" data-open="${key}">${iconMarkup(info.icon)}<span>${info.label}</span></button>`).join('')}
          <button type="button" data-action="sessions"><span class="c-menu-exit">↪</span><span>세션 선택으로</span></button>
          <button type="button" data-action="exit"><span class="c-menu-exit">⏻</span><span>정문으로 나가기</span></button>
        </div>
        <div class="c-toast" data-toast role="status" aria-live="polite"></div>
        <div class="c-taskbar">
          <button type="button" class="c-start-button" data-start>시작</button>
          <div class="c-task-buttons" data-task-buttons></div>
          <div class="c-task-status"><span data-clock>Day ${state.save.day || 2} · 14:20</span><span>${escapeHtml(label)}</span><span>토큰 <b data-tokens>${String(state.save.tokens ?? 8).padStart(2, '0')}</b>/${data.maxTokens}</span></div>
        </div>
      </div>
    </div>`;
  }

  function entryMonitor(inner) {
    return `<div class="c-entry-shell"><div class="c-entry-monitor"><div class="c-entry-screen">${inner}</div></div></div>`;
  }

  // 모니터가 켜지는 연출만 (글자 없음): 가운데 빛줄이 위아래로 펼쳐진 뒤 출입증 화면
  function buildBootMarkup() {
    return entryMonitor('<div class="c-entry-power" aria-hidden="true"><i></i></div>');
  }

  function buildSessionMarkup(state) {
    const context = state.context;
    const mode = state.mode;
    const title = '출입증을 고르세요';
    const intro = mode === 'new'
      ? `${roleLabel(context.role)} 역할로 관찰할 실험 기록을 고르세요.`
      : '이어갈 실험 기록을 골라 리더기에 대세요.';
    const cards = context.saves.map((save, index) => {
      const empty = !save;
      const disabled = mode === 'resume' && empty;
      const selected = state.selected === index;
      const reading = state.phase === 'reading' && state.reading === index;
      const action = empty ? (mode === 'new' ? '새 실험 관찰' : '발급 전') : (mode === 'new' ? '덮어쓰기 확인' : '리더기에 대기');
      const detail = save
        ? `<strong>${escapeHtml(roleLabel(save.role))}</strong><span>Day ${save.day}/3 · 토큰 ${save.tokens}/${context.maxTokens} · 단서 ${save.clues}</span><small>마지막 접속 ${escapeHtml(save.lastPlayed || '기록 없음')}</small>`
        : `<strong>발급 전</strong><span>새 실험 관찰</span><small>역할: ${escapeHtml(roleLabel(context.role || 'grad'))}</small>`;
      return `<button type="button" class="c-session-card${empty ? ' is-empty' : ''}${selected ? ' is-selected' : ''}${reading ? ' is-reading' : ''}${mode === 'new' && save ? ' is-overwrite' : ''}" data-slot="${index}" ${disabled ? 'disabled' : ''}>
        <span class="c-session-avatar c-avatar-${index}" aria-hidden="true"><i></i><i></i><b></b></span>
        <span class="c-session-number">${index + 1}번 기록</span>
        <span class="c-session-copy">${detail}</span>
        <span class="c-session-action">${action}</span>
      </button>`;
    }).join('');
    const status = state.phase === 'reading'
      ? (state.readingText || '리더기가 카드를 읽는 중…')
      : state.confirmSlot === null
        ? (mode === 'new' ? '발급 전 출입증은 새 실험 관찰로 사용합니다.' : '출입증을 고르면 리더기에 대기합니다.')
        : `슬롯 ${state.confirmSlot + 1}의 기록을 덮어씁니다. 같은 출입증을 한 번 더 고르세요.`;
    const readerStatus = state.phase === 'reading' ? (state.readingText || '카드를 읽는 중…') : status;
    return entryMonitor(`<div class="c-entry-session${state.phase === 'reading' ? ' is-reading' : ''}" data-entry-session>
      <div class="c-entry-wall" aria-hidden="true"><i></i><i></i><i></i></div>
      <div class="c-entry-session-head"><h1>${title}</h1><p>${intro}</p></div>
      <div class="c-session-grid">${cards}</div>
      <div class="c-reader" data-reader><div class="c-reader-top"></div><div class="c-reader-slot"></div><div class="c-reader-leds"><i></i><i></i></div><span data-reader-status>${readerStatus}</span></div>
      <div class="c-session-footer"><span>↑ ↓ 선택 · Enter 대기 · Esc 정문으로</span><button type="button" data-action="poweroff">정문으로</button></div>
    </div>`);
  }

  function addTimer(state, callback, delay) {
    const timer = setTimeout(() => {
      state.timers.delete(timer);
      callback();
    }, delay);
    state.timers.add(timer);
    return timer;
  }

  function isLiveState(state) {
    return state.entry ? entryState === state : instance?.state === state;
  }

  function firstSessionSlot(state) {
    if (state.mode === 'resume') {
      if (state.context.saves[state.context.lastSlot]) return state.context.lastSlot;
      const filled = state.context.saves.findIndex(Boolean);
      return filled >= 0 ? filled : 0;
    }
    const empty = state.context.saves.findIndex((save) => !save);
    return empty >= 0 ? empty : 0;
  }

  function renderSession(state) {
    state.selected = Number.isInteger(state.selected) ? state.selected : firstSessionSlot(state);
    state.root.className = 'screen play-c play-c-entry';
    state.root.hidden = false;
    state.root.innerHTML = buildSessionMarkup(state);
    state.root.querySelector(`[data-slot="${state.selected}"]:not([disabled])`)?.focus({ preventScroll: true });
  }

  function startBootSequence(state) {
    if (reduceMotion) {
      state.phase = 'session';
      renderSession(state);
      return;
    }
    state.phase = 'boot';
    state.root.innerHTML = buildBootMarkup();
    addTimer(state, () => {
      state.phase = 'session';
      renderSession(state);
      state.root.querySelector('[data-entry-session]')?.classList.add('is-powering-on');
    }, 480);
  }

  function beginSessionRead(state, index) {
    state.phase = 'reading';
    state.selected = index;
    state.reading = index;
    state.readingText = '리더기가 카드를 읽는 중…';
    state.root.className = 'screen play-c play-c-entry';
    state.root.hidden = false;
    state.root.innerHTML = buildSessionMarkup(state);
    if (reduceMotion) {
      state.readingText = '확인됨';
      state.root.innerHTML = buildSessionMarkup(state);
      addTimer(state, () => {
        if (!isLiveState(state)) return;
        if (state.entry) finishEntry(state);
        state.context.onStart?.(index, state.mode);
      }, 40);
      return;
    }
    addTimer(state, () => {
      if (!isLiveState(state)) return;
      state.readingText = '확인됨';
      state.root.innerHTML = buildSessionMarkup(state);
      state.root.classList.add('c-entry-confirmed');
    }, 270);
    addTimer(state, () => {
      if (!isLiveState(state)) return;
      if (state.entry) finishEntry(state);
      state.context.onStart?.(index, state.mode);
    }, 720);
  }

  function finishEntry(state) {
    if (entryState !== state) return;
    entryState = null;
    state.keydown && document.removeEventListener('keydown', state.keydown);
    state.click && state.root.removeEventListener('click', state.click);
    state.timers.forEach((timer) => clearTimeout(timer));
    state.timers.clear();
  }

  function powerOff(state) {
    const context = state.context;
    if (state.entry) finishEntry(state);
    context?.onBack?.(state.mode);
  }

  function chooseSession(state, index) {
    const save = state.context.saves[index];
    if (state.mode === 'resume' && !save) return;
    if (state.mode === 'new' && save && state.confirmSlot !== index) {
      state.confirmSlot = index;
      state.selected = index;
      renderSession(state);
      return;
    }
    state.confirmSlot = null;
    beginSessionRead(state, index);
  }

  function handleSessionKeyDown(state, event) {
    if (state.phase === 'reading' && event.key === 'Escape') {
      event.preventDefault();
      powerOff(state);
      return true;
    }
    if (state.phase !== 'session') return false;
    const options = [...state.root.querySelectorAll('[data-slot]:not([disabled])')];
    const current = options.findIndex((item) => Number(item.dataset.slot) === state.selected);
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight' || event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
      event.preventDefault();
      const direction = event.key === 'ArrowDown' || event.key === 'ArrowRight' ? 1 : -1;
      const next = (current + direction + options.length) % options.length;
      state.selected = Number(options[next]?.dataset.slot ?? state.selected);
      options[next]?.focus({ preventScroll: true });
      return true;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      chooseSession(state, state.selected);
      return true;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      powerOff(state);
      return true;
    }
    return false;
  }

  function showSessionSelection(state) {
    if (!state.context) return state.onExit?.();
    state.context = { ...state.context, mode: 'resume' };
    state.mode = 'resume';
    state.phase = 'session';
    state.confirmSlot = null;
    state.selected = null;
    state.sessionClick && state.root.removeEventListener('click', state.sessionClick);
    state.sessionClick = (event) => {
      const slot = event.target.closest('[data-slot]')?.dataset.slot;
      if (slot !== undefined && state.phase === 'session') chooseSession(state, Number(slot));
    };
    state.root.addEventListener('click', state.sessionClick);
    renderSession(state);
  }

  async function enter(options) {
    if (instance) instance.unmount();
    if (entryState) finishEntry(entryState);
    sessionContext = options;
    const state = {
      entry: true,
      root: options.root,
      context: options,
      mode: options.mode,
      phase: 'boot',
      selected: null,
      confirmSlot: null,
      timers: new Set(),
      keydown: null,
      reading: null,
      readingText: '',
      sessionClick: null,
    };
    entryState = state;
    state.root.className = 'screen play-c play-c-entry';
    state.root.hidden = true;
    state.root.replaceChildren();
    state.keydown = (event) => {
      if (handleSessionKeyDown(state, event)) return;
      if (event.key === 'Escape' && state.phase === 'boot') {
        event.preventDefault();
        powerOff(state);
      }
    };
    document.addEventListener('keydown', state.keydown);
    state.click = (event) => {
      const action = event.target.closest('[data-action]')?.dataset.action;
      if (action === 'poweroff') powerOff(state);
      const slot = event.target.closest('[data-slot]')?.dataset.slot;
      if (slot !== undefined && state.phase === 'session') chooseSession(state, Number(slot));
    };
    state.root.addEventListener('click', state.click);
    await options.zoomIn?.();
    if (entryState !== state) return;
    state.root.hidden = false;
    startBootSequence(state);
  }

  function mount(root, save, options) {
    if (instance) instance.unmount();
    const state = {
      root,
      save,
      role: save.role || 'grad',
      context: sessionContext,
      phase: 'desktop',
      windows: new Map(),
      z: 20,
      activeWindow: null,
      activeYb: 0,
      histories: data.ybs.map(() => []),
      clues: data.clues.slice(0, Math.max(0, Number(save.clues) || 0)),
      suspect: null,
      typing: null,
      timers: new Set(),
      recordClues: new Set(),
      drag: null,
      clockMinutes: 14 * 60 + 20,
      clockTimer: null,
      onExit: options?.onExit || (() => {}),
    };
    instance = { state, unmount: () => unmount(state) };
    root.className = 'screen play-c';
    root.hidden = false;
    root.innerHTML = buildMarkup(state);
    createWindows(state);
    bindEvents(state);
    openWindow(state, 'messenger');
    renderTaskbar(state);
    state.clockTimer = setInterval(() => {
      state.clockMinutes = (state.clockMinutes + 1) % (24 * 60);
      renderTaskbar(state);
    }, 3000);
  }

  function unmount(state) {
    document.removeEventListener('keydown', state.keydown);
    document.removeEventListener('pointermove', state.pointermove);
    document.removeEventListener('pointerup', state.pointerup);
    state.root.removeEventListener('click', state.click);
    state.root.removeEventListener('pointerdown', state.pointerdown);
    state.sessionClick && state.root.removeEventListener('click', state.sessionClick);
    state.timers.forEach((timer) => clearTimeout(timer));
    state.timers.clear();
    if (state.clockTimer) clearInterval(state.clockTimer);
    state.root.replaceChildren();
    if (instance?.state === state) instance = null;
  }

  function createWindows(state) {
    const layer = state.root.querySelector('[data-window-layer]');
    const windows = [
      ['messenger', 'YB 메신저', '15cqw', '8cqw', '58cqw', '57cqw', buildMessenger()],
      ['archive', '기록 보관함', '64cqw', '12cqw', '31cqw', '46cqw', buildArchive()],
      ['notebook', '단서 수첩', '20cqw', '20cqw', '42cqw', '45cqw', buildNotebook()],
      ['accuse', '지목', '29cqw', '25cqw', '42cqw', '37cqw', buildAccuse()],
    ];
    windows.forEach(([key, title, left, top, width, height, content]) => {
      const windowEl = document.createElement('section');
      windowEl.className = 'c-window';
      windowEl.dataset.window = key;
      windowEl.hidden = true;
      windowEl.style.left = left;
      windowEl.style.top = top;
      windowEl.style.width = width;
      windowEl.style.height = height;
      windowEl.innerHTML = `<div class="c-window-bar" data-drag-handle><span class="c-window-title">${title}</span><span class="c-window-actions"><button type="button" data-window-min="${key}" aria-label="최소화">_</button><button type="button" data-window-close="${key}" aria-label="닫기">×</button></span></div><div class="c-window-body" data-window-body>${content}</div>`;
      layer.append(windowEl);
      state.windows.set(key, windowEl);
    });
  }

  function buildMessenger() {
    return `<div class="c-messenger"><aside class="c-yb-list" data-yb-list></aside><section class="c-chat-panel"><div class="c-chat-head" data-chat-head></div><div class="c-chat-log" data-chat-log></div><div class="c-question-list" data-question-list></div><div class="c-compose"><textarea data-compose rows="1" placeholder="자유 질문을 입력하세요"></textarea><button type="button" data-send>보내기</button></div></section></div>`;
  }

  function buildArchive() {
    return `<div class="c-archive"><aside class="c-file-list" data-file-list></aside><section class="c-file-preview" data-file-preview><div class="c-empty-mark">▣</div><p>파일을 선택하면 로그가 열립니다.</p></section></div>`;
  }

  function buildNotebook() {
    return `<div class="c-notebook-body" data-notebook-body></div>`;
  }

  function buildAccuse() {
    return `<div class="c-accuse-body"><p>지금까지의 기록으로 한 명을 지목합니다.</p><div class="c-accuse-grid" data-accuse-grid></div><p class="c-accuse-result" data-accuse-result></p><button type="button" class="c-submit" data-submit-accuse disabled>제출</button></div>`;
  }

  function bindEvents(state) {
    state.keydown = (event) => handleKeyDown(state, event);
    state.pointermove = (event) => dragMove(state, event);
    state.pointerup = () => stopDrag(state);
    document.addEventListener('keydown', state.keydown);
    document.addEventListener('pointermove', state.pointermove);
    document.addEventListener('pointerup', state.pointerup);
    // root(#game-screen)는 다시 들어올 때도 같은 요소라서, 처리기를 state에 보관했다가 unmount에서 뗌
    state.click = (event) => {
      const open = event.target.closest('[data-open]')?.dataset.open;
      if (open) openWindow(state, open);
      if (event.target.closest('[data-start]')) toggleStartMenu(state);
      const action = event.target.closest('[data-action]')?.dataset.action;
      if (action === 'exit') leave(state);
       if (action === 'sessions') showSessionSelection(state);
       if (action === 'poweroff') powerOff(state);
      const task = event.target.closest('[data-task]')?.dataset.task;
      if (task) openWindow(state, task);
      const min = event.target.closest('[data-window-min]')?.dataset.windowMin;
      if (min) minimizeWindow(state, min);
      const close = event.target.closest('[data-window-close]')?.dataset.windowClose;
      if (close) closeWindow(state, close);
      const yb = event.target.closest('[data-yb]')?.dataset.yb;
      if (yb !== undefined) selectYb(state, Number(yb));
      const ask = event.target.closest('[data-ask]')?.dataset.ask;
      if (ask !== undefined) askQuestion(state, Number(ask));
      const record = event.target.closest('[data-record]')?.dataset.record;
      if (record !== undefined) openRecord(state, Number(record));
      const suspect = event.target.closest('[data-suspect]')?.dataset.suspect;
      if (suspect !== undefined) selectSuspect(state, Number(suspect));
      if (event.target.closest('[data-send]')) sendFreeQuestion(state);
      if (event.target.closest('[data-submit-accuse]')) submitAccuse(state);
    };
    state.root.addEventListener('click', state.click);
    state.pointerdown = (event) => {
      const handle = event.target.closest('[data-drag-handle]');
      if (!handle || event.target.closest('button')) return;
      const windowEl = handle.closest('[data-window]');
      if (!windowEl) return;
      bringToFront(state, windowEl.dataset.window);
      const rect = state.root.getBoundingClientRect();
      state.drag = { key: windowEl.dataset.window, startX: event.clientX, startY: event.clientY, left: parseFloat(windowEl.style.left), top: parseFloat(windowEl.style.top), unit: rect.width / 100 };
      event.preventDefault();
    };
    state.root.addEventListener('pointerdown', state.pointerdown);
    state.root.querySelector('[data-compose]').addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendFreeQuestion(state);
      }
    });
    renderMessenger(state);
    renderArchive(state);
    renderNotebook(state);
    renderAccuse(state);
  }

  function handleKeyDown(state, event) {
    if (handleSessionKeyDown(state, event)) return;
    if (event.key === 'Escape') {
      const menu = state.root.querySelector('[data-start-menu]');
      if (!menu.hidden) {
        menu.hidden = true;
        return;
      }
      const front = [...state.windows.values()].filter((item) => !item.hidden).sort((a, b) => Number(b.style.zIndex) - Number(a.style.zIndex))[0];
      if (front) closeWindow(state, front.dataset.window);
    }
  }

  function openWindow(state, key) {
    const windowEl = state.windows.get(key);
    if (!windowEl) return;
    windowEl.hidden = false;
    bringToFront(state, key);
    state.root.querySelector('[data-start-menu]').hidden = true;
    if (key === 'messenger') renderMessenger(state);
    if (key === 'archive') renderArchive(state);
    if (key === 'notebook') renderNotebook(state);
    if (key === 'accuse') renderAccuse(state);
    renderTaskbar(state);
  }

  function closeWindow(state, key) {
    const windowEl = state.windows.get(key);
    if (!windowEl) return;
    windowEl.hidden = true;
    if (state.activeWindow === key) state.activeWindow = null;
    renderTaskbar(state);
  }

  function minimizeWindow(state, key) {
    closeWindow(state, key);
  }

  function bringToFront(state, key) {
    const windowEl = state.windows.get(key);
    if (!windowEl) return;
    state.z += 1;
    windowEl.style.zIndex = state.z;
    state.activeWindow = key;
    state.windows.forEach((item, itemKey) => item.classList.toggle('is-active', itemKey === key));
  }

  function toggleStartMenu(state) {
    const menu = state.root.querySelector('[data-start-menu]');
    menu.hidden = !menu.hidden;
  }

  function renderTaskbar(state) {
    const wrap = state.root.querySelector('[data-task-buttons]');
    wrap.innerHTML = Object.entries(appInfo).map(([key, info]) => `<button type="button" data-task="${key}" class="${state.windows.get(key)?.hidden ? '' : 'is-open'}">${info.label}</button>`).join('');
    state.root.querySelector('[data-tokens]').textContent = String(state.save.tokens).padStart(2, '0');
    const clock = state.root.querySelector('[data-clock]');
    if (clock) {
      const hours = String(Math.floor(state.clockMinutes / 60)).padStart(2, '0');
      const minutes = String(state.clockMinutes % 60).padStart(2, '0');
      clock.textContent = `Day ${state.save.day || 2} · ${hours}:${minutes}`;
    }
  }

  function dragMove(state, event) {
    if (!state.drag) return;
    const windowEl = state.windows.get(state.drag.key);
    const rect = state.root.getBoundingClientRect();
    const dx = (event.clientX - state.drag.startX) / state.drag.unit;
    const dy = (event.clientY - state.drag.startY) / state.drag.unit;
    const maxLeft = 100 - (windowEl.offsetWidth / rect.width) * 100;
    const maxTop = 100 - (windowEl.offsetHeight / rect.width) * 100;
    windowEl.style.left = `${Math.max(0, Math.min(maxLeft, state.drag.left + dx))}cqw`;
    windowEl.style.top = `${Math.max(2, Math.min(maxTop, state.drag.top + dy))}cqw`;
  }

  function stopDrag(state) {
    state.drag = null;
  }

  function makePortrait(yb, index) {
    const canvas = document.createElement('canvas');
    canvas.width = 28;
    canvas.height = 28;
    canvas.className = 'c-portrait-canvas';
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    pixel.drawYb(ctx, { x: 14, y: 19, frame: 0 }, yb.color, index);
    return canvas;
  }

  function selectYb(state, index) {
    state.activeYb = index;
    renderMessenger(state);
  }

  function renderMessenger(state) {
    const windowEl = state.windows.get('messenger');
    if (!windowEl) return;
    const list = windowEl.querySelector('[data-yb-list]');
    list.replaceChildren();
    data.ybs.forEach((yb, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `c-yb-row${state.activeYb === index ? ' is-selected' : ''}`;
      button.dataset.yb = index;
      button.append(makePortrait(yb, index));
      button.insertAdjacentHTML('beforeend', `<span><strong>${yb.id}</strong><small>${escapeHtml(yb.trait)}</small></span>${state.histories[index].length ? '<i class="c-new-dot" aria-label="새 답변"></i>' : ''}`);
      list.append(button);
    });
    const yb = data.ybs[state.activeYb];
    const head = windowEl.querySelector('[data-chat-head]');
    head.innerHTML = `<strong>${yb.id}</strong><span>${escapeHtml(yb.roomLabel)} · ${escapeHtml(yb.trait)}</span>`;
    const log = windowEl.querySelector('[data-chat-log]');
    const history = state.histories[state.activeYb];
    log.innerHTML = history.length ? history.map((entry) => renderBubble(entry)).join('') : `<div class="c-system-message">${yb.id} 채널이 열려 있습니다. 질문을 선택하세요.</div>`;
    const questions = windowEl.querySelector('[data-question-list]');
    questions.innerHTML = yb.answers.map((answer, index) => `<button type="button" data-ask="${index}" ${state.save.tokens <= 0 || state.typing ? 'disabled' : ''}>${escapeHtml(answer.question)}</button>`).join('');
    windowEl.querySelector('[data-compose]').value = '';
    log.scrollTop = log.scrollHeight;
  }

  function renderBubble(entry) {
    const type = data.answerTypes[entry.answer.type] || data.answerTypes.unknown;
    const text = entry.typing ? entry.answer.text.slice(0, entry.typed) : entry.answer.text;
    return `<div class="c-bubble" style="--bubble-color:${type.color}"><div class="c-bubble-meta"><strong>${entry.question ? '나 → ' : ''}${entry.answer.from || 'YB'}</strong><span>${type.label}</span></div>${entry.question ? `<p class="c-question-text">${escapeHtml(entry.question)}</p>` : ''}<p class="c-answer-text">${escapeHtml(text)}${entry.typing ? '<i class="c-caret"></i>' : ''}</p></div>`;
  }

  function askQuestion(state, index) {
    if (state.typing || state.save.tokens <= 0) return;
    const yb = data.ybs[state.activeYb];
    const answer = yb.answers[index];
    if (!answer) return;
    state.save.tokens -= 1;
    answerQuestion(state, answer.question, answer);
  }

  function sendFreeQuestion(state) {
    if (state.typing || state.save.tokens <= 0) return;
    const input = state.windows.get('messenger').querySelector('[data-compose]');
    const question = input.value.trim();
    if (!question) return;
    const yb = data.ybs[state.activeYb];
    const match = yb.answers.find((answer) => question.includes(answer.question.slice(0, 3)) || answer.question.includes(question.slice(0, 3)));
    const answer = match || { type: 'unknown', text: '그 질문에 대해서는 아직 확인된 기록이 없어. 다른 단서를 살펴봐.', from: yb.id };
    state.save.tokens -= 1;
    input.value = '';
    answerQuestion(state, question, answer);
  }

  function answerQuestion(state, question, answer) {
    const yb = data.ybs[state.activeYb];
    const entry = { question, answer: { ...answer, from: yb.id }, typed: 0, typing: true };
    state.histories[state.activeYb].push(entry);
    state.typing = entry;
    renderMessenger(state);
    typeAnswer(state, entry);
    if (answer.clue && !state.clues.some((clue) => clue.text === answer.clue)) {
      const clue = data.clues.find((item) => item.text === answer.clue) || { id: `free-${state.clues.length}`, day: state.save.day, text: answer.clue };
      state.clues.push(clue);
      showToast(state, '새 단서가 수첩에 기록되었습니다.');
      renderNotebook(state);
    }
    renderTaskbar(state);
  }

  function typeAnswer(state, entry) {
    if (entry.typed >= entry.answer.text.length) {
      entry.typing = false;
      state.typing = null;
      renderMessenger(state);
      return;
    }
    entry.typed += 1;
    const timer = setTimeout(() => {
      state.timers.delete(timer);
      typeAnswer(state, entry);
    }, window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 35);
    state.timers.add(timer);
    renderMessenger(state);
  }

  function renderArchive(state) {
    const windowEl = state.windows.get('archive');
    const list = windowEl.querySelector('[data-file-list]');
    list.innerHTML = data.records.map((record, index) => {
      const locked = rankFor(state.role) < rankFor(record.role);
      const fileIcon = locked ? '<span class="c-lock-icon" aria-label="잠김"><i></i><i></i><i></i></span>' : '<span class="c-file-icon">□</span>';
      return `<button type="button" data-record="${index}" class="c-file-row${locked ? ' is-locked' : ''}">${fileIcon}<span><strong>${escapeHtml(record.name)}</strong><small>Day ${record.day} · ${escapeHtml(record.grade)}</small></span></button>`;
    }).join('');
  }

  function openRecord(state, index) {
    const record = data.records[index];
    const preview = state.windows.get('archive').querySelector('[data-file-preview]');
    if (rankFor(state.role) < rankFor(record.role)) {
      preview.innerHTML = `<div class="c-denied-mark">!</div><h3>접근 거부</h3><p>${escapeHtml(record.name)}은(는) ${escapeHtml(record.grade)} 등급입니다.</p><p>현재 역할보다 높은 권한이 필요합니다.</p>`;
      return;
    }
    preview.innerHTML = `<div class="c-paper-head"><span>${escapeHtml(record.name)}</span><small>Day ${record.day} · ${escapeHtml(record.grade)}</small></div><pre>${escapeHtml(record.text)}</pre><p class="c-file-foot">읽기 전용 기록 · 일부 원문은 █로 가려져 있습니다.</p>`;
    if (!state.recordClues.has(index)) {
      state.recordClues.add(index);
      state.clues.push({ id: `record-${index}`, day: record.day, text: `기록 ${record.name}: ${record.clue || record.text}` });
      state.save.clues = Math.max(Number(state.save.clues) || 0, state.clues.length);
      renderNotebook(state);
      showToast(state, '기록에서 새 단서를 찾아 수첩에 추가했습니다.');
    }
  }

  function renderNotebook(state) {
    const body = state.windows.get('notebook').querySelector('[data-notebook-body]');
    const groups = [1, 2, 3].map((day) => ({ day, items: state.clues.filter((clue) => clue.day === day) })).filter((group) => group.items.length);
    body.innerHTML = groups.length ? groups.map((group) => `<section><h3>Day ${group.day}</h3>${group.items.map((clue) => `<p>${escapeHtml(clue.text)}</p>`).join('')}</section>`).join('') : '<p class="c-empty-text">아직 기록된 단서가 없습니다.</p>';
  }

  function renderAccuse(state) {
    const grid = state.windows.get('accuse').querySelector('[data-accuse-grid]');
    grid.innerHTML = data.ybs.map((yb, index) => `<button type="button" class="c-suspect${state.suspect === index ? ' is-picked' : ''}" data-suspect="${index}"><span class="c-suspect-dot" style="background:${yb.color}"></span><strong>${yb.id}</strong><small>${escapeHtml(yb.trait)}</small></button>`).join('');
    state.windows.get('accuse').querySelector('[data-submit-accuse]').disabled = state.suspect === null;
  }

  function selectSuspect(state, index) {
    state.suspect = index;
    renderAccuse(state);
  }

  function submitAccuse(state) {
    if (state.suspect === null) return;
    state.windows.get('accuse').querySelector('[data-accuse-result]').textContent = `${data.ybs[state.suspect].id} 지목이 제출됨. 판정은 서버 연결 후 진행됩니다.`;
  }

  function showToast(state, message) {
    const toast = state.root.querySelector('[data-toast]');
    toast.textContent = message;
    toast.classList.add('is-visible');
    const timer = setTimeout(() => {
      state.timers.delete(timer);
      toast.classList.remove('is-visible');
    }, 2200);
    state.timers.add(timer);
  }

  function leave(state) {
    state.onExit();
  }

  window.Play = window.Play || {};
  window.Play.c = { enter, mount, unmount: () => instance?.unmount() };
})();
