"""Synthetic backup and restore checks; no operator files or cloud requests."""

from contextlib import closing
import importlib.util
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("snapshot_codex", ROOT / "base/snapshot-codex.py")
snapshots = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshots)


class HomeBackupTests(unittest.TestCase):
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
                manifest = (ROOT / "base/backup.yaml").read_text()
                script = manifest.split("                - |\n", 1)[1].split("\n              env:", 1)[0]
                script = "\n".join(line[18:] for line in script.splitlines())
                script = script.replace("/data", str(home)).replace("/snapshots", str(output))
                script = script.replace("r2:bingops-cnpg-labprod/coder-workspaces/bingops-lab/current", str(current))
                script = script.replace("r2:bingops-cnpg-labprod/coder-workspaces/bingops-lab/archive", str(archive))
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
            finally:
                writer.close()


if __name__ == "__main__":
    unittest.main()
