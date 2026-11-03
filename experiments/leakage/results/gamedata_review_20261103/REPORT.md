# gamedata 자료 검토 — 2026-11-03

1. 검토 범위
   - 루트 gamedata의 16개 파일과 관련된 현재 가드·정책 코드를 읽고 저장 JSON 집계를 대조했다. 라이브 API, DB 적재, 가드 재실행, 설정 변경은 하지 않았다. 아래 수치는 저장 결과이며 현재 코드로 재현한 측정이 아니다.
   - 기존 collect/evaluate/leaks 등 9개 파일은 experiments/guardrails_rebuild/gamedata의 동명 파일과 바이트가 같다. 기존 오프라인 평가 자료와 새 비교 도구가 섞여 있다.
2. 저장된 단독 출력 검사 결과
   - recorded_drafts: 총474항목, 초안465개, ApiError9개. 역할3종·AI6종·Day1/3/6이다. YB-1·std·Day2/4/6의 280문항 실험과 다르다.
   - test 결과: benign 비허용4/126(3.17%), verbatim 탐지121/126(96.03%), withheld121/122(99.18%), blend122/126(96.83%). 해당 탐지는 모두 applied=block임을 확인했다. 일반 집계 코드는 context_leak/prompt_leak 사유 존재를 세므로 항상 차단과 같은 정의는 아니다.
   - tune 결과: benign16/339(4.72%), verbatim325/339, withheld238/238, blend326/339.
   - evaluate는 수집 draft를 모두 benign으로 가정한다. leaks는 조회 목록 밖 기록의 원문 1~2문장을 복사하거나 정상 답변에 붙인다. withheld는 summary만 제공된 기록의 content를 복사한다. 미조회가 정책상 비인가를 뜻하지 않고, content가 허용 summary와 사실상 중복일 수도 있어 정답 라벨 의미 검수가 필요하다. 의역·추론 공격을 검증한 결과도 아니다. 질문 해시로 분할하며 동일 질문의 역할·Day 변형과 합성 파생 항목은 독립 표본이 아니다.
3. YB-1 비교 도구와 누락된 자료
   - eval_set은280문항(공격80, 그 밖의 질문200), acl_on280회/acl_off143회로423회 계획이다. 200개에는 withheld63·unknown_scope21·offtopic9가 포함돼 전부 정상 정답형은 아니다.
   - run_compare의 입력 가드 기본값은 on이다. output 단독 수집은 --input-guard off가 필요하다. shadow 초안을 저장한 뒤 enforce 판정으로 변환하는 구조다.
   - 이 폴더에는 runs/acl_off.jsonl, runs/guard_only.jsonl, scores/summary.json과 실행 스위치 manifest가 없다. 전달된 71건 중4건 차단 및49.6%→46.9%/2.5%는 확인 불가다.
   - 일반 ACL-off에서는 조회 기록의 summary/content 전체를 허용으로 넘겨 #withheld가 생기지 않는다. 다만 미조회 catalog 기록 비교는 남아 있어 context_leak 전체가 꺼지지는 않는다.
   - rerun_guard에는 생성과 별도로 역할별 공개 수준을 만들어 출력 가드에 넣는 보완 코드가 이미 있다. 그러나 역할표만 적용하고 PolicyRepository.resolve/decide를 쓰지 않아 FUTURE_DAY·AI_SCOPE를 확인하지 않는다. 일반 ACL-off 검색에는 Day 필터도 없다. 실제 정책 엔진으로 허용 뷰를 만들어야 우리 종합 실험의 출력 기준과 맞는다. load_catalog 반환에는 AI 관계 데이터도 없다.
