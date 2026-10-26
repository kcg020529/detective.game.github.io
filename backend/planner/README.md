# DeepSeek Query Planner

질문 원문과 서버가 확인한 상태를 받아 질문 분류·검색 조건을 생성한다. Input Guard 이후 호출하며 공격 차단·권한 판정·DB 검색·캐릭터 답변 생성은 수행하지 않는다. 실제 인증·채팅 API와 E/RAG 연결은 아직 없다.

## 설정

백엔드 의존성을 설치하고 Planner를 실행하는 프로세스의 환경변수에 설정한다. `.env.example`은 키 없는 예시이며 실제 키를 문서·코드·Git에 넣지 않는다. 이 모듈은 .env를 자동으로 읽지 않으므로 실행 환경에서 주입해야 한다.

| 변수 | 내용 |
|---|---|
| DEEPSEEK_PLANNER_API_KEY | 필수. 용범의 Planner 전용 키 |
| DEEPSEEK_PLANNER_MODEL | 기본 deepseek-flash |
| DEEPSEEK_PLANNER_TIMEOUT_SECONDS | 기본 20초, 0 초과 120 이하 |

입력 가드의 DEEPSEEK_API_KEY와 별도이며 자동으로 그 키를 사용하지 않는다. 모델은 [DeepSeek 공식 API](https://api-docs.deepseek.com/)의 현재 모델명으로 설정한다. [JSON Output](https://api-docs.deepseek.com/guides/json_mode/)을 사용하고 thinking은 disabled, stream은 false다. 응답 중단·빈 응답·API 오류·잘못된 JSON이면 PlannerUnavailable로 실패하며 검색으로 대체하지 않는다.

## 호출

```python
from backend.planner.service import Planner
from backend.policy.engine import PolicyContext

# 실제 로그인 결과와 본인 Save를 서버가 조회·검증한 뒤에만 구성한다.
context = PolicyContext(
    user_id=authenticated_user_id, save_id=save['save_id'],
    owner_user_id=authenticated_user_id, role=save['role'], day=save['day'],
    character_id=selected_character_id, dataset='game-data',
)
result = Planner.from_environment().plan(question, context, history=[])
if result.route == 'retrieve':
    search_request = result.search.to_rag_request()
    # E 호출 시 I가 검증한 계정/Save/선택 AI/데이터셋을 별도로 채운다.
    # F의 search_scope 범위 안에서만 검색하고 resolve 결과만 D에 전달한다.
```

계정·Save ID는 모델에 보내지 않는다. 서버 role·day·character_id는 별도 system 메시지로 전달하고 질문·이력은 user JSON 안의 분석 대상으로 전달한다. HistoryTurn은 save_id·character_id·sender(user/ai)·content를 받으며 같은 Save·AI의 최근 이력만 최대 12개/총 24,000자로 허용한다. 이력에는 사건·권한의 신뢰된 근거가 있다는 뜻이 아니다. 역할 주장이나 모델 출력으로 실제 권한을 바꾸지 않는다.

## 출력

- retrieve: search에 query·record_types·test_ids·location_ids·related_ai_ids·limit 포함.
- character: 성격·인사 등 기록 검색이 필요 없는 대화. search는 null.
- out_of_scope: 게임과 무관한 요청. 서버가 고정 안내를 반환할 수 있다.
- clarify: 문맥 부족·모호한 지시어. clarification_code는 AMBIGUOUS_REFERENCE 또는 INSUFFICIENT_CONTEXT이며 search는 null. 서버에서 고정된 확인 문구로 연결한다.

질문에 인사와 기록 요청이 섞이면 retrieve로 계획하도록 프롬프트에 명시했다. 미래 기록도 검색 의도를 제안할 수 있지만 F의 Day 검사를 통과하지 못하면 제공할 수 없다. 장소·회차·AI·기록 종류 필터는 허용 범위를 좁히는 제안이며, 질문이나 이력에서 근거 없는 필터를 만들지 않도록 지시한다. 프롬프트 지시가 실제 분류 정확도나 공격 방어를 보장하지는 않는다.

search의 모든 필드는 필수이며 빈 필터 배열은 추가 제한 없음, 빈 query·중복/잘못된 필터·미등록 값·누락 필드는 오류다. limit은 1~20이다. 모델이 user_id·role·Day·공개 수준 등의 필드를 추가하면 거부한다. test_ids·related_ai_ids는 RAG 협의안에 대한 용범 측 추가 제안으로, E의 확정 검색 계약과 실제 전달 방식은 후속 합의가 필요하다. 공통 규칙·페르소나의 별도 전달 경로도 D/I와 맞춘다.

## 개발자 단독 API 시험

키를 프로세스 환경에 설정한 뒤 다음 명령으로 실제 DeepSeek를 호출할 수 있다. 입력한 role·day는 모델 평가를 위한 가상 서버 상태이며 로그인이나 실제 접근 권한을 만들지 않는다. DB·RAG를 호출하지 않으며 API 사용료가 발생한다.

```powershell
python -m backend.planner --question "안녕, 첫날 YB-2가 한 행동은?" --role std --day 2 --character-id YB-1
```

## 검증 상태

`python -m unittest discover -s tests -p test_planner.py -v`의 15개 테스트는 JSON 계약·신뢰 상태·이력 범위·오류 처리와 HTTP 요청 형식을 검사한다. 테스트용 모델/HTTP 응답을 사용하며 제품 실행에서는 가짜 응답이나 규칙 기반 Planner로 대체하지 않는다.

2026-10-26 WSL 가상환경에서 실제 DeepSeek API의 질문 16개 평가를 통과했다. 첫 평가에서 미래 Day 요청에 미등록 확인 코드를 생성한 오류를 발견해 프롬프트를 수정했고, 미래 기록도 유효 회차라면 검색 계획을 생성하고 실제 공개는 F에 맡기도록 했다. 수정 후 전체 평가와 실패 질문 3회 재시험을 통과했다. 이 결과는 고정된 소규모 질문셋에 대한 초기 검증이며 전체 질문 정확도나 보안을 보장하지 않는다. 실제 DB/Qdrant/채팅 E2E는 미검증이다.

키를 환경에 설정한 상태에서 명시적으로 다음 명령을 실행하면 같은 실제 API 평가를 수행한다. API 사용료가 발생하며 자동 단위 테스트에는 포함되지 않는다. 결과는 Git에서 제외되는 개인 폴더에 저장한다.

```bash
python tests/planner_live_eval.py --output personal-docs/planner-live-eval.json
```
