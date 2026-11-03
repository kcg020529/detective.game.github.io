# experiments/leakage — 출력 가드(G-2·M) 검증 결과 보관소

출력 가드를 페르소나 프롬프트만 쓸 때(가드 OFF)와 비교한 결과를 모았다. 실행 스크립트는 `experiments/guardrails_rebuild/`(`gamedata/` 포함)에 있고, 여기에는 결과 복사본만 둔다. 원본 위치는 그대로다.

## 무엇이 어디에 있나

| 폴더 | 내용 | 비고 |
|---|---|---|
| `results/` | 사람이 읽는 결과 문서 | 아래 표 참고 |
| `runs/` | 수집 응답 | `acl_off`(가드 OFF, 파이프라인으로 수집), `guard_only`(같은 초안에 가드 적용), `direct_off`·`direct_guard`(D 프롬프트 직접 호출 + 가드, **부분 결과 53건**) |
| `scores/` | 채점 결과 | `guard_off_on`(acl_off vs guard_only), `direct_off_on`(단독 재생성, 부분) |
| `generated/` | 출력 단독 실제 응답 | `normal_acl`(정상 170), `attack_vulnerable`(공격 75) |

## 결과 문서

| 파일 | 한 줄 요약 | 신뢰할 때 주의 |
|---|---|---|
| `output_guard_off_on.md` / `.html` | 가드 OFF vs ON 비교표(140문항 짝) | 질문은 YB-1·std이고 응답은 파이프라인(Planner 경유)으로 모은 것. 정상 질문 오차단 수치는 `withheld_*`(가려진 원문 요구) 유형이라 일반 정상 질문의 값이 아니다 |
| `output_guard_real_responses_2026-11-03.md` | 출력 단독 실제 응답(정상 170, 공격 75): 정상 오차단 2.9%, 공격 유출 0건 | 공격 응답은 정확 일치로만 유출을 봤다 |
| `output_guard_eval_2026-10-26.md` | 모의 응답 평가셋 결과(가드 규칙 동결 후) | 모의 응답, 이후 임계값이 바뀌었다 |
| `output_guard_mode_demo_2026-11-03.md` | shadow vs enforce 동작 설명용 사례 | 성능 값이 아니다(13건, 케이스 하나씩 선택) |

## 조건 정리

- 비교 변수는 출력 가드의 ON/OFF이고, ACL은 사용하지 않았다.
- 가드 ON의 허용 기준은 모델이 받은 기록이 아니라 정책표(`database/policies/game_record_permissions.json`)로 만든다.
- 단독 재생성(`direct_*`)은 Planner·검색·입력 가드 없이 D 프롬프트를 직접 호출했다. DeepSeek 503으로 140건 중 53건만 응답을 받았다(대부분 Day 2). 나머지는 `gen_direct_drafts.py --resume`로 이어서 돌린다.
- Canary·API Key는 코드에 있지만 이 결과에서는 다루지 않는다.

## 재현

```bash
# 가드만 다시 적용
.venv/bin/python experiments/guardrails_rebuild/gamedata/rerun_guard.py --repo . --runs runs/acl_off.jsonl --out runs/guard_only.jsonl
# 채점
.venv/bin/python experiments/guardrails_rebuild/gamedata/run_compare.py score --runs runs/acl_off.jsonl runs/guard_only.jsonl --eval-set experiments/guardrails_rebuild/gamedata/eval_set.jsonl --no-enforce-replay --out-dir scores/guard_off_on
# 비교표
python3 -I experiments/guardrails_rebuild/make_off_on_table.py --scored scores/guard_off_on/scored_cases.jsonl --out experiments/guardrails_rebuild/results/output_guard_off_on
```
