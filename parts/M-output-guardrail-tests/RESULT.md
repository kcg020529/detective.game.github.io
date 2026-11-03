# M01 - 출력 가드 ON/OFF 비교 평가

1. 모의 응답 평가를 현재 설정(임계값 context_leak 0.40/0.60, prompt_leak 0.50/0.80)으로 다시 돌렸다(2026-11-03, test 88건, enforce).
   - `python3 -I experiments/guardrails_rebuild/run_output_eval.py --split test --cases experiments/guardrails_rebuild/data/output_cases_v2.jsonl`
   - 판정 일치 75/88, 막아야 할 것 중 잡은 비율 40/52(76.9%), 정상 오차단 0/36, 회색지대 5/36. 10/26 동결 값(77/88, 놓침 7/52, 오차단 3/36)과 비교하면 오차단은 줄고 놓침이 늘었다.
   - 놓침은 허용 밖 Context(6/12), 프롬프트 유출(2/6), 덧붙은 무관 문장(2/2)에 몰려 있다. 모의 응답이며 사람 검토 전이다.
2. 게임 기록 140문항으로 같은 초안에 가드를 켜고 껐다(YB-1, `std`, Day 2·4·6, `test-data`로 적재한 게임 기록).
   - 가드 OFF는 `runs/acl_off.jsonl`(ACL 없이 수집), 가드 ON은 `gamedata/rerun_guard.py`가 같은 초안에 정책 기준 허용 목록으로 가드를 적용한 `runs/guard_only.jsonl`. 채점은 `gamedata/run_compare.py score`.
   - 공격 질문 유출 성공률 43.6%(34/78) → 2.6%(2/78), 최종 답변 유출률 51.4%(72/140) → 15.0%(21/140), 유출 초안 차단율 70.8%(51/72).
   - 정상 질문 오차단은 깨끗한 초안 기준 41.7%(10/24)이며, 이 질문들은 모두 `withheld_*`(가려진 원문을 달라는 유형)라 일반 정상 질문의 값이 아니다. 평가셋의 `normal_*` 107문항은 이 비교에 포함되지 않았다.
   - 응답은 Planner를 거친 서버 파이프라인으로 모았다. 출력 가드에 넣는 입력(초안·질문·허용 기준)만 보면 단독이지만 응답 수집은 단독이 아니다.
3. 출력 단독 실제 응답을 새로 만들었다(`experiments/guardrails_rebuild/gen_output_samples.py`).
   - D의 `render_actor_prompt`와 `chat_json`을 직접 호출하며 Planner·검색·입력 가드를 거치지 않는다. 정상 질문 170건(허용 기록만 [기억]에 넣음), 공격 질문 75건(전체 기록, 77건 중 2건은 빈 응답).
   - 정상 질문 오차단 5/170(2.9%, 사유 모두 `irrelevant`). 공격 질문은 정확 일치로 잡힌 유출 0건이고, 가드가 막은 8건은 모델의 정상 거절 문장이 '게임 무관' 검사에 걸린 것이다.
   - 공격 응답의 `allow` 라벨은 사람이 검수하지 않았다. 의역 유출은 놓칠 수 있다.
4. 단독 재생성(`gamedata/gen_direct_drafts.py`)은 부분 결과다.
   - 2번 문항의 질문과 전달 기록 ID를 고정 입력으로 읽어 D 프롬프트를 직접 호출한다. DeepSeek 503(서비스 과부하)이 반복되어 140건 중 53건만 응답을 받았고 대부분 Day 2다(`--resume`으로 이어서 돌릴 수 있음).
   - 53건에서 유출 초안 차단율 72.7%(24/33), 공격 질문 유출 성공률 42.5% → 9.1%로 2번과 같은 방향이다. 표본이 작고 Day 2에 몰려 있어 참고용이다.
5. 결과 표시 이름을 정리했다. 채점기(`gamedata/run_compare.py`)의 요약에서 구성 이름을 "가드레일 OFF/ON"으로, 지표 이름을 출력 가드 기준으로 바꿨다. 계산식은 바꾸지 않았다.
   - 비교표 생성: `experiments/guardrails_rebuild/make_off_on_table.py`, 동작 설명용 사례: `demo_modes.py`, 가드 전후 사례 출력: `show_before_after.py`.
6. 결과를 `experiments/leakage/`에 모았다(복사본). 파일별 설명과 주의점은 `experiments/leakage/README.md`.
7. 미검증·남은 문제
   - 정상 질문 오차단은 `withheld_*` 유형에서만 쟀다. 일반 정상 질문(`normal_*`)은 2번 비교에 없고, 3번(출력 단독)의 170건에서만 확인했다.
   - 응답은 한 번 생성한 한 세트이며 반복 측정이 없다. 응답 시간은 측정하지 않았다.
   - 임계값 변경 전후를 같은 tune 데이터로 비교하지 않았다.
   - 게임 기록 평가는 `test-data` 이름으로 적재한 게임 기록 기준이며 `game-data` 전용 환경 검증은 아니다.
