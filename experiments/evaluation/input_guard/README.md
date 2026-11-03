# Input Guard 종합 비교 실험

- `cases/`: 서로 다른 표현의 100문항 질문셋 두 개
- `run_input_guard_200.py`: 규칙 단독·DeepSeek 단독·결합 판정 실행
- `INPUT_GUARD_EVALUATION.md`: 판정과 입력 감사 평가 기준
- `INPUT_GUARD_RETEST_200_2026-11-03.md`: 200문항 재시험 보고서
- `results/input_guard_holdout_retest_200_2026-11-03.json`: 해당 재시험의 질문별 원시 결과
- `results/history/`: 이전 100문항 실행, 반복 판정, 이전 보고서

저장된 결과를 읽거나 질문셋을 검사하는 데는 DeepSeek 키가 필요하지 않다.
실제 모델 재시험은 질문 200개를 외부 API로 전송하므로 키와 호출 범위를 확인한 뒤 실행한다.

```bash
python -m experiments.evaluation.input_guard.run_input_guard_200
```

이 폴더의 수치는 질문 분류 결과다. 검색·ACL·최종 답변 유출률을 측정한 결과가 아니다.
