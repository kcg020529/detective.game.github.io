#!/usr/bin/env bash
set -euo pipefail

# 데이터와 EBS가 삭제된다. ALB가 사라지기 전에는 네임스페이스·클러스터를 지우지 않는다.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/render.sh"
ROOT="$(cd -- "$K8S_DIR/../.." && pwd)"
read_aws_env
if [[ "$CLUSTER_NAME" != kervion || "$AWS_REGION" != ap-northeast-2 ]]; then
  printf '%s\n' 'Settings must match aws/cluster.yaml: kervion in ap-northeast-2.' >&2
  exit 2
fi
CONFIRMED=false
case "${1:-}" in
  '') ;;
  --yes) CONFIRMED=true ;;
  *) printf '%s\n' 'Usage: teardown-aws.sh [--yes]' >&2; exit 2 ;;
esac
(( $# <= 1 )) || exit 2
printf '%s\n' 'WARNING: this destroys cluster user data, saves, chats, and PVC/EBS data.' >&2
if ! "$CONFIRMED"; then
  printf 'Type cluster name %s to continue: ' "$CLUSTER_NAME" >&2
  read -r answer
  [[ "$answer" == "$CLUSTER_NAME" ]] || { printf '%s\n' 'Cancelled.'; exit 1; }
fi

# eksctl이 만든 컨텍스트 이름은 ARN이 아니라서 aws.env의 KUBE_CONTEXT를 확인해 쓴다.
resolve_kube_context aws
if ! "$CONFIRMED"; then
  printf '%s' 'Create a MariaDB backup first? [y/N] ' >&2
  read -r backup
  if [[ "$backup" == y || "$backup" == yes ]]; then
    umask 077
    mkdir -p "$ROOT/worklog/backups"
    dump="$ROOT/worklog/backups/${CLUSTER_NAME}-$(date -u +%Y%m%dT%H%M%SZ).sql"
    if ! kubectl --context "$KUBE_CONTEXT" exec --namespace kervion mariadb-0 -- \
      sh -c 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-dump --user=root --single-transaction --all-databases' > "$dump.tmp"; then
      rm -f "$dump.tmp"
      printf '%s\n' 'Backup failed; teardown stopped.' >&2
      exit 1
    fi
    mv "$dump.tmp" "$dump"
    printf 'Backup saved: %s\n' "$dump"
  fi
else
  printf '%s\n' 'Non-interactive mode: optional database backup skipped.' >&2
fi

cluster_load_balancers() {
  local arns arn matches
  arns="$(aws elbv2 describe-load-balancers --region "$AWS_REGION" --query 'LoadBalancers[].LoadBalancerArn' --output text)" || return
  for arn in $arns; do
    [[ "$arn" == None ]] && continue
    matches="$(aws elbv2 describe-tags --region "$AWS_REGION" --resource-arns "$arn" \
      --query "length(TagDescriptions[0].Tags[?(Key=='elbv2.k8s.aws/cluster' && Value=='$CLUSTER_NAME') || Key=='kubernetes.io/cluster/$CLUSTER_NAME'])" --output text)" || return
    if [[ "$matches" =~ ^[0-9]+$ ]] && (( matches > 0 )); then
      printf '%s\n' "$arn"
    elif [[ ! "$matches" =~ ^[0-9]+$ ]]; then
      printf '%s\n' 'Could not verify load-balancer tags; teardown stopped.' >&2
      return 1
    fi
  done
}

kubectl --context "$KUBE_CONTEXT" delete ingress --all --namespace kervion --wait=true --timeout=300s
deadline=$((SECONDS + 900))
remaining="$(cluster_load_balancers)"
while [[ -n "$remaining" ]]; do
  if (( SECONDS >= deadline )); then
    printf '%s\n' 'ALB deletion timed out; namespace and cluster were retained.' >&2
    exit 1
  fi
  sleep 10
  remaining="$(cluster_load_balancers)"
done
kubectl --context "$KUBE_CONTEXT" delete namespace kervion --wait=true --timeout=600s
helm uninstall aws-load-balancer-controller --namespace kube-system --kube-context "$KUBE_CONTEXT" --wait
eksctl delete cluster -f "$K8S_DIR/aws/cluster.yaml" --wait

# 태그가 다른 잔여 자원도 확인할 수 있도록 EIP는 리전 전체를 표시한다.
failed=0
printf '%s\n' 'Remaining cluster/PVC EBS volumes:'
aws ec2 describe-volumes --region "$AWS_REGION" \
  --query "Volumes[?Tags[?Key=='kubernetes.io/cluster/$CLUSTER_NAME' || (Key=='alpha.eksctl.io/cluster-name' && Value=='$CLUSTER_NAME') || (Key=='kubernetes.io/created-for/pvc/namespace' && Value=='kervion')]].{Id:VolumeId,State:State,Tags:Tags}" --output json || failed=1
printf '%s\n' 'Remaining cluster load balancers:'
cluster_load_balancers || failed=1
printf '%s\n' 'Remaining cluster security groups:'
aws ec2 describe-security-groups --region "$AWS_REGION" \
  --query "SecurityGroups[?Tags[?Key=='kubernetes.io/cluster/$CLUSTER_NAME' || ((Key=='alpha.eksctl.io/cluster-name' || Key=='aws:eks:cluster-name') && Value=='$CLUSTER_NAME')]].{Id:GroupId,Name:GroupName}" --output json || failed=1
printf '%s\n' 'Regional EIPs (review ownership):'
aws ec2 describe-addresses --region "$AWS_REGION" --query 'Addresses[].{Id:AllocationId,IP:PublicIp,Tags:Tags}' --output json || failed=1
printf '%s\n' 'Remaining eksctl stacks:'
aws cloudformation describe-stacks --region "$AWS_REGION" \
  --query "Stacks[?starts_with(StackName, 'eksctl-$CLUSTER_NAME-')].{Name:StackName,Status:StackStatus}" --output json || failed=1
printf '%s\n' 'CloudFront remains for the next session. To delete it, disable the kervion distribution in the CloudFront console, wait for deployment, then delete it.'
exit "$failed"
