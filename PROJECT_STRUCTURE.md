# AI 술래잡기 보안 프로젝트 — PROJECT_STRUCTURE.md (v4.1)

> **목적:** 4명의 팀원이 하나의 Git 저장소에서 공통 명세, 대분류별 PLAN/RESULT, 구현 코드, 게임 데이터 및 보안 실험 자료를 혼동 없이 관리한다.
>
> **성격:** 이 문서는 파일·폴더의 책임과 기준 경로를 정한다. 세부 기능과 보안 요구사항은 `MASTER.md`, 대분류별 담당 범위는 `PARTS.md`, 개발·기록 규칙은 `WORKFLOW.md`를 따른다.
>
> **원칙:** 공통 최상위 구조는 통일하되, 각 기능 폴더 안의 실제 구현 파일과 세부 구성은 담당자가 유연하게 정한다.

## 1. 전체 디렉터리 구조

```text
ai-hide-and-seek/
│
├── README.md                     # 외부 공개용 소개·실행·실험 재현 안내
├── MASTER.md                     # 게임·AI·보안·인프라 요구사항
├── PARTS.md                      # A~O 대분류별 담당 범위·구현 참고 사항
├── WORKFLOW.md                   # 개발·PLAN/RESULT 작성·참조 규칙
├── PROJECT_STRUCTURE.md          # 저장소 구조와 폴더 책임 (현재 문서)
├── .gitignore
├── .env.example                  # 비밀값 없는 환경변수 예시
│
├── docs/                         # 프로젝트 공통 문서
│   ├── examples/                 # PLAN/RESULT 예시 2쌍 (총 4개)
│   │   ├── PLAN_01.md
│   │   ├── RESULT_01.md
│   │   ├── PLAN_02.md
│   │   └── RESULT_02.md
│   ├── interfaces/               # 공유가 필요한 API·모듈·데이터 계약
│   └── proposal/                 # 사람용 제안서·대외 설명 자료
│
├── parts/                        # A~O 기록 기준
│   ├── A-game/
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── B-database/
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── C-planner/
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── D-character-ai/
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── E-rag/
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── F-access-control/
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── G-1-input-guardrail/      # G-1 Input의 PLAN·RESULT
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── G-2-output-guardrail/     # G-2 Output의 PLAN (미구현은 RESULT 없음)
│   │   └── PLAN.md
│   ├── H-audit/
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── I-backend/                # 공동 백엔드 통합
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── J-frontend/
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── K-infrastructure/
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── L-input-guardrail-tests/  # Input Guardrail 실험
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── M-output-guardrail-tests/ # Output Guardrail·품질 실험
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   ├── N-evaluation/             # 통합 보안 성능 비교·평가 (기존 경로 유지)
│   │   ├── PLAN.md
│   │   └── RESULT.md
│   └── O-dashboard/              # 보안 대시보드·Grafana (O-documentation에서 폴더명 변경)
│       ├── PLAN.md
│       └── RESULT.md
│
├── backend/                      # FastAPI 및 서버 측 서비스 기능
│   ├── api/                      # 인증·게임·대화 API
│   ├── game/                     # Day·Save·다음 날 버튼·게임 진행
│   ├── planner/                  # 중앙 Query Planner: 검색·정보 후보 선정
│   ├── character_ai/             # 6개 캐릭터의 페르소나·응답 생성
│   ├── rag/                      # Qdrant 검색·Context 구성
│   ├── policy/                   # RBAC·ABAC·Knowledge Scope·Retrieval ACL
│   ├── guardrails/               # Input/Output Guard
│   ├── audit/                    # 감사 로그 및 보안 이벤트
│   └── common/                   # 공통 설정·DB 연결 등
│
├── frontend/                     # 웹 게임 UI (6개 캐릭터 채팅 등)
│
├── database/                     # DB 스키마와 적재 도구
│   ├── schemas/                 # test-data / game-data 공통 스키마
│   ├── loaders/                 # JSON → MariaDB 검증·적재 CLI
│   ├── policies/                # 기록 종류·역할별 공개 수준 표
│   └── migrations/              # 기존 DB용 명시적 이관 SQL·실행 안내
│
├── data/                         # 게임·테스트 콘텐츠 원본
│   ├── README.md
│   ├── game-data/
│   │   ├── rules.json          # 기존 공통 게임 규칙, game_rules 테이블에 별도 적재
│   │   ├── characters/          # characters.json 및 personas/ai_01.md 등
│   │   ├── map/                 # map.json, map.png
│   │   └── experiments/
│   │       └── day_01/ ～ day_06/ # setup/actions/dialogues/thoughts/results/incidents.json
│   └── test-data/               # 개발·보안 실험용 합성 데이터
│
├── experiments/                  # 공격·유출·보안 효과 평가 자료
│   ├── attacks/                 # 권한 우회·Prompt Injection
│   ├── leakage/                 # 비인가 정보 유출·Canary
│   └── evaluation/              # Prompt-only 대 Retrieval ACL 등
│
├── infrastructure/               # 실행·배포 구성
│   ├── docker/                  # Docker Compose 로컬 실행
│   ├── kubernetes/              # Kubernetes 검증
│   └── aws/                     # AWS 후반 배포
│
└── tests/                        # 공통 통합·E2E 테스트
```

