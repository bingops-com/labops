#!/usr/bin/env bash
set -euo pipefail
umask 077

mkdir -p /home/coder/.ssh /home/coder/.config/lab /home/coder/projects
if [[ ! -f /home/coder/.ssh/ssh_host_ed25519_key ]]; then
  ssh-keygen -q -t ed25519 -N '' -f /home/coder/.ssh/ssh_host_ed25519_key
fi
chmod 700 /home/coder/.ssh
chmod 600 /home/coder/.ssh/ssh_host_ed25519_key

cat > /home/coder/.config/lab/sshd_config <<'CONFIG'
Port 2222
ListenAddress 0.0.0.0
HostKey /home/coder/.ssh/ssh_host_ed25519_key
PidFile /home/coder/.config/lab/sshd.pid
AuthorizedKeysFile /etc/coder-ssh/authorized_keys
AllowUsers coder
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthenticationMethods publickey
PubkeyAuthentication yes
PermitRootLogin no
UsePAM no
StrictModes yes
PermitUserEnvironment no
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding local
GatewayPorts no
ClientAliveInterval 60
ClientAliveCountMax 3
Subsystem sftp internal-sftp
SetEnv PATH=/home/coder/.local/bin:/usr/local/go/bin:/usr/local/bin:/usr/bin:/bin
CONFIG

/usr/sbin/sshd -t -f /home/coder/.config/lab/sshd_config
/usr/sbin/sshd -D -e -f /home/coder/.config/lab/sshd_config >> /home/coder/.config/lab/sshd.log 2>&1 &

if [[ ! -f /home/coder/.profile ]]; then
  # The profile expands these variables when the user logs in.
  # shellcheck disable=SC2016
  printf '%s\n' 'export PATH="$HOME/.local/bin:/usr/local/go/bin:$PATH"' 'cd "$HOME/projects"' > /home/coder/.profile
fi
touch /home/coder/.lab-initialized
echo 'Workspace ready. Connect with OpenSSH and use tmux new -As lab.'
