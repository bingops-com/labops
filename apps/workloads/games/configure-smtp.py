#!/usr/bin/env python3
"""Commit a Bitwarden identifier, never a credential. Safe to rerun."""
import pathlib
import sys
import uuid

if len(sys.argv) != 2:
    sys.exit("usage: configure-smtp.py BITWARDEN_SECRET_UUID (never the API key)")
try:
    secret_id = uuid.UUID(sys.argv[1])
except ValueError:
    sys.exit("expected a Bitwarden secret UUID, never an API key")
if secret_id.int == 0:
    sys.exit("a real Bitwarden secret UUID is required")

root = pathlib.Path(__file__).resolve().parent / "clusters/labprod"
source = (root / "r2-secret.yaml").read_text()
header = source.split("  map:\n", 1)[0].replace("games-r2-credentials", "games-smtp")
auth = source.split("  authToken:\n", 1)[1]
(root / "smtp-secret.yaml").write_text(
    header + f"  map:\n    - bwSecretId: {secret_id}\n      secretKeyName: password\n"
    + "  authToken:\n" + auth
)
kustomization = root / "kustomization.yaml"
content = kustomization.read_text()
if "  - smtp-secret.yaml\n" not in content:
    kustomization.write_text(content.replace("  - r2-secret.yaml\n", "  - r2-secret.yaml\n  - smtp-secret.yaml\n"))
print("Updated SMTP identifier and resource registration; review and commit both files.")
