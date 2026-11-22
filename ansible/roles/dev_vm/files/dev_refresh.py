#!/usr/bin/python3
"""Prepare a reviewed Git release and invoke the existing backup-protected updater."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True
BASE = Path('/opt/dev-vm')
STATE = Path('/var/lib/dev-vm')


def main():
    if os.geteuid() != 0:
        raise SystemExit('Use sudo dev-refresh')
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', default='master')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--run', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.revision != 'master' and not re.fullmatch('[a-f0-9]{40}', args.revision):
        raise ValueError('Use master or an exact reviewed merge commit')
    if not args.prepare_only and not (STATE / 'initial-acceptance.json').exists():
        raise RuntimeError('Initial backup/restore acceptance is still running')
    if not args.run:
        command = ['systemd-run', '--unit=dev-refresh', '--collect', '--property=Type=exec', sys.executable, '-B', str(Path(__file__).resolve()), '--run', '--revision', args.revision]
        if args.prepare_only:
            command.append('--prepare-only')
        subprocess.run(command, check=True)
        print('Refresh runs independently of SSH. Inspect sudo journalctl -u dev-refresh and sudo devctl status.')
        return
    os.environ['DEV_VM_BUILD_USER'] = 'dev'
    from dev_sources import fetch, github
    from dev_install import verify_release
    repository = 'bingops-com/labops'
    commit = github(repository, 'commits/' + args.revision)['sha']
    if not re.fullmatch('[a-f0-9]{40}', commit):
        raise ValueError('Invalid source identity')
    if args.revision != 'master':
        comparison = github(repository, 'compare/' + commit + '...master')
        if comparison['status'] not in {'ahead', 'identical'}:
            raise ValueError('The selected commit is not part of reviewed master history')
    print('Preparing reviewed source commit ' + commit, flush=True)
    archives = BASE / 'archives'
    releases = BASE / 'releases'
    archives.mkdir(exist_ok=True)
    releases.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=BASE) as directory:
        temporary = Path(directory)
        source = fetch(repository, commit, temporary / 'labops')
        result = subprocess.run([sys.executable, '-B', str(source / 'hacks/build-dev-release.py'), '--output', str(archives)], capture_output=True, text=True, timeout=600)
        if result.returncode:
            raise RuntimeError('Release packaging failed; the active environment was not changed')
        package = json.loads(result.stdout)
        identifier = package['release_id']
        archive = Path(package['archive']).resolve()
        if not re.fullmatch('[a-f0-9]{64}', identifier) or not archive.is_relative_to(archives):
            raise ValueError('Invalid release package')
        target = releases / identifier
        if not target.exists():
            staging = temporary / 'release'
            staging.mkdir()
            with tarfile.open(archive, 'r:gz') as bundle:
                for member in bundle.getmembers():
                    parts = PurePosixPath(member.name).parts
                    if not parts or parts[0] != identifier or '..' in parts or not (member.isfile() or member.isdir()):
                        raise ValueError('Invalid release archive entry')
                bundle.extractall(staging, filter='data')
            root = staging / identifier
            verify_release(root)
            for path in [root, *root.rglob('*')]:
                if path.is_dir():
                    path.chmod(0o755)
            root.rename(target)
        verify_release(target)
    STATE.mkdir(exist_ok=True)
    (STATE / 'refresh-prepared.json').write_text(json.dumps({'source_commit': commit, 'release': identifier, 'prepare_only': args.prepare_only}, indent=2) + '\n')
    if args.prepare_only:
        print('Verified staged release ' + identifier + '; active environment unchanged.')
        return
    subprocess.run(['/usr/local/sbin/devctl', '_update', identifier], check=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit(f'Refresh failed ({type(error).__name__}); inspect the recovery status. No credential output was displayed.') from None
