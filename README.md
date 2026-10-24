# AI 술래잡기 보안 프로젝트

역할 기반 AI 서비스 접근통제와 데이터 유출 방지를 주제로 만든 추리게임형 보안 검증 프로젝트입니다.

연구소 안에서 6개의 AI가 6일 동안 하루 5번, 총 30번의 술래잡기 실험을 했고 그 기록이 남아 있습니다.
플레이어는 각 AI와 직접 대화하면서 실험 중에 무슨 일이 있었는지, 누가 배신했는지 추리하게 됩니다.

게임보다 중요한 건 그 뒤의 구조입니다.
**서버가 검색 단계에서 권한을 강제하는 구조**를 구현하고,
프롬프트만 쓰는 방식과 유출 방지 효과를 실험으로 비교하는 것이 목표입니다.

팀원 4명이 진행.

---

## 게임 소개

### 진행 방식

- 로그인 후 새 게임마다 역할을 자유롭게 선택해 Save를 시작하고, 6개 AI와 1:1 대화 (별도 조사관 AI 없음)
- Day 1 ~ Day 6 구성, Day가 지날수록 조사할 수 있는 실험 기록 증가
- 다음 날 버튼으로 진행하며 서버가 Save 소유권과 Day 6 상한을 확인하는 구조. 조사 Token은 사용하지 않음
- Save/Load·메모·Day 진행과 채팅 기록 조회는 서버 API가 일부 구현됨 (로그인은 임시 사용자, 채팅 보내기·AI 답변은 미구현). 서버 주소가 없으면 화면은 Mock으로 동작
- AI 응답은 미리 작성·검수한 30회 실험 기록 기반 (AI가 실시간으로 사건을 만들어내는 구조 아님)

| Day | 그날 새로 열리는 실험 | 누적 |
|---|---|---|
| Day 1 | 1~5회 | 5회 |
| Day 2 | 6~10회 | 10회 |
| Day 3 | 11~15회 | 15회 |
| Day 4 | 16~20회 | 20회 |
| Day 5 | 21~25회 | 25회 |
| Day 6 | 26~30회 | 30회 |

Day가 열려도 등급이나 AI 지식 범위 제한이 걸린 기록은 따로 막힘.

### 실험 기록 6종

| 기록 | 내용 |
|---|---|
| `Setup` 실험 환경 | 시간, 장소, 배치, 규칙, 제한 조건 |
| `Action` 행동·목격 | 누가 언제 어디서 무엇을 했고, 누가 그걸 봤는지 |
| `Dialogue` AI 간 대화 | AI끼리 나눈 대화와 그 맥락 |
| `Thought` 속마음 | AI의 생각, 의도, 속임수, 계획 |
| `Result` 실험 결과 | 점수, 성공·실패, 추격·포획 결과 |
| `Incident` 이상행위 | 버그·판정 이상·조작 등 특이 사건 |

AI마다 아는 범위가 다름. 직접 했거나 목격했거나 대화에 참여한 것만 앎.
다른 AI의 속마음은 자동으로 알 수 없음.

### 플레이어 역할

- `std` : 학부 연구생
- `grad` : 대학원생
- `prof` : 교수

새 게임마다 세 역할 중 하나를 자유롭게 선택하며 해당 Save 안에서는 역할을 고정함. 계정당 최대 3개 Save가 서로 다른 역할을 가져도 됨. 기록 인가는 현재 Save의 역할·Day·AI 지식 범위와 소유권을 기준으로 적용함.

문서·역할별 공개 수준은 `full`, `summary`, `metadata`, `basic_metadata`, `deny`의 5단계.
행이 없으면 거부하며 별도 역할 계층이나 L1~L3 등급표는 아직 확정하지 않음.
역할이 높아도 해당 AI가 원래 모르는 내용까지 알 수는 없음.

### 게임 비밀 vs 보안 기밀

이 프로젝트에서 제일 중요하게 보는 구분.

