import base64
import hashlib
import http.server
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[4]


def load(filename):
    spec = importlib.util.spec_from_file_location(filename, root / "hacks" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


link = load("link-game-accounts.py")
services = load("arcade-pg-services.py")


class Helpers(unittest.TestCase):
    def test_redirect_does_not_forward_password(self):
        paths = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                paths.append(self.path)
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(302)
                self.send_header("Location", "/must-not-receive-password")
                self.end_headers()

            def do_GET(self):
                paths.append(self.path)
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(ValueError):
                link.authenticate(f"http://127.0.0.1:{server.server_port}", "Synthetic", "synthetic password", "games_session", fixture=True)
            self.assertEqual(paths, ["/api/login"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_arbitrary_origins_are_refused_before_network(self):
        for origin in ("https://example.invalid", "http://games.lab.bingo", "https://games.lab.bingo.evil.invalid", "https://games.lab.bingo/path"):
            with self.assertRaises(ValueError):
                link.authenticate(origin, "Synthetic", "synthetic password", "games_session")

    def test_proof_is_private_and_cannot_overwrite_symlink(self):
        digest = hashlib.sha256(b"synthetic session").hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "proof.csv"
            link.save_proof(target, "Synthetic", digest, digest)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            alias = Path(directory) / "alias.csv"
            alias.symlink_to(target)
            with self.assertRaises(FileExistsError):
                link.save_proof(alias, "Synthetic", digest, digest)

    def test_generated_libpq_files_are_private_and_use_only_restored_secrets(self):
        calls = []

        def kubectl(command, **kwargs):
            calls.append(command)
            secret = command[5]
            user = "games" if secret.startswith("arcade-games-restore-") else "slots" if secret.startswith("arcade-slots-restore-") else "arcade"
            data = {"username": base64.b64encode(user.encode()).decode(), "password": base64.b64encode(b"fake:password\\for-test").decode()}
            return subprocess.CompletedProcess(command, 0, json.dumps({"data": data}).encode(), b"")

        with tempfile.TemporaryDirectory() as directory, patch.object(services.subprocess, "run", kubectl):
            target = Path(directory)
            services.generate(target, [55463, 55464, 55465])
            services.generate(target, [55463, 55464, 55465])
            for name in ("pg_service.conf", "pgpass"):
                self.assertEqual((target / name).stat().st_mode & 0o777, 0o600)
            self.assertNotIn("fake", (target / "pg_service.conf").read_text())
            self.assertIn(r"fake\:password\\for-test", (target / "pgpass").read_text())
            self.assertEqual({call[5] for call in calls}, {"arcade-games-restore-app", "arcade-slots-restore-app", "arcade-postgresql-app"})
            self.assertTrue(all(call[:5] == ["kubectl", "--context", "labprod", "get", "secret"] for call in calls))
            calls.clear()
            services.generate(target, [55463, 55464, 55465], rehearsal=True)
            self.assertEqual({call[5] for call in calls}, {"arcade-games-restore-rehearsal-app", "arcade-slots-restore-rehearsal-app", "arcade-postgresql-rehearsal-app"})


if __name__ == "__main__":
    unittest.main()
