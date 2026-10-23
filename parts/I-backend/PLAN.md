# I01 - 인증·사용자 역할과 Save API

1. `002_users.sql`의 `users`와 `005_user_roles.sql`의 `user_roles`를 기준으로 J03 회원가입·로그인·로그아웃·내 정보 API를 구현한다.
   - 가입 시 선택 역할 한 개를 `user_roles`에 저장한다. 비밀번호 원문은 저장하지 않고 `password_hash`를 생성·검증한다.
2. 로그인 상태를 서버에서 검증할 수 있도록 `009_auth_sessions.sql`의 세션 테이블과 HttpOnly 쿠키를 사용한다.
   - 새 로그인마다 세션을 생성하고, 만료·로그아웃을 처리한다. 로컬 Origin·CORS를 확인하고 배포 도메인 쿠키 설정은 실제 주소가 정해지면 검증한다.
3. `003_saves.sql`의 `saves`를 기준으로 본인 Save 목록을 구현한 뒤 상세·생성 API를 확장한다.
   - `save_id`는 서버 생성값, `slot_no`는 사용자별 1~3, `role`은 `prof`·`grad`·`std`, `day`는 1~6이다. Save 생성 시 선택한 역할이 해당 계정의 `user_roles`에 있는지 서버에서 확인한다.
   - 모든 Save 조회·변경에서 인증된 `user_id`와 `saves.user_id`를 비교한다. 슬롯 덮어쓰기·삭제 및 연결 데이터 정리 규칙은 구현 전에 합의한다.
   - J03 화면은 모든 역할의 Save 생성을 허용하지만 DB 권한 문서는 계정의 허용 역할만 허용한다. 이 충돌을 합의하기 전까지 Save 생성은 보류한다.
4. 기존 `docs/interfaces/API_요청응답_계약.md`의 Save 요청·응답 형식을 현재 SQL과 프론트엔드 요구에 맞춰 확정한다.
   - `slot_no`, `save_id`, `role`, `day`, `last_played_at`의 형식과 미소유 Save의 외부 오류 응답을 확인한다.
5. 격리된 MariaDB에서 계정 API와 빈 Save 목록을 통합 검증하고, 공유 서버·J03 실제 화면 연동은 별도로 확인한다.

# I02 - Day 진행 API

1. `saves.day`를 서버의 현재 Day로 사용하고, 본인 Save에서만 “다음날” 요청을 허용한다.
2. 저장된 Day를 한 번에 1만 증가시키고 Day 6에서 추가 진행을 거부한다. 클라이언트가 보낸 Day 값으로 덮어쓰지 않는다.
3. 연속 클릭·재시도 시 Day가 두 번 증가하지 않도록 중복 처리 방식을 정하고, 상태 변경과 응답을 검증한다. `last_played_at` 갱신 시점도 합의한다.

# I03 - 채팅 API·Input Guard·대화 이력 연동

1. `004_chat_messages.sql`의 `chat_messages`를 기준으로 Save·AI별 대화 이력 조회와 사용자 질문·AI 응답 저장을 구현한다.
   - 조회·저장 전마다 Save 소유권을 확인한다. 질문 원문과 AI 응답의 DB 보관 범위·삭제 정책을 정한다.
2. 인증된 사용자와 Save 상태를 확인한 뒤 사용자 질문을 Input Guard에 전달한다.
   - 팀 합의에 따라 Input Guard는 탐지 전용으로 사용한다. `allow`, `warn`, `high_risk` 모두 후속 흐름을 계속하고, `warn` 이상은 요청 ID·위험 수준·탐지 사유를 감사 이벤트로 전달한다. 질문 원문을 대시보드 알림에 기본 포함하지 않는다.
3. Input Guard 다음에 Planner·F 정책·검색 ACL·캐릭터 응답·Output Guard를 연결한다. Input Guard 결과는 역할·Day·Save·문서 접근권한을 올리는 근거로 사용하지 않는다.
4. SQL의 AI 응답 `response_type` (`normal`, `partial`, `restricted`, `unknown`)과 API 초안의 `reply_kind` (`normal`, `redacted`, `access_denied`, `unknown`)가 다르므로, 저장값과 화면 표시값의 대응을 프론트엔드·DB 담당자와 합의한다.
5. 실제 DB와 각 모듈이 연결된 뒤 정상 질문, 위험 질문, 미소유 Save, Day 제한, 오류 흐름을 검증한다. 연결되지 않은 기능은 완료로 기록하지 않는다.
