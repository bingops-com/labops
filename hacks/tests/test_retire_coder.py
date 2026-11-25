"""Destructive retirement must reject incomplete migration evidence before kubectl."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('retire_coder', ROOT / 'hacks/retire-coder.py')
retire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retire)


class RetirementGuards(unittest.TestCase):
    def test_incomplete_evidence_never_contacts_cluster(self):
        example = json.loads((ROOT / 'environments/dev-vm/retirement-receipt.example.json').read_text())
        accepted = {key: True if isinstance(value, bool) else 'a' * 64 for key, value in example.items()}
        for missing in example:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                receipt = {**accepted, missing: example[missing]}
                path = Path(directory) / 'receipt.json'
                path.write_text(json.dumps(receipt))
                with patch.object(sys, 'argv', ['retire-coder', '--receipt', str(path), '--confirm', 'coder,coder-workspaces']), patch.object(retire.subprocess, 'run') as run:
                    with self.assertRaises(SystemExit):
                        retire.main()
                    run.assert_not_called()

    def test_existing_gitops_application_blocks_namespace_deletion(self):
        example = json.loads((ROOT / 'environments/dev-vm/retirement-receipt.example.json').read_text())
        accepted = {key: True if isinstance(value, bool) else 'a' * 64 for key, value in example.items()}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            path.write_text(json.dumps(accepted))
            with patch.object(sys, 'argv', ['retire-coder', '--receipt', str(path), '--confirm', 'coder,coder-workspaces']), patch.object(retire.subprocess, 'run') as run:
                run.return_value.stdout = 'application.argoproj.io/coder-labprod\n'
                with self.assertRaises(SystemExit):
                    retire.main()
                self.assertEqual(run.call_count, 1)
                self.assertNotIn('delete', run.call_args.args[0])


    def test_complete_evidence_deletes_only_the_two_exact_namespaces(self):
        example = json.loads((ROOT / 'environments/dev-vm/retirement-receipt.example.json').read_text())
        accepted = {key: True if isinstance(value, bool) else 'a' * 64 for key, value in example.items()}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'apps/gitops/clusters/labprod/kustomization.yaml'
            config.parent.mkdir(parents=True)
            config.write_text('resources: []\n')
            receipt = root / 'receipt.json'
            receipt.write_text(json.dumps(accepted))
            with patch.object(sys, 'argv', ['retire-coder', '--receipt', str(receipt), '--confirm', 'coder,coder-workspaces']), patch.object(retire, 'ROOT', root), patch.object(retire.subprocess, 'run') as run:
                run.return_value.stdout = ''
                retire.main()
                self.assertEqual(run.call_count, 3)
                self.assertEqual(run.call_args.args[0], [
                    'kubectl', '--context', 'labprod', 'delete', 'namespace',
                    'coder', 'coder-workspaces', '--ignore-not-found=true',
                    '--wait=true', '--timeout=10m'])


if __name__ == '__main__':
    unittest.main()
