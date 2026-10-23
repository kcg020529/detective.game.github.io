# I01 - 인증·사용자 역할과 Save API

1. `backend/app.py`에 회원가입·로그인·로그아웃·내 정보 API를 구현했다.
   - `POST /api/v1/auth/signup`은 `users`와 `user_roles`를 같은 DB 트랜잭션에 저장하고 201 및 사용자·역할 배열을 반환한다. 중복 아이디는 409, 잘못된 입력은 422 형식의 공통 오류로 반환한다.
   - `POST /api/v1/auth/login`은 저장된 비밀번호 해시를 검증한다. 아이디·비밀번호 중 어느 쪽이 틀렸는지는 구분하지 않고 401을 반환한다.
   - `POST /api/v1/auth/logout`은 서버 세션을 삭제하고 쿠키를 만료한다. `GET /api/v1/auth/me`는 유효 세션의 사용자와 역할 목록을 반환한다.
2. `database/schemas/mariadb/009_auth_sessions.sql`에 세션 테이블을 작성하고 `backend/common/security.py`에 비밀번호·쿠키 처리를 구현했다.
   - 비밀번호는 랜덤 salt를 사용한 scrypt 해시로 저장한다. 세션 쿠키는 랜덤값이며 DB에는 SHA-256 해시·사용자 ID·만료 시각만 저장한다. 세션 만료는 7일로 설정했다.
   - 쿠키는 HttpOnly, 기본 SameSite=Lax이며 로컬 HTTP에서 Secure를 끈다. 상태 변경 요청은 허용된 Origin을 요구하고 CORS 허용 주소를 명시적으로 제한한다. 다른 사이트에서 배포했을 때의 쿠키 동작은 미검증이다.
3. `GET /api/v1/saves`를 구현해 인증 사용자의 `user_id`로만 조회하고 `{ "saves": [] }` 형식으로 반환한다.
   - Save가 없는 가입 직후 J03 화면이 호출할 수 있는 첫 범위다. Save 상세·생성·덮어쓰기, Day 진행, 채팅 API는 아직 구현하지 않았다.
   - J03의 역할 자유 선택 설명과 DB의 `user_roles` 제한 계약이 다르므로 Save 생성 규칙은 팀 합의 전이다.
4. `backend/README.md`에 DB 환경변수·실행·J03 테스트 연결법을 기록했다.
   - `backend/requirements.txt`와 `requirements-dev.txt`에 실행·테스트 의존성을 구분했다. 공유 API 계약 문서의 전체 엔드포인트는 아직 구현되지 않았다.
5. 2026-10-23에 격리된 MariaDB 11.4.12 컨테이너에서 001~007, 009 SQL 초기 적용을 확인하고 `tests/backend/test_auth_integration.py`의 1개 통합 테스트를 실행해 통과했다.
   - 회원가입, 사용자 역할, 비밀번호 해시, 세션, 빈 Save 목록, 중복 가입, 허용되지 않은 Origin, 로그아웃, 틀린 비밀번호, 재로그인을 검증했다.
   - 명령: `python -m unittest discover -s tests/backend -p 'test_*.py' -v`. 테스트 DB 이름이 `_test`로 끝나야 실행된다.
   - 공유 DB, J03 브라우저에서 실제 서버 연동, 배포 환경의 쿠키, 기존 DB 볼륨에 009 SQL 적용은 아직 검증하지 않았다.
