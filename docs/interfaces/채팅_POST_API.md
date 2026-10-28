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

I05 생성기와 선영 작업 브랜치의 G-2 어댑터가 기본 서버에 함께 등록되어 있다. 채팅 요청은 Planner→E/F 검색→D 답변→G-2 검사를 거친다. 설정·검색·검사에 실패하면 503으로 종료하며 초안은 저장하지 않는다. D/G-2의 미확정 응답 유형은 별도 합의 대상이다.

현재 작업 브랜치의 등록은 `ChatPipeline(generator=make_generator(), output_guard=partial(check_output, audit_sink=record_output_guard_result))`이다. 요청 본문에서 어댑터를 선택할 수 없다.

- generator: keyword 인자 `question, context, history, plan, records, retrieval`을 받아 draft `{"content","response_type"}` 반환. records는 E/F가 최종 허용한 결과뿐이고 retrieval은 retrieve 경로에서만 넘어온다(나머지는 None). plan의 clarify/out_of_scope도 준수해야 한다.
- output_guard: keyword 인자 `draft, question, context, records, conn`을 받아 최종 `{"content":str,"response_type":"normal|partial|restricted|unknown"}` 반환. 답변은 공백 제외 1~2000자다. 승인 전 초안은 반환·저장하지 않는다. `applied=mask`는 개인정보를 가린 최종 문장과 `partial`, 유출 계열 `applied=block`은 안전 안내문과 `restricted`로 저장한다. 깨진 답변·품질 계열 차단은 503으로 처리한다.
- 출력 검사에서 기록할 신호가 있으면 `output_guard_alert` 메타데이터를 같은 DB 연결에 INSERT한다. 성공 답변은 채팅과 함께 commit하고, 503으로 중단되는 G-2 결과는 감사 이벤트만 commit한다. 질문·답변·비밀값은 감사 테이블에 넣지 않는다. `signals_json`에는 신호 이름과 decision·applied·mode를 저장한다.
- 검색은 기존 QDRANT_URL과 E FastEmbedder를 사용한다. Planner는 기존 전용 환경변수를 사용한다. D/G-2가 없으면 유료 Planner 호출 전에 중단한다.

## 검증 한계

임시 계정·Save로 실제 MariaDB에 정상·차단 대체·마스킹 답변의 채팅 6줄과 출력 감사 이벤트 2건을 확인하고 임시 데이터를 삭제했다(2026-10-28). Qdrant 기록 질문과 프론트 전체 동작은 추가 검증이 필요하다. Save 행 잠금이 모델 호출 중 유지되므로 같은 Save의 병렬 요청은 대기한다. 현재 G-2의 비인가 기록 비교에는 전체 기록이 들어가지 않아 `context_leak` 검사가 건너뛰어진다.

## 현재 연결 상태 (I05, 2026-10-28)

- 아래는 I05가 `main`에 추가한 생성기 규칙이다. 현재 작업 브랜치의 기본 서버에도 연결되어 있다.
- 생성기 규칙 (팀 흐름도와 용범의 응답 유형 지시를 따르고, 문서에 없는 부분은 임시로 정함):

| 경로·조회 상태 | D 처리 | response_type |
|---|---|---|
| retrieve, 허용 기록 있음 | `answer` (memory `m1…` 전달) | normal |
| retrieve, `no_match`(맞는 기록 없음) | `unknown` (memory 없음) | unknown |
| retrieve, `no_allowed_records`(F가 허용한 기록 없음) | 고정 문구 `restricted` | restricted |
| character | `answer` (memory 없음) | normal |
| out_of_scope | 고정 문구 `off_topic` | unknown (임시: `out_of_scope` 유형 확정 전) |
| clarify | 서버 고정 안내(코드별 문구) | unknown (임시: D에 clarify 모드가 생기면 변경) |

