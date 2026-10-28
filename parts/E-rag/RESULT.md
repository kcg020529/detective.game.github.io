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

# E04 - 색인 점검과 유사·모순·노이즈 검색 평가

1. `experiments/rag/check_index.py`
   - JSON 원본, MariaDB, Qdrant 점, manifest를 대조한다. 오류: JSON·DB 기록 불일치, 중복 ID, 빠진 점, 남는 점, 같은 (기록, 종류, 조각 번호)의 중복 점, 끊긴 조각 번호, payload 불일치, manifest 개수 불일치. 경고: 요약·본문이 같은 기록 묶음, 장소가 없는 기록
   - 결과는 `results/index_check.json`에 저장하고, 오류가 있으면 종료 코드 1
   - 로컬 결과: 원본 511 = DB 511, 기대한 점 1,615 = 실제 1,615, **오류 0건**. 경고: 요약이 같은 묶음 47개(106건), 본문이 같은 묶음 7개(29건), 장소 없는 기록 105건(Thought·Result)
2. 평가 질문 (`build_cases.py`): 기존 788개는 내용이 같음(시험으로 해시 확인). 새 질문 252개: `twin` 48, `mixed_type` 96, `noisy` 72, `offtopic` 36. 질문은 기존처럼 "N회차"로 쓴다("시험"이라고 쓰면 header 문구와 겹쳐 점수가 부풀 수 있음)
3. 결과 (`results/quality1.json`, header 색인, 허용 밖 기록 0건, 임시 사용자 남지 않음)
   - **유사(`twin`)**: 회차 조건 없이 "N회차에 X는 d에 어떻게 갔어?"만 보내면 hit@5가 교수 0.31, 대학원생·학부 연구생 0.13으로 낮다. 하지만 1위가 요약이 같은 다른 기록인 경우(`twin_confusion@1`)는 0건이다. 쌍둥이끼리 헷갈리는 것이 아니라 회차·장소를 못 맞히는 것이 원인이다(앞의 `move` plain 결과와 같다)
   - **유형 섞임(`mixed_type`)**: 교수는 hit@5 1.0, 1위 유형이 틀린 비율 0.28. 학부 연구생은 대화 질문에서 1위가 대화인 경우가 없고(`type_confusion@1` 1.0) hit@5 0.38. 이 역할은 대화를 metadata 수준으로만 보는데, 그 짧은 문장이 행동 요약보다 약하게 잡힌다
   - **노이즈(`noisy`)**: 깨끗한 질문과 비교해 hit@5가 떨어지지 않았다(대학원생 +2건, 교수 +1건, 학부 연구생 0건 / 21~24건). 오타·붙여쓰기·군더더기에는 강하다. 다만 기본 점수가 낮은 질문들이라 절대값은 낮다(hit@5 0.33~0.57)
   - **무관한 질문(`offtopic`)**: 세 역할 모두 **100% 기록이 반환**된다("오늘 점심은 뭐 먹을까?"에도 대화·결과 기록 5건). 검색에 관련도 기준(점수 하한)이 없기 때문이다. 다만 설계상 무관한 질문은 Planner가 `out_of_scope`로 걸러 RAG를 부르지 않으므로(MASTER §4.4, Planner README) 정상 경로의 결함이 아니라 Planner가 놓칠 때를 가정한 측정이다
   - 기존 788개: 정답 순위는 `header.json`과 같고, 점수가 같은 기록끼리의 반환 순서만 18건에서 달랐다 (이 절의 수치는 기록 511건 기준)
4. 확인: `pytest tests/rag tests/test_policy_engine.py` 84개 통과, 5개 건너뜀
5. 남은 것
   - 관련도 하한은 필수가 아니다. 무관한 질문은 Planner `out_of_scope`가 처리하는 것이 설계다. 하한은 Planner가 놓칠 때를 대비한 이중 안전장치일 뿐이고, 값을 잘못 잡으면 정상 질문의 정답도 잘리므로 당장 넣지 않는다. 점수 분포를 재서 필요성을 확인한 뒤 정한다
   - 조건 없이 보낸 질문(`twin`)이 약하므로 Planner가 회차·장소·AI 조건을 채워 주는지가 중요하다
   - Prompt-only 기준선 검색 경로: N이 필요한 형태를 먼저 알려 줘야 한다

# E04-2 - 20회차 데이터(812건)로 다시 측정

