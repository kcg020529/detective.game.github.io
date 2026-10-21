const loadingScreen = document.querySelector('#loading-screen');
const gameScreen = document.querySelector('#game-screen');
const startButton = document.querySelector('#start-button');
const restartButton = document.querySelector('.restart');
const logList = document.querySelector('#log');
const percentText = document.querySelector('#percent');
const progressEl = document.querySelector('#progress');
const dayText = document.querySelector('#day-text');
const canvas = document.querySelector('#lab');
const ctx = canvas.getContext('2d');

const playParams = new URLSearchParams(window.location.search);
const requestedPlay = 'c';
const skipToPlay = playParams.get('skip') === '1';
let mountedPlay = null;

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---------- 픽셀 장면 ---------- */

// 168 x 194 픽셀 그림을 S배로 키워서 그림 (canvas는 1344 x 1552)
// 건물 장면(160 x 120) 둘레로 여백을 둠: 왼쪽 OX, 위쪽 OY(밤하늘), 아래쪽 OB(땅)
// 여백은 CSS 마스크로 왼쪽 글 영역과 게임 창 바닥 속으로 사라짐
// GW:GH는 오른쪽 영역 비율(약 0.87)에 맞춰서 잘리는 부분이 거의 없게 함
const S = 8;
const GW = 168;
const GH = 194;
const OX = 6;
const OB = 24;
const OY = GH - 120 - OB;

const C = {
  sky: '#121a24',
  star: '#c3cec9',
  grass: '#3e5b48',
  soil: '#2b2622',
  rock: '#3a332d',
  shell: '#4a5560',
  slab: '#3a434c',
  dark: '#0b1016',
  wall: '#b9c0b4',
  wallShade: '#a7afa3',
  floor: '#7d857b',
  tile: '#737b71',
  desk: '#6b5a48',
  deskTop: '#86725c',
  screen: '#6fc3b8',
  screenDim: '#3d7e77',
  glass: '#8fb3b8',
  rack: '#2d3740',
  rackEdge: '#3d4954',
  ledGreen: '#5fd68a',
  ledAmber: '#f0a63a',
  crate: '#9a7550',
  crateEdge: '#7a5a3c',
  pillar: '#8d978c',
  pillarShade: '#7a8479',
  leaf: '#4f7a55',
  pot: '#8a5a3c',
  bot: '#e6ede4',
  botEye: '#1a2129',
  amber: '#f0a63a',
  caution: '#d9a43a',
  vault: '#3a434c',
  vaultEdge: '#56616b',
  label: '#2b353b',
  labelDim: '#5f6d76',
};

function px(x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(x * S, y * S, w * S, h * S);
}

function text(str, x, y, color, size = 3, weight = 500) {
  ctx.fillStyle = color;
  ctx.font = `${weight} ${size * S}px 'Pretendard Variable', Pretendard, sans-serif`;
  ctx.textBaseline = 'top';
  ctx.fillText(str, x * S, y * S);
}

// 방 위치 (픽셀 좌표). lightAt: 불이 켜지기 시작한 시각
const rooms = {
  observe: { x: 12, y: 20, w: 66, h: 26, label: '관찰실', lightAt: null },
  server: { x: 80, y: 20, w: 68, h: 26, label: '서버실', lightAt: null },
  arena: { x: 12, y: 50, w: 136, h: 30, label: '실험 구역', lightAt: null },
  restricted: { x: 12, y: 86, w: 136, h: 24, label: '제한 구역', state: 'idle' },
};

// 별: 하늘 전체에 흩뿌림 (canvas 좌표, 건물에 가려지는 별은 그대로 가려짐)
const stars = Array.from({ length: 46 }, (_, i) => ({
  x: (i * 37 + 11) % GW,
  y: (i * 23 + 5) % (OY + 76),
  phase: i * 0.9,
}));

const rocks = Array.from({ length: 40 }, (_, i) => ({
  x: (i * 29 + 5) % (GW - OX) - OX,
  y: 84 + ((i * 17) % (34 + OB)),
}));

const leds = [];
for (let r = 0; r < 5; r++) {
  for (let k = 0; k < 4; k++) {
    leds.push({
      x: 85 + r * 12 + (k % 2) * 3,
      y: 29 + k * 4,
      color: (r + k) % 3 === 0 ? C.ledAmber : C.ledGreen,
      period: 1400 + ((r * 7 + k * 5) % 9) * 260,
      phase: (r * 3 + k) * 400,
    });
  }
}

// 실험 구역 소품: 로봇이 뒤로 지나가면 가려짐 (술래잡기)
const props = [
  { type: 'crate', x: 32, w: 9, h: 8 },
  { type: 'crate', x: 41, w: 7, h: 6 },
  { type: 'pillar', x: 70, w: 6, h: 26 },
  { type: 'crate', x: 104, w: 9, h: 9 },
  { type: 'plant', x: 134, w: 7, h: 11 },
];

const botColors = ['#7fb3d5', '#e59a8c', '#9ccf8e', '#d8b4e2', '#e8cf7a', '#8fd0c8'];
const bots = botColors.map((color, i) => ({
  name: `YB-${i + 1}`,
  color,
  x: 18 + i * 21,
  target: 18 + i * 21,
  wait: 600 + i * 300,
  shownAt: null,
}));

const ARENA_FLOOR = 78; // 실험 구역 바닥 y
const BOT_W = 5;
const BOT_H = 7;

// 숨은 기능: 빨간 안테나를 누르면 제한 구역이 열리고 디스코볼 아래에서 캐릭터가 어슬렁거림
// (YB 로봇은 실험 구역에 그대로 있음). 그림 1칸을 canvas 3픽셀로 그림 (장면 1칸은 S = 8픽셀)
const CHAR_SCALE = 3;
const CHAR_START = [50, 70, 90]; // 제한 구역 안 시작 자리 (캐비닛 오른쪽)
const chars = ['chiigawa', 'hachigare', 'gugagi'].map((name, i) => {
  const img = new Image();
  img.src = `./assets/${name}.png`;
  return { img, x: CHAR_START[i], target: CHAR_START[i], wait: 800 + i * 500, facing: 1, seed: i * 2.1, hopAt: -Infinity, nextHop: 0 };
});
let secretOpen = false; // 안테나로 연 제한 구역 파티
let party = 0; // 0~1, 안테나로 연 제한 구역에 캐릭터가 서서히 나타나고 사라짐
// 디스코: 제한 구역이 열려 있을 때 맨 왼쪽 캐비닛의 빨간 봉인 테이프를 누르면 켜고 끔
let discoOn = false;
let discoDrop = 0; // 0이면 공이 천장 속, 1이면 다 내려옴
let discoGlow = 0; // 빛줄기·반짝이 밝기 (공이 거의 다 내려온 뒤 켜짐)
let antennaFlashAt = -Infinity;

// 앞서 맞춘 불 켜짐 곡선: 한 번 머뭇거린 뒤 천천히 밝아짐 (1.6초)
function powerCurve(t) {
  if (t <= 0) return 0;
  if (reduceMotion || t >= 1) return 1;
  if (t < 0.2) return (t / 0.2) * 0.35;
  if (t < 0.32) return 0.35 - ((t - 0.2) / 0.12) * 0.17;
  const k = (t - 0.32) / 0.68;
  return 0.18 + (1 - Math.pow(1 - k, 3)) * 0.82;
}

