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
   - test-data 색인과 검색 품질 평가는 아직 안 함
