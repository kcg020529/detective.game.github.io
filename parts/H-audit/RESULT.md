# H01 - Input Guard 감사 이벤트 저장 구조 (선영)

- `database/schemas/mariadb/012_audit_events.sql`에 메타데이터 전용 `audit_events` 테이블을 작성했다.
- `backend/audit/store.py`에 Input Guard 경고 이벤트의 필드·값을 검증하고 현재 DB 트랜잭션에 저장하는 함수를 작성했다. 질문 원문 등 임의 필드가 들어오면 저장 전에 거부한다.
- 실제 채팅 요청에서는 아직 호출하지 않는다. O Grafana와 정책·검색·출력 이벤트도 미연결이다.
- 2026-10-25 로컬 MariaDB 기존 볼륨에 `012_audit_events.sql`을 별도 적용했다. 임시 계정·Save로 `warn` 경고 저장·조회, 질문 원문 필드 거부, 원문·답변 컬럼 부재를 확인했다. `high_risk` 이벤트를 만든 뒤 Save·계정을 삭제해 두 외래키가 `NULL`로 바뀌는 것도 확인했다. 임시 행은 모두 삭제했다. 공유 DB 적용은 확인하지 않았다.
- `tests/audit/test_store.py`의 저장 메타데이터·원문 거부·판정 불일치 거부·`allow` 미저장 검사 3개와 기존 Input Guard 검사 4개가 통과했다.
- DeepSeek 추가 판정의 `deepseek_warn`·`deepseek_high_risk` 신호 코드를 저장 함수의 허용 목록에 반영했다. 모의 모델 판정으로 생성한 이벤트가 질문 원문 없이 저장 매개변수로 전달되는지 검사했다. 실제 채팅 요청에서 자동 저장되는 상태는 아니다.
