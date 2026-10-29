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
    notebook: { label: '수첩', icon: 'note' },
    map: { label: '지도', icon: 'map' },
    accuse: { label: '지목', icon: 'scale' },
  };

  const DAY_START_MINUTES = 14 * 60 + 20;

  function currentDay(state) {
    return Number(state.save.current_day || state.save.day) || 1;
  }

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

  function iconMarkup(type) {
    return `<span class="c-icon-art c-icon-${type}" aria-hidden="true"><i></i><i></i><i></i><i></i></span>`;
  }

  function buildMarkup(state) {
    const label = roleLabel(state.role);
    return `<div class="c-shell">
      <div class="c-desktop" data-desktop>
        <div class="c-system-line"><span>YB-LAB OS 2.0</span><span>단말기 07 · 조사 세션</span></div>
        <div class="c-connection" data-connection hidden role="status" aria-live="polite">서버와 연결이 끊겼습니다 · <button type="button" data-retry-connection>다시 시도</button></div>
        <div class="c-wall" aria-hidden="true"><div class="c-wall-lab" data-wall-lab></div><div class="c-wall-shade"></div></div>
        <div class="c-desktop-icons" aria-label="프로그램" data-desktop-icons></div>
        <div class="c-window-layer" data-window-layer></div>
        <div class="c-start-menu" data-start-menu hidden>
          <div class="c-start-head">연구소 단말기</div>
          <div class="c-start-apps" data-start-apps></div>
          <button type="button" data-action="sessions"><span class="c-menu-exit">↪</span><span>세션 선택으로</span></button>
          <button type="button" data-action="exit"><span class="c-menu-exit">⏻</span><span>정문으로 나가기</span></button>
        </div>
        <div class="c-toast" data-toast role="status" aria-live="polite"></div>
        <div class="c-dialog-layer" data-day-dialog hidden>
          <section class="c-dialog" role="alertdialog" aria-modal="true" aria-labelledby="c-day-dialog-title" aria-describedby="c-day-dialog-text">
            <div class="c-window-bar"><span class="c-window-title" id="c-day-dialog-title">다음 Day로 넘어가기</span></div>
            <div class="c-dialog-body">
              <p id="c-day-dialog-text" data-day-dialog-text></p>
              <div class="c-dialog-actions"><button type="button" data-day-cancel>취소</button><button type="button" class="c-submit" data-day-confirm>넘어가기</button></div>
            </div>
          </section>
        </div>
        <div class="c-day-curtain" data-day-curtain hidden aria-hidden="true"><strong data-day-curtain-title></strong><span data-day-curtain-text></span></div>
        <div class="c-taskbar">
          <button type="button" class="c-start-button" data-start>시작</button>
          <div class="c-task-buttons" data-task-buttons></div>
          <div class="c-task-status"><span data-clock>Day ${state.save.day || 2} · 14:20</span><span>${escapeHtml(label)}</span></div>
          <button type="button" class="c-day-next" data-day-next>다음 Day로</button>
        </div>
      </div>
    </div>`;
  }

  function entryMonitor(inner) {
    return `<div class="c-entry-shell"><div class="c-entry-monitor"><div class="c-entry-screen">${inner}</div></div></div>`;
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
        ? `<strong>${escapeHtml(roleLabel(save.role))}</strong><span>Day ${save.day}/${context.maxDay}</span><small>마지막 접속 ${escapeHtml(formatDate(save.last_played_at))}</small>`
        : `<strong>발급 전</strong><span>새 실험 관찰</span><small>역할: ${escapeHtml(roleLabel(context.role || 'grad'))}</small>`;
      return `<button type="button" class="c-session-card${empty ? ' is-empty' : ''}${selected ? ' is-selected' : ''}${reading ? ' is-reading' : ''}${mode === 'new' && save ? ' is-overwrite' : ''}" data-slot="${index}" ${disabled || state.phase === 'reading' ? 'disabled' : ''}>
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

  function formatDate(value) {
    if (!value) return '기록 없음';
    const raw = String(value).trim();
    const utc = /(?:Z|[+-]\d{2}:\d{2})$/i.test(raw) ? raw : `${raw.replace(' ', 'T')}Z`;
    const date = new Date(utc);
    if (Number.isNaN(date.getTime())) return '기록 없음';
    const parts = new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric',
    }).formatToParts(date);
    const month = parts.find((part) => part.type === 'month').value;
    const day = parts.find((part) => part.type === 'day').value;
    return `${month}월 ${day}일`;
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

  // 모니터 켜짐: 검은 화면에서 출입증 화면이 천천히 밝아짐
  function startBootSequence(state) {
    state.phase = 'session';
    renderSession(state);
    if (!reduceMotion) state.root.querySelector('[data-entry-session]')?.classList.add('is-powering-on');
  }

  function beginSessionRead(state, index) {
    state.phase = 'reading';
    state.readingText = '';
    state.selected = index;
    state.reading = index;
    if (!reduceMotion) {
      scanBadge(state, index);
      return;
    }
    state.readingText = '확인됨';
    state.root.className = 'screen play-c play-c-entry';
    state.root.hidden = false;
    state.root.innerHTML = buildSessionMarkup(state);
    addTimer(state, () => completeSessionRead(state, index), 40);
  }

  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function roleScope(role) {
    return { prof: '교수 전용 대화까지', grad: '보안 관련 대화까지', std: '일반 대화만' }[role] || '일반 대화만';
  }

  function setReader(root, color, text) {
    root.querySelectorAll('.c-reader-leds i').forEach((led) => {
      led.style.background = color;
      led.style.boxShadow = `0 0 1.3cqw ${color}`;
    });
    const status = root.querySelector('[data-reader-status]');
    if (status) {
      status.textContent = text;
      status.style.color = color;
    }
  }

  // 출입증 광학 판독: 카드 확대 → 빛줄 스캔 → 판독표 → 승인 도장 → 바탕화면으로
  async function scanBadge(state, index) {
    const root = state.root;
    const save = state.mode === 'new'
      ? { role: state.context.role, day: 1 }
      : state.context.saves[index];
    const session = root.querySelector('[data-entry-session]');
    const screen = root.querySelector('.c-entry-screen');
    const card = root.querySelector(`[data-slot="${index}"]`);
    if (!session || !card || !save) return;
    session.classList.add('is-scanning');
    card.classList.add('is-flying');
    const c = card.getBoundingClientRect();
    const sc = screen.getBoundingClientRect();
    const dx = sc.left + sc.width * 0.3 - (c.left + c.width / 2);
    const dy = sc.top + sc.height * 0.47 - (c.top + c.height / 2);
    setReader(root, '#e8b04a', '광학 판독 중…');
    await card.animate([
      { transform: 'translate(0, 0) rotate(0deg) scale(1)' },
      { transform: `translate(${dx}px, ${dy}px) rotate(0deg) scale(1.35)` },
    ], { duration: 520, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'forwards' }).finished;
    if (!isLiveState(state)) return;

    const beam = document.createElement('div');
    beam.className = 'c-scan-beam';
    beam.innerHTML = '<i></i>';
    card.append(beam);
    beam.querySelector('i').animate(
      [{ top: '-6%' }, { top: '100%' }],
      { duration: 700, iterations: 2, direction: 'alternate', easing: 'ease-in-out' },
    );

    const readout = document.createElement('div');
    readout.className = 'c-scan-readout';
    screen.append(readout);
    const lines = [
      ['판독', `출입증 ${index + 1}번`],
      ['역할', roleLabel(save.role)],
      ['진행', `Day ${save.day} / ${data.maxDay}`],
      ['대화로 알 수 있는 범위', roleScope(save.role)],
    ];
    for (const [label, value] of lines) {
      await wait(230);
      if (!isLiveState(state)) return;
      readout.insertAdjacentHTML('beforeend', `<p><span>${label}</span><b>${escapeHtml(value)}</b></p>`);
    }
    await wait(260);
    if (!isLiveState(state)) return;
    const stamp = document.createElement('div');
    stamp.className = 'c-scan-stamp';
    stamp.textContent = '승인';
    card.append(stamp);
    stamp.animate([
      { transform: 'translate(-50%, -50%) rotate(-14deg) scale(2.4)', opacity: 0 },
      { transform: 'translate(-50%, -50%) rotate(-14deg) scale(1)', opacity: 1 },
    ], { duration: 170, easing: 'cubic-bezier(.5,0,.75,0)', fill: 'forwards' });
    await wait(170);
    card.animate([{ translate: '0 0' }, { translate: '0 .5cqw' }, { translate: '0 0' }], { duration: 160 });
    setReader(root, '#70c6a5', '승인됨');
    await insertCard(state, { card, reader: root.querySelector('[data-reader]'), screen });
    if (!isLiveState(state)) return;
    // 애니메이션으로만 잡힌 위치·어둡기를 스타일로 굳힘 (바탕화면으로 넘어갈 때 쓰는 화면 복사본이 같은 모습이 되도록)
    root.getAnimations({ subtree: true }).forEach((animation) => {
      try { animation.commitStyles(); } catch (error) { /* 굳힐 수 없는 것은 무시 */ }
      animation.cancel();
    });
    completeSessionRead(state, index);
  }

  // 승인 뒤 카드를 리더기에 꽂는 연출 (약 2초)
  // 잠깐 쉼 → 카드가 리더기 크기로 줄며 슬롯 위로 → 잠깐 맞춤 → 윗판 뒤로 꽂힘 → 딸깍·초록 빛 → 단말기 화면이 꺼짐
  async function insertCard(state, { card, reader, screen }) {
    const REST_AFTER_APPROVE = 420; // 승인 도장 뒤, 카드가 움직이기 전 쉬는 시간
    const HOVER_OVER_READER = 260; // 리더기 위에서 맞추는 시간
    const CARD_WIDTH_RATIO = 0.75; // 슬롯 폭 대비 카드 폭
    const STUB = 0.3; // 다 꽂았을 때 슬롯 위로 남는 카드 윗부분 비율
    const plateTop = reader.querySelector('.c-reader-top').getBoundingClientRect().top + 2; // 이 선 아래는 리더기 속
    const slot = reader.querySelector('.c-reader-slot').getBoundingClientRect();
    const status = reader.querySelector('[data-reader-status]');
    const leds = reader.querySelectorAll('.c-reader-leds i');

    await wait(REST_AFTER_APPROVE);
    if (!isLiveState(state)) return;

    // 날아오기 애니메이션을 걷어내고 위치를 직접 정함 (겹쳐 쓰면 크기 변화에 이동량이 같이 줄어 슬롯과 어긋남)
    const now = card.getBoundingClientRect();
    card.getAnimations().forEach((animation) => animation.cancel());
    card.style.transform = 'none';
    const layout = card.getBoundingClientRect();
    const lx = layout.left + layout.width / 2;
    const ly = layout.top + layout.height / 2;
    const fit = Math.min(1, (slot.width * CARD_WIDTH_RATIO) / card.offsetWidth);
    const height = card.offsetHeight * fit;
    const ox = now.left + now.width / 2 - lx;
    const oy = now.top + now.height / 2 - ly;
    const dx = slot.left + slot.width / 2 - lx;
    const dy = plateTop - 4 - height / 2 - ly;

    screen.querySelector('.c-scan-readout')?.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, fill: 'forwards' });
    await card.animate([
      { translate: `${ox}px ${oy}px`, scale: '1.35', rotate: '0deg' },
      { translate: `${ox + (dx - ox) * 0.7}px ${oy + (dy - oy) * 0.7}px`, scale: String(fit + (1.35 - fit) * 0.25), rotate: '-4deg', offset: 0.7 },
      { translate: `${dx}px ${dy}px`, scale: String(fit), rotate: '0deg' },
    ], { duration: 360, easing: 'cubic-bezier(.3,.7,.3,1)', fill: 'forwards' }).finished;
    await wait(HOVER_OVER_READER);
    if (!isLiveState(state)) return;

    // 카드 아래쪽부터 리더기 윗판 뒤로 들어감
    status.textContent = '카드 삽입 중…';
    const slide = { duration: 380, easing: 'cubic-bezier(.5,0,.75,1)', fill: 'forwards' };
    card.animate([{ translate: `${dx}px ${dy}px` }, { translate: `${dx}px ${dy + height * (1 - STUB) + 4}px` }], slide);
    await card.animate([{ clipPath: 'inset(-10% -10% 0% -10%)' }, { clipPath: `inset(-10% -10% ${(1 - STUB) * 100}% -10%)` }], slide).finished;
    if (!isLiveState(state)) return;

    // 딸깍: 리더기가 한 번 흔들리고 LED가 커지며 초록 빛이 번짐
    status.textContent = '접속 중…';
    reader.animate([{ translate: '0 0' }, { translate: '0 .4cqw' }, { translate: '0 0' }], { duration: 110, easing: 'steps(3)' });
    leds.forEach((led) => led.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.9)' }, { transform: 'scale(1)' }], { duration: 300 }));
    const glow = reader.animate([
      { boxShadow: '.45cqw .45cqw 0 #0c1116, 0 0 0 0 rgba(112,198,165,0)' },
      { boxShadow: '.45cqw .45cqw 0 #0c1116, 0 0 3.2cqw 1.4cqw rgba(112,198,165,.9)', offset: 0.4 },
      { boxShadow: '.45cqw .45cqw 0 #0c1116, 0 0 1.4cqw .5cqw rgba(112,198,165,.45)' },
    ], { duration: 520, fill: 'forwards' });
    await wait(320);
    if (!isLiveState(state)) return;

    // 단말기 화면이 꺼짐 (어두운 막이 5단계로 내려앉음)
    const dim = document.createElement('div');
    Object.assign(dim.style, { position: 'absolute', inset: '0', zIndex: '30', background: '#050708', opacity: '0', pointerEvents: 'none' });
    screen.append(dim);
    await dim.animate([{ opacity: 0 }, { opacity: 0.94 }], { duration: 280, easing: 'steps(5, end)', fill: 'forwards' }).finished;
    await glow.finished;
  }

  async function completeSessionRead(state, index) {
    if (!isLiveState(state)) return;
    const leaving = state.root.querySelector('.c-entry-shell')?.cloneNode(true);
    const overwrite = state.mode === 'new' && Boolean(state.context.saves[index]);
    const waitTimer = setTimeout(() => {
      if (!isLiveState(state)) return;
      state.readingText = '기록 불러오는 중…';
      const readerStatus = state.root.querySelector('[data-reader-status]');
      // 연출 뒤에는 화면을 다시 그리지 않고 글자만 바꿈 (다시 그리면 꺼진 화면이 카드 화면으로 되돌아감)
      if (readerStatus && !reduceMotion) readerStatus.textContent = state.readingText;
      else renderSession(state);
    }, 300);
    try {
      await state.context.onStart?.(index, state.mode, overwrite, () => isLiveState(state));
    } catch (error) {
      clearTimeout(waitTimer);
      if (error.code === 'AUTH_REQUIRED') {
        finishEntry(state);
        return state.context.onAuthExpired?.();
      }
      if (!isLiveState(state)) return;
      if (error.code === 'NOT_FOUND') {
        const fresh = await state.context.refreshSaves?.();
        if (fresh) state.context.saves = fresh;
      }
      if (error.code === 'STATE_CONFLICT') {
        const fresh = await state.context.refreshSaves?.();
        if (fresh) state.context.saves = fresh;
      }
      state.phase = 'session';
      state.selected = index;
      state.confirmSlot = null;
      state.readingText = error.message;
      renderSession(state);
      setReader(state.root, '#e0605a', error.message || window.Api.messageFor(error.code));
      return;
    }
    clearTimeout(waitTimer);
    if (!isLiveState(state)) return;
    if (state.entry) finishEntry(state);
    // 단말기 화면에서 바탕화면으로: 잠깐 겹쳐 두었다가 흐려지며 사라짐 (전환 연출은 따로 정할 예정)
    if (!leaving || reduceMotion) return;
    const cover = document.createElement('div');
    cover.className = 'c-entry-cover';
    cover.append(leaving);
    state.root.append(cover);
    cover.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 280, easing: 'ease-out' }).finished.then(() => cover.remove());
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
    if (state.phase === 'reading') return;
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
    // 바탕화면 시계가 출입증 화면 위에서 작업 표시줄을 찾지 않도록 멈춤
    if (state.clockTimer) clearInterval(state.clockTimer);
    state.clockTimer = null;
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
      chatRows: data.ybs.map(() => []),
      hasMoreChats: data.ybs.map(() => false),
      oldestChatIds: data.ybs.map(() => null),
      chatOlderLoading: data.ybs.map(() => false),
      chatOlderWaitVisible: data.ybs.map(() => false),
      suspect: null,
      typing: null,
      timers: new Set(),
      drag: null,
      resize: null,
      verdictShown: false,
      clockMinutes: DAY_START_MINUTES,
      clockTimer: null,
      dayChanging: false,
      chatPending: false,
      chatWaitVisible: false,
      loadingInitial: false,
      loadingVisible: false,
      onAuthExpired: options?.onAuthExpired || sessionContext?.onAuthExpired,
      onSaveMissing: options?.onSaveMissing || sessionContext?.onSaveMissing,
      memoTimer: null,
      // 새 소식이 있는 프로그램: 아이콘·작업 표시줄에 점 표시, 열면 사라짐
      unread: new Set(['messenger']),
      onExit: options?.onExit || (() => {}),
    };
    instance = { state, unmount: () => unmount(state) };
    root.className = 'screen play-c';
    root.hidden = false;
    root.innerHTML = buildMarkup(state);
    // 바탕화면: 정문에서 보던 연구소를 글씨 없이 어둡게 깖. 그림을 못 뜨면 단색 배경
    const wallUrl = window.Play.labWallpaperUrl?.();
    if (wallUrl) root.querySelector('[data-wall-lab]').style.backgroundImage = `url(${wallUrl})`;
    createWindows(state);
    bindEvents(state);
    renderTaskbar(state);
    loadGameData(state);
    state.connection = (event) => {
      const banner = root.querySelector('[data-connection]');
      if (banner) banner.hidden = event.detail.online;
    };
    window.addEventListener('api:connection', state.connection);
    // 창 없이 아이콘만 있는 바탕화면에서 시작. 전환 연출이 끝난 뒤 할 일을 한 번 알림
    addTimer(state, () => showToast(state, 'YB들에게 물어보고 수첩 메모에 정리해 보세요.'), reduceMotion ? 300 : 1100);
    state.clockTimer = setInterval(() => {
      state.clockMinutes = (state.clockMinutes + 1) % (24 * 60);
      renderTaskbar(state);
    }, 3000);
  }

  async function loadGameData(state) {
    if (state.loadingInitial) return;
    state.loadingInitial = true;
    state.loadingVisible = false;
    state.loadFailed = false;
    const delay = setTimeout(() => { if (isLiveState(state) && state.loadingInitial) { state.loadingVisible = true; renderMessenger(state); } }, 300);
    try {
      const histories = await Promise.all(data.ybs.map((yb) => window.Api.listChats(state.save.save_id, yb.id)));
      if (!isLiveState(state)) return;
      if (histories.some((history) => !Array.isArray(history?.messages) || typeof history.has_more !== 'boolean')) throw new window.Api.ApiError(200, 'INVALID_RESPONSE', window.Api.messageFor('INVALID_RESPONSE'));
      state.chatRows = histories.map(({ messages }) => messages.slice());
      state.histories = histories.map(({ messages }, index) => rowsToEntries(messages, data.ybs[index].id));
      state.hasMoreChats = histories.map((history) => history.has_more);
      state.oldestChatIds = histories.map((history) => history.messages[0]?.message_id ?? null);
      state.loadingInitial = false;
      state.loadingVisible = false;
      renderMessenger(state);
      renderAccuse(state);
    } catch (error) {
      if (isLiveState(state)) {
        state.loadingInitial = false;
        state.loadFailed = true;
        renderMessenger(state);
        handleError(state, error);
      }
    } finally {
      clearTimeout(delay);
      if (state.retryLoadAfter && isLiveState(state)) { state.retryLoadAfter = false; loadGameData(state); }
    }
  }

  function rowsToEntries(rows, aiId) {
    const entries = [];
    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i];
      if (row.sender === 'user') {
        const answer = rows[i + 1]?.sender === 'ai' ? rows[++i] : null;
        entries.push({
          message_id: row.message_id,
          question: row.content,
          answer: { text: answer?.content || '응답 없음', type: answer?.response_type || 'unknown', from: aiId },
          typed: answer?.content?.length || 0,
          typing: false,
        });
      } else {
        entries.push({ message_id: row.message_id, question: '', answer: { text: row.content, type: row.response_type || 'unknown', from: aiId }, typed: row.content.length, typing: false });
      }
    }
    return entries;
  }

  function handleError(state, error) {
    if (!isLiveState(state)) return;
    if (error.code === 'AUTH_REQUIRED') return state.onAuthExpired?.();
    if (error.code === 'NOT_FOUND') { showToast(state, error.message); state.onSaveMissing?.(); return; }
    showToast(state, error.message || window.Api.messageFor(error.code));
  }

  async function retryConnection(state) {
    const button = state.root.querySelector('[data-retry-connection]');
    if (!button || !isLiveState(state) || button.disabled) return;
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    const label = button.textContent;
    const waitTimer = setTimeout(() => { if (button.isConnected) button.textContent = '연결 확인 중…'; }, 300);
    try {
      const user = await window.Api.me();
      sessionContext?.onUser?.(user);
      clearTimeout(waitTimer);
      button.textContent = label;
      if (!isLiveState(state)) return;
      const banner = state.root.querySelector('[data-connection]');
      if (!banner) return;
      banner.hidden = true;
      if (state.loadingInitial) state.retryLoadAfter = true; else await loadGameData(state);
    }
    catch (error) { clearTimeout(waitTimer); handleError(state, error); }
    finally { clearTimeout(waitTimer); if (isLiveState(state) && button.isConnected) { button.disabled = false; button.removeAttribute('aria-busy'); button.textContent = label; } }
  }

  function unmount(state) {
    document.removeEventListener('keydown', state.keydown);
    window.removeEventListener('api:connection', state.connection);
    document.removeEventListener('pointermove', state.pointermove);
    document.removeEventListener('pointerup', state.pointerup);
    state.root.removeEventListener('click', state.click);
    state.root.removeEventListener('pointerdown', state.pointerdown);
    state.sessionClick && state.root.removeEventListener('click', state.sessionClick);
    state.timers.forEach((timer) => clearTimeout(timer));
    state.timers.clear();
    if (state.memoTimer) clearTimeout(state.memoTimer);
    if (state.clockTimer) clearInterval(state.clockTimer);
    state.root.replaceChildren();
    if (instance?.state === state) instance = null;
  }

  function createWindows(state) {
    const layer = state.root.querySelector('[data-window-layer]');
    const windows = [
      ['messenger', 'YB 메신저', '15cqw', '8cqw', '58cqw', '57cqw', buildMessenger()],
      ['notebook', '수첩', '20cqw', '20cqw', '42cqw', '45cqw', buildNotebook()],
      ['map', '지도', '14cqw', '3cqw', '70cqw', '56cqw', `<div class="c-map" data-map>${window.Play.map.markup()}</div>`],
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
      windowEl.dataset.width = width;
      windowEl.dataset.height = height;
      windowEl.innerHTML = `<div class="c-window-bar" data-drag-handle><span class="c-window-title">${title}</span><span class="c-window-actions"><button type="button" data-window-min="${key}" aria-label="최소화">_</button><button type="button" data-window-close="${key}" aria-label="닫기">×</button></span></div><div class="c-window-body" data-window-body>${content}</div><span class="c-window-resize" data-resize-handle aria-hidden="true"></span>`;
      layer.append(windowEl);
      state.windows.set(key, windowEl);
      if (key === 'map') window.Play.map.bind(windowEl);
    });
  }

  function buildMessenger() {
    return `<div class="c-messenger"><aside class="c-yb-list" data-yb-list></aside><section class="c-chat-panel"><div class="c-chat-head" data-chat-head></div><div class="c-chat-log" data-chat-log aria-live="polite"></div><div class="c-question-list" data-question-list></div><p data-chat-error role="status" aria-live="polite"></p><div class="c-compose"><textarea data-compose rows="1" placeholder="자유 질문을 입력하세요"></textarea><button type="button" data-send>보내기</button></div></section></div>`;
  }

  function buildNotebook() {
    return `<div class="c-notebook-body"><label class="c-memo"><span>메모</span><textarea data-memo placeholder="YB들에게 들은 내용과 의심 가는 점을 자유롭게 적어 두세요."></textarea></label></div>`;
  }

  function buildAccuse() {
    return `<div class="c-accuse-body"><p>지금까지의 기록으로 게임 결과를 조작한 AI 한 명을 지목합니다. 지목은 한 번만 할 수 있습니다.</p><div class="c-accuse-grid" data-accuse-grid></div><div class="c-accuse-result" data-accuse-result></div><button type="button" class="c-submit" data-submit-accuse disabled>제출</button></div>`;
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
      if (event.target.closest('[data-load-older]')) loadOlderChats(state, state.activeYb);
      const suspect = event.target.closest('[data-suspect]')?.dataset.suspect;
      if (suspect !== undefined) selectSuspect(state, Number(suspect));
      if (event.target.closest('[data-send]')) sendFreeQuestion(state);
      if (event.target.closest('[data-retry-chat]')) retryChat(state, event.target.closest('[data-retry-chat]').dataset.retryChat);
      const retryLoad = event.target.closest('[data-retry-load]');
      if (retryLoad) { retryLoad.disabled = true; retryLoad.setAttribute('aria-busy', 'true'); loadGameData(state).finally(() => { retryLoad.disabled = false; retryLoad.removeAttribute('aria-busy'); }); }
      if (event.target.closest('[data-retry-connection]')) retryConnection(state);
      if (event.target.closest('[data-submit-accuse]')) submitAccuse(state);
      if (event.target.closest('[data-accuse-cancel]')) { state.accusationRequestId = null; renderAccuse(state); }
      if (event.target.closest('[data-accuse-confirm]')) confirmAccuse(state);
      if (event.target.closest('[data-verdict-open]')) showVerdict(state);
      if (event.target.closest('[data-verdict-back]')) closeVerdict(state);
      if (event.target.closest('[data-verdict-exit]')) leave(state);
      if (event.target.closest('[data-day-next]')) openDayDialog(state);
      if (event.target.closest('[data-day-cancel]')) closeDayDialog(state);
      if (event.target.closest('[data-day-confirm]')) advanceDay(state);
    };
    state.root.addEventListener('click', state.click);
    state.pointerdown = (event) => {
      const resizeHandle = event.target.closest('[data-resize-handle]');
      if (resizeHandle) {
        const windowEl = resizeHandle.closest('[data-window]');
        bringToFront(state, windowEl.dataset.window);
        const unit = state.root.getBoundingClientRect().width / 100;
        state.resize = { key: windowEl.dataset.window, startX: event.clientX, startY: event.clientY, width: windowEl.offsetWidth / unit, height: windowEl.offsetHeight / unit, unit };
        event.preventDefault();
        return;
      }
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
    const memo = state.root.querySelector('[data-memo]');
    memo.value = state.save.memo || '';
    memo.addEventListener('input', () => {
      clearTimeout(state.memoTimer);
      const value = memo.value;
      state.memoTimer = setTimeout(async () => {
        try {
          const result = await window.Api.saveMemo(state.save.save_id, value);
          state.save.memo = result.memo;
        } catch (error) {
          if (isLiveState(state)) handleError(state, error);
        }
      }, 600);
    });
    renderLaunchers(state);
    renderMessenger(state);
    renderAccuse(state);
  }

  // 지목은 마지막 Day에만 열린다
  function appOpen(state, key) {
    return key !== 'accuse' || currentDay(state) >= data.maxDay;
  }

  function openApps(state) {
    return Object.entries(appInfo).filter(([key]) => appOpen(state, key));
  }

  function unreadDot(state, key) {
    return state.unread.has(key) ? '<i class="c-unread-dot" aria-label="새 소식"></i>' : '';
  }

  function renderLaunchers(state) {
    state.root.querySelector('[data-desktop-icons]').innerHTML = openApps(state).map(([key, info]) => `<button type="button" class="c-desktop-icon" data-open="${key}">${iconMarkup(info.icon)}${unreadDot(state, key)}<span>${info.label}</span></button>`).join('');
    state.root.querySelector('[data-start-apps]').innerHTML = openApps(state).map(([key, info]) => `<button type="button" data-open="${key}">${iconMarkup(info.icon)}<span>${info.label}</span>${unreadDot(state, key)}</button>`).join('');
  }

  // 그 창이 이미 열려 있으면 바로 보고 있으므로 점을 달지 않음
  function markUnread(state, key) {
    if (state.windows.get(key)?.hidden === false) return;
    state.unread.add(key);
    renderLaunchers(state);
    renderTaskbar(state);
  }

  function handleKeyDown(state, event) {
    if (handleSessionKeyDown(state, event)) return;
    if (state.root.querySelector('[data-verdict]')) {
      if (event.key === 'Escape') closeVerdict(state);
      return;
    }
    if (!state.root.querySelector('[data-day-dialog]')?.hidden) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeDayDialog(state);
      }
      return;
    }
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
    if (!windowEl || !appOpen(state, key)) return;
    windowEl.hidden = false;
    bringToFront(state, key);
    state.root.querySelector('[data-start-menu]').hidden = true;
    if (state.unread.delete(key)) renderLaunchers(state);
    if (key === 'messenger') renderMessenger(state);
    if (key === 'accuse') renderAccuse(state);
    renderTaskbar(state);
  }

  function hideWindow(state, key) {
    const windowEl = state.windows.get(key);
    if (!windowEl) return;
    windowEl.hidden = true;
    if (state.activeWindow === key) state.activeWindow = null;
    renderTaskbar(state);
  }

  // 닫기: 다음에 열 때 처음 크기로. 위치는 그대로 두되 바탕화면 밖으로 나가지 않게 당김
  function closeWindow(state, key) {
    const windowEl = state.windows.get(key);
    if (!windowEl) return;
    windowEl.style.width = windowEl.dataset.width;
    windowEl.style.height = windowEl.dataset.height;
    windowEl.style.left = `${Math.min(parseFloat(windowEl.style.left), 100 - parseFloat(windowEl.dataset.width))}cqw`;
    const rect = state.root.getBoundingClientRect();
    const maxTop = rect.height / (rect.width / 100) - 4.3 - parseFloat(windowEl.dataset.height);
    windowEl.style.top = `${Math.max(2, Math.min(parseFloat(windowEl.style.top), maxTop))}cqw`;
    hideWindow(state, key);
  }

  // 최소화: 크기·위치 그대로 숨김
  function minimizeWindow(state, key) {
    hideWindow(state, key);
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
    if (!wrap) return;
    wrap.innerHTML = openApps(state).map(([key, info]) => `<button type="button" data-task="${key}" class="${state.windows.get(key)?.hidden ? '' : 'is-open'}">${info.label}${unreadDot(state, key)}</button>`).join('');
    const next = state.root.querySelector('[data-day-next]');
    if (next) {
      const last = currentDay(state) >= data.maxDay;
      next.disabled = last || state.dayChanging;
      next.textContent = last ? '마지막 Day' : '다음 Day로';
    }
    const clock = state.root.querySelector('[data-clock]');
    if (clock) {
      const hours = String(Math.floor(state.clockMinutes / 60)).padStart(2, '0');
      const minutes = String(state.clockMinutes % 60).padStart(2, '0');
      clock.textContent = `Day ${state.save.day || 2} · ${hours}:${minutes}`;
    }
  }

  function dragMove(state, event) {
    if (state.resize) {
      resizeMove(state, event);
      return;
    }
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
    state.resize = null;
  }

  // 창 오른쪽 아래 모서리를 끌어 크기 조절. 바탕화면(작업 표시줄 위) 밖으로는 못 나감
  function resizeMove(state, event) {
    const { key, startX, startY, width, height, unit } = state.resize;
    const windowEl = state.windows.get(key);
    const rect = state.root.getBoundingClientRect();
    const maxWidth = 100 - parseFloat(windowEl.style.left);
    const maxHeight = rect.height / unit - 4.3 - parseFloat(windowEl.style.top);
    const nextWidth = Math.max(22, Math.min(maxWidth, width + (event.clientX - startX) / unit));
    const nextHeight = Math.max(19, Math.min(maxHeight, height + (event.clientY - startY) / unit));
    windowEl.style.width = `${nextWidth}cqw`;
    windowEl.style.height = `${nextHeight}cqw`;
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

  function renderMessenger(state, preserveScroll = null) {
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
    head.innerHTML = `<strong>${yb.id}</strong><span>${escapeHtml(yb.trait)}</span>`;
    const log = windowEl.querySelector('[data-chat-log]');
    const history = state.histories[state.activeYb];
    const older = state.hasMoreChats[state.activeYb] ? `<button type="button" class="c-load-older" data-load-older ${state.chatOlderLoading[state.activeYb] ? 'disabled' : ''}>${state.chatOlderWaitVisible[state.activeYb] ? '불러오는 중…' : '이전 대화 더 보기'}</button>` : '';
    log.innerHTML = `${older}${history.length ? history.map((entry) => renderBubble(entry)).join('') : state.loadingInitial && state.loadingVisible ? '<div role="status">불러오는 중…</div>' : state.loadFailed ? '<div role="status">불러오지 못했습니다 · <button type="button" data-retry-load>다시 시도</button></div>' : `<div class="c-system-message">${yb.id} 채널이 열려 있습니다. 질문을 선택하세요.</div>`}`;
    const questions = windowEl.querySelector('[data-question-list]');
    questions.innerHTML = yb.questions.map((question, index) => `<button type="button" data-ask="${index}" ${state.chatPending ? 'disabled' : ''}>${escapeHtml(question)}</button>`).join('');
    windowEl.querySelector('[data-send]').disabled = state.chatPending;
    windowEl.querySelector('[data-send]').setAttribute('aria-busy', String(state.chatPending));
    const chatError = windowEl.querySelector('[data-chat-error]');
    if (chatError && !state.chatValidationError) chatError.textContent = '';
    windowEl.querySelector('[data-send]').textContent = state.chatWaitVisible ? '보내는 중…' : '보내기';
    if (preserveScroll) log.scrollTop = preserveScroll.top + log.scrollHeight - preserveScroll.height;
    else log.scrollTop = log.scrollHeight;
  }

  async function loadOlderChats(state, index) {
    if (state.chatOlderLoading[index] || !state.hasMoreChats[index]) return;
    const log = state.windows.get('messenger').querySelector('[data-chat-log]');
    const scroll = { height: log.scrollHeight, top: log.scrollTop };
    state.chatOlderLoading[index] = true;
    state.chatOlderWaitVisible[index] = false;
    if (state.activeYb === index) log.querySelector('[data-load-older]').disabled = true;
    const waitTimer = setTimeout(() => {
      state.chatOlderWaitVisible[index] = true;
      const button = state.windows.get('messenger')?.querySelector('[data-load-older]');
      if (state.activeYb === index && button) button.textContent = '불러오는 중…';
    }, 300);
    try {
      const page = await window.Api.listChats(state.save.save_id, data.ybs[index].id, state.oldestChatIds[index]);
      clearTimeout(waitTimer);
      if (!isLiveState(state)) return;
      if (!Array.isArray(page?.messages) || typeof page.has_more !== 'boolean') throw new window.Api.ApiError(200, 'INVALID_RESPONSE', window.Api.messageFor('INVALID_RESPONSE'));
      state.chatRows[index].unshift(...page.messages);
      state.chatRows[index].sort((a, b) => Number(a.message_id) - Number(b.message_id));
      state.histories[index] = rowsToEntries(state.chatRows[index], data.ybs[index].id);
      state.hasMoreChats[index] = page.has_more;
      state.oldestChatIds[index] = state.chatRows[index][0]?.message_id ?? state.oldestChatIds[index];
      state.chatOlderLoading[index] = false;
      state.chatOlderWaitVisible[index] = false;
      if (state.activeYb === index) renderMessenger(state, scroll);
    } catch (error) {
      clearTimeout(waitTimer);
      state.chatOlderLoading[index] = false;
      state.chatOlderWaitVisible[index] = false;
      if (isLiveState(state)) {
        if (state.activeYb === index) renderMessenger(state, scroll);
        handleError(state, error);
      }
    }
  }

  function renderBubble(entry) {
    const type = data.answerTypes[entry.answer.type] || data.answerTypes.unknown;
    const pendingVisible = entry.pendingVisible && !entry.failed;
    const text = entry.failed ? '' : pendingVisible ? '…' : entry.typing ? entry.answer.text.slice(0, entry.typed) : entry.answer.text;
    const label = entry.failed ? '응답 실패' : entry.pending ? '응답 대기' : type.label;
    return `<div class="c-bubble" style="--bubble-color:${type.color}"><div class="c-bubble-meta"><strong>${entry.question ? '나 → ' : ''}${entry.answer.from || 'YB'}</strong><span>${label}</span></div>${entry.question ? `<p class="c-question-text">${escapeHtml(entry.question)}</p>` : ''}${entry.failed ? '<p role="status">응답 실패 · <button type="button" data-retry-chat="' + escapeHtml(entry.clientRequestId) + '">다시 보내기</button></p>' : `<p class="c-answer-text">${escapeHtml(text)}${entry.typing || pendingVisible ? '<i class="c-caret"></i>' : ''}</p>`}</div>`;
  }

  function askQuestion(state, index) {
    const yb = data.ybs[state.activeYb];
    const question = yb.questions[index];
    if (question) sendQuestion(state, question);
  }

  function sendFreeQuestion(state) {
    if (state.chatPending) return;
    const input = state.windows.get('messenger').querySelector('[data-compose]');
    const question = input.value.trim();
    if (!question) return;
    input.value = '';
    sendQuestion(state, question);
  }

  async function sendQuestion(state, question, existing = null) {
    if (state.chatPending) return;
    const yb = data.ybs[state.activeYb];
    const entry = existing || { question, answer: { text: '', type: 'unknown', from: yb.id }, typed: 0, typing: false, pending: true, pendingVisible: false, clientRequestId: requestId() };
    if (!existing) state.histories[state.activeYb].push(entry);
    entry.failed = false;
    entry.pending = true;
    entry.pendingVisible = false;
    state.typing = entry;
    state.chatPending = true;
    state.chatWaitVisible = false;
    state.chatValidationError = false;
    const pendingTimer = setTimeout(() => { if (isLiveState(state) && state.chatPending) { entry.pendingVisible = true; state.chatWaitVisible = true; renderMessenger(state); } }, 300);
    renderMessenger(state);
    renderTaskbar(state);
    try {
      const result = await window.Api.sendChat(state.save.save_id, yb.id, question, entry.clientRequestId);
      if (!isLiveState(state)) return;
      clearTimeout(pendingTimer);
      entry.pendingVisible = false;
      entry.pending = false;
      state.chatWaitVisible = false;
      state.chatRows[state.activeYb].push(...result.messages);
      state.chatRows[state.activeYb].sort((a, b) => Number(a.message_id) - Number(b.message_id));
      state.histories[state.activeYb] = rowsToEntries(state.chatRows[state.activeYb], yb.id);
      const userRow = result.messages.find((row) => row.sender === 'user');
      const completed = state.histories[state.activeYb].find((item) => item.message_id === userRow?.message_id);
      if (completed) {
        completed.clientRequestId = entry.clientRequestId;
        completed.typing = true;
        completed.typed = 0;
      }
      if (completed) typeAnswer(state, completed);
    } catch (error) {
      if (!isLiveState(state)) return;
      clearTimeout(pendingTimer);
      state.typing = null;
      state.chatPending = false;
      state.chatWaitVisible = false;
      if (error.code === 'INVALID_REQUEST' || error.code === 'VALIDATION_ERROR') {
        state.histories[state.activeYb] = state.histories[state.activeYb].filter((item) => item !== entry);
        state.chatValidationError = true;
        state.windows.get('messenger').querySelector('[data-compose]').value = question;
        state.windows.get('messenger').querySelector('[data-chat-error]').textContent = error.message;
      } else if (['SERVICE_UNAVAILABLE', 'NETWORK_ERROR', 'TIMEOUT'].includes(error.code)) entry.failed = true;
      else state.histories[state.activeYb] = state.histories[state.activeYb].filter((item) => item !== entry);
      renderMessenger(state);
      if (!['INVALID_REQUEST', 'VALIDATION_ERROR', 'SERVICE_UNAVAILABLE', 'NETWORK_ERROR', 'TIMEOUT'].includes(error.code)) handleError(state, error);
    }
    renderTaskbar(state);
  }

  function requestId() { return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`; }

  function retryChat(state, id) {
    const index = state.histories.findIndex((items) => items.some((item) => item.clientRequestId === id));
    if (index < 0 || state.chatPending) return;
    const entry = state.histories[index].find((item) => item.clientRequestId === id);
    state.activeYb = index;
    sendQuestion(state, entry.question, entry);
  }

  function typeAnswer(state, entry) {
    if (entry.typed >= entry.answer.text.length) {
      entry.typing = false;
      state.typing = null;
      state.chatPending = false;
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

  function renderAccuse(state) {
    const windowEl = state.windows.get('accuse');
    const grid = windowEl.querySelector('[data-accuse-grid]');
    const result = windowEl.querySelector('[data-accuse-result]');
    const submit = windowEl.querySelector('[data-submit-accuse]');
    const savedAccusation = state.save.accusation;
    const accused = Boolean(savedAccusation);
    const accusedIndex = accused ? data.ybs.findIndex((yb) => yb.id === savedAccusation.character_id) : null;
    const picked = accused ? accusedIndex : state.suspect;
    grid.innerHTML = data.ybs.map((yb, index) => `<button type="button" class="c-suspect${picked === index ? ' is-picked' : ''}" data-suspect="${index}" ${accused ? 'disabled' : ''}><span class="c-suspect-dot" style="background:${yb.color}"></span><strong>${yb.id}</strong><small>${escapeHtml(yb.trait)}</small></button>`).join('');
    result.innerHTML = accused
      ? `<p class="c-accuse-done">${escapeHtml(savedAccusation.character_id)} 지목 완료</p><button type="button" class="c-submit" data-verdict-open>판정서 보기</button>`
      : '';
    submit.hidden = accused;
    submit.disabled = state.suspect === null;
  }

  function selectSuspect(state, index) {
    if (state.save.accusation || state.accusationPending) return;
    state.suspect = index;
    renderAccuse(state);
  }

  // 지목은 한 번만: 창 안에서 한 번 더 확인
  function submitAccuse(state) {
    if (state.suspect === null || state.save.accusation || state.accusationPending) return;
    const windowEl = state.windows.get('accuse');
    windowEl.querySelector('[data-submit-accuse]').hidden = true;
    windowEl.querySelector('[data-accuse-result]').innerHTML = `<div class="c-accuse-confirm"><p><b>${data.ybs[state.suspect].id}</b>를 결과 조작 AI로 지목합니다. 제출하면 바꿀 수 없습니다.</p><div><button type="button" data-accuse-cancel>취소</button><button type="button" class="c-submit" data-accuse-confirm>지목 확정</button></div></div>`;
    windowEl.querySelector('[data-accuse-confirm]').focus({ preventScroll: true });
  }

  async function confirmAccuse(state) {
    if (state.suspect === null || state.accusationPending) return;
    state.accusationPending = true;
    const button = state.root.querySelector('[data-accuse-confirm]');
    const original = button.textContent;
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    const waitTimer = setTimeout(() => { if (button.isConnected) button.textContent = '제출 중…'; }, 300);
    state.accusationRequestId ||= requestId();
    try {
      const result = await window.Api.submitAccusation(state.save.save_id, data.ybs[state.suspect].id, state.accusationRequestId);
      clearTimeout(waitTimer);
      if (!isLiveState(state)) return;
      state.save.accusation = result.accusation;
      state.accusationRequestId = null;
      renderAccuse(state);
      closeWindow(state, 'accuse');
      showVerdict(state);
    } catch (error) {
      clearTimeout(waitTimer);
      if (!isLiveState(state)) return;
      if (error.code === 'STATE_CONFLICT') {
        state.accusationRequestId = null;
        try { const fresh = await window.Api.getSave(state.save.save_id); state.save = { ...state.save, ...fresh }; state.windows.get('notebook').querySelector('[data-memo]').value = state.save.memo || ''; renderAccuse(state); if (!state.save.accusation) state.retryAccusationConfirm = true; renderTaskbar(state); renderLaunchers(state); showToast(state, '최신 상태로 맞췄습니다.'); }
        catch (syncError) { handleError(state, syncError); }
      } else {
        renderAccuse(state);
        if (['SERVICE_UNAVAILABLE', 'NETWORK_ERROR', 'TIMEOUT'].includes(error.code)) state.retryAccusationConfirm = true;
        if (!['SERVICE_UNAVAILABLE', 'NETWORK_ERROR', 'TIMEOUT'].includes(error.code)) { state.accusationRequestId = null; handleError(state, error); }
        else showToast(state, error.message);
      }
    } finally {
      clearTimeout(waitTimer);
      state.accusationPending = false;
      if (button.isConnected) { button.disabled = false; button.removeAttribute('aria-busy'); button.textContent = original; }
      if (state.retryAccusationConfirm && !state.save.accusation) { state.retryAccusationConfirm = false; submitAccuse(state); }
    }
  }

  function verdictPortrait(index) {
    const canvas = makePortrait(data.ybs[index], index);
    canvas.className = 'c-verdict-face';
    return canvas;
  }

  // 판정서: 종이가 올라오고 도장이 찍힌 뒤 가려진 진상이 드러남
  function showVerdict(state) {
    const accusation = state.save.accusation;
    if (!accusation || state.root.querySelector('[data-verdict]')) return;
    const { verdict } = accusation;
    const culprit = data.ybs.findIndex((yb) => yb.id === verdict.culprit_id);
    const pickedIndex = data.ybs.findIndex((yb) => yb.id === accusation.character_id);
    const picked = data.ybs[pickedIndex];
    const { hit, truth, evidence } = verdict;
    const labels = { found: '찾음', missed: '놓침', restricted: '권한 밖' };
    const layer = document.createElement('div');
    layer.className = `c-verdict${state.verdictShown || reduceMotion ? ' is-instant' : ''}`;
    layer.dataset.verdict = '';
    layer.innerHTML = `<article class="c-verdict-paper" role="dialog" aria-modal="true" aria-labelledby="c-verdict-title">
      <header><strong id="c-verdict-title">실험 판정서</strong><span>YB-LAB · Day ${currentDay(state)}</span></header>
      <div class="c-verdict-pick"><div data-verdict-pick></div><div><small>지목한 AI</small><b>${picked.id}</b><span>${escapeHtml(picked.trait)}</span></div></div>
      <div class="c-verdict-stamp ${hit ? 'is-hit' : 'is-miss'}" data-verdict-stamp>${hit ? '적중' : '불일치'}</div>
      <section><h3>결과를 조작한 AI</h3><div class="c-verdict-culprit"><div data-verdict-culprit></div><div><b>${escapeHtml(data.ybs[culprit].id)}</b><p class="c-verdict-redact" data-verdict-truth>${escapeHtml(truth)}</p></div></div></section>
      <section><h3>결정적 단서</h3><ul class="c-verdict-list">${evidence.map((item) => {
        const st = ['found', 'missed', 'restricted'].includes(item.status) ? item.status : 'missed';
        const style = st === 'restricted' ? 'locked' : st;
        return `<li class="is-${style}"><span>${labels[st]}</span>${escapeHtml(item.text)}</li>`;
      }).join('')}</ul></section>
      <footer><span>${escapeHtml(roleLabel(state.role))} · Day ${currentDay(state)}까지 조사</span><div class="c-verdict-actions"><button type="button" data-verdict-back>조사 화면으로</button><button type="button" class="c-submit" data-verdict-exit>정문으로 나가기</button></div></footer>
    </article>`;
    layer.querySelector('[data-verdict-pick]').append(verdictPortrait(pickedIndex));
    layer.querySelector('[data-verdict-culprit]').append(verdictPortrait(culprit));
    state.root.querySelector('[data-desktop]').append(layer);
    layer.querySelector('[data-verdict-back]').focus({ preventScroll: true });
    const stamp = layer.querySelector('[data-verdict-stamp]');
    const truthEl = layer.querySelector('[data-verdict-truth]');
    if (layer.classList.contains('is-instant')) {
      stamp.classList.add('is-on');
      truthEl.classList.add('is-open');
      return;
    }
    state.verdictShown = true;
    addTimer(state, () => {
      stamp.classList.add('is-on', 'is-landing');
      layer.querySelector('.c-verdict-paper').classList.add('is-stamped');
    }, 780);
    addTimer(state, () => truthEl.classList.add('is-open'), 1250);
  }

  function closeVerdict(state) {
    state.root.querySelector('[data-verdict]')?.remove();
  }

  // Day 전환: 확인 창 → Day 제목 화면 → 바탕화면. 되돌릴 수 없어 한 번 묻는다.
  function openDayDialog(state) {
    if (state.dayChanging || currentDay(state) >= data.maxDay) return;
    const day = currentDay(state);
    const layer = state.root.querySelector('[data-day-dialog]');
    state.advanceRequestId ||= requestId();
    layer.querySelector('[data-day-dialog-text]').textContent = `Day ${day} 조사를 마치고 Day ${day + 1}로 넘어갑니다. 넘어간 뒤에는 Day ${day}로 돌아올 수 없습니다.`;
    state.root.querySelector('[data-start-menu]').hidden = true;
    layer.hidden = false;
    layer.querySelector('[data-day-confirm]').focus({ preventScroll: true });
  }

  function closeDayDialog(state) {
    state.root.querySelector('[data-day-dialog]').hidden = true;
    state.root.querySelector('[data-day-next]')?.focus({ preventScroll: true });
    state.advanceRequestId = null;
  }

  async function advanceDay(state) {
    if (state.dayChanging || currentDay(state) >= data.maxDay) return;
    state.root.querySelector('[data-day-dialog]').hidden = true;
    state.dayChanging = true;
    const button = state.root.querySelector('[data-day-confirm]');
    const original = button.textContent;
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    const waitTimer = setTimeout(() => { if (button.isConnected) button.textContent = '진행 중…'; }, 300);
    renderTaskbar(state);
    try {
      const result = await window.Api.advanceDay(state.save.save_id, state.advanceRequestId);
      clearTimeout(waitTimer);
      if (!isLiveState(state)) return;
      state.save = { ...state.save, ...result.game_state };
      state.advanceRequestId = null;
      const day = currentDay(state);
      state.clockMinutes = DAY_START_MINUTES;
      const curtain = state.root.querySelector('[data-day-curtain]');
      curtain.querySelector('[data-day-curtain-title]').textContent = `Day ${day}`;
      curtain.querySelector('[data-day-curtain-text]').textContent = '새 실험이 시작되었습니다.';
      curtain.hidden = false;
      curtain.classList.remove('is-leaving');
      renderTaskbar(state);
      addTimer(state, () => curtain.classList.add('is-leaving'), reduceMotion ? 600 : 1500);
      addTimer(state, () => {
        curtain.hidden = true;
        curtain.classList.remove('is-leaving');
        state.dayChanging = false;
        if (day >= data.maxDay) state.unread.add('accuse');
        renderLaunchers(state);
        renderTaskbar(state);
        if (day >= data.maxDay) showToast(state, '마지막 Day입니다. 바탕화면에 지목이 열렸습니다.');
        else showToast(state, `Day ${day}이 시작되었습니다. YB들에게 새로 물어보세요.`);
      }, reduceMotion ? 650 : 1900);
    } catch (error) {
      clearTimeout(waitTimer);
      if (!isLiveState(state)) return;
      state.dayChanging = false;
      if (error.code === 'STATE_CONFLICT') {
        state.advanceRequestId = null;
        try { state.save = { ...state.save, ...(await window.Api.getSave(state.save.save_id)) }; state.windows.get('notebook').querySelector('[data-memo]').value = state.save.memo || ''; renderAccuse(state); renderTaskbar(state); showToast(state, '최신 상태로 맞췄습니다.'); }
        catch (syncError) { handleError(state, syncError); }
      } else {
        if (!['SERVICE_UNAVAILABLE', 'NETWORK_ERROR', 'TIMEOUT'].includes(error.code)) state.advanceRequestId = null;
        openDayDialog(state);
        if (!['SERVICE_UNAVAILABLE', 'NETWORK_ERROR', 'TIMEOUT'].includes(error.code)) handleError(state, error);
        else showToast(state, error.message);
      }
      renderTaskbar(state);
    } finally {
      clearTimeout(waitTimer);
      button.disabled = false; button.removeAttribute('aria-busy'); button.textContent = original;
    }
  }

  function showToast(state, message) {
    const toast = state.root.querySelector('[data-toast]');
    if (!toast) return;
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

  function unmountPlay() {
    if (instance) instance.unmount();
    if (entryState) finishEntry(entryState);
  }

  window.Play = window.Play || {};
  window.Play.c = { enter, mount, unmount: unmountPlay };
})();
