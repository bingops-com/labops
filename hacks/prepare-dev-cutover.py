#!/usr/bin/env python3
"""Generate a reviewable GitOps/DNS retirement patch after a VM tailnet IP is known."""
import argparse
import difflib
import ipaddress
from pathlib import Path
import re
import textwrap

ROOT=Path(__file__).resolve().parent.parent


def prepare(tail_ip, phase="retire"):
    if ipaddress.ip_address(tail_ip) not in ipaddress.ip_network('100.64.0.0/10'):
        raise ValueError('Use the VM Tailscale IPv4 address')
    changes={}
    def edit(name,transform):
        original=(ROOT / name).read_text();updated=transform(original)
        if updated!=original:changes[name]=(original,updated)
    edit('apps/gitops/clusters/labprod/kustomization.yaml',lambda s:s.replace('\n  - coder.yaml','').replace('\n  - dev.yaml',''))
    def dns(s):
        start=s.index('    dev.lab.bingo:53 {')
        following=s.index('    argocd.lab.bingo:53 {',start)
        end=s.find('    coder.lab.bingo:53 {',start,following)
        if end<0:end=following
        dev=s[start:end].replace('192.168.10.151',tail_ip)
        return s[:start]+dev+s[following:]
    edit('apps/platform/private-dns/labprod/configmap.yaml',dns)
    def authentik(s):
        start=s.index('  coder.yaml: |');end=s.index('  romm.yaml: |',start)
        tombstone='''  coder.yaml: |
    version: 1
    metadata:
      name: labops-coder
    entries:
      - model: authentik_core.application
        state: absent
        identifiers: {slug: coder}
      - model: authentik_providers_oauth2.oauth2provider
        state: absent
        identifiers: {name: Coder production}
      - model: authentik_providers_oauth2.scopemapping
        state: absent
        identifiers: {name: Coder verified email}
      - model: authentik_providers_oauth2.scopemapping
        state: absent
        identifiers: {name: Coder group membership}
      - model: authentik_core.group
        state: absent
        identifiers: {name: coder-admins}
'''
        if phase=='retire':s=s[:start]+tombstone+s[end:]
        marker='      - model: authentik_outposts.outpost\n'
        if s.count(marker)!=1:raise ValueError('Shared outpost ownership changed; review the blueprint')
        if 'id: dev-proxy-provider' not in s:
            entries=(ROOT / 'environments/dev-vm/dev-proxy-entries.yaml.tmpl').read_text()
            s=s.replace(marker,textwrap.indent(entries,'      ')+marker)
        key='            - !KeyOf rom-request-proxy-provider\n'
        if '            - !KeyOf dev-proxy-provider\n' not in s:s=s.replace(key,key+'            - !KeyOf dev-proxy-provider\n')
        return s
    edit('apps/platform/authentik/blueprint.yaml',authentik)
    def tailnet_dns(s):
        # network owns the entire DNS configuration; tailscale-dns is retired.
        block=f'''  split_dns {{
    domain = "dev.lab.bingo"

    nameservers {{
      address = "{tail_ip}"
    }}
  }}

'''
        existing=r'  split_dns \{\n    domain = "dev[.]lab[.]bingo"\n\n    nameservers \{\n      address = "[^"\n]+"\n    \}\n  \}\n\n'
        if re.search(existing,s):
            return re.sub(existing,lambda _:block,s,count=1)
        marker='  magic_dns          = true\n'
        if s.count(marker)!=1 or 'domain = "dev.lab.bingo"' in s:
            raise ValueError('Tailnet DNS ownership/layout changed; review terraform/network/dns.tf')
        return s.replace(marker,block+marker)
    if phase=='retire':edit('terraform/network/dns.tf',tailnet_dns)
    # Monitoring from Kubernetes cannot bypass the tailnet-only firewall.
    def gatus(s):
        pattern=r'  - name: Coder\n(?:(?!  - name:)[\s\S])*?(?=  - name:|\Z)'
        return re.sub(pattern,'',s,count=1)
    edit('apps/workloads/gatus/base/config.yaml',gatus)
    edit('apps/workloads/portal/base/portal.yaml',lambda s:s.replace('                - coder-workspaces/coder-home-r2-backup\n','').replace('{ title: Coder, url: "https://coder.lab.bingo", description: Développement persistant, checkUrl: "http://coder.coder.svc.cluster.local/healthz" }','{ title: Dev, url: "https://dev.lab.bingo", description: VM privée via Tailscale }'))
    return {name:change for name,change in changes.items() if name=='apps/platform/authentik/blueprint.yaml'} if phase=='bootstrap' else changes


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tailscale-ip',required=True)
    parser.add_argument('--phase',choices=['bootstrap','retire'],default='retire')
    parser.add_argument('--output',type=Path,default=ROOT / '.runtime/dev-vm/cutover.patch')
    args=parser.parse_args();changes=prepare(args.tailscale_ip,args.phase)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('w') as stream:
        for name,(old,new) in changes.items():
            stream.writelines(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+name if old else '/dev/null',tofile='b/'+name))
    print(f'Prepared {len(changes)} source changes for review. Nothing was applied.')
