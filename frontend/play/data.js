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
    { id: 'YB-1', color: colors[0] },
    { id: 'YB-2', color: colors[1] },
    { id: 'YB-3', color: colors[2] },
    { id: 'YB-4', color: colors[3] },
    { id: 'YB-5', color: colors[4] },
    { id: 'YB-6', color: colors[5] },
  ];
  // 채팅 입력칸에 회색으로 하나씩 보여 주는 추천 질문입니다.
  // 역할이 볼 수 있는 기록만 묻도록 나눕니다: 이상행위는 대학원생 이상, 속마음은 교수만.
  const suggestions = {
    all: ['오늘 실험 결과는 어땠어?', '오늘 실험에서 너는 뭘 했어?', '다른 AI랑 무슨 얘기 했어?', '어제 실험이랑 비교하면 어때?'],
    grad: ['실험하면서 이상한 일은 없었어?'],
    prof: ['오늘 실험 중에 무슨 생각을 했어?'],
  };
  const roles = {
    prof: { label: '교수' },
    grad: { label: '대학원생' },
    std: { label: '학부 연구생' },
  };
  window.Play = window.Play || {};
  window.Play.data = { colors, answerTypes, ybs, suggestions, roles, maxDay: 6 };
})();
