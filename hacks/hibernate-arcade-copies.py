#!/usr/bin/env python3
"""Reconcile the already-hibernated disposable copies without changing storage."""
import json
from pathlib import Path
import subprocess

import yaml

root = Path(__file__).resolve().parents[1]
manifest = root / 'apps/workloads/arcade/operations/hibernate-copies.yaml'
items = yaml.safe_load(manifest.read_text())['items']
commands = []
for item in items:
    meta = item['metadata']
    cmd = ['kubectl', '--context', 'labprod', '-n', meta['namespace']]
    live = json.loads(subprocess.check_output(cmd + ['get', 'cluster', meta['name'], '-o', 'json']))
    if (live['metadata'].get('annotations', {}).get('cnpg.io/hibernation') != 'on'
            or live['spec'].get('instances') != 1):
        raise SystemExit(f"Refusing to modify active or scaled cluster {meta['namespace']}/{meta['name']}")
    patch = {'metadata': {'annotations': meta['annotations']}, 'spec': item['spec']}
    commands.append(cmd + ['patch', 'cluster', meta['name'], '--type=merge', '-p', json.dumps(patch)])
for cmd in commands:
    subprocess.run(cmd, check=True)
