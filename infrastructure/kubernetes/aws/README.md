# AWS EKS + CloudFront 켜기·끄기 (K05)

**실제 AWS 배포는 아직 검증하지 않았다.** 파일·렌더링·가짜 CLI 시험까지 한 구성이다. EKS 1.36, 서울 리전, t3.large 1대(2a 고정), 공용 서브넷 2개 AZ·NAT 없음, EBS gp3를 쓴다. 실제 만들기 전에 `cluster.yaml` 필드와 Load Balancer Controller 차트 버전을 다시 확인한다.

접속 경로: 브라우저 → `https://dXXXX.cloudfront.net` → ALB HTTP:80 → web nginx → api. CloudFront 기본 인증서를 쓰며 별도 도메인은 필요 없다. ALB는 CloudFront origin-facing 관리형 prefix list만 허용한다. Viewer Host를 그대로 전달하므로 Ingress에는 host 조건을 두지 않는다.

## 준비 (한 번만)

1. `aws login`으로 임시 자격을 받는다. CLI는 `AWS_PROFILE` 환경변수를 따른다. 장기 액세스 키를 만들지 않는다.
2. (선택) AWS Budgets 알림, ECR 저장소 `kervion-backend`·`kervion-web`(최근 이미지 5개 보관)을 준비한다.
3. `aws/aws.env.example`을 `aws/aws.env`로 복사하고 `AWS_REGION`, `CLUSTER_NAME`, `ECR_REGISTRY`를 채운다(gitignore). `KUBE_CONTEXT`는 클러스터 생성 뒤 `kubectl config get-contexts`에서 확인해 넣는다.
4. 아래 prefix list ID를 한 번 조회해 `CF_PREFIX_LIST`에 넣는다.
   ```bash
   aws ec2 describe-managed-prefix-lists --region ap-northeast-2 \
     --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
     --query 'PrefixLists[0].PrefixListId' --output text
   ```
5. `infrastructure/docker/.env.example` 형식으로 `aws/.env.aws`를 만든다(gitignore). DB 비밀번호는 로컬과 다른 새 값, DeepSeek는 가능하면 사용 한도를 건 별도 키를 쓴다.
6. 배포 도구에 AWS CLI, eksctl, Helm, kubectl, Git Bash와 프로젝트에서 쓰는 Python(`python`, 표준 라이브러리만 사용)이 필요하다.

## CloudFront 만들기 (한 번만)

```bash
bash infrastructure/kubernetes/scripts/aws-cloudfront.sh create
```

출력된 `DOMAIN=dXXXX.cloudfront.net`을 `aws/aws.env`에 넣는다. Comment가 `kervion`인 배포가 이미 있으면 기존 주소를 출력하고 새로 만들지 않는다. 같은 Comment가 여러 개면 멈춘다.

기본 origin `example.com`은 첫 `sync` 전의 자리표시자다. 첫 sync가 끝나기 전에는 게임에 접속하지 않는다. 필요하면 `create <origin-hostname>`으로 초기 origin을 지정할 수 있다. CloudFront는 한 번 만든 뒤 세션 사이에 유지하므로 DOMAIN이 바뀌지 않는다.

## 클러스터 켜기 (다음 세션도 여기부터)

```bash
eksctl create cluster -f infrastructure/kubernetes/aws/cluster.yaml
# kubectl config get-contexts에서 확인한 이름을 aws/aws.env의 KUBE_CONTEXT에 넣는다.
bash infrastructure/kubernetes/scripts/aws-install-lbc.sh
# 커밋 SHA로 이미지 2개 빌드·태그 → ECR push (latest 금지)
bash infrastructure/kubernetes/scripts/create-secret.sh infrastructure/kubernetes/aws/.env.aws aws
bash infrastructure/kubernetes/scripts/deploy.sh aws <SHA>
bash infrastructure/kubernetes/scripts/aws-cloudfront.sh sync
bash infrastructure/kubernetes/scripts/smoke.sh https://dXXXX.cloudfront.net
```

`sync`는 지정한 컨텍스트의 Ingress에서 ALB 주소를 최대 600초 기다린다. 기존 배포 설정과 ETag를 읽어 `alb` origin 주소만 바꾸고 CloudFront 배포 완료까지 기다린다. aws.env의 DOMAIN이 해당 배포 주소와 다르면 변경하지 않는다. 매번 새 ALB가 생겨도 접속 주소는 그대로다.

캐시는 CachingDisabled, origin 요청 정책은 AllViewerAndCloudFrontHeaders-2022-06이다. 쿠키·query·viewer Host와 CloudFront 클라이언트 주소/프로토콜 헤더를 전달한다. nginx는 CloudFront-Viewer-Address의 포트를 제거해 IP별 제한을 적용하고, CloudFront-Forwarded-Proto를 우선한다.

**60초를 넘는 채팅 응답은 CloudFront에서 504로 끊길 수 있다.** 클라이언트에서 같은 요청을 다시 보내면 저장된 응답을 재생한다. 프론트 채팅 제한도 60초이고 nginx는 90초다.

## 끄기

```bash
bash infrastructure/kubernetes/scripts/teardown-aws.sh
```

(선택) DB 덤프 → Ingress 삭제 후 ALB 삭제 대기 → namespace/PVC 삭제 → Controller 제거 → 클러스터 삭제 → 남은 자원 확인 순서다. 출력에 남은 EBS·로드밸런서·보안그룹·EIP·스택은 소유권을 확인하고 지운다.

CloudFront는 남겨 다음 세션에서 재사용한다. CloudFront는 고정 유지 비용 없이 사용량에 따라 과금된다. 클러스터는 켜 둔 동안 비용이 나므로 시연 뒤 지운다. CloudFront까지 없애려면 콘솔에서 Comment `kervion`인 배포를 비활성화하고 배포 완료 후 삭제한다. 스크립트에는 삭제 명령을 두지 않았다.
