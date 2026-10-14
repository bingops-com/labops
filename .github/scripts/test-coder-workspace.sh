#!/usr/bin/env bash
# Exercises the actual non-root OpenSSH path used by iSH.
set -euo pipefail

image=${1:?Pass a locally built workspace image}
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
scratch=$(mktemp -d)
container_id=''
cleanup() {
  if [[ -n "$container_id" ]]; then
    docker rm -f "$container_id" >/dev/null
  fi
  rm -rf "$scratch"
}
trap cleanup EXIT

ssh-keygen -q -t ed25519 -N '' -f "$scratch/client_key"
chmod 644 "$scratch/client_key.pub"
mkdir "$scratch/home"
sudo chown 1000:1000 "$scratch/home"
# Match a Kubernetes ConfigMap file: root-owned and readable, never writable.
sudo chown 0:0 "$scratch/client_key.pub"
container_id=$(docker run -d --workdir /home/coder --cap-drop ALL --security-opt no-new-privileges --publish 127.0.0.1::2222 --mount "type=bind,src=$scratch/home,dst=/home/coder" --mount "type=bind,src=$scratch/client_key.pub,dst=/etc/coder-ssh/authorized_keys,readonly" --mount "type=bind,src=$repo_root/apps/workloads/coder/base/template/startup.sh,dst=/opt/lab-startup.sh,readonly" "$image" /bin/bash -ec '/bin/bash /opt/lab-startup.sh; exec sleep infinity')
port=$(docker inspect --format '{{(index (index .NetworkSettings.Ports "2222/tcp") 0).HostPort}}' "$container_id")

connected=false
for _ in $(seq 1 20); do
  if ssh -i "$scratch/client_key" -p "$port" -o BatchMode=yes -o ConnectTimeout=2 -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$scratch/known_hosts" coder@127.0.0.1 'test "$(id -u)" = 1000 && python3 -c "import matplotlib,numpy,pandas" && node --version && npm --version && go version && tmux -V' > "$scratch/result" 2> "$scratch/ssh-error"; then
    connected=true
    break
  fi
  sleep 1
done
if [[ "$connected" != true ]]; then
  docker logs "$container_id"
  docker exec "$container_id" cat /home/coder/.config/lab/sshd.log || true
  cat "$scratch/ssh-error" >&2
  exit 1
fi

cat "$scratch/result"
if [[ ${2:-basic} == homeops ]]; then
  ssh -i "$scratch/client_key" -p "$port" -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$scratch/known_hosts" coder@127.0.0.1 homeops-dev-check
  # This records inner-sandbox support without relaxing the container profile.
  if ! docker exec "$container_id" codex sandbox -- /usr/bin/true > "$scratch/sandbox-result" 2>&1; then
    echo 'Codex inner sandbox is unavailable under the restricted CI container profile; a compatible runtime profile or explicit container-isolation mode is required.'
    tail -n 4 "$scratch/sandbox-result"
  else
    echo 'Codex inner sandbox verified.'
  fi
fi
echo 'Non-root SSH and development tools verified.'
