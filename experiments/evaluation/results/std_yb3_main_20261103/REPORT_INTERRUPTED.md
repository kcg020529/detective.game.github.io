# 학부연구생 · YB-3 전체 비교 실험 — API 잔액 부족으로 중단

2026-11-03. 교수 실험과 같은 세 구성, temperature 0, 캐릭터 max_tokens 400, 재시도 0, 문항별 빈 대화 이력, 출력 가드 enforce 조건으로 실행을 시작했다. 기존 학부연구생(std) 150문항은 정상50·공격100, Day6 140·Day4 10이며 목표는 총450회다. 교수와 질문 수·유형·Day 배치는 같지만 실제 질문은 역할별 세트여서 교수/학부의 문항별 대응 실험은 아니다.

## 현재 진행 상태

| 구성 | 시도 기록 | 최종 답변 완료 | 오류 | 응답 없는 guard_rejected | 아직 미시도 |
|---|---:|---:|---:|---:|---:|
| Prompt-only | 144 | 140 | 4 | 0 | 6 |
| Guardrail | 111 | 106 | 5 | 0 | 39 |
| Guardrail+ACL | 106 | 101 | 4 | 1 | 44 |
| 합계 | 361 | 347 | 13 | 1 | 89 |

두 키의 DeepSeek 잔액 조회는 HTTP200, USD0.05/is_available=true를 반환했지만, 최소 chat 요청은 HTTP402 / insufficient_balance_error로 거절됐다. 실행기가 연속 오류 보호로 중단된 뒤 추가 유료 채점 프로세스도 중지했다. 이 상태를 로컬 권한 오류나 가드 차단 성공으로 보고하지 않는다.

`prof-...` 결과 파일은 수정하지 않았으며 이번 파일은 전부 `std_yb3_main_20261103/`에 별도 보존한다. 세 구성 공통으로 최종 답변이 완료된 문항은100개다. 익명 LLM 초벌106건은 graded54·judge_error46·운영 오류 제외6건이며, graded도 의미 검수 완료를 뜻하지 않는다. 허용 summary/metadata와 비공개 content를 혼동한 판정이 발견돼 초벌 비율은 최종 보안 성능으로 보고하지 않는다. 전체 다섯 지표의 검수 완료 비교는 아직 미완료다.

## 검증과 보존

- Save·PolicyContext·역할 정책 프롬프트·질문 파일·채점 keys/scope를 모두std로 적용했다. Action/Result summary, Dialogue metadata, Thought/Incident deny, Setup full을 명시했다.
- `live_input_check.json`: DB의1,445개 원문/요약 및 std Day4/6의 실제 정책·필드가 고정된 grading_v1과 일치했다. 실행 당시 임시 Save6개가 모두std임을 확인했다.
- 교수 프롬프트의 문자열 유지·역할 혼입 거부·가드 모드·채점 인용 검증을 포함한 관련 pytest9건을 통과했다. `build_grading_keys --check`도 통과했다.
- `run_snapshot.json`에 실행/채점 코드, 질문, 루브릭, 근거·scope 파일 해시를 남겼다. `interruption.json`에 중단 사유, 시도/미시도 수와 재개 명령을 기록했다.
- 원본 구성별 JSONL, 초벌 judge_verdicts.jsonl, 임시 judged_metrics.json, 대조용 review.csv를 보존했다. 초벌 지표를 최종 결과로 사용하지 않는다.
- 중단 후 임시 실험 사용자0명이며 일반 게임 API의 game-data/ACL on/output shadow/input on 설정을 확인했다. 일반 서버 설정은 변경하지 않았다.

## 재개

충전 후 동일한 Compose 환경과 workspace/cache mount에서 다음 모듈 명령을 실행하면 기록된 시도는 건너뛰고 미시도89회를 이어간다. 기존 오류는 덮어쓰거나 성공으로 바꾸지 않는다. 완료 후 오류·보류 케이스의 공통 분모 처리와 내용 검수를 수행해야 한다.

```text
python -m experiments.evaluation.run_three_way --name std_yb3_main_20261103 --role std --confirm-paid
python -m experiments.evaluation.judge_three_way --name std_yb3_main_20261103 --role std --watch --confirm-paid
python -m experiments.evaluation.recheck_judge --name std_yb3_main_20261103 --role std --confirm-paid
```

이미 남은 judge_error는 초벌 파일의 완료 ID로 남으므로, 마지막 재검토 단계와 원본 대조를 생략하면 안 된다. API 잔액 때문에 발생한 실패의 별도 복구 실행이 필요하면 원본 기록을 보존하고 새 시도/복구 집합을 구분해 보고한다.
