"""Exercise credential transport with fake clients and disposable directories."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("provision", Path(__file__).parents[1] / "provision-homeops-dev.py")
provision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provision)
FAKE = "TEST_ONLY_NOT_A_REAL_CREDENTIAL"


class CredentialTransport(unittest.TestCase):
    def test_selected_contexts_are_renamed_without_disclosing_data(self):
        def fake_run(arguments, input_data=None):
            context = arguments[2]
            return json.dumps({"contexts": [{"name": context, "context": {"cluster": "default", "user": "default"}}], "clusters": [{"name": "default", "cluster": {"server": "https://example.invalid"}}], "users": [{"name": "default", "user": {"token": FAKE}}]}).encode()
        with patch.object(provision, "run", side_effect=fake_run):
            result = provision.kubeconfig(("labmgmt", "labprod"))
        self.assertEqual([item["name"] for item in result["contexts"]], ["labmgmt", "labprod"])
        self.assertEqual(len({item["name"] for item in result["users"]}), 2)

    def install(self, directory):
        payload = {".kube/homeops-config": {"credential": FAKE}}
        script = provision.INSTALL.replace("/home/coder", str(directory))
        result = subprocess.run([sys.executable, "-c", script], input=json.dumps(payload), capture_output=True, text=True)
        self.assertNotIn(FAKE, result.stdout + result.stderr)
        return result

    def test_private_atomic_install_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertEqual(self.install(home).returncode, 0)
            self.assertEqual(self.install(home).returncode, 0)
            target = home / ".kube/homeops-config"
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual((home / ".kube/config").resolve(), target)

    def test_existing_default_configuration_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".kube").mkdir()
            default = home / ".kube/config"
            default.write_text("existing operator configuration")
            self.assertEqual(self.install(home).returncode, 0)
            self.assertEqual(default.read_text(), "existing operator configuration")

    def test_symlinked_credential_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".kube").mkdir()
            elsewhere = home / "elsewhere"
            elsewhere.write_text("preserved")
            (home / ".kube/homeops-config").symlink_to(elsewhere)
            self.assertNotEqual(self.install(home).returncode, 0)
            self.assertEqual(elsewhere.read_text(), "preserved")


if __name__ == "__main__":
    unittest.main()
