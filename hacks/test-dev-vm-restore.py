#!/usr/bin/env python3
"""Restore a local VM160 archive into a disconnected rehearsal VM; never replace a VM."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

ROOT=Path(__file__).resolve().parent.parent

# Run only against the stopped, restored copy. Debian's cloud-init network
# stage can hold sysinit (and the guest agent) indefinitely without a NIC.
OFFLINE_PREPARATION='''import json,pathlib,subprocess,sys,tempfile
device=sys.argv[1]
def run(*args):return subprocess.run(args,check=True,capture_output=True,text=True).stdout.strip()
loop=run('losetup','--find','--show','--partscan',device)
try:
 run('udevadm','settle')
 info=json.loads(run('lsblk','--json','--tree','--output','PATH,FSTYPE',loop))
 partitions=info['blockdevices'][0].get('children',[])
 roots=[p['path'] for p in partitions if p.get('fstype')=='ext4']
 if len(roots)!=1:raise RuntimeError('Expected one Debian root filesystem')
 with tempfile.TemporaryDirectory(prefix='dev-restore-offline-') as directory:
  run('mount','-o','nosuid,nodev,noexec',roots[0],directory)
  try:
   root=pathlib.Path(directory)
   (root/'etc/cloud/cloud-init.disabled').touch()
   for name in ['cloud-init-network.service','systemd-networkd-wait-online.service','tailscaled.service','dev-bootstrap.service','dev-backup.service','dev-backup-init.service','dev-backup.timer','dev-restore-test.service','dev-restore-test.timer','dev-checkpoint.service']:
    unit=root/'etc/systemd/system'/name
    unit.unlink(missing_ok=True);unit.symlink_to('/dev/null')
  finally:run('umount',directory)
finally:run('losetup','--detach',loop)
print('Offline-only cloud/network/backup units masked in the restored copy.')
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True)
    parser.add_argument('--vm-id',type=int,default=161)
    parser.add_argument('--identity',type=Path,default=Path.home()/'.ssh/homeops-proxmox')
    parser.add_argument('--proxmox',default='bingo@192.168.1.100')
    parser.add_argument('--receipt',type=Path,default=ROOT/'.runtime/dev-vm/system-restore.json')
    parser.add_argument('--resume',action='store_true',help='Resume only the stopped, disconnected copy recorded by this helper')
    args=parser.parse_args()
    if args.vm_id not in range(161,170):raise ValueError('Use a reserved development rehearsal ID, 161–169')
    if not re.fullmatch(r'/var/lib/vz/dump/vzdump-qemu-160-[0-9_]+-[0-9_]+\.vma\.zst',args.archive):raise ValueError('Expected a local VM160 archive')
    ssh=['ssh','-i',str(args.identity),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',args.proxmox]
    def remote(*command):
        result=subprocess.run([*ssh,shlex.join(command)],capture_output=True,text=True)
        if result.returncode:
            args.receipt.parent.mkdir(parents=True,exist_ok=True)
            log=args.receipt.with_suffix('.log')
            log.write_text(result.stdout+'\n'+result.stderr);log.chmod(0o600)
            raise RuntimeError('Proxmox rehearsal operation failed; inspect the private rehearsal log')
        return result.stdout
    def guest(vmid,script):
        result=json.loads(remote('sudo','qm','guest','exec',str(vmid),'--timeout','180','--','python3','-c',script))
        if result.get('exitcode')!=0:
            args.receipt.parent.mkdir(parents=True,exist_ok=True)
            log=args.receipt.with_suffix('.log')
            log.write_text(json.dumps(result));log.chmod(0o600)
            raise RuntimeError('Restored guest verification failed; inspect the private rehearsal log')
        return json.loads(result['out-data'])
    owned=args.receipt.with_suffix('.owned.json')
    identity={'source_vm_id':160,'rehearsal_vm_id':args.vm_id,'archive':args.archive}
    if args.resume:
        if not owned.exists() or json.loads(owned.read_text())!=identity:raise ValueError('Missing matching rehearsal ownership receipt')
        if 'status: stopped' not in remote('sudo','qm','status',str(args.vm_id)):raise ValueError('Stop the rehearsal before resuming')
        config=remote('sudo','qm','config',str(args.vm_id))
        if 'name: dev-restore-test\n' not in config or re.search(r'^(net|hostpci|usb)\d+:',config,re.MULTILINE):raise ValueError('Existing copy is not the disconnected rehearsal')
    else:
        # No --force or implicit existing-VM adoption.
        remote('sudo','test','!','-e',f'/etc/pve/qemu-server/{args.vm_id}.conf')
    print('Verifying local VM160 archive.',flush=True)
    remote('sudo','zstd','-tq',args.archive)
    files=['projects/AGENTS.md','.codex/auth.json','.kube/config','.talos/config','.ssh/homeops-proxmox','.bash_aliases']
    probe="import hashlib,json;from pathlib import Path;root=Path('/home/dev');names="+repr(files)+";print(json.dumps({n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names if (root/n).is_file()}))"
    expected=guest(160,probe)
    if len(expected)!=len(files):raise RuntimeError('Expected operator files are missing; rehearsal was not created')
    if not args.resume:
        print('Restoring into an unused rehearsal ID.',flush=True)
        remote('sudo','qmrestore',args.archive,str(args.vm_id),'--storage','local-lvm','--unique','1','--pool','Development')
    # Never boot a second copy of the enrolled tailnet identity with a NIC.
    config=remote('sudo','qm','config',str(args.vm_id))
    devices=[line.split(':',1)[0] for line in config.splitlines() if re.match(r'^(net|hostpci|usb)\d+:',line)]
    if any(not name.startswith('net') for name in devices):raise RuntimeError('Unexpected passthrough device; rehearsal was not booted')
    for name in devices:remote('sudo','qm','set',str(args.vm_id),'--delete',name)
    remote('sudo','qm','set',str(args.vm_id),'--name','dev-restore-test','--onboot','0')
    if re.search(r'^(net|hostpci|usb)\d+:',remote('sudo','qm','config',str(args.vm_id)),re.MULTILINE):raise RuntimeError('Rehearsal is not isolated')
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    owned.write_text(json.dumps(identity)+'\n');owned.chmod(0o600)
    volume=re.search(r'^scsi0: ([^,\n]+)',remote('sudo','qm','config',str(args.vm_id)),re.MULTILINE)[1]
    device=remote('sudo','pvesm','path',volume).strip()
    if not device.startswith('/dev/'):raise ValueError('Expected a dedicated restored block volume')
    print('Preparing the stopped copy for a boot without network dependencies.',flush=True)
    remote('sudo','python3','-c',OFFLINE_PREPARATION,device)
    print('Booting the disconnected copy; original VM stays running.',flush=True)
    remote('sudo','qm','start',str(args.vm_id))
    try:
        deadline=time.monotonic()+240
        while True:
            try:
                actual=guest(args.vm_id,probe)
                break
            except RuntimeError:
                if time.monotonic()>deadline:raise
                time.sleep(5)
        if len(expected)!=len(files) or actual!=expected:raise RuntimeError('Restored operator files differ; no recovery acceptance')
        script="""import json,subprocess,pathlib,sys
