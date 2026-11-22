#!/usr/bin/env python3
"""Recover VM inputs privately; persist and reread its independent backup key in Bitwarden."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'environments/dev-vm/recovery.json').read_text())
ORG = CONFIG['organization_id']
PROJECT = CONFIG['project_id']
R2_ACCESS = CONFIG['r2_access_secret_id']
R2_SECRET = CONFIG['r2_secret_secret_id']
STAGE = 'initialization'


def main():
    global STAGE
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--context', default='labprod')
    parser.add_argument('--use-cluster-token', action='store_true')
    parser.add_argument('--cloudflare-from-cluster', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)

    def cluster_secret(namespace, name, key):
        result = subprocess.run(['kubectl', '--context', args.context, 'get', 'secret', name, '-n', namespace, '-o', 'json'], capture_output=True, check=True)
        return base64.b64decode(json.loads(result.stdout)['data'][key]).decode()

    from bitwarden_sdk import BitwardenClient
    client = BitwardenClient()
    token = os.environ.get('BWS_ACCESS_TOKEN')
    if not token and args.use_cluster_token:
        token = cluster_secret('argocd-system', 'bw-auth-token', 'token')
    if not token:
        raise RuntimeError('Supply the external machine account access token')
    STAGE = 'Bitwarden authentication'
    login = client.auth().login_access_token(token)
    if not login.success or not login.data.authenticated:
        raise RuntimeError('Authentication failed')
    identifiers = client.secrets().list(ORG)
    if not identifiers.success:
        raise RuntimeError('Cannot list recovery project')

    def get(identifier):
        result = client.secrets().get(str(identifier))
        if not result.success:
            raise RuntimeError('Cannot read recovery input')
        return result.data.value

    def remember(key, generate, field):
        if CONFIG.get(field):
            identifier=CONFIG[field]
            return identifier,get(identifier)
        matches = [s for s in identifiers.data.data if s.key == key and PROJECT in map(str, s.project_ids or [])]
        if len(matches) > 1:
            raise RuntimeError('Ambiguous recovery key')
        if matches:
            identifier = matches[0].id
            return str(identifier), get(identifier)
        value = generate()
        result = client.secrets().create(uuid.UUID(ORG), key, value, 'Native development VM recovery. Never remove while retained encrypted backups depend on this input.', [uuid.UUID(PROJECT)])
        if not result.success:
            raise RuntimeError('Cannot persist independent recovery input')
        identifier = result.data.id
        if not secrets.compare_digest(get(identifier), value):
            raise RuntimeError('Vault read-back verification failed')
        return str(identifier), value

    def save(name, text):
        target = output / name
        if target.exists() and target.read_text() != text:
            raise RuntimeError('Existing private input differs; refusing replacement')
        target.write_text(text)
        target.chmod(0o600)

    STAGE = 'backup password persistence and verification'
    password_file = output / 'restic-password'
    password_id, password = remember('dev-vm-restic-password', lambda: password_file.read_text().strip() if password_file.exists() else secrets.token_urlsafe(48), 'restic_password_secret_id')
    save('restic-password', password + '\n')
    STAGE = 'TLS credential persistence and verification'
    def cloudflare():
        if not args.cloudflare_from_cluster:
            raise RuntimeError('Recover the existing TLS token before initial vault enrollment')
        return cluster_secret('cert-manager', 'cloudflare-api-token', 'api-token')
    cloudflare_id, cf_token = remember('dev-vm-cloudflare-dns-token', cloudflare, 'cloudflare_dns_token_secret_id')
    save('cloudflare.ini', 'dns_cloudflare_api_token = ' + cf_token.strip() + '\n')
    STAGE = 'R2 credential recovery'
    access, secret = get(R2_ACCESS), get(R2_SECRET)
    if any(c in access + secret for c in '\r\n\t '):
        raise RuntimeError('Invalid backup environment value')
    save('backup.env', 'RESTIC_REPOSITORY=s3:https://4d31056d6b4bf143606ff3ca757e0b8c.r2.cloudflarestorage.com/bingops-cnpg-labprod/dev-vm/restic\nRESTIC_PASSWORD_FILE=/etc/dev-vm/restic-password\nAWS_ACCESS_KEY_ID=' + access + '\nAWS_SECRET_ACCESS_KEY=' + secret + '\n')
    receipt = {'organization_id': ORG, 'project_id': PROJECT, 'restic_password_secret_id': password_id, 'cloudflare_dns_token_secret_id': cloudflare_id, 'r2_access_secret_id': R2_ACCESS, 'r2_secret_secret_id': R2_SECRET, 'vault_readback_verified': True}
    save('recovery-inputs.json', json.dumps(receipt, indent=2) + '\n')
    print('Recovery inputs prepared privately; independent password persisted and verified in Bitwarden.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit(f'Recovery preparation failed during {STAGE} ({type(error).__name__}); no secret output was displayed.') from None
