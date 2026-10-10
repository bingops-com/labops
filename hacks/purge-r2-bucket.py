#!/usr/bin/env python3
"""Inspect or explicitly purge an R2 bucket through the Cloudflare REST API."""

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


DEFAULT_TFVARS = (
    Path(__file__).resolve().parents[1]
    / "terraform/cloudflare/credentials.auto.tfvars"
)


def credential(name, text):
    match = re.search(rf'^\s*{name}\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing required Terraform input: {name}")
    return match.group(1)


parser = argparse.ArgumentParser()
parser.add_argument("bucket")
parser.add_argument("--purge", action="store_true")
parser.add_argument("--confirm-bucket")
parser.add_argument("--tfvars", type=Path, default=DEFAULT_TFVARS)
args = parser.parse_args()

if args.purge and args.confirm_bucket != args.bucket:
    parser.error("--purge requires --confirm-bucket with the exact bucket name")

config = args.tfvars.read_text(encoding="utf-8")
account_id = credential("cloudflare_account_id", config)
api_token = credential("cloudflare_api_token", config)
encoded_bucket = urllib.parse.quote(args.bucket, safe="")
base_url = (
    "https://api.cloudflare.com/client/v4/accounts/"
    f"{account_id}/r2/buckets/{encoded_bucket}/objects"
)


def request(url, method="GET", absent_ok=False):
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        if absent_ok and error.code == 404:
            return None
        raise RuntimeError(f"Cloudflare API returned HTTP {error.code}") from None
    if not payload.get("success"):
        raise RuntimeError("Cloudflare API rejected the R2 object operation")
    return payload


def list_page(limit):
    query = urllib.parse.urlencode({"per_page": limit})
    return request(f"{base_url}?{query}", absent_ok=True)


def delete_key(key):
    encoded_key = urllib.parse.quote(key, safe="/")
    request(f"{base_url}/{encoded_key}", method="DELETE")


first_page = list_page(1)
if first_page is None:
    print(json.dumps({"bucket": args.bucket, "state": "absent"}))
elif not args.purge:
    print(
        json.dumps(
            {
                "bucket": args.bucket,
                "state": "nonempty" if first_page.get("result") else "empty",
            }
        )
    )
else:
    deleted = 0
    while True:
        page = list_page(1000)
        keys = [item["key"] for item in page.get("result", [])]
        if not keys:
            break
        with ThreadPoolExecutor(max_workers=16) as executor:
            list(executor.map(delete_key, keys))
        deleted += len(keys)
        print(json.dumps({"bucket": args.bucket, "deleted": deleted}), flush=True)
    print(json.dumps({"bucket": args.bucket, "deleted_total": deleted, "remaining": 0}))