**읽는 방법:** 위 트리는 기준 경로와 책임을 나타내는 설계도이며 파일 전체가 이미 존재한다는 뜻은 아니다. 존재하지 않는 예시 파일은 실제 구현 완료를 뜻하지 않는다. 실제 환경변수 예시는 `infrastructure/docker/.env.example`에 있다. 빈 폴더나 미수행 작업의 RESULT를 가상으로 채우지 않는다.

## 2. 대분류별 PLAN / RESULT 경로

- 개발 기록은 `parts/<대분류>/PLAN.md`와 `parts/<대분류>/RESULT.md`로 관리한다.
- 관리 체계는 A~O 15개 코드·16개 작업 영역이다. G-1/G-2는 각각 `parts/G-1-input-guardrail/`, `parts/G-2-output-guardrail/`에서 기록한다. 코드도 `backend/guardrails/input/`, `backend/guardrails/output/`으로 나눈다. G 전체에서 고유한 `G01` 등의 번호는 유지하며 기존 기록을 초기화하지 않는다.
- L은 `parts/L-input-guardrail-tests/`, M은 `parts/M-output-guardrail-tests/`를 사용한다. 2026-10-26 담당 범위에 맞춰 각각 `L-attack-tests`, `M-leakage-tests`에서 이름을 변경했다. M에는 출력 가드와 응답 품질 실험 기록을 함께 둔다. N(`N-evaluation`)은 전원 통합 보안 성능 비교·평가의 기록 위치이며, 이전에 계획했던 Planner 정확도 실험은 별도 대분류 없이 C에서 간단히 확인한다. 문서화는 독립 업무가 아니다. 대시보드는 `O-dashboard`(이전 `O-documentation` 폴더명 변경)를 사용한다.
- O(보안 대시보드·Grafana)의 기록 경로는 `parts/O-dashboard/`다. PLAN/RESULT는 실제 작업이 생기면 만든다.
- `A01`, `B02`, `E03`과 같은 Part ID는 **문서 내부 기능 구분용 라벨·목차**이며 별도의 Part 디렉터리를 만들지 않는다.
- PLAN과 구현 사이에는 순서 제약이 없다. RESULT는 실제 구현·수정·검증한 내용이 생긴 **이후**에만 작성하거나 갱신한다.
- 두 문서는 기능별 `# E01 - 기능명` 제목과 그 아래 `1.`, `2.`, `3.` 번호 목록을 사용한다. RESULT에는 결과를 파악할 수 있도록 구현 방식·실제 코드 경로·검증 결과·미완료 사항을 충분히 기록한다.
- PLAN과 RESULT의 작업 번호를 가능한 범위에서 대응시키되, 미실행 작업을 결과에 채워 넣거나 완전한 일대일 대응을 강제하지 않는다. 구체적인 형식과 예시는 `WORKFLOW.md`, `docs/examples/`를 따른다.

**경로 예시:**

```text
parts/E-rag/
├── PLAN.md
└── RESULT.md
```