function lightLevel(room, now) {
  return room.lightAt === null ? 0 : powerCurve((now - room.lightAt) / 1600);
}

function darken(room, level, max = 0.9) {
  const alpha = max * (1 - level);
  if (alpha <= 0.001) return;
  ctx.globalAlpha = alpha;
  px(room.x, room.y, room.w, room.h, C.dark);
  ctx.globalAlpha = 1;
}

function drawSky(now) {
  px(0, 0, GW, OY + 80, C.sky);
  for (const s of stars) {
    const twinkle = reduceMotion ? 0.7 : 0.45 + 0.4 * Math.sin(now / 1800 + s.phase);
    ctx.globalAlpha = twinkle;
    px(s.x, s.y, 1, 1, C.star);
  }
  ctx.globalAlpha = 1;
}

function drawGround() {
  px(-OX, 80, GW, 40 + OB, C.soil);
  px(-OX, 80, GW, 2, C.grass);
  for (const r of rocks) px(r.x, r.y, 2, 1, C.rock);
}

function drawShell(now) {
  px(8, 16, 144, 4, C.slab); // 지붕
  px(10, 20, 2, 94, C.shell); // 왼쪽 벽
  px(148, 20, 2, 94, C.shell); // 오른쪽 벽
  px(78, 20, 2, 26, C.shell); // 3층 칸막이
  px(10, 46, 140, 4, C.slab); // 3층 바닥
  px(10, 80, 140, 6, C.slab); // 지상 바닥
  px(10, 110, 140, 4, C.slab); // 지하 바닥

  // 지붕 위 실외기와 안테나
  px(26, 11, 14, 5, C.shell);
  px(28, 12, 10, 1, C.slab);
  px(28, 14, 10, 1, C.slab);
  px(130, 5, 1, 11, C.shell);
  px(127, 8, 7, 1, C.shell);
  // 평소엔 천천히 깜빡이고, 누르면 잠깐 밝게 빛남
  const sinceClick = now - antennaFlashAt;
  const flash = sinceClick < 700 ? 1 - sinceClick / 700 : 0;
  const idle = reduceMotion ? 0.8 : 0.35 + 0.5 * (0.5 + 0.5 * Math.sin(now / 900));
  if (flash > 0) {
    ctx.globalAlpha = flash * 0.35;
    px(127, 1, 7, 6, '#ff8a6e');
  }
  ctx.globalAlpha = Math.max(idle, flash);
  px(129, 3, 3, 2, '#d9584a');
  ctx.globalAlpha = 1;
}

function drawRoomBase(room) {
  px(room.x, room.y, room.w, room.h, C.wall);
  px(room.x, room.y + room.h - 2, room.w, 2, C.floor);
  // 벽 아래쪽 걸레받이
  px(room.x, room.y + room.h - 3, room.w, 1, C.wallShade);
}

function drawObserve(now) {
  const r = rooms.observe;
  drawRoomBase(r);
  // 실험 구역을 내려다보는 관찰창
  px(52, 24, 22, 12, C.slab);
  px(53, 25, 20, 10, C.glass);
  px(55, 26, 3, 1, '#b8d3d6');
  // 책상과 모니터 세 대
  px(16, 38, 32, 2, C.deskTop);
  px(18, 40, 2, 4, C.desk);
  px(44, 40, 2, 4, C.desk);
  for (let i = 0; i < 3; i++) {
    const mx = 18 + i * 10;
    px(mx, 31, 8, 6, C.slab);
    const glow = reduceMotion ? 1 : 0.75 + 0.25 * Math.sin(now / 1300 + i * 2);
    ctx.globalAlpha = glow;
    px(mx + 1, 32, 6, 4, i === 1 ? C.screenDim : C.screen);
    ctx.globalAlpha = 1;
    px(mx + 3, 37, 2, 1, C.slab);
  }
  // 의자
  px(30, 41, 5, 1, C.slab);
  px(32, 42, 1, 2, C.slab);
}

function drawServer(now) {
  const r = rooms.server;
  drawRoomBase(r);
  for (let i = 0; i < 5; i++) {
    const rx = 84 + i * 12;
    px(rx, 26, 9, 18, C.rack);
    px(rx, 26, 9, 1, C.rackEdge);
    for (let k = 0; k < 4; k++) px(rx + 1, 28 + k * 4, 7, 1, C.rackEdge);
  }
  for (const led of leds) {
    const on = reduceMotion || ((now + led.phase) % led.period) < led.period * 0.6;
    if (on) px(led.x, led.y, 1, 1, led.color);
  }
  // 바닥 케이블
  px(84, 44, 58, 1, C.rack);
}

function drawArenaBase() {
  const r = rooms.arena;
  drawRoomBase(r);
  // 바닥 타일
  for (let x = r.x; x < r.x + r.w; x += 4) px(x, ARENA_FLOOR, 2, 1, C.tile);
  // 벽에 붙은 실험 번호판
  px(118, 54, 18, 7, C.slab);
  px(119, 55, 16, 5, '#cfd6cc');
}

function drawProps() {
  for (const p of props) {
    const top = ARENA_FLOOR - p.h;
    if (p.type === 'crate') {
      px(p.x, top, p.w, p.h, C.crate);
      px(p.x, top, p.w, 1, C.crateEdge);
      px(p.x, top, 1, p.h, C.crateEdge);
      px(p.x + p.w - 1, top, 1, p.h, C.crateEdge);
      px(p.x + 1, top + Math.floor(p.h / 2), p.w - 2, 1, C.crateEdge);
    } else if (p.type === 'pillar') {
      px(p.x, top, p.w, p.h, C.pillar);
      px(p.x + p.w - 2, top, 2, p.h, C.pillarShade);
    } else if (p.type === 'plant') {
      px(p.x + 1, ARENA_FLOOR - 4, 5, 4, C.pot);
      px(p.x, top, 7, 4, C.leaf);
      px(p.x + 1, top - 2, 2, 2, C.leaf);
      px(p.x + 4, top - 1, 2, 3, C.leaf);
      px(p.x + 3, top + 4, 1, 3, C.leaf);
    }
  }
}

function drawBot(bot, now) {
  const x = Math.round(bot.x);
  const y = ARENA_FLOOR - BOT_H;
  const appear = Math.min((now - bot.shownAt) / 500, 1);
  ctx.globalAlpha = reduceMotion ? 1 : appear;
  const walking = !reduceMotion && Math.abs(bot.target - bot.x) > 0.5;
  const step = walking && Math.floor(now / 220) % 2 === 0;

  px(x + 2, y, 1, 1, C.amber); // 안테나
  px(x + 1, y + 1, 3, 1, C.bot);
  px(x, y + 2, 5, 2, C.bot);
  px(x + 1, y + 2, 1, 1, C.botEye);
  px(x + 3, y + 2, 1, 1, C.botEye);
  px(x + 1, y + 4, 3, 2, bot.color);
  if (step) {
    px(x + 2, y + 6, 1, 1, C.botEye);
  } else {
    px(x + 1, y + 6, 1, 1, C.botEye);
    px(x + 3, y + 6, 1, 1, C.botEye);
  }
  ctx.globalAlpha = 1;
}

