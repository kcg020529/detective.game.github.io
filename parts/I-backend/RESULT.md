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
