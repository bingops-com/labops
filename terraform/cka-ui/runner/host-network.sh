#!/usr/bin/env bash
# Run as root only on the declared Proxmox host. No global firewall flush,
# network reload, existing-bridge edit, forwarding or Tailscale change.
set -euo pipefail
test "$(id -u)" -eq 0
command -v iptables >/dev/null
command -v ip6tables >/dev/null
marker=/etc/network/interfaces.d/cka-ui
if ip link show vmbr90 >/dev/null 2>&1 && ! test -f "$marker"; then
  echo 'Refusing an existing bridge without the CKA ownership marker.' >&2
  exit 1
fi
if test -f "$marker" && ! head -1 "$marker" | grep -qx '# Owned by LabOps terraform/cka-ui'; then
  echo 'Bridge ownership mismatch.' >&2
  exit 1
fi
install -d -m 0755 /etc/network/interfaces.d /usr/local/sbin
cat >"$marker" <<'NETWORK'
# Owned by LabOps terraform/cka-ui
auto vmbr90
iface vmbr90 inet manual
    bridge-ports none
    bridge-stp off
    bridge-fd 0
    post-up /usr/local/sbin/cka-ui-host-guard
NETWORK
cat >/usr/local/sbin/cka-ui-host-guard <<'GUARD'
#!/usr/bin/env bash
set -euo pipefail
for binary in iptables ip6tables; do
  "$binary" -w -N CKA_UI_INPUT 2>/dev/null || true
  "$binary" -w -F CKA_UI_INPUT
  "$binary" -w -A CKA_UI_INPUT -i vmbr90 -j DROP
  "$binary" -w -A CKA_UI_INPUT -j RETURN
  "$binary" -w -C INPUT -j CKA_UI_INPUT 2>/dev/null || "$binary" -w -I INPUT 1 -j CKA_UI_INPUT
  "$binary" -w -N CKA_UI_FORWARD 2>/dev/null || true
  "$binary" -w -F CKA_UI_FORWARD
  "$binary" -w -A CKA_UI_FORWARD -i vmbr90 ! -o vmbr90 -j DROP
  "$binary" -w -A CKA_UI_FORWARD ! -i vmbr90 -o vmbr90 -j DROP
  "$binary" -w -A CKA_UI_FORWARD -j RETURN
  "$binary" -w -C FORWARD -j CKA_UI_FORWARD 2>/dev/null || "$binary" -w -I FORWARD 1 -j CKA_UI_FORWARD
done
GUARD
chmod 0755 /usr/local/sbin/cka-ui-host-guard
/usr/local/sbin/cka-ui-host-guard
if ! ip link show vmbr90 >/dev/null 2>&1; then
  ip link add name vmbr90 type bridge
fi
# Deliberately no host address and no physical bridge port.
test -z "$(ip -o -4 addr show dev vmbr90)"
ip link set vmbr90 up
cat >/etc/systemd/system/cka-ui-host-guard.service <<'UNIT'
[Unit]
Description=Isolate the private CKA training bridge from the Proxmox IP stack
After=network-pre.target
Before=pve-guests.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/cka-ui-host-guard
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable cka-ui-host-guard.service >/dev/null
