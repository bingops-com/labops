"""Fetch an exact reviewed GitHub source archive without storing or logging credentials."""
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile


def github(repository, endpoint, output=None):
    if repository not in {'bingops-com/labops', 'bingops-com/dev'}:
        raise ValueError('Unexpected source repository')
    command = ['/usr/bin/gh', 'api', '--hostname', 'github.com', 'repos/' + repository + '/' + endpoint]
    if os.geteuid() == 0 and os.environ.get('DEV_VM_BUILD_USER') == 'dev':
        command = ['runuser', '-u', 'dev', '--', *command]
    result = subprocess.run(command, cwd='/tmp', stdout=output or subprocess.PIPE, stderr=subprocess.PIPE, timeout=240)
    if result.returncode:
        raise RuntimeError('Reviewed source download failed; verify GitHub login and connectivity')
    return json.loads(result.stdout) if output is None else None


def fetch(repository, commit, destination):
    if not re.fullmatch('[a-f0-9]{40}', commit):
        raise ValueError('Use an exact source commit')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / 'source.tar.gz'
    with archive.open('wb') as stream:
        github(repository, 'tarball/' + commit, stream)
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        roots = {PurePosixPath(member.name).parts[0] for member in members}
        if len(roots) != 1 or any(PurePosixPath(member.name).is_absolute() or '..' in PurePosixPath(member.name).parts for member in members):
            raise ValueError('Invalid GitHub source archive')
        source.extractall(destination, filter='data')
    root = destination / next(iter(roots))
    if not root.is_dir() or root.is_symlink():
        raise ValueError('Invalid source root')
    return root
