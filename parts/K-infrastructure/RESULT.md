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

2026-10-26 O01에서 별도 `docker-compose.grafana.yml`로 Grafana 로컬 선택 실행을 추가했다. 기본 Compose의 FastAPI·프론트엔드 구성은 K02에 기록되어 있다. Grafana와 앱 전체의 통합 실행 검증은 별도 확인이 필요하다. Kubernetes·AWS 배포는 미구현이다.
