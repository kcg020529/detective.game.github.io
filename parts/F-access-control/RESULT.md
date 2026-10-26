# F01 - 역할별 게임 기록 공개 정책

1. 2026-10-26 `docs/interfaces/역할별_권한_매트릭스.md`에 사용자 확정 공개 표를 작성함. Setup은 모든 역할 full, Thought는 prof summary·나머지 deny이며 Action·Dialogue·Result·Incident는 합의한 표를 유지함. 기존 미확정 L1~L3·release_day 제안과 과거 담당자 표기를 갱신함.
2. 네 공개 수준의 필드 허용 목록을 작성함. 기존 metadata의 공개 범위를 유지하며 basic_metadata는 신규 정책에서 제거함. 기존 basic_metadata 행을 검수 없이 metadata로 변환하면 AI 관계·장소 공개가 확대됨을 명시함.
3. 기록별 역할 권한과 Day·AI 지식 범위·Save 소유권을 함께 확인하도록 기록함. 권한 행 누락 시 표 기반 fallback 없이 거부하고, Qdrant 사전 필터·MariaDB 재검증 후 공개 수준별 필드만 Context에 전달하도록 정의함.
4. MASTER·PARTS·README에 새 정책을 반영하고 DB 계약·적재 안내에는 기존 5단계 구현과의 차이를 표시함. 실제 006 SQL CHECK와 적재 도구 LEVELS는 아직 5단계이며 단일 disclosure_level/allowed_roles 형식이므로 역할별 매트릭스 적재·DB 이관이 필요함. 문서만 수정했으며 정책 엔진·DB 적용·런타임 테스트는 미구현/미검증이다.
5. 사용자 추가 지시에 따라 MASTER와 역할별 권한 매트릭스에서 grad의 Action을 full에서 summary로, Incident를 std deny·grad metadata·prof summary로 변경함. 검증 기준에도 해당 네 조합을 추가함. 정책 문서의 표를 대조했으며 DB 권한 데이터·서버 적용은 미구현이다.

# F02 - Policy Engine과 MariaDB 인가 어댑터

1. `backend/policy/engine.py`에 PolicyContext·Decision·decide·project를 구현함. 서버 Save 소유권·역할·Day와 선택 AI·데이터셋을 검사하고, 대상 기록과 dataset/record_id/role이 일치하는 DB 권한 행만 인가 근거로 사용함. 권한 행 누락·deny·제거된 basic_metadata·미등록 값은 기본 거부하며 JSON allowed_roles·유형별 권한 표로 fallback하지 않음.
2. metadata·summary·full의 필드를 명시적으로 투영함. summary에는 content를 포함하지 않고, 공개 필드 누락·빈 허용 텍스트는 반환하지 않음. 알 수 없는 내부 필드는 복사하지 않고 배열은 새 객체로 반환함. Action의 witness_ai·Dialogue의 overheard_ai와 직접 참여 관계를 구분하고 Thought는 소유자 한 명만 허용함.
   - 사용자 확정: Incident는 시스템이 탐지한 보고서로 목격자 관계가 없으며, involved_ai에 명시된 관련 AI에게만 공개함. MASTER·공개 정책·모듈 README에 반영함. 본문의 사건 목격 서술이나 전달받았을 가능성만으로 지식 범위를 확장하지 않음.
3. `backend/policy/repository.py`에 MariaDB DictCursor 어댑터를 구현함. search_scope는 DB에서 Save·권한·AI/장소 메타데이터를 조회해 허용된 `(record_id, 공개 수준)` 목록을 반환하며 요약·본문은 읽지 않음. resolve는 최대 100개 후보 ID를 바인딩하고 DB 상태·권한을 재조회한 뒤 metadata에는 텍스트를 조회하지 않고 summary에는 summary만, full에는 summary·content를 조회해 다시 투영함.
4. 접근 불가능한 Save·잘못된 입력은 PolicyDenied, DB 조회·정책 데이터 오류는 PolicyUnavailable로 처리함. 장애 시 넓은 검색이나 부분 응답으로 대체하지 않으며 오류에 DB 원문을 담지 않음. 어댑터는 호출자의 트랜잭션을 사용하고, 실제 인증 ID·서버 데이터셋 설정을 받는 내부 계약을 README에 기록함. E의 Qdrant 사전 필터와 I의 실제 인증·채팅 라우터 연결은 후속 작업임. 현재 로컬 current_user_id는 임시 개발 사용자라 실서비스 인증으로 간주하지 않음.
5. `python -m unittest discover -s tests -p test_policy_engine.py -v` 19개 통과함. 확정 18개 역할 조합, 목격·엿듣기·타 AI Thought·Incident 관계, 미래 Day·타인 Save·다른 역할/기록/데이터셋 권한 행, 누락·오류·필드 누출 및 DB 어댑터의 조회 컬럼·권한 변경 후 재검증을 확인함.
   - game-data 302건 × 세 역할 × 여섯 AI의 5,436개 조합에서 공개 여부와 요약/본문 필드 경계를 확인함. 이는 로더가 생성한 권한으로 수행한 순수 함수 테스트이며 실제 DB·LLM 응답 검증은 아님.
   - B 로더 회귀 테스트 `python -m unittest discover -s tests -p test_mariadb_loader.py -q` 20개 통과함. DB 어댑터 테스트는 fake connection이며 실제 MariaDB SQL·Qdrant 사전 필터·채팅 E2E·감사 이벤트 연동은 미검증이다.
