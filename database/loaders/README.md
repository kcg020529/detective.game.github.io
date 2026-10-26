# MariaDB JSON 적재

> 2026-10-26 [역할별 공개 정책](../../docs/interfaces/역할별_권한_매트릭스.md)의 4단계와 역할별 매트릭스 적재를 구현했다. game-data에는 합의한 정책 파일을 사용하며 `--default-disclosure`를 허용하지 않는다. 실제 DB 이관·적재 실행은 별도로 수행해야 한다.

저장소 루트에서 실행한다. Docker·K8s·AWS에서 같은 Python 도구를 사용하고 접속 정보만 바꾼다. Python 3.10 이상이 필요하다.

```bash
python -m pip install -r database/loaders/requirements.txt
```

## 먼저 스키마 준비

`database/schemas/mariadb/001`~`008` SQL을 파일명 순으로 대상 DB에 적용해야 한다. 새 Docker 볼륨은 첫 실행 시 자동 적용한다. 이미 초기화한 DB는 누락된 SQL을 DB 클라이언트에서 직접 실행한다. 볼륨을 삭제할 필요는 없다. 적재 도구는 테이블을 생성·변경하지 않는다.

기존 5단계 DB는 먼저 [이관 안내](../migrations/README.md)를 따라 `001_disclosure_levels_v2.sql`을 적용한다. 기존 `basic_metadata`는 `deny`로 낮추며 공개 범위를 자동 확대하지 않는다. 이후 검수한 원본을 재적재해 역할별 표를 적용한다.

## DB 변경 없이 검증

```bash
python database/loaders/load_mariadb.py --dataset game-data --dry-run
python database/loaders/load_mariadb.py --dataset test-data --default-disclosure full --allow-missing-locations --dry-run
```

game-data는 `database/policies/game_record_permissions.json`의 여섯 기록 종류 × 세 역할 표로 권한을 생성한다. `allowed_roles`는 이 경로에서 권한 근거로 사용하지 않는다. 단일 `disclosure_level`이나 `--default-disclosure`를 지정하면 모호한 정책 덮어쓰기를 막기 위해 오류로 종료한다. 원본 JSON을 일괄 수정할 필요는 없다.

기록별 예외는 검수한 원본에 `"role_permissions": {"std": "deny", "grad": "metadata", "prof": "summary"}`처럼 명시할 수 있다. 이 객체가 있으면 유형별 표보다 우선하며 빠진 역할은 `deny`로 처리한다. `{}`는 전 역할 거부다. 미등록 역할·잘못된 수준·null·배열은 거부하고 단일 `disclosure_level`과 혼용하지 않는다. 허용 수준은 full·summary·metadata·deny뿐이다.

test-data도 `role_permissions`를 지원한다. 예전 합성 픽스처만 `allowed_roles`와 명시적 `disclosure_level` 또는 `--default-disclosure` 형식을 유지한다. 이때도 목록에 없는 역할은 `deny`이며 자동 full 매핑은 없다. 위 테스트 예시의 `--default-disclosure full`은 합성 픽스처에만 적용하는 명시적 선택이다.

모든 기록은 거부 역할을 포함해 세 개의 권한 행을 저장한다. 출력되는 역할·수준별 건수로 공개 범위를 확인할 수 있다. 런타임에서는 권한 행 누락이 거부이며 JSON이나 유형별 표를 fallback으로 사용하지 않는다.

예전 test-data 9건에는 location_ids가 없어 기본 실행은 실패한다. `--allow-missing-locations`는 누락을 빈 배열로 저장하는 명시적 호환 모드이며, 장소를 추론하지 않는다. game-data에는 이 옵션이 필요 없다.

## 실제 적재

Docker용 `.env`는 사용자가 준비한 `infrastructure/docker/.env`를 지정할 수 있다. 도구는 그 파일을 자동 생성하지 않는다.

```bash
python database/loaders/load_mariadb.py --dataset game-data --env-file infrastructure/docker/.env
python database/loaders/load_mariadb.py --dataset test-data --default-disclosure full --allow-missing-locations --env-file infrastructure/docker/.env
```

환경변수는 파일 값보다 우선한다.

| 변수 | 값 |
|---|---|
| MARIADB_HOST | DB 호스트, 기본 127.0.0.1 |
| MARIADB_PORT | DB 포트, 기본 3306 |
| MARIADB_DATABASE | 필수, Docker 예시 kervion |
| MARIADB_USER | 필수, Docker 예시 kervion |
| MARIADB_PASSWORD | 필수, 비밀번호를 명령행 인자로 전달하지 않음 |
| MARIADB_SSL_CA | 선택, TLS 인증기관 파일. 지정하면 인증서와 호스트명 검증 |

K8s에서는 Service 주소, AWS에서는 DB 엔드포인트를 MARIADB_HOST로 지정하고 Secret 등으로 환경변수를 전달한다. Python 프로세스가 Docker 컨테이너 안에 있으면 호스트를 mariadb, 포트를 컨테이너 내부 포트 3306으로 지정한다. 호스트의 공개 포트와 혼동하지 않는다.

env 파일은 단순 KEY=VALUE 형식과 값 전체를 감싼 따옴표만 지원한다. 셸 명령·변수 확장·값 뒤 주석은 처리하지 않는다. 인증정보는 Git에 저장하지 않는다.

## 적재 동작

- 기본 원본은 스크립트 위치 기준 `data/<dataset>`이다. 다른 원본은 `--source <데이터셋 디렉터리>`로 지정한다.
- game-data는 experiments/day_01~day_06의 여섯 유형 JSON 배열, test-data는 하위 JSON 배열을 읽는다. game-data/rules.json은 별도 공통 규칙으로 읽는다. 캐릭터·지도 파일은 실험 기록으로 읽지 않는다.
- ID·Day·회차·유형·AI·역할·장소·중복·관계 필드를 DB 접속 전에 검사한다. 빈 배열은 미작성 파일로 허용한다. 점수 계산·서사 시간선 검증은 이 도구의 범위가 아니다.
- game_records에 본문을 upsert하고 AI·장소·document_permissions 연결 행을 교체한다. game_record_allowed_roles는 읽거나 쓰지 않는다.
- 선택한 원본의 기존 수동 권한도 교체하므로, 유지할 예외는 재적재 전에 원본의 role_permissions로 명시한다. 원본에 없는 기존 DB 기록의 권한은 변경하지 않는다.
- 공통 규칙은 `008_game_rules.sql`의 game_rules에 저장한다. rule_id와 실험 record_id를 혼용하지 않는다. 규칙 본문은 JSON이며 관련 AI·허용 역할·full/deny는 별도 컬럼이다. 공통 규칙 API는 이 권한 컬럼을 직접 확인해야 한다. 아직 API 연동은 없다.
- 전체 선택 데이터셋을 한 트랜잭션으로 저장하고 오류 발생 시 전체 rollback한다. 같은 키 재실행은 행을 추가 중복 생성하지 않는다. 원본에서 사라진 기록을 DB에서 자동 삭제하지 않는다.
- 적재 중 같은 데이터셋을 다른 프로세스에서 동시에 수정하지 않는다. 동일 키를 가진 기존 DB 기록은 덮어쓰므로 실행 대상과 공개 수준을 확인한다. 사용자·Save·채팅 데이터는 건드리지 않는다.

## 테스트

```bash
python -m unittest discover -s tests -p test_mariadb_loader.py -v
```

단위 테스트와 dry-run은 실제 DB 제약·재적재 동작을 검증하지 않는다. 실제 MariaDB 적용·rollback·반복 적재 확인은 DB 접근이 가능한 환경에서 별도로 수행해야 한다.