// 로봇과 캐릭터가 함께 쓰는 걷기: 목표 지점까지 걷고, 잠깐 쉬고, 새 목표를 고름
function updateWalker(bot, dt, width, r = rooms.arena) {
  if (reduceMotion) return;
  if (Math.abs(bot.target - bot.x) <= 0.5) {
    bot.wait -= dt;
    if (bot.wait <= 0) {
      bot.target = r.x + 3 + Math.random() * (r.w - width - 6);
      bot.wait = 900 + Math.random() * 2400;
    }
    return;
  }
  const dir = Math.sign(bot.target - bot.x);
  bot.x += dir * Math.min(0.012 * dt, Math.abs(bot.target - bot.x));
}

function charWidth(ch) {
  return ch.img.naturalWidth ? (ch.img.naturalWidth * CHAR_SCALE) / S : 4;
}

// 그림 한 장을 몸통과 발(아래 FEET줄)로 잘라서 따로 움직임
// 발 조각은 몸통 마지막 줄을 한 줄 겹쳐 가져가서, 몸이 1칸 떠도 틈이 생기지 않음
const FEET = 4;

// 지금 자세: 각 발을 든 높이, 몸이 뜬 높이, 몸이 기운 방향 (모두 그림 칸 단위)
function charPose(ch, now) {
  const pose = { liftL: 0, liftR: 0, bob: 0, sway: 0 };
  if (reduceMotion) return pose;
  const walking = Math.abs(ch.target - ch.x) > 0.5;
  if (walking) {
    ch.facing = Math.sign(ch.target - ch.x) || ch.facing;
    // 왼발 듦 → 모음 → 오른발 듦 → 모음
    const step = Math.floor(now / 150) % 4;
    if (step === 0) Object.assign(pose, { liftL: 2, bob: 1, sway: -1 });
    if (step === 2) Object.assign(pose, { liftR: 2, bob: 1, sway: 1 });
    return pose;
  }
  // 쉬는 중: 숨 쉬듯 오르내리고, 가끔 제자리에서 폴짝
  if (Math.sin(now / 520 + ch.seed) > 0.6) pose.bob = 1;
  if (now >= ch.nextHop) {
    ch.hopAt = now;
    ch.nextHop = now + 2600 + Math.random() * 4200;
  }
  const t = (now - ch.hopAt) / 420;
  if (t >= 0 && t < 1) {
    const h = Math.round(Math.sin(t * Math.PI) * 4);
    pose.bob += h;
    pose.liftL += h;
    pose.liftR += h;
  }
  return pose;
}

function drawChar(ch, now, alpha, floorY) {
  const img = ch.img;
  if (!img.complete || !img.naturalWidth) return;
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  const k = CHAR_SCALE;
  const half = Math.floor(w / 2);
  const { liftL, liftR, bob, sway } = charPose(ch, now);

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.imageSmoothingEnabled = false;
  // 발바닥 가운데를 기준점으로, 가는 방향으로 좌우를 뒤집음
  const cx = Math.round((ch.x * S + (w * k) / 2) / k) * k;
  ctx.translate(cx, floorY * S);
  ctx.scale(ch.facing, 1);
  const left = -Math.floor(w / 2);
  // 발 (왼쪽 절반, 오른쪽 절반)
  ctx.drawImage(img, 0, h - FEET - 1, half, FEET + 1, left * k, (-(FEET + 1) - liftL) * k, half * k, (FEET + 1) * k);
  ctx.drawImage(img, half, h - FEET - 1, w - half, FEET + 1, (left + half) * k, (-(FEET + 1) - liftR) * k, (w - half) * k, (FEET + 1) * k);
  // 몸통
  ctx.drawImage(img, 0, 0, w, h - FEET, (left + sway) * k, (-h - bob) * k, w * k, (h - FEET) * k);
  ctx.restore();
}

/* ---------- 역할 선택 2안: 역할에 따라 볼 수 있는 구역만 열림 ---------- */
// 화면 연출용 대응표. 실제 권한 규칙(역할 × 문서 등급)은 서버 정책이 정하며 이 표와 무관함
const ROLE_ACCESS = {
  prof: ['arena', 'observe', 'server', 'restricted'],
  grad: ['arena', 'observe', 'server'],
  std: ['arena', 'observe'],
};
let sceneRole = null; // 역할 선택 화면에서 고른 역할 (없으면 null)
const veil = { observe: 0, server: 0, arena: 0 }; // 1이면 잠겨서 어두움
let restrictedOpen = 0; // 1이면 제한 구역이 열림

function updateAccess(dt) {
  const k = reduceMotion ? 1 : Math.min(dt / 160, 1);
  const open = sceneRole ? ROLE_ACCESS[sceneRole] : null;
  for (const key of Object.keys(veil)) {
    const target = open && !open.includes(key) ? 1 : 0;
    veil[key] += (target - veil[key]) * k;
  }
  const openTarget = (open && open.includes('restricted')) || secretOpen ? 1 : 0;
  restrictedOpen += (openTarget - restrictedOpen) * k;
  party += ((secretOpen ? 1 : 0) - party) * (reduceMotion ? 1 : Math.min(dt / 300, 1));
  // 거의 다 왔으면 딱 맞춤 (자물쇠가 희미하게 남지 않게)
  for (const key of Object.keys(veil)) if (Math.abs(veil[key] - Math.round(veil[key])) < 0.01) veil[key] = Math.round(veil[key]);
  if (Math.abs(restrictedOpen - openTarget) < 0.01) restrictedOpen = openTarget;
  if (Math.abs(party - (secretOpen ? 1 : 0)) < 0.01) party = secretOpen ? 1 : 0;

  // 방이 닫히면 디스코도 꺼짐. 공은 일정한 속도로 내려오고(0.9초) 올라감
  if (restrictedOpen < 0.5) discoOn = false;
  const dropTarget = discoOn ? 1 : 0;
  discoDrop = reduceMotion ? dropTarget
    : Math.max(0, Math.min(1, discoDrop + Math.sign(dropTarget - discoDrop) * (dt / 900)));
  // 내려올 땐 거의 다 내려온 뒤 켜지고, 올라갈 땐 먼저 꺼짐
  discoGlow = discoOn ? Math.max(0, (discoDrop - 0.8) / 0.2) : Math.max(0, discoGlow - dt / 250);
  if (reduceMotion) discoGlow = discoOn ? 1 : 0;
}

/* ---------- 숨은 기능: 제한 구역 디스코 ---------- */

const DISCO_X = 80; // 디스코볼이 매달린 x (제한 구역 가운데)
const discoColors = ['#ff6fae', '#6fd3ff', '#ffe36f', '#8dff8a', '#c79bff'];
const DISCO_Y = 94; // 디스코볼 가운데 y
const DISCO_R = 3; // 디스코볼 반지름 (지름 7칸)
// 미러볼 반사광: 공 둘레를 타원으로 도는 하얀 점들
const discoSparks = Array.from({ length: 46 }, (_, i) => ({
  angle: i * 2.4,
  rx: 14 + ((i * 13) % 58),
  ry: 3 + ((i * 5) % 11),
  speed: 0.0004 + (i % 5) * 0.00012,
  phase: i,
}));

