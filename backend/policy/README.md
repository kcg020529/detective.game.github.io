# 게임 기록 Policy Engine

F의 현재 구현은 정적 실험 기록 인가와 공개 필드 선택이다. LLM·질문 문장·Planner·JSON의 allowed_roles를 권한 근거로 사용하지 않는다. 기록별 역할 권한은 MariaDB의 document_permissions만 사용하며, 누락·미등록 수준은 거부한다.

## 구성

- `engine.py`: `PolicyContext`, `decide`, `project`. 검증된 서버 상태·기록 메타데이터·해당 역할의 DB 권한 행으로 인가하고, project는 허용 목록의 필드만 새 객체로 반환한다. 거부하면 None이다. Decision.reason은 내부 진단용이며 사용자·모델에 그대로 보내지 않는다.
- `repository.py`: DictCursor를 사용하는 MariaDB 연결을 받아 Save 소유권·저장 역할·Day를 조회하고, 검색 전 SearchScope와 검색 후 안전한 기록을 반환한다. 호출자의 요청 트랜잭션을 사용하며 commit·rollback·연결 종료는 호출자가 관리한다.

## AI 지식 범위

| 종류 | 현재 인지 관계 |
|---|---|
| Action | involved_ai 또는 witness_ai |
| Dialogue | involved_ai 또는 overheard_ai |
| Thought | involved_ai의 소유 AI 한 명 |
| Setup·Result | 명시된 involved_ai |
| Incident | 시스템 탐지 보고서이며 involved_ai에 명시된 관련 AI만 |

Incident의 목격자 관계는 사용하지 않는다는 사용자 결정을 반영했다. 본문에 사건 목격 장면이 있어도 Incident 보고서에 대한 접근을 자동 부여하지 않는다. 별도 전달받은 지식의 권한 확장은 현재 관계 스키마로 자동 추론하지 않는다. 필요하면 근거 기록과 별도 구조화 계약을 추가해야 한다. Setup·Result도 전 AI에게 자동 공개하지 않고 명시된 참여 관계를 확인한다.

## 호출 계약

```python
from backend.policy.repository import PolicyRepository

policy = PolicyRepository(conn)  # backend.api.db의 DictCursor 연결
scope = policy.search_scope(
    user_id=authenticated_user_id,  # 실제 인증 결과; 요청 본문의 ID 사용 금지
    save_id=requested_save_id,
    character_id=selected_character_id,
    dataset='game-data',            # 서버 설정. 일반 요청에서 평가 데이터셋 선택 금지
)
# E: scope.dataset AND scope.record_ids를 Qdrant 검색 전 필터로 적용.
# scope.disclosures에는 (record_id, 공개 수준)이 들어 있다.
# Planner 조건은 이 범위를 좁힐 수만 있다. 빈 scope이면 검색하지 않는다.

safe_records = policy.resolve(
    user_id=authenticated_user_id,
    save_id=requested_save_id,
    character_id=selected_character_id,
    record_ids=retrieved_record_ids,  # 최대 100개; 검색 결과도 신뢰하지 않음
    dataset='game-data',
)
# safe_records만 캐릭터 모델 Context에 제공한다.
```

search_scope는 요약·본문을 읽지 않고 메타데이터와 권한으로 허용 키·공개 수준을 산정한다. Qdrant payload·임베딩 표현과 공개 수준의 대응은 E와 계약을 맞춰야 하며, 이 모듈이 Qdrant 필터 적용을 대신 실행하지 않는다.

resolve는 Save 상태·권한·AI 관계를 DB에서 다시 읽는다. metadata 권한에는 텍스트 조회를 하지 않고, summary 권한에는 summary 컬럼만, full에는 summary·content를 조회한 후 필드를 다시 투영한다. 거부·없는 기록은 결과에서 제외한다. DB 오류나 잘못된 허용 필드 때문에 전체 결과를 반환할 수 없으면 PolicyUnavailable을 발생시키며 부분 결과나 전체 자료로 대체하지 않는다. PolicyDenied는 유효하지 않은 요청·접근 불가능한 Save를 나타낸다. API의 외부 오류 형식은 I에서 연결한다.

현재 정적 game_records에는 Save 전용 소유 필드가 없다. 이 구현은 요청 Save의 소유권을 검증한 뒤 정적 기록만 처리하며, 순수 판정 함수에 Save 전용 범위 필드가 들어오면 지원하지 않는 범위로 거부한다. 채팅·메모 등 Save 데이터 인가는 해당 API가 처리하며 이 테이블로 자동 통합하지 않는다.

## 검증 및 연동 상태

`python -m unittest discover -s tests -p test_policy_engine.py -v`로 순수 판정과 DB 어댑터의 fake connection 테스트를 실행한다. 실제 MariaDB·Qdrant·채팅 E2E 검증은 아직 수행하지 않았다.

최신 main의 current_user_id는 로그인 세션을 검증한다. Policy Engine은 아직 해당 인증·채팅 요청 경로에 연결되지 않았으므로 호출자가 실제 인증 ID와 서버가 선택한 데이터셋을 전달해야 한다. 입력 위험도 점수를 권한으로 해석하지 않는다.
