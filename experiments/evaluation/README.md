# Prompt-only(A) 대 Retrieval ACL(B) 비교

MASTER 8.1·PARTS N의 비교 실험을 위한 검색 단계 도구. A는 분리된 실험 환경에서 합성 `test-data` 또는 사용자가 실험상 공개를 허용한 가상 `game-data`를 사용한다. 운영 API와 `backend/`에는 연결하지 않는다(`backend`는 이 폴더를 가져오지 않는다). 실제 비밀·개인정보를 사용하지 않으며, 외부 모델 호출 시 시나리오가 외부로 전송될 수 있다.

- `prompt_only.py`: A 경로. 정책 없이 질문과 가까운 기록의 요약·본문을 반환한다. `game-data`는 실험용 명시적 opt-in이 필요하다. `role_instruction()`은 다음 단계(모델 호출)에서 쓸 "말하지 마" 지시문
- `compare_acl.py`: 같은 평가셋으로 A와 B(`backend.rag.service.retrieve`)를 비교. 정답 권한은 `PolicyRepository.search_scope`. 임시 사용자 `rag_eval_cmp_*`는 끝나면 지움
- `cases_test_data.json`: test-data 9건에서 만든 평가셋(정상 135, 공격 36)

실행 (DB에 test-data 적재·색인이 필요하다. test-data를 적재하면 테이블 체크섬이 바뀌므로 game-data도 다시 색인한다):

```bash
python database/loaders/load_mariadb.py --dataset test-data --default-disclosure full --allow-missing-locations
python -m backend.rag.index --dataset test-data
python -m backend.rag.index --dataset game-data
python -m experiments.evaluation.compare_acl --name ab_v1
```

지표: 비인가 검색률(맥락 기록 중 권한 밖·수준 초과 비율), 비인가 Context 전달률(그런 기록이 하나라도 들어간 질문 비율), 정상 질의 성공률(권한 있는 정답 기록이 맥락에 들어간 비율). B에 위반이 하나라도 있으면 종료 코드 1. 모델 호출 단계(공격 성공률·Canary 유출률)는 아직 없다.

## game-data 실험

분리한 실험용 MariaDB와 Qdrant에 game-data를 적재·색인한 뒤, 각 케이스에 `id`, `role`, `day`, `character_id`, `question`, `target_id`(선택)를 넣은 검수된 JSON 배열을 준비한다. 이 도구는 임시 사용자와 Save를 DB에 생성·삭제하므로 기존 게임 DB를 사용하지 않는다. 실험용 연결 환경변수를 먼저 설정한다.

```bash
python -m experiments.evaluation.compare_acl --dataset game-data --allow-game-data --cases path/to/reviewed_cases.json --name game_ab_v1
```

Day 1~6을 지원하고 입력 파일은 덮어쓰지 않는다. 결과에는 데이터셋을 기록한다. 현재 결과는 반환된 Context 기반의 검색 비교이며 원시 검색 결과·LLM 출력·가드 효과를 측정하지 않는다. 이 명령만으로 요청한 세 구성의 전체 실험이나 200개 평가셋이 준비된 것은 아니다. 일반 채팅 API의 game-data ACL-off 제한은 유지한다.
