# AI 술래잡기 보안 프로젝트

역할 기반 AI 서비스 접근통제와 데이터 유출 방지를 주제로 만든 추리게임형 보안 검증 프로젝트입니다.

연구소 안에서 6개의 AI가 6일 동안 하루 5번, 총 30번의 술래잡기 실험을 했고 그 기록이 남아 있습니다.
플레이어는 각 AI와 직접 대화하면서 실험 중에 무슨 일이 있었는지, 누가 배신했는지 추리하게 됩니다.

게임보다 중요한 건 그 뒤의 구조입니다.
AI가 말해도 되는 것을 프롬프트로 막는 대신 **서버가 검색 단계에서 먼저 거르고**,
이 방식이 프롬프트만 쓰는 방식보다 유출을 얼마나 줄이는지 실험으로 비교합니다.

팀원 4명이 진행.

---

## 게임 소개

### 진행 방식

- 로그인 후 역할 선택, 6개 AI와 1:1 대화 (별도 조사관 AI 없음)
- Day 1 ~ Day 6 구성, Day가 지날수록 조사할 수 있는 실험 기록 증가
- 조사 Token, 발견한 단서, Save/Load 등 게임 상태는 전부 서버에서 관리
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

### 실험 기록 5종

| 기록 | 내용 |
|---|---|
| 행동·목격 | 누가 언제 어디서 무엇을 했고, 누가 그걸 봤는지 |
| AI 간 대화 | AI끼리 나눈 대화와 그 맥락 |
| 속마음 | AI의 생각, 의도, 속임수, 계획 |
| 실험 결과 | 점수, 성공·실패, 추격·포획 결과 |
| 실험 환경 | 시간, 장소, 배치, 규칙, 제한 조건 |

AI마다 아는 범위가 다름. 직접 했거나 목격했거나 대화에 참여한 것만 앎.
다른 AI의 속마음은 자동으로 알 수 없음.

### 플레이어 역할

- `Developer` : 기본 정보 위주
- `Security Analyst` : 보안 사건 등 더 넓은 정보
- `Administrator` : 정책상 허용되는 관리자 전용 정보까지

지금은 후보 이름이라 게임에 맞게 바뀔 수 있음.
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
사용자 UI (역할 / Day / Save / 6개 AI 채팅)
   │
   ▼
FastAPI ─ 로그인, Save 소유권, 게임 상태 확인
   │
   ▼
Input Guard ─ 질문 유형과 위험 신호 분류
   │
   ▼
중앙 Query Planner ─ 선택한 AI에게 줄 정보 후보와 검색 조건 결정
   │
   ▼
Policy Engine ─ RBAC / ABAC / Scope / Day / Save 판정
   │
   ▼
Qdrant ─ 메타데이터 필터로 먼저 거르고, 결과를 한 번 더 확인
   │
   ▼
Character AI ─ 허용된 Context + 캐릭터 설정 + 대화 기록으로 답변
   │
   ▼
Output Guard ─ 민감정보, Canary 확인 후 마스킹 또는 차단
   │
   ▼
응답

(전 과정 감사 로그 기록, Grafana 모니터링)
```

Planner가 **무엇을 줄지** 고르고, Policy Engine이 **그중 줘도 되는 것**을 검증하고, 캐릭터는 허용된 내용을 **어떻게 말할지**만 담당.

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

- 여유가 되면 B에 Input/Output Guard를 더한 C 구성까지 비교
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

---

## 데이터

| 폴더 | 내용 |
|---|---|
| `data/test-data/` | 초기 개발·권한 검증용 합성 데이터 |
| `data/game-data/` | Day 1~6, 30회 정식 게임 시나리오 |
| `database/schemas/` | 두 데이터가 같이 쓰는 스키마 |

- 정식 시나리오 전까지는 `test-data`로 기능·보안 실험 먼저 진행
- 이후 `game-data`로 교체해서 적재 검증, E2E 테스트, 보안 재평가
- 실제 DB 볼륨, 비밀번호, API Key 등은 저장소에 올리지 않음

---

## 기술 스택

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
├── parts/                 # 대분류별 PLAN.md / RESULT.md (A~O)
├── backend/               # FastAPI 서버, 게임, AI, 보안 기능
├── frontend/              # 게임 웹 UI
├── database/              # DB 스키마와 적재용 SQL
├── data/                  # game-data, test-data 콘텐츠 원본
├── experiments/           # 공격, 유출, 평가 실험
├── infrastructure/        # Docker, Kubernetes, AWS
└── tests/                 # 통합, E2E 테스트
```

## 개발 방식

- A~O 대분류마다 `parts/<대분류>/PLAN.md`, `RESULT.md` 하나씩 두고 기록을 계속 쌓아감
- 문서 안에서는 `# J01 - 기능명` 같은 제목으로 기능을 나누고, 그 아래 번호 목록으로 작업을 적음
- RESULT는 실제로 구현하고 확인한 뒤에만 작성
- 실제 코드는 `parts/`가 아니라 각 소스 폴더에 둠

참고 문서

- [MASTER.md](MASTER.md) : 무엇을 만드는지
- [PARTS.md](PARTS.md) : 대분류별로 누가 무엇을 맡는지
- [WORKFLOW.md](WORKFLOW.md) : PLAN / RESULT 작성 방법
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) : 파일을 어디에 두는지

---

## 로컬 실행

프론트엔드 화면(Mock 데이터)은 GitHub Pages에서 볼 수 있음: https://kcg020529.github.io/detective.game.github.io/
로컬 실행 방법은 [frontend/README.md](frontend/README.md) 참고.

전체 서비스는 아직 개발 초기라 준비 중. 구현이 진행되면 아래 내용 추가 예정.

- 로컬 실행 방법 (Docker Compose)
- 테스트 데이터 적재
- 공격 / 방어 실험 재현 방법
- 실행 환경 제약