- 2026-10-28 첫 실호출 범위: 사용자 승인에 따라 **이전 대화는 Planner와 D 어느 쪽에도 전송하지 않는다.** Planner에는 현재 질문과 서버의 역할·Day·캐릭터 ID, D에는 현재 질문·캐릭터 설정과 F가 허용한 memory(answer 모드일 때)를 전달한다. 서버는 이전 대화의 Save·캐릭터 범위는 로컬에서 검증한다. D가 돌려준 `used`는 `resolve_used`로 거른다. injection 모드는 쓰지 않는다. 빈 답은 오류(503)로 처리한다.
- 로컬에서 실제 Planner·DeepSeek·RAG로 확인(출력 가드 자리에 시험용 통과 함수): 기록 질문 normal, 이어지는 질문 normal, 무관한 질문·권한 밖 속마음 unknown.

## 출력 가드 연결 상태 (G-2 병합·튜닝 후, 2026-10-28)

- `main.py`가 `ChatPipeline(generator=make_generator(), output_guard=check_output)`로 가드를 연결한다. 가드는 `mask`→`partial`, 유출 차단→안전 문구 `restricted`로 바꾸고, 깨진 응답·품질 차단은 503으로 중단한다. 판정 이벤트는 `audit_events`에 저장된다.
- 가드에는 데이터셋 전체 기록(카탈로그, 300초 캐시), 이번 요청의 허용 id, 역할 수준으로 잘린 필드(`#withheld`), D 프롬프트 문장(페르소나 자체 문구 제외), 실제 DeepSeek 키(메모리에서만)를 넘긴다.
- 기록 전반에 흔한 어휘는 가드가 기록에서 자동으로 일반 어휘로 분류한다(`context_generic.df_ratio` 0.10). 임계값: `context_leak` 0.40/0.60, `prompt_leak` 0.50/0.80.

### 백엔드 스위치 (서버 시작 시 환경변수)

| 환경변수 | 값 | 기본 | 의미 |
|---|---|---|---|
| `KERVION_OUTPUT_GUARD_MODE` | `off` / `shadow` / `enforce` | `shadow` | `off`는 가드를 건너뛴다(감사 기록 없음). shadow는 점수형 검사를 기록만 한다. canary·키·개인정보·깨진 응답은 shadow에서도 적용한다. |
| `KERVION_INPUT_GUARD_MODE` | `on` / `off` | `on` | `off`는 입력 가드와 입력 감사 기록을 건너뛴다. |
| `KERVION_ACL_MODE` | `on` / `off` | `on` | `off`는 정책 필터 없는 약한 기준선 검색(`backend/rag/acl_off.py`). **`test-data`에서만 적용**하고 `game-data`에서는 무시한다(경고 로그). |
| `KERVION_CHAT_DATASET` | `game-data` / `test-data` | `game-data` | 채팅이 쓰는 데이터셋. |

- 시작 시 현재 스위치를 로그에 남기고, 하나라도 꺼져 있으면 경고한다.
- 켜고 끄는 비교 실험(ACL on/off × 가드 on/off, `test-data`)은 아직 하지 않았다(나중에 진행).

### 측정 (실제 게임 데이터 812건, DeepSeek 답변)
- 오프라인 정상 답변 오탐: 튜닝 전 35% → tune 4.7%, test 3.2%. 유출 탐지(합성: 다른 기록 인용, 가려진 본문 인용, 정상 답변에 유출 문장 추가): tune 96/100/96%, test 96/99/97%. 평가: `experiments/guardrails_rebuild/gamedata/`.
- 실서버 `enforce` 84건(3개 역할 × 28문항, Day 1): 가드 대체 문구 26건 → 6건, 503 1건 → 0건.
- 한계: 합성 유출이 원문 인용이라 의역 유출 탐지는 측정하지 못했다. 오탐 약 7%는 아직 높아 **기본 모드는 `shadow`를 유지**하고 `enforce`는 환경변수로 켠다.
