#!/usr/bin/env bash
set -euo pipefail

# Job도 overlay로 렌더링하되 이름으로 골라 적용해 데이터·앱 계층에서는 실행하지 않는다.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
OVERLAY="${1:-local}"
if (( $# > 2 )); then
  printf '%s\n' 'Usage: deploy.sh [local | aws IMAGE_TAG]' >&2
  exit 2
fi
source "$SCRIPT_DIR/render.sh"
# 치환·검증을 마친 하나의 결과를 모든 계층과 Job에 공통 사용한다.
MANIFESTS="$(render_overlay "$OVERLAY" "${2:-}")"

apply_layer() {
  local selector="$1"
  printf '%s\n' "$MANIFESTS" | kubectl apply -f - --selector="$selector"
}

apply_layer 'app.kubernetes.io/name=namespace'
if ! kubectl get secret kervion-secrets --namespace kervion >/dev/null 2>&1; then
  printf '%s\n' 'Secret kervion-secrets is missing; run infrastructure/kubernetes/scripts/create-secret.sh first.' >&2
  exit 1
fi

apply_layer 'app.kubernetes.io/tier in (shared,data)'
kubectl rollout status statefulset/mariadb --namespace kervion --timeout=300s
kubectl rollout status statefulset/qdrant --namespace kervion --timeout=300s

run_job() {
  local name="$1"
  kubectl delete job "$name" --namespace kervion --ignore-not-found=true --wait=true
  apply_layer "app.kubernetes.io/name=$name"
  if ! kubectl wait --for=condition=complete "job/$name" --namespace kervion --timeout=1200s; then
    kubectl logs "job/$name" --namespace kervion --all-containers=true --tail=50 || true
    printf 'Job %s failed; deployment stopped.\n' "$name" >&2
    exit 1
  fi
}

run_job migrate
run_job load-data
run_job rag-index
apply_layer 'app.kubernetes.io/tier=app'
kubectl rollout status deployment/api --namespace kervion --timeout=600s
kubectl rollout status deployment/web --namespace kervion --timeout=300s
if [[ "$OVERLAY" == aws ]]; then
  apply_layer 'app.kubernetes.io/tier=edge'
fi
