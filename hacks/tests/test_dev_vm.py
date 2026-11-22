"""Offline acceptance: release tampering and actual encrypted SQLite backup/restore."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock
from contextlib import closing

ROOT=Path(__file__).resolve().parents[2]
FILES=ROOT / 'ansible/roles/dev_vm/files'


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class RecoveryTest(unittest.TestCase):
    def test_sqlite_snapshot_contains_committed_wal_changes(self):
        backup=load('backup_sqlite',FILES / 'dev_backup.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);home=root / 'home';(home / '.codex').mkdir(parents=True)
            connection=sqlite3.connect(home / '.codex/state.sqlite')
            connection.execute('PRAGMA journal_mode=WAL');connection.execute('CREATE TABLE test(value)');connection.execute('INSERT INTO test VALUES(42)');connection.commit()
            try:
                self.assertEqual(backup.snapshot_sqlite(home,root / 'snapshot'),['.codex/state.sqlite'])
                with closing(sqlite3.connect(root / 'snapshot/.codex/state.sqlite')) as restored:
                    self.assertEqual(restored.execute('SELECT value FROM test').fetchone(),(42,))
            finally:connection.close()

    @unittest.skipUnless(shutil.which('restic'),'restic is required for real recovery acceptance')
    def test_real_encrypted_backup_and_isolated_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);home=root / 'home';state=root / 'state';(home / '.codex').mkdir(parents=True)
            (home / 'project.txt').write_text('uncommitted fixture')
            with closing(sqlite3.connect(home / '.codex/state.sqlite')) as connection:
                connection.execute('CREATE TABLE test(value)');connection.execute('INSERT INTO test VALUES(42)');connection.commit()
            env={**os.environ,'RESTIC_REPOSITORY':str(root / 'repository'),'RESTIC_PASSWORD':'fixture-only-not-a-real-secret','DEV_VM_HOME':str(home),'DEV_VM_STATE':str(state),'DEV_VM_TEST':'1'}
            for action in ['init','backup','restore-test']:
                result=subprocess.run(['python3',str(FILES / 'dev_backup.py'),action],env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            status=json.loads((state / 'backup.json').read_text())
            listing=subprocess.run(['restic','ls',status['snapshot']],env=env,capture_output=True,text=True,check=True).stdout
            self.assertIn(str(state / 'sqlite/.codex/state.sqlite'),listing)
            self.assertNotIn(str(home / '.codex/state.sqlite'),listing)
            self.assertEqual((home / 'project.txt').read_text(),'uncommitted fixture')

    def test_renovate_regex_covers_every_native_tool(self):
        config=json.loads((ROOT / 'renovate.json').read_text())
        manager=next(m for m in config['customManagers'] if m.get('datasourceTemplate')=='deb')
        text=(ROOT / 'environments/dev-vm/apt-tools.json').read_text()
        pattern=manager['matchStrings'][0].replace('(?<','(?P<')
        records=[match.groupdict() for match in re.finditer(pattern,text)]
        expected=json.loads(text)
        self.assertEqual({r['depName'] for r in records},{r['name'] for r in expected})
        self.assertIn('mise',config['enabledManagers']);self.assertIn('pip-compile',config['enabledManagers'])

    def test_pinned_tool_versions_match_their_committed_locks(self):
        import tomllib
        environment=ROOT / 'environments/dev-vm'
        declared=tomllib.loads((environment / 'mise.toml').read_text())['tools']
        locked=tomllib.loads((environment / 'mise.lock').read_text())['tools']
        self.assertEqual(set(declared),set(locked))
        for name,value in declared.items():
            version=value if isinstance(value,str) else value['version']
            record=next(record for record in locked[name] if record['version']==version)
            options={} if isinstance(value,str) else {k:v for k,v in value.items() if k!='version'}
            for key,expected in options.items():
                actual=record.get('options',{}).get(key)
                if isinstance(expected,(list,dict)) and isinstance(actual,str):actual=json.loads(actual)
                self.assertEqual(actual,expected,f'{name}: locked option {key}')
            if 'aube' in record:
                sidecar=environment / record['aube']['path']
                self.assertTrue((sidecar / 'aube-lock.yaml').is_file(),name)
                self.assertTrue((sidecar / 'package.json').is_file(),name)
        requirements=dict(re.findall(r'^([A-Za-z0-9_.-]+)==(\S+)',(environment / 'requirements.txt').read_text(),re.MULTILINE))
        for name,version in re.findall(r'^([A-Za-z0-9_.-]+)==(\S+)',(environment / 'requirements.in').read_text(),re.MULTILINE):
            self.assertEqual(requirements.get(name),version,name)

    def test_renovate_covers_the_native_oci_tool_and_its_own_runner(self):
        config=json.loads((ROOT / 'renovate.json').read_text())
        for filename,package in [('oci-tools.json','aquasec/trivy'),('automation.json','ghcr.io/renovatebot/renovate')]:
            manager=next(m for m in config['customManagers'] if any(filename.removesuffix('.json') in p for p in m['managerFilePatterns']))
            pattern=manager['matchStrings'][0].replace('(?<','(?P<')
            records=[m.groupdict() for m in re.finditer(pattern,(ROOT / 'environments/dev-vm' / filename).read_text())]
            self.assertEqual([m['depName'] for m in records],[package])
            self.assertRegex(records[0]['currentDigest'],r'^sha256:[a-f0-9]{64}$')

    def test_additive_sso_bootstrap_preserves_coder_and_applications(self):
        import yaml
        cutover=load('cutover',ROOT / 'hacks/prepare-dev-cutover.py')
        changes=cutover.prepare('100.64.0.160','bootstrap')
        self.assertTrue(set(changes).issubset({'apps/platform/authentik/blueprint.yaml'}))
        if not changes:
            return
        before,after=changes['apps/platform/authentik/blueprint.yaml']
        self.assertEqual(yaml.safe_load(before)['data']['coder.yaml'],yaml.safe_load(after)['data']['coder.yaml'])
        self.assertIn('id: dev-proxy-provider',after)
        self.assertIn('            - !KeyOf rom-request-proxy-provider',after)
        self.assertIn('            - !KeyOf dev-proxy-provider',after)

    def test_retirement_keeps_parallel_ssh_dns_and_uses_the_active_dns_owner(self):
        cutover=load('cutover_retirement',ROOT / 'hacks/prepare-dev-cutover.py')
        changes=cutover.prepare('100.64.0.160','retire')
        self.assertNotIn('terraform/tailscale-dns/dev.tf',changes)
        _,network=changes['terraform/network/dns.tf']
        self.assertIn('domain = "code.lab.bingo"',network)
        self.assertIn('address = "100.64.0.160"',network)
        self.assertIn('domain = "lab.bingo"',network)
        _,dns=changes['apps/platform/private-dns/labprod/configmap.yaml']
        self.assertIn('code.lab.bingo:53',dns)
        self.assertIn('30 IN A 100.64.0.160',dns)
        self.assertNotIn('coder.lab.bingo:53',dns)

    def test_failed_backup_prevents_any_adoption_or_rollback(self):
        controller=load('update_controller',FILES / 'devctl.py')
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);state=base / 'state';current=base / 'releases' / ('a'*64);target=base / 'releases' / ('b'*64)
            for path in [current,target]:
                (path / 'environment').mkdir(parents=True)
                (path / 'configuration').mkdir()
                (path / 'environment/apt-tools.json').write_text('[]')
            (base / 'current').symlink_to(current)
            controller.BASE=base;controller.STATE=state
            trusted=mock.Mock();trusted.verify_release.return_value=target.name
            implementation=mock.Mock()
            error=subprocess.CalledProcessError(1,['systemctl','start','dev-backup.service'])
            import sys
            with mock.patch.dict(sys.modules,{'dev_install':trusted}), mock.patch.object(sys,'argv',['devctl','_update',target.name]), mock.patch.object(controller.os,'geteuid',return_value=0), mock.patch.object(controller,'installer',return_value=implementation), mock.patch.object(controller,'command',side_effect=error):
                with self.assertRaisesRegex(SystemExit,'active environment was not changed'):
                    controller.main()
            implementation.install.assert_not_called();implementation.activate.assert_not_called()
            self.assertEqual(json.loads((state / 'update.json').read_text())['status'],'aborted')

    def test_global_binary_or_runtime_update_requires_a_successful_vm_checkpoint(self):
        for changed in ['oci','runtime']:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                controller=load('checkpoint_controller_'+changed,FILES / 'devctl.py')
                base=Path(directory);current=base / 'releases' / ('a'*64);target=base / 'releases' / ('b'*64)
                for path in [current,target]:
                    (path / 'environment').mkdir(parents=True);(path / 'configuration').mkdir();(path / 'runtime').mkdir()
                    (path / 'environment/apt-tools.json').write_text('[]')
                    (path / 'environment/oci-tools.json').write_text('[]')
                if changed=='oci':(target / 'environment/oci-tools.json').write_text('["new-global-binary"]')
                else:(target / 'runtime/dev_install.py').write_text('new privileged installation behavior')
                (base / 'current').symlink_to(current)
                controller.BASE=base;controller.STATE=base / 'state';trusted=mock.Mock();implementation=mock.Mock()
                def command(*args):
                    if args==('systemctl','start','dev-checkpoint.service'):raise subprocess.CalledProcessError(1,list(args))
                import sys
                with mock.patch.dict(sys.modules,{'dev_install':trusted}),mock.patch.object(sys,'argv',['devctl','_update',target.name]),mock.patch.object(controller.os,'geteuid',return_value=0),mock.patch.object(controller,'installer',return_value=implementation),mock.patch.object(controller,'command',side_effect=command):
                    with self.assertRaisesRegex(SystemExit,'active environment was not changed'):controller.main()
                implementation.install.assert_not_called();implementation.activate.assert_not_called()
                self.assertEqual((base / 'current').resolve(),current)

    def test_tool_bootstrap_cannot_replace_an_initialized_tool_release(self):
        controller=load('guarded_tool_bootstrap',FILES / 'devctl.py')
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);previous=base / 'releases' / ('a'*64);target=base / 'releases' / ('b'*64)
            previous.mkdir(parents=True);target.mkdir()
            (base / 'tooling').symlink_to(previous)
            controller.BASE=base;controller.STATE=base / 'state'
            trusted=mock.Mock();implementation=mock.Mock()
            import sys
            with mock.patch.dict(sys.modules,{'dev_install':trusted}), mock.patch.object(sys,'argv',['devctl','install-tools',target.name]), mock.patch.object(controller.os,'geteuid',return_value=0), mock.patch.object(controller,'installer',return_value=implementation):
                with self.assertRaisesRegex(SystemExit,'later updates require backups'):
                    controller.main()
            implementation.install_tools.assert_not_called()
            self.assertEqual((base / 'tooling').resolve(),previous)

    def test_live_copy_never_certifies_migration_or_transfers_terraform_ownership(self):
        migration=load('live_migration',ROOT / 'hacks/migrate-dev-home.py')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);home=root / 'source';home.mkdir();project=home / 'project.txt';project.write_text('still running')
            migration.ROOT=root
            def run(command,**kwargs):
                return subprocess.CompletedProcess(command,0,'changed-during-copy' if '--dry-run' in command else '', '')
            import sys
            args=['migrate-dev-home','--host','100.64.0.160','--identity',str(root/'key'),'--source',str(home),'--live-copy']
            with mock.patch.object(sys,'argv',args),mock.patch.object(migration.subprocess,'run',side_effect=run):migration.main()
            receipt=json.loads((root / '.runtime/dev-vm/live-copy.json').read_text())
            self.assertFalse(receipt['data_verified']);self.assertTrue(receipt['provisional']);self.assertTrue(receipt['source_changes_observed'])
            self.assertEqual(receipt['terraform_primary'],'coder');self.assertTrue(project.is_file())
            self.assertFalse((root / '.runtime/dev-vm/migration.json').exists())

    def test_release_content_changes_are_detected(self):
        builder=load('builder',ROOT / 'hacks/build-dev-release.py')
        installer=load('installer',FILES / 'dev_install.py')
        with tempfile.TemporaryDirectory() as directory:
            import tarfile
            root=Path(directory);app=root / 'app';(app / 'workspace').mkdir(parents=True);(app / 'web').mkdir()
            for name in ['server.mjs','package.json','workspace/agent.py','web/index.html']:(app / name).write_text('fixture')
            identifier,archive=builder.build(app,root / 'artifacts')
            with tarfile.open(archive) as tar:tar.extractall(root / 'releases',filter='data')
            release=root / 'releases' / identifier
            self.assertEqual(installer.verify_release(release),identifier)
            controller=load('release_controller',FILES / 'devctl.py')
            controller.installer(release)
            self.assertEqual(installer.verify_release(release),identifier)
            (release / 'app/server.mjs').write_text('tampered')
            with self.assertRaises(ValueError):installer.verify_release(release)


if __name__=='__main__':unittest.main()
