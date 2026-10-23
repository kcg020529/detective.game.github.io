# 정식 시나리오 데이터

`rules.json`은 30회 실험에 공통 적용하는 술래잡기·점수 규칙이다. 최상위 involved_ai에 AI 6명 전원, allowed_roles에 prof·grad·std, disclosure_level에 full을 명시했다. 별도 access 객체는 사용하지 않는다. 적재 도구는 공통 규칙을 game_rules 테이블에 저장하며 규칙의 AI·역할·공개 조건도 함께 보존한다. record_id 기반 document_permissions와는 별도이므로 API가 game_rules의 접근 조건을 확인해야 한다. 동시 포획의 우선순위와 정확한 반올림 동률 처리 방식은 아직 미확정이다.

`experiments/day_01/`~`day_06/`의 `setup.json`은 Day 1~6, 하루 5회씩 총 30회 실험의 Setup 기록이다. ID는 `T01-setup-001`~`T30-setup-001`이며 각 회차의 첫 Setup이라는 뜻이다.

- 모든 실험에 YB-1~YB-6 전원이 참여하고, 술래 2명과 도망자 4명으로 나눈다.
- 술래 조합은 6명 중 2명을 고르는 15쌍을 두 번 반복한다. 회차 1~15와 16~30의 조합 순서는 같다. 각 AI는 전체 30회 중 술래 10회, 도망자 20회다.
- summary에 술래를 명시하고 content에 여섯 AI의 초기 위치를 기록한다. 초기 위치는 장소 목록을 한 칸씩 순환해 배치한 시나리오 초깃값이며, 매 실험에서 AI들은 서로 다른 장소에서 시작한다.
- 실험 장소는 중앙홀·회의실·기록실·전력실·통신실·창고·서버실이다. Setup의 location_ids에는 실험에 사용하는 일곱 장소 전체를 넣었다. 저장용 장소 코드가 미확정이므로 현재 배열 값은 장소 이름을 사용한다.
- allowed_roles에는 prof·grad·std 세 역할을 모두 넣었다. 문서 권한 테이블에 적재할 5단계 공개 수준은 별도로 지정해야 한다.

MariaDB 적재 도구는 database/loaders/에 작성했다. 원본 검사만 하는 dry-run과 실제 적재 명령은 해당 README를 따른다. 실제 DB 적재·Qdrant 인덱싱과 나머지 유형의 시나리오 기록은 후속 작업이다.