// F안: 빛줄기 + 반사 반짝이 (캐릭터 뒤에 그림)
function drawDiscoLights(now) {
  const r = rooms.restricted;
  const floor = r.y + r.h - 2;
  ctx.save();
  // 방 밖으로 새지 않게 제한 구역 안만 그림 (천장 줄무늬 아래부터)
  ctx.beginPath();
  ctx.rect(r.x * S, (r.y + 2) * S, r.w * S, (r.h - 2) * S);
  ctx.clip();

  ctx.globalAlpha = discoGlow * 0.55;
  px(r.x, r.y + 2, r.w, r.h - 2, '#3b2a5a'); // 보랏빛으로 어둡게 해서 빛이 보이게

  // 공에서 바닥까지 내려오는 색 빛줄기 3갈래, 좌우로 흔들림
  for (let i = 0; i < 3; i++) {
    const angle = (reduceMotion ? (i - 1) * 0.6 : Math.sin(now / 1000 + i * 2.1)) * 1.1;
    const color = discoColors[(i * 2 + (reduceMotion ? 0 : Math.floor(now / 1400))) % discoColors.length];
    ctx.globalAlpha = discoGlow * 0.26;
    for (let y = DISCO_Y + 2; y < floor; y++) {
      const d = y - DISCO_Y;
      const cx = DISCO_X + Math.tan(angle) * d;
      const half = 0.5 + d * 0.18;
      px(Math.round(cx - half), y, Math.max(1, Math.round(half * 2)), 1, color);
    }
  }

  // 반사 반짝이
  for (const sp of discoSparks) {
    const a = sp.angle + (reduceMotion ? 0 : now * sp.speed);
    const x = Math.round(DISCO_X + Math.cos(a) * sp.rx);
    const y = Math.round(DISCO_Y + 4 + Math.sin(a) * sp.ry);
    if (y < r.y + 2 || y >= floor) continue;
    ctx.globalAlpha = discoGlow * (reduceMotion ? 0.7 : 0.35 + 0.5 * Math.abs(Math.sin(now / 300 + sp.phase)));
    px(x, y, 1, 1, '#ffffff');
  }
  ctx.restore();
}

// 천장에 매달린 디스코볼 (지름 7칸): 칸 무늬가 돌아가고 한 칸씩 반짝임
// 천장에서 줄을 타고 내려옴 (discoDrop 0 → 1). 천장 위로는 그리지 않음
function drawDiscoBall(now) {
  const r = rooms.restricted;
  const eased = 1 - Math.pow(1 - discoDrop, 3);
  const top = r.y + 2;
  const cy = Math.round(top - DISCO_R - 1 + (DISCO_Y - (top - DISCO_R - 1)) * eased);
  ctx.save();
  ctx.beginPath();
  ctx.rect(r.x * S, top * S, r.w * S, (r.h - 2) * S);
  ctx.clip();
  if (cy - DISCO_R > top) px(DISCO_X, top, 1, cy - DISCO_R - top, '#8a979c'); // 줄
  // 켜져 있을 때만 돌아가며 반짝임
  const turn = reduceMotion || discoGlow < 0.5 ? 0 : Math.floor(now / 220);
  const cells = [];
  for (let y = -DISCO_R; y <= DISCO_R; y++) {
    for (let x = -DISCO_R; x <= DISCO_R; x++) {
      if (x * x + y * y <= DISCO_R * DISCO_R + DISCO_R) cells.push([DISCO_X + x, cy + y]);
    }
  }
  for (const [x, y] of cells) px(x, y, 1, 1, (x + y + turn) % 2 === 0 ? '#d9e0e3' : '#7d8a92');
  if (discoGlow > 0.5) {
    const [sx, sy] = cells[(turn * 7) % cells.length];
    px(sx, sy, 1, 1, '#ffffff');
  }
  ctx.restore();
}

const WARN_LAMP_X = 88; // 경고등 x (디스코볼과 환기구 사이)

// 잠긴 구역: 어둡게 덮고 가운데에 자물쇠 (제한 구역도 같은 자물쇠를 씀)
// dim: false면 덮지 않고 자물쇠만 그림 (원래 어두운 제한 구역용)
function drawLock(room, v, dim = true) {
  if (v < 0.01) return;
  if (dim) {
    ctx.globalAlpha = v * 0.72;
    px(room.x, room.y, room.w, room.h, C.dark);
  }
  ctx.globalAlpha = v;
  const cx = Math.round(room.x + room.w / 2);
  const cy = Math.round(room.y + room.h / 2);
  px(cx - 2, cy - 4, 5, 1, C.labelDim); // 고리
  px(cx - 2, cy - 4, 1, 3, C.labelDim);
  px(cx + 2, cy - 4, 1, 3, C.labelDim);
  px(cx - 3, cy - 1, 7, 5, C.labelDim); // 몸통
  px(cx, cy + 1, 1, 2, C.dark); // 열쇠 구멍
  ctx.globalAlpha = 1;
}

// 제한 구역 안쪽: 봉인된 서류 캐비닛(왼쪽) + 철망이 떼어진 환기구(오른쪽)
// 환기구에서 캐비닛까지 발자국: 누군가 몰래 들어와 문서를 뒤진 흔적
// 좌표는 방 왼쪽 위(r.x, r.y) 기준. 가운데(x 62~74) 천장은 디스코볼 자리라 비워 둠
function drawRestrictedInterior(now, r) {
  const p = (x, y, w, h, color) => px(r.x + x, r.y + y, w, h, color);
  const alpha = ctx.globalAlpha;
  const metal = '#8d978c';
  const metalShade = '#7a8479';
  const seal = '#c8553d';
  const paper = '#e6ede4';

  // 서류 캐비닛 3개 (서랍 3칸), 봉인 테이프
  for (let i = 0; i < 3; i++) {
    const x = 10 + i * 11;
    p(x, 7, 9, 15, metal);
    p(x + 8, 7, 1, 15, metalShade);
    for (let k = 0; k < 3; k++) {
      p(x + 1, 8 + k * 5, 7, 4, metalShade);
      p(x + 3, 9 + k * 5, 3, 1, '#56616b');
    }
    if (i !== 1) p(x + 1, 13, 7, 1, seal);
  }
  // 오른쪽 캐비닛 가운데 서랍이 열려 있고 서류가 삐져나옴
  p(41, 13, 5, 4, metalShade);
  p(42, 12, 3, 1, paper);
  // 바닥에 흩어진 서류
  p(46, 21, 4, 1, paper);
  p(51, 20, 3, 1, paper);
  p(55, 21, 3, 1, '#d8c79a');

  // 환기구: 쇠창살, 떼어낸 철망이 옆에 기대 있음
  p(100, 12, 18, 9, '#3a434c');
  p(101, 13, 16, 7, '#151a20');
  for (let k = 0; k < 4; k++) p(103 + k * 4, 13, 1, 7, '#56616b');
  p(94, 18, 7, 3, metal);
  p(95, 19, 5, 1, '#56616b');
  // 환기구 → 캐비닛 발자국
  for (let k = 0; k < 6; k++) p(90 - k * 8, 21, 2, 1, '#6b5a48');
  // 깜빡이는 형광등
  const flicker = reduceMotion || Math.floor(now / 230) % 7 !== 0;
  p(96, 4, 8, 1, flicker ? '#f3e7a0' : '#8a876c');
  // 벽에 붙은 쪽지
  p(122, 6, 8, 6, paper);
  p(123, 7, 6, 1, seal);
  p(123, 9, 4, 1, '#2a3138');
  ctx.globalAlpha = alpha;
}

