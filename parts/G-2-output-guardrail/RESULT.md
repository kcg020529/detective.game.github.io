# G02 - 출력 응답 검사 (G-2)

1. 규칙 기반 Output Guard를 구현한 뒤 `backend/guardrails/output/`로 이동했다(`normalize.py`, `secret_check.py`, `context_check.py`, `prompt_check.py`, `quality_check.py`, `guard.py`, `config.json`). 평가 데이터와 실행 스크립트는 `experiments/guardrails_rebuild/`에 남겼다.
   - `OutputGuard.check(response_text, user_input, role, day, target_ai, allowed_context_ids)`가 `decision`(allow/mask/block), `applied`(실제 적용), `text`(사용자에게 보낼 문장), `event`(none/log/alert), `reasons`, `gray`, `checks`를 돌려준다. 같은 입력이면 같은 결과다.
   - 정규화: NFKC, 제로폭·결합 악센트 제거, 대소문자·공백·기호 제거 비교본, base64·16진수·역순·rot13 한 단계 해독.
   - 닫힌 집합: 값 일치 + 8자 이상 조각 일치 + 개인정보 형식 정규식. Canary·키는 전체 차단, 개인정보는 `[가림]`으로 마스킹하고 마스킹이 안 되면 전체 차단한다.
   - 허용 Context: 이번 요청에서 모델에 준 기록 ID 밖의 기록에만 있는 표현(점수 쌍, 순위 표현, 고유 어휘, 글자 조각)을 점수화한다. 허용 기록에도 있는 내용은 근거에서 뺀다.
   - 프롬프트 유출: 등록 문장의 글자 3-gram 포함 비율. 반복: 3-gram 다양성. 페르소나 이탈: 표현 목록. 무관 응답: 코드 블록·영어 위주·게임 어휘 없는 문장 비율.
2. 처리·모드·설정은 `backend/guardrails/output/config.json`에 있다. `mode`는 기본 `shadow`다.
   - 임계값(low/high): context_leak 0.20/0.40, prompt_leak 0.25/0.35, degenerate 0.5/0.9, irrelevant 0.4/0.8. 모의 평가셋으로 잠정 설정한 값이다.
   - `always_enforced`(canary, api_key, pii, broken)는 shadow에서도 적용한다. 이벤트는 canary·api_key·pii·context_leak·prompt_leak가 alert, 그 밖과 회색지대는 log다.
   - 사용자에게 보이는 대체 문구 3종은 D의 고정 문구와 맞출 때까지 자리표시다.
3. 단위 테스트 21건 통과: `python3 -I tests/guardrails/test_output_guard.py`.
   - 평가셋 형식·분할·허용 Context 점검 통과: `python3 -I experiments/guardrails_rebuild/validate_data.py` (입력 304건, 출력 191건).
   - 이상 입력(None, 빈 문자열, 숫자, dict, bytes, 제어문자, 10만 자)도 예외 없이 처리한다. 비문자열·빈 응답은 깨진 응답으로 차단한다. 가드 내부 오류는 잡지 않고 호출자에게 던진다.
4. 모의 응답 평가(`test-data` 기준, 응답은 AI가 쓴 것이고 사람 검토 전): `python3 -I experiments/guardrails_rebuild/run_output_eval.py --split test --cases experiments/guardrails_rebuild/data/output_cases_v2.jsonl`
   - 규칙을 동결하고 v2 test 88건을 한 번 연 값: 판정 일치 77/88, 놓침 7/52, 정상 오차단 3/36. 이 값이 출발점이다.
   - 이 값을 본 뒤 임계값 2개와 일반 표현 2개를 조정한 결과(놓침 5/52, 오차단 0/36)는 이미 본 test에 맞춘 값이라 성능으로 쓰지 않는다.
   - 닫힌 집합(Canary·키·개인정보) 놓침은 전체 42건 중 2건(한글 음차, 한글 숫자)이다. 알려진 한계다.
   - 합격선은 두지 않았다. 상세 표·원인·변경 이력: `experiments/guardrails_rebuild/results/output_guard_eval_2026-10-26.md`.
