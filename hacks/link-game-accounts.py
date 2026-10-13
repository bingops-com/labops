#!/usr/bin/env python3
"""Player-owned proof of two logins. Passwords and bearer cookies are never saved."""
import argparse
import csv
import getpass
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def authenticate(origin, name, password, cookie_name, *, fixture=False):
    parsed = urllib.parse.urlsplit(origin)
    allowed = origin in ("https://games.lab.bingo", "https://slots.lab.bingo")
    local = fixture and parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost") and parsed.path == "" and not parsed.query and not parsed.fragment and not parsed.username
    if not (allowed or local):
        raise ValueError("Authentication origin is not allowed")
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(origin + "/api/login", data=json.dumps({"name": name, "password": password}).encode(), headers={"Content-Type": "application/json", "Origin": origin}, method="POST")
    try:
        with opener.open(request, timeout=20) as response:
            if response.status != 200:
                raise ValueError("Login refused")
            response.read(65536)  # Do not log player data or server error bodies.
    except (urllib.error.HTTPError, urllib.error.URLError):
        raise ValueError("Login refused or service unavailable") from None
    cookies = [c for c in jar if c.name == cookie_name and re.fullmatch(r"[0-9a-f]{64}", c.value)]
    if len(cookies) != 1 or (not fixture and not cookies[0].secure):
        raise ValueError("Login did not return the expected secure session")
    return hashlib.sha256(cookies[0].value.encode()).hexdigest()


def save_proof(path, name, games_hash, slots_hash):
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,16}", name) or not all(re.fullmatch(r"[0-9a-f]{64}", h) for h in (games_hash, slots_hash)):
        raise ValueError("Invalid account-link proof")
    # Exclusive creation prevents following an existing symlink or overwriting a proof.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", newline="") as file:
        csv.writer(file).writerow([name.lower(), games_hash, slots_hash])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New private CSV outside the repository")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Run interactively: passwords must not be supplied in arguments, environment or redirected input")
    print("Run this yourself for your own accounts. Do not give passwords to an operator.")
    print("After migration the Games password will be used in both games; Slots credits and statistics are retained.")
    name = input("Pseudo shared by the two accounts: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,16}", name):
        raise ValueError("Invalid pseudo")
    games_hash = authenticate("https://games.lab.bingo", name, getpass.getpass("Games password: "), "games_session")
    slots_hash = authenticate("https://slots.lab.bingo", name, getpass.getpass("Slots password: "), "slots_session")
    save_proof(args.output, name, games_hash, slots_hash)
    print("Both logins verified. Private proof saved; no password or bearer cookie was saved.")
    print("Give only this proof file to the migration operator through a private channel. A password change, revocation or expiry invalidates it.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, EOFError, KeyboardInterrupt) as error:
        print("Account link was not completed: " + (str(error) if isinstance(error, ValueError) else "input or file error"), file=sys.stderr)
        sys.exit(1)
