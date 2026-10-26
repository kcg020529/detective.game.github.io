# F01 - 역할별 게임 기록 공개 정책

1. 여섯 기록 종류 × 세 역할의 공개 수준을 사용자 합의에 따라 문서화한다.
   - 추가 확정: grad의 Action은 summary, Incident는 std deny·grad metadata·prof summary로 적용한다.
2. `deny`, `metadata`, `summary`, `full`의 허용 필드와 기존 `basic_metadata` 처리 방침을 정리한다.
3. Day·AI 지식 범위·Save 소유권과 검색 전 ACL·원본 재검증·필드 투영의 적용 경계를 명시한다.
4. 기존 SQL·적재 도구와의 차이를 기록하고 MASTER·PARTS·README의 정책 기준을 맞춘다.
5. 후속 구현: B와 역할별 권한 적재·DB 이관을 맞추고, F의 판정 및 E의 ACL·원본 재검증·Context 투영을 구현·검증한다. 현재 문서 작성 범위에서는 서버·DB를 변경하지 않는다.

# F02 - Policy Engine과 MariaDB 인가 어댑터

1. 서버 상태의 역할·Day·Save 소유권·선택 AI와 DB의 정확한 기록별 권한 행으로 순수 인가를 구현한다. 누락·미등록 값·다른 데이터셋/역할 권한 행은 거부한다.
2. 공개 수준별 필드 투영을 구현한다. Action의 참여자·목격자, Dialogue의 참여자·엿들은 AI, Thought 소유자와 Setup·Result의 명시된 관련 AI 관계를 확인한다. Incident는 사용자 결정대로 관련 involved_ai만 허용한다.
3. MariaDB에서 검증된 Save 상태를 조회하고, 요약·본문 없이 검색 전 허용 키/공개 수준을 산정한다. 검색 후에는 원본·권한·관계를 재확인하고 공개 수준에 필요한 텍스트 컬럼만 조회한다.
4. 정책 오류·DB 장애 시 넓은 fallback 없이 실패하도록 하고, E/I가 사용할 내부 호출 계약과 현재 임시 인증의 한계를 기록한다.
5. 역할·공개 수준·Day·소유권·AI Scope·권한 행 바인딩·필드 노출 및 DB 어댑터를 검증한다. 실제 game-data에도 적용해 인지 관계와 필드 경계를 확인한다. 실제 DB/Qdrant/채팅 연동 검증은 실행 환경과 담당 모듈 연결 후 수행한다.
