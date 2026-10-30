# Kubernetes 배포 (K04 로컬, K05 AWS 준비)

Docker Compose와 같은 이미지 두 개(`kervion-backend`, `kervion-web`)를 Kubernetes에서 실행한다. 공통 설정은 `base/`, 환경별 값은 `overlays/<환경>/`에 둔다. **노드 1대짜리 시연용 구성**이며 고가용성 구성이 아니다.

```
base/              namespace, configmap, mariadb, qdrant, fastembed-cache PVC, api, web, jobs/
overlays/local/    Docker Desktop: 이미지 :k8s, web NodePort 30080, http 쿠키
overlays/aws/      EKS: ECR 이미지 :<커밋 SHA>, gp3 StorageClass, ALB Ingress, https 쿠키 (aws/README.md)
scripts/           build-images, create-secret, deploy, reindex, smoke, teardown, render, aws-*
aws/               eksctl cluster.yaml, aws.env.example
```

## 로컬 실행 (Docker Desktop Kubernetes)

Git Bash에서 저장소 루트 기준으로 실행한다.

```bash
bash infrastructure/kubernetes/scripts/build-images.sh                 # kervion-backend:k8s, kervion-web:k8s
bash infrastructure/kubernetes/scripts/create-secret.sh <env 파일> local # 기본 infrastructure/docker/.env, 값은 출력하지 않음
bash infrastructure/kubernetes/scripts/deploy.sh local                 # 데이터 → Job 3개 → api/web 순서
bash infrastructure/kubernetes/scripts/smoke.sh                        # http://localhost:30080
```

- `deploy.sh`는 단계마다 기다리고 실패하면 멈춘다. 순서: namespace·Secret 확인 → ConfigMap·PVC·MariaDB·Qdrant → `migrate` → `load-data` → `rag-index` → api·web.
- 접속: http://localhost:30080
- smoke는 시험 계정을 지우지 않는다. 확인 후 DB에서 `k8s_smoke_%` 사용자의 Save를 먼저, 사용자를 다음에 지운다(`saves`가 `users`를 RESTRICT로 참조).
- 배포 스크립트를 실행하는 동안 같은 스크립트 파일을 고치지 않는다. bash는 실행 중에 파일을 이어서 읽는다.

AWS Secret은 `bash infrastructure/kubernetes/scripts/create-secret.sh infrastructure/kubernetes/aws/.env.aws aws`로 만든다.

## 무엇이 바뀌면 무엇을 다시 실행하나

| 바뀐 것 | 실행 |
|---|---|
| 코드만 | 이미지 다시 빌드 후 `deploy.sh` (변경 없는 색인은 생략) |
| DB 구조 (`database/schemas/mariadb/*.sql`) | **먼저 DB 백업**, 그다음 `deploy.sh` (migrate가 새 파일만 적용) |
| 시나리오 기록·권한 표 | `deploy.sh` (load-data와 rag-index 포함) |
| 임베딩 설정 | `reindex.sh <overlay>` 후 api 재시작 |

`reindex.sh`는 api를 0으로 줄이고 강제 색인한 뒤 1로 되돌린다. 직접 색인 명령도 `--force`로 생략 없이 다시 만들 수 있다. 색인이 실패해도 api를 되돌린다.

## 되돌리기와 복구

- **이미지 롤백**은 코드만 되돌린다. AWS는 `deploy.sh aws <이전 SHA>`로 되돌린다. `kubectl rollout undo`도 동작하지만 마지막 apply 기록과 어긋난다는 경고가 나와 비상용으로만 쓴다.
- **DB는 이미지 롤백으로 돌아가지 않는다.** migrate는 앞으로만 간다. DB 구조가 바뀌는 배포 전에 덤프를 받는다:
  ```bash
  MSYS_NO_PATHCONV=1 kubectl -n kervion exec mariadb-0 -- sh -c \
    'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-dump --user=root --single-transaction --routines kervion' > kervion.sql
  ```
  복원은 같은 방식으로 `mariadb --user=root kervion < kervion.sql`(`kubectl exec -i`).
- **검색 색인**은 `reindex.sh`로 언제든 다시 만든다(원본은 MariaDB·저장소).

## 지우기

```bash
bash infrastructure/kubernetes/scripts/teardown.sh                 # api·web·Job 삭제, 데이터(PVC) 유지
bash infrastructure/kubernetes/scripts/teardown.sh --delete-data   # PVC까지 삭제: 사용자·Save·대화가 사라짐
```

데이터를 남긴 채 잠시 멈추려면 `kubectl -n kervion scale sts/mariadb sts/qdrant deploy/api deploy/web --replicas=0`.

## Windows Git Bash 주의

`kubectl exec ... -- cat /sys/...`처럼 `/`로 시작하는 인자는 Git Bash가 Windows 경로로 바꾼다. 앞에 `MSYS_NO_PATHCONV=1`을 붙인다.

컨텍스트: 로컬은 `docker-desktop`(환경변수 `KUBE_CONTEXT`로 변경), AWS는 `aws/aws.env`의 필수 `KUBE_CONTEXT`를 사용한다. `kubectl config get-contexts`에서 확인한 이름을 넣는다.
