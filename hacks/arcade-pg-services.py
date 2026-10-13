#!/usr/bin/env python3
"""Generate private libpq configuration for restored Arcade copies, never primaries."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile


def atomic_private(path, content):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".arcade-")
    try:
        with os.fdopen(fd, "w") as file:
            file.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def generate(directory, ports, *, rehearsal=False):
    directory = directory.resolve()
    if any((p / ".git").is_file() or (p / ".git" / "HEAD").is_file() for p in (directory, *directory.parents)):
        raise ValueError("Generated credentials must be outside Git")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.stat().st_mode & 0o077:
        raise ValueError("Output directory must be private (mode 0700)")
    config, passwords = [], []
    sources = [
        ("arcade-games-copy", "games", "arcade-games-restore-app", "games", "arcade_games_restore"),
        ("arcade-slots-copy", "slots", "arcade-slots-restore-app", "slots", "arcade_slots_restore"),
        ("arcade-target", "games", "arcade-postgresql-app", "arcade", "arcade"),
    ]
    if rehearsal:
        sources = [(service, namespace, secret.removesuffix("-app") + "-rehearsal-app", user, database) for service, namespace, secret, user, database in sources]
    for (service, namespace, secret, user, database), port in zip(sources, ports):
        result = subprocess.run(["kubectl", "--context", "labprod", "get", "secret", secret, "-n", namespace, "-o", "json"], capture_output=True, check=True)
        data = json.loads(result.stdout)["data"]
        decoded_user = base64.b64decode(data["username"], validate=True).decode()
        password = base64.b64decode(data["password"], validate=True).decode()
        if decoded_user != user or not password or "\n" in password or "\r" in password:
            raise ValueError("Unexpected generated CNPG credential format")
        config.append(f"[{service}]\nhost=127.0.0.1\nport={port}\ndbname={database}\nuser={user}\nsslmode=require\nconnect_timeout=10\n")
        escaped = password.replace("\\", "\\\\").replace(":", "\\:")
        passwords.append(f"127.0.0.1:{port}:{database}:{user}:{escaped}\n")
    atomic_private(directory / "pg_service.conf", "\n".join(config))
    atomic_private(directory / "pgpass", "".join(passwords))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--games-port", type=int, default=55463)
    parser.add_argument("--slots-port", type=int, default=55464)
    parser.add_argument("--target-port", type=int, default=55465)
    parser.add_argument("--rehearsal", action="store_true", help="Read only the three isolated -rehearsal cluster credentials")
    args = parser.parse_args()
    ports = [args.games_port, args.slots_port, args.target_port]
    if any(p < 1024 or p > 65535 for p in ports) or len(set(ports)) != 3:
        parser.error("Use three distinct unprivileged local ports")
    try:
        generate(args.directory, ports, rehearsal=args.rehearsal)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError):
        parser.exit(1, "Configuration not completed; check private directory and access to the three named restored/target Secrets. No credential was logged.\n")
    print("Private libpq files generated. Use the matching loopback port-forwards and remove files after the operation.")


if __name__ == "__main__":
    main()
