import json
import os
import re
import subprocess

import pytest

from test_kubernetes_manifests import ROOT, K8S, _aws_env, bash


SCRIPT = K8S / 'scripts/aws-cloudfront.sh'
DOMAIN = 'd111111abcdef8.cloudfront.net'


def _config(bash, origin='example.com'):
    result = subprocess.run([bash, '-c', 'source "$1"; distribution_config "$2"',
                             'bash', SCRIPT.as_posix(), origin], cwd=ROOT,
                            text=True, encoding='utf-8', capture_output=True)
    return result


def test_distribution_config_without_aws(bash):
    result = _config(bash)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    assert config['Enabled'] and config['Comment'] == 'kervion'
    assert config['PriceClass'] == 'PriceClass_200'
    assert config['HttpVersion'] == 'http2and3' and config['IsIPV6Enabled']
    assert config['ViewerCertificate'] == {'CloudFrontDefaultCertificate': True}
    assert config['Aliases'] == {'Quantity': 0}
    assert config['Origins']['Quantity'] == 1
    origin = config['Origins']['Items'][0]
    assert origin['Id'] == 'alb' and origin['DomainName'] == 'example.com'
    custom = origin['CustomOriginConfig']
    assert custom['OriginProtocolPolicy'] == 'http-only' and custom['HTTPPort'] == 80
    assert custom['OriginReadTimeout'] == 60 and custom['OriginKeepaliveTimeout'] == 5
    behavior = config['DefaultCacheBehavior']
    assert behavior['TargetOriginId'] == 'alb' and behavior['Compress']
    assert behavior['ViewerProtocolPolicy'] == 'redirect-to-https'
    assert behavior['CachePolicyId'] == '4135ea2d-6df8-44a3-9df3-4b5a84be39ad'
    assert behavior['OriginRequestPolicyId'] == '33f36d7e-f396-46d9-90e0-52428a34d9dc'
    methods = behavior['AllowedMethods']
    assert methods['Quantity'] == 7 and set(methods['Items']) == {'GET', 'HEAD', 'OPTIONS', 'PUT', 'PATCH', 'POST', 'DELETE'}
    assert methods['CachedMethods'] == {'Quantity': 2, 'Items': ['GET', 'HEAD']}


@pytest.mark.parametrize('origin', ['alb.example.net', 'https://example.com', 'bad"host.example', 'bad\nhost.example'])
def test_distribution_origin_validation(bash, origin):
    result = _config(bash, origin)
    assert result.returncode == (0 if origin == 'alb.example.net' else 2)
    if result.returncode:
        assert not result.stdout


def _run(bash, tmp_path, action, mode='', domain=DOMAIN):
    log = tmp_path / 'calls.log'
    current = tmp_path / 'current.json'
    current.write_text(json.dumps({'ETag': 'etag-123', 'DistributionConfig': {
        'CallerReference': 'keep-reference', 'Comment': 'kervion', 'Enabled': True,
        'DefaultRootObject': 'keep-root',
        'Origins': {'Quantity': 1, 'Items': [{'Id': 'alb', 'DomainName': 'old.example.com',
                                          'CustomOriginConfig': {'OriginProtocolPolicy': 'http-only'}}]},
    }}), encoding='utf-8')
    env = dict(os.environ, KERVION_AWS_ENV_FILE=_aws_env(tmp_path, DOMAIN=domain).as_posix(),
               R24_LOG=log.as_posix(), R24_CURRENT=current.as_posix(), R24_MODE=mode, AWS_PROFILE='offline-profile')
    command = r"""
aws() {
  printf 'aws %s profile=%s\n' "$*" "$AWS_PROFILE" >> "$R24_LOG"
  case "$1 $2" in
    'cloudfront list-distributions')
      [[ "$R24_MODE" != new ]] || return 0
      printf 'EDIST1\td111111abcdef8.cloudfront.net\n'
      if [[ "$R24_MODE" == duplicate ]]; then printf 'EDIST2\td222222.cloudfront.net\n'; fi ;;
    'cloudfront get-distribution-config') cat "$R24_CURRENT" ;;
    'cloudfront create-distribution'|'cloudfront update-distribution')
      local arg
      for arg in "$@"; do
        if [[ "$arg" == file://* ]]; then cat "${arg#file://}" > "$R24_LOG.payload"; fi
      done
      [[ "$R24_MODE" != update-failure ]] || return 1
      printf 'd111111abcdef8.cloudfront.net\n' ;;
    'cloudfront wait') ;;
    *) return 97 ;;
  esac
}
kubectl() {
  printf 'kubectl %s\n' "$*" >> "$R24_LOG"
  [[ "$1 $2" == '--context mock-eks-context' ]] || return 96
  if [[ "$3" == config ]]; then
    printf 'mock-eks-context\n'
  elif [[ "$R24_MODE" != timeout && -f "$R24_LOG.polled" ]]; then
    printf 'new-alb.ap-northeast-2.elb.amazonaws.com\n'
  else
    touch "$R24_LOG.polled"
  fi
}
sleep() { if [[ "$R24_MODE" == timeout ]]; then SECONDS=$((SECONDS + 601)); fi; }
source "$1"
main "$2"
"""
    result = subprocess.run([bash, '-c', command, 'bash', SCRIPT.as_posix(), action], cwd=ROOT,
                            env=env, text=True, encoding='utf-8', capture_output=True)
    calls = log.read_text(encoding='utf-8').splitlines() if log.exists() else []
    payload_path = tmp_path / 'calls.log.payload'
    payload = json.loads(payload_path.read_text(encoding='utf-8')) if payload_path.exists() else None
    return result, calls, payload


