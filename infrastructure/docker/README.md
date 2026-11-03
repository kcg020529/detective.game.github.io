# 로컬 전체 실행 (Docker Compose)

MariaDB·Qdrant·백엔드 API·웹(nginx)을 한 번에 띄운다. 처음이라면 아래 "준비"를 마친 뒤 [전체 앱 실행](#전체-앱-실행)을 따른다.

| 서비스 | 하는 일 |
|---|---|
| `mariadb`, `qdrant` | DB, 검색 색인 |
| `api` | FastAPI (`backend/`를 연결해 저장하면 자동 재시작) |
| `web` | `frontend/`를 그대로 보여 주고 `/api/`를 `api`로 넘김. http://127.0.0.1:8080 |
| `migrate`, `load-data`, `rag-index` | 필요할 때 `docker compose run --rm <이름>`으로 실행하는 도구 |
| `grafana` (선택) | 보안 대시보드. `docker-compose.grafana.yml`을 함께 지정할 때만 실행 ([아래](#grafana-보안-대시보드-선택-실행)) |

Kubernetes(로컬·AWS) 배포는 `infrastructure/kubernetes/README.md`를 따른다.

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

## Grafana 보안 대시보드 (선택 실행)

Grafana는 `docker-compose.grafana.yml`을 함께 지정할 때만 실행한다. `audit_events`의
Input·Output Guard 메타데이터를 MariaDB에서 읽는다. `allow` 질문은 저장하지 않아
전체 질문 수를 보여주지 않는다. 이제 Grafana의 직접 포트는 열지 않고, 웹사이트
관리자만 `http://127.0.0.1:8080/admin/audit`에서 대시보드를 본다.

1. `infrastructure/docker/.env`에 `GRAFANA_ADMIN_PASSWORD`와
   `GRAFANA_DB_PASSWORD`를 각각 긴 임의 문자열로 설정한다. `.env.example`에는
   자리만 있으며 실제 비밀번호는 Git에 올리지 않는다.
2. MariaDB에 `012_audit_events.sql` 테이블이 있어야 한다. 신규 볼륨이면 초기화
   때 자동 적용된다. 기존 볼륨에 없으면 `infrastructure/docker`에서
   `docker compose exec mariadb mariadb -u root -p`로 DB에 접속한 뒤
   `SOURCE /docker-entrypoint-initdb.d/012_audit_events.sql;`을 한 번 실행한다.
3. 저장소 루트에서 백엔드 의존성을 설치한 파이썬으로 전용 읽기 계정을 만든다.

   ```bash
   python infrastructure/docker/setup_grafana_reader.py
   ```

   이 계정은 `audit_events` 테이블에 대한 `SELECT`만 받는다.
4. 기존 DB에는 `015_site_admins.sql`을 적용한다. 저장소 루트에서
   `python -m infrastructure.docker.migrate`를 실행하거나 기존 Compose의
   `migrate` 서비스를 사용한다. 신규 DB에는 초기화 때 자동 적용된다.
   그 뒤 기존 웹 로그인 아이디에만 관리자 권한을 부여한다.

   ```bash
   python -m infrastructure.docker.grant_site_admin symin123
   ```

   이 명령은 사용자 계정이 없으면 실패하며, 회원가입 시 관리자를 만들지 않는다.
5. `infrastructure/docker`에서 API·웹·Grafana를 함께 실행한다.

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.grafana.yml up -d api web grafana
   ```

6. KERVION 웹사이트에 `symin123`으로 로그인한 뒤
   [관리자 대시보드](http://127.0.0.1:8080/admin/audit)를 연다. 다른 계정과
   비로그인 사용자는 접근할 수 없다. 외부 도메인에서 사용할 때는
   `GRAFANA_PUBLIC_ROOT_URL=https://<웹주소>/api/v1/admin/grafana/`를 설정한다.

대시보드 설정은 `infrastructure/docker/grafana/`의 파일로 관리한다. UI에서
바꾼 내용은 소스 파일에 자동 저장되지 않는다. Grafana만 멈추려면
`docker compose -f docker-compose.yml -f docker-compose.grafana.yml stop grafana`를
사용한다. Grafana는 Docker 내부 네트워크에서만 열리며, 웹 프록시는 매 요청마다
KERVION 세션과 관리자 권한을 확인한다. 이전 버전의 직접 포트가 남아 있다면
Grafana 컨테이너를 새 Compose 설정으로 재생성해야 한다.

### Discord 보안 감사 알림 (선택 실행)

Discord 채널에서 웹훅을 만든 뒤 URL을 `infrastructure/docker/.env`의
`KERVION_DISCORD_WEBHOOK_URL`에 넣는다. URL은 Git이나 채팅에 올리지 않는다.
저장소의 알림 설정은 최근 1분간의 감사 이벤트를 10초 간격으로 평가한다.
Input Guard는 `high_risk`를 요청 ID별로, Output Guard는 `level=alert`이거나
`applied=mask/block`인 이벤트를 이벤트 ID별로 보낸다. 따라서 출력 `log`도
마스킹·차단이 적용되면 알림 대상이다. 정책 거부는 `policy_denial`을 이벤트
ID별로 보낸다. 입력 `allow`·`warn`은 Discord 알림 대상이 아니다.

제목은 `INPUT`·`OUTPUT`·`POLICY`로 구분하고, 본문은 판정·처리·신호·요청 ID
순서로 표시한다. 출력에는 검사 모드와 적용 결과도 포함한다. 입력의
`role_or_state_override` 유형은 초록색, 그 밖의 고위험 입력과 출력 차단·중단은
빨간색, 출력 마스킹·관찰 모드와 정책 기록 제외는 주황색이다. 초록색도 입력
판정은 `high_risk`이며 일반 답변 생성으로 진행하지 않는다. 여백은 본문 위에만
두며, 첫 줄의 U+2800 공백 문자는 Discord 표시용이므로 제거하지 않는다.
질문·답변 원문, 비밀값과 계정 정보는 보내지 않는다.

출력의 응답 중단 표시는 `applied`와 탐지 신호를 현재 채팅 어댑터의 처리 규칙에
대응한 결과이며, 최종 HTTP 상태 자체를 조회하는 것은 아니다. 같은 사건의
재알림 간격은 30분이며, 전송은 평가 시각과 Grafana 처리에 따라 지연될 수 있다.
설정을 수정하면 Grafana를 재생성해야 하며, 이미 도착한 메시지는 변경되지 않는다.

`infrastructure/docker`에서 다음처럼 Discord 설정 파일을 추가해 Grafana를
재생성한다. URL이 비어 있으면 이 명령은 시작 전에 실패한다.

```bash
docker compose -f docker-compose.yml -f docker-compose.grafana.yml -f docker-compose.discord.yml up -d --force-recreate grafana
```

Grafana의 **Alerting → Alert rules**에서 Input Guard·Output Guard·정책 거부의
3개 규칙을, **Contact points**에서 각각의 Discord 연락처를 확인한다. 실제
조건 검증에는 해당 유형의 시험용 감사 이벤트가 필요하다. Discord 설정을 쓰지 않을 때는
`docker-compose.discord.yml`을 빼고 기존 Compose 명령으로 Grafana를 재생성한다.

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

MariaDB, Qdrant, web 포트는 `127.0.0.1`에만 바인딩한다. Grafana는 호스트 포트를 열지 않는다.

## 참고

- 데이터 볼륨 이름: `kervion_mariadb_data`, `qdrant_storage`, 선택 실행 시 `kervion_grafana_data`
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
