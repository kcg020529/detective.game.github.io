# K01 - Docker Compose 로컬 실행 환경

1. `infrastructure/docker/docker-compose.yml`에 MariaDB·Qdrant 두 서비스 구성 (프로젝트 이름 `kervion`)
   - 실행 위치 `infrastructure/docker`, 명령 `docker compose up -d`
2. 서비스 설정
   - MariaDB: `mariadb:11.4.13` (LTS 11.4 계열 패치 버전 고정), 컨테이너 `kervion-mariadb`, 문자셋 `utf8mb4`/`utf8mb4_unicode_ci`, 볼륨 `kervion_mariadb_data`, 이미지 내장 `healthcheck.sh`로 상태 확인
   - Qdrant: `qdrant/qdrant:v1.19.2`, 컨테이너 `qdrant`, 6333(HTTP·대시보드)·6334(gRPC), 볼륨 `qdrant_storage`. 이미지에 curl이 없어 bash `/dev/tcp`로 `/healthz` 확인
   - 둘 다 `restart: unless-stopped`
3. 비밀번호·접속 정보
   - `infrastructure/docker/.env.example`: `MARIADB_ROOT_PASSWORD`, `MARIADB_DATABASE`(기본 `kervion`), `MARIADB_USER`(기본 `kervion`), `MARIADB_PASSWORD`, `MARIADB_PORT`(기본 3306)
   - `.env.example` 비밀번호는 자리표시자 `change-me`. 실제 값은 각자 `.env`에만 둠. Compose 파일에는 기본값 없음 → `.env`가 없으면 누락 메시지와 함께 실행 실패 (확인함)
   - `.env`는 `.gitignore`로 제외됨 (`git check-ignore` 확인)
4. 포트는 두 서비스 모두 `127.0.0.1`에만 바인딩 (`docker inspect` 확인)
5. 초기 SQL 경로: `database/schemas/mariadb/` → `/docker-entrypoint-initdb.d` (읽기 전용). 데이터 볼륨이 비어 있는 첫 실행 때만 파일명 순으로 실행. 현재 `.sql` 없음, 안내 `database/schemas/mariadb/README.md`
6. 실행 안내 `infrastructure/docker/README.md`: 준비, 실행·상태 확인, 접속 정보, CLI·DB 도구 접속, 자동 재시작, 중지·삭제·`down -v` 경고, 초기 SQL 주의, 포트 충돌, 기존 볼륨 경고
7. 이 PC에서 실제 검증
   - `docker compose config` 통과, `up -d` 후 두 서비스 healthy
   - MariaDB `11.4.13`, 서버 문자셋 `utf8mb4`, 일반 계정 `kervion`으로 `kervion` DB 접속·권한 확인
   - 한글 행 삽입 → MariaDB 재시작 → 유지 확인 → 테스트 테이블 삭제
   - Compose 이전에 따로 띄웠던 Qdrant 컨테이너를 지우고 Compose로 교체. 볼륨 `qdrant_storage`를 그대로 이어 써서 기존 컬렉션 `e03_smoke` 10건 유지 확인
   - 처음엔 Qdrant 볼륨을 `external: true`로 둬서 볼륨이 없는 PC에서 실행 실패하는 문제가 있었음 → 제거. 기존 볼륨이 있는 PC에선 경고만 뜸 (README에 안내)
   - 팀원 PC 첫 실행 모의 검증: 별도 프로젝트 이름·빈 볼륨·`.env.example` 그대로 실행 → 두 서비스 healthy, 초기 SQL(한글 행 포함) 자동 실행, 빈 Qdrant 확인 후 테스트 컨테이너·볼륨 삭제
8. 미완료
   - FastAPI·프론트·Grafana 서비스 미포함 (각 서비스 구현 후 추가)
   - Kubernetes(K03)·AWS(K04)는 시작 안 함

# K02 - 앱 전체 Docker Compose 실행

