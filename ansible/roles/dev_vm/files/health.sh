#!/bin/bash
set -euo pipefail
export HOME=/root
export XDG_CONFIG_HOME=/root/.config
export XDG_CACHE_HOME=/root/.cache
systemctl is-active --quiet tailscaled ssh dev-agent dev-gateway nginx dnsmasq
tailscale ip -4 >/dev/null
sshd -t
nft list table inet dev_vm >/dev/null
curl --fail --silent --show-error --max-time 5 --retry 10 --retry-connrefused --retry-delay 1 -H 'Host: code.lab.bingo' -H 'X-Authentik-Username: bingops' http://127.0.0.1:8080/api/workspace >/dev/null
tail_ip=$(tailscale ip -4)
dig +short @"$tail_ip" code.lab.bingo | command grep -Fx "$tail_ip" >/dev/null
curl --fail --silent --show-error --max-time 5 --resolve "code.lab.bingo:443:$tail_ip" https://code.lab.bingo/ >/dev/null
MISE_DATA_DIR=/opt/dev-vm/mise /usr/local/bin/mise exec -- node --version >/dev/null
MISE_DATA_DIR=/opt/dev-vm/mise /usr/local/bin/mise exec -- terraform version >/dev/null
MISE_DATA_DIR=/opt/dev-vm/mise /usr/local/bin/mise exec -- /bin/bash /opt/dev-vm/current/environment/check-tools.sh >/dev/null
echo 'Development VM checks passed'
