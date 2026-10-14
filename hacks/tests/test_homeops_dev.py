"""Exercise credential transport with fake clients and disposable directories."""
import importlib.util
import base64
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

    def install(self, directory, payload=None):
        if payload is None:
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
            self.assertEqual(json.loads(target.read_text()), {"credential": FAKE})
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

    def test_binary_file_is_private_and_conflict_preserves_all_files(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            payload = {".codex/auth.json": {"_file_base64": base64.b64encode(FAKE.encode()).decode()}}
            self.assertEqual(self.install(home, payload).returncode, 0)
            self.assertEqual(self.install(home, payload).returncode, 0)
            target = home / ".codex/auth.json"
            self.assertEqual(target.read_text(), FAKE)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            target.write_text("existing session")
            payload = {".kube/homeops-config": {"credential": FAKE}, **payload}
            self.assertNotEqual(self.install(home, payload).returncode, 0)
            self.assertEqual(target.read_text(), "existing session")
            self.assertFalse((home / ".kube").exists())

    def test_parent_symlink_and_path_escape_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            outside = home / "outside"
            outside.mkdir()
            (home / ".config").symlink_to(outside)
            payload = {".config/gh/hosts.yml": {"_file_base64": base64.b64encode(FAKE.encode()).decode()}}
            self.assertNotEqual(self.install(home, payload).returncode, 0)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertNotEqual(self.install(home, {"../escape": {"credential": FAKE}}).returncode, 0)

    def test_state_and_sessions_require_explicit_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            stack = home / "labops/terraform/proxmox"
            stack.mkdir(parents=True)
            (stack / "credentials.auto.tfvars").write_text(FAKE)
            (stack / "terraform.tfstate").write_text(FAKE)
            (home / ".codex").mkdir()
            (home / ".codex/auth.json").write_text(FAKE)
            selected = provision.operator_files(home, home / "labops")
            self.assertEqual(set(selected), {"projects/labops/terraform/proxmox/credentials.auto.tfvars"})
            selected = provision.operator_files(home, home / "labops", cli_sessions=True, terraform_state=True)
            self.assertIn("projects/labops/terraform/proxmox/terraform.tfstate", selected)
            self.assertIn(".codex/auth.json", selected)
            self.assertNotIn(".ssh/id_rsa", selected)

    def test_project_inputs_require_checkout_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            payload = {".kube/homeops-config": {"credential": FAKE}, "projects/labops/terraform/proxmox/terraform.tfstate": {"_file_base64": base64.b64encode(FAKE.encode()).decode()}}
            self.assertNotEqual(self.install(home, payload).returncode, 0)
            self.assertFalse((home / ".kube").exists())
            (home / "projects/labops/.git").mkdir(parents=True)
            self.assertEqual(self.install(home, payload).returncode, 0)
            self.assertEqual((home / "projects/labops/terraform/proxmox/terraform.tfstate").stat().st_mode & 0o777, 0o600)

    def test_ssh_default_links_configuration_instead_of_private_key(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            encode = lambda value: {"_file_base64": base64.b64encode(value.encode()).decode()}
            payload = {".ssh/homeops-proxmox": encode(FAKE), ".ssh/homeops-config": encode("Host proxmox\n")}
            self.assertEqual(self.install(home, payload).returncode, 0)
            self.assertEqual((home / ".ssh/config").resolve(), home / ".ssh/homeops-config")


if __name__ == "__main__":
    unittest.main()
