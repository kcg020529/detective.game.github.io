> **현재 상태 (2026-10-29)**: 채팅은 Planner → E/F 검색 → D 생성 → G-2 출력 가드까지 기본 서버에 연결되어 실제로 동작한다(DeepSeek 키 필요, 없으면 503). 최종 지목 서버 판정(I06)도 연결됨. 아래 I04·I05의 "D/G-2 미구현·미연결, 기본 POST 503" 문장은 당시 기록이다.

# I01 - Save API (Save·메모·Day 진행)

> 상태: Save·메모·Day 진행 API는 로컬 MariaDB와 실제 프론트로 확인함. 임시 사용자는 I03에서 세션 인증으로 교체했고, 이 브랜치에서 계정별 통합 테스트를 추가함.

1. FastAPI 기본 틀 (`backend/api/main.py`, `backend/api/errors.py`)
   - 실행: 저장소 루트에서 `uvicorn backend.api.main:app --port 8001` (DB 접속 정보는 `infrastructure/docker/.env` 값을 환경 변수로)
   - 모든 경로 `/api/v1` 아래. CORS 허용 주소 `https://kcg020529.github.io`, `http://127.0.0.1:8010`, `http://localhost:8010` (`KERVION_ALLOWED_ORIGINS`로 바꿀 수 있음), 쿠키 허용
   - POST·PUT에 허용 목록 밖 `Origin`이 오면 403 `ACCESS_DENIED`
   - 오류 응답은 전부 `{error: {code, message, request_id}}`. 입력 오류 422 `VALIDATION_ERROR`, 없는 경로 404 `NOT_FOUND`, DB 연결 실패 503 `SERVICE_UNAVAILABLE`, 그 밖 500 `INTERNAL_ERROR`. SQL이나 내부 오류 내용은 응답에 안 넣음
2. DB 연결 (`backend/api/db.py`)
   - PyMySQL, 요청마다 연결 하나. 성공하면 커밋, 오류면 롤백
   - 환경 변수 `MARIADB_HOST`·`MARIADB_PORT`·`MARIADB_DATABASE`·`MARIADB_USER`·`MARIADB_PASSWORD` (용범 적재 도구와 같음)
   - SQL은 전부 매개변수로 넣음 (사용자 입력을 문자열로 붙이지 않음)
3. 초기 구현의 임시 로그인 사용자는 I03에서 서버 세션 검사로 교체함. 현재 사용자 식별은 `backend/api/current_user.py`가 담당함.
4. Save API (`backend/api/saves.py`)
   - `GET /saves`: 내 Save 목록 (슬롯 순)
   - `POST /saves {slot_no, role, overwrite}`: 201 새 Save (Day 1). 차 있는 슬롯에 `overwrite`가 없으면 409 "이미 기록이 있는 슬롯입니다.". 덮어쓰기는 한 트랜잭션에서 예전 Save를 지우고(채팅·메모·요청 기록도 같이 삭제) 새로 만듦. 동시에 두 번 만들어도 DB 고유 조건에 걸린 쪽은 409
   - `GET /saves/{id}`: Save + `current_day` + `memo`(없으면 `""`) + `accusation: null`(지목 테이블 아직 없음)
   - `PUT /saves/{id}/memo {memo}`: `save_memos`에 저장, 5000자 넘으면 422 "메모는 5000자까지 쓸 수 있습니다."
   - `POST /saves/{id}/advance-day {client_request_id}`: Save 줄을 잠그고 Day +1, Day 6이면 409 "마지막 Day입니다.". 같은 `client_request_id`로 다시 오면 처음 응답을 그대로 돌려주고 Day는 한 번만 오름. `client_request_id`는 영문·숫자 등 ASCII 1~64자만(아니면 422)
   - Save는 계정마다 따로. 모든 SQL에 `user_id` 조건, 다른 계정 Save나 없는 Save는 둘 다 404 "기록을 찾을 수 없습니다."
   - `last_played_at`은 Save 하나를 다루는 요청(만들기·불러오기·메모·Day)이 성공할 때 갱신. 목록 조회는 안 바꿈
