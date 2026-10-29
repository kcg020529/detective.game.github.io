from pathlib import Path
import os
import json
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
K8S = ROOT / 'infrastructure/kubernetes'
BASE = K8S / 'base'
LOCAL = K8S / 'overlays/local'
AWS = K8S / 'overlays/aws'
SCRIPTS = ('build-images.sh', 'create-secret.sh', 'deploy.sh', 'teardown.sh', 'smoke.sh', 'reindex.sh',
           'render.sh', 'aws-install-lbc.sh', 'teardown-aws.sh')


def _load(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def _documents():
    for path in K8S.rglob('*.yaml'):
        for obj in yaml.safe_load_all(path.read_text(encoding='utf-8')):
            if isinstance(obj, dict):
                yield path, obj


def _containers(obj):
    pod = obj.get('spec', {}).get('template', {}).get('spec', {})
    return pod.get('initContainers', []) + pod.get('containers', [])


def test_kubernetes_manifests():
    docs = list(_documents())
    base = _load(BASE / 'kustomization.yaml')
    local = _load(LOCAL / 'kustomization.yaml')
    assert base['namespace'] == 'kervion'
    assert set(base['resources']) == {
        'namespace.yaml', 'configmap.yaml', 'mariadb.yaml', 'qdrant.yaml',
        'fastembed-cache-pvc.yaml', 'api.yaml', 'web.yaml',
        'jobs/migrate.yaml', 'jobs/load-data.yaml', 'jobs/rag-index.yaml',
    }
    assert all('secret' not in item for item in base['resources'])
    assert base['configMapGenerator'][0]['files'] == ['nginx.conf=../../docker/nginx.conf']
    assert base['configMapGenerator'][0]['options']['disableNameSuffixHash'] is True
    assert 'images' not in base
    assert local['resources'] == ['../../base']
    assert {item['name']: (item['newName'], item['newTag']) for item in local['images']} == {
        'kervion-backend': ('kervion-backend', 'k8s'), 'kervion-web': ('kervion-web', 'k8s'),
    }
    assert _load(BASE / 'configmap.yaml')['data'] == {
        'MARIADB_HOST': 'mariadb', 'MARIADB_PORT': '3306', 'MARIADB_DATABASE': 'kervion',
        'QDRANT_URL': 'http://qdrant:6333', 'FASTEMBED_CACHE_PATH': '/home/app/.cache/fastembed',
        'KERVION_COOKIE_SAMESITE': 'lax',
    }
    assert _load(LOCAL / 'configmap-patch.yaml')['data'] == {
        'KERVION_ALLOWED_ORIGINS': 'http://localhost:30080,http://127.0.0.1:30080',
        'KERVION_COOKIE_SECURE': 'false',
    }
    base_web = next(obj for path, obj in docs if path == BASE / 'web.yaml' and obj['kind'] == 'Service')
    assert base_web['spec']['type'] == 'ClusterIP'
    assert all('nodePort' not in port for port in base_web['spec']['ports'])

    for path, obj in docs:
        assert 'sk-' not in path.read_text(encoding='utf-8')
        if obj.get('kind') == 'Secret':
            assert path.name == 'secret.example.yaml'
            assert all(value in (None, '', 'CHANGE_ME') for value in obj.get('stringData', {}).values())
        if obj.get('kind') not in ('Kustomization', 'Namespace', 'StorageClass', 'ClusterConfig'):
            assert obj.get('metadata', {}).get('namespace', base['namespace']) == 'kervion'
        for key, value in obj.get('data', {}).items():
            if re.search('PASSWORD|KEY', key):
                assert not value
        for container in _containers(obj):
            image = container['image']
            if image not in ('kervion-backend', 'kervion-web'):
                assert ':' in image.rsplit('/', 1)[-1] and image.rsplit(':', 1)[-1] not in ('latest', '')
            assert '--reload' not in ' '.join(container.get('command', []) + container.get('args', []))
            assert container.get('resources', {}).get('requests') and container.get('resources', {}).get('limits')
            for env in container.get('env', []):
                if re.search('PASSWORD|KEY', env['name']):
                    assert not env.get('value')

    workloads = {obj['metadata']['name']: obj for _, obj in docs if obj.get('kind') in ('Deployment', 'StatefulSet', 'Job')}
    for name in ('api', 'mariadb', 'qdrant'):
        assert any('readinessProbe' in c for c in _containers(workloads[name]))
    security = workloads['api']['spec']['template']['spec']['securityContext']
    assert security['runAsNonRoot'] is True and security['runAsUser'] == 10001
    for name in ('migrate', 'load-data', 'rag-index'):
        job = workloads[name]
        assert job['metadata']['labels']['app.kubernetes.io/tier'] == 'job'
        assert job['spec']['backoffLimit'] == 3
        assert any(c['name'].startswith('wait-for-') for c in job['spec']['template']['spec']['initContainers'])
        assert all(c['image'] == 'kervion-backend' for c in _containers(job))

    for filename in ('secret.yaml', 'prod.secret.yaml'):
        assert subprocess.run(['git', 'check-ignore', '--quiet', f'infrastructure/kubernetes/{filename}'], cwd=ROOT).returncode == 0
    assert subprocess.run(['git', 'check-ignore', '--quiet', 'infrastructure/kubernetes/secret.example.yaml'], cwd=ROOT).returncode != 0
    for name in SCRIPTS:
        script = K8S / 'scripts' / name
        assert script.is_file()
        assert script.read_text(encoding='utf-8').splitlines()[:2] == ['#!/usr/bin/env bash', 'set -euo pipefail']
    reindex = (K8S / 'scripts/reindex.sh').read_text(encoding='utf-8')
    assert 'trap restore_api EXIT' in reindex
    assert 'kubectl scale deployment/api --namespace kervion --replicas=1' in reindex


def test_nginx_preserves_forwarded_protocol():
    conf = (ROOT / 'infrastructure/docker/nginx.conf').read_text(encoding='utf-8')
    assert re.search(r'map\s+\$http_x_forwarded_proto\s+\$kervion_forwarded_proto\s*\{\s*default\s+\$http_x_forwarded_proto;\s*""\s+\$scheme;\s*\}', conf)
    assert 'proxy_set_header X-Forwarded-Proto $kervion_forwarded_proto;' in conf


def test_rendered_local_images_tiers_and_client_dry_run():
    kubectl = shutil.which('kubectl')
    if not kubectl:
        pytest.skip('kubectl is not installed')
    rendered = subprocess.run([kubectl, 'kustomize', '--load-restrictor', 'LoadRestrictionsNone', str(LOCAL)],
                              cwd=ROOT, text=True, encoding='utf-8', capture_output=True)
    assert rendered.returncode == 0, rendered.stderr
    objects = list(yaml.safe_load_all(rendered.stdout))
    allowed_images = {'kervion-backend:k8s', 'kervion-web:k8s', 'mariadb:11.4.13', 'qdrant/qdrant:v1.19.2'}
    for obj in objects:
        if obj['kind'] != 'Namespace':
            assert obj['metadata']['namespace'] == 'kervion'
        for container in _containers(obj):
            assert container['image'] in allowed_images
    jobs = [obj for obj in objects if obj['kind'] == 'Job']
    assert {job['metadata']['name'] for job in jobs} == {'migrate', 'load-data', 'rag-index'}
    assert all(c['image'] == 'kervion-backend:k8s' for job in jobs for c in _containers(job))
    service = next(obj for obj in objects if obj['kind'] == 'Service' and obj['metadata']['name'] == 'web')
    assert service['spec']['type'] == 'NodePort' and service['spec']['ports'][0]['nodePort'] == 30080
    config = next(obj for obj in objects if obj['kind'] == 'ConfigMap' and obj['metadata']['name'] == 'kervion-config')
    assert config['data']['KERVION_ALLOWED_ORIGINS'] == 'http://localhost:30080,http://127.0.0.1:30080'
    assert config['data']['KERVION_COOKIE_SECURE'] == 'false'
    deploy = (K8S / 'scripts/deploy.sh').read_text(encoding='utf-8')
    assert "apply_layer 'app.kubernetes.io/tier in (shared,data)'" in deploy
    assert "apply_layer 'app.kubernetes.io/tier=app'" in deploy
    assert 'apply_layer "app.kubernetes.io/name=$name"' in deploy
    for tiers in ({'shared', 'data'}, {'app'}):
        selected = [obj for obj in objects if obj['metadata'].get('labels', {}).get('app.kubernetes.io/tier') in tiers]
        assert selected and not any(obj['kind'] == 'Job' for obj in selected)
    # client dry-run도 API 서버를 조회하므로 오프라인 실행에서는 생략한다.
    if os.getenv('KERVION_OFFLINE_TESTS') == '1':
        return
    for selector in (None, 'app.kubernetes.io/tier in (shared,data)', 'app.kubernetes.io/tier=app'):
        command = [kubectl, 'apply', '--dry-run=client', '-f', '-']
        if selector:
            command.append('--selector=' + selector)
        result = subprocess.run(command, cwd=ROOT, input=rendered.stdout, text=True, encoding='utf-8', capture_output=True)
        assert result.returncode == 0, result.stderr
        if selector:
            assert 'job.batch/' not in result.stdout


@pytest.fixture
def bash():
    git_bash = Path('C:/Program Files/Git/bin/bash.exe')
    executable = str(git_bash) if git_bash.is_file() else shutil.which('bash')
    if not executable:
        pytest.skip('Bash is not installed')
    return executable


def test_script_syntax(bash):
    for name in SCRIPTS:
        result = subprocess.run([bash, '-n', (K8S / 'scripts' / name).as_posix()], cwd=ROOT, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def _mock_script(bash, tmp_path, name, *, fail_at='', overlay=None):
    log = tmp_path / 'kubectl.log'
    env = dict(os.environ, R20_LOG=log.as_posix(), FAIL_AT=fail_at)
    command = r'''
kubectl() {
  printf '%s\n' "$*" >> "$R20_LOG"
  if [[ "$1" == kustomize ]]; then
    printf 'rendered-overlay\n'
  elif [[ "$1" == apply ]]; then
    cat >/dev/null
    [[ "$FAIL_AT" != apply ]]
  elif [[ "$1" == wait && "$*" == *condition=complete* ]]; then
    [[ "$FAIL_AT" != wait ]]
  fi
}
script="$1"
shift
source "$script" "$@"
'''
    args = [bash, '-c', command, 'bash', (K8S / 'scripts' / name).as_posix()]
    if overlay:
        args.append(overlay)
    result = subprocess.run(args, cwd=ROOT, env=env, text=True, encoding='utf-8', capture_output=True)
    return result, log.read_text(encoding='utf-8').splitlines() if log.exists() else []


@pytest.mark.parametrize('fail_at', ['', 'wait', 'apply'])
def test_reindex_restores_api_after_success_and_failure(bash, tmp_path, fail_at):
    result, calls = _mock_script(bash, tmp_path, 'reindex.sh', fail_at=fail_at)
    assert result.returncode == (1 if fail_at else 0), result.stderr
    assert calls[1] == 'scale deployment/api --namespace kervion --replicas=0'
    assert 'wait --for=delete pod --namespace kervion --selector=app.kubernetes.io/name=api --timeout=300s' in calls
    assert any(call.startswith('kustomize ') and call.endswith('/overlays/local') for call in calls)
    assert calls[-2:] == ['scale deployment/api --namespace kervion --replicas=1',
                         'rollout status deployment/api --namespace kervion --timeout=600s']
    if fail_at == 'wait':
        assert 'logs job/rag-index --namespace kervion --all-containers=true --tail=50' in calls


@pytest.mark.parametrize('name', ['deploy.sh', 'reindex.sh'])
def test_invalid_overlay_stops_before_kubectl(bash, tmp_path, name):
    result, calls = _mock_script(bash, tmp_path, name, overlay='missing-overlay')
    assert result.returncode == 2 and not calls
    assert 'Overlay not found' in result.stderr


@pytest.mark.parametrize('fail_at', ['', 'wait'])
def test_deploy_orders_selected_jobs_and_aborts_before_app_on_failure(bash, tmp_path, fail_at):
    result, calls = _mock_script(bash, tmp_path, 'deploy.sh', fail_at=fail_at)
    assert result.returncode == (1 if fail_at else 0), result.stderr
    selectors = [call.split('--selector=', 1)[1] for call in calls if call.startswith('apply ')]
    expected = ['app.kubernetes.io/name=namespace', 'app.kubernetes.io/tier in (shared,data)',
                'app.kubernetes.io/name=migrate']
    if not fail_at:
        expected += ['app.kubernetes.io/name=load-data', 'app.kubernetes.io/name=rag-index', 'app.kubernetes.io/tier=app']
    assert selectors == expected
    if fail_at:
        assert 'logs job/migrate --namespace kervion --all-containers=true --tail=50' in calls
    else:
        for current, following in [('migrate', 'load-data'), ('load-data', 'rag-index')]:
            assert calls.index(f'wait --for=condition=complete job/{current} --namespace kervion --timeout=1200s') < calls.index(f'delete job {following} --namespace kervion --ignore-not-found=true --wait=true')


def _aws_env(tmp_path, **updates):
    values = dict(AWS_REGION='ap-northeast-2', CLUSTER_NAME='kervion',
                  ECR_REGISTRY='registry.example.invalid', DOMAIN='app.example.invalid',
                  CERT_ARN='arn:aws:acm:ap-northeast-2:000000000000:certificate/demo')
    values.update(updates)
    path = tmp_path / 'aws.env'
    path.write_text(''.join(f'{key}={value}\n' for key, value in values.items()), encoding='utf-8')
    return path


def test_aws_overlay_and_shared_render(bash, tmp_path):
    kubectl = shutil.which('kubectl')
    if not kubectl:
        pytest.skip('kubectl is not installed')
    raw = subprocess.run([kubectl, 'kustomize', '--load-restrictor', 'LoadRestrictionsNone', str(AWS)],
                         cwd=ROOT, text=True, encoding='utf-8', capture_output=True)
    assert raw.returncode == 0, raw.stderr
    assert '__ECR_REGISTRY__' in raw.stdout
    result = subprocess.run([bash, (K8S / 'scripts/render.sh').as_posix(), 'aws', 'abcdef0', _aws_env(tmp_path).as_posix()],
                            cwd=ROOT, text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr
    assert not re.search(r'__[A-Z_]+__', result.stdout)
    assert 'registry.example.invalid' not in result.stderr and 'arn:' not in result.stderr
    objects = list(yaml.safe_load_all(result.stdout))
    allowed = {'registry.example.invalid/kervion-backend:abcdef0', 'registry.example.invalid/kervion-web:abcdef0',
               'mariadb:11.4.13', 'qdrant/qdrant:v1.19.2'}
    for obj in objects:
        if obj['kind'] not in ('Namespace', 'StorageClass'):
            assert obj['metadata']['namespace'] == 'kervion'
        assert all(c['image'] in allowed for c in _containers(obj))
    jobs = [obj for obj in objects if obj['kind'] == 'Job']
    assert len(jobs) == 3 and all(c['image'] == 'registry.example.invalid/kervion-backend:abcdef0'
                                  for job in jobs for c in _containers(job))
    ingress = next(obj for obj in objects if obj['kind'] == 'Ingress')
    assert ingress['metadata']['labels']['app.kubernetes.io/tier'] == 'edge'
    assert ingress['spec']['ingressClassName'] == 'alb'
    assert ingress['spec']['rules'][0]['host'] == 'app.example.invalid'
    assert ingress['spec']['rules'][0]['http']['paths'][0]['backend']['service'] == {'name': 'web', 'port': {'number': 80}}
    annotations = ingress['metadata']['annotations']
    assert json.loads(annotations['alb.ingress.kubernetes.io/listen-ports']) == [{'HTTP': 80}, {'HTTPS': 443}]
    assert annotations['alb.ingress.kubernetes.io/ssl-redirect'] == '443'
    assert annotations['alb.ingress.kubernetes.io/certificate-arn'].endswith('/demo')
    assert annotations['alb.ingress.kubernetes.io/scheme'] == 'internet-facing'
    assert annotations['alb.ingress.kubernetes.io/target-type'] == 'ip'
    assert annotations['alb.ingress.kubernetes.io/healthcheck-path'] == '/'
    storage = next(obj for obj in objects if obj['kind'] == 'StorageClass')
    assert storage['provisioner'] == 'ebs.csi.aws.com'
    assert storage['parameters'] == {'type': 'gp3', 'encrypted': 'true'}
    assert storage['volumeBindingMode'] == 'WaitForFirstConsumer' and storage['reclaimPolicy'] == 'Delete'
    assert storage['allowVolumeExpansion'] is True
    assert storage['metadata']['annotations']['storageclass.kubernetes.io/is-default-class'] == 'true'
    config = next(obj for obj in objects if obj['kind'] == 'ConfigMap' and obj['metadata']['name'] == 'kervion-config')
    assert config['data']['KERVION_COOKIE_SECURE'] == 'true'
    assert config['data']['KERVION_COOKIE_SAMESITE'] == 'lax'
    assert config['data']['KERVION_ALLOWED_ORIGINS'] == 'https://app.example.invalid'
    service = next(obj for obj in objects if obj['kind'] == 'Service' and obj['metadata']['name'] == 'web')
    assert service['spec']['type'] == 'ClusterIP'
    for obj in objects:
        claims = ([obj] if obj['kind'] == 'PersistentVolumeClaim' else obj.get('spec', {}).get('volumeClaimTemplates', []))
        assert all('storageClassName' not in claim['spec'] for claim in claims)


@pytest.mark.parametrize('tag,updates', [('', {}), ('latest', {}), ('bad-tag', {}), ('abcdef0', {'DOMAIN': ''})])
def test_aws_render_rejects_invalid_settings(bash, tmp_path, tag, updates):
    result = subprocess.run([bash, (K8S / 'scripts/render.sh').as_posix(), 'aws', tag, _aws_env(tmp_path, **updates).as_posix()],
                            cwd=ROOT, text=True, encoding='utf-8', capture_output=True)
    assert result.returncode != 0 and not result.stdout


def test_aws_render_rejects_leftover_placeholders(bash, tmp_path):
    command = r'''
kubectl() { printf 'data: __UNRESOLVED__\n'; }
source "$1"
render_overlay aws abcdef0 "$2"
'''
    result = subprocess.run([bash, '-c', command, 'bash', (K8S / 'scripts/render.sh').as_posix(), _aws_env(tmp_path).as_posix()],
                            cwd=ROOT, text=True, encoding='utf-8', capture_output=True)
    assert result.returncode != 0 and not result.stdout
    assert 'Unresolved placeholder' in result.stderr


def test_cluster_config_and_gitignore():
    cluster = _load(K8S / 'aws/cluster.yaml')
    assert cluster['apiVersion'] == 'eksctl.io/v1alpha5' and cluster['kind'] == 'ClusterConfig'
    assert cluster['metadata'] == {'name': 'kervion', 'region': 'ap-northeast-2', 'version': '1.36'}
    assert cluster['availabilityZones'] == ['ap-northeast-2a', 'ap-northeast-2c']
    assert cluster['vpc']['nat']['gateway'] == 'Disable'
    assert cluster['addonsConfig']['autoApplyPodIdentityAssociations'] is True
    addons = {item['name']: item for item in cluster['addons']}
    assert set(addons) == {'vpc-cni', 'coredns', 'kube-proxy', 'eks-pod-identity-agent', 'aws-ebs-csi-driver'}
    assert addons['aws-ebs-csi-driver']['useDefaultPodIdentityAssociations'] is True
    assert cluster['iam']['podIdentityAssociations'] == [dict(namespace='kube-system', serviceAccountName='aws-load-balancer-controller',
                                                          createServiceAccount=True, wellKnownPolicies={'awsLoadBalancerController': True})]
    assert len(cluster['managedNodeGroups']) == 1
    node = cluster['managedNodeGroups'][0]
    assert node['name'] == 'ng-demo' and node['instanceType'] == 't3.large'
    assert node['minSize'] == node['desiredCapacity'] == node['maxSize'] == 1
    assert node['availabilityZones'] == ['ap-northeast-2a'] and node['privateNetworking'] is False
    assert node['volumeSize'] == 20 and node['volumeType'] == 'gp3' and node['disableIMDSv1'] is True
    for path in ('aws/aws.env', 'aws/.env.aws', 'anything.secret.yaml'):
        assert subprocess.run(['git', 'check-ignore', '--quiet', f'infrastructure/kubernetes/{path}'], cwd=ROOT).returncode == 0
    assert subprocess.run(['git', 'check-ignore', '--quiet', 'infrastructure/kubernetes/aws/aws.env.example'], cwd=ROOT).returncode != 0


def test_infrastructure_has_no_committable_identifiers_or_keys():
    names = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '--', 'infrastructure/'], cwd=ROOT, text=True, encoding='utf-8')
    for name in names.splitlines():
        path = ROOT / name
        if path.is_file():
            text = path.read_text(encoding='utf-8')
            assert not re.search(r'\b[0-9]{12}\b', text), name
            assert 'arn:aws:acm' not in text and 'sk-' not in text, name


def test_ci_builds_and_tests_without_publishing():
    path = ROOT / '.github/workflows/ci.yml'
    text = path.read_text(encoding='utf-8')
    workflow = _load(path)
    triggers = workflow.get('on', workflow.get(True))
    assert 'pull_request' in triggers and triggers['push']['branches'] == ['main']
    assert workflow['permissions'] == {'contents': 'read'}
    assert workflow['concurrency']['cancel-in-progress'] is True
    assert '${{ github.ref }}' in workflow['concurrency']['group']
    assert set(workflow['jobs']) == {'test', 'images'}
    assert all(job['runs-on'] == 'ubuntu-latest' for job in workflow['jobs'].values())
    test_steps = workflow['jobs']['test']['steps']
    assert test_steps[0]['uses'] == 'actions/checkout@v4'
    assert test_steps[1]['uses'] == 'actions/setup-python@v5' and test_steps[1]['with']['python-version'] == '3.12'
    assert 'python -m pytest tests -q -p no:cacheprovider' in text
    assert 'GITHUB_SHA::7' in text and 'Dockerfile.backend' in text and 'Dockerfile.web' in text
    assert not any(forbidden in text for forbidden in ('docker push', 'docker login', 'secrets.'))


def _mock_aws_script(bash, tmp_path, name, args=(), *, mode='', input_text=''):
    log = tmp_path / 'aws-commands.log'
    env = dict(os.environ, R21_LOG=log.as_posix(), R21_MODE=mode,
               KERVION_AWS_ENV_FILE=_aws_env(tmp_path).as_posix())
    command = r'''
aws() {
  printf 'aws %s\n' "$*" >> "$R21_LOG"
  case "$1 $2" in
    'eks describe-cluster')
      if [[ "$*" == *vpcId* ]]; then printf 'mock-eks-context\tvpc-demo\n'; else printf 'mock-eks-context\n'; fi ;;
    'elbv2 describe-load-balancers')
      if [[ ! -f "$R21_LOG.lb" ]]; then touch "$R21_LOG.lb"; printf 'mock-load-balancer\n'; fi ;;
    'elbv2 describe-tags') printf '1\n' ;;
    *) printf '[]\n' ;;
  esac
}
kubectl() {
  printf 'kubectl %s\n' "$*" >> "$R21_LOG"
  if [[ "$1" == kustomize ]]; then
    printf 'image: __ECR_REGISTRY__/kervion-backend:__IMAGE_TAG__\n'
  elif [[ "$1" == apply ]]; then
    cat >> "$R21_LOG.payload"
  fi
}
helm() { printf 'helm %s\n' "$*" >> "$R21_LOG"; }
eksctl() { printf 'eksctl %s\n' "$*" >> "$R21_LOG"; }
sleep() { printf 'sleep %s\n' "$*" >> "$R21_LOG"; [[ "$R21_MODE" != alb-failure ]]; }
script="$1"
shift
source "$script" "$@"
'''
    result = subprocess.run([bash, '-c', command, 'bash', (K8S / 'scripts' / name).as_posix(), *args],
                            cwd=ROOT, env=env, input=input_text, text=True, encoding='utf-8', capture_output=True)
    return result, log.read_text(encoding='utf-8').splitlines() if log.exists() else []


def test_aws_deploy_applies_edge_last_and_reuses_substituted_manifest(bash, tmp_path):
    result, calls = _mock_aws_script(bash, tmp_path, 'deploy.sh', ('aws', 'abcdef0'))
    assert result.returncode == 0, result.stderr
    assert sum(call.startswith('kubectl kustomize') for call in calls) == 1
    assert calls[-1] == 'kubectl apply -f - --selector=app.kubernetes.io/tier=edge'
    assert calls[-2] == 'kubectl rollout status deployment/web --namespace kervion --timeout=300s'
    payload = (tmp_path / 'aws-commands.log.payload').read_text(encoding='utf-8')
    assert '__' not in payload and 'registry.example.invalid/kervion-backend:abcdef0' in payload


def test_lbc_installer_pins_chart_and_uses_eks_context(bash, tmp_path):
    result, calls = _mock_aws_script(bash, tmp_path, 'aws-install-lbc.sh')
    assert result.returncode == 0, result.stderr
    install = next(call for call in calls if call.startswith('helm upgrade'))
    assert '--version 3.6.2' in install and '--set serviceAccount.create=false' in install
    assert '--set vpcId=vpc-demo' in install and '--set region=ap-northeast-2' in install
    assert '--kube-context mock-eks-context' in install
    assert calls[-1].startswith('kubectl --context mock-eks-context rollout status')


@pytest.mark.parametrize('mode', ['', 'alb-failure'])
def test_teardown_aws_orders_deletion_and_retains_cluster_on_alb_failure(bash, tmp_path, mode):
    result, calls = _mock_aws_script(bash, tmp_path, 'teardown-aws.sh', ('--yes',), mode=mode)
    assert result.returncode == (1 if mode else 0), result.stderr
    assert 'WARNING' in result.stderr
    ingress = next(i for i, call in enumerate(calls) if 'delete ingress' in call)
    tags = next(i for i, call in enumerate(calls) if call.startswith('aws elbv2 describe-tags'))
    assert ingress < tags
    assert 'elbv2.k8s.aws/cluster' in calls[tags]
    if mode:
        assert not any('delete namespace' in call or 'eksctl delete' in call for call in calls)
    else:
        namespace = next(i for i, call in enumerate(calls) if 'delete namespace' in call)
        helm = next(i for i, call in enumerate(calls) if call.startswith('helm uninstall'))
        cluster = next(i for i, call in enumerate(calls) if call.startswith('eksctl delete'))
        assert tags < namespace < helm < cluster
        assert any(call.startswith('aws ec2 describe-volumes') for call in calls[cluster:])
        assert any(call.startswith('aws ec2 describe-security-groups') for call in calls[cluster:])
        assert any(call.startswith('aws ec2 describe-addresses') for call in calls[cluster:])
        assert any(call.startswith('aws cloudformation describe-stacks') for call in calls[cluster:])
        assert all('--context mock-eks-context' in call for call in calls if call.startswith('kubectl '))


def test_teardown_aws_requires_confirmation_before_any_external_call(bash, tmp_path):
    result, calls = _mock_aws_script(bash, tmp_path, 'teardown-aws.sh', input_text='wrong-cluster\n')
    assert result.returncode != 0 and not calls
    text = (K8S / 'scripts/teardown-aws.sh').read_text(encoding='utf-8')
    assert 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-dump' in text
    assert 'worklog/backups' in text and 'umask 077' in text


def test_app_rollout_drains_before_shutdown():
    # K04-b 실측: preStop 없이 교체하면 1,661건 중 6건이 502·시간 초과였다.
    for name in ('api', 'web'):
        deploy = next(obj for obj in yaml.safe_load_all((BASE / f'{name}.yaml').read_text(encoding='utf-8')) if obj and obj.get('kind') == 'Deployment')
        rolling = deploy['spec']['strategy']['rollingUpdate']
        assert rolling == {'maxSurge': 1, 'maxUnavailable': 0}
        container = deploy['spec']['template']['spec']['containers'][0]
        assert container['lifecycle']['preStop']['exec']['command'] == ['sleep', '10']


def test_teardown_deletes_every_statefulset_claim():
    claims = {'pvc/fastembed-cache'}
    for name in ('mariadb', 'qdrant'):
        sts = next(obj for obj in yaml.safe_load_all((BASE / f'{name}.yaml').read_text(encoding='utf-8')) if obj and obj.get('kind') == 'StatefulSet')
        claims |= {f"pvc/{t['metadata']['name']}-{name}-0" for t in sts['spec']['volumeClaimTemplates']}
    script = (K8S / 'scripts/teardown.sh').read_text(encoding='utf-8')
    assert claims <= set(re.findall(r'pvc/[\w-]+', script))
