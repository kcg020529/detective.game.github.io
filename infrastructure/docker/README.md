# 로컬 전체 실행 (Docker Compose)

MariaDB·Qdrant·백엔드 API·웹(nginx)을 한 번에 띄운다. 처음이라면 아래 "준비"를 마친 뒤 [전체 앱 실행](#전체-앱-실행)을 따른다.

| 서비스 | 하는 일 |
|---|---|
| `mariadb`, `qdrant` | DB, 검색 색인 |
| `api` | FastAPI (`backend/`를 연결해 저장하면 자동 재시작) |
| `web` | `frontend/`를 그대로 보여 주고 `/api/`를 `api`로 넘김. http://127.0.0.1:8080 |
| `migrate`, `load-data`, `rag-index` | 필요할 때 `docker compose run --rm <이름>`으로 실행하는 도구 |

## 준비

Docker Desktop이 실행 중이어야 함.

`infrastructure/docker`에서 `.env.example`을 `.env`로 복사한 뒤 `change-me` 두 곳을 원하는 비밀번호로 변경함.

```powershell
Copy-Item .env.example .env      # Windows PowerShell
cp .env.example .env             # macOS·Linux·Git Bash
```

`.env`는 Git에 올라가지 않음 (`.gitignore`). DB는 각자 PC에 따로 생기며 데이터는 공유되지 않음. AWS 등 외부 배포 시에는 반드시 다른 비밀번호 사용.

## 실행과 확인

`infrastructure/docker`에서 다음 명령을 실행함.

```powershell
docker compose up -d
docker compose ps
```

| 서비스 | 호스트 | 포트 | 데이터베이스 | 계정 |
|---|---|---|---|---|
| MariaDB | 127.0.0.1 | `.env`의 `MARIADB_PORT` | `.env`의 `MARIADB_DATABASE` | `.env`의 `MARIADB_USER` |
| Qdrant | 127.0.0.1 | 6333 (HTTP), 6334 (gRPC) | 해당 없음 | 해당 없음 |

MariaDB CLI 접속 예시는 다음과 같음.

```powershell
docker compose exec mariadb mariadb -u kervion -p kervion
```

`-p` 뒤 비밀번호 입력 프롬프트가 뜸. DBeaver 등 DB 도구는 위 표의 호스트·포트·계정으로 접속.

Qdrant 대시보드는 [http://127.0.0.1:6333/dashboard](http://127.0.0.1:6333/dashboard)에서 확인함.

두 서비스 모두 `restart: unless-stopped`라 Docker Desktop이 켜지면 자동으로 다시 실행됨 (직접 멈춘 경우 제외).

## 중지와 삭제

```powershell
docker compose stop    # 컨테이너만 멈춤, 데이터 유지
docker compose down    # 컨테이너 삭제, 데이터 볼륨은 유지
```

다음 명령은 **MariaDB·Qdrant 데이터 볼륨까지 모두 삭제**하므로 주의가 필요함.

```powershell
docker compose down -v
```

초기 SQL은 MariaDB 데이터 볼륨이 비어 있는 첫 실행 때만 자동 실행됨. 이미 DB가 있는 상태에서 새 SQL 파일이 생기면 볼륨을 지우지 말고 `docker compose run --rm migrate`를 실행함. 적용한 파일을 `schema_migrations` 표에 기록해 새 파일만 실행하고, 이 도구 이전에 손으로 만든 표는 다시 만들지 않고 적용됨으로 기록함.

두 서비스 포트는 `127.0.0.1`에만 바인딩하여 외부 네트워크에서 직접 접속할 수 없게 제한함.

## 참고

- 데이터 볼륨 이름: `kervion_mariadb_data`, `qdrant_storage`
- 예전에 Compose 없이 `qdrant_storage` 볼륨을 만든 PC에서는 `volume "qdrant_storage" already exists but was not created by Docker Compose` 경고가 뜸. 기존 데이터를 그대로 이어 쓰는 것이라 무시해도 됨
- 3306 포트를 이미 다른 MariaDB·MySQL이 쓰고 있으면 `.env`의 `MARIADB_PORT`를 다른 값(예: 3307)으로 바꿈
## 전체 앱 실행

Docker Desktop을 실행한 뒤 `infrastructure/docker`에서 최초 한 번 준비합니다.

```powershell
Copy-Item .env.example .env
# .env의 MariaDB 비밀번호를 설정한 뒤 실행
# 채팅을 쓰려면 .env의 DEEPSEEK_API_KEY·DEEPSEEK_PLANNER_API_KEY도 채운다(비우면 채팅만 503)

docker compose up -d
docker compose run --rm migrate
docker compose run --rm load-data
docker compose run --rm rag-index
```

웹 화면은 [http://127.0.0.1:8080](http://127.0.0.1:8080)에서 엽니다. 프론트와 API는 Compose에서 같이 실행합니다.

## 코드 갱신

`git pull` 후 스키마 또는 원본 데이터가 바뀌었으면 해당 도구를 다시 실행합니다.

```powershell
docker compose run --rm migrate
docker compose run --rm load-data
docker compose run --rm rag-index
```

프론트와 백엔드 소스는 바인드 마운트되어 저장 후 새로고침하면 반영됩니다. 새 파이썬 패키지를 추가한 경우에만 이미지를 빌드합니다. 2026-10-27 이전에 만든 이미지에는 캐릭터 AI가 쓰는 Jinja2·PyYAML이 없으므로 한 번 다시 빌드합니다.

```powershell
docker compose up -d --build
```

## 초기화 주의

```powershell
docker compose down -v
```

이 명령은 로컬 MariaDB, Qdrant, fastembed 캐시 볼륨을 모두 삭제합니다. 필요한 자료를 백업한 뒤에만 사용하세요.

## 문제 해결

- 포트가 사용 중이면 `.env`의 `WEB_PORT` 또는 `MARIADB_PORT`를 빈 포트로 바꾸고 서비스를 재시작합니다.
- 처음 `rag-index`를 실행하면 fastembed 모델을 다운로드하므로 시간이 걸립니다. 다음 실행부터는 지정된 캐시 볼륨을 재사용합니다.
- `docker compose ps`와 `docker compose logs api web mariadb qdrant`로 서비스 상태와 로그를 확인합니다.
