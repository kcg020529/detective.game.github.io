# B01 - 게임 기록 스키마

1. `database/schemas/mariadb/001_game_records.sql`에 정적 게임 기록용 DDL을 작성함.
   - `game_records`에 A01 공통 필드 중 AI 목록을 제외한 식별·회차·Day·요약·본문을 저장함. `dataset`을 추가하고 `(dataset, record_id)`를 기본키로 사용해 테스트·정식 데이터의 ID 충돌을 방지함.
2. AI 배열을 `game_record_ai`로 분리함.
   - `relation_kind`로 직접 참여(`involved`), 목격(`witness`), 엿듣기(`overheard`)를 구분함. 부모 유형을 포함하는 외래키와 CHECK 제약으로 목격은 Action, 엿듣기는 Dialogue에만 연결하도록 설계함.
   - 기본키로 같은 기록·AI의 중복 관계를 제한함. AI별 검색과 Day·유형·회차 조회를 위한 인덱스를 작성함.
3. A02의 `allowed_roles`를 `game_record_allowed_roles`에 역할별 행으로 저장하도록 설계함.
   - 역할은 prof·grad·std만 허용하며 기록 삭제 시 연결 행을 삭제함. 역할 서열이나 최종 등급 정책은 정의하지 않음. 실제 인가·기본 거부는 서버 조회 흐름에서 구현해야 함.
4. `database/schemas/mariadb/README.md`에 JSON 매핑, 트랜잭션 적재 원칙, 초기화된 볼륨에 대한 수동 적용 필요성을 기록함.
5. DDL 작성 단계이며 실제 MariaDB 실행·제약 동작·JSON 적재·Qdrant 연계는 미검증.
   - 문서 등급·공개 Day·발생 시점·Save별 기록 정책과 채팅 테이블은 미구현. 사용자 테이블 정의는 B02, Save 테이블 정의는 B03에 작성함. ID 일치·AI ID 유효성·Thought 참여자 수·관계 누락 검증 및 적재 도구는 후속 과제임.

# B02 - 유저 테이블

1. `database/schemas/mariadb/002_users.sql`에 로그인·회원가입용 `users` 테이블 정의를 작성함.
2. 합의한 네 필드를 적용함.
   - `user_id`: BIGINT UNSIGNED 자동 증가 기본키.
   - `username`: VARCHAR(50), 필수·고유값. 현재 utf8mb4_unicode_ci 비교 규칙을 사용하므로 대소문자만 다른 아이디는 구분하지 않음. 입력 형식·정규화 규칙은 인증 API에서 후속 협의함.
   - `password_hash`: VARCHAR(255), 필수. 해시 생성 결과 문자열을 보관하며 원문 비밀번호는 저장하지 않음.
   - `created_at`: DATETIME, 기본값 CURRENT_TIMESTAMP. `updated_at`과 역할 필드는 추가하지 않음.
3. 실제 MariaDB 적용과 회원가입·로그인 실행은 미검증. 해시 알고리즘 선택·생성·검증 및 인증 API는 후속 백엔드 작업임.

# B03 - Save 테이블

1. `database/schemas/mariadb/003_saves.sql`에 유저별 게임 진행 상태를 저장하는 `saves` 테이블 정의를 작성함.
2. `save_id`, `user_id`, `slot_no`, `role`, `day`, `created_at`, `last_played_at` 일곱 필드를 적용함.
   - `save_id`는 자동 증가 기본키, `user_id`는 `users.user_id` 외래키임. Save가 남아 있는 사용자의 삭제는 RESTRICT로 제한함.
   - 슬롯은 1~3만 허용하고 `(user_id, slot_no)`를 고유키로 두어 유저당 최대 세 개 Save를 저장하도록 설계함. 빈 슬롯은 행을 만들지 않음.
   - 역할은 prof·grad·std, Day는 1~6만 허용하며 새 Save의 Day 기본값은 1임. 조사 Token 필드는 없음.
   - 생성·마지막 플레이 시각의 기본값은 CURRENT_TIMESTAMP임. 마지막 플레이 시각은 서버가 실제 플레이 시 갱신해야 하며 자동 ON UPDATE는 사용하지 않음.
3. 실제 MariaDB 적용·슬롯 개수 제약·Save/Load API 연동은 미검증.
   - 사용자 소유권 확인, 기존 Save의 역할 고정, 다음 날 버튼의 한 Day씩 진행, 슬롯 덮어쓰기와 연결 데이터 정리는 서버에서 후속 구현해야 함. 채팅·발견 단서 테이블은 아직 작성하지 않음.
