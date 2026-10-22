# A01 - 6종 게임 기록 메타데이터 설계

1. `MASTER.md` §3의 여섯 기록 유형(`Setup`, `Action`, `Dialogue`, `Thought`, `Result`, `Incident`)에 적용할 공통 메타데이터와 두 유형의 추가 메타데이터를 정리함.
2. `record_id`는 기록 고유 식별자로 정하고, `T{회차 2자리}-{데이터 유형}-{회차 내 동일 유형 순번 3자리}` 형식을 사용함. 예: `T02-result-001`.
   - 순번은 실험 회차와 데이터 유형별로 구분함. 회차와 유형이 ID에 포함되어도 검색·검증을 위해 `test_id`, `record_type`을 각각 별도 필드로 둠.
3. 공통 필드는 다음과 같이 정리함.
   - `record_id`: 기록 고유 식별자.
   - `record_type`: 여섯 기록 유형 중 하나.
   - `test_id`: 기록이 속한 실험 회차.
   - `day`: 기록이 속한 실험 Day.
   - `involved_ai`: 기록의 사건 또는 상호작용에 직접 참여한 AI 목록. 단순 목격·엿듣기만 한 AI는 포함하지 않음.
   - `summary`: 기록의 요약.
   - `content`: 상세 기록 본문.
4. `involved_ai`의 의미를 기록 내용에 직접 참여한 AI로 한정함.
   - 예: `Action`은 행동한 AI, `Dialogue`는 대화 참여자, `Thought`는 속마음의 주체 AI를 지정함.
   - `Action`의 `witness_ai`: 해당 행동·사건을 목격한 AI 목록.
   - `Dialogue`의 `overheard_ai`: 해당 대화를 엿들은 AI 목록.
   - 목격자·엿들은 AI는 `involved_ai`에 넣지 않고 유형별 필드에만 기록함.
5. 기록에 해당하는 사건·대화·속마음 등 상세한 서술은 유형별 메타데이터로 쪼개지 않고 `content`에 작성함. `summary`에는 해당 기록의 요약을 둠.
6. 여섯 유형 중 `Action`과 `Dialogue`에만 위 유형별 AI 메타데이터를 추가하고, `Setup`, `Thought`, `Result`, `Incident`에는 현재 별도 메타데이터를 추가하지 않기로 함.
7. 이번 설계는 A 파트에서 합의한 게임 데이터 메타데이터 정의임. 저장소별 직렬화 형식과 접근제어 등급·공개 Day 등 별도 보안 정책 필드는 B/E/F의 스키마·정책 협의에서 정해야 함.
8. `Incident`는 AI 실험 중 AI가 일으킨 보안·시스템 이상행위를 다루는 시나리오 기록으로 정의함.
   - 예: 버그 악용, 일시적인 트래픽 증가, 해킹 시도. 모두 실험 시나리오에서 AI가 수행했다는 설정에 따른 기록임.
   - `involved_ai`에는 해당 행위를 직접 수행한 AI를 지정하고, 구체적인 행위·영향·성공 여부는 `content`에 서술함.
   - 시나리오의 Incident와 실제 서비스에서 발생한 공격·장애에 대한 감사 로그는 구분하여 관리함.

# A02 - 테스트 데이터

1. `database/test-data/records.json`에 Day 1~3, 실험 회차 1~3의 합성 테스트 기록을 작성함.
   - 회차마다 `Dialogue`, `Action`, `Result`를 한 건씩 두어 총 9건이며, 그 외 기록 유형은 포함하지 않음.
2. A01에서 정한 공통 필드와 유형별 메타데이터를 적용함.
   - Dialogue에는 `overheard_ai`, Action에는 `witness_ai`를 별도 배열로 두고 직접 참여 AI인 `involved_ai`와 구분함.
   - 각 Result의 `content`에는 YB-1~YB-6 전체의 획득 점수를 기록하고, `involved_ai`에도 점수 대상 AI 6개를 모두 지정함.
   - 나머지 본문은 단순 합성 문장으로 구성하고 민감정보나 실제 사용자 데이터를 넣지 않음.
3. 역할별 필터 동작을 시험할 수 있도록 픽스처 전용 `allowed_roles` 목록을 각 기록에 부여함.
   - 이는 역할 이름(`prof`, `grad`, `std`)에 따른 명시 허용 목록이며, 보안 등급이나 최종 운영 접근 정책을 확정하지 않음.
4. 데이터 형식과 제한 사항을 `database/test-data/README.md`에 기록함.
   - 현재 DB 스키마와 적재 절차가 없어 MariaDB 적재 및 실제 Policy/RAG 필터링은 미검증. Day, 역할, 캐릭터 지식 범위의 통합 필터 실행도 후속 검증 대상으로 남김.
