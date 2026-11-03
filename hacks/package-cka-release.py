#!/usr/bin/env python3
"""Snapshot only non-secret CKA deployment manifests from an immutable Git commit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-f0-9]{40}', args.revision):
        parser.error('Use the exact 40-character source commit.')
    target = Path(__file__).resolve().parents[1] / 'apps/workloads/cka/labprod'
    names = ('kustomization.yaml', 'namespace.yaml', 'storage.yaml', 'deployment.yaml', 'service.yaml')
    content = {name: subprocess.check_output(['git', '-C', str(args.source), 'show', args.revision + ':deploy/' + name]) for name in names}
    # Only this explicit manifest allowlist is released, never controller faults,
    # worked solutions, source code, local environment or runtime state.
    target.mkdir(parents=True, exist_ok=True)
    for name, data in content.items():
        (target / name).write_bytes(data)
    record = {'repository': 'https://github.com/bingops-com/cka', 'revision': args.revision,
              'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}}
    (target / 'release.json').write_text(json.dumps(record, indent=2) + '\n')
    print('CKA deployment-only snapshot prepared at ' + args.revision + '; no live changes.')


if __name__ == '__main__':
    main()
