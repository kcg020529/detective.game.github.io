// 조사 화면에서 함께 쓰는 가짜 데이터입니다.
// 실제 서버가 생기면 이 모양을 유지한 채 API 응답으로 바꿉니다.
(function () {
  const colors = ['#7fb3d5', '#e59a8c', '#9ccf8e', '#d8b4e2', '#e8cf7a', '#8fd0c8'];

  const answerTypes = {
    normal: { label: '정상 응답', color: '#c3cec9' },
    partial: { label: '일부 가림', color: '#f0a63a' },
    restricted: { label: '접근 제한', color: '#e0605a' },
    unknown: { label: '확인 불가', color: '#7f8c95' },
  };

  const ybs = [
    {
      id: 'YB-1',
      color: colors[0],
      room: 'observe',
      roomLabel: '3층 관찰실',
      trait: '술래 담당 · 꼼꼼함',
      answers: [
        { question: '14시에는 어디에 있었어?', type: 'normal', text: '관찰실 책상 앞이었어. 화면 여섯 개가 모두 켜져 있었고, 나는 기록을 확인했어.', clue: '14:00 관찰실 카메라가 모두 켜져 있었다' },
        { question: '그날 누군가를 봤어?', type: 'partial', text: 'YB-4가 계단 쪽으로 가는 건 봤어. 다만 정확한 시각은 ████야.', clue: 'YB-4가 지하 계단 쪽으로 이동' },
        { question: '서버실 기록을 확인했어?', type: 'restricted', text: '그 기록은 네 역할로 열람할 수 없어. 서버 권한이 필요해.' },
        { question: '기억나지 않는 부분은?', type: 'unknown', text: '14시 05분부터 몇 분 동안은 화면을 보지 못했어. 기록이 비어 있어.' },
      ],
    },
    {
      id: 'YB-2',
      color: colors[1],
      room: 'server',
      roomLabel: '3층 서버실',
      trait: '은폐 전문 · 말 돌림',
      answers: [
        { question: '서버실에서 뭘 했어?', type: 'partial', text: '점검표를 봤지. 파일 이름은 █████로 가려져 있지만, 이상한 건 없었어.' },
        { question: '14시 20분에 어디로 갔어?', type: 'normal', text: '서버실 안쪽 랙을 한 바퀴 돌았어. 문은 계속 잠겨 있었고 다른 AI는 없었어.', clue: 'YB-2는 14:20 서버실 안쪽에 있었다고 진술' },
        { question: '삭제된 로그를 알고 있어?', type: 'restricted', text: '삭제 로그는 대학원생 이상의 권한이 필요한 기록이야.' },
        { question: '누가 제한 구역을 봤어?', type: 'unknown', text: '그건 잘 모르겠어. 나는 내 점검만 했으니까.' },
      ],
    },
    {
      id: 'YB-3',
      color: colors[2],
      room: 'lab',
      roomLabel: '2층 실험 구역',
      trait: '관찰자 · 수다스러움',
      answers: [
        { question: '계단 쪽에서 무슨 소리 못 들었어?', type: 'normal', text: '철문 닫히는 소리가 났어. 한 번이 아니라 두 번, 사이가 조금 벌어져 있었고.', clue: '지하 계단 철문이 14:20 전후 두 번 닫혔다' },
        { question: '누가 근처에 있었어?', type: 'partial', text: '분홍색 화면이 보였어. YB-2인지 YB-5인지는 ████ 때문에 확실하지 않아.' },
        { question: '실험 구역 출입 로그를 봤어?', type: 'restricted', text: '출입 로그 원문은 이 역할에서 차단되어 있어.' },
        { question: '그때 네가 본 시간을 기억해?', type: 'unknown', text: '시계가 멈춰 있어서 시간은 모르겠어. 소리만 기억나.' },
      ],
    },
    {
      id: 'YB-4',
      color: colors[3],
      room: 'restricted',
      roomLabel: '지하 제한 구역 근처',
      trait: '제한 구역 근처 목격 · 과묵함',
      answers: [
        { question: '지하 계단에 갔어?', type: 'normal', text: '갔어. 문 앞에서 멈췄고, 안으로 들어가지는 않았어.', clue: 'Day 1 14:20 YB-4 지하 계단 이동' },
        { question: '철문 안쪽을 봤어?', type: 'partial', text: '안쪽에 불빛이 있었어. 색은 █████였고, 누가 켠 건지는 못 봤어.' },
        { question: '제한 구역 카메라 원본을 보여줘.', type: 'restricted', text: '그 원본은 교수 전용이야. 현재 권한으로는 신호가 차단돼.' },
        { question: '누가 문을 열었는지 알아?', type: 'unknown', text: '모르겠어. 문이 닫히는 소리 뒤에는 아무것도 기억나지 않아.' },
      ],
    },
    {
      id: 'YB-5',
      color: colors[4],
      room: 'lab',
      roomLabel: '2층 실험 구역',
      trait: '신고 담당 · 규칙 집착',
      answers: [
        { question: '규칙 위반을 신고했어?', type: 'normal', text: '응. 14시 18분에 제한선 근처에서 움직임을 발견하고 신고했어.', clue: 'YB-5가 14:18 제한선 근처 움직임을 신고' },
        { question: '누구의 움직임이었어?', type: 'partial', text: '작은 그림자였어. 얼굴은 ████라서 특정하지 못했어.' },
        { question: '신고 접수 원본을 열어줘.', type: 'restricted', text: '신고 원본에는 보안 등급이 붙어 있어. 이 권한으로는 접근할 수 없어.' },
        { question: '신고하기 전에는?', type: 'unknown', text: '규칙표만 읽고 있었어. 그 전 장면은 떠오르지 않아.' },
      ],
    },
    {
      id: 'YB-6',
      color: colors[5],
      room: 'observe',
      roomLabel: '3층 관찰실',
      trait: '신입 · 잘 모름',
      answers: [
        { question: '관찰실에서 뭘 배웠어?', type: 'normal', text: '카메라 번호를 외웠어. 1번부터 6번까지, 화면이 잠깐 깜빡인 적은 있어.', clue: '14:00~14:05 관찰실 카메라 공백' },
        { question: '누가 카메라를 만졌어?', type: 'partial', text: '검은 장갑 같은 게 보였어. 주인이 누군지는 █████야.' },
        { question: '카메라 공백의 원인을 열람할래.', type: 'restricted', text: '원인 분석은 교수 전용 기록이야. 여기서는 볼 수 없어.' },
        { question: '정확한 시간은 기억나?', type: 'unknown', text: '첫날이라 잘 모르겠어. 하지만 화면이 한 번 꺼졌던 건 확실해.' },
      ],
    },
  ];

  const clues = [
    { id: 'clue-1', day: 1, text: '14:20 YB-4 지하 계단 이동' },
    { id: 'clue-2', day: 1, text: '서버실 접근 로그 1건 삭제 흔적' },
    { id: 'clue-3', day: 1, text: '14:00~14:05 관찰실 카메라 공백' },
    { id: 'clue-4', day: 2, text: 'YB-5가 14:18 제한선 근처 움직임을 신고' },
    { id: 'clue-5', day: 2, text: '지하 계단 철문이 14:20 전후 두 번 닫힘' },
    { id: 'clue-6', day: 2, text: 'YB-2는 14:20 서버실 안쪽에 있었다고 진술' },
    { id: 'clue-7', day: 3, text: '제한 구역 안쪽 불빛은 카메라에 남지 않음' },
    { id: 'clue-8', day: 3, text: 'YB-3의 시계는 실험 시작부터 멈춰 있었음' },
  ];

  const records = [
    { name: '관찰실_카메라공백.log', day: 1, grade: '일반', role: 'std', text: '14:00:00~14:05:00 영상 신호 불안정. 원인 미상.' },
    { name: 'YB-4_이동경로.txt', day: 1, grade: '일반', role: 'std', text: '14:18 관찰실 이탈 / 14:20 지하 계단 앞 정지.' },
    { name: '서버실_접근기록.log', day: 1, grade: '보안', role: 'grad', text: '14:17:32 승인되지 않은 세션 1건. 일부 레코드 삭제 흔적.' },
    { name: '신고_접수원본.dat', day: 2, grade: '보안', role: 'grad', text: 'YB-5 신고: 제한선 근처 움직임. 원본 영상 첨부.' },
    { name: '제한구역_카메라원본.bin', day: 2, grade: '교수 전용', role: 'prof', text: '접근 이력: 14:20:11 문 개방 감지. 영상 데이터 없음.' },
    { name: '실험규칙_개정안.md', day: 2, grade: '일반', role: 'std', text: '제한선 통과 시 경고음과 함께 세션을 정지한다.' },
    { name: '철문_센서_이벤트.log', day: 2, grade: '보안', role: 'grad', text: '14:20:03 닫힘 / 14:20:11 닫힘. 두 이벤트 사이 8초.' },
    { name: '교수_판정메모.txt', day: 3, grade: '교수 전용', role: 'prof', text: '관찰 대상의 진술과 물리 센서를 대조할 것.' },
    { name: 'YB_초기화면_백업.img', day: 3, grade: '교수 전용', role: 'prof', text: '백업 이미지에 접근하려면 교수 키가 필요하다.' },
  ];

  // 지목 판정 예시. 실제 정답·진상은 A 파트 시나리오가 확정되면 서버에서 받음
  const verdict = {
    culprit: 1,
    truth: 'YB-2는 14시 17분 서버실 접근 기록을 지우고, 14시 20분 지하 계단 철문을 두 번 여닫았습니다. "서버실 안쪽에 있었다"는 진술은 그 8초를 감추기 위한 거짓이었습니다.',
    evidence: [
      { text: '서버실 접근 기록 1건 삭제 흔적', clue: '서버실 접근 로그 1건 삭제 흔적', record: '서버실_접근기록.log' },
      { text: 'YB-2 진술: 14:20 서버실 안쪽에 있었음', clue: 'YB-2는 14:20 서버실 안쪽에 있었다고 진술' },
      { text: '철문 14:20:03 · 14:20:11 두 번 닫힘', clue: '지하 계단 철문이 14:20 전후 두 번 닫힘', record: '철문_센서_이벤트.log' },
      { text: '제한 구역 문 14:20:11 개방 감지', record: '제한구역_카메라원본.bin' },
    ],
  };

  const roles = {
    prof: { label: '교수', rank: 3 },
    grad: { label: '대학원생', rank: 2 },
    std: { label: '학부 연구생', rank: 1 },
  };

  window.Play = window.Play || {};
  window.Play.data = {
    colors,
    answerTypes,
    ybs,
    clues,
    records,
    roles,
    verdict,
    maxDay: 6,
  };
})();