result=subprocess.run(['runuser','-u','dev','--','bash','-lc','homeops-dev-check'],capture_output=True,text=True,timeout=120)
if result.returncode:
 print(result.stdout+'\\n'+result.stderr,file=sys.stderr)
 raise SystemExit('Native tool checks failed')
root=pathlib.Path('/home/dev/projects')
print(json.dumps({'tools_verified':True,'project_directories':sum(p.is_dir() for p in root.iterdir()),'agents_preserved':(root/'AGENTS.md').is_file()}))
"""
        checks=guest(args.vm_id,script)
        if not checks['agents_preserved'] or checks['project_directories']<1:raise RuntimeError('Restored projects are missing')
        args.receipt.parent.mkdir(parents=True,exist_ok=True)
        args.receipt.write_text(json.dumps({**identity,'system_restore_verified':True,'network_isolated':True,'offline_preparation':True,'selected_files_matched':len(expected),**checks,'completed_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n')
        args.receipt.chmod(0o600)
        print('Isolated boot, native tools and restored operator files verified.',flush=True)
    finally:
        remote('sudo','qm','stop',str(args.vm_id))
        print('Rehearsal VM stopped and retained; original VM unchanged.',flush=True)


if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError) as error:raise SystemExit(str(error)) from None
    except Exception as error:raise SystemExit(f'VM restoration rehearsal failed ({type(error).__name__}); inspect private host state before retrying.') from None
