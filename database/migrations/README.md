# 기존 MariaDB 공개 수준 이관

새 DB는 `database/schemas/mariadb/006_document_permissions.sql`의 4단계 CHECK를 사용한다. 이미 초기화한 DB는 초기 SQL을 편집해도 변경되지 않으므로 다음 순서로 이관한다. 이 절차는 계정·Save·대화를 삭제하지 않는다.

1. 대상 DB를 백업하고 콘텐츠 적재·권한 쓰기·서비스 접근을 일시 중단한다. 기존 수동 권한 예외를 유지하려면 검수 후 원본의 role_permissions에 옮겨 둔다.
2. 저장소 루트에서 DB 클라이언트에 접속한다. 비밀번호는 `-p`의 프롬프트로 입력하고 명령행에 넣지 않는다. 예: `mariadb --host=127.0.0.1 --user=kervion -p kervion`.
3. 클라이언트에서 `SOURCE database/migrations/mariadb/001_disclosure_levels_v2.sql;`을 실행한다. 첫 조회는 기존 basic_metadata 행 수를 보여주며 이어서 그 행을 deny로 변경하고 4단계 CHECK로 교체한다. 대상 테이블의 ALTER 권한이 필요하다.
4. 마이그레이션은 기존 네 수준 행을 유지한다. 합의한 유형별·역할별 표를 적용하려면 dry-run 결과와 원본 예외를 검수한 뒤 `python database/loaders/load_mariadb.py --dataset game-data --env-file infrastructure/docker/.env`로 재적재한다. 원본에 없는 DB 기록은 자동 변경하지 않으므로 별도 검수한다.
5. 기록 수와 권한 수(기록당 세 행), 역할별 공개 수준, 필요한 수동 예외를 조회하고 서비스를 재개한다. 실제 접근 강제에는 F/E의 후속 연동이 필요하다.

기존 basic_metadata는 메타데이터의 일부만 공개했으므로 metadata로 승격하지 않는다. deny로 내려간 합성 테스트 기록은 검수한 role_permissions 등으로 별도 재적재할 수 있다. 신규 역할 표를 적용하는 것은 공개 범위 변경이므로 기존 데이터에 무조건 자동 실행하지 않는다.

MariaDB의 [ALTER TABLE](https://mariadb.com/docs/server/reference/sql-statements/data-definition/alter/alter-table)은 [암묵적 COMMIT](https://mariadb.com/docs/server/reference/sql-statements/transactions/sql-statements-that-cause-an-implicit-commit)을 수행한다. 이관 SQL의 UPDATE 트랜잭션과 DDL 전체를 하나의 rollback 단위로 가정하지 않는다. 중간에 실패하면 서비스를 중단한 상태로 대상 제약·행 값을 확인하고 다시 실행한다. 같은 이름의 CHECK를 교체하므로 정상 완료 후에도 재실행할 수 있다.

현재 세션에서는 Docker 엔진과 로컬 MariaDB에 연결할 수 없어 이관 SQL의 실제 실행은 미검증이다.
