"""Offline access-control and archive-retention tests; no real account inputs."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor("!KeyOf", lambda loader, node: loader.construct_scalar(node))
BlueprintLoader.add_constructor("!Find", lambda loader, node: loader.construct_sequence(node))


class NotesTests(unittest.TestCase):
    def test_only_active_owner_can_access_both_sso_layers(self):
        cm = yaml.safe_load((REPO / "apps/platform/authentik/blueprint.yaml").read_text())
        bp = yaml.load(cm["data"]["romm.yaml"], Loader=BlueprintLoader)
        entries = {item.get("id"): item for item in bp["entries"]}
        expression = entries["notes-owner-policy"]["attrs"]["expression"]
        code = "def evaluate(request):\n" + "\n".join("    " + line for line in expression.splitlines())
        scope = {}
        exec(compile(code, "notes-owner-policy", "exec"), scope)
        for username, active, member, expected in [("bingops", True, True, True),
                                                  ("bingops", False, True, False),
                                                  ("bingops", True, False, False),
                                                  ("another-user", True, True, False)]:
            groups = SimpleNamespace(filter=lambda **_kw: SimpleNamespace(exists=lambda: member))
            user = SimpleNamespace(username=username, is_active=active, is_authenticated=True,
                                   all_groups=lambda: groups)
            self.assertEqual(scope["evaluate"](SimpleNamespace(user=user)), expected)
        for target in ["notes-application", "notes-oidc-application"]:
            bindings = [x for x in bp["entries"] if x["model"] == "authentik_policies.policybinding"
                        and x.get("attrs", {}).get("target") == target]
            self.assertEqual(len(bindings), 1)
            self.assertEqual(bindings[0]["attrs"]["policy"], "notes-owner-policy")
        provider = entries["notes-oidc-provider"]["attrs"]
        self.assertEqual(provider["client_type"], "public")
        self.assertEqual(provider["grant_types"], ["authorization_code"])
        self.assertEqual(provider["redirect_uris"], [{"matching_mode": "strict", "url": "https://notes.lab.bingo/oauth/callback"}])
        outpost = next(x for x in bp["entries"] if x["model"] == "authentik_outposts.outpost")
        self.assertIn("rom-request-proxy-provider", outpost["attrs"]["providers"])
        self.assertIn("notes-proxy-provider", outpost["attrs"]["providers"])
        config = json.loads((ROOT / "base/config.json").read_text())
        self.assertFalse(config["auth"]["allowSignup"])
        self.assertEqual(config["oauth"]["providers.oidc"]["clientId"], provider["client_id"])

    @unittest.skipUnless(shutil.which("rclone"), "requires rclone")
    def test_backup_retention_uses_archive_name_and_preserves_unknown_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backup, remote = root / "backup", root / "remote"
            backup.mkdir()
            remote.mkdir()
            now = datetime.now(timezone.utc)
            stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
            old = (now - timedelta(days=15)).strftime("%Y-%m-%dT%H-%M-%SZ") + ".tar.gz"
            recent = (now - timedelta(days=13)).strftime("%Y-%m-%dT%H-%M-%SZ") + ".tar.gz"
            (backup / "stamp").write_text(stamp)
            (backup / "affine.tar.gz").write_bytes(b"TEST_ONLY_ARCHIVE")
            for name in [old, recent, "unknown.tar.gz", "2026-02-30T00-00-00Z.tar.gz"]:
                (remote / name).write_bytes(b"TEST_ONLY_OLD_DATA")
            old_time = (now - timedelta(days=60)).timestamp()
            os.utime(remote / recent, (old_time, old_time))
            script = (ROOT / "base/backup-files.sh").read_text()
            script = script.replace("r2:bingops-cnpg-labprod/affine-files/snapshots", str(remote))
            script = script.replace("/backup", str(backup))
            self.assertNotIn("r2:", script)
            result = subprocess.run(["/bin/sh", "-ec", script], capture_output=True, text=True,
                                    env={**os.environ, "RCLONE_CONFIG": "/dev/null"}, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((remote / old).exists())
            for name in [recent, "unknown.tar.gz", "2026-02-30T00-00-00Z.tar.gz"]:
                self.assertTrue((remote / name).exists())
            self.assertEqual((remote / (stamp + ".tar.gz")).read_bytes(), b"TEST_ONLY_ARCHIVE")
            # Failed staging must not enter archive cleanup.
            (remote / old).write_bytes(b"TEST_ONLY_RECOVERY")
            (backup / "affine.tar.gz").unlink()
            result = subprocess.run(["/bin/sh", "-ec", script], capture_output=True, text=True,
                                    env={**os.environ, "RCLONE_CONFIG": "/dev/null"}, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((remote / old).exists())


if __name__ == "__main__":
    unittest.main()
