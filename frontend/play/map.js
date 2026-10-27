// 지도 앱: 연구실 코르크 게시판에 테이프로 붙인 손그림 연구동 지도.
// 방을 가리키거나 누르면 그 방이 살짝 칠해짐.
(function () {
  // 방 상자 [x, y, w, h] (SVG 1200 x 800 좌표)
  const ROOMS = {
    회의실: [170, 110, 300, 250], 기록실: [490, 140, 270, 220], 서버실: [760, 100, 290, 260],
    중앙홀: [150, 360, 700, 130],
    통신실: [170, 490, 250, 210], 창고: [440, 490, 230, 230], 전력실: [690, 490, 360, 200],
  };
  const LINKS = [['중앙홀', '회의실'], ['중앙홀', '기록실'], ['중앙홀', '통신실'], ['중앙홀', '창고'], ['중앙홀', '전력실'], ['서버실', '기록실'], ['서버실', '전력실']];

  const box = ([x, y, w, h]) => `<path class="c-map-pen" d="M${x} ${y} L${x + w} ${y + 2} L${x + w - 1} ${y + h} L${x + 1} ${y + h - 1} Z"/>`;
  // 문: 벽에 빈칸(종이색) + 반원
  const doorH = (x, y, up) => `<path class="c-map-gap" d="M${x} ${y} h40"/><path class="c-map-pen-l" d="M${x} ${y} q 20 ${up ? -26 : 26} 40 0"/>`;
  const doorV = (x, y) => `<path class="c-map-gap" d="M${x} ${y} v40"/><path class="c-map-pen-l" d="M${x} ${y} q -26 20 0 40"/>`;

  function drawing() {
    let h = '';
    for (const [name, b] of Object.entries(ROOMS)) {
      h += `<g class="c-map-room" data-map-room="${name}" tabindex="0" role="button" aria-label="${name}">${box(b)}<rect class="c-map-hit" x="${b[0]}" y="${b[1]}" width="${b[2]}" height="${b[3]}"/></g>`;
    }
    // 서버실 ↔ 전력실 통로. 중앙홀과 통로 사이는 막힌 벽(빗금)
    h += '<rect class="c-map-hatch" x="852" y="363" width="86" height="125"/>';
    h += '<path class="c-map-pen" d="M940 360 L941 490 M992 360 L991 490"/><path class="c-map-gap" d="M943 360 h46 M943 490 h46"/>';
    h += '<path class="c-map-pen-l" d="M966 380 v90 M957 392 l9 -12 l9 12 M957 458 l9 12 l9 -12"/>';
    h += '<text class="c-map-hand c-map-hand-s" x="1002" y="432">통로</text>';
    // 문: 위 두 방·아래 세 방 → 중앙홀, 서버실 → 기록실
    h += doorH(300, 360, true) + doorH(600, 360, true);
    h += doorH(275, 490, false) + doorH(535, 490, false) + doorH(760, 490, false);
    h += doorV(760, 220);
    for (const [name, [x, y]] of Object.entries(ROOMS)) if (name !== '중앙홀') h += `<text class="c-map-hand c-map-hand-b" x="${x + 24}" y="${y + 48}">${name}</text>`;
    h += '<text class="c-map-hand c-map-hand-b" x="360" y="438">중앙홀</text>';
    // 방 안 낙서
    h += `<path class="c-map-pen-l" d="M230 230 h170 v50 h-170 z"/>${[0, 1, 2, 3].map((i) => `<circle class="c-map-pen-l" cx="${252 + i * 42}" cy="214" r="8"/><circle class="c-map-pen-l" cx="${252 + i * 42}" cy="296" r="8"/>`).join('')}`;
    h += '<rect class="c-map-hatch" x="560" y="220" width="120" height="90"/><path class="c-map-pen-l" d="M560 220 h120 v90 h-120 z M560 250 h120 M560 280 h120"/>';
    h += [0, 1, 2].map((i) => `<path class="c-map-pen-l" d="M${810 + i * 70} 180 h44 v140 h-44 z"/>${[0, 1, 2, 3].map((j) => `<path class="c-map-pen-l" d="M${818 + i * 70} ${200 + j * 30} h28"/>`).join('')}`).join('');
    // 통신실: 이름은 왼쪽 위, 안테나는 오른쪽, 무전기는 왼쪽 아래
    h += '<path class="c-map-pen-l" d="M310 670 l40 -60 l40 60 z M350 610 v-34"/><path class="c-map-pen-l" d="M342 570 q8 -10 16 0 M334 561 q16 -20 32 0"/>';
    h += '<path class="c-map-pen-l" d="M200 610 h70 v44 h-70 z M212 624 h20 M250 624 h8"/>';
    h += '<path class="c-map-pen-l" d="M480 600 h60 v60 h-60 z M480 600 l60 60 M550 630 h50 v70 h-50 z M608 665 h36 v35 h-36 z"/>';
    h += '<path class="c-map-pen-l" d="M760 560 h120 v100 h-120 z"/><path class="c-map-pen c-map-bolt" d="M830 575 l-26 36 h30 l-24 36"/><path class="c-map-pen-l" d="M880 600 q60 0 60 40 t60 25"/>';
    h += [0, 1, 2, 3, 4, 5].map((i) => `<circle class="c-map-pen-l" cx="${620 + i * 30}" cy="425" r="7"/>`).join('') + '<text class="c-map-hand c-map-hand-s" x="620" y="465">YB 6대</text>';
    h += '<text class="c-map-hand c-map-title" x="70" y="64">YB 실험동</text><path class="c-map-pen-l" d="M70 76 h150"/>';
    h += '<g transform="translate(1110 730)"><path class="c-map-pen-l" d="M0 -36 L9 0 L0 36 L-9 0 Z"/><text class="c-map-hand c-map-hand-s" x="-6" y="-44">N</text></g>';
    return h;
  }

  function markup() {
    return `<div class="c-map-board">
      <span class="c-map-pin" aria-hidden="true"></span>
      <div class="c-map-paper">
        <span class="c-map-tape is-tl" aria-hidden="true"></span><span class="c-map-tape is-tr" aria-hidden="true"></span>
        <span class="c-map-tape is-bl" aria-hidden="true"></span><span class="c-map-tape is-br" aria-hidden="true"></span>
        <svg viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid meet" role="group" aria-label="연구동 손그림 지도">
          <defs>
            <filter id="c-map-rough"><feTurbulence type="fractalNoise" baseFrequency=".035" numOctaves="2" seed="4"/><feDisplacementMap in="SourceGraphic" scale="4"/></filter>
            <pattern id="c-map-hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="10" stroke="#2f2b26" stroke-width="1.2" opacity=".35"/></pattern>
          </defs>
          ${drawing()}
        </svg>
      </div>
    </div>`;
  }

  function show(root, name) {
    root.querySelectorAll('[data-map-room]').forEach((g) => g.classList.toggle('is-on', g.dataset.mapRoom === name));
  }

  function bind(root) {
    root.addEventListener('pointerover', (e) => { const g = e.target.closest('[data-map-room]'); if (g) show(root, g.dataset.mapRoom); });
    root.addEventListener('click', (e) => { const g = e.target.closest('[data-map-room]'); if (g) show(root, g.dataset.mapRoom); });
    root.addEventListener('focusin', (e) => { const g = e.target.closest('[data-map-room]'); if (g) show(root, g.dataset.mapRoom); });
    root.addEventListener('keydown', (e) => { const g = e.target.closest('[data-map-room]'); if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); show(root, g.dataset.mapRoom); } });
  }

  window.Play = window.Play || {};
  window.Play.map = { markup, bind, rooms: Object.keys(ROOMS), links: LINKS };
})();
