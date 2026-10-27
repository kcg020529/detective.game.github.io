# 로컬 MariaDB·Qdrant 실행

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
Input Guard 경고 메타데이터를 MariaDB에서 읽어 브라우저에 표시한다. 채팅 전송
API와 감사 자동 저장은 아직 연결되지 않았으므로 실제 이벤트가 없으면 0 또는
빈 그래프가 정상이다. `allow` 질문은 저장하지 않아 전체 질문 수를 보여주지 않는다.

1. `infrastructure/docker/.env`에 `GRAFANA_ADMIN_PASSWORD`와
   `GRAFANA_DB_PASSWORD`를 각각 긴 임의 문자열로 설정한다. `.env.example`에는
   자리만 있으며 실제 비밀번호는 Git에 올리지 않는다. 기본 접속 포트는 3000이다.
2. MariaDB에 `012_audit_events.sql` 테이블이 있어야 한다. 신규 볼륨이면 초기화
   때 자동 적용된다. 기존 볼륨에 없으면 `infrastructure/docker`에서
   `docker compose exec mariadb mariadb -u root -p`로 DB에 접속한 뒤
   `SOURCE /docker-entrypoint-initdb.d/012_audit_events.sql;`을 한 번 실행한다.
3. 저장소 루트에서 백엔드 의존성을 설치한 파이썬으로 전용 읽기 계정을 만든다.

   ```bash
   python infrastructure/docker/setup_grafana_reader.py
   ```

   이 계정은 `audit_events` 테이블에 대한 `SELECT`만 받는다.
4. `infrastructure/docker`에서 실행한다.

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.grafana.yml up -d grafana
   ```

5. [http://127.0.0.1:3000/d/kervion-security-audit](http://127.0.0.1:3000/d/kervion-security-audit)를
   연다. 로그인 이름은 `.env`의 `GRAFANA_ADMIN_USER`(기본 `admin`), 비밀번호는
   `GRAFANA_ADMIN_PASSWORD`다. 비밀번호를 채팅이나 Git에 붙여넣지 않는다.

대시보드 설정은 `infrastructure/docker/grafana/`의 파일로 관리한다. UI에서
바꾼 내용은 소스 파일에 자동 저장되지 않는다. Grafana만 멈추려면
`docker compose -f docker-compose.yml -f docker-compose.grafana.yml stop grafana`를
사용한다. Grafana는 로컬 `127.0.0.1`에만 열린다.

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

초기 SQL은 MariaDB 데이터 볼륨이 비어 있는 첫 실행 때만 실행됨. 스키마를 변경한 경우에는 필요한 데이터를 백업한 뒤 MariaDB 볼륨을 삭제하고 다시 실행해야 함.

두 서비스 포트는 `127.0.0.1`에만 바인딩하여 외부 네트워크에서 직접 접속할 수 없게 제한함.

## 참고

- 데이터 볼륨 이름: `kervion_mariadb_data`, `qdrant_storage`, 선택 실행 시 `kervion_grafana_data`
- 예전에 Compose 없이 `qdrant_storage` 볼륨을 만든 PC에서는 `volume "qdrant_storage" already exists but was not created by Docker Compose` 경고가 뜸. 기존 데이터를 그대로 이어 쓰는 것이라 무시해도 됨
- 3306 포트를 이미 다른 MariaDB·MySQL이 쓰고 있으면 `.env`의 `MARIADB_PORT`를 다른 값(예: 3307)으로 바꿈