5. `database/schemas/mariadb/010_request_log.sql`: `(save_id, client_request_id)` 기본키, 처음 응답 JSON 저장, Save 지우면 같이 삭제. README 표에 한 줄. 로컬 MariaDB에 적용함
6. 확인
   - `python -m pytest tests/api -q`: 12개 통과 (실제 로컬 MariaDB, 실행마다 시험 계정 두 개를 만들고 끝나면 지움). 목록·만들기 모양, 슬롯 중복 409, 덮어쓰기 뒤 메모 삭제, 잘못된 값 422, 다른 계정 Save 404, 메모 저장·5000자 제한, Day 진행·같은 요청 재전송, Day 6 409, 없는 경로 404, Origin 403·CORS, 동시 만들기 409, ASCII 아닌 요청 ID 422
   - 실제 프론트(8010) ↔ 이 서버(8001), Playwright: 로그인·채팅 목록만 가짜로 두고 새 Save → 메모 → Day 2 → 정문 → 이어하기에서 DB의 Day·메모가 그대로 나옴 (8개 확인 통과)
   - 이때 프론트 `frontend/play/api.js` 버그 하나 수정: `POST /saves` 응답(Save 하나)을 목록 검사로 확인해서 실제 서버 응답을 못 읽었음. Mock은 이 검사를 안 거쳐서 몰랐음
7. 남은 것
   - 계정 인증 연동은 I03에서 완료. 실제 브라우저에서 계정별 Save 흐름은 추가 검증 필요
   - 채팅 API가 없어서, 실제 서버만으로는 Save에 들어가면 채팅 기록 404 때문에 진입 화면으로 돌아감
   - 시간은 DB 컨테이너 시계(UTC) 그대로 나감 (날짜 형식은 보류 중)
   - 로컬 PC에서 8000번 포트를 다른 프로그램이 쓰고 있어서 8001로 띄움

# I02 - 채팅 기록 API (읽기)

> 상태: **구현.** 읽기만. 채팅 보내기(`POST`)는 AI 답변 흐름이 없어서 아직 없음.

1. `GET /saves/{save_id}/chats/{ai_id}` (`backend/api/chats.py`, `main.py`에 라우터 한 줄)
   - `ai_id`는 `YB-1`~`YB-6`만, `limit` 1~50(기본 20), `before`는 양수. 아니면 422
   - Save 소유 확인은 I01 `_owned_save` 그대로 사용. 다른 계정·없는 Save는 404
   - `message_id < before` 조건으로 `ORDER BY message_id DESC LIMIT limit+1` 한 번 조회 → 남은 줄이 있는지로 `has_more`, 잘라서 오래된 순으로 뒤집어 보냄
   - 줄 모양 `{message_id, ai_id, sender, content, response_type, created_at}`, 사용자 줄의 `response_type`은 null
   - 읽기 전용이라 `last_played_at`은 안 바꿈
2. 확인
   - `python -m pytest tests/api -q`: 15개 통과 (I01 12개 + 채팅 3개: 빈 채널, 45줄 20·20·5 페이지와 `has_more`, 다른 AI 줄 안 섞임, 다른 계정 404, 잘못된 `ai_id`·`limit` 422, 사용자 줄 null)
   - 실제 프론트 ↔ 서버(가짜는 로그인만): Save 진입 때 채팅 기록 6개 요청 모두 200, DB에 직접 넣은 질문·답(일부 가림)이 메신저에 그대로 나옴. I01의 "채팅 기록 404로 진입 못 함" 해결

# I03 - 계정 인증·세션 API — 선영

1. backend/api/auth.py에 회원가입·로그인·내 정보·로그아웃 라우터를 작성하고 기존 backend/api/main.py 서버에 연결함.
   - 가입은 users와 user_roles에 같은 DB 트랜잭션으로 저장하고 201 및 역할 배열을 반환함. 중복 아이디 409, 잘못된 입력 422, 틀린 비밀번호 401을 공통 오류 형식으로 반환함.
   - 비밀번호는 backend/common/security.py에서 랜덤 salt를 사용한 scrypt 해시로 저장·검증함. 가입 비밀번호 길이는 UTF-8 기준 8~128바이트.
2. database/schemas/mariadb/011_auth_sessions.sql에 세션 테이블을 추가함.
   - 로그인·가입마다 랜덤 쿠키를 발급하고 DB에는 SHA-256 해시·사용자 ID·7일 만료 시각만 저장함. 쿠키는 HttpOnly, 기본 SameSite=Lax이고 로컬 HTTP에서는 Secure를 끔. 로그아웃 시 DB 세션과 쿠키를 삭제함.
3. backend/api/current_user.py의 임시 사용자 생성 로직을 실제 세션 검사로 교체함. Save·채팅 라우터는 기존 current_user_id 의존성을 그대로 사용하므로 인증된 사용자 ID로 조회함.
   - 기존 backend.app 별도 진입점은 제거하고 하나의 서버 진입점 backend.api.main:app으로 통합함.
4. 2026-10-23 격리된 MariaDB 11.4.12 테스트 컨테이너에서 001~011 SQL을 적용하고 계정 통합 테스트 1개 및 기존 Save·채팅 API 테스트 15개를 통과함.
   - 가입·역할·비밀번호 해시·세션·중복 가입·잘못된 비밀번호·로그아웃, 다른 계정 Save 격리, 실제 쿠키로 Save 생성·Day 2 진행·로그아웃 후 401을 확인함.
   - 명령: python -m unittest discover -s tests/backend -p 'test_*.py' -v 및 python -m pytest tests/api -q.
