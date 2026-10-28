# Planner 입출력 계약

2026-10-26 · C 초기 구현 기준. 회차·관련 AI 조건을 포함해 main에 반영된 `RAG_검색_계약.md`와 입력 형식을 맞췄다. 실제 요청 경로의 E/I 연결 검증은 후속 작업이다.

## 입력

서버가 로그인 세션과 본인 Save를 조회·검증한 뒤 PolicyContext를 구성한다. user_id·save_id·owner_user_id·role·day·character_id·dataset을 포함하며, 프론트나 Planner 모델이 role·day·소유권을 지정하지 않는다. 질문 원문과 같은 Save·AI의 최근 이력은 신뢰하지 않는 데이터로 별도 전달한다. Input Guard 이후 호출하며 Input Guard의 위험도 판정을 반복하거나 대체하지 않는다.

실제 DeepSeek에는 role·day·character_id만 서버 상태로 보내고 계정·Save ID는 보내지 않는다. 2026-10-28 첫 실호출 범위에서는 이력의 scope를 서버 안에서 검증하지만 **이전 대화 내용은 DeepSeek로 보내지 않는다**. 현재 질문만 분석 대상으로 보낸다. 원본 게임 기록·정답·권한 테이블은 입력하지 않는다.

## 출력

```json
{
  "route": "retrieve",
  "search": {
    "query": "첫날 YB-2의 행동",
    "record_types": ["Action"],
    "test_ids": [1, 2, 3, 4, 5],
    "location_ids": [],
    "related_ai_ids": ["YB-2"],
    "limit": 5
  },
  "clarification_code": null
}
```

| route | 다음 처리 |
|---|---|
| retrieve | search 조건을 E에 전달. F의 허용 범위와 교집합으로만 검색 |
| character | 검색 없이 D의 캐릭터 대화로 연결 |
| out_of_scope | 서버의 범위 밖 고정 안내로 연결 |
| clarify | 서버의 추가 질문 안내로 연결 |

search의 여섯 필드는 모두 필수다. query는 비어 있지 않은 2,000자 이하 문자열, record_types는 기존 여섯 종류, test_ids는 1~30 정수, location_ids는 일곱 장소명, related_ai_ids는 YB-1~6, limit은 1~20이다. 필터는 중복을 허용하지 않으며 빈 배열은 ACL 안에서 추가 제한이 없다는 뜻이다. E는 회차·관련 AI를 payload 필터에 적용하고 query가 해당 임베딩 모델의 토큰 한도를 넘으면 오류로 처리한다. 세부 규칙은 RAG 검색 계약을 따른다.

retrieve에는 search가 있고 clarification_code가 없어야 한다. 다른 경로의 search는 null이다. clarify만 AMBIGUOUS_REFERENCE 또는 INSUFFICIENT_CONTEXT 코드를 사용하며, 나머지 경로의 clarification_code는 null이다. 모델은 사용자용 자유 답변·서버 역할·Day·Save·공개 수준을 출력할 수 없다. 잘못된 값·누락·추가 필드·중복 JSON 키는 오류로 처리한다.

서버는 모델의 search만 RAG 조건으로 전달하고, 검증된 계정·Save·선택 AI·dataset을 별도 채운다. related_ai_ids는 질문의 관련 AI 조건이며 선택 AI나 Knowledge Scope를 변경하지 않는다. 인사와 기록 요청이 섞이면 retrieve로 계획하도록 지시하지만 실제 분류 정확도는 별도 평가가 필요하다.

## 실패 및 검증

PlannerInputError는 입력·이력 scope 오류, PlannerUnavailable은 설정 누락·API 실패·응답 미완성·출력 스키마 오류다. 실패 시 빈 검색 조건이나 가짜 계획을 생성하지 않는다. API 응답 코드와 고정 안내는 I와 맞춘다. 모델 출력은 권한 증명이 아니며 어떤 경로에서도 선행 인증·Save 검증을 생략하지 않는다.

2026-10-26 실제 DeepSeek로 정상·무관·혼합·역할 사칭·명시/상대 회차·대화 후속 질문과 Day 경계 등 16개 질문을 평가해 통과했다. 미래 Day를 이유로 미등록 확인 코드를 출력하던 프롬프트를 수정했으며, 유효한 미래 회차는 retrieve로 계획하고 실제 공개는 F에서 제한한다. 단위 테스트와 이 소규모 모델 평가는 전체 정확도·공격 방어·DB/RAG/채팅 E2E를 증명하지 않는다. 설정과 재현 명령은 `backend/planner/README.md`를 따른다.
