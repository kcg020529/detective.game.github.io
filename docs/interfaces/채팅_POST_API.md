# 채팅 POST API — I04

`POST /api/v1/saves/{save_id}/chats/{ai_id}`. 기존 세션 쿠키 인증을 사용한다.

요청: `{"message":"첫날 무슨 일이 있었어?","client_request_id":"chat-unique-1"}`.
message는 공백만 있는 값을 제외한 1~2000자, 요청 ID는 출력 가능한 ASCII 1~64자다. 역할·Day·사용자 ID·dataset 추가 필드는 받지 않는다.

성공 200: `{"messages":[사용자 메시지, AI 메시지],"game_state":Save 상태}`. 메시지 형식은 기존 GET과 동일하다. 안전한 최종 답변만 대화에 저장한다. Save별 요청 ID를 직렬화하며 동일 AI·동일 질문 재전송은 저장된 응답을 반환한다. 같은 ID로 다른 질문·AI·Day 진행을 요청하면 409다. 실패한 요청은 성공 캐시에 넣지 않아 재시도할 수 있다.

## 호출 순서

1. 인증 및 Save 소유권 확인.
2. 입력 가드. 기본 규칙 판정이며 `KERVION_INPUT_GUARD_LLM=1`이면 기존 선택적 DeepSeek 결합 판정을 사용한다. 모든 위험 수준은 계속 처리한다.
3. warn/high_risk는 기존 H 저장 함수를 호출해 별도 단계로 commit한다. 후속 모델 실패에도 경고는 남는다. 요청마다 서버 감사 ID를 발급하므로 재전송도 별도 탐지 이벤트가 될 수 있다. 질문 원문은 감사로그에 저장하지 않는다. 감사 저장 실패 시 처리를 중단한다.
4. Save를 다시 소유권 확인·행 잠금하고 중복 요청을 확인한다. 같은 Save의 Day 진행·덮어쓰기는 답변 처리 트랜잭션과 직렬화된다.
5. 동일 Save/AI의 최근 이력 최대 12개·합계 24000자를 서버에서 조회해 Planner에 전달한다. dataset은 game-data로 고정한다.
6. retrieve 경로만 E search_records를 호출한다. E가 F 사전 인가·최종 resolve를 수행한다. 다른 경로는 검색하지 않는다.
7. D 생성 → G-2 출력 검사 → 최종 답변·질문·요청 캐시 저장 → commit 성공 후 응답한다.

## D / G-2 연결 제안

현재 두 모듈은 없어 기본 POST는 입력 검사·감사 단계 후 503을 반환하며 대화는 저장하지 않는다. 다음 내부 연결 방식은 I 구현의 제안이며 D/G-2 담당자의 합의·실제 구현은 남아 있다.

서버 시작 시 `app.state.chat_pipeline = ChatPipeline(generator, output_guard)`로 연결한다. 요청 본문에서 어댑터를 선택할 수 없다.

- generator: keyword 인자 `question, context, history, plan, records`를 받아 draft 반환. records는 E/F가 최종 허용한 결과뿐이다. plan의 clarify/out_of_scope도 준수해야 한다.
- output_guard: keyword 인자 `draft, context, records`를 받아 최종 `{"content":str,"response_type":"normal|partial|restricted|unknown"}` 반환. 답변은 공백 제외 1~2000자다. 검사 실패 시 예외를 발생시킨다. 승인 전 초안은 반환·저장하지 않는다.
- 검색은 기존 QDRANT_URL과 E FastEmbedder를 사용한다. Planner는 기존 전용 환경변수를 사용한다. D/G-2가 없으면 유료 Planner 호출 전에 중단한다.

## 검증 한계

DB 없는 HTTP·실패·중복·어댑터 회귀 검사는 실제 DB 통합 검증이 아니다. 실제 MariaDB 동시 요청·롤백·감사 영속성, Qdrant 검색, D/G-2 및 프론트 전체 동작은 추가 검증이 필요하다. Save 행 잠금이 모델 호출 중 유지되므로 같은 Save의 병렬 요청은 대기한다.
