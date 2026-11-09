#!/usr/bin/env python3
"""Recover CKA mail and session inputs without disclosing credentials.

The selected vault entry owns Resend; the generated session key is retained in
.runtime/cka-account-services/session-key on the backed-up Coder home volume.
This helper creates only an absent cka/cka-account-services Secret. It refuses
an existing differing Secret instead of silently rotating active sessions.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

VAULT_SECRET = 'b5019b76-14a0-4cdc-9de9-b4fd009d63d9'
SENDER = 'KubeQuest <accounts@cka.lab.bingo>'


def captured(args, **kwargs):
    result = subprocess.run(args, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError('Private input unavailable; no provider diagnostics displayed')
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--bws', default=os.environ.get('BWS_BIN', 'bws'))
    args = parser.parse_args()
    if not args.apply:
        print('No mutation. Pass --apply to create the absent named Secret from its recovery sources.')
        return
    os.umask(0o077)
    root = Path(__file__).resolve().parents[1] / '.runtime/cka-account-services'
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    keyfile = root / 'session-key'
    existing = subprocess.run(['kubectl', '--context', 'labprod', '-n', 'cka', 'get', 'secret', 'cka-account-services', '--ignore-not-found', '-o', 'json'], capture_output=True)
    if existing.returncode:
        raise RuntimeError('Cannot inspect the exact target Secret')
    saved = json.loads(existing.stdout) if existing.stdout.strip() else None
    if saved and not keyfile.exists():
        raise RuntimeError('Restore session-key from retained-home backup before reconciling an existing Secret')
    if not keyfile.exists():
        with keyfile.open('x') as file:
            file.write(secrets.token_hex(32) + '\n')
    if keyfile.stat().st_mode & 0o077:
        raise RuntimeError('Session recovery input must have mode 0600')
    key = keyfile.read_text().strip()
    if not re.fullmatch('[a-f0-9]{64}', key):
        raise RuntimeError('Invalid retained session input')
    token_secret = json.loads(captured(['kubectl', '--context', 'labprod', '-n', 'argocd-system', 'get', 'secret', 'bw-auth-token', '-o', 'json']))
    token = base64.b64decode(token_secret['data']['token'], validate=True).decode()
    config = root / 'bws-config.toml'
    config.write_text('[profiles.default]\nserver_api="https://api.bitwarden.com"\nserver_identity="https://identity.bitwarden.com"\nstate_opt_out="true"\n')
    env = dict(os.environ, BWS_ACCESS_TOKEN=token)
    entry = json.loads(captured([args.bws, '--config-file', str(config), 'secret', 'get', VAULT_SECRET], env=env))
    if entry.get('key') != 'lab-bingo-resend-api-key' or not entry.get('value', '').startswith('re_'):
        raise RuntimeError('Unexpected vault entry')
    data = {name: base64.b64encode(value.encode()).decode() for name, value in {'RESEND_API_KEY': entry['value'], 'CKA_MAIL_FROM': SENDER, 'CKA_SESSION_ENCRYPTION_KEY': key}.items()}
    if saved:
        if saved.get('data') != data:
            raise RuntimeError('Existing Secret differs; review a separate rotation before replacing it')
        print('CKA account-services input already matches its recovery sources; no change.')
        return
    payload = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': 'cka-account-services', 'namespace': 'cka', 'labels': {'app.kubernetes.io/part-of': 'kubequest'}}, 'type': 'Opaque', 'data': data}
    captured(['kubectl', '--context', 'labprod', 'create', '-f', '-'], input=json.dumps(payload).encode())
    print('Created cka/cka-account-services; vault sender and retained session input verified, values withheld.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError):
        raise SystemExit('Account-services bootstrap refused. Check named input access, retained recovery file and existing Secret without printing their values.')