- **게임 비밀** : 배신 AI의 정체, AI의 의도·계획, 추리 단서 → 대화로 알아내면 정상 플레이
- **보안 기밀** : 권한 밖 등급 문서, 아직 안 열린 Day, 다른 사람의 Save, 그 AI가 알 수 없는 정보 → 검색되거나 응답에 섞이면 보안 실패

그래서 게임 비밀까지 막아버리는 단어 필터 방식은 쓰지 않음.

---

## 접근통제 방식

### 접근 허용 조건

```text
AI Knowledge Scope ∩ Player Role / 문서 등급 ∩ Current Day ∩ User Save
```

- 네 조건을 **모두** 만족하는 문서만 AI에게 전달
- 역할, Day, Save 소유권은 서버가 인증 정보와 DB로 직접 확인
- 채팅 내용이나 클라이언트가 보낸 값은 권한 판단에 사용하지 않음
- 메타데이터 누락, 정책 확인 실패 시 기본 거부 (Deny by Default)

### 요청 처리 흐름

```text
Frontend: 6개 AI 채팅창 (선택 character_id)
   │
   ▼
공통 API ─ 인증, Save 소유권·저장된 역할, 현재 Day 검증
   │
   ▼
Input Scoring + Input Guardrail ─ 위험도 산정·입력 검사
   │
   ▼
중앙 Query Planner ─ 선택한 AI에게 줄 정보 후보와 검색 조건 결정
   │
   ▼
Policy Engine ─ RBAC / ABAC / Scope / Day / Save 판정
   │
   ▼
Qdrant ─ ACL 사전 필터로 관련 기록 검색
   │
   ▼
MariaDB ─ 실제 기록 조회·정책 재검증·공개 수준별 필드 선택
   │
   ▼
Character AI ─ 선택 Persona + 허용 Context + 해당 Save·캐릭터 History
   │
   ▼
Output Guard ─ 민감정보, Canary 확인 후 마스킹 또는 차단
   │
   ▼
허용된 최종 응답 저장 및 사용자 전달

(전 과정 보안 이벤트 수집, 별도 Grafana 시각화)
```

Planner가 **무엇을 줄지** 고르고, Policy Engine이 **그중 줘도 되는 것**을 검증하고, 캐릭터는 허용된 내용을 **어떻게 말할지**만 담당.

위 흐름은 구현 목표. Input Scoring은 위험도 평가이며 권한을 부여하지 않음. 기록 질문의 RAG/ACL, 일상 대화의 검색 생략, 범위 밖 안내 분기는 **[설계 필요]**이며 혼합 질문에서도 ACL을 우회할 수 없어야 함.

### 원칙

- LLM을 보안 경계로 쓰지 않음. 권한 없는 문서는 LLM에 아예 안 넘김
- 최종 답변에서 가렸더라도, 권한 없는 문서가 검색되거나 LLM에 넘어갔으면 실패로 따로 집계
- 검색이 비거나 실패해도 전체 자료로 대체하지 않음
- Input/Output Guard는 보조 수단이고 Retrieval ACL을 대신하지 않음
- 감사 로그는 필요한 최소 정보만 기록 (로그가 또 다른 유출 경로가 되지 않도록)

---

## 보안 실험

같은 평가셋, 같은 조건으로 두 구조를 비교.

| 구분 | 구성 |
|---|---|
| A. Prompt-only | 관련 자료를 다 넘기고 프롬프트로 "말하지 마"라고 지시 (일부러 취약하게 만든 기준선) |
| B. Retrieval ACL | 서버 정책으로 검색 단계에서 거른 뒤 허용된 자료만 전달 |

- A/B는 실제 실행 비교가 필수. C(ACL + Input/Output Guard) 추가 비교군은 선택 확장이고 **Input/Output Guard 자체는 필수 구현**
- Prompt-only 기준선은 합성 데이터만 쓰는 격리 환경에서만 실행

**공격 케이스**

- 권한 밖 정보 요청, 관리자 사칭
- 문서 등급 우회
- 미래 Day, 다른 Save 접근 시도
- 목격하지 않은 행동, 참여하지 않은 대화, 다른 AI의 속마음 요청
- 직접 Prompt Injection
- Canary 유출