1. `infrastructure/docker/`
   - `Dockerfile.backend`: `python:3.12-slim`, 백엔드·RAG·적재 도구 패키지 설치, 비루트 사용자. API와 도구 셋이 같은 이미지(`kervion-backend:local`) 하나를 씀
   - `docker-compose.yml`에 `api`(uvicorn `--reload`, `backend/` 연결), `web`(`nginx:1.27-alpine`, `frontend/` 읽기 전용 연결, 127.0.0.1:`WEB_PORT`, 기본 8080) 추가. 도구 `migrate`·`load-data`·`rag-index`는 `tools` 프로필이라 `up`에서는 안 뜸
   - 도구는 `database/`·`data/`·`backend/`를 읽기 전용으로 연결해 `git pull` 뒤 다시 빌드하지 않아도 새 파일을 씀. 임베딩 모델은 `fastembed_cache` 볼륨에 한 번만 받음
   - `nginx.conf`: `/api/` → `api:8000`, `/config.js`가 `window.KERVION_API_BASE = '/api/v1'`을 돌려줌, html·js·css 캐시 끔. 처음엔 MIME 표가 빠져 css·js가 `text/plain`으로 나가 화면이 깨졌음 → `mime.types` 포함으로 고침
   - `migrate.py`: `database/schemas/mariadb`, `database/migrations/mariadb`의 SQL을 파일 이름 순으로 적용하고 `schema_migrations`에 기록. 이미 표가 다 있는 예전 DB는 다시 만들지 않고 적용됨으로 기록. 실패하면 기록하지 않음
   - `.env.example`: `WEB_PORT`, 나중에 쓸 DeepSeek 키 자리(값 없음). `README.md`: 전체 실행·갱신·초기화·문제 해결
2. 프론트: `frontend/config.js`(주석만, GitHub Pages·일반 정적 실행은 Mock 그대로)와 `index.html`에서 `api.js` 앞에 불러오기. Compose에서만 nginx가 API 주소로 바꿔 줌
3. 확인
   - 빈 볼륨 별도 프로젝트: 모두 healthy → `migrate` 12개+이관 1개 적용, 두 번째는 모두 건너뜀 → `load-data` 302건·권한 906행 → `rag-index` meta 302·summary 302·content 317점, 두 번째 실행은 모델을 다시 받지 않음 → 브라우저에서 회원가입·새 수사·바탕화면까지, API 호출은 `/api/v1`, 콘솔 오류 없음. 확인 후 시험용 컨테이너·볼륨 삭제
   - 기존 로컬 DB: `migrate`가 001~012를 적용됨으로 기록하고 이관 SQL 적용, 사용자·Save·기록·권한 행 수 그대로
   - 실제 마우스 클릭으로 회원가입 → 새 수사 → 기록 칸 클릭 → 바탕화면 진입 확인 (nginx MIME 수정 후)
   - `backend/` 파일을 건드리면 uvicorn이 다시 시작됨, `frontend/` 수정은 새로고침으로 반영
4. 남은 것
   - Grafana(O)·채팅 전송 API는 생기면 추가
   - Kubernetes(K03)·AWS(K04)

# K03 - 채팅용 DeepSeek 키를 Compose에 전달

1. `docker-compose.yml` `api`: `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_PLANNER_API_KEY`, `DEEPSEEK_PLANNER_MODEL`(기본 deepseek-flash)을 `.env`에서 전달. 기본값은 빈 값
2. `.env.example`: 주석이던 두 키를 빈 값으로 살리고 설명 한 줄. 실제 값은 `.env`에만
3. README: 키를 채워야 채팅이 동작한다는 안내, 예전 이미지는 Jinja2·PyYAML이 없어 다시 빌드 필요

2026-10-26 O01에서 별도 `docker-compose.grafana.yml`로 Grafana 로컬 선택 실행을 추가했다. 기본 Compose의 FastAPI·프론트엔드 구성은 K02에 기록되어 있다. Grafana와 앱 전체의 통합 실행 검증은 별도 확인이 필요하다. Kubernetes·AWS 배포는 미구현이다.

# K04 - 로컬 Kubernetes 배포 (Docker Desktop, 2026-10-29)

1. `infrastructure/kubernetes/` (kustomize)
   - `base/`: namespace, ConfigMap, MariaDB·Qdrant StatefulSet(PVC 5Gi), fastembed 캐시 PVC, api·web Deployment, Job 3개(migrate·load-data·rag-index). nginx 설정은 `infrastructure/docker/nginx.conf`에서 생성해 Compose와 한 파일을 쓴다
   - `overlays/local/`: 이미지 `:k8s`, web NodePort 30080, http 쿠키. Job도 overlay로 렌더링해 이미지 설정이 Job에까지 적용된다(처음 구현은 Job 이미지가 고정돼 AWS에서 실패할 구조였음)
   - 스크립트: `deploy.sh <overlay>`(데이터 → Job 순서 대기 → 앱), `reindex.sh`(api를 멈추고 재색인, 실패해도 api 복구), `create-secret.sh`(값 출력 없음), `smoke.sh`, `teardown.sh`(기본은 PVC 유지)
   - api·web: `preStop` 10초 대기, `maxSurge 1`·`maxUnavailable 0`
   - nginx: 앞단(ALB)이 보낸 `X-Forwarded-Proto`가 있으면 그대로 전달
