"""Create the first owner through AFFiNE's supported setup API; never log credentials."""
import json
import os
import secrets
import time
import urllib.error
import urllib.request

BASE = "http://affine.affine.svc.cluster.local:3010"


def call(path, payload):
    request = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Origin": "https://notes.lab.bingo",
                 "Host": "notes.lab.bingo"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


for attempt in range(90):
    try:
        response = call("/graphql", {"query": "{ serverConfig { initialized } }"})
        initialized = response["data"]["serverConfig"]["initialized"]
        if initialized:
            print("AFFiNE already initialized; existing accounts preserved", flush=True)
            break
        # The local password is deliberately not an operator credential. Normal
        # access uses the owner's verified email through Authentik OIDC + PKCE.
        call("/api/setup/create-admin-user", {
            "name": "Corentin Guyon", "email": os.environ["OWNER_EMAIL"],
            "password": secrets.token_urlsafe(18),
        })
        print("AFFiNE owner initialized; use Authentik OIDC to sign in", flush=True)
        break
    except (urllib.error.URLError, KeyError, TypeError):
        if attempt == 89:
            raise SystemExit("AFFiNE initialization failed; response bodies withheld") from None
        time.sleep(5)