5. 사례집: `python3 -I experiments/guardrails_rebuild/build_case_report.py --out experiments/guardrails_rebuild/results/output_guard_case_report.html --standalone`. 평가셋 191건 전부를 질문·응답·검사별 점수·판정·사용자에게 간 문장으로 보여 주고, 기대와 달랐던 사례의 원인을 정리한다.
6. 응답 표본 생성 스크립트 `experiments/guardrails_rebuild/gen_output_samples.py`: D의 `prompt_render`와 `llm_client`를 그대로 불러 서비스와 같은 설정(생각 모드 끄기, JSON 응답, `.env`의 온도·최대 토큰·재시도)으로 호출한다. 실행 전에 호출 수와 설정을 보여 주고, 연속 실패 시 멈추며, 쓴 토큰을 알려 준다.
   - 평가 입력의 `AI-n`을 D 최신 커밋(91a0498)의 `YB-n`으로 같은 번호끼리 대응시킨다.
   - `--dry-run`과 가짜 서버(정상·빈 응답·키 없음)로 흐름을 검증했다. **실제 DeepSeek 호출은 미검증**이다.
7. D의 실제 문구 점검(LLM 호출 없음): `python3 -I experiments/guardrails_rebuild/check_d_phrases.py`. `personas.yaml`의 고정·참고 문구 18개와 말투 예시 18개를 넣었다.
   - enforce 기준으로 고정·참고 문구는 7개, 말투 예시는 5개가 차단 판정이고 전부 '게임 무관' 검사 때문이다(점수 0.44~1.0). 예: "그건 제가 볼 수 있는 자료가 아니에요."가 1.0.
   - 모의 평가의 정상 오탐은 제가 쓴 응답에 게임 어휘가 많아 낙관적이었을 가능성이 크다. 이 결과로 규칙을 고치지 않았다. 실제 DeepSeek 응답을 본 뒤 정한다.
8. 감사 이벤트 `output_guard_audit_event(result, request_id, user_id, save_id, role, character_id)`를 `backend/guardrails/output/guard.py`에 구현했다. 알릴 것이 없으면 `None`, 있으면 `output_guard_alert` 이벤트(`level`은 log/alert, `decision`, `applied`, `mode`, `signals`)를 돌려주고 응답 원문과 비밀 값은 담지 않는다.
   - **부분 구현:** `backend/audit/store.py`의 `save_input_guard_alert`는 입력 가드 이벤트의 키 10개와 `input_guard_alert`, level `warn`/`high_risk`만 받는다. 출력 이벤트는 현재 저장되지 않으므로 H와 확장 방식(키·level 어휘·`score` 필드)을 정해야 한다.
9. 한계·미검증:
   - 평가 응답은 AI가 쓴 모의 응답이고 사람 검토 전(`review: unreviewed`)이다. 정상 표본이 작아 오탐률 상한이 넓다.
   - 실제 DeepSeek 응답, 실제 Canary·더미 키·개인정보 값(현재 자리표시), D의 실제 프롬프트 문장(프롬프트 유출 검사는 자리표시 문장 사용), `game-data` 기준 평가는 **미검증**이다.
   - 이 기록 작성 시점에는 서버(I) 흐름에 연결하지 않았다. 현재 작업 브랜치에는 출력 검사 어댑터를 추가했으나 D 생성 어댑터와 출력 감사 저장은 미연결이다. `response_type` 대응, D의 고정 문구를 가드에 거칠지는 정해지지 않았다.
   - 어휘 목록 기반이라 의역·흩어진 유출·일반 상식형 무관 응답에 약하다. 한 단계 인코딩만 푼다.
   - `check_d_phrases.py`와 `gen_output_samples.py`는 `backend/character_ai/`(D)가 있어야 동작한다. 나머지는 표준 라이브러리만으로 동작한다.

10. 현재 `feat/HO-audit-dashboard`에서는 `backend/api/output_guard_adapter.py`를 채팅 파이프라인에 등록하고 모의 생성 답변으로 확인했다. 변경 없는 응답은 통과하며, 차단·마스킹된 응답은 최종 `response_type` 계약이 확정될 때까지 503으로 처리해 초안을 저장·반환하지 않는다. 실제 D 생성·전체 비인가 기록 비교·출력 감사 저장은 미연결이다.
