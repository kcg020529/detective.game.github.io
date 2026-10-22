# MariaDB 초기 SQL

이 폴더의 `.sql` 파일은 MariaDB 데이터 볼륨이 비어 있는 첫 실행 때 파일명 순서대로 자동 실행됨.

`001_game_records.sql`은 B01에서 작성한 정적 게임 기록 스키마다. 아직 실제 MariaDB에서 실행 검증하지 않았다.

| 테이블 | 저장 내용 |
|---|---|
| `game_records` | 공통 필드 `record_id`, `record_type`, `test_id`, `day`, `summary`, `content`와 데이터셋 구분 |
| `game_record_ai` | `involved_ai`, `witness_ai`, `overheard_ai` 배열을 AI별 관계 행으로 저장 |
| `game_record_allowed_roles` | 테스트 픽스처의 `allowed_roles`를 역할별 행으로 저장 |
| `users` | `002_users.sql`: 로그인·회원가입용 계정 ID, 로그인 아이디, 비밀번호 해시, 가입 시각 |
| `saves` | `003_saves.sql`: 사용자별 최대 세 개 슬롯, 역할·현재 Day·생성·마지막 플레이 시각 |

`users`는 `user_id`, `username`, `password_hash`, `created_at` 네 필드로 구성한다. `username`은 최대 50자이고 고유값이며 현재 테이블 비교 규칙상 대소문자를 구분하지 않는다. 비밀번호 해시 생성·검증은 인증 API에서 처리한다. 이 SQL도 아직 실제 MariaDB에서 실행 검증하지 않았다.

## JSON 원본과의 대응

- 원본 경로에 따라 `dataset`에 `test-data` 또는 `game-data`를 넣는다. 모든 연결과 조회에 `dataset`과 `record_id`를 함께 사용한다. Qdrant에서도 같은 두 값으로 원본을 식별해야 한다.
- `record_type`은 `Setup`, `Action`, `Dialogue`, `Thought`, `Result`, `Incident`의 대소문자를 그대로 저장한다.
- AI 배열은 `game_record_ai`에 원소당 한 행으로 넣는다. `relation_kind`는 각각 `involved`, `witness`, `overheard`다. 빈 배열이면 해당 관계 행이 없다.
- 관계 테이블의 `record_type`은 부모와 일치하는지 외래키로 확인하기 위한 값이다. CHECK 제약으로 Action만 witness, Dialogue만 overheard를 가질 수 있다.
- 같은 기록에서 동일 AI가 직접 참여자이면서 관찰자로 중복 등록되지 않도록 기본키를 둔다.
- `allowed_roles`도 역할당 한 행으로 넣는다. 역할 행이 없으면 허용 대상이 없는 것으로 처리해야 한다. SQL 테이블 자체가 서비스의 인가를 수행하는 것은 아니므로 조회 시 역할·Day·AI 범위 조건을 서버가 강제해야 한다.
- 기록 본문과 관계·허용 역할은 하나의 트랜잭션으로 적재한다. JSON 적재 도구는 아직 없다.

## 설계 범위와 남은 작업

현재는 A에서 합의한 정적 기록과 테스트용 역할 목록, 로그인·회원가입용 사용자 계정 및 유저별 Save의 저장 구조다. 채팅·발견 단서·실서비스 감사 로그는 후속 스키마 대상이다. 문서 등급, 공개 Day, 발생 순서·시각 및 Save별 기록 정책도 MASTER 요구사항에 따라 추가 설계해야 한다.

`saves`는 `users` 생성 후 적용한다. `slot_no`의 1~3 범위와 사용자·슬롯 고유키로 유저당 Save를 최대 세 개로 제한한다. 빈 슬롯은 행이 없다. 역할은 Save에 저장하며 조사 Token은 저장하지 않는다. `last_played_at` 갱신, Save 소유권 검사, 역할 고정, Day를 한 단계씩 진행하는 처리는 서버 책임이다. Day는 1~6 범위만 DB에서 제한한다. 실제 DB 적용은 아직 미검증이다.

`test_id`는 1~30, `day`는 1~6이다. 테스트 데이터는 하루 1회이므로 DB에 하루 5회 관계를 강제하지 않았다. 정식 데이터의 Day별 5회 규칙, ID 형식과 필드의 일치, Thought의 참여 AI 한 명 제한, AI ID 유효성 및 필수 관계 누락은 후속 적재 검증에서 확인해야 한다.

Docker의 첫 실행은 `.env`의 `MARIADB_DATABASE`에 이 SQL을 적용한다. 이미 초기화된 볼륨에는 새 SQL이 자동 적용되지 않는다. 기존 DB에는 선택한 데이터베이스에서 이 파일을 한 번 실행해야 하며, 재실행용 마이그레이션은 아직 없다. 기존 데이터를 삭제할 필요는 없다.
