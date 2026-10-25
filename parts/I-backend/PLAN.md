# I01 - Save API (Save·메모·Day 진행)

> 담당: J. 기능 단위로 나눠서 Save 기능은 화면·서버·DB를 J가 같이 맡음. 회원가입·로그인·로그아웃은 선영.

1. FastAPI 기본 틀 (`backend/api/main.py`)
   - 경로 `/api/v1`, CORS(GitHub Pages·로컬 프론트 주소, 쿠키 허용), POST·PUT의 `Origin` 확인
   - 오류는 프론트가 읽는 `{error: {code, message, request_id}}` 모양으로 통일
2. DB 연결 (`backend/api/db.py`, PyMySQL, 용범 적재 도구와 같은 환경 변수)
3. 임시 로그인 사용자 (`backend/api/current_user.py`)
   - 선영 세션 코드가 들어오면 이 파일만 교체
4. Save API (`backend/api/saves.py`)
   - Save 목록·만들기·덮어쓰기·불러오기, 메모 저장, Day 진행
   - Save는 계정마다 따로, 최대 3개 (`saves.user_id`, 슬롯 1~3). 다른 계정 Save는 404
5. 같은 요청 다시 보내기 기록 테이블 `010_request_log.sql`
6. 시험 (`tests/api`, 실제 로컬 MariaDB) + 프론트와 실제 서버 연결 확인
7. 선영 로그인과 합치기 (세션으로 `current_user` 교체, `GET /auth/me`)

# I02 - 채팅 기록 API (읽기)

> 담당: J. 채팅 보내기(AI 답변)는 RAG·캐릭터 AI 흐름이 생긴 뒤 따로.

1. `GET /saves/{save_id}/chats/{ai_id}?limit=20&before={message_id}` (`backend/api/chats.py`)
   - `chat_messages`에서 오래된 순으로 최근 20줄, 남은 게 있으면 `has_more`
2. 시험 (`tests/api/test_chats.py`) + 프론트와 실제 서버 연결 확인

# I03 - 계정 인증·세션 API — 선영

1. users와 user_roles에 가입 계정·선택 역할을 함께 저장하고, 로그인·로그아웃·내 정보 API를 구현한다.
2. 011_auth_sessions.sql에 세션을 저장하고 HttpOnly 쿠키로 인증한다. 비밀번호 원문과 쿠키 원문은 DB에 저장하지 않는다.
3. 기존 backend/api/main.py에 계정 라우터를 붙이고 backend/api/current_user.py의 임시 사용자를 실제 세션 확인으로 교체한다.
4. Save·채팅 API에서 인증된 사용자 ID를 사용하고 다른 사용자 Save 접근을 검증한다.
5. J03 화면의 역할 자유 선택 설명과 DB의 user_roles 제한 계약을 팀과 맞춘다. 배포 도메인 쿠키 설정도 실제 주소에서 검증한다.

# I04 - 채팅 전 Input Guard 연동 — 선영

1. 채팅 전송 API에서 인증·Save 확인 뒤 Input Guard를 호출한다.
2. 팀 합의에 따라 Input Guard는 탐지 전용이다. allow, warn, high_risk 모두 후속 흐름을 계속하고 warn 이상은 감사 이벤트로 만든다. H 저장소·대시보드 전송은 후속 연동한다.
3. 탐지 결과가 권한 상승의 근거가 되지 않도록 F 정책·검색 ACL 검사를 별도로 강제한다.
4. 실제 Planner·RAG·캐릭터 응답·Output Guard와 연결한 후 정상·위험 질문을 검증한다.

# I05 - 채팅 전송 API와 응답 생성 경계 — 선영

1. J 화면의 `POST /api/v1/saves/{save_id}/chats/{ai_id}` 요청 형식에 맞춰 메시지·재시도 ID를 검증한다.
2. 인증·Save 소유권·서버 저장 역할·Day를 확인하고 Input Guard를 호출한다. 같은 재시도 ID는 질문과 AI가 같을 때 처음 응답을 재사용한다.
3. 팀에서 모델을 정하고 C·F·E·D·G-2의 안전한 Context·응답 흐름이 준비되면 실제 생성기를 연결한다. 준비 전에는 503을 반환하고 질문·가짜 답변을 저장하지 않는다.
4. 성공한 생성 응답만 질문과 함께 한 트랜잭션으로 저장하고 프론트의 `messages`·`game_state.current_day` 형식으로 반환한다.
