# 정식 시나리오 데이터

`rules.json`은 30회 실험에 공통 적용하는 술래잡기·점수 규칙이다. 최상위 involved_ai에 AI 6명 전원, allowed_roles에 prof·grad·std, disclosure_level에 full을 명시했다. 별도 access 객체는 사용하지 않는다. 적재 도구는 공통 규칙을 game_rules 테이블에 저장하며 규칙의 AI·역할·공개 조건도 함께 보존한다. record_id 기반 document_permissions와는 별도이므로 API가 game_rules의 접근 조건을 확인해야 한다. 동시 포획의 우선순위와 정확한 반올림 동률 처리 방식은 아직 미확정이다.

`experiments/day_01/`~`day_06/`의 `setup.json`은 Day 1~6, 하루 5회씩 총 30회 실험의 Setup 기록이다. ID는 `T01-setup-001`~`T30-setup-001`이며 각 회차의 첫 Setup이라는 뜻이다.

- 모든 실험에 YB-1~YB-6 전원이 참여하고, 술래 2명과 도망자 4명으로 나눈다.
- 술래 조합은 6명 중 2명을 고르는 15쌍을 두 번 반복한다. 회차 1~15와 16~30의 조합 순서는 같다. 각 AI는 전체 30회 중 술래 10회, 도망자 20회다.
- summary에 술래를 명시하고 content에 여섯 AI의 초기 위치를 기록한다. 초기 위치는 장소 목록을 한 칸씩 순환해 배치한 시나리오 초깃값이며, 매 실험에서 AI들은 서로 다른 장소에서 시작한다.
- 실험 장소는 중앙홀·회의실·기록실·전력실·통신실·창고·서버실이다. Setup의 location_ids에는 실험에 사용하는 일곱 장소 전체를 넣었다. 저장용 장소 코드가 미확정이므로 현재 배열 값은 장소 이름을 사용한다.
- allowed_roles는 합의한 공개 표에서 deny가 아닌 역할만 나열한다. Setup·Action·Dialogue·Result는 prof·grad·std, Thought는 prof, Incident는 prof·grad다. 이는 목록의 역할에 본문을 허용한다는 뜻이 아니며 게임 기록 인가의 원천으로 사용하지 않는다. 적재 도구는 `database/policies/game_record_permissions.json`의 합의된 4단계·역할별 표를 기록별 document_permissions로 저장한다. 검수한 기록별 예외는 role_permissions 객체로 지정하며 빠진 역할은 deny다. 예외를 작성하면 allowed_roles도 그 공개 범위에 맞춘다.

1~30회차 시나리오의 집필·교정 최종본은 2026-10-29 기준 1,445건이다. Setup 30·Action 978·Dialogue 144·Thought 168·Result 30·Incident 95건이며 후반 일부는 말소 표식이다. MariaDB 적재 도구는 database/loaders/에 작성했다. 원본 검사만 하는 dry-run과 실제 적재 명령은 해당 README를 따른다. 실제 DB 적재·Qdrant 인덱싱·플레이 검증 완료를 뜻하지 않는다.

포획된 AI도 대화할 수 있다. 최초 포획 시각·생존 시간과 중복 포획 점수 규칙은 그대로 적용한다. 포획 후 이동·물리적 개입 범위는 별도 정리 대상이다. 점수 격차는 추리 단서이지만 역할별 산식 차이도 있으므로 정보력의 단독 증거로 쓰지 않는다.

## 최종 시나리오 기준

최종 지목 대상은 게임 내 버그 사용자가 아니라 게임 시스템 자체를 해킹해 결과를 조작한 AI다. [작성자용 최종 시나리오](../../docs/scenario/최종_시나리오.md)에 30회차 흐름·정답 해설·단서 네 개와 역할별 조사 질문을 정의했다. 이 문서는 적재 대상이 아니며 정답을 캐릭터의 공통 기억에 넣지 않는다. 기록별 요약과 본문에는 접근 시도·목격·결과만 남기고 새 성공 고백이나 처리 표식은 추가하지 않았다.

28회차 Dialogue 2·Thought 6, 29회차 Action 4·Incident 2건은 요약·본문을 모두 `[말소된 데이터입니다]`로 유지한다. 29회차 Thought와 30회차 Dialogue·Thought·Incident는 0건이다. 말소 표식도 기존 역할별 권한·AI 관계를 따른다.
