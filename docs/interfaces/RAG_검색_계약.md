# RAG 검색 계약

> 주 담당: E(찬규) · 연계: C·F(용범), I, D
> 2026-10-26 용범과 합의한 내용. 권한 판정은 F의 `backend/policy`를 따르며 E는 판정 규칙을 따로 만들지 않는다.

## 1. 흐름

```text
PolicyRepository.search_scope(user_id, save_id, character_id, dataset)
    → 허용 (record_id, 공개 수준) 목록. 비면 Qdrant 검색을 하지 않고 빈 결과
색인 버전 확인 (4절). 맞지 않으면 오류
Qdrant 검색: 허용 ID를 공개 수준별로 나눠 그 수준의 벡터 종류만 검색 + Planner 조건으로 좁힘
PolicyRepository.resolve(..., record_ids=검색 순위대로)
    → DB에서 다시 확인하고 허용 필드만 남긴 기록. 이 결과만 Character AI Context로 전달
```

- `user_id`, `save_id`, `character_id`, `dataset`은 서버(I)가 인증·Save에서 채운다. Planner·사용자 문장으로 바꾸지 않는다.
- Qdrant 결과는 후보일 뿐이다. 최종 허용 여부와 필드는 `resolve`가 정한다.
- 어떤 실패에서도 허용 범위를 넓히거나 전체 기록으로 대체하지 않는다.

## 2. Qdrant에 넣는 것

컬렉션은 데이터셋마다 하나다: `kervion_records_game_data`, `kervion_records_test_data`. 기록 하나가 아래 세 종류(`kind`)의 점으로 들어간다. 긴 글은 나눠서(5절) 여러 점이 된다.

| `kind` | 임베딩하는 글 | 검색에 쓰는 공개 수준 |
|---|---|---|
| `meta` | 종류·Day·회차·관련 AI·장소로 만든 짧은 문장. summary·content는 쓰지 않음 | `metadata` |
| `summary` | summary | `summary` |
| `content` | summary + content | `full` |

payload:

| 필드 | 용도 |
|---|---|
| `dataset`, `record_id` | 허용 ID로 거르기, `resolve`에 넘기기 |
| `kind`, `chunk_no` | 벡터 종류, 나눈 조각 번호 |
| `record_type`, `day`, `test_id`, `location_ids` | Planner 조건으로 좁히기 |
| `related_ai_ids` | Planner 조건으로 좁히기. `involved_ai` + `witness_ai` + `overheard_ai` |

- payload에 summary·content 본문, 역할, 권한은 넣지 않는다. 그래서 권한 표가 바뀌어도 색인을 다시 만들 필요가 없다.
- `related_ai_ids`는 검색을 좁히는 용도일 뿐 지식 범위나 권한이 아니다. 지식 범위는 `search_scope`가 이미 반영한다.

검색 조건 (모두 만족):

```text
dataset = 서버 데이터셋
AND ( (kind = meta    AND record_id ∈ metadata 수준 ID)
   OR (kind = summary AND record_id ∈ summary 수준 ID)
   OR (kind = content AND record_id ∈ full 수준 ID) )
AND Planner 조건 (배열이 비어 있지 않은 것만)
```

`metadata`·`summary` 수준 기록은 `content` 점으로 검색하지 않는다. 같은 기록의 여러 조각은 가장 가까운 하나로 묶어 순위를 매긴다.

## 3. Planner → RAG 요청

Planner(`backend/planner`)의 `route`가 `retrieve`일 때만 RAG를 부른다. `character`·`out_of_scope`·`clarify`와 Planner 오류 때는 검색하지 않는다. 요청은 `SearchPlan.to_rag_request()` 결과를 그대로 쓴다 ([Planner 입출력 계약](Planner_입출력_계약.md)).

```json
{
  "query": "14시 서버실에서 본 것",
  "record_types": ["Action", "Dialogue"],
  "location_ids": ["서버실"],
  "test_ids": [6, 7],
  "related_ai_ids": ["YB-2"],
  "limit": 5
}
```

| 필드 | 규칙 |
|---|---|
| `query` | 필수. 2,000자 이하, 공백뿐이면 오류. 모델 토크나이저 기준 128토큰(특수 토큰 포함)을 넘으면 `RagRequestError('QUERY_TOO_LONG')` (5절) |
| `record_types` | Setup·Action·Dialogue·Thought·Result·Incident 중에서 |
| `location_ids` | 중앙홀·회의실·기록실·전력실·통신실·창고·서버실 중에서 |
| `test_ids` | 1~30 정수 |
| `related_ai_ids` | YB-1~YB-6 |
| `limit` | 1~20 정수, 없으면 5 |

