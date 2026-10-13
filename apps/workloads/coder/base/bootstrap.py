"""Idempotent, operator-owned Coder initialization using its supported CLI/API."""

import base64
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


BASE = "https://coder.lab.bingo"
OWNER = "bingops"
EMAIL = "therealbingops@gmail.com"
TEMPLATE = Path("/opt/lab-template")
STATE = Path("/data/.config/lab/bootstrap.json")
RESERVED_DOMAIN = "@coder-bootstrap.invalid"
SENSITIVE = []


def log(message):
    for value in SENSITIVE:
        if value:
            message = message.replace(value, "[redacted]")
    message = re.sub(r"postgres(?:ql)?://[^\s\"]+", "[database URL redacted]", message)
    print(message, flush=True)


class APIError(RuntimeError):
    def __init__(self, method, path, status):
        self.status = status
        super().__init__(f"Coder {method} {path}: HTTP {status}")


class API:
    def __init__(self, token=""):
        self.token = token

    def call(self, path, method="GET", payload=None, missing=False):
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Coder-Session-Token"] = self.token
        request = urllib.request.Request(BASE + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
                return json.loads(content) if content else None
        except urllib.error.HTTPError as error:
            if missing and error.code == 404:
                return None
            # Do not log raw API responses, which can carry credentials.
            raise APIError(method, path, error.code) from None


def cli(arguments, token="", extra_env=None):
    env = dict(os.environ, CODER_URL=BASE, CODER_CONFIG_DIR="/tmp/coder-config", CODER_CACHE_DIRECTORY="/tmp/coder-cache")
    if token:
        env["CODER_SESSION_TOKEN"] = token
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(["coder", *arguments], env=env, cwd="/tmp", capture_output=True, text=True, timeout=720)
    if result.returncode:
        log("\n".join((result.stdout + result.stderr).splitlines()[-20:]))
        raise RuntimeError(f"Coder command failed: {' '.join(arguments[:2])}, exit {result.returncode}")


def kubernetes(path):
    root = Path("/var/run/secrets/kubernetes.io/serviceaccount")
    context = ssl.create_default_context(cafile=str(root / "ca.crt"))
    request = urllib.request.Request(
        "https://kubernetes.default.svc" + path,
        headers={"Authorization": "Bearer " + (root / "token").read_text().strip()},
    )
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        return json.load(response)


def desired_state():
    digest = hashlib.sha256()
    for name in ("main.tf", "startup.sh", ".terraform.lock.hcl"):
        digest.update(name.encode() + b"\0" + (TEMPLATE / name).read_bytes())
    digest.update(Path(__file__).read_bytes())
    digest.update(os.environ["CODER_BOOTSTRAP_GENERATION"].encode())
    account = kubernetes("/api/v1/namespaces/coder-workspaces/serviceaccounts/coder-bootstrap")
    return {"hash": digest.hexdigest(), "service_account_uid": account["metadata"]["uid"]}


def wait_for_server():
    for _ in range(24):
        try:
            # This endpoint is public; 404 means a healthy, uninitialized server.
            return API().call("/api/v2/users/first", missing=True)
        except (RuntimeError, urllib.error.URLError):
            time.sleep(5)
    raise RuntimeError("Coder did not become available")


def setup(desired):
    database = kubernetes("/api/v1/namespaces/coder/secrets/coder-postgresql-app")
    connection = base64.b64decode(database["data"]["uri"]).decode()
    SENSITIVE.append(connection)
    generation = desired["service_account_uid"] + ":" + os.environ["CODER_BOOTSTRAP_GENERATION"]
    name = "setup-" + hmac.new(connection.encode(), ("identity:" + generation).encode(), hashlib.sha256).hexdigest()[:12]
    password = hmac.new(connection.encode(), ("password:" + generation).encode(), hashlib.sha256).hexdigest() + "Aa1!"
    SENSITIVE.append(password)
    bootstrap_id = None
    owner_id = None
    owner_token = ""
    owner_api = None
    try:
        login = {"email": name + RESERVED_DOMAIN, "password": password}
        try:
            session = API().call("/api/v2/users/login", "POST", login)["session_token"]
            log("Resuming temporary bootstrap access from an interrupted attempt")
        except APIError as error:
            if error.status != 401:
                raise
            log("Creating temporary bootstrap access through the official Coder CLI")
            cli(["server", "create-admin-user"], extra_env={"CODER_USERNAME": name, "CODER_EMAIL": name + RESERVED_DOMAIN, "CODER_PASSWORD": password, "CODER_PG_CONNECTION_URL": connection})
            session = API().call("/api/v2/users/login", "POST", login)["session_token"]
        SENSITIVE.append(session)
        bootstrap_api = API(session)
        bootstrap_id = bootstrap_api.call("/api/v2/users/me")["id"]
        organizations = bootstrap_api.call("/api/v2/organizations")
        organization = next(org for org in organizations if org["is_default"])
        owner = bootstrap_api.call(f"/api/v2/users/{OWNER}", missing=True)
        if owner is None:
            owner = bootstrap_api.call("/api/v2/users", "POST", {
                "username": OWNER, "name": "Bingops", "email": EMAIL,
                "login_type": "oidc", "user_status": "active",
                "organization_ids": [organization["id"]], "roles": ["owner"],
            })
        if owner["email"] != EMAIL or owner["login_type"] != "oidc" or owner["status"] != "active":
            raise RuntimeError("Existing bingops identity differs from the declared active OIDC owner; refusing to reset it")
        owner_id = owner["id"]
        roles = {role["name"] for role in owner["roles"]}
        if "owner" not in roles:
            bootstrap_api.call(f"/api/v2/users/{owner_id}/roles", "PUT", {"roles": sorted(roles | {"owner"})})
        owner_token = bootstrap_api.call(f"/api/v2/users/{owner_id}/keys/tokens", "POST", {
            "lifetime": 900_000_000_000, "scopes": ["all"], "token_name": name + "-" + secrets.token_hex(4),
        })["key"]
        SENSITIVE.append(owner_token)
        owner_api = API(owner_token)
        owner_api.call(f"/api/v2/users/{bootstrap_id}", "DELETE")
        bootstrap_id = None
        log("OIDC owner ready; temporary local bootstrap identity removed")

        # Recover temporary identities from an interrupted previous setup.
        for user in owner_api.call("/api/v2/users?limit=1000")["users"]:
            if user["username"].startswith("setup-") and user["email"].endswith(RESERVED_DOMAIN) and user["login_type"] == "password":
                owner_api.call(f"/api/v2/users/{user['id']}", "DELETE")

        template = owner_api.call(f"/api/v2/organizations/{organization['id']}/templates/lab", missing=True)
        message = "LabOps desired " + desired["hash"]
        version = None if template is None else owner_api.call(f"/api/v2/templateversions/{template['active_version_id']}")
        if version is None or version["message"] != message:
            log("Importing the declared lab template")
            with tempfile.TemporaryDirectory(prefix="coder-template-") as directory:
                for filename in ("main.tf", "startup.sh", ".terraform.lock.hcl"):
                    shutil.copyfile(TEMPLATE / filename, Path(directory) / filename)
                cli(["templates", "push", "lab", "--directory", directory, "--message", message, "--yes"], token=owner_token)
        cli(["templates", "edit", "lab", "--default-ttl", "0h", "--yes"], token=owner_token)
        workspace = owner_api.call(f"/api/v2/users/{OWNER}/workspace/lab", missing=True)
        if workspace is None:
            log("Creating the retained bingops/lab workspace with autostop disabled")
            cli(["create", "bingops/lab", "--template", "lab", "--stop-after", "0h", "--yes"], token=owner_token)
            workspace = owner_api.call(f"/api/v2/users/{OWNER}/workspace/lab")
        # An existing workspace is preserved, including an intentional stop.
        desired.update(owner_id=owner_id, workspace_id=workspace["id"])
    finally:
        if owner_api is not None:
            if bootstrap_id is not None:
                owner_api.call(f"/api/v2/users/{bootstrap_id}", "DELETE", missing=True)
            if owner_token:
                owner_api.call(f"/api/v2/users/{owner_id}/keys/{owner_token.split('-', 1)[0]}", "DELETE", missing=True)


def main():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with (STATE.parent / "bootstrap.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("Another initialization is in progress")
            return
        desired = desired_state()
        initialized = wait_for_server() is not None
        if STATE.exists():
            try:
                saved = json.loads(STATE.read_text())
            except json.JSONDecodeError:
                saved = {}
                log("Ignoring an invalid generated setup marker")
            if initialized and all(saved.get(key) == value for key, value in desired.items()):
                log("Coder already initialized; preserving the existing workspace")
                return
        setup(desired)
        temporary = STATE.with_suffix(".tmp")
        temporary.write_text(json.dumps(desired) + "\n")
        temporary.chmod(0o600)
        temporary.replace(STATE)
        log("Automatic Coder initialization complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        log(f"Initialization failed: {error}")
        raise SystemExit(1) from None
