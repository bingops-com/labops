#!/usr/bin/python3
"""Controlled development releases: backup, VM checkpoint, install, health, rollback."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

# Release trees are immutable and their complete file sets are checksummed.
sys.dont_write_bytecode = True

BASE = Path('/opt/dev-vm')
STATE = Path('/var/lib/dev-vm')


def command(*args):
    subprocess.run(list(map(str,args)),check=True)


def installer(root):
    spec = importlib.util.spec_from_file_location('dev_install',root / 'runtime/dev_install.py')
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def system_change(before, after):
    for name in ['apt-tools.json','oci-tools.json']:
        def content(release):
            path=release / 'environment' / name
            return path.read_bytes() if path.exists() else b''
        if content(before)!=content(after):return True
    for name in ['configuration','runtime']:
        def files(release):
            return sorted((p.name,p.read_bytes()) for p in (release / name).glob('*') if p.is_file())
        if files(before)!=files(after):return True
    return False


def main():
    if os.geteuid() != 0:
        raise SystemExit('Use sudo devctl')
    os.umask(0o077)
    if len(sys.argv) < 2:
        raise SystemExit('Usage: devctl install|update|rollback RELEASE_ID; devctl status')
    action=sys.argv[1]
    STATE.mkdir(parents=True,exist_ok=True)
    if action == 'status':
        path=STATE / 'update.json'
        print(path.read_text() if path.exists() else '{"status":"not-updated"}')
        return
    if len(sys.argv) != 3 or not re.fullmatch('[a-f0-9]{64}',sys.argv[2]):
        raise SystemExit('Supply the exact content-addressed release ID')
    root=BASE / 'releases' / sys.argv[2]
    # Verify with the already-installed trusted code before importing release code.
    sys.path.insert(0,'/usr/local/lib/dev-vm')
    from dev_install import verify_release
    verify_release(root)
    current=(BASE / 'current').resolve() if (BASE / 'current').exists() else None
    if action == 'repair-initial':
        if (STATE / 'initial-acceptance.json').exists() or (STATE / 'tooling.json').exists():
            raise SystemExit('Initial repair cannot replace an accepted environment; use devctl update')
        # Explicit recovery of a failed first installation, before acceptance.
        # Preserve the previous tree and require all initial acceptance again.
        action='install';current=None
    if action == 'install-tools':
        tooling=BASE / 'tooling'
        if current or (tooling.exists() and tooling.resolve() != root):
            raise SystemExit('Tool bootstrap only accepts the same initial release; later updates require backups and devctl update')
        installer(root).install_tools(root)
        command('/usr/bin/env','MISE_DATA_DIR=/opt/dev-vm/mise','/usr/local/bin/mise','exec','--','/bin/bash',root / 'environment/check-tools.sh')
        (STATE / 'tooling.json').write_text(json.dumps({'release':root.name,'tools_verified':True,'backup_ready':False,'completed_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
        return
    if action == 'install':
        if current:
            if current != root:
                raise SystemExit('Already installed; use devctl update to create recovery checkpoints')
        if not current:
            if (BASE / 'tooling').exists() and (STATE / 'tooling.json').exists():
                command('systemctl','start','dev-backup-init.service')
                command('systemctl','start','dev-backup.service')
                command('systemctl','start','dev-restore-test.service')
                command('systemctl','start','dev-checkpoint.service')
            installer(root).install(root)
        else:
            installer(root).activate(root)
        command('/usr/local/sbin/dev-health')
        command('systemctl','start','dev-backup-init.service')
        command('systemctl','start','dev-backup.service')
        command('systemctl','start','dev-restore-test.service')
        command('systemctl','enable','--now','dev-backup.timer','dev-restore-test.timer')
        (STATE / 'initial-acceptance.json').write_text(json.dumps({'release':root.name,'backup_restore_verified':True,'completed_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
        return
    if action == 'update':
        if not (STATE / 'initial-acceptance.json').exists():
            raise SystemExit('Initial backup/restore acceptance is still running')
        if current == root: return
        command('systemd-run','--unit=dev-update','--collect','--property=Type=exec','/usr/local/sbin/devctl','_update',root.name)
        print('Update runs independently of SSH. Inspect sudo devctl status.')
        return
    with (STATE / 'update.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        if action == 'rollback':
            if not current: raise SystemExit('No active release')
            if system_change(current,root):
                raise SystemExit('System inputs differ; use the full VM recovery procedure')
            installer(root).activate(root)
            command('/usr/local/sbin/dev-health')
            return
        if action != '_update' or not current:
            raise SystemExit('Unknown action or missing initial installation')
        status={'target':root.name,'previous':current.name,'started_at':datetime.now(timezone.utc).isoformat(),'status':'backing-up'}
        def report(value):
            status['status']=value
            temp=STATE / 'update.new';temp.write_text(json.dumps(status,indent=2)+'\n');temp.replace(STATE / 'update.json')
        report('backing-up')
        adoption_started=False
        system_changed=system_change(current,root)
        try:
            command('systemctl','start','dev-backup.service')
            command('systemctl','start','dev-restore-test.service')
            if system_changed:
                report('checkpointing-system')
                command('systemctl','start','dev-checkpoint.service')
            report('installing')
            adoption_started=True
            installer(root).install(root)
            command('/usr/local/sbin/dev-health')
            report('healthy')
        except Exception:
            if not adoption_started:
                report('aborted')
                raise SystemExit('Recovery prerequisite failed; the active environment was not changed') from None
            report('failed')
            try:
                installer(current).activate(current)
                command('/usr/local/sbin/dev-health')
                report('system-restore-required' if system_changed else 'rolled-back')
            except Exception:
                report('system-restore-required')
            raise SystemExit('Update failed; inspect devctl status and the recovery runbook') from None


if __name__ == '__main__':
    main()
