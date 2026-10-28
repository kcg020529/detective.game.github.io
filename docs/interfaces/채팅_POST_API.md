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
6. retrieve 경로만 E `backend.rag.service.retrieve`를 호출한다(I05). E가 F 사전 인가·최종 resolve를 수행하고 허용 기록(`records`), D용 memory(`m1…`), 조회 상태(`signal`)를 돌려준다. 다른 경로는 검색하지 않는다.
7. D 생성 → G-2 출력 검사 → 최종 답변·질문·요청 캐시 저장 → commit 성공 후 응답한다.

## D / G-2 연결 현황

I05 생성기와 선영 작업 브랜치의 G-2 어댑터는 코드에 있다. 현재 작업 브랜치의 기본 서버에는 G-2만 등록되어 있으며 생성기는 등록하지 않았다. 따라서 기본 POST는 Planner 호출 전에 503을 반환하고 대화는 저장하지 않는다. 실제 외부 LLM 전송 범위와 D/G-2 최종 계약은 별도 확인 대상이다.

현재 작업 브랜치의 등록은 `ChatPipeline(output_guard=check_output)`이다. 요청 본문에서 어댑터를 선택할 수 없다.

- generator: keyword 인자 `question, context, history, plan, records, retrieval`을 받아 draft `{"content","response_type"}` 반환. records는 E/F가 최종 허용한 결과뿐이고 retrieval은 retrieve 경로에서만 넘어온다(나머지는 None). plan의 clarify/out_of_scope도 준수해야 한다.
- output_guard: keyword 인자 `draft, question, context, records`를 받아 최종 `{"content":str,"response_type":"normal|partial|restricted|unknown"}` 반환. 답변은 공백 제외 1~2000자다. 검사 실패 시 예외를 발생시킨다. 승인 전 초안은 반환·저장하지 않는다. 현재 어댑터는 `applied=allow`만 통과시키고 `mask|block`은 503으로 처리한다.
- 검색은 기존 QDRANT_URL과 E FastEmbedder를 사용한다. Planner는 기존 전용 환경변수를 사용한다. D/G-2가 없으면 유료 Planner 호출 전에 중단한다.

## 검증 한계

DB 없는 HTTP·실패·중복·어댑터 회귀 검사는 실제 DB 통합 검증이 아니다. 실제 MariaDB 동시 요청·롤백·감사 영속성, Qdrant 검색, D/G-2 및 프론트 전체 동작은 추가 검증이 필요하다. Save 행 잠금이 모델 호출 중 유지되므로 같은 Save의 병렬 요청은 대기한다.

## 현재 연결 상태 (I05, 2026-10-28)

- 아래는 I05가 `main`에 추가한 생성기 규칙이다. 현재 선영 작업 브랜치에서는 생성기를 기본 서버에 등록하지 않았으므로 채팅은 Planner 호출 전에 503이다.
- 생성기 규칙 (팀 흐름도와 용범의 응답 유형 지시를 따르고, 문서에 없는 부분은 임시로 정함):

| 경로·조회 상태 | D 처리 | response_type |
|---|---|---|
| retrieve, 허용 기록 있음 | `answer` (memory `m1…` 전달) | normal |
| retrieve, `no_match`(맞는 기록 없음) | `unknown` (memory 없음) | unknown |
| retrieve, `no_allowed_records`(F가 허용한 기록 없음) | 고정 문구 `restricted` | restricted |
| character | `answer` (memory 없음) | normal |
| out_of_scope | 고정 문구 `off_topic` | unknown (임시: `out_of_scope` 유형 확정 전) |
| clarify | 서버 고정 안내(코드별 문구) | unknown (임시: D에 clarify 모드가 생기면 변경) |

- 이전 대화는 최근 6개만 D에 넘기고 `user`는 `조사자`, `ai`는 캐릭터 ID로 바꾼다. D가 돌려준 `used`는 `resolve_used`로 거른다. injection 모드는 쓰지 않는다. 빈 답은 오류(503)로 처리한다.
- 로컬에서 실제 Planner·DeepSeek·RAG로 확인(출력 가드 자리에 시험용 통과 함수): 기록 질문 normal, 이어지는 질문 normal, 무관한 질문·권한 밖 속마음 unknown.
