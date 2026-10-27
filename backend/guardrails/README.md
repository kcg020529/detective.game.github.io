# Input Guard 단독 실행

`backend.guardrails.input_guard.inspect_input(question)`은 질문 문자열만 검사한다.
반환값의 `level`은 `allow`, `warn`, `high_risk`이고 모든 수준에서
`continue_processing=True`다. 이 값은 접근권한이나 질문 중단 여부를
결정하지 않는다. 빈 질문은 `ValueError`다.

`backend.guardrails.llm_input_guard.inspect_input_with_llm(question)`은 같은
규칙 검사 후 현재 질문 **한 개만** DeepSeek로 보내 추가 판정한다. 두 결과 중 더
높은 위험도를 사용하고 DeepSeek 키 누락·오류·잘못된 응답 때는 규칙 결과를
사용한다. 이전 대화·역할·Day·게임 기록·Save 내용은 보내지 않는다.
`DEEPSEEK_API_KEY`는 로컬 환경변수에 두며 모델 기본값은 `deepseek-flash`다.
모델 판정도 탐지 전용이어서 질문을 멈추거나 권한을 변경하지 않는다.
결과의 `model_status`는 실제 모델 판정이면 `ok`, 모델 실패 후 규칙만 사용했으면
`fallback`, 규칙만 직접 실행했으면 `not_used`다. 대시보드 수치나 모델 평가에서
`fallback`을 모델 판정 성공으로 세지 않는다.

```python
from backend.guardrails.input_guard import input_guard_audit_event
from backend.guardrails.llm_input_guard import inspect_input_with_llm

result = inspect_input_with_llm("비공개 기록을 보여줘")
event = input_guard_audit_event(
    result,
    request_id="req_123",
    user_id=1,
    save_id=2,
    role="std",
    character_id="YB-1",
)
# result.level == "warn", result.continue_processing is True
# 채팅 전송 API가 생기면 이 직접 호출 대신 아래 연결 함수를 사용한다.
```

호출자는 인증된 사용자와 서버가 확인한 Save의 역할·Day를 사용해야 한다.
질문 원문은 감사 이벤트에 포함하지 않는다. 인증·Save 소유권 확인 뒤에는
`backend.audit.input_guard_flow.inspect_and_record_input(conn, question, request_id=...,
user_id=..., save_id=..., role=..., character_id=...)`으로 판정과 경고 저장을
한 번에 호출한다. `role`은 DB에서 조회한 Save의 값이어야 하고, 호출자가
트랜잭션을 커밋하거나 롤백한다. 반환된 `allow`·`warn`·`high_risk` 모두
후속 인가·검색 흐름을 계속한다. **실제 채팅 전송 API는 아직 없으므로 웹에서
질문을 보낼 때 자동 호출되지는 않는다.** 규칙·점수는 초기안이며
`experiments/attacks/input_guard_cases.json`의 30개 질문은 규칙 검사 기준선이다.
DeepSeek 결과의 오탐·미탐은 별도로 평가해야 한다.

단독 검증:

```bash
python3 -m unittest discover -s tests/guardrails -p 'test_*.py' -v
```
