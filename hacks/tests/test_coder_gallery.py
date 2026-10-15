"""Offline HTTP acceptance for the read-only workspace image gallery."""

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from http.server import ThreadingHTTPServer
import unittest
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


if __name__ == "__main__":
    unittest.main()
