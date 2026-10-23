# 백엔드 계정 API 첫 구현

현재 구현 범위는 회원가입, 로그인, 내 정보, 로그아웃, Save 목록 조회다.
Save 생성·Day 진행·채팅 API는 아직 없다. J03 화면은 로그인 직후
Save 목록을 요청하므로 새 계정에는 빈 saves 배열을 반환한다.

## 로컬 실행

1. MariaDB에 002_users.sql, 003_saves.sql, 005_user_roles.sql,
   009_auth_sessions.sql이 적용되어 있어야 한다. 새 Docker 볼륨은
   infrastructure/docker/docker-compose.yml의 초기 SQL을 파일명 순서로 실행한다.
   **기존 볼륨에는 새 SQL이 자동 적용되지 않는다.** 데이터 삭제 없이
   009_auth_sessions.sql을 해당 DB에 별도로 적용한다.
2. 저장소 루트에서 Python 가상환경에 backend/requirements.txt를 설치한다.
3. DB 접속 환경변수를 설정하고 서버를 실행한다. 비밀번호는 Git에 넣지 않는다.

    export KERVION_DB_HOST=127.0.0.1
    export KERVION_DB_PORT=3306
    export KERVION_DB_NAME=kervion
    export KERVION_DB_USER=kervion
    export KERVION_DB_PASSWORD='로컬_DB_비밀번호'
    python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000

프론트엔드를 http://127.0.0.1:8010 에서 띄울 때는 J03의
frontend/index.html에서 play/api.js를 불러오기 **앞**에
window.KERVION_API_BASE = 'http://127.0.0.1:8000/api/v1' 를 설정한다.
이 변경은 테스트용 J03 worktree에서만 하고, 프론트 담당자와 합의 없이
공유 브랜치에 넣지 않는다.

쿠키는 기본적으로 HttpOnly; SameSite=Lax이며 로컬 HTTP에서는 Secure를
끄고 실행한다. 서버가 HTTPS이고 프론트와 다른 사이트에서 운영되면
KERVION_COOKIE_SAMESITE=none, KERVION_COOKIE_SECURE=true가 필요할 수 있다.
실제 배포 주소가 정해진 뒤 브라우저에서 검증해야 한다. 허용 Origin은
KERVION_ALLOWED_ORIGINS에 쉼표로 구분해 지정할 수 있다.
상태 변경 요청은 허용된 Origin 헤더가 있어야 한다.

가입 비밀번호는 UTF-8 기준 8~128바이트다. 비밀번호는 scrypt 해시로,
세션은 랜덤 쿠키의 SHA-256 해시와 만료 시각을 auth_sessions에 저장한다.
세션 만료는 7일이다. 만료된 행의 주기적 정리는 후속 운영 작업이다.

## 테스트

KERVION_DB_NAME이 _test로 끝나는 격리 DB에서만 통합 테스트가 실행된다.
위 DB 환경변수와 별도의 테스트 DB를 설정한 뒤 다음을 실행한다.

    pip install -r backend/requirements-dev.txt
    python -m unittest discover -s tests/backend -p 'test_*.py' -v

테스트는 회원가입, 역할 저장, 쿠키, Save 목록, 아이디 중복, 출처 거부,
로그아웃, 틀린 비밀번호, 재로그인과 DB에 원문 비밀번호가 없는지 확인한다.

## 팀 합의가 필요한 부분

- J03 화면은 가입 역할을 기본 선택값으로 보고 이후 모든 역할의 Save 생성을
  허용한다. 현재 database/schemas/mariadb/permissions.md는 계정의
  user_roles에 있는 역할만 Save에 사용할 수 있다고 한다. 이 충돌이
  해결되기 전에는 Save 생성 API를 구현하지 않는다.
- 프론트의 배포 주소와 백엔드 도메인이 확정되면 쿠키의 SameSite,
  Secure, CORS, Origin 허용 목록을 함께 검증한다.
