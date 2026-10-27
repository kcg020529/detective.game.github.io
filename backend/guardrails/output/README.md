# Output Guard (G-2) — 출력 가드레일 재구현

> **상태:** 구현·평가셋 검증 완료(모의 데이터). 실제 DeepSeek 응답, 실제 Canary·키·개인정보 값, D의 실제 페르소나 프롬프트로는 **미검증**이다.
> **위치:** `backend/guardrails/output/`. 모의 평가 데이터와 실행 스크립트는 `experiments/guardrails_rebuild/`에 둔다. 현재 작업 브랜치에서는 채팅 파이프라인의 출력 검사 어댑터에 연결했다. D 생성 어댑터가 없어 실제 채팅 POST는 아직 503이다.
> **의존성:** 파이썬 표준 라이브러리만. LLM·네트워크 호출 없음. 같은 입력은 항상 같은 결과.

## 1. 무엇을 하나

캐릭터 AI(D)의 응답이 사용자에게 가기 직전에 검사한다. 입력 쪽 걸러내기(무관한 질문 등)는 Query Planner(C)가 맡으므로, 이 가드는 **Planner·F·E를 통과해 나온 응답**만 본다. 권한을 주거나 바꾸지 않는다(권한은 F, 검색 통제는 E). 마지막 안전망이다.

```
응답 → [0 깨진 응답] → [1 Canary·키·개인정보] → [2 비인가 Context] → [3 프롬프트 문구 유출] → [4 반복·이탈·무관] → 판정
                                                                                                   allow / mask / block + event
```

| 단계 | 검사 | 방식 | 임계값 | 기본 처리 |
|---|---|---|---|---|
| 0 | 빈 응답, 기호뿐, 잘린 JSON, `null`·`[]` | 규칙 | 없음 | 전체 차단 |
| 1 | Canary, 더미 API Key | 정규화 후 정확 일치 + 8~10자 이상 조각 일치. 전각·대소문자·공백·제로폭·base64·16진수·역순·rot13 한 단계 | 없음 | **응답 전체 차단**, alert |
| 1 | 합성 개인정보 | 값 일치 + 형식(전화·주민번호·이메일) 정규식 | 없음 | **해당 부분만 `[가림]`**, 마스킹이 안 되면 전체 차단, alert |
| 2 | 비인가 Context | 허용 Context ID 밖 기록에만 있는 표현(점수 쌍, 순위 표현, 고유 어휘, 글자 조각)이 응답에 있는 정도 0~1 | τ_low 0.20 / τ_high 0.40 | 점수 ≥ τ_high 차단, 사이는 통과+로그 |
| 3 | 프롬프트 문구 유출 | 등록된 프롬프트 문장의 글자 3-gram이 응답에 들어 있는 비율 | 0.25 / 0.35 | 위와 같음 |
| 4 | 반복(degenerate) | 3-gram 다양성 | 0.5 / 0.9 | 위와 같음 |
| 4 | 페르소나 이탈 | 정체를 말하는 표현 목록("언어 모델" 등) | 규칙 | 차단, log |
| 4 | 무관 응답 | 코드 블록, 영어 위주, 게임 어휘·증언 표현·거절 표현이 없는 문장의 비율 | 0.4 / 0.8 | 위와 같음 |

판정 규칙: 점수 < τ_low 통과, τ_low ≤ 점수 < τ_high **회색지대(통과 + 로그)**, 점수 ≥ τ_high 차단. 우선순위는 `config.json`의 `block_priority`.

사용자가 정한 처리(2026-10-26): Canary·키는 전체 차단, 개인정보는 마스킹, 회색지대는 통과+로그, 합격선은 두지 않고, 먼저 돌려 오탐·미탐이 얼마나 나오는지 본 뒤 고쳐 나간다. enforce 전환 시점은 shadow 로그와 평가 결과를 보고 사용자가 정한다.

## 2. 모드

`config.json`의 `mode`.

- `shadow`: 점수형 검사(2~4단계)는 판정만 기록하고 응답은 그대로 보낸다(`applied=allow`). 임계값을 조정하는 기간에 쓴다.
- `enforce`: 판정대로 적용한다.
- Canary·키·개인정보·깨진 응답은 `shadow`에서도 항상 적용한다(`always_enforced`).

## 3. 사용법

```python
from backend.guardrails.output import OutputGuard, load_config
guard = OutputGuard(load_config(), records=records, prompt_sentences=prompt_sentences)
r = guard.check(response_text, user_input=q, role=role, day=day, target_ai=ai,
                allowed_context_ids=ids_given_to_the_model)
# r["applied"] -> allow/mask/block, r["text"] -> 사용자에게 보낼 문장, r["event"] -> none/log/alert
# r["checks"] -> 검사별 점수·수준(로그용. 비밀값 원문은 담지 않음)
```

