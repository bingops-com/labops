#!/usr/bin/env python3
"""Package the reviewed VM environment and Dev application without private inputs."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parent.parent


def build(app, output):
    files = {}
    def add(path, name):
        if path.is_symlink():
            raise ValueError('Symlinked release inputs are not allowed')
        files[name] = path.read_bytes()
    for name in ['apt-tools.json','mise.toml','mise.lock','requirements.in','requirements.txt','collections.yml','versions.yml','trust.json','check-tools.sh','authorized_keys','codex.toml','claude.json','screenrc']:
        add(ROOT / 'environments/dev-vm' / name,'environment/'+name)
    for path in (ROOT / 'environments/dev-vm/.mise/locks').rglob('*'):
        if path.is_file():
            add(path,'environment/'+str(path.relative_to(ROOT / 'environments/dev-vm')))
    for name in ['dev_backup.py','devctl.py','dev_install.py','health.sh']:
        add(ROOT / 'ansible/roles/dev_vm/files' / name,'runtime/'+name)
    role=ROOT / 'ansible/roles/dev_vm'
    for path in (role / 'templates').glob('*.j2'):
        add(path,'configuration/'+path.name)
    for name in ['nftables.conf','sshd.conf']:
        add(role / 'files' / name,'configuration/'+name)
    for name in ['server.mjs','package.json','workspace/agent.py']:
        add(app / name,'app/'+name)
    for path in (app / 'web').rglob('*'):
        if path.is_file():
            add(path,'app/'+str(path.relative_to(app)))
    hashes={name:hashlib.sha256(content).hexdigest() for name,content in sorted(files.items())}
    identifier=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    files['manifest.json']=(json.dumps({'files':hashes},indent=2)+'\n').encode()
    output.mkdir(parents=True,exist_ok=True)
    archive=output / (identifier+'.tar.gz')
    with tarfile.open(archive,'w:gz') as tar:
        for name,content in sorted(files.items()):
            info=tarfile.TarInfo(identifier+'/'+name);info.size=len(content);info.mode=0o755 if name.endswith(('.py','.sh')) else 0o644
            tar.addfile(info,io.BytesIO(content))
    return identifier,archive


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT / '.runtime/dev-vm')
    args=parser.parse_args()
    identifier,archive=build(args.app.resolve(),args.output.resolve())
    print(json.dumps({'release_id':identifier,'archive':str(archive)}))
