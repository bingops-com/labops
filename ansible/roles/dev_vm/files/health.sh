#!/bin/bash
set -euo pipefail
systemctl is-active --quiet tailscaled ssh dev-agent dev-gateway nginx dnsmasq
tailscale ip -4 >/dev/null
sshd -t
nft list table inet dev_vm >/dev/null
curl --fail --silent --show-error --max-time 5 -H 'Host: dev.lab.bingo' -H 'X-Authentik-Username: bingops' http://127.0.0.1:8080/api/workspace >/dev/null
tail_ip=$(tailscale ip -4)
dig +short @"$tail_ip" dev.lab.bingo | command grep -Fx "$tail_ip" >/dev/null
curl --fail --silent --show-error --max-time 5 --resolve "dev.lab.bingo:443:$tail_ip" https://dev.lab.bingo/ >/dev/null
MISE_DATA_DIR=/opt/dev-vm/mise /usr/local/bin/mise exec -- node --version >/dev/null
MISE_DATA_DIR=/opt/dev-vm/mise /usr/local/bin/mise exec -- terraform version >/dev/null
MISE_DATA_DIR=/opt/dev-vm/mise /usr/local/bin/mise exec -- /bin/bash /opt/dev-vm/current/environment/check-tools.sh >/dev/null
echo 'Development VM checks passed'
