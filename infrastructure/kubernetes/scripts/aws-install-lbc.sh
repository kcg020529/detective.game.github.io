#!/usr/bin/env bash
set -euo pipefail

# 2026-10-30 eks-charts 최신(3.6.2)과 eksctl 스키마의 Pod Identity 필드를 확인했다. 올리기 직전 한 번 더 본다.
LBC_CHART_VERSION='3.6.2'
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/render.sh"
read_aws_env
cluster_info="$(aws eks describe-cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" --query 'cluster.[arn,resourcesVpcConfig.vpcId]' --output text)"
read -r KUBE_CONTEXT VPC_ID <<< "$cluster_info"
[[ -n "$KUBE_CONTEXT" && "$KUBE_CONTEXT" != None && -n "$VPC_ID" && "$VPC_ID" != None ]] || exit 1

# ARN 컨텍스트를 명시해 현재 로컬 컨텍스트에 설치하지 않는다.
helm repo add eks https://aws.github.io/eks-charts --force-update
helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
  --namespace kube-system --kube-context "$KUBE_CONTEXT" --version "$LBC_CHART_VERSION" \
  --set clusterName="$CLUSTER_NAME" --set serviceAccount.create=false \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set region="$AWS_REGION" --set vpcId="$VPC_ID"
kubectl --context "$KUBE_CONTEXT" rollout status deployment/aws-load-balancer-controller --namespace kube-system --timeout=300s
