# MariaDB 초기 SQL

이 폴더의 `.sql` 파일은 MariaDB 데이터 볼륨이 비어 있는 첫 실행 때 파일명 순서대로 자동 실행됨.

`001_game_records.sql`은 B01에서 작성한 정적 게임 기록 스키마다. 아직 실제 MariaDB에서 실행 검증하지 않았다.

| 테이블 | 저장 내용 |
|---|---|
| `game_records` | 공통 필드 `record_id`, `record_type`, `test_id`, `day`, `summary`, `content`와 데이터셋 구분 |
| `game_record_ai` | `involved_ai`, `witness_ai`, `overheard_ai` 배열을 AI별 관계 행으로 저장 |
| `game_record_allowed_roles` | 초기 픽스처용 레거시 목록. 인가에 사용하지 않음 |
| `users` | `002_users.sql`: 로그인·회원가입용 계정 ID, 로그인 아이디, 비밀번호 해시, 가입 시각 |
| `saves` | `003_saves.sql`: 사용자별 최대 세 개 슬롯, 역할·현재 Day·생성·마지막 플레이 시각 |
| `chat_messages` | `004_chat_messages.sql`: Save·AI별 사용자/AI 메시지 이력 |
| `user_roles` | `005_user_roles.sql`: 기존 계정·역할 관계. 새 게임의 선택 가능 역할을 제한하는 인가 목록으로 사용하지 않음 |
| `document_permissions` | `006_document_permissions.sql`: 문서·역할별 4단계 공개 수준 |
| `locations` | `007_record_locations.sql`: 중앙홀·회의실·기록실·전력실·통신실·창고·서버실 |
| `game_record_locations` | 기록별 location_ids 목록의 관계 행 |
| `game_rules` | `008_game_rules.sql`: 공통 규칙 본문 JSON 및 AI·역할·원문 공개 조건 |
| `save_memos` | `009_save_memos.sql`: Save별 플레이어 메모 1개 (최대 5000자) |
| `request_log` | `010_request_log.sql`: 같은 요청을 다시 보냈을 때 처음 응답을 돌려주기 위한 기록 (Day 진행 등) |
| `auth_sessions` | `011_auth_sessions.sql`: 로그인 쿠키 해시·사용자·만료 시각 |
| `audit_events` | `012_audit_events.sql`: Input·Output Guard의 시각·요청·판정·신호·Save 메타데이터 저장 (H) |

세 테이블의 상세 계약과 공개 범위는 [permissions.md](permissions.md)에 있다. SQL은 파일명 순서로 적용한다. 2026-10-23 격리된 MariaDB 테스트 컨테이너에서 초기 적용을 확인했으나, 모든 제약·적재 결과와 공유 DB 적용은 검증하지 않았다.

기존 5단계 DB에는 [기존 DB 이관](../../migrations/README.md)을 먼저 수행한다. 신규 초기 SQL을 수정해도 기존 Docker 볼륨에는 자동 적용되지 않는다. 게임 권한 표는 `database/policies/game_record_permissions.json`이며 적재 도구가 각 기록의 세 역할 권한을 생성한다.

`users`는 `user_id`, `username`, `password_hash`, `created_at` 네 필드로 구성한다. `username`은 최대 50자이고 고유값이며 현재 테이블 비교 규칙상 대소문자를 구분하지 않는다. 비밀번호 해시 생성·검증은 인증 API에서 처리한다. 선영의 로컬 MariaDB에서 가입·중복 아이디·해시 저장을 확인했으며 공유 DB 적용은 미검증이다.

## JSON 원본과의 대응