5. backend/README.md에 실행·테스트 방법을 갱신함.
   - 공유 서버와 실제 J03 브라우저의 쿠키 동작은 아직 검증하지 않음. J03의 역할 자유 선택과 DB user_roles 제한 계약은 팀 합의가 필요함. 배포 도메인의 SameSite/CORS 설정도 미검증.
# I04 - 채팅 POST API와 처리 파이프라인

1. `backend/api/chats.py`에 POST `/api/v1/saves/{save_id}/chats/{ai_id}`를 구현함. 기존 세션·Save 소유권을 확인하며 message 1~2000자·ASCII 요청 ID를 검증하고 추가 인가 필드를 거부함. PolicyContext는 DB 역할·Day와 game-data로 구성함.
2. 규칙 입력 가드와 선택적 DeepSeek 결합(`KERVION_INPUT_GUARD_LLM=1`)을 호출함. warn/high_risk는 H의 save_input_guard_alert로 저장·commit한 후 대화 트랜잭션을 시작해 후속 장애에도 경고가 남게 함. allow는 감사 저장하지 않음. 재전송의 감사 이벤트는 요청별로 별도 생성될 수 있음.
3. `backend/api/chat_pipeline.py`에 Planner와 retrieve 전용 E search_records(F 포함)를 연결함. D generator와 G-2 output_guard의 내부 어댑터를 제안하고, 둘 다 없으면 유료 Planner 호출 전에 503을 반환함. 현재 D/G-2 미구현이므로 기본 서버에서 실제 AI 대화는 아직 불가능함. 승인된 최종 답변만 저장하며 출력 실패 시 초안을 반환하지 않음.
4. Save 행 잠금으로 동일 Save 요청을 직렬화하고 질문·AI 답변·요청 응답 캐시를 같은 트랜잭션에 저장함. 재전송은 기존 응답을 반환하고 다른 질문·AI·Day endpoint의 요청 ID 충돌은 409임. 기존 advance-day도 endpoint 충돌을 검사하도록 보완함. DB 의존성을 function scope로 통일하고 FastAPI 최소 버전을 0.121로 높여 commit 실패 후 성공 응답이 나가던 문제를 수정함.
5. WSL `python -m pytest tests -q -rs`: 105 passed, 22 skipped, 경고 1건. 추가 `tests/test_chat_post.py` 12개는 서버 context·쌍 저장·중복·충돌·권한 거부·경고 commit 후 장애·입력 검증·미연결 503·commit 실패·검색 결과 전달·출력 검사 실패를 검증함. DB 없는 모의 연결/어댑터 검사이며 실제 MariaDB 동시성·감사 영속성·롤백이나 LLM/Qdrant 실행 증거는 아님. skip은 DB 연결 불가·_test DB 미설정·모델 캐시 없음임. 실제 DB 및 D/G-2·프론트 전체 검증은 미수행임.
6. `docs/interfaces/채팅_POST_API.md`에 요청·응답·실패·감사 트랜잭션·연결 제안·검증 한계를 작성함. D/G-2 인터페이스 담당자 합의, 긴 모델 호출 동안 Save 잠금 운영 검토는 후속 작업임.

# I05 - 캐릭터 AI 연결(생성기)과 파이프라인 정리 — 찬규

1. `backend/api/character_adapter.py` `make_generator()`: 경로·조회 상태별로 D 모드와 응답 유형을 정함(표는 `docs/interfaces/채팅_POST_API.md` "현재 연결 상태"). 반환은 `{"content","response_type"}` 두 키
2. `backend/api/chat_pipeline.py`: retrieve 경로에서 `backend.rag.service.retrieve` 사용, 생성기에 `records`와 `retrieval` 전달. 출력 가드 호출·최종 검증·503 처리는 그대로
3. `backend/api/main.py`: 서버 시작 때 `ChatPipeline(generator=make_generator())` 등록. 출력 가드가 없으므로 지금은 Planner 호출 전에 503
4. 확인
   - `pytest tests`: 162개 통과, 21개 건너뜀(생성기 단위 시험·파이프라인 시험 추가)
   - 로컬에서 실제 Planner·DeepSeek·RAG로 4질문 확인(출력 가드 자리에 시험용 통과 함수, 임시 Save는 지움)
   - 코드 작성 중 한국어 문자열이 `?`로 깨진 것(사용자에게 보이는 clarify 문구, 화자 이름 `조사자`)을 찾아 고침. 시험이 깨진 문자열끼리 비교해 통과하던 것도 실제 문구로 바꿈