def test_create_reuses_distribution_without_update(bash, tmp_path):
    result, calls, payload = _run(bash, tmp_path, 'create')
    assert result.returncode == 0, result.stderr
    assert result.stdout == f'DOMAIN={DOMAIN}\n'
    assert len(calls) == 1 and 'list-distributions' in calls[0]
    assert 'profile=offline-profile' in calls[0] and '--profile' not in calls[0]
    assert payload is None


def test_create_new_distribution(bash, tmp_path):
    result, calls, payload = _run(bash, tmp_path, 'create', mode='new')
    assert result.returncode == 0, result.stderr
    assert result.stdout == f'DOMAIN={DOMAIN}\n'
    assert payload['Origins']['Items'][0]['DomainName'] == 'example.com'
    assert any('create-distribution' in call for call in calls)


def test_sync_waits_for_alb_preserves_config_and_uses_etag(bash, tmp_path):
    result, calls, payload = _run(bash, tmp_path, 'sync')
    assert result.returncode == 0, result.stderr
    ingress = [call for call in calls if 'get ingress' in call]
    assert len(ingress) == 2 and all('--context mock-eks-context' in call for call in ingress)
    assert payload['Origins']['Items'][0]['DomainName'] == 'new-alb.ap-northeast-2.elb.amazonaws.com'
    assert payload['CallerReference'] == 'keep-reference' and payload['DefaultRootObject'] == 'keep-root'
    assert '--if-match etag-123' in next(call for call in calls if 'update-distribution' in call)
    assert 'wait distribution-deployed' in calls[-1]


@pytest.mark.parametrize('mode,domain', [('timeout', DOMAIN), ('duplicate', DOMAIN), ('', 'dwrong.cloudfront.net'),
                                        ('update-failure', DOMAIN)])
def test_sync_failure_paths_do_not_continue(bash, tmp_path, mode, domain):
    result, calls, _ = _run(bash, tmp_path, 'sync', mode, domain)
    assert result.returncode != 0
    assert not any('wait distribution-deployed' in call for call in calls)
    if mode != 'update-failure':
        assert not any('update-distribution' in call for call in calls)


@pytest.mark.parametrize('address,expected', [('198.51.100.10:46532', '198.51.100.10'),
    ('198.51.100.10:50000', '198.51.100.10'), ('[2600:9000:a518:2d8c::1]:8080', '2600:9000:a518:2d8c::1'),
    ('2001:db8::1:46532', '2001:db8::1'), ('[::ffff:192.0.2.1]:1234', '::ffff:192.0.2.1')])
def test_nginx_cloudfront_address_strips_port(address, expected):
    conf = (ROOT / 'infrastructure/docker/nginx.conf').read_text(encoding='utf-8')
    for target, fallback in [('kervion_viewer_ip', '$remote_addr'), ('kervion_client_key', '$binary_remote_addr')]:
        block = re.search(r'map \$http_cloudfront_viewer_address \$' + target + r' \{([^}]+)\}', conf).group(1)
        assert f'default {fallback};' in block
        matches = [re.fullmatch(pattern[1:], address) for pattern in re.findall(r'"(~[^"\n]+)" \$1;', block)]
        assert next(match.group(1) for match in matches if match) == expected
    assert 'POST $kervion_client_key;' in conf
    assert 'proxy_set_header X-Real-IP $kervion_viewer_ip;' in conf
    assert 'map $http_cloudfront_forwarded_proto $kervion_forwarded_proto' in conf
    assert '"" $kervion_origin_proto;' in conf


def test_cloudfront_docs_teardown_and_no_old_setting():
    tracked = subprocess.check_output(['git', 'ls-files', 'infrastructure'], cwd=ROOT, text=True).splitlines()
    assert all(b'CERT_ARN' not in (ROOT / name).read_bytes() for name in tracked)
    teardown = (K8S / 'scripts/teardown-aws.sh').read_text(encoding='utf-8')
    assert 'CloudFront remains' in teardown and 'disable' in teardown
    assert 'aws cloudfront ' not in teardown
    readme = (K8S / 'aws/README.md').read_text(encoding='utf-8')
    assert 'aws-cloudfront.sh create' in readme and 'aws-cloudfront.sh sync' in readme
    assert '60초' in readme and '504' in readme
    assert 'CERT_ARN' not in (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
