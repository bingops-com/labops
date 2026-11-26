#!/usr/bin/env python3
"""Retire only the confirmed Coder namespaces after native VM recovery acceptance."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent.parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--confirm',choices=['coder,coder-workspaces'],required=True)
    args=parser.parse_args()
    receipt=json.loads(args.receipt.read_text())
    required=['data_verified','vm_health_verified','tailscale_ssh_verified','lan_ssh_denied','backup_verified','restore_verified','dev_dns_verified']
    if any(receipt.get(key) is not True for key in required):
        raise SystemExit('Migration and recovery acceptance are incomplete')
    for key in ['release_id','data_snapshot','system_snapshot']:
        if not isinstance(receipt.get(key),str) or not receipt[key]:raise SystemExit('Missing recovery identity')
    def kubectl(*args):
        return subprocess.run(['kubectl','--context','labprod',*args],check=True,capture_output=True,text=True).stdout
    # Argo must first stop declaring these applications, otherwise self-heal can
    # recreate resources while their namespaces and data are being retired.
    for name in ['coder-labprod','dev-labprod']:
        if kubectl('get','application',name,'-n','argocd-system','--ignore-not-found','-o','name').strip():
            raise SystemExit('Retire the GitOps Application declarations before namespace deletion')
    config=(ROOT / 'apps/gitops/clusters/labprod/kustomization.yaml').read_text()
    if '\n  - coder.yaml' in config or '\n  - dev.yaml' in config:
        raise SystemExit('The local GitOps source still declares Coder')
    # Exact namespace targets, no generic label/volume/bucket deletion.
    kubectl('delete','namespace','coder','coder-workspaces','--ignore-not-found=true','--wait=true','--timeout=10m')
    print('Coder namespaces retired. Existing off-host archives remain under their retention policy.')


if __name__=='__main__':
    main()
