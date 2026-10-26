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

# B06 - MariaDB 적재 도구

1. `database/loaders/load_mariadb.py`에 game-data/test-data 원본을 읽는 Python CLI를 구현함. 접속 전 ID·Day·회차·파일 유형·중복·필수 메타데이터·AI 관계를 검증하며 dry-run을 지원함.
2. 환경변수 또는 명시한 env 파일로 PyMySQL 접속 정보를 구성함. 비밀번호를 로그나 명령행 인자로 노출하지 않으며 선택적으로 TLS CA·서버 호스트명 검증을 지원함.
   - records와 AI·장소·document_permissions 관계를 전체 묶음 단위로 트랜잭션 저장함. 동일 키는 upsert, 연결 행은 교체하며 원본에서 사라진 기록은 자동 삭제하지 않음. 레거시 game_record_allowed_roles 및 사용자·Save·채팅은 변경하지 않음.
3. disclosure_level 누락은 기본 거부(검증 실패)하며 `--default-disclosure`를 명시해야 함. 데이터별 값은 옵션보다 우선함. 예전 test-data의 장소 누락은 `--allow-missing-locations`를 지정할 때만 빈 배열로 처리함.
   - 이 적재 도구는 선택한 기록의 기존 권한을 원본 기준으로 교체함. 운영자 수동 권한을 유지하는 merge 모드는 없으며 역할마다 다른 수준을 가진 원본 형식은 후속 확장 대상임.
4. `008_game_rules.sql`에 공통 game_rules 테이블을 추가함. 실험 record_id와 별도 rule_id로 규칙 본문 JSON과 AI·역할·full/deny 조건을 저장함. 규칙의 권한 검사는 API에서 구현해야 하며 document_permissions를 통한 자동 인가는 아님.
5. 원본 dry-run 결과 game-data 113건과 공통 규칙 1건, test-data 9건 검증 성공함. 게임 데이터의 장소 누락은 0건, 테스트 데이터는 명시적 호환 모드로 9건 처리함.
   - 실행 명령: `python database/loaders/load_mariadb.py --dataset game-data --default-disclosure full --dry-run`, `python database/loaders/load_mariadb.py --dataset test-data --default-disclosure full --allow-missing-locations --dry-run`.
   - `python -m unittest discover -s tests -p test_mariadb_loader.py -v`로 검증 실패·권한 누락·중복 JSON 키/ID·DB child insert 실패 시 rollback 호출·공통 규칙 저장 등 단위 테스트 13개 통과함. 트랜잭션 테스트는 fake connection으로 호출 흐름을 확인한 것이며 실제 DB 실행 검증은 아님.
   - 현재 세션에서 Docker API 접근은 permission denied로 거부됨. 실제 MariaDB 제약·재적재·DB rollback·TLS 접속 및 운영 API 연동은 미검증이고 실제 DB에 적재하지 않음.
6. 의존성은 `database/loaders/requirements.txt`, 준비·실행·배포 환경별 설정과 권한 덮어쓰기 범위는 같은 폴더의 README에 기록함. 기존 DB는 누락된 001~008 스키마를 순서대로 적용한 후 사용해야 함.

# B07 - 역할별 공개 수준 적재와 4단계 이관

1. `database/policies/game_record_permissions.json`에 확정된 18개 조합을 작성함. Action은 std·grad summary/prof full, Incident는 std deny/grad metadata/prof summary이며 Setup·Dialogue·Thought·Result도 확정 표를 반영함.
2. `database/loaders/load_mariadb.py`에서 game-data 적재 시 유형별 표를 기록별 role_permissions로 정규화하고 document_permissions에 세 역할 행을 저장하도록 변경함. game-data의 allowed_roles는 인가에 사용하지 않고 단일 disclosure_level·--default-disclosure는 오류로 처리함.
   - 검수한 원본의 role_permissions 객체는 명시적 예외로 우선하며 생략한 역할은 deny다. 빈 객체는 전부 deny이며, 미등록 역할·제거된 basic_metadata·null·배열·혼합 형식은 거부함. 테스트 데이터에만 기존 allowed_roles+명시적 단일 수준 형식을 유지함. 권한 오류는 DB 쓰기 전에 검증하며 기존 일괄 트랜잭션·rollback 처리는 유지함.
3. 신규 `006_document_permissions.sql`의 CHECK를 네 수준으로 제한하고 `database/migrations/mariadb/001_disclosure_levels_v2.sql`과 실행 안내를 작성함. 기존 basic_metadata 행을 deny로 낮춘 뒤 같은 이름의 CHECK를 한 ALTER 문에서 교체함. 기존 네 수준의 행은 이 SQL만으로 변경하지 않으며, 검수한 원본을 재적재해야 역할 표가 적용됨. DDL의 암묵적 commit과 원본에 없는 기록·수동 예외의 검수 필요성을 명시함.
4. `python -m unittest discover -s tests -p test_mariadb_loader.py -v` 20개 통과함. 18개 확정 조합 및 현재 게임 원본 전체의 권한, 명시적 예외의 누락 역할 거부, 기존 역할 목록·단일 옵션에 의한 덮어쓰기 거부, 잘못된 정책의 쓰기 전 실패, 세 권한 행 전달과 기존 rollback 등을 확인함. DB 호출 테스트는 fake connection을 사용하므로 실제 SQL 실행 검증은 아님.
   - `python database/loaders/load_mariadb.py --dataset game-data --dry-run`: 기록 302건·공통 규칙 1건·권한 906행 검증. grad는 deny 66/full 41/metadata 15/summary 180, prof는 full 221/summary 81, std는 deny 81/full 30/metadata 47/summary 144행임.
   - `python database/loaders/load_mariadb.py --dataset test-data --default-disclosure full --allow-missing-locations --dry-run`: 합성 기록 9건·권한 27행 검증. 두 dry-run 모두 DB에 접속하거나 쓰지 않음.
   - Docker CLI는 Linux 엔진 named pipe를 찾지 못했고 로컬 3306 리스너·MariaDB 실행 파일도 확인되지 않음. 실제 DB 이관·재적재·CHECK 제약·반복 적재 검증은 미수행이며 기존 DB를 변경하지 않음.
5. 적재·스키마·게임 데이터 안내, 정책 문서와 MASTER·PARTS·README·PROJECT_STRUCTURE를 현재 구현에 맞춤. 게임 JSON의 allowed_roles·내용은 이번 B 변경으로 수정하지 않았으며 앞선 A의 summary 변경은 그대로 보존함. Policy Engine·Qdrant 필터·공개 필드 투영·서버 접근 강제는 후속 F/E/I 구현임.
6. 추가 사용자 요청으로 게임 원본의 allowed_roles를 deny가 아닌 역할 목록과 일치시킴. Thought 66건은 prof만, Incident 15건은 prof·grad만 남겼으며 나머지 네 유형은 세 역할을 유지함. Day 1·2·3의 thoughts.json과 Day 1·2·5의 incidents.json, 총 6개 파일의 81개 목록을 수정함.
   - 변경 직전 원본 302건과 비교해 allowed_roles 외 필드·키·기록 순서·건수 및 앞서 수정한 summary가 보존됨을 확인함. 단위 테스트의 전체 게임 원본 검사에 allowed_roles와 역할별 표의 일치 검증을 추가했고 20개 테스트가 통과함. game-data dry-run도 302건·공통 규칙 1건·권한 906행으로 유지됨. 이 목록은 이진 공개 여부만 나타내며 실제 공개 수준의 원천은 역할별 정책과 document_permissions임. 실제 DB 적용은 여전히 미수행임.