function drawRestricted(now) {
  const r = rooms.restricted;
  px(r.x, r.y, r.w, r.h, '#1c232b');
  px(r.x, r.y + r.h - 2, r.w, 2, '#262e36');
  // 안쪽은 잠겨 있는 동안 보이지 않고, 열리면(교수·안테나) 불이 켜지며 나타남
  if (restrictedOpen > 0.01) {
    ctx.globalAlpha = restrictedOpen;
    drawRoomBase(r);
    drawRestrictedInterior(now, r);
    ctx.globalAlpha = 1;
  }

  if (r.state !== 'idle') {
    // 경고 줄무늬
    for (let x = r.x; x < r.x + r.w; x += 6) {
      px(x, r.y, 3, 2, C.caution);
      px(x + 3, r.y, 3, 2, '#2b2f2a');
    }
    // 천천히 숨 쉬듯 깜빡이는 경고등
    const lamp = reduceMotion ? 0.9 : 0.45 + 0.45 * (0.5 + 0.5 * Math.sin(now / 1000));
    ctx.globalAlpha = lamp;
    px(WARN_LAMP_X, 91, 3, 2, C.amber);
    ctx.globalAlpha = 1;
  }
}

function drawLabels(now) {
  for (const key of ['observe', 'server', 'arena']) {
    const room = rooms[key];
    const lit = lightLevel(room, now) > 0.5 && veil[key] < 0.5;
    text(room.label, room.x + 2, room.y + 1.5, lit ? C.label : C.labelDim);
  }
  const r = rooms.restricted;
  const open = restrictedOpen > 0.5;
  text(r.label, r.x + 2, r.y + 3, open ? C.label : r.state === 'active' ? C.amber : C.labelDim);
}

function drawBotLabels(now) {
  for (const bot of bots) {
    if (bot.shownAt === null) continue;
    ctx.globalAlpha = Math.min((now - bot.shownAt) / 500, 1);
    const label = bot.name;
    ctx.font = `700 ${2.4 * S}px 'Pretendard Variable', Pretendard, sans-serif`;
    const w = ctx.measureText(label).width / S;
    text(label, bot.x + BOT_W / 2 - w / 2, ARENA_FLOOR - BOT_H - 3.4, C.label, 2.4, 700);
    ctx.globalAlpha = 1;
  }
}

let frameId = null;
let lastTime = 0;

function frame() {
  const now = performance.now(); // 로딩 쪽 lightAt/shownAt과 같은 시계
  const dt = lastTime ? Math.min(now - lastTime, 50) : 16;
  lastTime = now;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawSky(now);
  ctx.save();
  ctx.translate(OX * S, OY * S); // 여기부터는 건물 장면 좌표
  drawGround();
  drawShell(now);

  updateAccess(dt);
  drawObserve(now);
  darken(rooms.observe, lightLevel(rooms.observe, now));
  drawLock(rooms.observe, veil.observe);
  drawServer(now);
  darken(rooms.server, lightLevel(rooms.server, now));
  drawLock(rooms.server, veil.server);

  drawArenaBase();
  for (const bot of bots) {
    if (bot.shownAt === null) continue;
    updateWalker(bot, dt, BOT_W);
    drawBot(bot, now);
  }
  drawProps();
  darken(rooms.arena, lightLevel(rooms.arena, now));
  drawLock(rooms.arena, veil.arena);

  drawRestricted(now);
  const r = rooms.restricted;
  if (discoGlow > 0.01) drawDiscoLights(now);
  if (party > 0.01) {
    // 캐비닛(디스코 스위치) 앞은 가리지 않게 그 오른쪽에서만 돌아다님
    const floorArea = { x: r.x + 44, w: r.w - 44 };
    for (const ch of chars) {
      updateWalker(ch, dt, charWidth(ch), floorArea);
      drawChar(ch, now, party, r.y + r.h - 2);
    }
  }
  if (discoDrop > 0) drawDiscoBall(now);
  // 잠금 검사가 끝난 제한 구역은 서버실과 같은 자물쇠로 표시 (열리면 사라짐)
  if (rooms.restricted.state === 'checked') drawLock(rooms.restricted, 1 - restrictedOpen, false);
  drawLabels(now);
  if (lightLevel(rooms.arena, now) > 0.5) drawBotLabels(now);
  ctx.restore();

  frameId = requestAnimationFrame(frame);
}

function startScene() {
  cancelAnimationFrame(frameId);
  lastTime = 0;
  for (const key of ['observe', 'server', 'arena']) rooms[key].lightAt = null;
  rooms.restricted.state = 'idle';
  bots.forEach((bot, i) => {
    bot.shownAt = null;
    bot.x = 18 + i * 21;
    bot.target = bot.x;
    bot.wait = 600 + i * 300;
  });
  chars.forEach((ch, i) => {
    ch.x = CHAR_START[i];
    ch.target = ch.x;
    ch.wait = 800 + i * 500;
    ch.facing = 1;
    ch.nextHop = performance.now() + 1500 + i * 900;
  });
  frameId = requestAnimationFrame(frame);
}

function stopScene() {
  cancelAnimationFrame(frameId);
  frameId = null;
}

// 멈췄던 장면을 처음 상태로 되돌리지 않고 이어서 돌림 (단말기에서 정문으로 나올 때)
function resumeScene() {
  cancelAnimationFrame(frameId);
  lastTime = 0;
  frameId = requestAnimationFrame(frame);
}

// canvas는 object-fit: cover로 잘려 보이므로 화면 좌표를 장면 좌표로 바꿔야 함
function toScene(event) {
  const rect = canvas.getBoundingClientRect();
  const scale = Math.max(rect.width / canvas.width, rect.height / canvas.height);
  const [posX = 50, posY = 100] = getComputedStyle(canvas).objectPosition.split(' ').map(parseFloat);
  const offX = (rect.width - canvas.width * scale) * ((Number.isNaN(posX) ? 50 : posX) / 100);
  const offY = (rect.height - canvas.height * scale) * ((Number.isNaN(posY) ? 100 : posY) / 100);
  return {
    x: (event.clientX - rect.left - offX) / scale / S - OX,
    y: (event.clientY - rect.top - offY) / scale / S - OY,
  };
}

// 안테나 둘레를 넉넉히 잡음 (안테나 기둥 x 130, 꼭대기 y 3)
function onAntenna({ x, y }) {
  return x >= 123 && x <= 138 && y >= -1 && y <= 17;
}

// 맨 왼쪽 캐비닛의 빨간 봉인 테이프 (방 기준 x 11~17, y 13) 둘레. 제한 구역이 열려 있을 때만
function onDiscoSwitch({ x, y }) {
  const r = rooms.restricted;
  const tx = x - r.x;
  const ty = y - r.y;
  return restrictedOpen > 0.5 && tx >= 10 && tx <= 19 && ty >= 11 && ty <= 15;
}

canvas.addEventListener('click', (event) => {
  const pos = toScene(event);
  if (onAntenna(pos)) {
    secretOpen = !secretOpen;
    antennaFlashAt = performance.now();
  } else if (onDiscoSwitch(pos)) {
    discoOn = !discoOn;
  }
});

canvas.addEventListener('mousemove', (event) => {
  const pos = toScene(event);
  canvas.style.cursor = onAntenna(pos) || onDiscoSwitch(pos) ? 'pointer' : '';
});

/* ---------- 로딩 진행 ---------- */

