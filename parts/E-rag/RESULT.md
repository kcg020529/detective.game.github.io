# E01 - Qdrant 색인과 권한 범위 검색

1. 계약 `docs/interfaces/RAG_검색_계약.md` (2026-10-26 용범과 합의)
   - Planner 요청: `query`, `record_types`, `location_ids`, `test_ids`, `related_ai_ids`, `limit`. 빈 배열은 제한 없음, 잘못된 값·빈 query·모르는 필드는 오류
   - 용범 Planner v1(`codex/query-planner`)의 `SearchPlan`에 맞춤: `query` 2,000자까지, `retrieve`일 때만 호출, `limit`은 `resolve`를 통과한 기록 수
   - 용범 리뷰 반영: 검색어가 128토큰을 넘으면 자르지 않고 `QUERY_TOO_LONG` 오류, 색인 전후 체크섬이 같을 때만 manifest를 써서 완료 처리
   - 색인은 적재와 별도 명령. `rules.json`·`characters/`·`map/`은 제외
2. `backend/rag/`
   - `index.py`: `python -m backend.rag.index --dataset game-data --env-file infrastructure/docker/.env`. MariaDB에서 기록·AI 관계·장소를 읽어 데이터셋 컬렉션을 새로 만들고, 마지막에 manifest(`CHECKSUM TABLE` 3개, 모델 이름, 개수)를 씀
   - `search.py`: `search_records(...)`. 허용 ID를 공개 수준별로 나눠 같은 종류의 점만 검색, 기록별로 묶어 후보 최대 100개, `resolve` 뒤 순위대로 `limit`개. 범위가 비면 Qdrant를 부르지 않음. 체크섬·모델·나누기 설정이 manifest와 다르면 `INDEX_STALE`
   - `chunking.py`·`embedder.py`: `paraphrase-multilingual-MiniLM-L12-v2`(384차원, fastembed). 토큰 수는 자르기를 끈 토크나이저로 셈 (fastembed 기본 토크나이저는 128에서 멈춰서 긴 글이 나뉘지 않던 문제를 고침)
   - payload에는 본문·역할·권한을 넣지 않음
3. 로컬 색인 결과 (game-data)
   - 302건 → `meta` 302, `summary` 302, `content` 317점. 15건이 둘 이상으로 나뉨, 가장 긴 조각 128토큰, 빠진 글 없음
4. 확인
   - `pytest tests/rag tests/test_policy_engine.py`: 51개 통과 (메모리 Qdrant + 가짜 임베딩, 실제 토크나이저 나누기 시험 포함)
   - `tests/rag/test_rag_real_policy.py`: 실제 `PolicyRepository`와 로컬 MariaDB로 미래 Day 차단, 남의 Save 거부(Qdrant 호출 전), AI 지식 범위·다른 AI의 Thought 차단, game-data만 검색, std Dialogue는 metadata 필드만 확인. DB가 없으면 건너뜀
   - Planner 계약 예시 출력을 그대로 넣어 통과 확인
   - 실제 로컬 MariaDB·Qdrant: grad·YB-2 Save로 검색하면 허용 기록 5건(summary·full), std Save의 Dialogue는 metadata 필드만 나옴
5. 남은 연동
   - C: Planner가 계약 3절 모양으로 요청
   - I: 채팅 전송 API에서 인증·Save 확인 뒤 호출, `RagRequestError`·`RagUnavailable`을 API 오류 형식으로 바꿈
   - D: `resolve` 결과만 Context로 사용
   - test-data 색인은 아직 안 함. 검색 품질 평가는 E03

# E02 - 채팅 파이프라인 연동

1. 확인: `chat_pipeline.py`는 `plan.route == 'retrieve'`일 때 `search_records`를 `QDRANT_URL`과 `FastEmbedder()`로 부른다. 그대로 동작하지만, 채팅마다 새 `FastEmbedder()`가 모델을 다시 읽던 점을 고쳤다.
2. `backend/rag/embedder.py`: 모델·토크나이저를 모듈 전체에서 공유한다(잠금 포함). 로컬 실제 검색: 첫 호출 약 2.5초, 두 번째 약 0.27초.
3. `backend/rag/search.py`: `search_with_signal(...)`이 `(기록, 신호)`를 돌려준다. 신호는 `ok` / `no_allowed_records`(F가 허용한 기록 없음, Qdrant 호출 안 함) / `no_match`. `search_records`는 같은 인자로 기록 목록만 돌려주며 동작이 그대로다.
4. `backend/rag/service.py`: `retrieve(...)`가 `Retrieval(records, memory, signal)`을 돌려준다. `to_memory`는 공개 수준에 맞는 글만 쓴다: full은 요약+본문, summary는 요약, metadata는 종류·Day·회차·장소·관련 AI 한 줄. 없는 값은 만들지 않는다.
5. 확인
   - `pytest tests/rag tests/test_policy_engine.py` (로컬 MariaDB 포함): 60개 통과. 새 시험 `tests/rag/test_service.py` 9개: memory 변환·신호 3종·재확인에서 모두 걸러진 경우·기존 목록 반환·`retrieve` 묶음·모델 1회 로딩
   - 실제 로컬 Qdrant·MariaDB·임베딩 모델로 임시 Save(grad, Day 2) 검색: 신호 `ok`, memory 3건, 맞지 않는 조건은 `no_match`. 임시 사용자·Save는 삭제함
