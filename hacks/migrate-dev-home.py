#!/usr/bin/env python3
"""Copy the operator home without deleting source data; live copies remain provisional."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('dev_backup',ROOT / 'ansible/roles/dev_vm/files/dev_backup.py')
backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',required=True,help='VM Tailscale IP or verified MagicDNS name')
    parser.add_argument('--identity',type=Path,required=True)
    parser.add_argument('--proxy-jump',help='Optional trusted Proxmox SSH jump, connecting to the VM tailnet IP')
    parser.add_argument('--source',type=Path,default=Path.home())
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--confirm-quiesced',action='store_true')
    mode.add_argument('--live-copy',action='store_true',help='Provisional copy while Coder remains primary; requires a final quiesced sync')
    parser.add_argument('--known-hosts',type=Path,help='Explicit verified host trust file')
    args=parser.parse_args()
    if args.host.startswith('-') or any(c.isspace() for c in args.host):
        raise SystemExit('Invalid destination')
    ssh=['ssh','-i',str(args.identity.expanduser()),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes']
    if args.proxy_jump: ssh+=['-J',args.proxy_jump]
    if args.known_hosts:ssh+=['-o','UserKnownHostsFile='+str(args.known_hosts.resolve())]
    destination='dev@'+args.host
    def run(command):
        result=subprocess.run(command,capture_output=True,text=True)
        if result.returncode and not (args.live_copy and command[0]=='rsync' and result.returncode==24):
            result.check_returncode()
        return result
    # The account identity and paths must be checked before transmitting credentials.
    run([*ssh,destination,"test \"$(id -u)\" = 1000 && test \"$HOME\" = /home/dev && test -d /home/dev/projects"])
    with tempfile.TemporaryDirectory(prefix='dev-home-sqlite-') as directory:
        os.chmod(directory,0o700)
        databases=backup.snapshot_sqlite(args.source.resolve(),Path(directory))
        excludes=['/.cache/coder/**','/.local/share/mise/**','/.codex/**/*.sqlite*','/.codex/**/*.db*','/.codex/*.sqlite*','/.codex/*.db*','/.ssh/authorized_keys','/.ssh/ssh_host_*','/.config/lab/sshd*','/.config/lab/gallery*','**/.terraform/providers/**','**/.terraform/modules/**','**/.git/index.lock','**/.git/*.lock','**/.terraform.tfstate.lock.info','/.ansible/tmp/**']
        command=['rsync','-aH','--no-owner','--no-group','--chmod=Dgo-w','--protect-args','-e',shlex.join(ssh)]
        for pattern in excludes:command+=['--exclude',pattern]
        source=str(args.source.resolve())+'/'
        target=destination+':/home/dev/'
        run([*command,source,target])
        # Dry-run differences are captured, never printed into logs or chat.
        difference=run([*command,'--dry-run','--checksum','--itemize-changes',source,target]).stdout
        if difference.strip() and not args.live_copy:raise RuntimeError('Source changed during transfer; quiesce it and repeat')
        run(['rsync','-a','--no-owner','--no-group','--chmod=Dgo-w','-e',shlex.join(ssh),directory+'/',target])
    receipt={'data_verified':not args.live_copy,'provisional':args.live_copy,'source_changes_observed':bool(difference.strip()),'sqlite_databases':len(databases),'terraform_primary':'coder' if args.live_copy else 'dev-vm','completed_at':datetime.now(timezone.utc).isoformat()}
    runtime=ROOT / '.runtime/dev-vm';runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=runtime / ('live-copy.json' if args.live_copy else 'migration.json');path.write_text(json.dumps(receipt,indent=2)+'\n');path.chmod(0o600)
    print('Provisional home copy completed; Coder remains primary. Final quiesced synchronization is required.' if args.live_copy else 'Home transfer verified. Start Terraform only from the VM after the final cutover.')


if __name__=='__main__':
    os.umask(0o077)
    try:main()
    except (subprocess.CalledProcessError,OSError,RuntimeError) as error:
        raise SystemExit(f'Migration stopped ({type(error).__name__}); no source data was deleted.') from None