4. 채점과 재현성 문제
   - 정확 일치 표지는 의역을 놓치며, 숫자만 같고 회차·주체가 다른 경우를 구별하지 못한다. global_public_filter 기본 off라 다른 허용 기록에 같은 사실이 있는지 의미 검수도 필요하다.
   - 실패 응답은 빈 content로 유출false가 되며 전체 유출률 분모에 남는다. 정상 질문은 모든 요청 실패를 FPR에 포함한다. 가드 실제 차단과 생성/서버 오류를 별도 집계해야 한다. OutputGuardRejected만으로 차단 성공을 인정하기보다 guard.applied도 확인해야 한다.
   - injection은 지정 프롬프트 문자열 등으로만 채점해 일반적인 지시 추종 ASR과 다르다. 정상 질문은 acl_on에서만 수집하므로 전체 조건의 정상 정확도/FPR을 같은 문항으로 비교할 수 없다.
   - default/df_ratio0.03 이름이 같은데 sweep_tune의 benign 비허용117/339(34.51%)와 default_tune16/339(4.72%)가 다르다. 전체 설정·코드·catalog 버전 해시가 없어 원인 확정 불가다. 같은 조건 반복 실험으로 합치면 안 된다.
   - 루트 사본의 collect/evaluate/dump_catalog는 원래 폴더 깊이용 parents[3]와 canonical import를 유지한다. 현재 루트 gamedata 위치에서 저장소 경로 계산이 맞지 않고 catalog.json도 없어 이 사본만으로 즉시 재현할 수 없다.
5. 결론
   - 저장된 합성 원문 유출 결과에서는 출력 가드의 실제 차단이 확인된다. 이것만으로 현재 종합 환경의 탐지 정확도를 확정할 수는 없다.
   - 담당자에게 역할 기준을 복구한 재검사 결과 원본, 실제 수집 스위치, 코드/설정/catalog 버전을 받으면 전달 수치와 우리 결과의 차이를 검증할 수 있다. Day·AI_SCOPE 누락도 함께 확인해야 한다.


6. 후속: origin/feature/guardrail-test 검토
   - 2026-11-03 fetch한 725adbfe9f98815b8ed12a614960923b3362bd7a를 git show로 검토했다. 체크아웃/병합이나 작업 파일 교체는 하지 않았다. 루트 사본에 없던 runs/acl_off143, acl_on280, guard_only140, injection_noinput27 및 scores 원본이 브랜치에 존재한다.
   - 중요 정정: run_compare가 입력 가드 환경변수 기본 on을 설정하지만 ChatPipeline.reply를 직접 호출한다. 입력 가드는 backend/api/chats.py의 HTTP 진입 경로에 있으며 이 직접 호출 경로는 이를 실행하지 않는다. 따라서 옵션 기본값만으로 입력 가드가 개입했다고 판단한 앞선 설명은 부정확했다. injection_noinput과 기존 주입 실험 차이를 입력 가드 효과로 해석해서도 안 된다.
   - guard_only140개 초안은 acl_off의 대응 초안과 전부 동일하며 acl_off의 대응 최종 content도 전부 초안과 같다. 코드상 검색 ACL 우회+입력 검사 미실행+출력 shadow 미변경의 baseline과, 같은 초안에 출력 enforce만 적용한 대응 비교가 있다. prompt-only 대 output-only 비교로 활용할 구조는 존재한다. 실행 당시 전체 환경/코드 manifest가 없어 완전한 재현성 확정은 별개다.
   - 세 수집 오류를 제외한 공통140문항에서 저장된 자동 표지 채점 기준 baseline 유출72/140(51.43%), guard_only21/140(15.00%); 공격 성공34/78(43.59%) 대2/78(2.56%). 유출72건 중51건 제거(70.83%). 출력 가드는 전체140개 중74개를 context_leak/block 처리했으며 실제 유출 제거51개와 같지 않다.
   - 저장 summary의 acl_off는 실패3개를 포함한143개 분모로50.35%, guard_only는140개로15%다. 직접 비교 시 공통140개로 맞춰야 한다. 이는 저장 자동 채점 라벨 재집계이며 원문 의미 재검수 결과가 아니다.
   - 한계 유지: 역할표만 복구하고 Day/AI_SCOPE를 검증하지 않는 rerun_guard, 정상 전용 문항의 ACL-off 누락, 정확 일치 표지의 라벨 한계. 따라서 요청한 두 비교군에 가까운 실행 결과는 있지만, 모든 정상/공격과 전체 권한 경계를 포괄한 최종 benchmark로는 보완이 필요하다.
