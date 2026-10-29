#!/usr/bin/env bash
set -euo pipefail

# Docker Desktop은 로컬 이미지를 직접 사용하고 kind는 이미지 로드가 필요합니다.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
docker build -t kervion-backend:k8s -f "$ROOT/infrastructure/docker/Dockerfile.backend" "$ROOT"
docker build -t kervion-web:k8s -f "$ROOT/infrastructure/kubernetes/Dockerfile.web" "$ROOT"
printf '%s\n' "Docker Desktop uses these local images directly; kind requires kind load docker-image."
