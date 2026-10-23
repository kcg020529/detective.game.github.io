# MariaDB 테스트 데이터 픽스처

- `records.json`은 Day 1~3의 실험 회차 1~3을 대상으로 한 합성 데이터다.
- 각 회차에 `Dialogue`, `Action`, `Result` 한 건씩, 총 9건이 있다.
- 공통 필드는 A 파트에서 정한 `record_id`, `record_type`, `test_id`, `day`, `involved_ai`, `summary`, `content`를 사용한다.
- `Dialogue`에는 `overheard_ai`, `Action`에는 `witness_ai`를 유형별 필드로 둔다.
- 각 `Result` 본문에는 YB-1~YB-6의 획득 점수를 기록하고, `involved_ai`에는 점수가 포함된 6개 AI를 모두 둔다.
- `allowed_roles`는 이 픽스처에서 역할별 필터 동작을 확인하기 위한 테스트 전용 접근 조건이다. 역할별 실제 보안 등급 매트릭스나 운영 정책을 확정하는 값이 아니다.
- Day 필터는 현재 플레이어 Day보다 뒤의 기록을 숨기는지 확인하는 용도다. Save 범위와 접근제어 등급은 아직 포함하지 않는다.
- YB-1~YB-6은 테스트용 캐릭터 ID이며, 운영 데이터 계약 확정 시 기준 ID와 맞춘다.

현재 MariaDB 스키마와 적재 도구가 없으므로 이 JSON은 적재 전 원본 픽스처다.
