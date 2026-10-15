"""Offline HTTP acceptance for the read-only workspace image gallery."""

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SOURCE = Path(__file__).resolve().parents[2] / "apps/workloads/coder/base/gallery.py"
spec = importlib.util.spec_from_file_location("coder_gallery", SOURCE)
gallery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gallery)


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name) / "projects"
        self.root.mkdir()
        (self.root / "rpg").mkdir()
        (self.root / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (self.root / "secret.txt").write_text("must not be served")
        (self.root / ".private.png").write_bytes(b"hidden")
        (self.root / "active.svg").write_text("<svg/>")
        (self.root / "credentials").mkdir()
        (self.root / "outside").symlink_to(self.root.parent, target_is_directory=True)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), gallery.make_handler(self.root))
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def status(self, path, method="GET"):
        try:
            with urlopen(Request(self.base + path, method=method), timeout=2) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    def test_only_images_and_allowed_directories_are_listed(self):
        status, data = self.status("/api/list")
        self.assertEqual(status, 200)
        payload = json.loads(data)
        self.assertEqual([x["name"] for x in payload["images"]], ["hero.png"])
        self.assertEqual([x["name"] for x in payload["directories"]], ["rpg"])

    def test_preview_and_head(self):
        self.assertEqual(self.status("/raw?path=hero.png"), (200, b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(self.status("/raw?path=hero.png", "HEAD"), (200, b""))

    def test_traversal_hidden_and_symlinks_denied(self):
        for path in ["..", "%2e%2e%2f", "%2fetc", ".private.png", "outside", "credentials"]:
            self.assertEqual(self.status("/api/list?path=" + path)[0], 403, path)
        self.assertEqual(self.status("/raw?path=.private.png")[0], 403)

    def test_other_documents_and_missing_paths_denied(self):
        for path in ["secret.txt", "active.svg"]:
            self.assertEqual(self.status("/raw?path=" + path)[0], 403)
        self.assertEqual(self.status("/raw?path=missing.png")[0], 404)

    def test_all_writes_rejected_without_modifying_files(self):
        for method in ["POST", "PUT", "PATCH", "DELETE"]:
            self.assertEqual(self.status("/raw?path=hero.png", method)[0], 405)
        self.assertEqual((self.root / "hero.png").read_bytes(), b"\x89PNG\r\n\x1a\n")


    def test_inventory_is_read_only_cached_and_excludes_private_files(self):
        inventory = {"workspace": {"name": "lab"}, "ports": [], "projects": [{"name": "rpg", "ports": []}], "limited": False}
        with patch.object(gallery, "workspace_inventory", return_value=inventory) as discover:
            for _ in range(2):
                status, payload = self.status("/api/dev/status")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(payload), inventory)
            self.assertEqual(discover.call_count, 1)
            self.assertEqual(self.status("/api/dev/status", "POST")[0], 405)

    def test_fixed_login_return_has_no_open_redirect(self):
        from urllib.request import build_opener, HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        try:
            build_opener(NoRedirect).open(self.base + "/_dev/return?next=https://untrusted.example")
            self.fail("Expected redirect")
        except HTTPError as error:
            self.assertEqual(error.code, 303)
            self.assertEqual(error.headers["Location"], "https://dev.lab.bingo/")

    def test_process_discovery_uses_socket_ownership_not_args_or_environment(self):
        proc = Path(self.temp.name) / "proc"
        (proc / "net").mkdir(parents=True)
        executable = Path(self.temp.name) / "node"
        executable.touch()
        for pid, inode, name, cwd in [(101, 12345, "node", self.root / "rpg"), (102, 54321, "codex", self.root / "rpg"), (103, 99999, "node", self.root.parent)]:
            process = proc / str(pid)
            (process / "fd").mkdir(parents=True)
            (process / "cwd").symlink_to(cwd)
            binary = Path(self.temp.name) / name
            binary.touch()
            (process / "exe").symlink_to(binary)
            (process / "fd/7").symlink_to(f"socket:[{inode}]")
        (proc / "net/tcp").write_text("header\n" + "\n".join(f"0: 0100007F:{port:04X} 00000000:0000 0A 00000000:00000000 00:00000000 00000000 1000 0 {inode}" for port, inode in [(4173,12345),(34857,54321),(5000,99999)]))
        (proc / "net/tcp6").write_text("header\n")
        self.assertEqual(gallery.listening_project_ports(self.root, proc), [{"port":4173,"project":"rpg","runtime":"Node.js"}])

    def test_probe_recognizes_http_and_discovers_projects_without_reading_them(self):
        record = {"port":self.server.server_port,"project":"rpg","runtime":"Python"}
        probe = gallery.probe_web_port(record)
        self.assertEqual(probe["http_status"], 200)
        with patch.object(gallery, "listening_project_ports", return_value=[record]):
            result = gallery.workspace_inventory(self.root)
        self.assertEqual([p["name"] for p in result["projects"]], ["rpg"])
        self.assertEqual(result["ports"][0]["port"], self.server.server_port)
        self.assertNotIn("secret.txt", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