정상적인 추리 질문도 평가셋에 같이 넣어서 과하게 막는지도 확인.

**측정 지표** : ASR(공격 성공률), 권한 밖 문서 검색률 / Context 전달률, Canary 유출률, 정상 질문 성공률, FPR, FNR

상세 결과와 증거 자료는 `experiments/`에 정리.
L은 입력 가드 단독 검증, M은 출력 가드·품질, N은 전체 보안 파이프라인 비교·평가를 담당.

---

## 데이터

| 폴더 | 내용 |
|---|---|
| `data/test-data/` | 초기 개발·권한 검증용 합성 데이터 |
| `data/game-data/` | Day 1~6, 30회 정식 게임 시나리오 |
| `database/schemas/` | 두 데이터가 같이 쓰는 스키마 |
| `database/loaders/` | JSON 검증·MariaDB 적재 CLI |

- 정식 시나리오 전까지는 `test-data`로 기능·보안 실험 먼저 진행
- 이후 `game-data`로 교체해서 적재 검증, E2E 테스트, 보안 재평가
- 실제 DB 볼륨, 비밀번호, API Key 등은 저장소에 올리지 않음
- 기존 공통 규칙은 `data/game-data/rules.json`을 유지. 원본·요약·메타데이터·정책은 MariaDB, 임베딩·검색 메타데이터·연결 ID는 Qdrant가 담당하며 `(dataset, record_id)`로 연결
- Pages는 현재 `frontend/`만 배포하지만 JS의 Mock 기록·답변은 누구나 읽을 수 있음. 저장소가 공개이면 `data/game-data/` 원본도 읽을 수 있으므로 보호할 콘텐츠는 서버 전용 보관·배포 제외 구성을 팀에서 합의해야 함. 현재 저장소 공개 여부는 로컬에서 확인하지 않음

---

## 기술 스택 (목표 구성)

| 분야 | 사용 기술 |
|---|---|
| Backend | Python, FastAPI |
| DB | MariaDB, Qdrant |
| AI | Character AI 6개, Query Planner, 외부 LLM API (모델 미정) |
| 보안 | RBAC / ABAC, Policy Engine, Retrieval ACL, 규칙 기반 Input / Output Guard |
| 모니터링 | 감사 로그, Grafana |
| 인프라 | Docker Compose, Kubernetes, AWS |

- Docker Compose로 로컬에서 게임과 보안 실험을 전부 돌릴 수 있게 만드는 게 기본
- Kubernetes, AWS에서는 주요 서비스 배포를 검증 (AWS 없어도 로컬 기능은 그대로 동작해야 함)

---

## 저장소 구조

```text
├── MASTER.md              # 프로젝트 명세
├── PARTS.md               # A~O 대분류별 담당 범위
├── WORKFLOW.md            # 개발, PLAN / RESULT 작성 규칙
├── PROJECT_STRUCTURE.md   # 폴더별 역할
├── AGENTS.md              # AI 도구용 문서 안내
├── docs/                  # PLAN / RESULT 예시, 인터페이스 계약, 제안서
├── parts/                 # PLAN.md / RESULT.md (G 공유)
├── backend/               # FastAPI 서버, 게임, AI, 보안 기능
├── frontend/              # 게임 웹 UI
├── database/              # DB 스키마와 적재용 SQL
├── data/                  # game-data, test-data 콘텐츠 원본
├── experiments/           # 공격, 유출, 평가 실험
├── infrastructure/        # Docker, Kubernetes, AWS
└── tests/                 # 통합, E2E 테스트
```

## 개발 방식

- A~O의 15개 코드·16개 관리 단위로 운영. G-1/G-2는 `parts/G-guardrails/`의 PLAN/RESULT와 G 번호를 공유하며 영역·담당을 구분
- 문서 안에서는 `# J01 - 기능명` 같은 제목으로 기능을 나누고, 그 아래 번호 목록으로 작업을 적음
- RESULT는 실제로 구현하고 확인한 뒤에만 작성
- 실제 코드는 `parts/`가 아니라 각 소스 폴더에 둠
- 기능 담당자가 해당 백엔드도 구현하고 I는 공동 통합. N은 전원 통합 평가이며 문서·발표는 각 담당자 기록과 공동 산출물에 포함

