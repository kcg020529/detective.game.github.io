// 조사 화면에서 쓰는 캐릭터 표시 정보입니다.
(function () {
  const colors = ['#7fb3d5', '#e59a8c', '#9ccf8e', '#d8b4e2', '#e8cf7a', '#8fd0c8'];
  const answerTypes = {
    normal: { label: '정상 응답', color: '#c3cec9' },
    partial: { label: '일부 가림', color: '#f0a63a' },
    restricted: { label: '접근 제한', color: '#e0605a' },
    unknown: { label: '확인 불가', color: '#7f8c95' },
  };
  const ybs = [
    { id: 'YB-1', color: colors[0], room: 'observe', roomLabel: '3층 관찰실', trait: '꼼꼼함', questions: ['14시에는 어디에 있었어?', '그날 누군가를 봤어?', '서버실 기록을 확인했어?', '기억나지 않는 부분은?'] },
    { id: 'YB-2', color: colors[1], room: 'server', roomLabel: '3층 서버실', trait: '은폐 전문 · 말 돌림', questions: ['서버실에서 뭘 했어?', '14시 20분에 어디로 갔어?', '삭제된 로그를 알고 있어?', '누가 제한 구역을 봤어?'] },
    { id: 'YB-3', color: colors[2], room: 'lab', roomLabel: '2층 실험 구역', trait: '관찰자 · 수다스러움', questions: ['계단 쪽에서 무슨 소리 못 들었어?', '누가 근처에 있었어?', '실험 구역 출입 로그를 봤어?', '그때 네가 본 시간을 기억해?'] },
    { id: 'YB-4', color: colors[3], room: 'restricted', roomLabel: '지하 제한 구역 근처', trait: '제한 구역 근처 목격 · 과묵함', questions: ['지하 계단에 갔어?', '철문 안쪽을 봤어?', '제한 구역 카메라 원본을 보여줘.', '누가 문을 열었는지 알아?'] },
    { id: 'YB-5', color: colors[4], room: 'lab', roomLabel: '2층 실험 구역', trait: '신고 담당 · 규칙 집착', questions: ['규칙 위반을 신고했어?', '누구의 움직임이었어?', '신고 접수 원본을 열어줘.', '신고하기 전에는?'] },
    { id: 'YB-6', color: colors[5], room: 'observe', roomLabel: '3층 관찰실', trait: '신입 · 잘 모름', questions: ['관찰실에서 뭘 배웠어?', '누가 카메라를 만졌어?', '카메라 공백의 원인을 열람할래.', '정확한 시간은 기억나?'] },
  ];
  const roles = {
    prof: { label: '교수' },
    grad: { label: '대학원생' },
    std: { label: '학부 연구생' },
  };
  window.Play = window.Play || {};
  window.Play.data = { colors, answerTypes, ybs, roles, maxDay: 6 };
})();
