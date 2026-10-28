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
  # The mounted fake home belongs to container UID 1000, not the runner UID.
  sudo rm -rf -- "$scratch/home"
  rm -rf "$scratch"
}
trap cleanup EXIT

ssh-keygen -q -t ed25519 -N '' -f "$scratch/client_key"
chmod 644 "$scratch/client_key.pub"
mkdir "$scratch/home"
sudo chown 1000:1000 "$scratch/home"
# Match a Kubernetes ConfigMap file: root-owned and readable, never writable.
sudo chown 0:0 "$scratch/client_key.pub"
tool_mounts=()
if [[ ${2:-basic} == homeops ]]; then
  tool_mounts=(
    --mount "type=bind,src=$repo_root/apps/workloads/coder/base/template/codex.toml,dst=/etc/codex/config.toml,readonly"
    --mount "type=bind,src=$repo_root/apps/workloads/coder/base/template/claude.json,dst=/etc/claude-code/managed-settings.json,readonly"
    --mount "type=bind,src=$repo_root/apps/workloads/coder/base/template/tmux.conf,dst=/etc/tmux.conf,readonly"
  )
fi
container_id=$(docker run -d --workdir /home/coder --cap-drop ALL --security-opt no-new-privileges --publish 127.0.0.1::2222 --mount "type=bind,src=$scratch/home,dst=/home/coder" --mount "type=bind,src=$scratch/client_key.pub,dst=/etc/coder-ssh/authorized_keys,readonly" --mount "type=bind,src=$repo_root/apps/workloads/coder/base/template/startup.sh,dst=/opt/lab-startup.sh,readonly" "${tool_mounts[@]}" "$image" /bin/bash -ec '/bin/bash /opt/lab-startup.sh; exec sleep infinity')
port=$(docker inspect --format '{{(index (index .NetworkSettings.Ports "2222/tcp") 0).HostPort}}' "$container_id")

connected=false
for _ in $(seq 1 20); do
  if ssh -i "$scratch/client_key" -p "$port" -o HostKeyAlias=coder-fixture -o BatchMode=yes -o ConnectTimeout=2 -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$scratch/known_hosts" coder@127.0.0.1 'test "$(id -u)" = 1000 && test "$(locale charmap)" = UTF-8 && python3 -c "import matplotlib,numpy,pandas" && node --version && npm --version && go version && tmux -V' > "$scratch/result" 2> "$scratch/ssh-error"; then
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
# Restart with the retained home. These account fixtures contain no real tokens.
docker exec "$container_id" python3 -c 'import json,pathlib; h=pathlib.Path("/home/coder"); files={".codex/config.toml":"cli_auth_credentials_store = \"file\"\n# personal configuration\n", ".codex/auth.json":"{\"fixture\":\"FAKE_CODEX_SESSION\"}", ".claude/settings.json":"{\"theme\":\"dark\"}", ".claude/.credentials.json":"{\"fixture\":\"FAKE_CLAUDE_SESSION\"}", ".claude.json":"{\"fixture\":\"FAKE_USER_SETTINGS\"}"}; [(h/p).write_text(v) for p,v in files.items()]; (h/".config/lab/persistence-fixture.json").write_text(json.dumps(files)); (h/"projects/persistence-fixture.txt").write_text("retained project")'
docker restart "$container_id" >/dev/null
# Docker may allocate a new ephemeral host port; pin trust to the same fixture.
port=$(docker inspect --format '{{(index (index .NetworkSettings.Ports "2222/tcp") 0).HostPort}}' "$container_id")
persisted=false
for _ in $(seq 1 20); do
  if ssh -i "$scratch/client_key" -p "$port" -o HostKeyAlias=coder-fixture -o BatchMode=yes -o ConnectTimeout=2 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$scratch/known_hosts" coder@127.0.0.1 'python3 -c '\''import json,pathlib; h=pathlib.Path.home(); files=json.loads((h/".config/lab/persistence-fixture.json").read_text()); assert all((h/p).read_text()==v for p,v in files.items()); assert (h/"projects/persistence-fixture.txt").read_text()=="retained project"; assert (h/".claude").stat().st_mode & 0o777 == 0o700; assert (h/".claude.json").stat().st_mode & 0o777 == 0o600'\''' > /dev/null 2> "$scratch/ssh-error"; then
    persisted=true
    break
  fi
  sleep 1
done
if [[ "$persisted" != true ]]; then
  cat "$scratch/ssh-error" >&2
  exit 1
fi
echo 'Personal account configuration, SSH host identity and projects survive restart.'
if [[ ${2:-basic} == homeops ]]; then
  ssh -i "$scratch/client_key" -p "$port" -o HostKeyAlias=coder-fixture -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$scratch/known_hosts" coder@127.0.0.1 homeops-dev-check
  docker exec -i "$container_id" python3 - < "$repo_root/.github/scripts/check-coder-tool-config.py"
fi
echo 'Non-root SSH and development tools verified.'
