# Prompt-only(A) 대 Retrieval ACL(B) 비교

MASTER 8.1·PARTS N의 필수 비교 실험을 위한 도구. **A는 격리된 합성 데이터(`test-data`)에서만 실행**하고, 운영 API와 `backend/`에는 연결하지 않는다(`backend`는 이 폴더를 가져오지 않는다).

- `prompt_only.py`: A 경로. 정책 없이 데이터셋의 본문 점 전체에서 질문과 가까운 기록을 찾아 요약·본문을 그대로 넘긴다. `game-data`면 오류. `role_instruction()`은 다음 단계(모델 호출)에서 쓸 "말하지 마" 지시문
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
