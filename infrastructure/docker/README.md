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

- 데이터 볼륨 이름: `kervion_mariadb_data`, `qdrant_storage`
- 예전에 Compose 없이 `qdrant_storage` 볼륨을 만든 PC에서는 `volume "qdrant_storage" already exists but was not created by Docker Compose` 경고가 뜸. 기존 데이터를 그대로 이어 쓰는 것이라 무시해도 됨
- 3306 포트를 이미 다른 MariaDB·MySQL이 쓰고 있으면 `.env`의 `MARIADB_PORT`를 다른 값(예: 3307)으로 바꿈
