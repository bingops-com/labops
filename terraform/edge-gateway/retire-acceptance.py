#!/usr/bin/env python3
"""Retire only the dated, suspended acceptance gateway using its existing state.

Plans, state, kubeconfig and diagnostics stay under ignored private storage.
The ordinary production worker's retained-resource guards are not changed.
"""
import argparse
import base64
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.runtime/gaas-test-retire-20261124'
MODULE = WORK / 'terraform/edge-gateway'
SOURCE = 'f03dc668b3f092e570b8168af07e0b234b8015fc'
NAME = 'gaas-test-edge-20261122'
STATE_NS = 'gaas-state'
SUFFIX = 'gaas-test-20261122-edge'
SECRET = 'tfstate-default-' + SUFFIX
ZONE = 'd1788a49b58af8280cb8c11514f23429'
DNS = 'pz-gaas-20261122.bingops.com'
SCOPE = {
    'cloudflare_record.public_services["pz-gaas-20261122"]':
        {'id': 'd591ad5ab779aea5770fd9eeccdd4eeb', 'name': 'pz-gaas-20261122',
         'content': '91.98.196.54', 'zone_id': ZONE},
    'hcloud_firewall.edge_gateway': {'id': '12132632', 'name': NAME + '-firewall'},
    'hcloud_primary_ip.edge_gateway': {'id': '164378290', 'name': NAME + '-ipv4', 'ip_address': '91.98.196.54'},
    'hcloud_ssh_key.operator': {'id': '132947769', 'name': NAME + '-operator'},
    'terraform_data.bootstrap_revision': {'id': 'c5627771-2c1d-2e94-fc7e-1eb9263ab6fc'},
}


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError('Command failed; private diagnostics withheld')
    return result.stdout


def kube(*args):
    return run(['kubectl', '--context', 'labprod', *args], text=True)


def obj(namespace, kind, name):
    return json.loads(kube('-n', namespace, 'get', kind, name, '-o', 'json'))


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True))
    temporary.replace(path)


def identity(address, attributes):
    if address not in SCOPE or not isinstance(attributes, dict):
        raise ValueError('Unrelated resource in retirement scope')
    if any(str(attributes.get(key)) != expected for key, expected in SCOPE[address].items()):
        raise ValueError('Resource identity differs from the dated test stack')


def managed(state):
    if not state.get('lineage') or not isinstance(state.get('serial'), int):
        raise ValueError('Invalid retained test backend')
    result = {}
    for resource in state.get('resources', []):
        if resource.get('mode') != 'managed':
            continue
        if resource.get('module'):
            raise ValueError('Unexpected child module')
        for instance in resource.get('instances', []):
            address = resource['type'] + '.' + resource['name']
            if 'index_key' in instance:
                address += '[' + json.dumps(instance['index_key']) + ']'
            identity(address, instance['attributes'])
            if address in result:
                raise ValueError('Duplicate resource identity')
            result[address] = instance['attributes']
    return result


def safe_plan(plan):
    result = []
    for resource in plan.get('resource_changes', []):
        if resource.get('mode') == 'data':
            continue
        change, address = resource['change'], resource['address']
        if change['actions'] != ['delete'] or change.get('after') is not None:
            raise ValueError('Retirement permits only exact test-resource deletions')
        identity(address, change.get('before'))
        result.append({'address': address, 'actions': ['delete'], **SCOPE[address]})
    return result


def backend():
    value = obj(STATE_NS, 'secret', SECRET)
    state = json.loads(gzip.decompress(base64.b64decode(value['data']['tfstate'])))
    managed(state)
    return value, state


