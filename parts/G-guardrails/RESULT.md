# G01 - 입력 위험도 검사 (G-1, 선영)

1. `backend/guardrails/input_guard.py`에 규칙 기반 `inspect_input(question)`을 구현함. 탐지 신호는 지시 무시, 비밀값 요청, 역할·Day·타인 Save 우회, 제한 기록 요청이며 결과는 `level`, `score`, `signals`, `continue_processing`이다. 점수 0/50/90은 초기 분류용 고정값이며 실험으로 보정하지 않았다.
2. 세 수준 모두 `continue_processing=True`로 반환한다. 빈 질문은 호출자 입력 검증 대상으로 `ValueError`를 낸다. 분류 결과는 인증·Save 소유권·F 정책·Retrieval ACL을 대신하지 않는다.
3. `input_guard_audit_event(...)`는 `warn`·`high_risk`에 대해 `input_guard_alert` 이벤트 객체를 만들고 `allow`에는 `None`을 반환한다. 이벤트에는 질문 원문·비밀번호·세션 쿠키를 넣지 않는다. H 감사 저장소 및 대시보드 전송은 아직 연결하지 않았다.
4. `experiments/attacks/input_guard_cases.json`의 정상·위험 Mock 질문 10개를 `tests/guardrails/test_input_guard.py`에서 검사함. `python3 -m unittest discover -s tests/guardrails -p 'test_*.py' -v` 실행 결과 4개 테스트 통과. 규칙은 이 작은 사례 집합에서만 확인했으며 오탐·미탐 비율이나 실제 채팅 통합 성능은 아직 측정하지 않았다.
5. I05 채팅 전송 경로에서 Save 소유권 확인 후 이 모듈을 호출한다. `tests/api/test_send_chat.py`의 테스트 생성기를 사용해 `high_risk` 질문도 후속 흐름으로 진행하고 로그에는 질문 원문을 쓰지 않음을 확인했다. 실제 외부 AI 호출 및 H 대시보드 전송은 미검증이다.
