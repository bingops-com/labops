"""Create standalone Codex SQLite backups without changing application rows."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import time


def snapshot(home, output):
    home, output = Path(home).resolve(), Path(output).resolve()
    if home == output or home in output.parents or output in home.parents:
        raise ValueError("Snapshot storage must be separate from the home")
    source = home / ".codex"
    if source.is_symlink():
        raise ValueError("Refusing a symlinked Codex directory")
    target = output / ".codex"
    if target.is_symlink():
        raise ValueError("Refusing a symlinked snapshot directory")
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    count = 0
    for database in sorted(source.glob("*.sqlite")):
        if database.is_symlink():
            raise ValueError("Refusing a symlinked SQLite database")
        deadline = time.monotonic() + 120

        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError("SQLite snapshot exceeded its deadline")

        descriptor, temporary = tempfile.mkstemp(prefix=".snapshot-", dir=target)
        os.close(descriptor)
        try:
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=5)) as reader:
                reader.execute("PRAGMA query_only=ON")
                with closing(sqlite3.connect(temporary)) as writer:
                    reader.backup(writer, pages=256, progress=progress, sleep=0.05)
                    writer.execute("PRAGMA journal_mode=DELETE")
                    if writer.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                        raise RuntimeError("SQLite snapshot validation failed")
            os.replace(temporary, target / database.name)
        finally:
            Path(temporary).unlink(missing_ok=True)
        count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", default="/data")
    parser.add_argument("--output", default="/snapshots")
    arguments = parser.parse_args()
    os.umask(0o077)
    if not (Path(arguments.home) / ".lab-initialized").is_file():
        raise SystemExit("Refusing to snapshot an uninitialized home")
    print(f"Codex SQLite snapshots ready: {snapshot(arguments.home, arguments.output)}", flush=True)
