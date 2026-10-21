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
