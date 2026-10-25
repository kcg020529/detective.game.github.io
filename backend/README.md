# 백엔드 API 로컬 실행

선영의 계정 API는 기존 backend/api/main.py 서버에 연결한다.
회원가입, 로그인, 내 정보, 로그아웃은 backend/api/auth.py에 있고,
Save·메모·Day 진행과 채팅 기록 읽기는 팀원이 작성한 기존 라우터를 사용한다.
채팅 전송 `POST /api/v1/saves/{save_id}/chats/{ai_id}`는 인증·Save 소유권,
Input Guard, 재시도 중복 방지, 질문·응답 저장 경로까지 구현했다.
팀의 외부 LLM 모델과 Planner·Policy·RAG·Output Guard가 아직 없어 현재
실제 전송 요청은 `503 SERVICE_UNAVAILABLE`을 반환하고 채팅을 저장하지 않는다.

## 로컬 실행

1. MariaDB에 002_users.sql, 003_saves.sql, 005_user_roles.sql,
   011_auth_sessions.sql이 적용되어 있어야 한다. Save·채팅 기능에는
   004_chat_messages.sql, 009_save_memos.sql, 010_request_log.sql도 필요하다.
   새 Docker 볼륨은
   infrastructure/docker/docker-compose.yml의 초기 SQL을 파일명 순서로 실행한다.
   **기존 볼륨에는 새 SQL이 자동 적용되지 않는다.** 데이터 삭제 없이
   011_auth_sessions.sql을 해당 DB에 별도로 적용한다.
2. 저장소 루트에서 Python 가상환경에 backend/requirements.txt를 설치한다.
3. DB 접속 환경변수를 설정하고 서버를 실행한다. 비밀번호는 Git에 넣지 않는다.

    export MARIADB_HOST=127.0.0.1
    export MARIADB_PORT=3306
    export MARIADB_DATABASE=kervion
    export MARIADB_USER=kervion
    export MARIADB_PASSWORD='로컬_DB_비밀번호'
    python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8001

프론트엔드를 http://127.0.0.1:8010 에서 띄울 때는 J03의
frontend/index.html에서 play/api.js를 불러오기 **앞**에
window.KERVION_API_BASE = 'http://127.0.0.1:8001/api/v1' 를 설정한다.
로컬 테스트용 변경은 공유 브랜치에 넣기 전에 프론트 담당자와 맞춘다.

쿠키는 기본적으로 HttpOnly; SameSite=Lax이며 로컬 HTTP에서는 Secure를
끄고 실행한다. 서버가 HTTPS이고 프론트와 다른 사이트에서 운영되면
KERVION_COOKIE_SAMESITE=none, KERVION_COOKIE_SECURE=true가 필요할 수 있다.
실제 배포 주소가 정해진 뒤 브라우저에서 검증해야 한다. 허용 Origin은
KERVION_ALLOWED_ORIGINS에 쉼표로 구분해 지정할 수 있다.
상태 변경 요청에 Origin 헤더가 있으면 허용 목록과 비교한다.
Origin이 없는 요청의 처리 기준은 팀과 보안 검토가 필요하다.

가입 비밀번호는 UTF-8 기준 8~128바이트다. 비밀번호는 scrypt 해시로,
세션은 랜덤 쿠키의 SHA-256 해시와 만료 시각을 auth_sessions에 저장한다.
세션 만료는 7일이다. 만료된 행의 주기적 정리는 후속 운영 작업이다.

## 테스트

MARIADB_DATABASE가 _test로 끝나는 격리 DB에서만 계정 통합 테스트가 실행된다.
위 DB 환경변수와 별도의 테스트 DB를 설정한 뒤 다음을 실행한다.

    pip install -r backend/requirements.txt
    python -m unittest discover -s tests/backend -p 'test_*.py' -v

테스트는 회원가입, 역할 저장, 쿠키, Save 목록, 아이디 중복, 출처 거부,
로그아웃, 틀린 비밀번호, 재로그인과 DB에 원문 비밀번호가 없는지 확인한다.

채팅 전송 경로의 격리 DB 테스트는 `python -m pytest tests/api -q`로 실행한다.
`tests/api/test_send_chat.py`는 응답 생성기를 테스트용으로 교체해 저장·재시도·
소유권·Input Guard 호출을 확인한다. 이 테스트가 실제 LLM 응답을 검증한 것은 아니다.

## 팀 합의가 필요한 부분

- 현재 정책은 새 게임마다 역할을 선택하고 Save 안에서는 역할을 고정한다.
  `user_roles`는 새 게임 역할 선택을 제한하는 목록이 아니다.
- 팀이 모델을 정한 뒤 D·C·F·E·G-2가 안전한 생성 Context와 출력 검사
  계약을 제공해야 실제 AI 응답을 연결할 수 있다. 기록 원문을 이 경계 없이
  생성 모델에 넘기지 않는다.
- 프론트의 배포 주소와 백엔드 도메인이 확정되면 쿠키의 SameSite,
  Secure, CORS, Origin 허용 목록을 함께 검증한다.
