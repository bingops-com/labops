#!/usr/bin/python3
"""Encrypted data backup, real isolated restore acceptance and full-VM checkpoints."""
import argparse
from contextlib import closing
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone

STATE = Path(os.environ.get('DEV_VM_STATE', '/var/lib/dev-vm'))
HOME = Path(os.environ.get('DEV_VM_HOME', '/home/dev'))


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, **kwargs)


def restic(*args):
    return run(['restic', *map(str, args)], text=True).stdout


def write_json(path, value):
    temporary = path.with_suffix('.new')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def completed_snapshot(output):
    for line in reversed(output.splitlines()):
        value = json.loads(line)
        if value.get('message_type') == 'summary' and value.get('snapshot_id'):
            return value['snapshot_id']
    raise RuntimeError('Restic returned no completed snapshot')


def snapshot_sqlite(home, destination):
    """Use SQLite's backup API, including committed WAL data; never copy a live DB."""
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    databases = []
    account = home / '.codex'
    for source in sorted(set(account.rglob('*.sqlite')) | set(account.rglob('*.db'))):
        if source.is_symlink() or any(p.is_symlink() for p in source.parents if p != home.parent):
            raise RuntimeError('Refusing symlinked account database')
        relative = source.relative_to(home)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.unlink(missing_ok=True)
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=30)) as original:
            with closing(sqlite3.connect(target)) as copied:
                original.backup(copied)
                if copied.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    raise RuntimeError('SQLite snapshot verification failed')
        target.chmod(0o600)
        databases.append(str(relative))
    # Do not keep databases deleted since the previous backup.
    for old in destination.rglob('*'):
        if old.is_file() and str(old.relative_to(destination)) not in databases:
            old.unlink()
    return databases


def backup():
    sentinel = os.urandom(32).hex() + '\n'
    (STATE / 'restore-sentinel').write_text(sentinel)
    databases = snapshot_sqlite(HOME, STATE / 'sqlite')
    paths = [HOME, STATE / 'sqlite', STATE / 'restore-sentinel']
    for path in ['/etc/dev-vm', '/etc/ssh', '/etc/mise', '/opt/dev-vm/releases', '/var/cache/apt/archives']:
        if Path(path).exists() and not os.environ.get('DEV_VM_TEST'):
            paths.append(Path(path))
    args = ['backup', '--json', '--host', 'dev-vm', '--tag', 'dev-vm-data']
    for pattern in ['**/node_modules/**', '**/.venv/**', '**/.cache/**', '**/.npm/**', str(HOME / '.codex/**/*.sqlite*'), str(HOME / '.codex/**/*.db*'), str(HOME / '.codex/*.sqlite*'), str(HOME / '.codex/*.db*')]:
        args += ['--exclude', pattern]
    identifier = completed_snapshot(restic(*args, *paths))
    write_json(STATE / 'backup.json', {'snapshot':identifier,'sentinel_sha256':hashlib.sha256(sentinel.encode()).hexdigest(),'databases':databases,'completed_at':datetime.now(timezone.utc).isoformat()})
    return identifier


def restore_test():
    status = json.loads((STATE / 'backup.json').read_text())
    restic('check', '--read-data-subset=1/10')
    with tempfile.TemporaryDirectory(prefix='restore-', dir=STATE) as directory:
        root = Path(directory)
        restic('restore', status['snapshot'], '--target', root, '--include', STATE / 'restore-sentinel', '--include', str(STATE / 'sqlite') + '/**')
        sentinel = root / (STATE / 'restore-sentinel').relative_to('/')
        if hashlib.sha256(sentinel.read_bytes()).hexdigest() != status['sentinel_sha256']:
            raise RuntimeError('Restored sentinel differs')
        for database in status['databases']:
            restored = root / (STATE / 'sqlite').relative_to('/') / database
            with closing(sqlite3.connect(restored.as_uri() + '?mode=ro', uri=True)) as connection:
                if connection.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    raise RuntimeError('Restored SQLite database is corrupt')
    write_json(STATE / 'restore-test.json', {'snapshot':status['snapshot'],'completed_at':datetime.now(timezone.utc).isoformat()})
    return status['snapshot']


