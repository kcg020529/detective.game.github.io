#!/usr/bin/env bash
set -euo pipefail

# API와 색인의 메모리 사용이 겹치지 않게 멈추고 실패해도 API를 복구한다.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
OVERLAY="${1:-local}"
if (( $# > 2 )); then
  printf '%s\n' 'Usage: reindex.sh [local | aws IMAGE_TAG]' >&2
  exit 2
fi
source "$SCRIPT_DIR/render.sh"
resolve_kube_context "$OVERLAY"
MANIFESTS="$(render_overlay "$OVERLAY" "${2:-}")"

restore_api() {
  local status=$?
  trap - EXIT
  kc scale deployment/api --namespace kervion --replicas=1 || exit 1
  kc rollout status deployment/api --namespace kervion --timeout=600s || exit 1
  exit "$status"
}
trap restore_api EXIT

kc scale deployment/api --namespace kervion --replicas=0
kc rollout status deployment/api --namespace kervion --timeout=300s
kc wait --for=delete pod --namespace kervion --selector=app.kubernetes.io/name=api --timeout=300s
kc delete job rag-index --namespace kervion --ignore-not-found=true --wait=true
# set env --local은 혼합 리소스의 selector를 적용하지 않아 Job 문서만 넘긴다.
printf '%s\n' "$MANIFESTS" | awk 'BEGIN { RS = "\n---\n" } /\nkind: Job\n/ && /\n  name: rag-index\n/ { print }' | kc set env --local -f - --selector=app.kubernetes.io/name=rag-index --containers=rag-index KERVION_RAG_FORCE=1 -o yaml | kc apply -f - --selector=app.kubernetes.io/name=rag-index
if ! kc wait --for=condition=complete job/rag-index --namespace kervion --timeout=1200s; then
  kc logs job/rag-index --namespace kervion --all-containers=true --tail=50 || true
  printf '%s\n' 'Job rag-index failed; API will be restored.' >&2
  exit 1
fi
