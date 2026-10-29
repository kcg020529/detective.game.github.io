#!/usr/bin/env bash
set -euo pipefail

# PVC 삭제는 데이터를 지우므로 확인이 필요합니다.
DELETE_DATA=false
CONFIRMED=false
for arg in "$@"; do
  case "$arg" in
    --delete-data) DELETE_DATA=true ;;
    --yes) CONFIRMED=true ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done
if "$DELETE_DATA"; then
  printf '%s\n' 'WARNING: deleting PVCs permanently destroys the MariaDB, Qdrant, and model-cache data.' >&2
  if ! "$CONFIRMED"; then
    printf 'Type yes to continue: ' >&2
    read -r answer
    [[ "$answer" == yes ]] || { printf '%s\n' 'Cancelled.'; exit 1; }
  fi
fi
kubectl delete --namespace kervion --ignore-not-found=true --wait=true \
  deployment/api deployment/web statefulset/mariadb statefulset/qdrant \
  service/api service/web service/mariadb service/qdrant \
  job/migrate job/load-data job/rag-index configmap/kervion-config configmap/kervion-nginx
if "$DELETE_DATA"; then
  kubectl delete --namespace kervion --ignore-not-found=true pvc/data-mariadb-0 pvc/storage-qdrant-0 pvc/fastembed-cache
fi
