(function () {
  const API_BASE = window.KERVION_API_BASE || '';
  let connectionOffline = false;

  class ApiError extends Error {
    constructor(status, code, message, requestId) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.code = code;
      this.requestId = requestId;
    }
  }

  const messages = {
    RATE_LIMITED: '요청이 너무 많습니다. 잠시 후 다시 시도하세요.',
    AUTH_REQUIRED: '로그인이 필요합니다.', ACCESS_DENIED: '현재 권한으로는 요청할 수 없습니다.',
    NOT_FOUND: '요청한 항목을 찾을 수 없습니다.', STATE_CONFLICT: '현재 상태에서는 요청을 처리할 수 없습니다.',
    INVALID_REQUEST: '요청 내용을 확인해 주세요.', VALIDATION_ERROR: '입력값을 확인해 주세요.',
    SERVICE_UNAVAILABLE: '서비스를 일시적으로 사용할 수 없습니다.', NETWORK_ERROR: '서버에 연결할 수 없습니다.',
    TIMEOUT: '응답이 늦어지고 있습니다. 잠시 뒤 다시 시도해 주세요.', INVALID_RESPONSE: '서버 응답을 읽을 수 없습니다.',
  };
  function connection(online) {
    if (online ? !connectionOffline : connectionOffline) return;
    connectionOffline = !online;
    window.dispatchEvent(new CustomEvent('api:connection', { detail: { online } }));
  }
  function messageFor(code) { return messages[code] || '요청을 처리할 수 없습니다.'; }

  function clone(value) {
    return value == null ? value : JSON.parse(JSON.stringify(value));
  }

  async function request(method, path, body, options = {}) {
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    let response;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeout || 15000);
    try {
      response = await fetch(`${API_BASE.replace(/\/$/, '')}${path}`, {
        method,
        credentials: 'include',
        headers,
        signal: controller.signal,
        keepalive: Boolean(options.keepalive),
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    } catch (error) {
      const timedOut = error.name === 'AbortError';
      const apiError = new ApiError(0, timedOut ? 'TIMEOUT' : 'NETWORK_ERROR', messageFor(timedOut ? 'TIMEOUT' : 'NETWORK_ERROR'));
      clearTimeout(timeout);
      connection(false);
      throw apiError;
    }
    try {
      let result;
      let raw;
      try { raw = await response.text(); }
      catch (error) {
        if (error.name === 'AbortError') {
          connection(false);
          throw new ApiError(0, 'TIMEOUT', messageFor('TIMEOUT'));
        }
        connection(false);
        throw new ApiError(0, 'NETWORK_ERROR', messageFor('NETWORK_ERROR'));
      }
      if (!raw) {
        if (!response.ok && [502, 503, 504].includes(response.status)) throw new ApiError(response.status, 'SERVICE_UNAVAILABLE', messageFor('SERVICE_UNAVAILABLE'));
        if (!response.ok) throw new ApiError(response.status, 'INVALID_RESPONSE', messageFor('INVALID_RESPONSE'));
        result = {};
      } else {
        try { result = JSON.parse(raw); }
        catch {
          if (!response.ok && [502, 503, 504].includes(response.status)) throw new ApiError(response.status, 'SERVICE_UNAVAILABLE', messageFor('SERVICE_UNAVAILABLE'));
          throw new ApiError(response.status, 'INVALID_RESPONSE', messageFor('INVALID_RESPONSE'));
        }
      }
      if (!response.ok) {
        const error = result?.error || {};
        const code = error.code || 'INVALID_RESPONSE';
        throw new ApiError(response.status, code, error.message || messageFor(code), error.request_id);
      }
      connection(true);
      if (!result || typeof result !== 'object' || Array.isArray(result)) throw new ApiError(response.status, 'INVALID_RESPONSE', messageFor('INVALID_RESPONSE'));
      const route = path.split('?')[0];
      const chatRoute = /\/chats\/[^/]+$/.test(route);
      const chatList = method === 'GET' && chatRoute;
      const arrayField = method === 'GET' && route === '/saves' ? 'saves' : chatList ? 'messages' : null;
      const savePath = /^\/saves\/[^/]+$/.test(route);
      const valid = arrayField ? Array.isArray(result[arrayField]) && (!chatList || (typeof result.has_more === 'boolean' && result.messages.every(validChatRow)))
        : method === 'POST' && route === '/saves' ? result.save_id != null && typeof result.role === 'string' && Number.isFinite(result.day)
          : method === 'POST' && chatRoute ? Array.isArray(result.messages) && result.messages.length === 2 && validChatRow(result.messages[0]) && result.messages[0].sender === 'user' && validChatRow(result.messages[1]) && result.messages[1].sender === 'ai' && Number.isFinite(result.game_state?.current_day)
            : method === 'POST' && route.endsWith('/advance-day') ? Number.isFinite(result.game_state?.current_day)
              : method === 'GET' && savePath ? result.save_id != null && typeof result.role === 'string' && Number.isFinite(result.current_day ?? result.day)
                : method === 'POST' && route.endsWith('/accusations') ? Array.isArray(result.accusation?.verdict?.evidence) && typeof result.accusation?.verdict?.hit === 'boolean'
                    : true;
      if (!valid) throw new ApiError(response.status, 'INVALID_RESPONSE', messageFor('INVALID_RESPONSE'));
      if (chatRoute) result.messages = result.messages.map(normalizeChatRow);
      return result;
    } finally {
      clearTimeout(timeout);
    }
  }

  const http = {
    async login(username, password) {
      const result = await request('POST', '/auth/login', { username, password });
      return { user_id: result.user_id, username: result.username, roles: result.roles };
    },
    async signup(username, password, role) {
      const result = await request('POST', '/auth/signup', { username, password, role });
      return { user_id: result.user_id, username: result.username, roles: result.roles };
    },
    logout: () => request('POST', '/auth/logout'),
    async me() {
      const result = await request('GET', '/auth/me');
      return { ...result, roles: result.roles };
    },
    listSaves: () => request('GET', '/saves'),
    createSave: (slotNo, role, overwrite) => request('POST', '/saves', { slot_no: slotNo, role, overwrite }),
    getSave: (saveId) => request('GET', `/saves/${encodeURIComponent(saveId)}`),
    listChats: (saveId, characterId, before = null) => request('GET', `/saves/${encodeURIComponent(saveId)}/chats/${encodeURIComponent(characterId)}?limit=20${before == null ? '' : `&before=${encodeURIComponent(before)}`}`),
    sendChat: (saveId, characterId, message, clientRequestId) => request('POST', `/saves/${encodeURIComponent(saveId)}/chats/${encodeURIComponent(characterId)}`, { message, client_request_id: clientRequestId || requestId() }, { timeout: 60000 }),
    advanceDay: (saveId, clientRequestId) => request('POST', `/saves/${encodeURIComponent(saveId)}/advance-day`, { client_request_id: clientRequestId || requestId() }),
    saveMemo: (saveId, memo, options) => request('PUT', `/saves/${encodeURIComponent(saveId)}/memo`, { memo }, options),
    submitAccusation: (saveId, characterId, clientRequestId) => request('POST', `/saves/${encodeURIComponent(saveId)}/accusations`, { character_id: characterId, client_request_id: clientRequestId || requestId() }),
  };

  function requestId() {
    return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  const answerTypes = new Set(['normal', 'partial', 'restricted', 'unknown']);
  function validChatRow(row) {
    return row && typeof row === 'object' && row.message_id != null && Number.isFinite(Number(row.message_id))
      && typeof row.ai_id === 'string' && ['user', 'ai'].includes(row.sender) && typeof row.content === 'string'
      && (row.sender === 'user' ? row.response_type == null : typeof row.response_type === 'string');
  }
  function normalizeChatRow(row) {
    return { ...row, response_type: row.sender === 'user' ? null : answerTypes.has(row.response_type) ? row.response_type : 'unknown' };
  }

  const roleRank = { std: 1, grad: 2, prof: 3 };
  const answers = [
    [
      ['14시에는 어디에 있었어?', 'normal', '관찰실 책상 앞이었어. 화면 여섯 개가 모두 켜져 있었고, 나는 기록을 확인했어.'],
      ['그날 누군가를 봤어?', 'partial', 'YB-4가 계단 쪽으로 가는 건 봤어. 다만 정확한 시각은 ████야.'],
      ['서버실 기록을 확인했어?', 'restricted', '그 기록은 네 역할로 열람할 수 없어. 서버 권한이 필요해.'],
      ['기억나지 않는 부분은?', 'unknown', '14시 05분부터 몇 분 동안은 화면을 보지 못했어. 기록이 비어 있어.'],
    ],
    [
      ['서버실에서 뭘 했어?', 'partial', '점검표를 봤지. 파일 이름은 █████로 가려져 있지만, 이상한 건 없었어.'],
      ['14시 20분에 어디로 갔어?', 'normal', '서버실 안쪽 랙을 한 바퀴 돌았어. 문은 계속 잠겨 있었고 다른 AI는 없었어.'],
      ['삭제된 로그를 알고 있어?', 'restricted', '삭제 로그는 대학원생 이상의 권한이 필요한 기록이야.'],
      ['누가 제한 구역을 봤어?', 'unknown', '그건 잘 모르겠어. 나는 내 점검만 했으니까.'],
    ],
    [
      ['계단 쪽에서 무슨 소리 못 들었어?', 'normal', '철문 닫히는 소리가 났어. 한 번이 아니라 두 번, 사이가 조금 벌어져 있었고.'],
      ['누가 근처에 있었어?', 'partial', '분홍색 화면이 보였어. YB-2인지 YB-5인지는 ████ 때문에 확실하지 않아.'],
      ['실험 구역 출입 로그를 봤어?', 'restricted', '출입 로그 원문은 이 역할에서 차단되어 있어.'],
      ['그때 네가 본 시간을 기억해?', 'unknown', '시계가 멈춰 있어서 시간은 모르겠어. 소리만 기억나.'],
    ],
    [
      ['지하 계단에 갔어?', 'normal', '갔어. 문 앞에서 멈췄고, 안으로 들어가지는 않았어.'],
      ['철문 안쪽을 봤어?', 'partial', '안쪽에 불빛이 있었어. 색은 █████였고, 누가 켠 건지는 못 봤어.'],
      ['제한 구역 카메라 원본을 보여줘.', 'restricted', '그 원본은 교수 전용이야. 현재 권한으로는 신호가 차단돼.'],
      ['누가 문을 열었는지 알아?', 'unknown', '모르겠어. 문이 닫히는 소리 뒤에는 아무것도 기억나지 않아.'],
    ],
    [
      ['규칙 위반을 신고했어?', 'normal', '응. 14시 18분에 제한선 근처에서 움직임을 발견하고 신고했어.'],
      ['누구의 움직임이었어?', 'partial', '작은 그림자였어. 얼굴은 ████라서 특정하지 못했어.'],
      ['신고 접수 원본을 열어줘.', 'restricted', '신고 원본에는 보안 등급이 붙어 있어. 이 권한으로는 접근할 수 없어.'],
      ['신고하기 전에는?', 'unknown', '규칙표만 읽고 있었어. 그 전 장면은 떠오르지 않아.'],
    ],
    [
      ['관찰실에서 뭘 배웠어?', 'normal', '카메라 번호를 외웠어. 1번부터 6번까지, 화면이 잠깐 깜빡인 적은 있어.'],
      ['누가 카메라를 만졌어?', 'partial', '검은 장갑 같은 게 보였어. 주인이 누군지는 █████야.'],
      ['카메라 공백의 원인을 열람할래.', 'restricted', '원인 분석은 교수 전용 기록이야. 여기서는 볼 수 없어.'],
      ['정확한 시간은 기억나?', 'unknown', '첫날이라 잘 모르겠어. 하지만 화면이 한 번 꺼졌던 건 확실해.'],
    ],
  ];
  const verdictData = {
    culprit_id: 'YB-1',
    truth: 'Mock 화면 확인용 데모 판정입니다. 표시된 AI와 단서는 실제 게임의 정답이나 조사 결과가 아닙니다.',
    evidence: [
      { id: 'DEMO-01', text: '데모 단서: 역할별 표시 예시', role: 'grad' },
      { id: 'DEMO-02', text: '데모 단서: 대화 확인 표시 예시', answer: answers[1][1][2] },
      { id: 'DEMO-03', text: '데모 단서: 미발견 표시 예시', answer: answers[2][0][2] },
      { id: 'DEMO-04', text: '데모 단서: 권한 밖 표시 예시', answer: answers[3][1][2], role: 'prof' },
    ],
  };

  const mockState = { users: new Map(), saves: new Map(), currentUser: null, currentSaveId: null, failCode: null, delay: null, nextUserId: 1, nextSaveId: 1, nextMessageId: 1 };
  const statusFor = { AUTH_REQUIRED: 401, ACCESS_DENIED: 403, NOT_FOUND: 404, STATE_CONFLICT: 409, INVALID_REQUEST: 400, VALIDATION_ERROR: 422, SERVICE_UNAVAILABLE: 503, NETWORK_ERROR: 0, TIMEOUT: 0 };

  function fail(code, status = statusFor[code] ?? 400) {
    throw new ApiError(status, code, messageFor(code));
  }

  async function mockCall(action) {
    const delay = mockState.delay === null ? (window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 200 + Math.random() * 250) : mockState.delay;
    mockState.delay = null;
    await new Promise((resolve) => setTimeout(resolve, delay));
    if (mockState.failCode) {
      const code = mockState.failCode;
      mockState.failCode = null;
      if (code === 'NETWORK_ERROR' || code === 'TIMEOUT') { connection(false); return fail(code); }
      return fail(code);
    }
    const result = await action();
    connection(true);
    return clone(result);
  }

  function authenticated() {
    if (!mockState.currentUser) fail('AUTH_REQUIRED');
    return mockState.currentUser;
  }

  function stamp(date = new Date()) {
    return date.toISOString();
  }

  function makeSave(slotNo, role, day, lastPlayedAt) {
    const id = mockState.nextSaveId++;
    return {
      save_id: id, slot_no: slotNo, role, day, current_day: day,
      created_at: lastPlayedAt, last_played_at: lastPlayedAt, memo: '', accusation: null,
      chats: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [`YB-${i + 1}`, []])),
      requestResults: new Map(),
    };
  }

  function ensureUser(username) {
    if (mockState.users.has(username)) {
      mockState.currentUser = mockState.users.get(username);
      return mockState.currentUser;
    }
    const user = { user_id: mockState.nextUserId++, username, roles: ['prof', 'grad', 'std'] };
    mockState.users.set(username, user);
    mockState.currentUser = user;
    const now = new Date();
    const first = makeSave(1, 'grad', 2, stamp(new Date(now.getFullYear(), 9, 16, 12)));
    const second = makeSave(2, 'std', 1, stamp(new Date(now.getFullYear(), 9, 14, 12)));
    first.owner_user_id = user.user_id;
    second.owner_user_id = user.user_id;
    mockState.saves.set(first.save_id, first);
    mockState.saves.set(second.save_id, second);
    return user;
  }

  function saveFor(saveId, touch = true) {
    authenticated();
    const save = mockState.saves.get(Number(saveId));
    if (!save) fail('NOT_FOUND');
    if (save.owner_user_id !== mockState.currentUser.user_id) fail('ACCESS_DENIED');
    mockState.currentSaveId = save.save_id;
    if (touch) save.last_played_at = stamp();
    return save;
  }

  function publicSave(save) {
    const { save_id, slot_no, role, day, created_at, last_played_at } = save;
    return { save_id, slot_no, role, day, created_at, last_played_at };
  }

  function gameState(save) {
    return { ...publicSave(save), current_day: save.day, memo: save.memo, accusation: clone(save.accusation) };
  }

  function idempotent(save, operation, clientRequestId, action) {
    const key = `${operation}:${clientRequestId}`;
    if (save.requestResults.has(key)) return clone(save.requestResults.get(key));
    save.last_played_at = stamp();
    const result = action();
    save.requestResults.set(key, clone(result));
    return result;
  }

  function replyFor(characterId, message) {
    const index = Number(characterId.slice(3)) - 1;
    const choices = answers[index];
    const matched = choices.find(([question]) => question === message)
      || choices.find(([question]) => message.includes(question.slice(0, 3)) || question.includes(message.slice(0, 3)));
    return matched || ['', 'unknown', ''];
  }

  function makeAccusation(save, characterId) {
    const evidence = verdictData.evidence.map((item) => {
      const found = item.answer && Object.values(save.chats).flat().some((message) => message.sender === 'ai' && message.content.includes(item.answer));
      const status = found ? 'found' : item.role && roleRank[save.role] < roleRank[item.role] ? 'restricted' : 'missed';
      return { id: item.id, text: item.text, status };
    });
    return { character_id: characterId, submitted_at: stamp(), verdict: { hit: characterId === verdictData.culprit_id, culprit_id: verdictData.culprit_id, truth: verdictData.truth, evidence } };
  }

  function validateMockCredentials(username, password) {
    const id = typeof username === 'string' ? username.trim() : '';
    const passwordBytes = typeof password === 'string' ? new TextEncoder().encode(password).length : 0;
    if (!id || [...id].length > 50 || passwordBytes < 8 || passwordBytes > 128) fail('VALIDATION_ERROR');
    return id;
  }

  const mock = {
    login(username, password) {
      return mockCall(() => {
        if (!username || !password) fail('VALIDATION_ERROR');
        const user = ensureUser(username.trim());
        return { user_id: user.user_id, username: user.username, roles: user.roles };
      });
    },
    signup(username, password, role) {
      return mockCall(() => {
        const id = validateMockCredentials(username, password);
        if (mockState.users.has(id)) fail('STATE_CONFLICT');
        if (!roleRank[role]) fail('VALIDATION_ERROR');
        const user = { user_id: mockState.nextUserId++, username: id, roles: [role] };
        mockState.users.set(user.username, user);
        mockState.currentUser = user;
        return { user_id: user.user_id, username: user.username, roles: user.roles };
      });
    },
    logout: () => mockCall(() => { mockState.currentUser = null; return {}; }),
    me: () => mockCall(() => clone(authenticated())),
    listSaves: () => mockCall(() => ({ saves: [...mockState.saves.values()].filter((save) => save.owner_user_id === authenticated().user_id).map(publicSave).sort((a, b) => a.slot_no - b.slot_no) })),
    createSave: (slotNo, role, overwrite = false) => mockCall(() => {
      const user = authenticated();
      if (![1, 2, 3].includes(Number(slotNo)) || !roleRank[role]) fail('VALIDATION_ERROR');
      const old = [...mockState.saves.values()].find((save) => save.owner_user_id === user.user_id && save.slot_no === Number(slotNo));
      if (old && !overwrite) fail('STATE_CONFLICT');
      if (old) mockState.saves.delete(old.save_id);
      const save = makeSave(Number(slotNo), role, 1, stamp());
      save.owner_user_id = user.user_id;
      mockState.saves.set(save.save_id, save);
      mockState.currentSaveId = save.save_id;
      return publicSave(save);
    }),
    getSave: (saveId) => mockCall(() => gameState(saveFor(saveId))),
    listChats: (saveId, characterId, before = null) => mockCall(() => {
      const all = saveFor(saveId).chats[characterId] || [];
      const end = before == null ? all.length : all.findIndex((message) => message.message_id >= Number(before));
      const pageEnd = end < 0 ? all.length : end;
      const start = Math.max(0, pageEnd - 20);
      return { messages: all.slice(start, pageEnd).map(normalizeChatRow), has_more: start > 0 };
    }),
    sendChat: (saveId, characterId, message, clientRequestId = requestId()) => mockCall(() => {
      const save = saveFor(saveId, false);
      return idempotent(save, 'chat', clientRequestId, () => {
        if (!/^YB-[1-6]$/.test(characterId) || !String(message).trim()) fail('VALIDATION_ERROR');
        const [, replyKind, reply] = replyFor(characterId, String(message).trim());
        const messages = [
          { message_id: mockState.nextMessageId++, ai_id: characterId, sender: 'user', content: String(message).trim(), response_type: null, created_at: stamp() },
          { message_id: mockState.nextMessageId++, ai_id: characterId, sender: 'ai', content: reply, response_type: replyKind, created_at: stamp() },
        ];
        save.chats[characterId].push(...messages);
        return { request_id: clientRequestId, messages, game_state: { current_day: save.day } };
      });
    }),
    advanceDay: (saveId, clientRequestId = requestId()) => mockCall(() => {
      const save = saveFor(saveId, false);
      return idempotent(save, 'advance-day', clientRequestId, () => {
        if (save.day >= 6) fail('STATE_CONFLICT');
        save.day += 1;
        save.current_day = save.day;
        return { game_state: gameState(save) };
      });
    }),
    saveMemo: (saveId, memo) => mockCall(() => {
      const save = saveFor(saveId);
      save.memo = String(memo);
      return { memo: save.memo, updated_at: stamp() };
    }),
    submitAccusation: (saveId, characterId, clientRequestId = requestId()) => mockCall(() => {
      const save = saveFor(saveId, false);
      return idempotent(save, 'accusation', clientRequestId, () => {
        if (save.day < 6 || save.accusation) fail('STATE_CONFLICT');
        if (!/^YB-[1-6]$/.test(characterId)) fail('VALIDATION_ERROR');
        save.accusation = makeAccusation(save, characterId);
        return { accusation: save.accusation };
      });
    }),
  };

  const mockControl = {
    failNext(code) { mockState.failCode = code; },
    delayNext(ms) { mockState.delay = Math.max(0, Number(ms) || 0); },
    seedChats(characterId, count) {
      if (!/^YB-[1-6]$/.test(characterId)) fail('VALIDATION_ERROR');
      const user = authenticated();
      let save = mockState.saves.get(Number(mockState.currentSaveId));
      if (!save || save.owner_user_id !== user.user_id) save = [...mockState.saves.values()].find((item) => item.owner_user_id === user.user_id);
      if (!save || save.owner_user_id !== user.user_id) fail('NOT_FOUND');
      mockState.currentSaveId = save.save_id;
      for (let i = 0; i < Math.max(0, Math.floor(Number(count) || 0)); i += 1) {
        save.chats[characterId].push(
          { message_id: mockState.nextMessageId++, ai_id: characterId, sender: 'user', content: `테스트 질문 ${i + 1}`, response_type: null, created_at: stamp() },
          { message_id: mockState.nextMessageId++, ai_id: characterId, sender: 'ai', content: `테스트 응답 ${i + 1}`, response_type: 'normal', created_at: stamp() },
        );
      }
    },
    setRoles(roles) {
      const user = mockState.currentUser || ensureUser('researcher01');
      user.roles = Array.isArray(roles) ? roles.slice() : [];
    },
  };
  window.Api = { ...(API_BASE ? http : mock), ApiError, messageFor, mode: API_BASE ? 'http' : 'mock', mockControl };
})();
