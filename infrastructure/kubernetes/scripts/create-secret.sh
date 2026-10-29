#!/usr/bin/env bash
set -euo pipefail

# 비밀값은 화면에 출력하지 않고 필요한 DB 항목을 확인합니다.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd)"
ENV_FILE="${1:-$ROOT/infrastructure/docker/.env}"
if [[ ! -f "$ENV_FILE" ]]; then
  printf 'Environment file not found: %s\n' "$ENV_FILE" >&2
  exit 1
fi
umask 077
tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

declare -A values=()
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
  key="${line%%=*}"
  case "$key" in
    MARIADB_ROOT_PASSWORD|MARIADB_USER|MARIADB_PASSWORD|DEEPSEEK_API_KEY|DEEPSEEK_MODEL|DEEPSEEK_PLANNER_API_KEY|DEEPSEEK_PLANNER_MODEL)
      values["$key"]="${line#*=}"
      ;;
  esac
done < "$ENV_FILE"
for key in MARIADB_ROOT_PASSWORD MARIADB_USER MARIADB_PASSWORD; do
  if [[ -z "${values[$key]:-}" ]]; then
    printf 'Required key %s is missing or empty in %s\n' "$key" "$ENV_FILE" >&2
    exit 1
  fi
done
# 선택 항목은 값이 있을 때만 넣는다(빈 모델 이름이 앱 기본값을 덮지 않게).
for key in MARIADB_ROOT_PASSWORD MARIADB_USER MARIADB_PASSWORD DEEPSEEK_API_KEY DEEPSEEK_MODEL DEEPSEEK_PLANNER_API_KEY DEEPSEEK_PLANNER_MODEL; do
  if [[ -n "${values[$key]:-}" ]]; then printf '%s=%s\n' "$key" "${values[$key]}" >> "$tmp_file"; fi
done
kubectl create secret generic kervion-secrets --namespace kervion --from-env-file="$tmp_file" --dry-run=client -o yaml | kubectl apply -f -
