#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/render.sh"

# 설정 출력은 AWS 없이 시험할 수 있다. 기본 origin은 첫 sync 전의 자리표시자다.
distribution_config() {
  local origin="${1:-example.com}" reference="kervion-$(date -u +%Y%m%dT%H%M%S)-$$"
  if [[ ! "$origin" =~ ^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$ ]]; then
    printf '%s\n' 'Origin must be a DNS hostname without scheme or path.' >&2
    return 2
  fi
  cat <<EOF
{
  "CallerReference": "$reference",
  "Comment": "kervion",
  "Enabled": true,
  "PriceClass": "PriceClass_200",
  "HttpVersion": "http2and3",
  "IsIPV6Enabled": true,
  "Aliases": {"Quantity": 0},
  "ViewerCertificate": {"CloudFrontDefaultCertificate": true},
  "Origins": {
    "Quantity": 1,
    "Items": [{
      "Id": "alb",
      "DomainName": "$origin",
      "CustomOriginConfig": {
        "HTTPPort": 80,
        "HTTPSPort": 443,
        "OriginProtocolPolicy": "http-only",
        "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
        "OriginReadTimeout": 60,
        "OriginKeepaliveTimeout": 5
      }
    }]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "alb",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 7,
      "Items": ["GET", "HEAD", "OPTIONS", "PUT", "PATCH", "POST", "DELETE"],
      "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}
    },
    "Compress": true,
    "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
    "OriginRequestPolicyId": "33f36d7e-f396-46d9-90e0-52428a34d9dc"
  },
  "Restrictions": {"GeoRestriction": {"RestrictionType": "none", "Quantity": 0}}
}
EOF
}

find_distribution() {
  local matches
  DIST_ID='' DIST_DOMAIN=''
  matches="$(aws cloudfront list-distributions --region "$AWS_REGION" \
    --query "DistributionList.Items[?Comment=='kervion'].[Id,DomainName]" --output text)" || return
  matches="${matches//$'\r'/}"
  [[ -n "$matches" && "$matches" != None ]] || return 0
  if [[ "$matches" == *$'\n'* ]]; then
    printf '%s\n' 'Multiple kervion distributions found; resolve duplicates before continuing.' >&2
    return 1
  fi
  read -r DIST_ID DIST_DOMAIN <<< "$matches"
}

main() {
  local action="${1:-}" hostname deadline etag
  case "$action" in
    create) (( $# <= 2 )) || return 2 ;;
    sync) (( $# == 1 )) || return 2 ;;
    *) printf '%s\n' 'Usage: aws-cloudfront.sh create [origin-hostname] | sync' >&2; return 2 ;;
  esac
  read_aws_env
  if [[ "$action" == sync ]]; then
    resolve_kube_context aws
    require_aws_keys DOMAIN
  fi
  find_distribution
  if [[ "$action" == create && -n "$DIST_ID" ]]; then
    printf 'DOMAIN=%s\n' "$DIST_DOMAIN"
    return
  fi
  if [[ "$action" == sync && ( -z "$DIST_ID" || "$DIST_DOMAIN" != "$DOMAIN" ) ]]; then
    printf '%s\n' 'Run create first and set DOMAIN to its CloudFront domain in aws.env.' >&2
    return 1
  fi

  CF_TMP_FILE="$(mktemp)"
  # Windows AWS CLI도 file:// 경로를 읽을 수 있게 한다.
  if command -v cygpath >/dev/null; then CF_TMP_FILE="$(cygpath -m "$CF_TMP_FILE")"; fi
  trap 'rm -f "$CF_TMP_FILE" "$CF_TMP_FILE.config"' EXIT
  if [[ "$action" == create ]]; then
    distribution_config "${2:-example.com}" > "$CF_TMP_FILE.config"
    hostname="$(aws cloudfront create-distribution --region "$AWS_REGION" \
      --distribution-config "file://$CF_TMP_FILE.config" --query Distribution.DomainName --output text)"
    printf 'DOMAIN=%s\n' "$hostname"
    return
  fi

  deadline=$((SECONDS + 600))
  while true; do
    hostname="$(kc -n kervion get ingress kervion -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')"
    hostname="${hostname%$'\r'}"
    [[ -z "$hostname" || "$hostname" == None ]] || break
    if (( SECONDS >= deadline )); then
      printf '%s\n' 'Timed out waiting for the ALB hostname; CloudFront was not changed.' >&2
      return 1
    fi
    sleep 10
  done
  aws cloudfront get-distribution-config --region "$AWS_REGION" --id "$DIST_ID" --output json > "$CF_TMP_FILE"
  # 기존 설정과 CallerReference를 보존하고 ALB origin만 바꾼다.
  etag="$(python - "$CF_TMP_FILE" "$CF_TMP_FILE.config" "$hostname" <<'PYCONFIG'
import json
import sys

with open(sys.argv[1], encoding='utf-8') as stream:
    response = json.load(stream)
config = response['DistributionConfig']
origins = [origin for origin in config['Origins']['Items'] if origin['Id'] == 'alb']
if len(origins) != 1:
    raise SystemExit('Expected exactly one alb origin; CloudFront was not changed.')
origins[0]['DomainName'] = sys.argv[3]
with open(sys.argv[2], 'w', encoding='utf-8') as stream:
    json.dump(config, stream)
print(response['ETag'])
PYCONFIG
)"
  aws cloudfront update-distribution --region "$AWS_REGION" --id "$DIST_ID" \
    --if-match "$etag" --distribution-config "file://$CF_TMP_FILE.config" --output json >/dev/null
  aws cloudfront wait distribution-deployed --region "$AWS_REGION" --id "$DIST_ID"
  printf 'DOMAIN=%s\n' "$DIST_DOMAIN"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