6. 남은 것
   - I: `chat_pipeline.py`가 `retrieve`를 쓰도록 바꾸기(선택. 지금도 동작함)
   - D·I·F: memory를 `render_actor_prompt`에 연결, 신호와 D 모드(`restricted`·`unknown`)의 대응, memory `id`와 D의 `used` 연결
   - 검색 품질은 E03에서 측정함

# E03 - 검색 품질 측정과 메타데이터 머리글

1. 평가 도구 `experiments/rag/`
   - `build_cases.py` → `eval_cases.json`: 질문 788개(기록에서 규칙으로 만들어 매번 같음). 종류: move·place·talk·incident·result·move_day·place_day·talk_day·guard. 기본 질문 하나를 역할(교수 Day 6, 대학원생·학부 연구생 Day 3)과 변형(`filtered`·`broad`·`plain`)별로 낸다
   - `run_eval.py --name <이름>`: 임시 사용자·Save를 만들어 `service.retrieve`로 실제 검색, hit@1·3·5·MRR 표와 `results/<이름>.json` 저장. 허용 밖 기록·허용 밖 필드·금지 유형·미래 Day 기록이 나오면 위반으로 출력. 끝나면 임시 사용자를 지우고, 남은 것이 있으면 알림. 이미 `rag_eval_%` 사용자가 있으면 멈춤
   - `results/baseline.json`은 첫 측정(질문 472개). 비교는 같은 질문 788개로 잰 `baseline2.json`(plain 색인)과 `header.json`(header 색인)을 쓴다
2. `backend/rag/index.py --text-mode plain|header` (기본 `header`)
   - 머리글: `{유형} Day {day} {시험}시험 | 장소 … | AI …`(involved만). `summary`·`content` 조각 앞에만 붙이고 `meta`는 그대로. witness·overheard AI는 쓰지 않음. 머리글 포함 128토큰 이내
   - manifest에 `text_mode`를 적음. 검색은 어느 쪽 색인이든 동작
3. 결과 (로컬 DB·Qdrant, 위반 0건, 임시 사용자 남지 않음)
   - 전체 hit@1 / @3 / @5 / MRR: plain 색인 0.4595 / 0.5621 / 0.6113 / 0.5177 → header 색인 0.5116 / 0.6460 / 0.6980 / 0.5857
   - 조건을 정확히 주면(`filtered`) 거의 1.0이고 머리글 영향이 거의 없음. 이동 hit@1 0.94→0.85처럼 한두 건 내려간 곳이 있음
   - 질문만 보내면(`plain`) 머리글 효과가 큼. hit@5 기준 result 0→0.56, talk 0.12→0.33, move_day 0.38→0.60, place_day 0.31→0.48. place는 0.34→0.28로 조금 내려감
   - 날짜 범위만 준 경우(`broad`)는 place_day 1.0, move_day·talk_day hit@5 0.9 안팎
   - 조건 없는 질문은 아직 약함(Incident 0.10, place 0.28). 그래서 Planner가 장소·AI·회차 조건을 채워 주는 것이 중요함
4. 확인
   - `pytest tests/rag tests/test_policy_engine.py`: 65개 통과, 5개 건너뜀(DB·토크나이저 캐시 없을 때)
   - 평가 보고서 만들기·저장 실패 때도 위반 수가 출력되는지는 `tests/rag/test_eval_report.py`로 DB 없이 확인
5. 남은 것
   - 조건 없는 질문 개선(질문에서 회차·장소 읽어 조건 채우기, 키워드 검색 혼합, 다른 임베딩 모델)
   - 지나가기만 하는 방(중앙홀 등)은 `location_ids`에 없어 장소 검색이 안 됨. 용범·F와 결정 필요
   - test-data 색인