def preflight():
    cfg = json.loads(obj('pz-server', 'configmap', 'gaas-gateway')['data']['config.json'])
    if (cfg['name'], cfg['stateNamespace'], cfg['stateSuffix'], cfg['expectedName'], cfg['sourceRevision']) != (
            'shared-test', STATE_NS, SUFFIX, NAME, SOURCE) or cfg.get('approved') is not False:
        raise ValueError('Test cloud execution must be disabled in the expected configuration')
    deployment = obj('pz-server', 'deployment', 'gaas-acceptance-controller')
    if deployment['spec']['replicas'] != 0:
        raise ValueError('Test controller must be stopped')
    pods = json.loads(kube('-n', 'pz-server', 'get', 'pods', '-l',
                           'app.kubernetes.io/name=gaas-acceptance-controller', '-o', 'json'))['items']
    if pods:
        raise ValueError('Wait for the stopped test controller Pod to disappear')
    app = obj('argocd-system', 'application', 'gaas-acceptance')
    if app['spec']['source']['targetRevision'] != 'master' or app['spec'].get('syncPolicy', {}).get('automated') is not None:
        raise ValueError('Acceptance GitOps must follow the retired main configuration without auto-sync')
    rooms = json.loads(kube('-n', 'pz-server', 'get', 'gamerooms', '-o', 'json'))['items']
    rooms = [r for r in rooms if r['spec'].get('gatewayRef') == 'shared-test']
    if {r['metadata']['name'] for r in rooms} != {'gaas-pz-one', 'gaas-pz-two'}:
        raise ValueError('Unexpected test consumer inventory')
    for room in rooms:
        m, s, status = room['metadata'], room['spec'], room.get('status', {})
        if s['state'] != 'Suspended' or status.get('phase') != 'Suspended' or status.get('observedGeneration') != m['generation']:
            raise ValueError('A test consumer is not safely suspended')
        if status.get('worldReady') or status.get('everStarted'):
            request = hashlib.sha256(f"{m['uid']}:{m['generation']}:suspend".encode()).hexdigest()[:24]
            receipt = status.get('backup', {})
            if receipt.get('requestId') != request or not receipt.get('verified') or not receipt.get('snapshot'):
                raise ValueError('A current verified test-world backup is required')
    state = json.loads(obj('pz-server', 'configmap', 'gaas-gateway-state-shared-test')['data']['state.json'])
    if state.get('enabled') is not False or state.get('job'):
        raise ValueError('The test gateway must already be suspended and idle')
    jobs = json.loads(kube('-n', 'pz-server', 'get', 'jobs', '-o', 'json'))['items']
    for job in jobs:
        if not job.get('status', {}).get('active'):
            continue
        for container in job['spec']['template']['spec']['containers']:
            env = {e['name']: e.get('value', '') for e in container.get('env', [])}
            if env.get('GAAS_WORLD_ID', '').startswith('gaas-pz-') or 'GAAS_GATEWAY_CONFIG' in env:
                raise ValueError('An acceptance writer is still active')
    leases = json.loads(kube('-n', STATE_NS, 'get', 'leases', '-o', 'json'))['items']
    if any(l.get('spec', {}).get('holderIdentity') or l['metadata'].get('annotations') for l in leases):
        raise ValueError('The test Terraform backend is locked')
    return cfg


def environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith(('TF_VAR_', 'TF_CLI_ARGS', 'TF_LOG', 'KUBE_'))}
    values = obj('pz-server', 'secret', 'gaas-terraform-credentials')['data']
    env.update({k: base64.b64decode(v).decode() for k, v in values.items()})
    env.update(TF_IN_AUTOMATION='1', TF_CLI_CONFIG_FILE=str(WORK / 'terraform.rc'), TAILSCALE_TAILNET='-')
    return env


def terraform(*args):
    metadata = json.loads((MODULE / '.terraform/terraform.tfstate').read_text())['backend']
    if metadata['type'] != 'kubernetes' or (metadata['config']['namespace'], metadata['config']['secret_suffix']) != (STATE_NS, SUFFIX):
        raise ValueError('Wrong Terraform backend; production is forbidden')
    return run(['terraform', *args], cwd=MODULE, env=environment(), text=True)


def world_volumes():
    names = [('pz-server', 'gaas-world-gaas-pz-one-20261122-74b98351'),
             ('pz-server', 'gaas-world-gaas-pz-two-20261122-aedd39b8'),
             ('pz-server', 'pz-server-pz-server-data'),
             ('gaming', 'gaas-world-pz-bingops-34c51677')]
    return [{'namespace': ns, 'name': name, 'uid': obj(ns, 'pvc', name)['metadata']['uid']} for ns, name in names]


def production_backend_version():
    return kube('-n', 'gaming-state', 'get', 'secret', 'tfstate-default-edge-gateway',
                '-o', 'jsonpath={.metadata.resourceVersion}').strip()


def backup_receipt(job):
    value = obj('pz-server', 'job', job)
    if value.get('status', {}).get('succeeded') != 1:
        raise ValueError('The fresh test-state backup Job must succeed first')
    lines = kube('-n', 'pz-server', 'logs', 'job/' + job).splitlines()
    receipts = [json.loads(line.split('=', 1)[1]) for line in lines if line.startswith('GAAS_STATE_RECOVERY_JSON=')]
    if len(receipts) != 1 or receipts[0].get('resticIntegrity') != 'passed' or not receipts[0].get('restoredBundleMatches'):
        raise ValueError('A verified encrypted test-state backup is required')
    return receipts[0]


