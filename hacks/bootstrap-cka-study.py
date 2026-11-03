#!/usr/bin/env python3
"""Prepare generated CKA role/URI Secrets for the declared shared database.

Requires --apply. Never prints a credential or executes the account migration.
"""
import argparse
import base64
import json
import secrets
import subprocess
import urllib.parse


def kubectl(args, payload=None):
    result = subprocess.run(["kubectl", "--context", "labprod", *args], input=None if payload is None else json.dumps(payload).encode(), capture_output=True)
    if result.returncode:
        raise RuntimeError("Kubernetes operation failed; no credential output")
    return json.loads(result.stdout) if result.stdout.strip() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.parse_args()
    cluster = kubectl(["get", "cluster", "arcade-postgresql", "-n", "games", "-o", "json"])
    declared_db = cluster["spec"].get("bootstrap", {}).get("initdb", {}).get("database")
    role = next((role for role in cluster["spec"].get("managed", {}).get("roles", []) if role.get("name") == "cka_app"), {})
    if declared_db not in (None, "arcade") or role.get("passwordSecret", {}).get("name") != "cka-database-role":
        raise RuntimeError("Unexpected shared database identity")
    ca = kubectl(["get", "secret", "arcade-postgresql-ca", "-n", "games", "-o", "json"])["data"]["ca.crt"]
    existing = kubectl(["get", "secret", "cka-database-role", "-n", "games", "--ignore-not-found", "-o", "json"])
    if existing:
        if base64.b64decode(existing["data"]["username"]).decode() != "cka_app":
            raise RuntimeError("Existing credential belongs to another role")
        password = base64.b64decode(existing["data"]["password"]).decode()
    else:
        password = secrets.token_urlsafe(48)
        kubectl(["create", "-f", "-", "-o", "json"], {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "cka-database-role", "namespace": "games", "labels": {"cnpg.io/reload": "true"}}, "type": "kubernetes.io/basic-auth", "stringData": {"username": "cka_app", "password": password}})
    if existing and existing.get("metadata",{}).get("labels",{}).get("cnpg.io/reload") != "true":
        kubectl(["patch","secret","cka-database-role","-n","games","--type=merge","--patch-file","-","-o","json"], {"metadata":{"labels":{"cnpg.io/reload":"true"}}})
    uri = "postgresql://cka_app:" + urllib.parse.quote(password, safe="") + "@arcade-postgresql-rw.games.svc.cluster.local:5432/arcade?sslmode=verify-full&sslrootcert=/run/cka-db/ca.crt"
    desired = {"uri": base64.b64encode(uri.encode()).decode(), "ca.crt": ca}
    target = kubectl(["get", "secret", "cka-database", "-n", "cka", "--ignore-not-found", "-o", "json"])
    if target:
        if target.get("data") != desired:
            kubectl(["patch", "secret", "cka-database", "-n", "cka", "--type=merge", "--patch-file", "-", "-o", "json"], {"data": desired})
    else:
        kubectl(["create", "-f", "-", "-o", "json"], {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "cka-database", "namespace": "cka"}, "type": "Opaque", "data": desired})
    print("CKA study credentials reconciled; no account migration or application restart performed.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("CKA credential bootstrap refused; inspect prerequisite names and operator permissions without printing Secrets.")
