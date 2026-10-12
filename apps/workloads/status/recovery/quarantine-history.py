"""Quarantine only the inspected, invalid history; never reset valid JSON."""

import datetime
import hashlib
import json
import pathlib
import sys
import uuid


def quarantine(data_dir, expected_sha256):
    history = pathlib.Path(data_dir) / "history.json"
    if history.is_symlink():
        raise RuntimeError("refusing a history symlink")
    if not history.exists():
        print("No history file; nothing to quarantine.")
        return
    raw = history.read_bytes()
    try:
        json.loads(raw)
    except (ValueError, UnicodeError):
        pass
    else:
        print("History is valid JSON; left unchanged.")
        return
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise RuntimeError("history differs from the inspected file; inspect again")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = history.with_name(f"history.json.corrupt-{stamp}-{uuid.uuid4().hex}")
    # A rename on the same volume preserves the original bytes atomically.
    history.rename(backup)
    if hashlib.sha256(backup.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"backup verification failed: {backup.name}")
    print(f"Preserved {len(raw)} bytes as {backup.name}; sha256={digest}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or len(sys.argv[1]) != 64:
        raise SystemExit("usage: quarantine-history.py EXPECTED_SHA256")
    quarantine("/data", sys.argv[1])
