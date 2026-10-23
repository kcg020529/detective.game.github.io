# B01 - 게임 기록 스키마

1. `database/schemas/mariadb/001_game_records.sql`에 정적 게임 기록용 DDL을 작성함.
   - `game_records`에 A01 공통 필드 중 AI 목록을 제외한 식별·회차·Day·요약·본문을 저장함. `dataset`을 추가하고 `(dataset, record_id)`를 기본키로 사용해 테스트·정식 데이터의 ID 충돌을 방지함.
   - `day`는 해당 날의 실험이 모두 끝난 뒤 질문·조사가 가능해지는 날을 의미함. Day 1 기록은 Save가 Day 1일 때부터 조회 대상이 되므로 별도 공개 Day 필드는 두지 않음.
   - 이전 Day의 기록도 누적 조회하므로 서버는 `game_records.day <= saves.day` 조건을 적용해야 함. 이 조건을 통과해도 문서·역할별 공개 수준과 선택 AI의 지식 범위를 함께 확인해야 함.
2. AI 배열을 `game_record_ai`로 분리함.
   - `relation_kind`로 직접 참여(`involved`), 목격(`witness`), 엿듣기(`overheard`)를 구분함. 부모 유형을 포함하는 외래키와 CHECK 제약으로 목격은 Action, 엿듣기는 Dialogue에만 연결하도록 설계함.
   - 기본키로 같은 기록·AI의 중복 관계를 제한함. AI별 검색과 Day·유형·회차 조회를 위한 인덱스를 작성함.
3. A02의 `allowed_roles`를 `game_record_allowed_roles`에 역할별 행으로 저장하도록 설계함.
   - 역할은 prof·grad·std만 허용하며 기록 삭제 시 연결 행을 삭제함. 역할 서열이나 최종 등급 정책은 정의하지 않음. 실제 인가·기본 거부는 서버 조회 흐름에서 구현해야 함.
4. `database/schemas/mariadb/README.md`에 JSON 매핑, 트랜잭션 적재 원칙, 초기화된 볼륨에 대한 수동 적용 필요성을 기록함.
5. DDL 작성 단계이며 실제 MariaDB 실행·제약 동작·JSON 적재·Qdrant 연계는 미검증.
   - 문서 등급·발생 시점·Save별 기록 정책은 후속 검토 대상임. 별도 공개 Day는 사용하지 않음. 사용자 테이블 정의는 B02, Save 테이블 정의는 B03, 채팅 테이블 정의는 B04에 작성함. ID 일치·AI ID 유효성·Thought 참여자 수·관계 누락 검증 및 적재 도구는 후속 과제임.

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
   - 사용자 소유권 확인, 기존 Save의 역할 고정, 다음 날 버튼의 한 Day씩 진행, 슬롯 덮어쓰기와 연결 데이터 정리는 서버에서 후속 구현해야 함. 채팅 테이블은 B04에서 작성했으며 발견 단서 테이블은 미작성.

# B04 - 대화 및 권한 테이블

1. `database/schemas/mariadb/004_chat_messages.sql`에 대화 이력 DDL을 작성함.
   - 사용자 질문과 AI 답변을 별도 행으로 저장하며 Save 외래키와 `(save_id, ai_id, message_id)` 인덱스를 둠. 사용자 메시지의 response_type은 NULL, AI 메시지는 normal·partial·restricted·unknown만 허용함. Save 삭제 시 연결 이력도 삭제하도록 정의함.
2. `005_user_roles.sql`에 계정별 허용 역할 DDL을 작성함.
   - `(user_id, role)` 기본키, 사용자 외래키와 prof·grad·std CHECK를 정의함. 초기 역할은 자동 부여하지 않음. Save 생성·재개·인가 시 현재 계정의 허용 역할을 서버가 확인해야 하며 역할 회수 처리도 후속 구현 대상임.
3. `006_document_permissions.sql`에 문서·역할별 공개 수준 DDL을 작성함.
   - `(dataset, record_id, role)` 기본키와 게임 기록 외래키를 정의함. 공개 수준은 full·summary·metadata·basic_metadata·deny 중 하나로 제한함. 행 누락은 서버에서 기본 거부해야 함.
4. `database/schemas/mariadb/permissions.md`에 공개 필드, 유형별 관찰자 배열, 현재 권한에 따른 이력 처리 및 레거시 권한 목록 대체 방식을 기록함.
   - 문서 역할 권한의 판정 원천은 document_permissions로 정함. 기존 game_record_allowed_roles는 삭제하지 않고 레거시로 표시했으며 인가 fallback으로 사용하지 않도록 명시함.
   - 기존 JSON allowed_roles에서 5단계 수준을 자동 추론하지 않음. 공개 수준 지정 및 기존 권한 이관은 후속 작업임.
5. SQL·문서 작성 완료. 실제 MariaDB 실행·제약 동작 및 대화/권한 API 연동은 미검증이며, 권한 데이터·적재·이관 도구는 미구현.

# B05 - 장소 메타데이터

1. `database/schemas/mariadb/007_record_locations.sql`에 locations와 game_record_locations를 정의함.
   - 현재 JSON과 동일하게 일곱 장소 이름을 location_id로 사용해 초기 등록함. 기록의 dataset·record_id와 장소 외래키, 중복 방지 기본키 및 장소별 검색 인덱스를 둠.
   - 기록 삭제 시 장소 연결만 삭제하며 참조 중인 장소 삭제는 제한함. 빈 location_ids는 연결 행 없음으로 표현함.
2. 스키마 README에 data/ 원본 경로와 목록의 행 변환을 기록함. Setup의 장소 목록은 실험 장소 전체이며 AI별 초기 배치는 content에 유지함.
   - permissions.md에서 장소 목록은 metadata 이상에 포함하고 basic_metadata는 기존 네 필드를 유지하도록 명시함. AI별 초기 위치 본문은 full에서만 제공함.
3. SQL·안내 작성 완료이며 실제 DB 적용·JSON 적재·외래키 실행 검증은 미수행. 기존 초기화 DB에는 001~006 이후 007을 별도 적용해야 하며 볼륨 삭제는 필요하지 않음. 예전 테스트 원본의 location_ids 보완과 적재 도구는 후속 작업임.
