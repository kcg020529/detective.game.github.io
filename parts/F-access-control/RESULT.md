# F01 - 역할별 게임 기록 공개 정책

1. 2026-10-26 `docs/interfaces/역할별_권한_매트릭스.md`에 사용자 확정 공개 표를 작성함. Setup은 모든 역할 full, Thought는 prof summary·나머지 deny이며 Action·Dialogue·Result·Incident는 합의한 표를 유지함. 기존 미확정 L1~L3·release_day 제안과 과거 담당자 표기를 갱신함.
2. 네 공개 수준의 필드 허용 목록을 작성함. 기존 metadata의 공개 범위를 유지하며 basic_metadata는 신규 정책에서 제거함. 기존 basic_metadata 행을 검수 없이 metadata로 변환하면 AI 관계·장소 공개가 확대됨을 명시함.
3. 기록별 역할 권한과 Day·AI 지식 범위·Save 소유권을 함께 확인하도록 기록함. 권한 행 누락 시 표 기반 fallback 없이 거부하고, Qdrant 사전 필터·MariaDB 재검증 후 공개 수준별 필드만 Context에 전달하도록 정의함.
4. MASTER·PARTS·README에 새 정책을 반영하고 DB 계약·적재 안내에는 기존 5단계 구현과의 차이를 표시함. 실제 006 SQL CHECK와 적재 도구 LEVELS는 아직 5단계이며 단일 disclosure_level/allowed_roles 형식이므로 역할별 매트릭스 적재·DB 이관이 필요함. 문서만 수정했으며 정책 엔진·DB 적용·런타임 테스트는 미구현/미검증이다.
5. 사용자 추가 지시에 따라 MASTER와 역할별 권한 매트릭스에서 grad의 Action을 full에서 summary로, Incident를 std deny·grad metadata·prof summary로 변경함. 검증 기준에도 해당 네 조합을 추가함. 정책 문서의 표를 대조했으며 DB 권한 데이터·서버 적용은 미구현이다.