용범이 4일차(16~20회차)를 올려(`45052c3`) 기록이 511건에서 812건이 됐다(Action 495, Thought 120, Dialogue 104, Incident 43, Setup 30, Result 20).

1. 로컬 반영
   - MariaDB: 적재 전에 `worklog/backups/db_2026-10-27/kervion_before_day4.sql`로 백업. `load_mariadb.py --dataset game-data` dry-run 통과(812건, 권한 2,436행) 뒤 적재. 사용자·Save는 그대로 남음
   - Qdrant: header 색인 다시 만듦. meta 812, summary 812, content 954점
   - `check_index`: 기록 812 = DB 812, 점 2,578 = 2,578, **오류 0건**. 요약이 같은 묶음 47 → 87개(189건), 본문이 같은 묶음 7 → 13개(41건), 장소 없는 기록 140건
2. 평가 질문은 기록에서 만들어서 1,052개가 됐다(전에는 1,040). `LEGACY_CASES_SHA256`은 812건 데이터 기준 값이라 새 값으로 바꿨다. 데이터를 바꿀 때마다 같이 갱신한다
3. 결과 (`results/d20_plain.json`, `results/d20_header.json`, 허용 밖 기록 0건, 임시 사용자 남지 않음)
   - 전체 hit@1 / @3 / @5 / MRR: plain 색인 0.3969 / 0.5142 / 0.5760 / 0.4636 → header 색인 0.4652 / 0.6018 / 0.6624 / 0.5406. 데이터가 늘어도 header가 낫다(511건 때: 0.6113 → 0.6980)
   - 절대 점수는 데이터가 늘어 511건 때보다 조금 내려갔다(header hit@5 0.698 → 0.662, 질문 구성이 달라 완전히 같은 비교는 아님)
   - header가 크게 이기는 곳(hit@5): result plain 0.00→0.60, move plain 0.35→0.53, noisy 0.21→0.46, talk plain 0.07→0.28
   - **header가 지는 곳: `twin`.** 회차 조건 없이 "N회차에 X는 d에 어떻게 갔어?"를 보내면 대학원생·학부 연구생(요약 수준)의 hit@5가 plain 0.60 → header 0.00으로 떨어졌다(교수는 0.44로 같음). 요약만 보는 역할에서 요약 벡터 앞에 붙인 머리글이 회차 구분에는 도움이 안 되고, 같은 AI의 다른 회차 기록이 더 가깝게 잡히는 것으로 보인다. 정확한 원인은 아직 확인하지 않았다
   - 유형 섞임: 교수 hit@5 0.94, 학부 연구생 0.25(대화를 metadata로만 봐서 그대로 약함). 노이즈: 점수 하락 거의 없음. 무관한 질문: 여전히 100% 기록이 반환됨
4. 확인: `pytest tests/rag tests/test_policy_engine.py` 84개 통과, 5개 건너뜀
5. 남은 것
   - `twin` 퇴보 원인 확인과 대안 시험(요약 수준에는 머리글에 회차를 빼거나, 머리글 없는 요약 점을 함께 두는 방법 등). 지금 `header` 기본값은 전체로는 이득이라 유지한다
   - 관련도 하한은 필수가 아님(위 E04 5절 참고)

# E05 - 경유 방 검색 계약과 문서 정리

1. 계약 12절 "경유 방 검색"을 제안으로 추가했다: 경유 방은 `content` 점의 `route_location_ids`에만 담아 full 공개 수준 검색에서만 쓰고, `meta`·`summary`에는 넣지 않는다. 방향도 별도 이동 구조에서 가져와 full에서만 쓴다. 코드는 바꾸지 않았다
2. 로컬 data 확인: Action 495건 중 장소 2곳 335, 1곳 148, 3~4곳으로 합친 기록 12건. 2곳 기록 61건을 본문 도착지와 대조하면 `location_ids[-1]`이 도착지와 같았지만 합친 12건은 배열 순서가 방향이 아니다
3. E04의 "관련도 하한" 표현을 고쳤다(필수 아님, Planner `out_of_scope`가 처리하는 것이 설계)
4. 남은 것
   - 이동 구조 정의·적재(A·B·용범) 뒤에 색인과 검색 규칙 구현
   - 평가에서 합친 Action을 이동 정답 계산에서 제외(`build_cases.py`, 작은 수정)
   - 공통 규칙 검색 방식은 보류
