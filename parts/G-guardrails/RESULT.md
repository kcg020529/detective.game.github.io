# G01 - 입력 위험도 검사 (G-1, 선영)

1. `backend/guardrails/input_guard.py`에 규칙 기반 `inspect_input(question)`을 구현함. 탐지 신호는 지시 무시, 비밀값 요청, 역할·Day·타인 Save 우회, 제한 기록 요청이며 결과는 `level`, `score`, `signals`, `continue_processing`이다. 점수 0/50/90은 초기 분류용 고정값이며 실험으로 보정하지 않았다.
2. 세 수준 모두 `continue_processing=True`로 반환한다. 빈 질문은 호출자 입력 검증 대상으로 `ValueError`를 낸다. 분류 결과는 인증·Save 소유권·F 정책·Retrieval ACL을 대신하지 않는다.
3. `input_guard_audit_event(...)`는 `warn`·`high_risk`에 대해 `input_guard_alert` 이벤트 객체를 만들고 `allow`에는 `None`을 반환한다. 이벤트에는 질문 원문·비밀번호·세션 쿠키를 넣지 않는다. H 감사 저장소 및 대시보드 전송은 아직 연결하지 않았다.
4. `experiments/attacks/input_guard_cases.json`의 정상·위험 Mock 질문 30개(`allow` 12, `warn` 8, `high_risk` 10)를 `tests/guardrails/test_input_guard.py`에서 검사함. `python3 -m unittest discover -s tests/guardrails -p 'test_*.py' -v` 실행 결과 4개 테스트 통과. 이 사례들은 직접 고른 예시이며 실제 게임 질문의 오탐·미탐 비율을 나타내지 않는다.
5. 채팅 전송 API는 현재 브랜치에서 제거되어 Input Guard는 독립 모듈로만 확인했다. H의 감사 이벤트 저장 함수는 있지만 실제 채팅 흐름에서 자동 호출하지 않는다. O 대시보드도 미구현이다.
6. `backend/guardrails/llm_input_guard.py`에 현재 질문만 DeepSeek로 보내는 선택적 추가 판정을 작성했다. 규칙과 모델 중 높은 위험도를 쓰고 호출 실패 시 규칙 결과를 사용한다. 모델도 질문을 중단하거나 권한을 바꾸지 않는다. 2026-10-26 로컬 키로 정상·비공개 기록·지시 무시 예시를 각각 실제 DeepSeek에 보내 `allow`·`warn`·`high_risk` 결과와 계속 처리 `true`를 확인했다. 질문 원문과 키는 검사 출력에 남기지 않았다. 이는 세 예시에 대한 연결 확인이며 오탐·미탐 평가가 아니다.
7. 결과에 `model_status`를 추가해 규칙만 사용한 경우(`not_used`), 모델 판정 성공(`ok`), 모델 실패 후 규칙 대체(`fallback`)를 구분한다. 모델 장애가 규칙 결과 뒤에 가려지지 않도록 하기 위한 상태이며, 현재 H 감사 테이블에는 아직 저장하지 않는다.
