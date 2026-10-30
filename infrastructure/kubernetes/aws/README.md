# AWS EKS 켜기·끄기 (K05)

**아직 실제 AWS에 만들지 않았다.** 파일과 스크립트는 오프라인 검증(렌더링·테스트)까지 했다. 2026-10-30 공식 문서로 확인: EKS 1.36 사용 가능(표준 지원 2027-08-02까지), `cluster.yaml`의 필드(`autoApplyPodIdentityAssociations`, `useDefaultPodIdentityAssociations`, `podIdentityAssociations[].createServiceAccount`·`wellKnownPolicies.awsLoadBalancerController`, `disableIMDSv1`, `nat.gateway: Disable`)가 eksctl 스키마에 있음, Load Balancer Controller 차트 최신이 고정값 3.6.2. 실제 만들 때는 `eksctl create cluster -f ... --dry-run`으로 한 번 더 본다.

설계와 이유: 팀 worklog의 K05 설계안. 요약하면 서울 리전, EKS 1.36, t3.large 1대(2a 고정), 공용 서브넷 2개 AZ·NAT 없음, EBS gp3, ALB + HTTPS, ECR 이미지는 커밋 SHA 태그.

## 비용

켜 두면 시간당 약 $0.25(하루 약 $6). **시연·검증할 때만 만들고 끝나면 지운다.** 만들기 전에 AWS Budgets 알림($20)을 먼저 만든다.

## 준비 (한 번만)

1. `aws login`으로 임시 자격을 받는다. 장기 액세스 키를 만들지 않는다.
2. AWS Budgets 알림, ECR 저장소 `kervion-backend`·`kervion-web`(수명 주기: 최근 5개 보관), 도메인의 ACM 인증서(`ISSUED`)를 만든다.
3. `aws/aws.env.example`을 `aws/aws.env`로 복사해 `ECR_REGISTRY`, `DOMAIN`, `CERT_ARN`을 채운다(gitignore).
4. `infrastructure/docker/.env.example` 형식으로 `aws/.env.aws`를 만든다(gitignore). **DB 비밀번호는 로컬과 다른 새 값**, DeepSeek는 가능하면 사용 한도를 건 별도 키.

## 켜기

```bash
eksctl create cluster -f infrastructure/kubernetes/aws/cluster.yaml     # VPC·노드·Pod Identity·EBS CSI
bash infrastructure/kubernetes/scripts/aws-install-lbc.sh               # Load Balancer Controller (Helm)
# 이미지: 커밋 SHA로 빌드·태그 → ECR push (latest 금지)
bash infrastructure/kubernetes/scripts/create-secret.sh infrastructure/kubernetes/aws/.env.aws aws
bash infrastructure/kubernetes/scripts/deploy.sh aws <SHA>              # 데이터 → Job → api/web → Ingress
```

DNS에서 도메인을 ALB 주소로 연결한 뒤 `smoke.sh https://<도메인>`.

## 끄기

```bash
bash infrastructure/kubernetes/scripts/teardown-aws.sh
```

순서: (선택) DB 덤프 → **Ingress 삭제 후 ALB가 사라질 때까지 대기** → namespace 삭제(EBS도 삭제) → Controller 제거 → `eksctl delete cluster` → 남은 EBS·로드밸런서·보안그룹·EIP·CloudFormation 스택 출력. 출력에 남은 자원이 있으면 콘솔에서 지운다. Ingress를 먼저 지우지 않으면 ALB가 남아 요금이 계속 나간다.

컨텍스트: 로컬은 `docker-desktop`(환경변수 `KUBE_CONTEXT`로 변경), AWS는 `aws/aws.env`의 필수 `KUBE_CONTEXT`를 사용한다. `kubectl config get-contexts`에서 확인한 이름을 넣는다.
