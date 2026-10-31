"""Synthetic backup and restore checks; no operator files or cloud requests."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import shlex
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from xml.etree.ElementTree import Element, SubElement, tostring

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("snapshot_codex", ROOT / "base/snapshot-codex.py")
snapshots = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshots)


class HomeBackupTests(unittest.TestCase):
    def pipeline(self, home, output, current, archive):
        manifest = (ROOT / "base/backup.yaml").read_text()
        script = manifest.split("                - |\n", 1)[1].split("\n              env:", 1)[0]
        script = "\n".join(line[18:] for line in script.splitlines())
        script = script.replace("/data", str(home)).replace("/snapshots", str(output))
        script = script.replace("/scripts/prune-archives.sh", str(ROOT / "base/prune-archives.sh"))
        script = script.replace("r2:bingops-cnpg-labprod/coder-workspaces/bingops-lab/current", str(current))
        return script.replace("r2:bingops-cnpg-labprod/coder-workspaces/bingops-lab/archive", str(archive))

    def fixture(self, home, name="state_5.sqlite"):
        codex = home / ".codex"
        codex.mkdir(parents=True, exist_ok=True)
        database = codex / name
        writer = sqlite3.connect(database)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE fixture(value INTEGER PRIMARY KEY)")
        writer.execute("INSERT INTO fixture VALUES (1)")
        writer.commit()
        return database, writer

    def test_active_wal_is_preserved_in_a_standalone_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home, output = root / "home", root / "snapshots"
            database, writer = self.fixture(home)
            try:
                writer.execute("INSERT INTO fixture VALUES (2)")
                writer.commit()
                self.assertTrue(Path(str(database) + "-wal").exists())
                self.assertEqual(snapshots.snapshot(home, output), 1)
                target = output / ".codex" / database.name
                with closing(sqlite3.connect(target)) as restored:
                    self.assertEqual(restored.execute("PRAGMA quick_check").fetchall(), [("ok",)])
                    self.assertEqual(restored.execute("SELECT count(*) FROM fixture").fetchone(), (2,))
                self.assertFalse(Path(str(target) + "-wal").exists())
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)
                self.assertEqual(writer.execute("SELECT count(*) FROM fixture").fetchone(), (2,))
            finally:
                writer.close()

    def test_concurrent_writer_keeps_working_during_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database, initial = self.fixture(root / "home")
            initial.close()
            stop = threading.Event()
            ready = threading.Event()
            failures = []

            def write():
                try:
                    with closing(sqlite3.connect(database, timeout=5)) as connection:
                        ready.set()
                        for number in range(2, 10000):
                            if stop.is_set():
                                break
                            connection.execute("INSERT INTO fixture VALUES (?)", (number,))
                            connection.commit()
                            time.sleep(0.002)
                except Exception as error:
                    failures.append(error)

            thread = threading.Thread(target=write)
            thread.start()
            try:
                self.assertTrue(ready.wait(5))
                snapshots.snapshot(root / "home", root / "snapshots")
                with closing(sqlite3.connect(root / "snapshots/.codex/state_5.sqlite")) as restored:
                    self.assertEqual(restored.execute("PRAGMA quick_check").fetchone(), ("ok",))
                    self.assertGreaterEqual(restored.execute("SELECT count(*) FROM fixture").fetchone()[0], 1)
            finally:
                stop.set()
                thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(failures, [])

    def test_symlink_and_failed_snapshot_do_not_publish_partial_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex = root / "home/.codex"
            codex.mkdir(parents=True)
            (codex / "invalid.sqlite").write_text("TEST_ONLY_INVALID_DATABASE")
            with self.assertRaises(sqlite3.DatabaseError):
                snapshots.snapshot(root / "home", root / "snapshots")
            self.assertEqual(list((root / "snapshots/.codex").iterdir()), [])
            (codex / "invalid.sqlite").unlink()
            (codex / "linked.sqlite").symlink_to(root / "outside.sqlite")
            with self.assertRaises(ValueError):
                snapshots.snapshot(root / "home", root / "snapshots")

    @unittest.skipUnless(shutil.which("rclone"), "rclone is required for the real pipeline check")
    def test_full_pipeline_archives_old_journals_and_restores_the_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home, output, current, archive = [root / name for name in ("home", "snapshots", "current", "archive")]
            database, writer = self.fixture(home, "thread_history_1.sqlite")
            try:
                (home / ".lab-initialized").touch()
                (home / ".codex/auth.json").write_text('{"fixture":"TEST_ONLY_AUTH"}')
                snapshots.snapshot(home, output)
                (current / ".codex").mkdir(parents=True)
                (current / ".codex/thread_history_1.sqlite").write_text("TEST_ONLY_OLD_DATABASE")
                (current / ".codex/thread_history_1.sqlite-wal").write_text("TEST_ONLY_OLD_WAL")
                (current / ".codex/thread_history_1.sqlite-shm").write_text("TEST_ONLY_OLD_SHM")
                (home / "project").mkdir()
                (home / "project/app.txt").write_text("NEW_VALUE")
                (current / "project").mkdir()
                (current / "project/app.txt").write_text("OLD_VALUE")
                # Same size AND mtime; only a content comparison detects this edit.
                old_time = time.time() - 35 * 86400
                for path in [home / "project/app.txt", current / "project/app.txt"]:
                    os.utime(path, (old_time,) * 2)
                (current / "project/deleted.txt").write_text("TEST_ONLY_DELETED")
                now = datetime.now(timezone.utc)
                expired = (now - timedelta(days=15)).strftime("%Y-%m-%dT%H-%M-%SZ")
                recent = (now - timedelta(days=13)).strftime("%Y-%m-%dT%H-%M-%SZ")
                for name, age in [(expired, 0), (recent, 35), ("unknown-prefix", 35),
                                  ("2026-02-30T00-00-00Z", 35)]:
                    target = archive / name / "file.txt"
                    target.parent.mkdir(parents=True)
                    target.write_text("TEST_ONLY_ARCHIVE")
                    os.utime(target, (time.time() - age * 86400,) * 2)
                script = self.pipeline(home, output, current, archive)
                result = subprocess.run(["/bin/sh", "-ec", script], env={**os.environ, "RCLONE_CONFIG": "/dev/null"}, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Workspace backup complete", result.stdout)
                self.assertEqual((current / ".codex/auth.json").read_text(), '{"fixture":"TEST_ONLY_AUTH"}')
                self.assertFalse(list((current / ".codex").glob("*.sqlite-*")))
                with closing(sqlite3.connect(current / ".codex" / database.name)) as restored:
                    self.assertEqual(restored.execute("PRAGMA quick_check").fetchone(), ("ok",))
                    self.assertEqual(restored.execute("SELECT count(*) FROM fixture").fetchone(), (1,))
                self.assertEqual(len(list(archive.glob("*/.codex/thread_history_1.sqlite-wal"))), 1)
                self.assertEqual(len(list(archive.glob("*/.codex/thread_history_1.sqlite"))), 1)
                self.assertEqual((current / "project/app.txt").read_text(), "NEW_VALUE")
                self.assertFalse((current / "project/deleted.txt").exists())
                self.assertEqual(len(list(archive.glob("*/project/deleted.txt"))), 1)
                self.assertEqual(next(archive.glob("*/project/app.txt")).read_text(), "OLD_VALUE")
                self.assertFalse((archive / expired).exists())
                self.assertTrue((archive / recent / "file.txt").exists())
                self.assertTrue((archive / "unknown-prefix/file.txt").exists())
                self.assertTrue((archive / "2026-02-30T00-00-00Z/file.txt").exists())
                self.assertGreater((time.time() - next(archive.glob("*/project/app.txt")).stat().st_mtime) / 86400, 34)
                result = subprocess.run(
                    ["/bin/sh", str(ROOT / "base/prune-archives.sh"), str(archive)],
                    env={**os.environ, "RCLONE_CONFIG": "/dev/null"},
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("0 expired prefixes purged", result.stdout)
                restore = root / "restored"
                result = subprocess.run(
                    ["rclone", "copy", str(current), str(restore), "--fast-list"],
                    env={**os.environ, "RCLONE_CONFIG": "/dev/null"},
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((restore / "project/app.txt").read_text(), "NEW_VALUE")
                with closing(sqlite3.connect(restore / ".codex" / database.name)) as restored:
                    self.assertEqual(restored.execute("PRAGMA quick_check").fetchone(), ("ok",))
                    self.assertEqual(restored.execute("SELECT count(*) FROM fixture").fetchone(), (1,))
            finally:
                writer.close()

    @unittest.skipUnless(shutil.which("rclone"), "rclone is required for the failure check")
    def test_failed_snapshot_upload_keeps_expired_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home, output, current, archive = [root / name for name in ("home", "snapshots", "current", "archive")]
            (home / ".codex").mkdir(parents=True)
            (home / ".lab-initialized").touch()
            (home / ".codex/auth.json").write_text("TEST_ONLY_AUTH")
            (output / ".codex").mkdir(parents=True)
            expired = (datetime.now(timezone.utc) - timedelta(days=15)).strftime("%Y-%m-%dT%H-%M-%SZ")
            protected = archive / expired / "file.txt"
            protected.parent.mkdir(parents=True)
            protected.write_text("TEST_ONLY_RECOVERY_FILE")
            fake_bin = root / "bin"
            fake_bin.mkdir()
            wrapper = fake_bin / "rclone"
            wrapper.write_text('#!/bin/sh\nif [ "$1" = copy ]; then exit 42; fi\nexec '
                               + shlex.quote(shutil.which("rclone")) + ' "$@"\n')
            wrapper.chmod(0o700)
            env = {**os.environ, "RCLONE_CONFIG": "/dev/null", "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]}
            result = subprocess.run(["/bin/sh", "-ec", self.pipeline(home, output, current, archive)],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 42, result.stderr)
            self.assertTrue(protected.exists())
            self.assertNotIn("Archive retention complete", result.stdout)

    def test_retention_rejects_current_as_a_prune_root(self):
        with tempfile.TemporaryDirectory() as directory:
            current = Path(directory) / "current"
            current.mkdir()
            protected = current / "file.txt"
            protected.write_text("TEST_ONLY_CURRENT")
            result = subprocess.run(["/bin/sh", str(ROOT / "base/prune-archives.sh"), str(current)],
                                    capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(protected.exists())

    @unittest.skipUnless(shutil.which("rclone"), "rclone is required for the S3 listing check")
    def test_fast_list_preserves_paginated_inventory_with_fewer_s3_requests(self):
        # Loopback-only S3 listing fixture: no cloud endpoint or operator credentials.
        keys = [f"current/project-{i:02d}/file-{j:03d}" for i in range(25) for j in range(45)]
        checksum = hashlib.md5(b"fixture").hexdigest()
        requests = []
        heads = []

        class ListingHandler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_HEAD(self):
                path = urlsplit(self.path).path
                key = path.removeprefix("/fixture/")
                if key in keys:
                    heads.append(key)
                    self.send_response(200)
                    self.send_header("Content-Length", "7")
                    self.send_header("ETag", f'"{checksum}"')
                    self.send_header("Last-Modified", "Thu, 01 Jan 2026 00:00:00 GMT")
                    self.send_header("X-Amz-Meta-Mtime", str((source / key.removeprefix("current/")).stat().st_mtime))
                else:
                    self.send_response(200 if path.rstrip("/") == "/fixture" else 404)
                    self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                query = parse_qs(urlsplit(self.path).query)
                requests.append(query)
                prefix = query.get("prefix", [""])[0]
                delimiter = query.get("delimiter", [""])[0]
                entries = set()
                for key in keys:
                    if not key.startswith(prefix):
                        continue
                    suffix = key[len(prefix):]
                    if delimiter and delimiter in suffix:
                        entries.add((prefix + suffix.split(delimiter, 1)[0] + delimiter, True))
                    else:
                        entries.add((key, False))
                entries = sorted(entries)
                offset = int(query.get("continuation-token", ["0"])[0])
                limit = min(int(query.get("max-keys", ["1000"])[0]), 1000)
                page = entries[offset:offset + limit]
                more = offset + limit < len(entries)
                xml = Element("ListBucketResult", xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
                for tag, value in [("Name", "fixture"), ("Prefix", prefix), ("MaxKeys", str(limit)),
                                   ("KeyCount", str(len(page))), ("IsTruncated", str(more).lower())]:
                    SubElement(xml, tag).text = value
                if more:
                    SubElement(xml, "NextContinuationToken").text = str(offset + limit)
                for key, directory in page:
                    item = SubElement(xml, "CommonPrefixes" if directory else "Contents")
                    SubElement(item, "Prefix" if directory else "Key").text = key
                    if not directory:
                        SubElement(item, "Size").text = "7"
                        SubElement(item, "LastModified").text = "2026-01-01T00:00:00.000Z"
                        SubElement(item, "ETag").text = f'"{checksum}"'
                        SubElement(item, "StorageClass").text = "STANDARD"
                body = tostring(xml, encoding="utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/xml")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            for key in keys:
                file = source / key.removeprefix("current/")
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b"fixture")
                fixture_time = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
                os.utime(file, (fixture_time, fixture_time))
            with ThreadingHTTPServer(("127.0.0.1", 0), ListingHandler) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    env = {
                        "PATH": os.environ["PATH"], "HOME": directory, "RCLONE_CONFIG": "/dev/null",
                        "RCLONE_CONFIG_FIXTURE_TYPE": "s3", "RCLONE_CONFIG_FIXTURE_PROVIDER": "Other",
                        "RCLONE_CONFIG_FIXTURE_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
                        "RCLONE_CONFIG_FIXTURE_ACCESS_KEY_ID": "TEST_ONLY_ACCESS_KEY",
                        "RCLONE_CONFIG_FIXTURE_SECRET_ACCESS_KEY": "TEST_ONLY_SECRET_KEY",
                        "RCLONE_CONFIG_FIXTURE_NO_CHECK_BUCKET": "true",
                        "RCLONE_CONFIG_FIXTURE_LIST_VERSION": "2",
                    }
                    inventory_result = subprocess.run(
                        ["rclone", "size", "fixture:fixture/current", "--json"],
                        env=env, capture_output=True, text=True, timeout=30,
                    )
                    self.assertEqual(inventory_result.returncode, 0, inventory_result.stderr)
                    inventory = json.loads(inventory_result.stdout)
                    self.assertEqual(inventory["count"], len(keys))
                    self.assertEqual(inventory["bytes"], len(keys) * 7)
                    counts = []
                    for flags in [[], ["--fast-list"]]:
                        requests.clear()
                        result = subprocess.run(
                            ["rclone", "sync", str(source), "fixture:fixture/current",
                             "--dry-run", "--checksum", "--use-json-log", "--stats", "0",
                             "--retries", "1", "--low-level-retries", "1", "--timeout", "3s", *flags],
                            env=env, capture_output=True, text=True, timeout=30,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        messages = [json.loads(line) for line in result.stderr.splitlines() if line]
                        changed = [line for line in messages if line.get("skipped") or line.get("object")]
                        self.assertEqual(len(changed), 0, changed[:3])
                        counts.append(len(requests))
                    self.assertGreater(counts[0], counts[1] * 5)
                    self.assertEqual(counts[1], 2)  # Both recursive pages were read.
                    print(f"S3 fixture listings: {counts[0]} -> {counts[1]} with fast-list")
                    head_counts = []
                    for flags in [[], ["--checksum"]]:
                        heads.clear()
                        result = subprocess.run(
                            ["rclone", "sync", str(source), "fixture:fixture/current", "--dry-run",
                             "--fast-list", "--use-json-log", "--stats", "0", "--retries", "1",
                             "--low-level-retries", "1", "--timeout", "3s", *flags],
                            env=env, capture_output=True, text=True, timeout=30,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        messages = [json.loads(line) for line in result.stderr.splitlines() if line]
                        changed = [line for line in messages if line.get("skipped") or line.get("object")]
                        self.assertEqual(len(changed), 0, changed[:3])
                        head_counts.append(len(heads))
                    self.assertEqual(head_counts, [len(keys), 0])
                    print(f"S3 fixture metadata HEADs: {head_counts[0]} -> {head_counts[1]} with checksum")
                finally:
                    server.shutdown()
                    thread.join(5)


if __name__ == "__main__":
    unittest.main()
