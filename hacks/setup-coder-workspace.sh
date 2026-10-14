#!/usr/bin/env bash
# Creates or updates the single retained experimentation workspace after SSO.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
template_dir="$repo_root/apps/workloads/coder/base/template"
coder_bin=${CODER_BIN:-coder}

if [[ -z ${CODER_SESSION_TOKEN:-} ]]; then
  echo 'Set CODER_SESSION_TOKEN using a short-lived token issued to bingops after SSO login.' >&2
  exit 1
fi
if ! command -v "$coder_bin" >/dev/null 2>&1; then
  echo 'Install the pinned Coder CLI on the operator host, or set CODER_BIN to its path.' >&2
  exit 1
fi
if ! grep -Eq 'image[[:space:]]*=[[:space:]]*"ghcr.io/bingops-com/(coder-workspace|homeops-dev)@sha256:[0-9a-f]{64}"' "$template_dir/main.tf"; then
  echo 'Pin the published workspace image digest in main.tf before importing the template.' >&2
  exit 1
fi

coder_cmd=("$coder_bin" --url https://coder.lab.bingo)
"${coder_cmd[@]}" templates push lab --directory "$template_dir" --yes
"${coder_cmd[@]}" templates edit lab --default-ttl 0h --yes

inventory=$(mktemp)
trap 'rm -f "$inventory"' EXIT
chmod 600 "$inventory"
"${coder_cmd[@]}" list --output json > "$inventory"
if ! python3 -c 'import json,sys; rows=json.load(open(sys.argv[1])); sys.exit(0 if any(w["name"] == "lab" and w["owner_name"] == "bingops" for w in rows) else 1)' "$inventory"; then
  "${coder_cmd[@]}" create bingops/lab --template lab --stop-after 0h --yes
fi

echo 'Template ready; verify the workspace is running and its autostop is disabled.'
echo 'OpenSSH endpoint: coder@coder.lab.bingo, port 30222.'
