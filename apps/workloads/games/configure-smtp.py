#!/usr/bin/env python3
"""Configure Postfix using secret identifiers and optional public DNS metadata."""
import argparse
import base64
import ipaddress
import json
import pathlib
import subprocess
import uuid


def secret_uuid(value):
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a Bitwarden UUID, never a secret value") from error
    if parsed.int == 0:
        raise argparse.ArgumentTypeError("a real nonzero Bitwarden UUID is required")
    return str(parsed)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("smtp_password_uuid", type=secret_uuid)
parser.add_argument("dkim_key_uuid", type=secret_uuid)
parser.add_argument("--egress-ip")
parser.add_argument("--dkim-public-key-file", type=pathlib.Path)
args = parser.parse_args()
if args.smtp_password_uuid == args.dkim_key_uuid:
    parser.error("SMTP password and DKIM key must be different secrets")
if bool(args.egress_ip) != bool(args.dkim_public_key_file):
    parser.error("provide --egress-ip and --dkim-public-key-file together")

public_key = None
if args.egress_ip:
    try:
        address = ipaddress.ip_address(args.egress_ip)
        if address.version != 4 or not address.is_global:
            raise ValueError("expected the actual public IPv4 egress address")
        public_key = args.dkim_public_key_file.read_text().strip()
        decoded = base64.b64decode(public_key, validate=True)
        check = subprocess.run(
            ["openssl", "rsa", "-pubin", "-inform", "DER", "-noout"],
            input=decoded, capture_output=True, check=False,
        )
        if check.returncode or len(decoded) < 270:
            raise ValueError("expected an RSA public key of at least 2048 bits")
    except (ValueError, OSError) as error:
        parser.error(str(error))

repo = pathlib.Path(__file__).resolve().parents[3]
games = repo / "apps/workloads/games/clusters/labprod"
mail = repo / "apps/platform/mail/labprod"
source = (games / "r2-secret.yaml").read_text()
header = source.split("  map:\n", 1)[0]
auth = source.split("  authToken:\n", 1)[1]


def mapping(directory, filename, name, namespace, secret_id, key):
    prefix = header.replace("games-r2-credentials", name).replace("namespace: games", f"namespace: {namespace}")
    (directory / filename).write_text(
        prefix + f"  map:\n    - bwSecretId: {secret_id}\n      secretKeyName: {key}\n"
        + "  authToken:\n" + auth
    )
    path = directory / "kustomization.yaml"
    content = path.read_text()
    entry = f"  - {filename}\n"
    if entry not in content:
        path.write_text(content.replace("resources:\n", "resources:\n" + entry, 1))


mapping(games, "smtp-secret.yaml", "games-smtp", "games", args.smtp_password_uuid, "password")
mapping(mail, "smtp-secret.yaml", "mail-smtp", "mail", args.smtp_password_uuid, "password")
mapping(mail, "dkim-secret.yaml", "mail-dkim", "mail", args.dkim_key_uuid, "games.lab.bingo.private")
if public_key:
    settings = {
        "egress_ipv4": args.egress_ip,
        "dkim_selector": "games1",
        "dkim_public_key": public_key,
    }
    fields = "\n".join(f"    {key} = {json.dumps(value)}" for key, value in settings.items())
    (repo / "terraform/cloudflare/games-mail-settings.tf").write_text(
        "# Public DNS metadata; contains no private key or password.\n"
        + "locals {\n  games_mail = {\n" + fields + "\n  }\n}\n"
    )
print("Updated Bitwarden identifiers and resource registration; review and commit the diff.")