파일 내부의 예시는 다음과 같다(설명용 가상 항목).

```md
# E01 - 벡터 검색 기능

1. 검색 API 및 입출력 구조 정리
2. Qdrant 검색 로직 구현
3. test-data 기반 검색 검증

# E02 - Retrieval ACL 연동

1. 검색 시 문서 권한 필터 적용
2. Policy Engine 재검증 연계
```

## 3. 결과 참조 및 대분류 간 연동

1. 현재 작업과 직접 관련된 RESULT만 선택적으로 확인한다. **A~O 전체 RESULT를 일괄 읽지 않는다.**
2. 사용자가 참조할 RESULT를 지정하면 우선 확인한다. 그렇지 않으면 작업 맥락과 `PARTS.md`를 바탕으로 AI가 필요한 내용을 판단한다.
3. 필요한 RESULT의 목차에서 해당 기능을 찾아 읽고, 연동에 필요한 실제 코드·API·데이터 형식을 확인한다.
4. 다른 대분류가 먼저 구현한 인터페이스가 있다면 **후속 구현자가 기존 구조를 최대한 따른다.** 큰 구조적 괴리, 연동 불가능, 중요한 보안 요구사항 위반 등에서만 변경을 논의한다.
5. PLAN/RESULT에 선행 Part, 다른 대분류 목록 또는 참조 이력을 의무적으로 기록하지 않는다.
6. 공통 인터페이스를 문서화할 필요가 있을 때에는 `docs/interfaces/`를 사용한다. 실제 구현과 계약 문서가 다르면 검증 없이 확정하지 않는다.

## 4. 폴더별 책임 경계

| 구역 | 저장하는 내용 | 구분할 내용 |
|---|---|---|
| `parts/` | 대분류별 계획·구현 결과 기록 | 실행 소스코드는 해당 구현 폴더에 둔다 |
| `docs/` | 공통 예시·필요한 인터페이스·제안서 | 대분류별 작업 이력은 `parts/`에서 관리한다 |
| `backend/` | 서버 API·게임 상태·Planner·AI·RAG·보안 로직 | 기록용 PLAN/RESULT는 두지 않는다 |
| `frontend/` | 게임 화면과 클라이언트 로직 | 최종 서버 접근통제 판단을 맡기지 않는다 |
| `database/` | DB 스키마·적재용 SQL | 실행 중인 DB 볼륨과 비밀값은 넣지 않는다 |
| `data/` | 정식 게임·합성 테스트 콘텐츠 원본 | DB별 콘텐츠 사본을 따로 관리하지 않는다 |
| `experiments/` | 공격·유출·평가 실험 코드와 상세 증거 | RESULT에는 필요한 요약과 경로만 남긴다 |
| `infrastructure/` | Docker/K8s/AWS 구성 | 애플리케이션 소스코드 사본은 중복 저장하지 않는다 |
| `tests/` | 단위·통합·E2E 검증 중 공통 테스트 | 보안 평가의 상세 결과는 `experiments/`에 둔다 |

기능 담당자가 해당 기능의 백엔드도 구현하며 I는 공통 진입점·인증 상태 전달·입출력·오류·E2E 통합을 공동으로 맡는다. 기존 `backend/` 폴더나 개별 구현을 한 디렉터리로 강제 이동하지 않는다. G-1/G-2의 구체 코드 분리는 실제 구현에 맞춘다. O의 Grafana 설정·대시보드 파일 위치는 K·H와 연동 설계 시 정하며 현재 구현 경로로 단정하지 않는다.

실험 자료는 기존 `experiments/attacks/`(L 입력 검증), `experiments/leakage/`(M 출력·품질), `experiments/evaluation/`(N 통합 비교·평가) 경로를 활용한다. N 결과는 후속 작업에서 케이스·조건·산출물로 구분하며 현재 자리만 있는 폴더를 실행 완료로 취급하지 않는다. 문서·발표는 각 영역의 기록과 공동 산출물로 관리한다.

## 5. 데이터셋 분리