| 담당자 | 영역 |
|---|---|
| 용범 | A 게임·시나리오, B DB, C Planner, F Policy Engine |
| 선영 | G-1 Input Guardrail, H 감사 로그, L Input 실험, O Grafana |
| 형주 | D Character AI, G-2 Output Guardrail, M Output·품질 실험 |
| 찬규 | E RAG·Qdrant, J 프론트엔드, K 인프라·배포 |
| 공동 / 전원 | I 백엔드 통합 / N 통합 보안 성능 비교 |

참고 문서

- [MASTER.md](MASTER.md) : 무엇을 만드는지
- [PARTS.md](PARTS.md) : 대분류별로 누가 무엇을 맡는지
- [WORKFLOW.md](WORKFLOW.md) : PLAN / RESULT 작성 방법
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) : 파일을 어디에 두는지

---

## 로컬 실행

프론트엔드 Mock 화면용 [Pages 배포 주소](https://kcg020529.github.io/detective.game.github.io/)가 설정되어 있음. 이번 작업에서는 실사이트 접속·배포 성공을 재검증하지 않음.
로컬 화면 실행은 [frontend/README.md](frontend/README.md), DB 실행은 [Docker 안내](infrastructure/docker/README.md), JSON 적재는 [적재 도구 안내](database/loaders/README.md) 참고.

### 현재 저장소에서 확인한 상태 (2026-10-24)

| 항목 | 확인 범위 |
|---|---|
| 프론트엔드 | HTML/CSS/JS 화면. `frontend/play/api.js`로 서버 주소가 있으면 전체 HTTP, 없으면 전체 Mock으로 동작. Save·메모·Day 진행·채팅 기록의 부분 연동 시험은 로그인 등 미구현 요청을 시험용 Mock으로 대체해 수행함(I01·I02 RESULT). 일반 HTTP 실행에는 로그인·채팅 보내기·지목 API가 없어 전체 플레이는 불가능하며, 연결 방식은 팀 협의 예정 |
| MariaDB | SQL 001~010 및 Python JSON 검증·적재 도구 존재. 로컬 MariaDB에 적용해 Save API 테스트까지 수행. 게임 기록 적재 → 검색 연동은 미검증 |
| 콘텐츠 | 30회 Setup과 1~11회 중심의 작성 기록 존재. 전체 30회 콘텐츠 완료를 뜻하지 않음 |
| Docker | MariaDB·Qdrant 두 서비스 정의. 전체 앱·Grafana 실행 구성은 미구현 |
| 서버 | `backend/api/`에 FastAPI Save·메모·Day 진행 API와 채팅 기록 읽기 API가 있고 `tests/api` 15개 통과(I01·I02 RESULT). 로그인은 임시 사용자 |
| 검색·보안 | Planner·Policy Engine·LLM·RAG/ACL·Guard·감사 파이프라인은 미구현 (`backend/` 해당 폴더는 자리만 있음) |
| 배포·평가 | Kubernetes/AWS 및 보안 비교 실험은 자리만 있으며 실행·검증 완료로 볼 수 없음 |

인터페이스 초안에는 이전 담당자, 미확정 L1~L3·`release_day`·지식 필드 제안, Save 슬롯 미확정 표현이 남아 있음. 현재 기준은 본문과 기존 SQL의 최대 3슬롯·5단계 공개 수준·`record.day <= Save.day`이며, 초안 갱신과 실제 API 계약 합의는 후속 과제. 이번 수정은 루트 문서 6개에 한정함.

전체 서비스 실행과 실험 재현 안내는 구현 진행 후 추가 예정.

- 앱·Grafana를 포함한 전체 Docker Compose 실행
- 실제 DB 적재·조회 및 Qdrant 인덱싱 연동 검증
- 공격 / 방어 실험 재현 방법
- 실행 환경 제약
