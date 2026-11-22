#!/bin/bash
set -euo pipefail
for _ in {1..120}; do
  address=$(tailscale ip -4 2>/dev/null || true)
  if [[ -n "$address" ]] && ip -4 -o address show dev tailscale0 2>/dev/null | grep -F " $address/" >/dev/null; then
    exit 0
  fi
  sleep 1
done
echo 'Waiting for the enrolled Tailscale interface timed out' >&2
exit 1