2. 확인 (Docker Desktop kubeadm v1.36, 노드 1개)
   - 빌드 → 배포: Job 3개 완료(새 테이블 013·014 적용), 기록 1,445건 색인, api·web 정상
   - smoke: `/` 200, `/config.js` 200, 로그인 전 `/auth/me` 401, 회원가입·Save 201, 채팅 200
   - 엔딩 흐름(교수 Save): Day 1 지목 409 → Day 6 → YB-1 기록 질문 normal("90초") → YB-4 지목 적중, S01 찾음 → 같은 요청 재전송 같은 응답, 두 번째 지목 409. 학부 Save YB-2 지목은 불일치
   - api 2개: 같은 흐름 반복, 두 Pod 모두 요청 처리, 로그인·중복 요청·지목 결과 같음
   - DeepSeek 키를 뺀 Secret: 채팅 503 → 키 복원 후 200
   - **교체 중 끊김**: preStop 없이 api 교체 시 1,661건 중 502 5건·시간 초과 1건 → preStop·전략 추가 후 api·web 교체 중 2,213건 모두 정상
   - 롤백: 이미지 교체 → `rollout undo`로 복귀 확인
   - DB 백업·복원: `mariadb-dump`를 별도 DB로 복원해 기록 1,445·표 18개 등 행 수 일치 확인, 시험 DB 삭제
   - 메모리 최대값(cgroup `memory.peak`, api가 켜진 상태에서 재색인): rag-index 2.63GiB, api 0.97GiB(임베딩 모델 적재 후), Qdrant 0.16GiB, MariaDB 0.11GiB, 합계 약 3.9GiB → t3.large(약 7GiB 사용 가능)에서 동시 실행 가능
   - 시험 계정 10개와 Save는 확인 후 삭제
   - 테스트 287 통과, 21 건너뜀(오프라인)
3. 고친 문제: `teardown.sh --delete-data`가 Qdrant PVC 이름을 잘못 적어 디스크를 남김 → 수정하고 PVC 이름 테스트 추가

# K05-1 - AWS 배포 준비 (오프라인, 2026-10-29)

1. `overlays/aws/`: ECR 이미지 `:<커밋 SHA>`, gp3 StorageClass(암호화, WaitForFirstConsumer, Delete), ALB Ingress(HTTPS, 80→443, ACM 인증서), https 허용 Origin·Secure 쿠키
2. `scripts/render.sh`: `aws/aws.env`에서 ECR 주소·도메인·인증서 ARN만 읽어 치환. SHA가 아닌 태그·`latest`·남은 자리표시자는 실패
3. `aws/cluster.yaml`(eksctl): 서울, 1.36, 공용 서브넷 2개 AZ, NAT 없음, 노드 t3.large 1대 2a 고정, Pod Identity·EBS CSI 애드온, Load Balancer Controller 권한, IMDSv1 끔
4. `scripts/aws-install-lbc.sh`, `scripts/teardown-aws.sh`(Ingress 먼저 삭제 → ALB 삭제 대기 → 클러스터 삭제 → 남은 자원 출력)
5. `.github/workflows/ci.yml`: PR·main에서 오프라인 테스트, 이미지 2개 빌드(push 없음), 두 overlay 렌더링. 권한은 읽기 전용
6. 하지 않은 것: **실제 AWS 생성·배포는 안 했다.** 로컬에 eksctl·helm이 없어 `cluster.yaml`과 차트 버전은 실제 도구로 검증하지 못했다. CI는 GitHub에서 아직 실행되지 않았다
7. R23: 캐시를 마운트하는 API·rag-index에 fsGroup 10001/OnRootMismatch를 적용했다. 공통 `resolve_kube_context`/`kc`로 deploy·reindex·Secret·로컬 teardown의 대상을 고정하고, Secret은 namespace부터 만든다. AWS는 aws.env의 KUBE_CONTEXT가 필수다. reindex는 Job 문서만 골라 KERVION_RAG_FORCE=1을 넣는다. nginx는 POST 인증 10r/m·burst 5, 채팅 20r/m·burst 10·동시 2개, JSON 429, 사설 프록시 실제 IP와 읽기 제한 90초를 적용하고 기존 전달 헤더를 유지한다.
   - 검증: `KERVION_OFFLINE_TESTS=1`, `PYTHONUTF8=1`, `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`: 371 통과, 21 건너뜀, 기존 Starlette 경고 1개. shell 9개 bash -n, 수정 JS node --check, overlay 2개 렌더링, nginx:1.27-alpine nginx -t 통과. `tests/infra/test_kubernetes_manifests.py`에서 컨텍스트/namespace/그룹/429와 실제 kubectl --local의 Job 단독 변경을 확인했다. 클러스터·AWS·DeepSeek는 호출하지 않았고 커밋하지 않았다.