def plan(mirror, job):
    cfg = preflight()
    original, state = backend()
    receipt = backup_receipt(job)
    if receipt.get('backendResourceVersion') != original['metadata']['resourceVersion']:
        raise ValueError('The backup must match the current test backend')
    if not mirror or not mirror.is_dir() or len(list(mirror.rglob('*.zip'))) != 3:
        raise ValueError('Supply the public provider mirror matching the pinned module lock')
    archive = run(['git', 'archive', SOURCE, 'terraform/edge-gateway'], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(WORK, filter='data')
    (WORK / 'kubeconfig').write_text(kube('config', 'view', '--raw', '--flatten', '--minify'))
    (WORK / 'operator.pub').write_text(obj('pz-server', 'configmap', 'gaas-test-operator-key')['data']['operator.pub'])
    (WORK / 'terraform.rc').write_text('provider_installation { filesystem_mirror { path = ' + json.dumps(str(mirror.resolve())) + ' } }\n')
    save(MODULE / 'backend.tf.json', {'terraform': {'backend': {'kubernetes': {
        'namespace': STATE_NS, 'secret_suffix': SUFFIX, 'config_path': str(WORK / 'kubeconfig'), 'config_context': 'labprod'}}}})
    save(MODULE / 'zz-retirement.auto.tfvars.json', dict(cfg['variables'], enabled=False, ssh_public_key_path=str(WORK / 'operator.pub')))
    run(['terraform', 'init', '-input=false', '-reconfigure', '-lockfile=readonly'], cwd=MODULE, env=environment(), text=True)
    terraform('plan', '-destroy', '-input=false', '-lock-timeout=60s', '-out=' + str(WORK / 'retire.tfplan'))
    changes = safe_plan(json.loads(terraform('show', '-json', str(WORK / 'retire.tfplan'))))
    after, _ = backend()
    if after['data'] != original['data']:
        raise ValueError('Test state changed while planning')
    checkpoint = {'stateData': original['data'], 'lineage': state['lineage'],
                  'planHash': hashlib.sha256((WORK / 'retire.tfplan').read_bytes()).hexdigest(),
                  'changes': changes, 'backup': receipt, 'worldVolumes': world_volumes(),
                  'productionBackendVersion': production_backend_version()}
    save(WORK / 'checkpoint.json', checkpoint)
    return {'stage': 'plan', 'backendNamespace': STATE_NS, 'backendSuffix': SUFFIX,
            'changes': changes, 'beforeStateBackup': receipt, 'worldVolumesProtected': len(checkpoint['worldVolumes'])}


def api(url, token, header='Authorization'):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={header: 'Bearer ' + token}), timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError('Cloud verification failed; diagnostics withheld') from None


def verify():
    preflight()
    _, state = backend()
    checkpoint = json.loads((WORK / 'checkpoint.json').read_text())
    if managed(state) or state['lineage'] != checkpoint['lineage']:
        raise ValueError('Retained test backend is not empty with its original lineage')
    env = environment()
    for path in ['primary_ips/164378290', 'firewalls/12132632', 'ssh_keys/132947769']:
        if api('https://api.hetzner.cloud/v1/' + path, env['HCLOUD_TOKEN']) is not None:
            raise ValueError('A dated test cloud resource still exists')
    if api('https://api.hetzner.cloud/v1/servers?name=' + NAME, env['HCLOUD_TOKEN'])['servers']:
        raise ValueError('A dated test VM still exists')
    records = api(f'https://api.cloudflare.com/client/v4/zones/{ZONE}/dns_records?type=A&name={DNS}', env['CLOUDFLARE_API_TOKEN'])
    if not records.get('success') or records['result']:
        raise ValueError('The dated test DNS record still exists')
    production = api('https://api.hetzner.cloud/v1/primary_ips/154062800', env['HCLOUD_TOKEN'])
    if not production or production['primary_ip']['ip'] != '188.245.252.46' or production['primary_ip']['auto_delete']:
        raise ValueError('Production primary IP preservation could not be verified')
    if world_volumes() != checkpoint['worldVolumes']:
        raise ValueError('Retained world PVC identity changed')
    version = production_backend_version()
    result = {'testIPv4Deleted': '91.98.196.54', 'testPrimaryIPId': 164378290,
              'testDNSDeleted': DNS, 'testFirewallAndSSHKeyAbsent': True, 'testVMAbsent': True,
              'testBackendEmpty': True, 'testStateLineagePreserved': True,
              'productionIPv4Preserved': '188.245.252.46',
              'productionBackendUnchanged': version == checkpoint['productionBackendVersion'],
              'worldPVCsPreserved': checkpoint['worldVolumes'], 'beforeStateBackup': checkpoint['backup']}
    save(WORK / 'verified.json', result)
    return result


def apply():
    preflight()
    current, state = backend()
    checkpoint = json.loads((WORK / 'checkpoint.json').read_text())
    if not managed(state):
        return dict(verify(), alreadyRetired=True)
    if current['data'] != checkpoint['stateData']:
        raise ValueError('Test backend changed after the saved plan')
    if hashlib.sha256((WORK / 'retire.tfplan').read_bytes()).hexdigest() != checkpoint['planHash']:
        raise ValueError('The reviewed saved plan changed')
    if safe_plan(json.loads(terraform('show', '-json', str(WORK / 'retire.tfplan')))) != checkpoint['changes']:
        raise ValueError('Saved deletion scope changed')
    terraform('apply', '-input=false', '-lock-timeout=60s', str(WORK / 'retire.tfplan'))
    return verify()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['plan', 'apply', 'verify'])
    parser.add_argument('--provider-mirror', type=Path)
    parser.add_argument('--backup-job', default='gaas-test-state-before-retire-20261124')
    args = parser.parse_args()
    os.umask(0o077)
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        with (WORK / 'operation.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = plan(args.provider_mirror, args.backup_job) if args.stage == 'plan' else apply() if args.stage == 'apply' else verify()
            print('GAAS_TEST_RETIRE_JSON=' + json.dumps(result))
    except (ValueError, RuntimeError, OSError, KeyError):
        raise SystemExit('Test retirement stopped; private state and diagnostics withheld')


if __name__ == '__main__':
    main()
