#!/usr/bin/python3
"""Install or reactivate a verified development release. Called only by devctl."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request

BASE = Path('/opt/dev-vm')
ENV = {**os.environ, 'MISE_DATA_DIR':str(BASE / 'mise'), 'DEBIAN_FRONTEND':'noninteractive', 'DISABLE_AUTOUPDATER':'1'}


def call(args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, env=ENV, umask=0o022, **kwargs)


def verify_release(root):
    root = Path(root)
    manifest = json.loads((root / 'manifest.json').read_text())
    files = manifest['files']
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if root.name != digest:
        raise ValueError('Release identity mismatch')
    if any(path.is_symlink() for path in root.rglob('*')):
        raise ValueError('Symlinked release content')
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p != root / 'manifest.json'}
    if actual != set(files):
        raise ValueError('Release file set differs')
    for name, expected in files.items():
        path = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root.parent):
            raise ValueError('Invalid release path')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Release checksum mismatch')
    return digest


def link(source, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.new')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(source)
    temporary.replace(destination)


def configure(root):
    tail_ip=subprocess.run(['tailscale','ip','-4'],check=True,capture_output=True,text=True).stdout.strip()
    import ipaddress
    if ipaddress.ip_address(tail_ip) not in ipaddress.ip_network('100.64.0.0/10'):
        raise ValueError('Missing VM tailnet address')
    for source in (root / 'configuration').glob('*.j2'):
        content=source.read_text().replace('{{ dev_tail_ip.stdout | trim }}',tail_ip)
        if '{{' in content or '{%' in content:
            raise ValueError('Unresolved native configuration template')
        name=source.name.removesuffix('.j2')
        if name=='nginx.conf':target=Path('/etc/nginx/sites-enabled/dev')
        elif name=='dnsmasq.conf':target=Path('/etc/dnsmasq.d/dev.conf')
        else:target=Path('/etc/systemd/system') / name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content);target.chmod(0o644)
    Path('/etc/nginx/sites-enabled/default').unlink(missing_ok=True)
    for name,target in [('nftables.conf','/etc/nftables.conf'),('sshd.conf','/etc/ssh/sshd_config.d/00-dev-vm.conf')]:
        shutil.copy2(root / 'configuration' / name,target)
    keys=Path('/home/dev/.ssh/authorized_keys')
    shutil.copy2(root / 'environment/authorized_keys',keys)
    os.chown(keys,1000,1000);keys.chmod(0o600)
    call(['sshd','-t']);call(['nft','-c','-f','/etc/nftables.conf'])
    call(['nft','-f','/etc/nftables.conf']);call(['systemctl','reload','ssh'])
    call(['systemctl','enable','--now','dnsmasq'])
    call(['systemctl','restart','dnsmasq'])


def venv_identity(root):
    environment=root / 'environment'
    return hashlib.sha256((environment / 'requirements.txt').read_bytes() + (environment / 'collections.yml').read_bytes()).hexdigest()


def activate_tools(root):
    verify_release(root)
    for name in ['mise.toml', 'mise.lock']:
        link(root / 'environment' / name, Path('/etc/mise') / ('config.toml' if name == 'mise.toml' else name))
    link(root / 'environment/.mise', '/etc/mise/.mise')
    link(BASE / 'venvs' / venv_identity(root), BASE / 'venv')
    link(Path('/home/dev/projects'), '/opt/homeops')
    version = re.search(r'dev_mise_version: "([0-9.]+)"', (root / 'environment/versions.yml').read_text())[1]
    link(BASE / 'bootstrap' / version / 'mise', '/usr/local/bin/mise')
    for executable in ['ansible', 'ansible-playbook', 'ansible-galaxy', 'ansible-lint', 'yamllint', 'pytest']:
        link(BASE / 'venv/bin' / executable, Path('/usr/local/bin') / executable)
    profile = '''export MISE_DATA_DIR=/opt/dev-vm/mise
export PATH="/opt/dev-vm/mise/shims:/opt/dev-vm/venv/bin:/usr/lib/postgresql/18/bin:$PATH"
export LANG=C.UTF-8
export LC_CTYPE=C.UTF-8
export CHROMIUM=/usr/bin/chromium
export DISABLE_AUTOUPDATER=1
export CLUSTERCTL_DISABLE_VERSIONCHECK=true
export ANSIBLE_COLLECTIONS_PATH=/home/dev/.ansible/collections:/opt/dev-vm/venv/collections
'''
    Path('/etc/profile.d/dev-tools.sh').write_text(profile)
    Path('/etc/profile.d/dev-tools.sh').chmod(0o644)
    Path('/etc/default/locale').write_text('LANG=C.UTF-8\n')
    Path('/etc/environment.d').mkdir(exist_ok=True)
    Path('/etc/environment.d/90-dev-tools.conf').write_text('MISE_DATA_DIR=/opt/dev-vm/mise\nDISABLE_AUTOUPDATER=1\n')
    Path('/etc/environment.d/90-dev-tools.conf').chmod(0o644)
    link(root, BASE / 'tooling')
    link(root / 'environment/check-tools.sh', '/usr/local/bin/homeops-dev-check')

    for source,target in [('codex.toml','/etc/codex/config.toml'),('claude.json','/etc/claude-code/managed-settings.json'),('screenrc','/etc/screenrc')]:
        destination=Path(target);destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(root / 'environment' / source,destination);destination.chmod(0o644)
    # Copied personal profiles may prepend legacy paths; reload the native tools last.
    hook='\n# Native development tools (managed)\n[ ! -r /etc/profile.d/dev-tools.sh ] || . /etc/profile.d/dev-tools.sh\n'
    for name in ['.profile','.bashrc']:
        path=Path('/home/dev') / name
        if path.is_symlink():raise ValueError('Refusing a symlinked shell profile')
        previous=path.read_text() if path.exists() else ''
        if hook not in previous:
            path.write_text(previous+hook);os.chown(path,1000,1000)


def activate(root):
    verify_release(root)
    configure(root)
    activate_tools(root)
    link(root, BASE / 'current')
    for name in ['dev_backup.py', 'devctl.py', 'dev_install.py', 'health.sh']:
        shutil.copy2(root / 'runtime' / name, Path('/usr/local/lib/dev-vm') / name)
    call(['systemctl','daemon-reload'])
    call(['systemctl','enable','--now','dev-agent','dev-gateway'])
    call(['systemctl','restart','dev-agent','dev-gateway'])
    call(['nginx','-t'])
    call(['systemctl','reload-or-restart','nginx'])


def install_oci_tools(environment):
    # Old upstream release assets can disappear. OCI manifest/layer digests
    # retain the exact reviewed tool from the original workspace image.
    import io
    state_path=Path('/var/lib/dev-vm/oci-tools.json')
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    accept='application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json'
    for tool in json.loads((environment / 'oci-tools.json').read_text()):
        if not re.fullmatch('[a-z0-9-]+',tool['name']):raise ValueError('Invalid OCI tool name')
        image=tool['image']
        match=re.fullmatch(r'(mirror[.]gcr[.]io)/([a-z0-9/_-]+):([^@]+)@(sha256:[a-f0-9]{64})',image)
        if not match:raise ValueError('Use a pinned public OCI image from the declared mirror')
        registry,repository,version,digest=match.groups()
        target=Path('/usr/local/bin') / tool['name']
        previous=state.get(tool['name'],{})
        if previous.get('image')==image and target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==previous.get('sha256'):
            continue
        base=f'https://{registry}/v2/{repository}'
        def fetch(kind,identifier):
            request=urllib.request.Request(f'{base}/{kind}/{identifier}',headers={'Accept':accept})
            data=urllib.request.urlopen(request,timeout=180).read()
            if 'sha256:'+hashlib.sha256(data).hexdigest()!=identifier:
                raise ValueError('OCI content digest differs')
            return data
        manifest=json.loads(fetch('manifests',digest))
        if 'manifests' in manifest:
            selected=next(m for m in manifest['manifests'] if m.get('platform',{}).get('os')=='linux' and m.get('platform',{}).get('architecture')=='amd64')
            manifest=json.loads(fetch('manifests',selected['digest']))
        binary=None
        for layer in manifest['layers']:
            with tarfile.open(fileobj=io.BytesIO(fetch('blobs',layer['digest'])),mode='r:*') as archive:
                for member in archive.getmembers():
                    if member.name.removeprefix('./')==tool['binary'] and member.isfile():
                        binary=archive.extractfile(member).read()
        if binary is None:raise ValueError('Declared binary is absent from the verified OCI image')
        temporary=target.with_name(target.name+'.dev-vm-new')
        temporary.write_bytes(binary);temporary.chmod(0o755);temporary.replace(target)
        state[tool['name']]={'image':image,'sha256':hashlib.sha256(binary).hexdigest()}
        state_path.write_text(json.dumps(state,indent=2)+'\n');state_path.chmod(0o600)


def install_tools(root):
    identifier = verify_release(root)
    environment = root / 'environment'
    # APT retains downloaded archives for recovery when upstream versions disappear.
    Path('/etc/apt/apt.conf.d/90-dev-cache').write_text('Binary::apt::APT::Keep-Downloaded-Packages "true";\nAPT::Keep-Downloaded-Packages "true";\n')
    keys = json.loads((environment / 'trust.json').read_text())
    for record in keys:
        content = urllib.request.urlopen(record['url'], timeout=30).read()
        if hashlib.sha256(content).hexdigest() != record['sha256']:
            raise ValueError('APT signing key changed; review trust.json')
        Path(record['path']).write_bytes(content)
        Path(record['path']).chmod(0o644)
    Path('/etc/apt/sources.list.d/dev-pgdg.list').write_text('deb [signed-by=/usr/share/keyrings/dev-pgdg.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main\n')
    packages = json.loads((environment / 'apt-tools.json').read_text())
    for package in packages:
        if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*', package['name']) or not re.fullmatch(r'[A-Za-z0-9:.+~_-]+',package['version']):
            raise ValueError('Invalid package declaration')
    requested = {p['name']:p['version'] for p in packages}
    installed = subprocess.run(['dpkg-query','--show','--showformat=${Package}\t${Version}\n',*requested],capture_output=True,text=True).stdout
    actual = dict(line.split('\t',1) for line in installed.splitlines() if '\t' in line)
    if any(actual.get(name) != version for name,version in requested.items()):
        call(['apt-get','update','-q'])
        call(['apt-get','install','-y','--no-install-recommends', *[p['name']+'='+p['version'] for p in packages]])
    install_oci_tools(environment)
    version = re.search(r'dev_mise_version: "([0-9.]+)"', (environment / 'versions.yml').read_text())[1]
    binary = BASE / 'bootstrap' / version / 'mise'
    if not binary.exists():
        url = f'https://api.github.com/repos/jdx/mise/releases/tags/v{version}'
        release = json.load(urllib.request.urlopen(url, timeout=30))
        name = f'mise-v{version}-linux-x64.tar.gz'
        asset = next(a for a in release['assets'] if a['name'] == name)
        expected = asset.get('digest','')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', expected):
            raise ValueError('Release has no SHA-256 provenance')
        data = urllib.request.urlopen(f'https://github.com/jdx/mise/releases/download/v{version}/{name}', timeout=120).read()
        if 'sha256:'+hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('mise artifact checksum differs')
        import io
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
            content = archive.extractfile('mise/bin/mise').read()
        binary.parent.mkdir(parents=True,exist_ok=True)
        (BASE / 'bootstrap').chmod(0o755)
        binary.parent.chmod(0o755)
        binary.write_bytes(content);binary.chmod(0o755)
    call([binary,'trust', environment / 'mise.toml'])
    call([binary,'install','--yes','--cd',environment])
    call([binary,'reshim','--cd',environment])
    venv = BASE / 'venvs' / venv_identity(root)
    if not (venv / '.ready').exists():
        call(['python3','-m','venv','--system-site-packages',venv])
        call([venv / 'bin/pip','install','--require-hashes','-r', environment / 'requirements.txt'])
        call([venv / 'bin/ansible-galaxy','collection','install','-r',environment / 'collections.yml','-p',venv / 'collections'])
        (venv / '.ready').touch()
    activate_tools(root)


def install(root):
    install_tools(root)
    # Keep previous tool installations and release venvs for rollback.
    if not Path('/etc/letsencrypt/live/code.lab.bingo/fullchain.pem').exists():
        call(['certbot','certonly','--non-interactive','--agree-tos','--register-unsafely-without-email','--dns-cloudflare','--dns-cloudflare-credentials','/etc/dev-vm/cloudflare.ini','--cert-name','code.lab.bingo','-d','code.lab.bingo','-d','*.code.lab.bingo'])
    hook = Path('/etc/letsencrypt/renewal-hooks/deploy/dev-nginx')
    hook.parent.mkdir(parents=True,exist_ok=True)
    hook.write_text('#!/bin/sh\nnginx -t && systemctl reload nginx\n');hook.chmod(0o755)
    activate(root)
    call(['systemctl','enable','--now','certbot.timer'])


if __name__ == '__main__':
    if len(sys.argv) != 2 or os.geteuid() != 0:
        raise SystemExit('Run through sudo devctl with a prepared release ID')
    install(Path(sys.argv[1]))