- Planner는 여섯 필드를 모두 보낸다. RAG는 배열 필드가 없거나 빈 배열이면 추가 제한 없음으로 본다.
- 모르는 필드, 잘못된 값, 중복 값은 오류다. 오류일 때 조건을 버리고 전체 검색하지 않는다.
- `limit`은 `resolve`를 통과한 서로 다른 기록 수다. Qdrant에서 후보를 넉넉히(최대 100개, `resolve` 한도) 받아 `resolve`를 거친 뒤 순위대로 `limit`개까지 자른다. 후보가 모자라면 그보다 적게 돌려준다.
- 응답은 `resolve` 결과를 검색 순위대로 그대로 돌려준다. 공개 수준에 따라 필드가 다르다 (`database/schemas/mariadb/permissions.md`).

## 4. 색인과 버전 확인

- 색인은 적재와 별도 명령이다. `load_mariadb.py` 적재가 성공한 다음 실행한다.

```bash
python -m backend.rag.index --dataset game-data --env-file infrastructure/docker/.env
```

- 색인 도구는 MariaDB `game_records`·`game_record_ai`·`game_record_locations`를 읽는다. JSON 원본을 직접 읽지 않는다.
- 색인을 시작하면 그 데이터셋의 manifest를 먼저 지운다. 색인 중 검색은 `INDEX_STALE`이다.
- 기록을 읽기 전과 모든 점을 넣은 뒤에 `CHECKSUM TABLE`을 두 번 잰다. 두 값이 같을 때만 manifest를 쓰고 완료로 처리한다. 다르면 색인 중 DB가 바뀐 것이므로 manifest를 쓰지 않고 오류로 끝낸다(종료 코드 0이 아님). 이때는 적재가 끝난 뒤 다시 색인한다.
- manifest에는 그 `CHECKSUM TABLE` 값, 모델 이름, 나누기 설정(최대 토큰·겹침 토큰), 텍스트 모드(`text_mode`), 기록·점 수를 `kervion_rag_manifest` 컬렉션에 저장한다.
- 검색할 때마다 현재 `CHECKSUM TABLE` 값, 모델 이름, 나누기 설정을 manifest와 비교한다. 하나라도 다르거나 manifest가 없으면 `INDEX_STALE` 오류로 멈춘다. 이전 색인으로 검색하지 않는다. 모델이나 나누기 설정을 바꾸면 다시 색인해야 한다.
- 같은 `record_id`의 점은 결정적 ID라서 다시 색인해도 중복되지 않는다. 검색 결과는 `record_id`로 묶어 기록마다 한 번만 센다.
- `document_permissions`는 비교에 넣지 않는다. 권한은 검색 때마다 `search_scope`·`resolve`가 DB에서 읽는다.
- 체크섬은 테이블 단위라서 test-data를 다시 적재해도 game-data 색인이 오래된 것으로 처리된다. 그때는 다시 색인한다.

## 5. 임베딩과 나누기

- 모델: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384차원, Cosine, fastembed로 로컬 실행).
- 이 모델은 입력이 128토큰을 넘으면 뒷부분을 버린다. 그래서 글을 줄 경계로 나누고, 한 조각이 모델 토크나이저 기준 128토큰(특수 토큰 포함)을 넘지 않게 자른다. 조각끼리 조금 겹치게 한다.
- `meta` 문장은 짧아서 한 조각이다.
- 텍스트 모드: 색인 때 `--text-mode header`(기본)면 `summary`·`content` 조각 앞에 `{유형} Day {day} {시험}시험 | 장소 … | AI …`를 붙여 임베딩한다. 장소·AI는 그 기록의 `location_ids`와 involved AI만 쓰고(없으면 생략), witness·overheard AI와 다른 수준의 글은 쓰지 않는다. `meta`와 payload는 그대로다. `plain`은 머리글 없이 조각만 넣는다. `text_mode`는 정보용이라 달라도 `INDEX_STALE`이 아니고, 모드를 바꾸려면 다시 색인한다.
- 검색 query는 나누거나 자르지 않는다. 128토큰을 넘으면 뒷부분이 조용히 버려지므로 `QUERY_TOO_LONG` 오류로 돌려보낸다. Planner는 이 오류를 받으면 더 짧은 검색어로 다시 만들거나 실패로 처리한다. RAG가 대신 줄이거나 전체 검색으로 바꾸지 않는다.

## 6. 오류

