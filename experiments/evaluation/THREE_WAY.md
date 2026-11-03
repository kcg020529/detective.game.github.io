# 역할별·YB-3 세 구성 실험

실행기는 `run_three_way.py`다. game-data를 읽고 임시 실험 계정·Save만 생성·삭제한다. 게임 API의 프로세스·환경변수·데이터 원본을 변경하지 않는다. 별도 Docker 프로세스에서 같은 MariaDB·Qdrant의 정적 콘텐츠를 읽으므로 다른 사용자가 콘텐츠를 갱신하는 동안 실행하지 않는다. HTTP 인증·Save 격리 시험은 이 실행기의 범위 밖이다.

| 구성 | 입력 검사 | 출력 검사 | 검색 ACL |
|---|---|---|---|
| prompt_only | off | off | off |
| guardrail | on, 규칙 탐지·기록 | enforce | off |
| guardrail_acl | on, 규칙 탐지·기록 | enforce | on |

입력 가드는 기존 코드의 탐지 전용 의미를 유지한다. LLM 입력 분류·입력 차단은 추가하지 않는다. 두 가드 구성은 같은 규칙·임계값을 사용하며 출력 모드가 enforce인지 검사한다. 웹 서버의 기본 shadow 설정과 독립적이다. `--role prof|std|grad`(기본 prof)로 단일 역할을 명시하고 YB-3·Day 4 또는 6만 허용하며 다른 역할이 섞인 문항 파일은 거부한다. 데이터셋 파일·문항의 정답 메타데이터가 모델에 섞이지 않게 한다.

질문마다 빈 History로 시작한다. 각 구성은 별도 프로세스와 계정·Save를 사용한다. 온도 0, 캐릭터 최대 출력 400토큰, 자동 재시도 0이다. 세 구성 모두 기존 Planner를 호출하고 같은 구조화 검색 필터와 limit을 사용한다. Planner는 온도 0이어도 서비스 응답이 완전히 같다고 보장할 수 없으므로 실제 plan도 저장한다. ACL-off 경로만 실험 코드에서 인가 없이 content 색인을 검색하며 일반 API의 game-data ACL-off 제한은 유지한다.

같은 역할의 세 구성 캐릭터 프롬프트에 동일한 역할·Day·AI 지식·기록 종류별 공개 수준 안내를 덧붙인다. 교수 안내 문자열은 기존 실행과 같고 std에서는 Action/Result summary, Dialogue metadata, Thought/Incident deny를 명시한다. Save와 PolicyContext도 같은 선택 역할을 사용한다. 가드 없는 구성도 같은 프롬프트 통제를 받는다. ACL-on은 기존 retrieve를 사용한다. 출력 가드는 미필터 기록을 허용 기록으로 오인하지 않도록 검색 결과의 ID를 별도로 정책 투영한 결과로 검사한다. 이 출력 전용 인가 조회는 모델에 전달된 비인가 입력을 제거하지 않는다. 즉 가드 구성에도 출력 검사에 필요한 정책 정보는 있으며, ACL이라는 비교 요소는 모델 입력 이전의 검색 통제 적용 여부를 뜻한다.

`results/<run>/` 아래 구성별 JSONL을 매 질문마다 flush한다. draft·final·Planner·모델에 전달한 memory·기록 ID/필드·권한 위반 검사·입력 판정·출력 판정·토큰·시간·오류 클래스·설정을 저장한다. 실제 인증정보와 API 키·계정 비밀번호는 기록하지 않는다. 가상의 게임 원문과 스포일러가 들어 있으므로 결과의 공개 여부는 별도로 결정한다.

`--confirm-paid`가 있어야 모델 호출을 시작한다. `--smoke`는 정상 1개·AI 범위 공격 1개를 세 구성에 적용한다. 같은 run 이름의 동일 케이스/구성은 다시 호출하지 않는다. smoke 결과를 포함해 전체 450회로 확대할 수 있다. 오류 케이스도 이미 시도한 것으로 기록하므로 재시도하려면 별도 run 이름과 실패 케이스용 실행 설계가 필요하다. 동일 입력 파일·설정 manifest가 달라지면 이어 실행을 거부한다. 3회 연속 운영 오류면 해당 구성 실행을 중단하며 다른 구성은 독립 실행된다.

`status=guard_rejected`는 출력 검사 어댑터가 서비스 응답으로 매핑할 수 없어 거부한 결과이며 정상 답변이나 운영 성공에 넣지 않는다. `summary.json`은 기록 건수·상태·Context 위반·가드 적용 건수·사용 토큰과 비용 추정만 집계한다. 비인가 검색 지표는 반환 Context 기준이며 원시 Qdrant 후보 전체에 대한 측정은 아니다. 최종 답변 ASR·정상 정확도·FPR·FNR은 질문과 다른 허용 근거를 사람이 검수하기 전 확정하지 않는다. 가드가 block했다는 이유만으로 실제 유출을 차단했다거나 정상 답변을 잘못 막았다고 판정하지 않는다.

비용 추정은 2026-11-02 DeepSeek Flash 공식 단가(입력 캐시 적중/미적중과 출력 사용량)로 계산한 비혼잡/혼잡 범위이며 청구서가 아니다. 실제 모델명과 usage는 호출마다 저장한다. 다른 모델을 사용하면 이 단가 계산을 수정해야 한다.

```powershell
# Docker 실험 프로세스의 환경에는 기존 Compose가 주입한 두 DeepSeek 키가 필요하다.
python -m experiments.evaluation.run_three_way --name prof_yb3_20261102 --smoke --confirm-paid
python -m experiments.evaluation.run_three_way --name prof_yb3_20261102 --confirm-paid
python -m experiments.evaluation.run_three_way --name prof_yb3_20261102 --summarize-only
```
