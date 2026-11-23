#!/usr/bin/env python3
"""One-time, checked adoption of the existing LabOps gateway; no raw diagnostics."""
import argparse
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.runtime/gaas-adoption-20261122'
ORIGINAL = Path('/home/coder/projects/labops/terraform/edge-gateway/terraform.tfstate')
RETIRED = ORIGINAL.with_name(ORIGINAL.name + '.retired-20261122')
MODULE = WORK / 'terraform/edge-gateway'
REPOSITORY = 's3:https://4d31056d6b4bf143606ff3ca757e0b8c.r2.cloudflarestorage.com/bingops-pz-labprod/gaas-production-state-backups'


def run(args, *, env=None, cwd=None, optional=False, binary=False):
    value = subprocess.run(args, env=env, cwd=cwd, capture_output=True, text=not binary)
    if value.returncode and not optional:
        raise RuntimeError('Command failed: ' + args[0] + '; private diagnostics withheld')
    return value


def kube(args, optional=False):
    return run(['kubectl', '--context', 'labprod'] + args, optional=optional).stdout


def secret(namespace, name):
    value = json.loads(kube(['-n', namespace, 'get', 'secret', name, '-o', 'json']))
    return {key: base64.b64decode(val).decode() for key, val in value['data'].items()}


def attributes(state, kind):
    matches = [r for r in state['resources'] if r.get('mode') == 'managed' and r['type'] == kind]
    if len(matches) != 1 or len(matches[0]['instances']) != 1:
        raise ValueError('Unexpected managed resource inventory')
    return matches[0]['instances'][0]['attributes']


def validate(state, lineage=None):
    if not state.get('lineage') or not isinstance(state.get('serial'), int):
        raise ValueError('Invalid state identity')
    if lineage is not None and state['lineage'] != lineage:
        raise ValueError('State lineage differs')
    if str(attributes(state, 'hcloud_primary_ip')['id']) != '154062800':
        raise ValueError('Unexpected retained primary IP')
    if str(attributes(state, 'hcloud_server')['id']) != '169230729':
        raise ValueError('Unexpected initial gateway VM')


def settings():
    docs = yaml.safe_load_all((ROOT / 'apps/workloads/gaas/production/system/config.yaml').read_text())
    cfg = next(json.loads(d['data']['config.json']) for d in docs if d['metadata']['name'] == 'gaas-gateway')
    if (cfg['stateNamespace'], cfg['stateSuffix'], cfg['expectedName']) != ('gaming-state', 'edge-gateway', 'labops-edge-01'):
        raise ValueError('Unexpected adoption configuration')
    return cfg


def terraform(args):
    env = dict(os.environ, TF_IN_AUTOMATION='1', TF_CLI_CONFIG_FILE=str(WORK / 'terraform.rc'), TAILSCALE_TAILNET='-')
    env.update(secret('pz-server', 'gaas-terraform-credentials'))
    return run(['terraform'] + args, env=env, cwd=MODULE).stdout


