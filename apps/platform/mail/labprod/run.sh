#!/usr/bin/env bash
set -euo pipefail

# Hash only the public certificate; never inspect or print a private key.
fingerprint() { sha256sum /etc/postfix/tls/tls.crt | cut -d ' ' -f 1; }
previous=$(fingerprint)
/scripts/run.sh &
relay_pid=$!
stopping=0
sleep_pid=""
stop() {
  stopping=1
  kill -TERM "$relay_pid" 2>/dev/null || true
  if [[ -n "$sleep_pid" ]]; then kill "$sleep_pid" 2>/dev/null || true; fi
}
trap stop TERM INT
while kill -0 "$relay_pid" 2>/dev/null; do
  sleep 30 &
  sleep_pid=$!
  wait "$sleep_pid" || true
  if [[ "$stopping" == 1 ]]; then break; fi
  current=$(fingerprint)
  if [[ "$current" != "$previous" ]]; then
    if postfix reload; then
      previous=$current
      echo "SMTP certificate reloaded"
    fi
  fi
done
wait "$relay_pid"