// 로딩 단계: 방 하나씩. weight는 진행률에서 차지하는 비중
const stages = [
  { room: 'server', text: '연구소 서버를 켜는 중', weight: 1 },
  { room: 'observe', text: '관찰실 모니터를 켜는 중', weight: 1 },
  { room: 'arena', text: 'YB-1부터 YB-6까지 깨우는 중', weight: 1.6 },
  { room: 'restricted', text: '제한 구역을 잠그는 중', weight: 1 },
];

const totalWeight = stages.reduce((sum, s) => sum + s.weight, 0);
let acc = 0;
for (const stage of stages) {
  stage.start = (acc / totalWeight) * 100;
  acc += stage.weight;
  stage.end = (acc / totalWeight) * 100;
}

let progress = 0;
let stageIndex = -1;
let pauseTicks = 0;
let loadTimer = null;

function addLogLine(str) {
  const prev = logList.querySelector('li.current');
  if (prev) {
    prev.classList.replace('current', 'complete');
    prev.querySelector('.state').textContent = '완료';
  }
  const li = document.createElement('li');
  li.className = 'current';
  const label = document.createElement('span');
  label.textContent = str;
  const state = document.createElement('span');
  state.className = 'state';
  state.textContent = '진행 중';
  li.append(label, state);
  logList.append(li);
}

function enterStage(index) {
  stageIndex = index;
  const { room, text: str } = stages[index];
  // 제한 구역은 불을 켜지 않고 검사 중 표시만 함
  if (room === 'restricted') rooms.restricted.state = 'active';
  else rooms[room].lightAt = performance.now();
  addLogLine(str);
}

// 실험 구역 단계 동안 AI가 한 명씩 나타남
function showBots() {
  const arena = stages.find((s) => s.room === 'arena');
  const ratio = (progress - arena.start) / (arena.end - arena.start);
  const count = Math.max(0, Math.min(bots.length, Math.ceil(ratio * bots.length)));
  bots.forEach((bot, i) => {
    if (i < count && bot.shownAt === null) bot.shownAt = performance.now();
  });
}

function render() {
  const pct = Math.floor(progress);
  percentText.textContent = pct;
  progressEl.setAttribute('aria-valuenow', pct);
  showBots();
}

function finish() {
  clearInterval(loadTimer);
  rooms.restricted.state = 'checked';
  addLogLine('준비 완료');
  logList.querySelector('li.current .state').textContent = '';
  dayText.textContent = '게임을 시작할 수 있습니다';
  loadingScreen.classList.add('done');
  loadingScreen.setAttribute('aria-busy', 'false');
  startButton.hidden = false;
}

function tick() {
  if (pauseTicks > 0) {
    pauseTicks -= 1;
    return;
  }
  progress = Math.min(100, progress + 0.3 + Math.random() * 1.0);

  const next = stages.findIndex((s) => progress < s.end);
  const index = next === -1 ? stages.length - 1 : next;
  if (index !== stageIndex) {
    enterStage(index);
    pauseTicks = 8 + Math.floor(Math.random() * 6);
  }

  render();
  if (progress >= 100) finish();
}

function startLoading() {
  clearInterval(loadTimer);
  progress = 0;
  stageIndex = -1;
  pauseTicks = 0;
  logList.replaceChildren();
  dayText.textContent = '게임 준비 중';
  loadingScreen.classList.remove('done');
  loadingScreen.setAttribute('aria-busy', 'true');
  startButton.hidden = true;
  showTitle();
  startScene();
  render();
  loadTimer = setInterval(tick, 70);

  // 개발용 지름길: 첫 슬롯(대학원생, Day 2, 토큰 8/20)으로 조사 화면만 바로 엶
  if (skipToPlay) {
    clearInterval(loadTimer);
    showInvestigation(saves[0]);
  }
}

/* ---------- 로그인 ---------- */

const titleView = document.querySelector('#title-view');
const loginView = document.querySelector('#login-view');
const idInput = document.querySelector('#login-id');
const pwInput = document.querySelector('#login-pw');
const idError = document.querySelector('#login-id-error');
const pwError = document.querySelector('#login-pw-error');
const pwToggle = document.querySelector('#pw-toggle');
const loginSubmit = document.querySelector('#login-submit');
const loginMessage = document.querySelector('#login-message');

// is-login: 모바일에서 로그인 폼이 들어갈 자리를 위해 연구소 그림을 줄임
function showTitle() {
  resetRole();
  document.querySelector('#lobby-view').hidden = true;
  loginView.hidden = true;
  document.querySelector('#role-view').hidden = true;
  titleView.hidden = false;
  loadingScreen.classList.remove('is-login', 'is-role');
}

function showLogin() {
  titleView.hidden = true;
  loginView.hidden = false;
  loadingScreen.classList.add('is-login');
  loginMessage.textContent = '';
  idInput.focus();
}

function setFieldError(input, errorEl, message) {
  errorEl.textContent = message;
  input.setAttribute('aria-invalid', message ? 'true' : 'false');
}

// 오른쪽 연구소 장면은 그대로 두고 왼쪽만 로그인 폼으로 바꿈
startButton.addEventListener('click', showLogin);

document.querySelector('#back-to-title').addEventListener('click', showTitle);

document.querySelector('#signup-link').addEventListener('click', () => {
  loginMessage.textContent = '계정 만들기는 아직 준비 중입니다.';
});

pwToggle.addEventListener('click', () => {
  const show = pwInput.type === 'password';
  pwInput.type = show ? 'text' : 'password';
  pwToggle.textContent = show ? '숨기기' : '보기';
  pwToggle.setAttribute('aria-pressed', String(show));
});

idInput.addEventListener('input', () => setFieldError(idInput, idError, ''));
pwInput.addEventListener('input', () => setFieldError(pwInput, pwError, ''));

loginView.addEventListener('submit', (event) => {
  event.preventDefault();
  if (loginSubmit.getAttribute('aria-busy') === 'true') return;

  const id = idInput.value.trim();
  const pw = pwInput.value;
  setFieldError(idInput, idError, id ? '' : '아이디를 입력하세요.');
  setFieldError(pwInput, pwError, pw ? '' : '비밀번호를 입력하세요.');
  if (!id) return idInput.focus();
  if (!pw) return pwInput.focus();

  // TODO: 백엔드(FastAPI) 인증 API가 생기면 여기서 요청을 보냄.
  // 지금은 입력만 확인하고 다음 화면으로 넘어가는 임시 로그인
  loginSubmit.setAttribute('aria-busy', 'true');
  loginSubmit.querySelector('.label').textContent = '로그인 중…';
  loginMessage.textContent = '';
  setTimeout(() => {
    loginSubmit.removeAttribute('aria-busy');
    loginSubmit.querySelector('.label').textContent = '로그인';
    pwInput.value = '';
    currentUser = id;
    showLobby();
  }, 700);
});

/* ---------- 역할 선택 (1안: 출입증 3장) ---------- */

// 역할 = 난이도. sample: 계획서 예시 "제한 파일 접근" 사건이 역할별로 보이는 모습
// name: 계획서·백엔드에서 쓰는 이름, label: 화면에 보이는 이름
const roles = {
  prof: { name: 'Professor', label: '교수', sample: '→ 접근한 파일명까지 확인' },
  grad: { name: 'Graduate Student', label: '대학원생', sample: '→ 제한 리소스 접근 시도 탐지' },
  std: { name: 'Undergraduate Researcher', label: '학부 연구생', sample: '→ 403 요청 실패' },
};