def checkpoint():
    """A snapshot on the same hypervisor is only a checkpoint, so also ship it off-host."""
    backup()
    restore_test()
    ssh = ['runuser','-u','dev','--','ssh','-i',str(HOME / '.ssh/homeops-proxmox'),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=10','bingo@192.168.1.100']
    output = run([*ssh, 'sudo vzdump 160 --mode snapshot --compress zstd --storage local --quiet 0'], text=True)
    text = output.stdout + output.stderr
    candidates = re.findall(r"(/var/lib/vz/dump/vzdump-qemu-160-[0-9_\-]+\.vma\.zst)", text)
    if not candidates:
        raise RuntimeError('No completed VM archive found in vzdump output')
    archive = candidates[-1]
    source = subprocess.Popen([*ssh, 'sudo cat -- ' + archive], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        destination = subprocess.run(['restic','backup','--json','--host','dev-vm','--tag','dev-vm-system','--stdin','--stdin-filename','vm-160.vma.zst'], stdin=source.stdout, capture_output=True, text=True)
        source.stdout.close()
        source_code = source.wait()
        destination.check_returncode()
        if source_code != 0:
            raise RuntimeError('Incomplete VM archive stream')
        identifier = completed_snapshot(destination.stdout)
        # Checking the encrypted repository is required before admitting an update.
        restic('check')
        write_json(STATE / 'checkpoint.json', {'snapshot':identifier,'archive':archive,'completed_at':datetime.now(timezone.utc).isoformat()})
        return identifier
    finally:
        if source.poll() is None:
            source.kill()
            source.wait()


def checkpoint():
    ssh = ['runuser','-u','dev','--','ssh','-i','/home/dev/.ssh/homeops-proxmox','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','bingo@192.168.1.100']
    result = run([*ssh,'sudo vzdump 160 --mode snapshot --compress zstd --storage local --prune-backups keep-last=2'],text=True)
    output = result.stdout + '\n' + result.stderr
    matches = re.findall(r"(/var/lib/vz/dump/vzdump-qemu-160-[0-9_]+-[0-9_]+\.vma\.zst)",output)
    if not matches:
        raise RuntimeError('Cannot identify the completed VM archive')
    archive = matches[-1]
    with tempfile.TemporaryFile() as errors:
        source = subprocess.Popen([*ssh,'sudo cat -- '+archive],stdout=subprocess.PIPE,stderr=errors)
        try:
            result = subprocess.run(['restic','backup','--json','--host','dev-vm','--tag','dev-vm-system','--stdin','--stdin-filename','vm160.vma.zst'],stdin=source.stdout,capture_output=True,text=True)
            source.stdout.close()
            if source.wait() or result.returncode:
                raise RuntimeError('Full VM off-host backup failed')
            identifier = completed_snapshot(result.stdout)
        finally:
            if source.poll() is None:
                source.terminate(); source.wait()
    restic('check')
    write_json(STATE / 'checkpoint.json',{'snapshot':identifier,'archive':archive,'vm_id':160,'completed_at':datetime.now(timezone.utc).isoformat()})
    return identifier


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init','backup','restore-test','checkpoint','retention'])
    args = parser.parse_args()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE / 'backup.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.command == 'init':
            
            try:
                restic('cat','config')
            except subprocess.CalledProcessError:
                restic('init')
        elif args.command == 'retention':
            restic('forget','--host','dev-vm','--keep-within','7d','--keep-daily','30','--keep-weekly','8','--keep-monthly','6','--group-by','host,paths,tags','--prune')
        else:
            identifier = {'backup':backup,'restore-test':restore_test,'checkpoint':checkpoint}[args.command]()
            print(f'{args.command} completed: {identifier}')


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        # Never relay subprocess output: credentials and account paths can occur there.
        raise SystemExit(f'Development recovery operation failed ({type(error).__name__}); no update is permitted.') from None
