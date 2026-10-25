# Input Guard 단독 실행

`backend.guardrails.input_guard.inspect_input(question)`은 질문 문자열만 검사한다.
반환값의 `level`은 `allow`, `warn`, `high_risk`이고 모든 수준에서
`continue_processing=True`다. 이 값은 접근권한이나 질문 중단 여부를
결정하지 않는다. 빈 질문은 `ValueError`다.

```python
from backend.guardrails.input_guard import inspect_input, input_guard_audit_event

result = inspect_input("비공개 기록을 보여줘")
event = input_guard_audit_event(
    result,
    request_id="req_123",
    user_id=1,
    save_id=2,
    role="std",
    character_id="yb_01",
)
# result.level == "warn", result.continue_processing is True
# event는 H 감사 저장소에 전달할 자료이며 아직 자동 저장되지 않는다.
```

호출자는 인증된 사용자와 서버가 확인한 Save의 역할·Day를 사용해야 한다.
질문 원문은 이벤트에 포함하지 않는다. 채팅 전송 API와 H 감사 저장소가
생기면 그 위치에서 호출·저장을 연결한다. 규칙·점수는 초기안이며
`experiments/attacks/input_guard_cases.json`을 늘려 오탐·미탐을 측정해야 한다.

단독 검증:

```bash
python3 -m unittest discover -s tests/guardrails -p 'test_*.py' -v
```
