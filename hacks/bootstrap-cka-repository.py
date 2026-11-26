#!/usr/bin/env python3
"""Create/adopt a repository-scoped read-only deploy key for private CKA GitOps."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess


def run(args, payload=None):
    result = subprocess.run(args, input=None if payload is None else json.dumps(payload).encode(), capture_output=True)
    if result.returncode:
        raise RuntimeError("Operator operation failed; sensitive output suppressed")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.add_argument("--key-directory", type=Path, default=Path.home() / ".local/share/cka-gitops")
    args = parser.parse_args()
    os.umask(0o077)
    args.key_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = args.key_directory / "argocd-readonly"
    if not key.exists():
        if key.with_suffix(".pub").exists():
            raise RuntimeError("Partial key material; restore before retry")
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "cka-argocd-readonly", "-f", str(key)])
    public = run(["ssh-keygen", "-y", "-f", str(key)]).decode().strip()
    title = "labprod-argocd-cka-readonly"
    keys = json.loads(run(["gh", "api", "repos/bingops-com/cka/keys"]))
    match = next((entry for entry in keys if entry["title"] == title), None)
    if match:
        if match["key"].split()[:2] != public.split()[:2] or not match["read_only"]:
            raise RuntimeError("Existing deploy key differs; no overwrite")
    else:
        run(["gh", "api", "--method", "POST", "repos/bingops-com/cka/keys", "--input", "-"], {"title": title, "key": public, "read_only": True})
    desired = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "cka-git-repository", "namespace": "argocd-system", "labels": {"argocd.argoproj.io/secret-type": "repository"}}, "type": "Opaque", "stringData": {"type": "git", "url": "git@github.com:bingops-com/cka.git", "sshPrivateKey": key.read_text()}}
    existing = run(["kubectl", "--context", "labprod", "get", "secret", "cka-git-repository", "-n", "argocd-system", "--ignore-not-found", "-o", "json"])
    if existing.strip():
        current = json.loads(existing)
        data = {name: base64.b64decode(value).decode() for name, value in current.get("data", {}).items()}
        if any(data.get(name) != value for name, value in desired["stringData"].items()):
            raise RuntimeError("Existing repository credential differs; no overwrite")
    else:
        run(["kubectl", "--context", "labprod", "create", "-f", "-"], desired)
    print("Read-only CKA repository credential ready. Reconcile the declared SSH source/AppProject separately.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Private CKA repository bootstrap refused; restore the retained key or inspect operator permissions. No sensitive output emitted.")