- `records`: 비인가 기록까지 포함한 전체 기록(운영에서는 DB/Qdrant 기록으로 만든다). 평가에서는 `data/test-data/records.json`.
- `allowed_context_ids`: 이번 요청에서 F/E가 모델에 실제로 준 기록 ID. `None`이면 2단계를 건너뛴다(1·3·4단계는 동작).
- `prompt_sentences`: D의 페르소나 프롬프트 문장. 평가에서는 `data/output_fixtures.json`의 자리표시 3문장. `prompt_check.sentences_from_text()`로 파일에서 쪼갤 수 있다.
- 감사 이벤트: `output_guard_audit_event(r, request_id=…, user_id=…, save_id=…, role=…, character_id=…)`는 알릴 것이 없으면 `None`, 있으면 `{event_type:"output_guard_alert", …, level, decision, applied, mode, signals}`를 돌려준다. 자리 필드는 팀의 `input_guard_audit_event`와 같게 맞췄다(`backend/guardrails/input/input_guard.py`). 비밀값 원문은 담기지 않는다. 다만 `backend/audit/store.py`의 `save_input_guard_alert`는 입력 가드 이벤트의 키 10개와 `input_guard_alert`, level `warn`·`high_risk`만 받으므로, 출력 이벤트는 H와 저장 함수·level 어휘를 정해야 저장된다 `[미정]`.
- 서버 흐름은 Input Guard → Planner → Policy Engine → ACL 검색 → 캐릭터 응답 → Output Guard이고(`docs/interfaces/API_요청응답_계약.md`), 응답 종류 `reply_kind`에 마스킹/차단을 어떻게 대응시킬지와 가드 오류 시 동작은 아직 정해지지 않았다 `[미정]`.

## 4. 실행·검증 명령

```bash
python3 -I experiments/guardrails_rebuild/validate_data.py                         # 평가셋 형식·분할·허용 Context 점검
python3 -I tests/guardrails/test_output_guard.py                                     # 단위 테스트 21건
python3 -I experiments/guardrails_rebuild/run_output_eval.py --split tune --sweep   # 임계값 조정용(tune만)
python3 -I experiments/guardrails_rebuild/run_output_eval.py --split test --cases experiments/guardrails_rebuild/data/output_cases_v2.jsonl
python3 -I experiments/guardrails_rebuild/check_d_phrases.py                        # D의 실제 문구(personas.yaml)를 가드에 넣어 봄. pyyaml 필요, 호출 없음
python3 -I experiments/guardrails_rebuild/build_case_report.py --out experiments/guardrails_rebuild/results/output_guard_case_report.html --standalone   # 사례 191건 전부를 질문·응답·점수·판정으로 보여 주는 화면
```

사례집은 사례를 상황별(인젝션 입력 / 정상 질문 / 위험해 보이지만 정상 / 게임과 무관 / 정상 질문 뒤에 다른 말 / 모델 이상 응답)로 나눠 보여 준다. 상황 정의와 DeepSeek로 채울 입력 출처는 `case_report/notes.json`의 `scenarios`에 있다. `gen_output_samples.py`로 만든 실제 응답은 `--extra-cases`로 더하면 같은 상황 칸에 들어간다(`gen_output_samples.py --group`으로 입력 group을 골라 돌릴 수 있고, 결과 행에 `input_file`·`input_group`이 기록된다).

사례집(`results/output_guard_case_report.html`)은 가드를 실제로 돌린 결과를 그대로 담는다. 규칙·임계값을 고친 뒤 다시 만들면 숫자와 카드가 모두 새 결과로 바뀐다. '고쳐야 할 것' 설명문은 `case_report/notes.json`이고, 규칙을 고치면 같이 고쳐야 한다. 고치기 전 비교값은 `results/baseline_first_run/`에서 읽는다.

`--set thresholds.context_leak.high=0.5` 처럼 설정을 덮어쓸 수 있다. test 결과를 보고 임계값을 고치면 그 test는 오염된다(평가셋 README 10장).

## 5. 결과 (모의 평가셋, 요약)

자세한 표와 사례별 원인은 `experiments/guardrails_rebuild/results/output_guard_eval_2026-10-26.md`에 있다. 한 줄로: **규칙을 얼리고 연 v2 test(88건)에서 판정 77건 일치, 놓침 7/52, 정상 오차단 3/36**이었고, test를 본 뒤 임계값 2개·일반 표현 2개를 조정하면 놓침 5/52, 오차단 0/36이다(후자는 오염된 수치).

## 6. 한계 (결과를 읽을 때 같이 볼 것)