const roleView = document.querySelector('#role-view');
const sampleResult = document.querySelector('#sample-result');
const roleError = document.querySelector('#role-error');
const readyTitle = document.querySelector('#ready-title');

function showRoleSelect() {
  loginView.hidden = true;
  titleView.hidden = true;
  roleView.hidden = false;
  loadingScreen.classList.add('is-login', 'is-role');
  // 브라우저가 예전 선택을 복원해 둔 경우에도 화면과 연구소를 그 선택에 맞춤
  // (이미 골라진 걸 다시 누르면 change가 안 일어나서, 안 맞추면 다른 역할을 눌렀다 와야 풀렸음)
  const picked = roleView.querySelector('input[name="role"]:checked');
  if (picked) applyRole(picked.value);
}

// 고른 역할을 예시 상자와 오른쪽 연구소에 반영
function applyRole(value) {
  const role = roles[value];
  if (!role) return;
  sceneRole = value;
  sampleResult.textContent = role.sample;
  sampleResult.classList.add('is-set');
  roleError.textContent = '';
}

// 역할 선택을 처음 상태로 (선택 해제, 예시 상자 비움, 연구소 원래대로)
function resetRole() {
  roleView.reset();
  sceneRole = null;
  sampleResult.textContent = '역할을 고르면 여기에 나옵니다.';
  sampleResult.classList.remove('is-set');
  roleError.textContent = '';
}

roleView.addEventListener('change', (event) => applyRole(event.target.value));

roleView.addEventListener('submit', (event) => {
  event.preventDefault();
  const picked = roleView.querySelector('input[name="role"]:checked');
  if (!picked) {
    roleError.textContent = '역할을 하나 고르세요.';
    return;
  }
  enterPlay('new', picked.value);
});

document.querySelector('#role-back').addEventListener('click', showLobby);

/* ---------- 정문 (로비) ---------- */

const lobbyView = document.querySelector('#lobby-view');
const continueButton = document.querySelector('#menu-continue');
const continueInfo = document.querySelector('#continue-info');
let currentUser = 'researcher01';

// 저장 슬롯 3칸. 역할은 슬롯마다 고정 (계획서: Save마다 Role 고정)
// TODO: 백엔드 Save API가 생기면 여기서 불러옴. 지금은 예시 기록
const MAX_TOKENS = 20; // 조사 토큰 총량: 계획서상 미확정, 임시 값
const saves = [
  { role: 'grad', day: 2, tokens: 8, clues: 5, lastPlayed: '10월 16일' },
  { role: 'std', day: 1, tokens: 17, clues: 1, lastPlayed: '10월 14일' },
  null,
];
let lastSlot = 0; // 가장 최근에 한 슬롯

function saveSummary(save) {
  return `${roles[save.role].label}, Day ${save.day}, 조사 토큰 ${save.tokens} / ${MAX_TOKENS}`;
}

function showLobby() {
  resetRole();
  titleView.hidden = true;
  loginView.hidden = true;
  roleView.hidden = true;
  lobbyView.hidden = false;
  loadingScreen.classList.add('is-login');
  loadingScreen.classList.remove('is-role');
  document.querySelector('#lobby-user').textContent = currentUser;
  document.querySelector('#lobby-account').textContent = currentUser;
  const recent = saves[lastSlot] || saves.find(Boolean);
  continueButton.disabled = !recent;
  continueInfo.textContent = recent ? saveSummary(recent) : '저장된 기록이 없습니다';
}

continueButton.addEventListener('click', () => enterPlay('resume'));
document.querySelector('#menu-new').addEventListener('click', () => {
  lobbyView.hidden = true;
  showRoleSelect();
});
document.querySelector('#logout').addEventListener('click', () => {
  // TODO: 백엔드가 생기면 세션 종료 요청
  lobbyView.hidden = true;
  showTitle();
});

/* ---------- 관찰실 모니터로 들어가는 전환 ---------- */

const fade = document.querySelector('#fade');
const terminal = document.querySelector('#terminal');
const ZOOM = 7;
const MONITOR_AT = [32, 34]; // 관찰실 가운데 모니터 (장면 좌표)