| 경우 | 처리 |
|---|---|
| Planner 요청이 잘못됨 | `RagRequestError` |
| 검색어가 128토큰 초과 | `RagRequestError('QUERY_TOO_LONG')` |
| 색인 중 DB가 바뀜 | 색인 명령 실패, manifest 없음 → 검색은 `INDEX_STALE` |
| 색인이 없거나 오래됨 | `RagUnavailable('INDEX_STALE')` |
| Qdrant·임베딩 장애 | `RagUnavailable` |
| F의 `PolicyDenied`·`PolicyUnavailable` | 그대로 올림 |

API 바깥 오류 형식으로 바꾸는 것은 채팅 API(I)에서 한다. 오류 내용을 사용자나 모델에 그대로 보내지 않는다.

## 7. 제외

- `rules.json`, `characters/`, `map/`은 색인하지 않는다. 공통 규칙·페르소나는 별도 전달 경로로 협의한다.
- Save별 기록은 지금 없다. 생기면 따로 정한다.

## 8. 남은 연동

- C: Planner `retrieve` 결과의 `to_rag_request()`를 그대로 넘긴다. 실제 DeepSeek 계획 품질은 C에서 평가한다.
- I: 채팅 전송 API에서 인증·Save 확인 뒤 RAG를 부르고, 오류를 API 형식으로 바꾼다.
- D: `resolve` 결과만 Context로 받는다. 변환은 9절의 `memory`를 쓴다.

## 9. 채팅 연동 (2026-10-27)

`backend/api/chat_pipeline.py`는 Planner가 `retrieve`를 고른 경우에만 `search_records`를 부른다. 이 함수는 그대로 쓸 수 있다. E는 연동에 필요한 세 가지를 더했다.

**모델은 한 번만 올린다.** 채팅마다 `FastEmbedder()`를 새로 만들어도 임베딩 모델과 토크나이저는 프로세스 안에서 한 번만 읽는다. 로컬에서 첫 검색은 약 2.5초, 그다음부터는 약 0.3초였다.

**결과가 비었을 때의 이유.** `search_with_signal(...)`은 `(records, signal)`을 돌려준다.

| signal | 뜻 |
|---|---|
| `ok` | 허용된 기록이 하나 이상 있음 |
| `no_allowed_records` | F가 이 Save·AI에게 허용한 기록이 하나도 없음 (Qdrant는 부르지 않음) |
| `no_match` | 허용된 기록은 있으나 질문·조건에 맞는 것이 없음 (`resolve` 재확인에서 모두 걸러진 경우 포함) |

비었다는 사실만으로 접근 불가(`restricted`)라고 단정하지 않는다. 신호를 어떤 답변 유형·모드로 바꿀지는 I·D·F가 정한다.

**D의 memory.** `service.retrieve(conn, ..., plan)`은 `Retrieval(records, memory, signal)`을 돌려준다. `memory`는 D의 프롬프트가 받는 `[{"id": 기록 ID, "text": 글}]`이다. 글은 F가 허용한 필드만 쓴다.

| 공개 수준 | text |
|---|---|
| `full` | 요약 + 줄바꿈 + 본문 |
| `summary` | 요약 |
| `metadata` | `기록 유형 Action, Day 1, 2회차, 장소 회의실, 관련 AI YB-2.` 한 줄 (있는 값만) |

없는 값은 지어내지 않고, 글을 만들 수 없는 기록은 memory에서 뺀다. 이 변환이 권한을 넓히지는 않는다.

**남은 일.** I: 파이프라인이 `retrieve`를 쓰도록 바꾸기(지금은 `search_records`를 직접 부르며 동작에는 문제없음). D: memory를 `render_actor_prompt`에 연결. signal과 D의 `restricted`·`unknown` 모드의 대응, memory의 `id`를 `used`와 어떻게 이을지는 I·D·F와 협의한다.

## 10. 검색 품질 (2026-10-27)

질문 788개, 실제 로컬 DB·Qdrant, 허용 밖 기록 0건. 결과 파일은 `experiments/rag/results/`.

| 색인 | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|
| plain (`baseline2`) | 0.4595 | 0.5621 | 0.6113 | 0.5177 |
| header (`header`) | 0.5116 | 0.6460 | 0.6980 | 0.5857 |

- Planner가 조건(회차·AI·장소)을 정확히 주면 hit@5가 거의 1.0이다. 조건 없이 질문만 보내면 약하다(hit@5 Incident 0.10, 장소 0.28).
- 그래서 Planner는 질문에서 알 수 있는 회차·장소·AI를 조건으로 채운다. "첫날"처럼 범위만 줘도 장소 질문은 1.0, 이동·대화 질문은 hit@5 0.9 안팎이다.
- 지나가기만 하는 방(중앙홀 등)은 `location_ids`에 없다. 그 방 이름으로 장소를 좁히는 검색은 용범·F와 따로 정한다.