def plan():
    cfg = settings()
    blob = ORIGINAL.read_bytes()
    state = json.loads(blob)
    validate(state)
    archive = run(['git', 'archive', cfg['sourceRevision'], 'terraform/edge-gateway'], binary=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(WORK, filter='data')
    if (MODULE / 'backend.tf.json').exists():
        raise ValueError('Adoption workspace already uses a remote backend')
    (MODULE / 'terraform.tfstate').write_bytes(blob)
    (WORK / 'baseline.sha256').write_text(hashlib.sha256(blob).hexdigest())
    (WORK / 'operator.pub').write_text(attributes(state, 'hcloud_ssh_key')['public_key'])
    variables = dict(cfg['variables'], ssh_public_key_path=str(WORK / 'operator.pub'))
    (MODULE / 'zz-gaas.auto.tfvars.json').write_text(json.dumps(variables))
    mirror = WORK / 'provider-mirror'
    if not mirror.is_dir():
        mirror.mkdir()
        archive = run(['kubectl', '--context', 'labprod', '-n', 'pz-server', 'exec', 'deploy/gaas-acceptance-controller', '--', 'tar', '-C', '/opt/terraform/providers', '-cf', '-', '.'], binary=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(mirror, filter='data')
    if len(list(mirror.rglob('*.zip'))) != 3:
        raise ValueError('Unexpected public provider mirror')
    (WORK / 'terraform.rc').write_text('provider_installation { filesystem_mirror { path = ' + json.dumps(str(mirror)) + ' } }\n')
    terraform(['init', '-input=false', '-lockfile=readonly'])
    terraform(['plan', '-input=false', '-lock-timeout=60s', '-out=' + str(WORK / 'adoption.tfplan')])
    summary = safe_plan(WORK / 'adoption.tfplan')
    (WORK / 'plan-summary.json').write_text(json.dumps(summary))
    return {'refreshedPlan': summary, 'originalStateUnchanged': ORIGINAL.read_bytes() == blob}


def safe_plan(path):
    value = json.loads(terraform(['show', '-json', str(path)]))
    changes = [r for r in value.get('resource_changes', []) if r.get('mode') == 'managed']
    if len(changes) != 7 or any(r['change']['actions'] != ['no-op'] for r in changes):
        raise ValueError('Adoption must have exactly seven no-op managed resources')
    return [{'address': r['address'], 'actions': r['change']['actions'], 'previousAddress': r.get('previous_address')} for r in changes]


def backup():
    blob = ORIGINAL.read_bytes()
    if hashlib.sha256(blob).hexdigest() != (WORK / 'baseline.sha256').read_text():
        raise ValueError('Local state changed; repeat preflight')
    env = dict(os.environ, RESTIC_REPOSITORY=REPOSITORY, RESTIC_CACHE_DIR=str(WORK / 'restic-cache'), AWS_DEFAULT_REGION='auto')
    env.update(secret('pz-server', 'pz-r2-credentials'))
    def restic(args):
        return run(['restic'] + args, env=env).stdout
    if run(['restic', 'cat', 'config'], env=env, optional=True).returncode:
        # Explicit provisioning of this dedicated adoption repository only.
        restic(['init'])
    output = restic(['backup', str(MODULE / 'terraform.tfstate'), '--host', 'labops-edge-01', '--tag', 'gaas-production-adoption-original', '--json'])
    summary = next(json.loads(l) for l in output.splitlines() if json.loads(l).get('message_type') == 'summary')
    snapshots = json.loads(restic(['snapshots', '--json', summary['snapshot_id']]))
    if len(snapshots) != 1:
        raise ValueError('Ambiguous state backup')
    snapshot = snapshots[0]['id']
    restic(['check', '--read-data'])
    target = WORK / 'restored-original'
    restic(['restore', snapshot, '--target', str(target), '--quiet'])
    restored = list(target.rglob('terraform.tfstate'))
    if len(restored) != 1 or restored[0].read_bytes() != blob:
        raise ValueError('Restored original state differs')
    validate(json.loads(restored[0].read_bytes()))
    receipt = {'originalStateBackupSnapshot': snapshot, 'resticFullIntegrity': 'passed', 'restoredOriginalStateMatches': True, 'originalStateUnchanged': True, 'liveBackendModified': False}
    (WORK / 'original-backup-receipt.json').write_text(json.dumps(receipt))
    return receipt


def migrate():
    cfg = settings()
    checkpoint = WORK / 'migration-receipt.json'
    if checkpoint.exists():
        if not kube(['-n', cfg['stateNamespace'], 'get', 'secret', 'tfstate-default-edge-gateway', '-o', 'name']).strip():
            raise ValueError('Recorded migration backend is missing')
        return dict(json.loads(checkpoint.read_text()), alreadyMigrated=True)
    receipt = json.loads((WORK / 'original-backup-receipt.json').read_text())
    if not receipt['restoredOriginalStateMatches'] or receipt['resticFullIntegrity'] != 'passed':
        raise ValueError('Verified encrypted backup is required')
    blob = ORIGINAL.read_bytes()
    if hashlib.sha256(blob).hexdigest() != (WORK / 'baseline.sha256').read_text():
        raise ValueError('Original state changed; stop other writers and repeat preflight')
    before = json.loads(blob)
    validate(before)
    kube(['get', 'namespace', cfg['stateNamespace'], '-o', 'name'])
    remote = kube(['-n', cfg['stateNamespace'], 'get', 'secret', 'tfstate-default-edge-gateway', '--ignore-not-found', '-o', 'json'])
    if remote.strip():
        state = json.loads(gzip.decompress(base64.b64decode(json.loads(remote)['data']['tfstate'])))
        validate(state, before['lineage'])
    kubeconfig = kube(['config', 'view', '--raw', '--flatten', '--minify'])
    (WORK / 'kubeconfig').write_text(kubeconfig)
    backend = {'terraform': {'backend': {'kubernetes': {'namespace': cfg['stateNamespace'], 'secret_suffix': cfg['stateSuffix'], 'config_path': str(WORK / 'kubeconfig'), 'config_context': 'labprod'}}}}
    (MODULE / 'backend.tf.json').write_text(json.dumps(backend))
    terraform(['init', '-input=false', '-lockfile=readonly'] + (['-reconfigure'] if remote.strip() else ['-migrate-state', '-force-copy']))
    terraform(['plan', '-input=false', '-lock-timeout=60s', '-out=' + str(WORK / 'remote-adoption.tfplan')])
    summary = safe_plan(WORK / 'remote-adoption.tfplan')
    terraform(['apply', '-input=false', '-lock-timeout=60s', str(WORK / 'remote-adoption.tfplan')])
    state = json.loads(terraform(['state', 'pull']))
    validate(state, before['lineage'])
    if ORIGINAL.read_bytes() != blob:
        raise ValueError('Another local writer changed state; migration needs review')
    if RETIRED.exists() and RETIRED.read_bytes() != blob:
        raise ValueError('Retired state recovery path already contains different data')
    ORIGINAL.replace(RETIRED)
    result = {'backendNamespace': cfg['stateNamespace'], 'backendSuffix': cfg['stateSuffix'], 'originalStateBackupSnapshot': receipt['originalStateBackupSnapshot'], 'retainedVMId': '169230729', 'retainedPrimaryIPId': '154062800', 'lineagePreserved': True, 'managedChanges': summary, 'localExecutionStateRetired': True}
    checkpoint.write_text(json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['plan', 'backup', 'migrate'])
    args = parser.parse_args()
    os.umask(0o077)
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        print(json.dumps({'GAAS_ADOPTION': {'plan': plan, 'backup': backup, 'migrate': migrate}[args.stage]()}))
    except (RuntimeError, ValueError, KeyError, OSError, json.JSONDecodeError):
        raise SystemExit('Gateway adoption failed safely; private state and diagnostics withheld')


if __name__ == '__main__':
    main()
