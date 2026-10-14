#!/usr/bin/env bash
set -euo pipefail

image=${1:?Pass the bootstrap image}
mode=${2:-basic}
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
scratch=$(mktemp -d)
prefix="coder-acceptance-$RANDOM"
network="$prefix-network"
containers=()
kind_created=false
port_forward_pid=''
cleanup() {
  if [[ -n "$port_forward_pid" ]]; then
    kill "$port_forward_pid" >/dev/null 2>&1 || true
  fi
  for container in "${containers[@]}"; do
    docker rm -f "$container" >/dev/null 2>&1 || true
  done
  if [[ "$kind_created" == true ]]; then
    kind delete cluster --name "$prefix" >/dev/null 2>&1 || true
  fi
  docker network rm "$network" >/dev/null 2>&1 || true
  rm -rf "$scratch"
}
trap cleanup EXIT

mkdir "$scratch/home" "$scratch/template"
chmod 777 "$scratch/home" "$scratch/template"
cat > "$scratch/template/main.tf" <<'TERRAFORM'
terraform {
  required_providers {
    coder = {
      source  = "coder/coder"
      version = "2.19.0"
    }
  }
}
provider "coder" {}
data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}
resource "terraform_data" "initial_failure" {
  provisioner "local-exec" {
    command = "exit 1"
  }
}
output "workspace_name" {
  value = data.coder_workspace.me.name
}
TERRAFORM
chmod 666 "$scratch/template/main.tf"
touch "$scratch/template/startup.sh"
cp "$repo_root/apps/workloads/coder/base/template/.terraform.lock.hcl" "$scratch/template/.terraform.lock.hcl"
cat > "$scratch/oidc.py" <<'PYTHON'
import http.server
import json

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        issuer = "http://oidc:8080/"
        body = json.dumps({"issuer": issuer, "authorization_endpoint": issuer + "authorize", "token_endpoint": issuer + "token", "jwks_uri": issuer + "keys", "code_challenge_methods_supported": ["S256"], "id_token_signing_alg_values_supported": ["RS256"]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

http.server.HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
PYTHON

docker network create "$network" >/dev/null
coder_options=()
if [[ "$mode" == kubernetes ]]; then
  kind_created=true
  kind create cluster --name "$prefix" --image mirror.gcr.io/kindest/node:v1.36.4@sha256:099e049362a1526b2db71494e1947aae99bd16290d7c895f2b7ea312e3cbfaed --wait 120s
  docker network connect "$network" "$prefix-control-plane"
  kind get kubeconfig --internal --name "$prefix" > "$scratch/kubeconfig"
  chmod 644 "$scratch/kubeconfig"
  coder_options=(-e KUBECONFIG=/acceptance-kubeconfig -e KUBE_CONFIG_PATH=/acceptance-kubeconfig --mount "type=bind,src=$scratch/kubeconfig,dst=/acceptance-kubeconfig,readonly")
  cp "$repo_root/apps/workloads/coder/base/template/main.tf" "$scratch/template/main.tf"
  cp "$repo_root/apps/workloads/coder/base/template/startup.sh" "$scratch/template/startup.sh"
  ssh-keygen -q -t ed25519 -N '' -f "$scratch/client_key"
  kubectl create namespace coder-workspaces
  kubectl label namespace coder-workspaces pod-security.kubernetes.io/enforce=restricted
  kubectl -n coder-workspaces create configmap coder-workspace-ssh --from-file="authorized_keys=$scratch/client_key.pub"
  kubectl apply -f - <<'PVC'
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: coder-bingops-home
  namespace: coder-workspaces
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: standard
  resources:
    requests: {storage: 1Gi}
PVC
fi
database_uri='postgresql://coder_test:TEST_ONLY_NOT_A_REAL_PASSWORD@postgres:5432/coder?sslmode=disable'
containers+=("$prefix-postgres" "$prefix-oidc" "$prefix-coder")
docker run -d --name "$prefix-postgres" --network "$network" --network-alias postgres -e POSTGRES_USER=coder_test -e POSTGRES_DB=coder -e POSTGRES_PASSWORD=TEST_ONLY_NOT_A_REAL_PASSWORD docker.io/postgres:18.4-trixie >/dev/null
for attempt in {1..30}; do
  if docker exec "$prefix-postgres" pg_isready -U coder_test -d coder >/dev/null 2>&1; then
    break
  fi
  if [[ $attempt == 30 ]]; then
    echo 'Disposable PostgreSQL did not become ready' >&2
    exit 1
  fi
  sleep 2
done
docker run -d --name "$prefix-oidc" --network "$network" --network-alias oidc --entrypoint python3 --mount "type=bind,src=$scratch/oidc.py,dst=/oidc.py,readonly" "$image" /oidc.py >/dev/null
docker run -d --name "$prefix-coder" --network "$network" --network-alias coder --entrypoint /opt/coder -e "CODER_PG_CONNECTION_URL=$database_uri" -e CODER_ACCESS_URL=http://coder:8080 -e CODER_HTTP_ADDRESS=0.0.0.0:8080 -e CODER_OIDC_ISSUER_URL=http://oidc:8080/ -e CODER_OIDC_CLIENT_ID=acceptance -e CODER_DISABLE_PASSWORD_AUTH=true -e CODER_OIDC_ALLOW_SIGNUPS=false -e CODER_TELEMETRY_ENABLE=false -e CODER_PROVISIONER_DAEMONS=1 "${coder_options[@]}" ghcr.io/coder/coder:v2.36.7 server --oauth2-github-default-provider-enable=false --external-auth-github-default-provider-enable=false >/dev/null
if [[ "$mode" == kubernetes ]]; then
  server_ip=$(docker inspect --format "{{(index .NetworkSettings.Networks \"$network\").IPAddress}}" "$prefix-coder")
  # Only reroute the private production hostname to the disposable Coder server.
  sed -i "s/192.168.10.151/$server_ip/; s/coder.lab.bingo/coder/" "$scratch/template/main.tf"
fi

run_phase() {
  docker run --rm --network "$network" --cap-drop ALL --security-opt no-new-privileges --entrypoint python3 -e "TEST_PHASE=$1" -e "TEST_DATABASE_URI=$database_uri" -e CODER_BOOTSTRAP_GENERATION=acceptance-g1 --mount "type=bind,src=$scratch/home,dst=/data" --mount "type=bind,src=$scratch/template,dst=/opt/lab-template" --mount "type=bind,src=$repo_root/apps/workloads/coder/base/bootstrap.py,dst=/scripts/bootstrap.py,readonly" --mount "type=bind,src=$repo_root/.github/scripts/test-coder-bootstrap.py,dst=/acceptance.py,readonly" "$image" -u /acceptance.py
}
query() {
  docker exec "$prefix-postgres" psql -XAt -U coder_test -d coder -c "$1"
}

if [[ "$mode" == kubernetes ]]; then
  run_phase kubernetes_initial
  kubectl -n coder-workspaces rollout status deployment/coder-bingops-lab --timeout=180s
  kubectl -n coder-workspaces exec deployment/coder-bingops-lab -- test -f /home/coder/.lab-initialized
  kubectl -n coder-workspaces port-forward deployment/coder-bingops-lab :2222 --address=127.0.0.1 > "$scratch/port-forward.log" 2>&1 &
  port_forward_pid=$!
  for _ in {1..30}; do
    port=$(sed -nE 's/^Forwarding from 127.0.0.1:([0-9]+).*/\1/p' "$scratch/port-forward.log")
    if [[ -n "$port" ]]; then break; fi
    sleep 1
  done
  test -n "$port"
  if ! ssh -i "$scratch/client_key" -p "$port" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$scratch/known_hosts" coder@127.0.0.1 'test "$(id -u)" = 1000 && test -f ~/.lab-initialized && codex --version'; then
    kubectl -n coder-workspaces exec deployment/coder-bingops-lab -- tail -n 20 /home/coder/.config/lab/sshd.log
    exit 1
  fi
  ssh-keygen -q -t ed25519 -N '' -f "$scratch/unlisted_key"
  if ssh -i "$scratch/unlisted_key" -p "$port" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$scratch/known_hosts" coder@127.0.0.1 true > "$scratch/unlisted-result" 2>&1; then
    echo 'An unlisted SSH key was accepted' >&2
    exit 1
  fi
  [[ $(query "SELECT count(*) FROM workspace_agents WHERE first_connected_at IS NOT NULL") == 1 ]]
  echo 'Real template provisioning, agent authorization, retained-home initialization and native SSH verified.'
  exit 0
fi

run_phase initial_failure
[[ $(query "SELECT count(*) FROM workspaces WHERE NOT deleted AND name='lab'") == 1 ]]
run_phase initial
[[ $(query "SELECT count(*) FROM workspace_builds") == 2 ]]
[[ $(query "SELECT count(*) FROM users WHERE NOT deleted AND username='bingops' AND login_type='oidc' AND status='active' AND 'owner'=ANY(rbac_roles)") == 1 ]]
[[ $(query "SELECT count(*) FROM users WHERE NOT deleted AND email LIKE '%@coder-bootstrap.invalid'") == 0 ]]
[[ $(query "SELECT count(*) FROM api_keys WHERE token_name LIKE 'setup-%'") == 0 ]]
[[ $(query "SELECT count(*) FROM workspaces WHERE NOT deleted AND name='lab'") == 1 ]]
before=$(query "SELECT count(*) FROM users")
build_before=$(query "SELECT count(*) FROM workspace_builds")
run_phase repeat
[[ $(query "SELECT count(*) FROM users") == "$before" ]]
[[ $(query "SELECT count(*) FROM workspace_builds") == "$build_before" ]]
run_phase update
[[ $(query "SELECT count(*) FROM workspace_builds") == "$build_before" ]]
[[ $(query "SELECT count(*) FROM users WHERE NOT deleted AND email LIKE '%@coder-bootstrap.invalid'") == 0 ]]
[[ $(query "SELECT count(*) FROM api_keys WHERE token_name LIKE 'setup-%'") == 0 ]]
echo 'OIDC provisioning, credential cleanup, idempotence and workspace preservation verified.'