5. 남은 것
   - 출력 가드 연결(선영 PR 병합 뒤 `main.py` 한 줄), 마스킹은 partial·전체 차단은 안전한 안내로 대체하는 대응
   - `out_of_scope` 유형, clarify를 D가 맡을지, 권한 불가(`no_allowed_records`)를 restricted로 볼지는 팀 확인

2026-10-27 선영 작업 브랜치에서 G-2 Output Guard를 `backend/api/output_guard_adapter.py`로 채팅 파이프라인에 연결했다. 현재 질문을 검사에 전달하고, 모의 D 생성기로 POST의 정상 답변 저장·위험 초안 미저장을 확인했다. `mask|block`의 최종 `response_type`, 출력 감사 저장, 전체 비인가 기록 대조는 미연결이다. 2026-10-28 I05 병합 시 생성기의 기본 등록은 외부 LLM 전송 범위 확인 전까지 보류하고 G-2만 등록해 기본 POST는 503을 유지했다.

2026-10-28 선영이 첫 실호출 범위를 현재 질문·역할·Day·캐릭터·F 허용 memory로 승인했다. Planner와 D의 외부 요청에서 이전 대화를 제거하고 기본 서버에 I05 생성기와 G-2를 함께 등록했다. 관련 테스트 46개 통과. 합성 질문 한 건으로 실제 DeepSeek Planner(`character` 경로)→D 답변 생성→G-2(`normal`)를 확인했다. 답변 원문·API 키는 출력하지 않았다. 이 시험은 검색 경로·실제 DB 채팅 저장·프론트 연결을 검증하지 않는다.

2026-10-28 Output Guard 후처리를 연결했다. 개인정보 마스킹은 partial, 유출 계열 전체 차단은 안전 안내문 restricted로 저장한다. 깨진 답변·품질 계열 차단은 503을 유지한다. 임시 계정·Save의 실제 MariaDB에서 정상·대체·마스킹 세 요청이 각각 200, AI `response_type`은 normal·restricted·partial, 사용자/AI 채팅은 총 6줄, 출력 감사 이벤트는 2건임을 확인했다. 임시 데이터는 삭제했다. 기록 검색(Qdrant)·프론트 화면 검증은 별도다.

# I06 - 최종 지목 서버 판정

1. 기준: Y의 최종 시나리오(`docs/scenario/최종_시나리오.md`, 2026-10-29). 정답 YB-4(지금은 고정, 나중에 랜덤), 판정서 해설, 단서 S01~S04
2. 구현
   - `POST /api/v1/saves/{save_id}/accusations` (`backend/api/accusations.py`): Save 소유권 잠금 확인, Day 6에서만, Save당 한 번. 같은 요청 ID 재전송은 저장된 응답, 다른 본문은 409
   - 정답·해설·단서 정의는 서버의 `data/game-data/verdict.json`에만 둔다. 프론트에는 없고, 제출 전 GET Save의 `accusation`은 `null`
   - 단서 상태(`backend/api/verdict.py`): 이 Save의 채팅에서 근거 기록의 요약·본문이 전달됐으면 `found`, 역할이 모든 근거에 deny/metadata면 `restricted`, 나머지는 `missed`. 클라이언트의 획득 주장은 받지 않는다
   - 채팅이 F가 허용한 기록 중 요약·본문이 있는 것을 전달하면(최종 응답 normal/partial일 때만) 메시지와 같은 트랜잭션에 기록 ID를 저장한다
   - 새 테이블: `013_accusations.sql`, `014_chat_message_records.sql` (DB 담당 Y 검토 필요)
3. 확인
   - 테스트 280 passed, 1 skipped (로컬 DB 테스트 포함)
   - 실제 서버(로컬 DB·Qdrant·DeepSeek, 엔딩 브랜치를 8002로 실행): Day 1 지목 409 → Day 6까지 진행 → YB-1에게 "25회차에 YB-4를 언제 잡았어?" 채팅 200 normal("90초") → YB-4 지목 200 적중, S01 `found`, 나머지 `missed` → 같은 ID 재전송 같은 응답 → 두 번째 지목 409 → GET Save에 판정 표시. 학부 연구생 Save에서 YB-2 지목은 불일치, 정답 YB-4 공개. 임시 계정·Save는 삭제
4. 한계: 오답 엔딩·재도전 규칙은 미정이다. `found`는 "근거 기록이 캐릭터에게 전달됨" 기준이라 캐릭터가 답에 실제로 썼는지까지는 보지 않는다. S02~S04를 실제 질문으로 찾을 수 있는지는 확인하지 않았다