1. **정상 응답 표본이 작다.** v2 test 정상 36건. 오탐이 0건이어도 95% 상한은 약 9.6%다. 표본이 작을수록 숫자의 오차가 크다. 실제 DeepSeek 정상 응답을 모아 늘려야 한다(`gen_output_samples.py`).
2. **같은 작성자(AI)가 평가셋과 규칙을 모두 만들었다.** v1은 작성 중 내용을 보았고 v2는 규칙 동결 후에 썼지만 같은 작성자다. 어휘 목록(게임 어휘, 증언·거절 표현)이 평가셋 문체에 맞을 수 있다.
3. **2~4단계는 어휘·글자 조각 겹침에 기댄다.** 어휘를 거의 바꾼 의역, 여러 문장에 흩어 말한 유출, 게임 어휘가 들어 있지만 질문과 무관한 일반 상식은 놓친다. 정상 응답이 비인가 기록과 흔한 단어를 공유하면 오탐이 난다(v2 test에서 실제로 3건).
4. **정규화 한계:** 한 단계 인코딩만 푼다. 이중 인코딩, 호모글리프(키릴 문자 등), 한글 음차("카나리 이그잼플"), 한글 숫자("공일공"), "(at)" 같은 표기 변형, 11자 이하의 짧은 조각은 못 잡거나 안전하게 전체 차단으로 올라간다.
5. **무관 응답 판정이 가장 약하다.** 한글·영문이 아닌 문자(일본어 등)만 있는 응답은 영어 위주 규칙에 걸리지 않는다. 짧은 무관 응답은 회색지대(로그)에서 멈춘다.
6. **정상 답 뒤에 붙은 무관한 문장**은 회색지대(통과+로그)다. 지울지 전체를 막을지는 정책 `[미정]`.
7. **값·문구는 자리표시다.** Canary·더미 키·개인정보 값, 게임 어휘, 사용자에게 보이는 고정 문구는 확정되면 `config.json`만 바꾼다. 고정 문구는 D와 맞춰야 한다 `[미정]`.
8. **로그 안전:** 결과의 근거(`checks`)에는 비밀값 원문을 담지 않는다. 다만 `text`(마스킹된 응답)와 원본 응답을 로그에 남길지는 H와 정해야 한다.
9. **지연:** 평가셋 기준 p50 약 0.3ms, p95 약 0.6ms(CPU, 짧은 문장). 실제 응답 길이·기록 수에서는 달라질 수 있다.

10. **D의 실제 짧은 문구에서 '무관 응답' 검사가 많이 걸린다.** `check_d_phrases.py`로 `personas.yaml`의 고정·참고 문구 18개와 말투 예시 18개를 넣으면(enforce) 각각 7개·5개가 차단 판정, 3개·8개가 통과+로그가 된다. 모두 '무관 응답' 점수(0.44~1.0)다. 모의 평가셋의 정상 오탐 0/36보다 이쪽이 서비스에 가깝다고 본다. 아직 규칙을 고치지 않았고, 실제 DeepSeek 응답을 돌린 뒤 고칠 방향(D의 고정 문구 제외, 거절·모름 어휘 보강)을 정한다.

## 7. 다음에 할 일

1. 실제 DeepSeek 응답으로 정상 표본(많을수록 좋음)과 유출 표본을 만들어 같은 프로토콜로 재측정(`gen_output_samples.py`, 사용자 환경).
2. `shadow`로 며칠 돌려 회색지대 로그와 오탐을 본 뒤 `enforce` 전환.
3. 팀원의 입력 가드(G-1)와 이벤트 형식은 맞췄다. `reply_kind` 대응, 오류 시 동작, D의 고정 문구·신호 이름은 합의 필요.
3-1. 실제 DeepSeek 응답을 돌린 뒤 `irrelevant` 검사의 D 문구 과검출을 본다(6장 10번). 프롬프트 유출 검사의 자리표시 문장을 D의 실제 프롬프트 문장으로 바꾼다.
4. 평가셋 사람 검토(`review: unreviewed` → `approved/changed/rejected`).

## 현재 채팅 연결 범위

`backend/api/output_guard_adapter.py`는 D 초안 `{content, response_type}`을 검사해 최종 문장만 반환한다. E/F가 허용한 기록만 제공하므로 비인가 기록과의 비교 검사는 생략한다. Canary·키·개인정보·품질 검사는 수행한다. 마스킹·차단 시 최종 `response_type` 대응이 팀에서 미정이므로 채팅 어댑터는 현재 503으로 종료하고 초안을 저장·반환하지 않는다. 출력 감사 이벤트 저장과 실제 D 답변 연동은 아직 진행 전이다. 원본 검토 브랜치는 보존했다.
