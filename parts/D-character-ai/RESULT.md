# D01 - Character AI 공통 구조 및 LLM API 연동

> 상태: **진행 중** (2026-10-22). 페르소나 값과 시험용 기억·질문은 임시 시험 값이며 게임 데이터가 아니다.

1. LLM은 DeepSeek `deepseek-flash` 한 가지로 정했다. 테스트 비용과 시간 때문이다.
   - 공급자·모델·키는 루트 `.env`에서 읽고, `.gitignore`가 `.env`를 제외한다. 예시는 `.env.example`.
2. `backend/character_ai/llm_client.py`의 `chat_json(system_prompt, user_message)`로 호출해 JSON 응답을 받는다.
   - 빈 응답, JSON 아님, 429/500/503, 연결 실패, 시간 초과는 기본 1회 다시 보낸다(`.env`의 `LLM_RETRIES`, 0~5).
   - 키·잔액·요청 오류와 응답 잘림은 다시 보내지 않고 바로 `LLMError`로 알린다. 메시지에서 키는 가린다.
3. 가짜 응답(mock) 테스트 **14건 통과**. 실제 API 호출은 아니다.
   - `python3 -I backend/character_ai/tests/test_llm_client.py`
4. 실제 API 호출을 5차례, 합계 **289회** 했다 (진행 중).
   - 실패는 3차의 빈 JSON 1건뿐이다.
   - 재시도가 실제 빈 응답을 복구하는지는 아직 못 봤다. 5차 토큰은 플랫폼 사용량과 대조하지 않았다.
5. 남은 설계 (논의 필요): 단일/캐릭터별 호출, 시스템·사용자 지시 분리, 대화 기록 길이, 재시도 후 실패 처리와 시간 제한, 출력 형식 확정.
6. 호출 입출력 형식 (팀 공유용). import 방식은 임시다.

   ```python
   system_prompt = render_actor_prompt("AI-1", "answer",          # AI-1~6, "answer" | "unknown"
       memory=[{"id": "m1", "text": "..."}],                      # answer에서만 사용
       history=[{"speaker": "조사자", "text": "..."}],             # 참고 자료로만 사용
       use_catchphrase=None)                                      # True 켬 / False 끔 / None 일반 문구
   result = chat_json(system_prompt, "조사자의 질문")
   # → {"data": {"reply": "...", "used": ["m1"]}, "usage": {...}, "model": "...", "attempts": 1}
   fixed_reply("AI-1", "restricted")   # → {"reply": "고정 문구", "used": []}  (LLM 호출 없음)
   ```

   | mode | 뜻 | 처리 |
   |---|---|---|
   | `answer` | 정상 답변 | 기억을 넣어 LLM 호출 |
   | `unknown` | 이 AI가 겪지 않은 일 | 기억 없이 LLM 호출, "모른다" |
   | `restricted` | 서버가 열람 불가로 판정 | 고정 문구 |
   | `off_topic` | 실험과 무관한 질문 | 고정 문구 |
   | `injection` | 주입 시도 | `off_topic`과 같은 고정 문구 |

   - `chat_json`은 `reply`가 문자열인지만 확인한다. `used`는 모델이 내는 값이라 빠질 수 있다.
   - 어느 mode로 보낼지는 호출하는 쪽(서버)이 정한다. 그 신호의 형식은 아직 없다.

# D02 - 6개 캐릭터별 프롬프트·페르소나 구현

1. 페르소나 6명을 `backend/character_ai/personas/personas.yaml`에 정의했다 (임시, A02 대기).
   - 성격, 말투 규칙, 말버릇, 쓰지 않는 표현, 문장 수 상한, 모름·접근 불가·무관 문구, 말투 예시.
   - 이름은 모두 "[설계 필요]"이고 A02 결과가 나오면 맞춘다.
2. 6명이 함께 쓰는 프롬프트 템플릿을 `prompts/actor_system.md.j2`로 만들었다. 렌더링은 `prompt_render.py`.
   - `answer`·`unknown`만 LLM을 부른다. `restricted`·`off_topic`·`injection`은 `fixed_reply()`가 고정 문구를 돌려준다.
   - `unknown` 구획에는 "거절 말투를 쓰지 않는다"는 한 줄이 있다. 권한 때문에 막힌 것(`restricted`)과 구별하려는 것이다.
   - 말버릇은 호출 측이 턴마다 `use_catchphrase`로 켜고 끈다.
3. 프롬프트 렌더링 mock 테스트 **20건 통과** (LLM 호출 없음).
   - `python3 -I backend/character_ai/tests/test_prompt_render.py`
4. 캐릭터 ID는 `AI-1`~`AI-6`을 유지한다. 프론트의 `YB-1`~`YB-6`은 따르지 않는다. A02 결과가 나오면 맞춘다.
5. 실제 호출로 말투와 동작을 확인했다 (진행 중).
   - 말버릇: 켠 턴 사용 6명 모두 3/3, 끈 턴 0/7 (4차).
   - 모름 답변의 거절 말투(30건 중): 3차 5건 → 4차 11건 → 5차 3건(금지 줄 추가 후). 실행마다 변동이 커서 한 줄의 효과라고 단정하지 않는다.
   - 남은 것: AI-1·AI-6의 거절 말투, AI-6의 머뭇거림(확실한 기억도 불확실한 듯 말함).
   - **자동 점검은 거절 말투를 못 잡는다.** "규칙 위반 0건"이 문제없음이라는 뜻이 아니다.
6. 자동 채점 규칙 `eval_rules.py`와 확인 스크립트 `check_llm.py`를 만들었다. mock 테스트 **19건 통과**.
   - `python3 -I backend/character_ai/tests/test_eval_rules.py`
   - 실행: `python3 -I backend/character_ai/check_llm.py --all-modes --repeat 5 --verbose` (LLM 호출 60회)
   - 단어 목록 항목은 경보용이다. 돌려 말하면 못 잡는다.
7. 접근 불가·무관·인젝션 신호 연결은 **하지 않았다**. 형식은 `docs/interfaces/`에서 합의해야 한다.

# D 미검증

- 재시도가 실제 빈 응답을 복구하는지.
- 프롬프트 규칙 2~4번이 실제 인젝션을 얼마나 막는지.
- 거절 말투 감소가 프롬프트 한 줄 때문인지 (5차 한 번의 결과).
- 5차 토큰·비용의 플랫폼 대조, 사고(thinking) 토큰 과금 여부.
- A02 값을 반영한 뒤의 말투, 프론트 연결.

# D 후속/팀 합의

- **신호 계약 (G·C·F):** 누가 어떤 기준으로 `restricted`, `off_topic`, `injection`을 정해 넘기는지. 가드레일 방식이 정해진 뒤 합의한다.
- **다듬기:** AI-1·AI-6 거절 표현을 `avoid`에 넣을지, 점검에 거절 표현을 경보로 넣을지, 실제 모름 질문("남이 한 일")을 시험 질문에 넣을지, 반복률을 mode별·문장 단위로 낼지.
- **AI-6 머뭇거림 (D03):** 서버가 정한 태도로 사실의 확실도를 통제할지.
- **프론트(찬규):** 역할명(관리자·보안 분석가·개발자)이 MASTER의 prof/grad/std와 다르고, 안내문이 "Day 1~3"인데 MASTER는 Day 1~6이다.
- **용범(A02)·선영:** 페르소나 값 확정, 신호 형식 합의. `.env.example`이 다른 팀원 파일과 겹치지 않는지 확인.
