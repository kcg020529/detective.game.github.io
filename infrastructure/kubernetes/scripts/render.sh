#!/usr/bin/env bash
set -euo pipefail

# env 파일은 실행하지 않고 허용된 설정만 읽는다.
K8S_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
read_aws_env() {
  local file="${1:-${KERVION_AWS_ENV_FILE:-$K8S_DIR/aws/aws.env}}" line key value
  AWS_REGION='' ECR_REGISTRY='' DOMAIN='' CF_PREFIX_LIST='' CLUSTER_NAME='' KUBE_CONTEXT=''
  if [[ ! -f "$file" ]]; then
    printf '%s\n' 'AWS settings file is missing; copy aws/aws.env.example to aws/aws.env.' >&2
    return 2
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*(#|$) || "$line" != *=* ]] && continue
    key="${line%%=*}" value="${line#*=}"
    case "$key" in
      AWS_REGION|ECR_REGISTRY|DOMAIN|CF_PREFIX_LIST|CLUSTER_NAME|KUBE_CONTEXT) printf -v "$key" '%s' "$value" ;;
    esac
  done < "$file"
  require_aws_keys AWS_REGION CLUSTER_NAME || return
  if [[ ! "$AWS_REGION" =~ ^[a-z]{2}-[a-z-]+-[0-9]+$ || ! "$CLUSTER_NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*$ ]]; then
    printf '%s\n' 'Invalid AWS_REGION or CLUSTER_NAME.' >&2
    return 2
  fi
}

require_aws_keys() {
  local key
  for key in "$@"; do
    if [[ -z "${!key}" ]]; then
      printf 'Required AWS setting is missing or empty: %s\n' "$key" >&2
      return 2
    fi
  done
}

# 변경 명령은 확인한 컨텍스트만 사용한다.
kc() { kubectl --context "$KUBE_CONTEXT" "$@"; }

resolve_kube_context() {
  local overlay="${1:-local}" contexts context found=false
  case "$overlay" in
    local) KUBE_CONTEXT="${KUBE_CONTEXT:-docker-desktop}" ;;
    aws) read_aws_env || return; require_aws_keys KUBE_CONTEXT || return ;;
    *) printf 'Unknown overlay: %s\n' "$overlay" >&2; return 2 ;;
  esac
  contexts="$(kc config get-contexts -o name)" || return
  while IFS= read -r context; do
    [[ "${context%$'\r'}" != "$KUBE_CONTEXT" ]] || found=true
  done <<< "$contexts"
  if ! "$found"; then
    printf 'Kube context not found: %s\n' "$KUBE_CONTEXT" >&2
    return 2
  fi
  printf 'Kube context: %s\n' "$KUBE_CONTEXT" >&2
}

render_overlay() {
  local overlay="${1:-local}" tag="${2:-}" dir rendered
  dir="$K8S_DIR/overlays/$overlay"
  if (( $# > 3 )) || [[ ! "$overlay" =~ ^[a-zA-Z0-9_-]+$ || ! -f "$dir/kustomization.yaml" ]]; then
    printf 'Overlay not found or invalid arguments: %s\n' "$overlay" >&2
    return 2
  fi
  if [[ "$overlay" == aws ]]; then
    if [[ ! "$tag" =~ ^[a-fA-F0-9]{7,40}$ ]]; then
      printf '%s\n' 'AWS requires a 7-40 hex IMAGE_TAG; empty and latest are forbidden.' >&2
      return 2
    fi
    read_aws_env "${3:-${KERVION_AWS_ENV_FILE:-$K8S_DIR/aws/aws.env}}" || return
    require_aws_keys ECR_REGISTRY DOMAIN CF_PREFIX_LIST || return
    if [[ ! "$ECR_REGISTRY" =~ ^[a-z0-9][a-z0-9.-]+(:[0-9]+)?$ || ! "$DOMAIN" =~ ^[a-z0-9]+\.cloudfront\.net$ || ! "$CF_PREFIX_LIST" =~ ^pl-[0-9a-f]+$ ]]; then
      printf '%s\n' 'Invalid ECR_REGISTRY, DOMAIN or CF_PREFIX_LIST format.' >&2
      return 2
    fi
  elif [[ -n "$tag" ]]; then
    printf '%s\n' 'IMAGE_TAG is supported only for the aws overlay.' >&2
    return 2
  fi
  rendered="$(kubectl kustomize --load-restrictor LoadRestrictionsNone "$dir")" || return
  if [[ "$overlay" == aws ]]; then
    rendered="${rendered//__ECR_REGISTRY__/$ECR_REGISTRY}"
    rendered="${rendered//__IMAGE_TAG__/$tag}"
    rendered="${rendered//__DOMAIN__/$DOMAIN}"
    rendered="${rendered//__CF_PREFIX_LIST__/$CF_PREFIX_LIST}"
    printf 'AWS render: tag=%s domain=%s\n' "$tag" "$DOMAIN" >&2
  fi
  if [[ "$rendered" =~ __[A-Z_]+__ ]]; then
    printf '%s\n' 'Unresolved placeholder in rendered manifests.' >&2
    return 2
  fi
  printf '%s\n' "$rendered"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  render_overlay "$@"
fi
