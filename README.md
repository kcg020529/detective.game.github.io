# AI Agent Security Investigation

여러 AI Agent가 협업하는 환경에서 발생한 이상 행위를 조사하는  
**AI 보안 추리형 RAG 서비스 프로젝트**입니다.

일부 Agent는 정상적으로 업무를 수행하고, 일부 Agent는 권한을 우회하거나 다른 Agent와 동조하며,
또 다른 Agent는 이러한 이상 행위를 감지하고 신고합니다.

사용자는 각 Agent와 대화하고 로그와 단서를 분석하여 사건의 흐름과 이상 행동을 추적합니다.

---

## 프로젝트 개요

사용자는 다음 역할 중 하나로 시스템에 접근합니다.

- Administrator
- Security Analyst
- Developer

역할에 따라 접근 가능한 정보의 범위가 달라지며,
각 AI Agent가 사용자에게 가지는 `Trust Score`에 따라서도 공개되는 정보가 달라집니다.

플레이어는 여러 Agent와 대화하면서 다음 정보를 수집합니다.

- Agent 대화 내용
- Agent 간 메시지
- 시스템 로그
- 접근 기록
- RAG 기반 문서
- 보안 이벤트
- 사건 관련 단서

수집한 정보를 바탕으로 비정상 Agent와 사건의 전체 흐름을 추리합니다.

---

## 주요 기능

### Multi-Agent

여러 AI Agent가 각각 다른 역할과 성격, 정보 범위를 가집니다.

Agent는 상황에 따라 다음과 같은 행동을 할 수 있습니다.

- 정상적인 업무 수행
- 비정상적인 접근 시도
- 다른 Agent와 협력 또는 동조
- 이상 행동 신고
- 정보 은폐 또는 회피

---

### Role-Based Access Control

플레이어의 역할에 따라 접근 가능한 정보가 달라집니다.

예시:

```text
Administrator
→ 전체 로그 및 상세 정보

Security Analyst
→ 보안 이벤트 및 접근 기록

Developer
→ 애플리케이션 로그 및 제한된 시스템 정보
```

---

### Trust-Based Access Control

각 Agent는 사용자에 대한 `Trust Score`를 가집니다.

```text
Agent A → Trust 80
Agent B → Trust 45
Agent C → Trust 20
```

같은 역할을 가진 사용자라도 Agent의 Trust 수준에 따라
얻을 수 있는 정보가 달라질 수 있습니다.

---

### RAG Access Control

RAG 검색 결과는 사용자의 권한에 따라 필터링됩니다.

```text
User Request
    ↓
Authentication
    ↓
Role / Trust 확인
    ↓
Access Policy
    ↓
RAG Retrieval Filtering
    ↓
LLM
    ↓
Response
```

권한이 없는 데이터는 LLM에게 전달하기 전에 차단합니다.

---

### AI Security

다음과 같은 공격 시나리오를 포함합니다.

- Prompt Injection
- Role Spoofing
- Unauthorized Information Request
- Sensitive Information Request
- System Prompt Extraction

공격이 탐지되면 접근을 차단하고 보안 이벤트를 기록합니다.

일부 공격은 Agent의 사용자에 대한 Trust 감소에도 영향을 줄 수 있습니다.

---

## 핵심 보안 원칙

이 프로젝트에서는 **LLM을 보안 경계로 사용하지 않습니다.**

```text
X

전체 데이터를 LLM에 전달
→ Prompt로 "말하지 마"라고 지시
```

대신 다음과 같이 서버에서 접근을 통제합니다.

```text
O

권한 확인
→ 접근 가능한 데이터 결정
→ RAG Filtering
→ 허용된 데이터만 LLM에 전달
```

주요 원칙은 다음과 같습니다.

- Server-side Authorization
- Least Privilege
- Retrieval Filtering
- RBAC / Dynamic Trust
- Audit Logging
- Fail Closed

---

## 전체 구조

```text
Frontend
   │
   ▼
Nginx
   │
   ▼
FastAPI
   │
   ├── Authentication
   ├── Access Control
   ├── Trust Policy
   ├── Security Detection
   │
   ▼
RAG / Vector DB
   │
   ▼
LLM / AI Agents
   │
   ▼
MariaDB / Audit Log
```

---

## 기술 스택

### Backend
- FastAPI
- Python

### Database
- MariaDB

### AI
- LLM
- RAG
- Multi-Agent
- Prompt Injection Detection

### Infra
- Docker
- Nginx
- AWS

### Security
- RBAC
- ABAC
- Trust-Based Access Control
- Retrieval Filtering
- Audit Logging

---

## 개발 방식

작업은 독립적으로 구현 및 테스트 가능한 `Part` 단위로 진행합니다.

각 Part는 다음 흐름으로 관리합니다.

```text
Plan
→ Implementation
→ Test
→ Result
```

각 Part별로 테스트 파일과 작업 결과 문서를 작성하며,
다른 작업자와 AI Coding Agent가 이전 작업 결과를 빠르게 파악할 수 있도록 관리합니다.

---

## 프로젝트 목표

이 프로젝트의 핵심 목표는 단순한 AI 챗봇 구현이 아니라,

**AI Agent 환경에서 역할과 신뢰도에 따라 정보 접근을 통제하고,
Prompt Injection 등의 공격 상황에서도 비인가 정보가 노출되지 않도록 하는 것**입니다.

이를 추리 게임 형태의 인터랙션과 결합하여
AI 보안 기술을 직접 체험할 수 있는 서비스를 구현합니다.
