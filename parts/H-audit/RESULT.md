# H01 - Input Guard 감사 이벤트 저장 구조 (선영)

- `database/schemas/mariadb/012_audit_events.sql`에 메타데이터 전용 `audit_events` 테이블을 작성했다.
- `backend/audit/store.py`에 Input Guard 경고 이벤트의 필드·값을 검증하고 현재 DB 트랜잭션에 저장하는 함수를 작성했다. 질문 원문 등 임의 필드가 들어오면 저장 전에 거부한다.
- 실제 채팅 요청에서는 아직 호출하지 않는다. O Grafana와 정책·검색·출력 이벤트도 미연결이다.
- 2026-10-25 로컬 MariaDB 기존 볼륨에 `012_audit_events.sql`을 별도 적용했다. 임시 계정·Save로 `warn` 경고 저장·조회, 질문 원문 필드 거부, 원문·답변 컬럼 부재를 확인했다. `high_risk` 이벤트를 만든 뒤 Save·계정을 삭제해 두 외래키가 `NULL`로 바뀌는 것도 확인했다. 임시 행은 모두 삭제했다. 공유 DB 적용은 확인하지 않았다.
- `tests/audit/test_store.py`의 저장 메타데이터·원문 거부·판정 불일치 거부·`allow` 미저장 검사 3개와 기존 Input Guard 검사 4개가 통과했다.
- DeepSeek 추가 판정의 `deepseek_warn`·`deepseek_high_risk` 신호 코드를 저장 함수의 허용 목록에 반영했다. 모의 모델 판정으로 생성한 이벤트가 질문 원문 없이 저장 매개변수로 전달되는지 검사했다. 실제 채팅 요청에서 자동 저장되는 상태는 아니다.

## H02 - Output Guard 감사 이벤트 자동 저장 (2026-10-28, 선영 작업 브랜치)

- `save_output_guard_alert()`와 `record_output_guard_result()`를 추가했다. 출력 검사의 신호·decision·applied·mode·점수와 사용자·Save·캐릭터 식별자만 기존 `audit_events`에 저장한다. 질문·답변·비밀값은 저장하지 않는다.
- 채팅의 Save 행 잠금 중 별도 DB 연결로 감사 이벤트를 INSERT하면 외래키 잠금 대기가 발생했다. 같은 채팅 DB 연결에서 저장하도록 수정했다. 성공 답변은 채팅과 함께 commit하고, 검사 결과를 기록한 뒤 503으로 끝나는 경우에는 감사 이벤트만 commit한다.
- 임시 계정·Save의 실제 MariaDB에서 normal·restricted·partial 답변을 각각 한 건씩 보내 채팅 6줄과 출력 감사 이벤트 2건을 확인했다. 임시 데이터는 삭제했다.
