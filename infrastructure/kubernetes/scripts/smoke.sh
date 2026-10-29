#!/usr/bin/env bash
set -euo pipefail

# 임시 사용자를 생성하고 기본 채팅 흐름을 확인합니다.
BASE_URL="${1:-http://localhost:30080}"
BASE_URL="${BASE_URL%/}"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
cookies="$tmp_dir/cookies"
body="$tmp_dir/body"

request_status() {
  curl -sS -b "$cookies" -c "$cookies" -o "$body" -w '%{http_code}' "$@"
}

status="$(request_status "$BASE_URL/")"
printf 'GET /: %s\n' "$status"
[[ "$status" == 200 ]] || exit 1
status="$(request_status "$BASE_URL/config.js")"
printf 'GET /config.js: %s\n' "$status"
[[ "$status" == 200 ]] || exit 1
status="$(request_status "$BASE_URL/api/v1/auth/me")"
printf 'GET /api/v1/auth/me: %s\n' "$status"
[[ "$status" == 401 ]] || exit 1

suffix="$(date +%s)${RANDOM}${RANDOM}"
username="k8s_smoke_${suffix}"
password="K8s-Smoke-${RANDOM}-${RANDOM}-Aa"
printf '{"username":"%s","password":"%s","role":"prof"}' "$username" "$password" > "$tmp_dir/signup.json"
status="$(request_status -H 'Content-Type: application/json' --data-binary "@$tmp_dir/signup.json" "$BASE_URL/api/v1/auth/signup")"
printf 'POST /api/v1/auth/signup: %s\n' "$status"
[[ "$status" == 201 ]] || exit 1
printf '{"slot_no":1,"role":"prof","overwrite":false}' > "$tmp_dir/save.json"
status="$(request_status -H 'Content-Type: application/json' --data-binary "@$tmp_dir/save.json" "$BASE_URL/api/v1/saves")"
printf 'POST /api/v1/saves: %s\n' "$status"
[[ "$status" == 201 ]] || exit 1
save_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["save_id"])' "$body")"
request_id="k8s-smoke-${suffix}"
printf '{"message":"\uc548\ub155, \uac8c\uc784 \uc9c4\ud589\uc744 \ub3c4\uc640\uc918","client_request_id":"%s"}' "$request_id" > "$tmp_dir/chat.json"
status="$(request_status -H 'Content-Type: application/json' --data-binary "@$tmp_dir/chat.json" "$BASE_URL/api/v1/saves/$save_id/chats/YB-1")"
printf 'POST /api/v1/saves/<id>/chats/YB-1: %s\n' "$status"
if [[ "$status" == 200 ]]; then
  response_type="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["messages"][-1]["response_type"])' "$body")"
  printf 'response_type: %s\n' "$response_type"
  printf '%s\n' 'chat OK'
elif [[ "$status" == 503 ]]; then
  keys_empty="$(kubectl get secret kervion-secrets -n kervion -o json | python3 -c 'import base64,json,sys; d=json.load(sys.stdin).get("data",{}); print("true" if all(not base64.b64decode(d.get(k, "")).strip() for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_PLANNER_API_KEY")) else "false")')"
  if [[ "$keys_empty" == true ]]; then
    printf '%s\n' 'chat 503 (expected only when DeepSeek keys are empty; this is NOT a chat pass)'
  else
    printf '%s\n' 'chat FAIL (503 while DeepSeek keys are present)'
    exit 1
  fi
else
  printf '%s\n' 'chat FAIL'
  exit 1
fi
