# Input Guard 단독 실험

- `cases/input_guard_cases.json`: 규칙 검사 기준선 질문 30개
- `cases/input_guard_signal_cases.json`: 신호별 질문과 정상 질문
- `results/INPUT_GUARD_RETEST_2026-11-03.md`: 3문항 판정 및 입력 감사 저장 확인

자동 회귀 테스트는 `tests/guardrails/test_input_guard.py`,
`tests/guardrails/test_llm_input_guard.py`, `tests/audit/`에 둔다.
규칙·모델·결합의 200문항 비교는
[종합 비교 실험](../../evaluation/input_guard/README.md)에 둔다.