// 장면 좌표 → canvas 요소 안의 픽셀 위치 (toScene의 반대)
function sceneToElement(x, y) {
  const rect = canvas.getBoundingClientRect();
  const scale = Math.max(rect.width / canvas.width, rect.height / canvas.height);
  const [posX, posY] = getComputedStyle(canvas).objectPosition.split(' ').map(parseFloat);
  const offX = (rect.width - canvas.width * scale) * ((Number.isNaN(posX) ? 50 : posX) / 100);
  const offY = (rect.height - canvas.height * scale) * ((Number.isNaN(posY) ? 100 : posY) / 100);
  return [offX + (x + OX) * S * scale, offY + (y + OY) * S * scale];
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// 연구소가 관찰실 모니터 쪽으로 확대되며 어두워진 뒤 단말기가 켜짐
async function zoomIn() {
  const [ox, oy] = sceneToElement(...MONITOR_AT);
  canvas.style.transformOrigin = `${ox}px ${oy}px`;
  if (!reduceMotion) {
    canvas.classList.remove('zoom-out');
    canvas.classList.add('zooming');
    canvas.style.transform = `scale(${ZOOM})`;
    await wait(450);
  }
  fade.classList.add('on');
  await wait(reduceMotion ? 0 : 320);
  stopScene();
  // 예전 터미널 DOM은 보존하지만 v3 진입에서는 사용하지 않는다.
  terminal.hidden = true;
  fade.classList.remove('on');
}

// 반대로: 어두운 화면에서 연구소가 모니터 쪽에서 축소되며 정문이 보임
async function zoomOut() {
  fade.classList.add('on');
  await wait(reduceMotion ? 0 : 300);
  mountedPlay?.unmount();
  mountedPlay = null;
  terminal.hidden = true;
  gameScreen.hidden = true;
  loadingScreen.hidden = false;
  showLobby();
  resumeScene();
  canvas.classList.remove('zooming');
  if (!reduceMotion) {
    canvas.style.transform = `scale(${ZOOM})`;
    await wait(30);
    canvas.classList.add('zoom-out');
  }
  canvas.style.transform = '';
  fade.classList.remove('on');
  await wait(reduceMotion ? 0 : 600);
  canvas.classList.remove('zoom-out');
  continueButton.focus({ preventScroll: true });
}

restartButton.addEventListener('click', zoomOut);

/* ---------- 안별 진입 훅 ---------- */

// v3의 진입 연출은 각 플레이 모듈이 소유한다. 기존 터미널 함수는 아래에
// 남겨 두어 나중에 되돌릴 수 있지만, 새 경로에서는 절대 호출하지 않는다.
function enterPlay(mode, role = null) {
  const play = window.Play?.[requestedPlay];
  if (!play?.enter) return;
  play.enter({
    mode,
    role,
    saves,
    maxTokens: MAX_TOKENS,
    lastSlot,
    root: gameScreen,
    zoomIn,
    zoomOut,
    onStart(slotIndex, startMode = mode) {
      if (startMode === 'new') {
        saves[slotIndex] = { role, day: 1, tokens: MAX_TOKENS, clues: 0, lastPlayed: '오늘' };
      }
      const save = saves[slotIndex];
      if (!save) return;
      lastSlot = slotIndex;
      showInvestigation(save);
    },
    onBack(backMode = mode) {
      zoomOutTo(backMode === 'new' ? () => { lobbyView.hidden = true; showRoleSelect(); } : null);
    },
  });
}

/* ---------- 단말기 ---------- */

const termOut = document.querySelector('#term-out');
const termList = document.querySelector('#term-list');
const termHelp = document.querySelector('#term-help');
let termMode = null; // 'resume' | 'new' | 'boot'
let newRole = null;
let confirmSlot = null; // 새 기록이 기존 기록을 덮어쓸 때 한 번 더 확인

function termLine(html) {
  const line = document.createElement('div');
  line.innerHTML = html;
  termOut.append(line);
}

function termPrompt(cmd) {
  return `<span class="prompt">${currentUser}@yb-lab</span>:~$ ${cmd}`;
}

function renderSlots() {
  termList.replaceChildren();
  saves.forEach((save, i) => {
    const opt = document.createElement('button');
    opt.type = 'button';
    opt.className = 'term-opt';
    opt.dataset.slot = i;
    const cells = save
      ? [`슬롯${i + 1}`, roles[save.role].label, `Day ${save.day}/3`, `토큰 ${save.tokens}  단서 ${save.clues}`]
      : [`슬롯${i + 1}`, '(비어 있음)', '', ''];
    if (termMode === 'new' && save) cells[3] += '  (덮어쓰기)';
    for (const text of cells) {
      const cell = document.createElement('span');
      cell.textContent = text;
      opt.append(cell);
    }
    opt.addEventListener('mouseenter', () => opt.focus());
    opt.addEventListener('click', () => pickSlot(i));
    termList.append(opt);
  });
}

async function enterTerminal(mode, role = null) {
  termMode = mode;
  newRole = role;
  confirmSlot = null;
  termOut.replaceChildren();
  termList.replaceChildren();
  termHelp.textContent = '';
  await zoomIn();
  if (mode === 'resume') {
    termLine(termPrompt('ls 수사기록/'));
    termHelp.innerHTML = '<b>↑ ↓</b> 고르기   <b>Enter</b> 이어하기   <b>Esc</b> 정문으로';
  } else {
    termLine(termPrompt(`./새수사 --역할 ${roles[role].label.replace(/ /g, '')}`));
    termLine('<span class="muted">새 기록을 만들 슬롯을 고르세요.</span>');
    termHelp.innerHTML = '<b>↑ ↓</b> 고르기   <b>Enter</b> 이 슬롯에 만들기   <b>Esc</b> 정문으로';
  }
  renderSlots();
  const first = mode === 'resume'
    ? (saves[lastSlot] ? lastSlot : saves.findIndex(Boolean))
    : Math.max(0, saves.findIndex((s) => !s));
  termList.children[Math.max(0, first)]?.focus();
}

function pickSlot(i) {
  if (termMode === 'resume') {
    // 빈 슬롯을 고르면 새 수사로
    if (!saves[i]) { zoomOutTo(() => { lobbyView.hidden = true; showRoleSelect(); }); return; }
    lastSlot = i;
    boot(saves[i]);
    return;
  }
  if (termMode === 'new') {
    if (saves[i] && confirmSlot !== i) {
      confirmSlot = i;
      termLine(`<span class="deny">슬롯${i + 1}의 ${roles[saves[i].role].label} 기록을 덮어씁니다. 한 번 더 Enter를 누르면 진행합니다.</span>`);
      return;
    }
    // TODO: 백엔드가 생기면 "이 역할로 새 Save 만들기"를 한 번 요청함.
    // 그 뒤로는 서버가 저장한 역할을 쓰고, 프론트는 역할을 다시 보내지 않음
    saves[i] = { role: newRole, day: 1, tokens: MAX_TOKENS, clues: 0, lastPlayed: '오늘' };
    lastSlot = i;
    termLine(`<span class="ok">슬롯${i + 1}에 새 기록을 만들었습니다.</span>`);
    boot(saves[i]);
  }
}

// 접속 연출: 역할에 따라 볼 수 없는 기록 줄이 달라짐
async function boot(save) {
  termMode = 'boot';
  termList.replaceChildren();
  termHelp.textContent = '';
  const access = ROLE_ACCESS[save.role];
  const days = save.day > 1 ? `Day 1~${save.day}` : 'Day 1';
  const lines = [
    termPrompt(`./접속 --기록 슬롯${lastSlot + 1}`),
    `접속 권한 확인 중 ......... <span class="ok">${roles[save.role].label}</span>`,
    `${days} 실험 기록 불러오는 중 ... <span class="ok">완료</span>`,
    `YB-1 ~ YB-6 대화 채널 여는 중 ... <span class="ok">완료</span>`,
    `서버실 기록 .................. ${access.includes('server') ? '<span class="ok">열람 가능</span>' : '<span class="deny">권한 없음</span>'}`,
    `제한 구역 기록 ............... ${access.includes('restricted') ? '<span class="ok">열람 가능</span>' : '<span class="deny">권한 없음</span>'}`,
    '조사를 시작합니다.<span class="cursor"></span>',
  ];
  for (const line of lines) {
    await wait(reduceMotion ? 0 : 280);
    termOut.querySelector('.cursor')?.remove();
    termLine(line);
  }
  await wait(reduceMotion ? 300 : 900);
  showInvestigation(save);
}

// 메인 조사 화면 자리 (C안은 다음 단계)
function showInvestigation(save) {
  termMode = null;
  terminal.hidden = true;
  loadingScreen.hidden = true;
  gameScreen.hidden = false;
  mountedPlay?.unmount();
  const play = window.Play?.[requestedPlay];
  if (play?.mount) {
    mountedPlay = play;
    play.mount(gameScreen, save, { onExit: zoomOut });
    return;
  }
  // 모듈이 로드되지 않은 경우에도 기존 종료 경로를 잃지 않도록 최소 대체 화면을 보임
  readyTitle.textContent = `${roles[save.role].label}, Day ${save.day} 조사를 시작합니다.`;
  gameScreen.className = 'screen ready';
  gameScreen.innerHTML = '<div class="ready-inner"><h2>조사 모듈을 불러오지 못했습니다.</h2><button class="start restart" type="button">정문으로 나가기</button></div>';
  gameScreen.querySelector('.restart').addEventListener('click', zoomOut);
  gameScreen.querySelector('.restart').focus({ preventScroll: true });
}

// 단말기에서 정문으로 (축소 전환). after: 정문을 보여준 뒤 할 일
async function zoomOutTo(after) {
  await zoomOut();
  if (after) after();
}

// 단말기 키보드: ↑ ↓ 고르기, Enter는 버튼 기본 동작, Esc 정문으로
document.addEventListener('keydown', (event) => {
  if (terminal.hidden || termMode === 'boot' || termMode === null) return;
  const opts = [...termList.children];
  const at = opts.indexOf(document.activeElement);
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    const next = (at + (event.key === 'ArrowDown' ? 1 : -1) + opts.length) % opts.length;
    opts[next]?.focus();
  } else if (event.key === 'Escape') {
    event.preventDefault();
    zoomOutTo(termMode === 'new' ? () => { lobbyView.hidden = true; showRoleSelect(); } : null);
  }
});

// 시작 화면에서는 Enter로도 게임 시작 (로그인 폼의 Enter는 폼 제출)
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' || startButton.hidden || titleView.hidden || loadingScreen.hidden) return;
  if (document.activeElement === startButton) return;
  startButton.click();
});

startLoading();