- 원본 경로에 따라 `dataset`에 `test-data` 또는 `game-data`를 넣는다. 모든 연결과 조회에 `dataset`과 `record_id`를 함께 사용한다. Qdrant에서도 같은 두 값으로 원본을 식별해야 한다.
- `record_type`은 `Setup`, `Action`, `Dialogue`, `Thought`, `Result`, `Incident`의 대소문자를 그대로 저장한다.
- AI 배열은 `game_record_ai`에 원소당 한 행으로 넣는다. `relation_kind`는 각각 `involved`, `witness`, `overheard`다. 빈 배열이면 해당 관계 행이 없다.
- 관계 테이블의 `record_type`은 부모와 일치하는지 외래키로 확인하기 위한 값이다. CHECK 제약으로 Action만 witness, Dialogue만 overheard를 가질 수 있다.
- 같은 기록에서 동일 AI가 직접 참여자이면서 관찰자로 중복 등록되지 않도록 기본키를 둔다.
- 테스트 JSON의 `allowed_roles`는 초기 이진 허용 목록이다. 현재 권한은 `document_permissions`에 공개 수준을 명시하여 저장하며 기존 목록을 자동으로 full에 매핑하지 않는다. game_record_allowed_roles를 인가 fallback으로 사용하지 않는다. 실제 조회의 역할·Day·AI 범위 조건은 서버가 강제해야 한다.
- 기록 본문과 관계·허용 역할은 하나의 트랜잭션으로 적재한다. 실행 방법은 [적재 도구 안내](../../loaders/README.md)를 따른다.
- 콘텐츠 원본은 `data/test-data/records.json`과 `data/game-data/experiments/day_01/`~`day_06/`의 유형별 JSON에서 읽는다. DB별 원본 사본은 만들지 않는다.
- `location_ids`는 원소당 `game_record_locations` 한 행으로 저장한다. 현재 JSON의 장소 이름을 location_id 값으로 그대로 사용하며 영문 코드로 임의 변환하지 않는다. 일곱 장소는 `locations`에 초기 등록한다.
- Setup의 장소 관계는 실험에 사용하는 장소 전체를 뜻한다. AI별 초기 위치와 이동 순서는 content에 유지하며 장소 관계 테이블이 AI 배치나 경로를 뜻하지 않는다. 장소와 관계없는 기록의 빈 목록은 연결 행이 없는 상태로 표현한다.
- 현재 예전 테스트 JSON에는 location_ids가 없다. 적재 도구에서 누락과 명시적 빈 배열을 구분하고 원본을 보완해야 하며, 본문에서 위치를 임의 추론하지 않는다.

## 설계 범위와 남은 작업

현재 정적 기록·장소 관계, 사용자·Save·채팅, 기존 계정·역할 관계 및 문서 공개 수준의 저장 구조를 정의했다. 새 게임마다 역할을 자유롭게 선택하고 해당 Save 안에서는 고정하며 계정별 역할 목록으로 선택을 제한하지 않는다. 발견 단서는 후속 스키마 대상이다. 감사 로그는 Input Guard 경고 메타데이터의 첫 저장 구조만 정의했으며 정책·검색·출력 이벤트의 상세 계약과 실제 요청 흐름 연결은 후속 작업이다. 문서 등급, 발생 순서·시각 및 Save별 기록 정책은 후속 검토 대상이다. day는 해당 실험 종료 후 조사 가능한 날이며 별도 공개 Day 없이 기록.day <= Save.day로 누적 조회한다.

`saves`는 `users` 생성 후 적용한다. `slot_no`의 1~3 범위와 사용자·슬롯 고유키로 유저당 Save를 최대 세 개로 제한한다. 빈 슬롯은 행이 없다. 역할은 Save에 저장하며 조사 Token은 저장하지 않는다. `last_played_at` 갱신, Save 소유권 검사, 역할 고정, Day를 한 단계씩 진행하는 처리는 서버 책임이다. Day는 1~6 범위만 DB에서 제한한다. 실제 DB 적용은 아직 미검증이다.

`test_id`는 1~30, `day`는 1~6이다. 테스트 데이터는 하루 1회이므로 DB에 하루 5회 관계를 강제하지 않았다. 정식 데이터의 Day별 5회 규칙, ID 형식과 필드의 일치, Thought의 참여 AI 한 명 제한, AI ID 유효성 및 필수 관계 누락은 후속 적재 검증에서 확인해야 한다.

Docker의 첫 실행은 `.env`의 `MARIADB_DATABASE`에 이 SQL을 적용한다. 이미 초기화된 볼륨에는 새 SQL이 자동 적용되지 않는다. 기존 DB에는 필요한 신규 SQL을 별도로 적용해야 한다. 공개 수준의 5단계 → 4단계 변경은 위의 별도 이관 절차를 따른다. 기존 데이터를 삭제할 필요는 없다.

`011_auth_sessions.sql`은 I 백엔드의 세션 저장용이다. 기존 DB에는 이 파일만
별도로 적용한다. 2026-10-23에 격리된 MariaDB 11.4 테스트 컨테이너에서
001~007과 세션 SQL의 초기 적용, 계정 API의 세션 생성·조회·삭제를 확인했다.
공유 서버나 기존 볼륨에 적용된 상태를 뜻하지 않는다.

`012_audit_events.sql`은 H의 Input Guard 경고 저장용이다. 기존 DB에는 이 파일을
별도로 적용한다. `warn`·`high_risk`만 저장하며 질문·답변·비밀번호·쿠키·API 키
원문 컬럼은 없다. Save 또는 계정이 삭제되면 해당 외래키는 `NULL`이 되고 사건
메타데이터는 남는다. 보존 기간·조회 권한·다른 모듈의 이벤트 형식은 팀 계약 후
확정한다. `backend.audit.store.save_input_guard_alert`의 호출자가 트랜잭션을
커밋하거나 롤백한다. 현재 채팅 전송 API에서 자동 호출하지 않는다.