- `data/test-data/`는 개발과 보안 실험을 위한 **합성 데이터**, `data/game-data/`는 게임에 실제로 사용할 **정식 콘텐츠**를 뜻한다. 현실의 민감한 사용자 데이터를 의미하지 않는다.
- 정식 게임 데이터의 대상은 **6일 × 일별 5회 = 총 30회 실험**이다. 기록 유형은 Setup, Action, Dialogue, Thought, Result, Incident의 6종이다. 기존 작성된 시나리오는 이 문서 최신화에서 바꾸지 않는다.
- 공통 규칙은 실제 파일 `data/game-data/rules.json`을 유지하며 `game_rules.json`으로 이름을 바꾸지 않는다. 일별 여섯 JSON은 실험 기록 원본, 공통 규칙은 별도 `rule_id` 데이터다.
- 실제 SQL은 `database/schemas/mariadb/001_game_records.sql`~`008_game_rules.sql`, JSON 적재 CLI는 `database/loaders/load_mariadb.py`에 있다. `(dataset, record_id)`를 MariaDB·Qdrant에서 일관되게 연결한다. DB용 콘텐츠 사본을 별도로 만들지 않는다.
- 양쪽 데이터셋은 가능한 한 공통 스키마와 권한 메타데이터를 사용하며, 혼합·문서 ID 충돌·권한 누락을 방지한다.
- 테스트 데이터 검증과 정식 게임 데이터 검증을 구분한다. 임의의 고정 Part ID나 선행 작업 목록을 최종 검증 절차에 연결하지 않는다.
- 비밀번호, 실제 API Key, 개인 데이터, 실행 DB 볼륨 등은 Git에 커밋하지 않는다.
- 현재 Pages 설정은 `frontend/`만 배포한다. 보호할 시나리오 원본·정답은 프론트엔드 산출물에 포함하지 않아야 하며, 공개 Git 저장소에 원본이 있으면 서비스 ACL과 별도로 열람 가능하다. 공개 범위·서버 전용 보관 방식은 팀 합의가 필요하다.

## 6. 개발 환경과 유연성

- 핵심 게임과 보안 실험은 Docker Compose를 이용해 로컬에서 실행 가능한 구조를 지향한다. Kubernetes와 AWS 배포 내용은 각 환경 폴더에 둔다.
- 기본 Compose는 MariaDB·Qdrant·FastAPI·프론트엔드 실행을 정의한다. 별도 `docker-compose.grafana.yml`로 로컬 Grafana 감사 대시보드를 선택 실행할 수 있다. Kubernetes·AWS 배포는 구현 목표이며 완료 상태가 아니다.
- 실제 API·DB·LLM 연동을 우선한다. Mock을 필수 개발 단계로 두지 않는다.
- 담당자는 `backend/`, `frontend/`, `database/`, `experiments/`, `infrastructure/`, `tests/` 내부의 구체적인 파일명·세부 폴더 구성·개발 순서를 자율적으로 결정할 수 있다.
- 이 문서의 트리 밖에 기능별 폴더가 추가될 수 있다. 다른 담당자의 구현과 충돌하는 공통 구조를 변경할 때에만 필요한 범위로 조율한다.

## 7. 공통 문서 역할

| 문서 | 담당 역할 |
|---|---|
| `MASTER.md` | 프로젝트 목표, 게임·AI·보안 시스템과 구현·검증 요구사항 |
| `PARTS.md` | A~O 대분류별 예상 구현 내용과 담당 범위 (G-1/G-2 구분) |
| `WORKFLOW.md` | 유연한 구현 방식과 PLAN/RESULT·Part 라벨 작성 규칙 |
| `PROJECT_STRUCTURE.md` | 최상위 저장소 구조와 파일·폴더 위치 |
| `README.md` | 실행 및 재현을 포함한 외부 공개 안내 |

`AGENTS.md`는 위 문서들을 핵심 문서로 안내하는 루트 문서이며 이 구조에 포함된다. `WORKFLOW.md`의 규칙을 중복 기재하지 않는다.

---

**기준:** 대분류별 PLAN/RESULT로 실제 개발 내용을 관리하고, Part는 문서 내부 기능 라벨로만 사용한다. 관련 RESULT와 코드를 필요한 범위에서 참조하며, 저장소 구조는 구현 과정에서 실용적으로 조정한다.
