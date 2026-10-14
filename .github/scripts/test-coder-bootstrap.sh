#!/usr/bin/env bash
set -euo pipefail

image=${1:?Pass the bootstrap image}
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
scratch=$(mktemp -d)
prefix="coder-acceptance-$RANDOM"
network="$prefix-network"
containers=()
cleanup() {
  for container in "${containers[@]}"; do
    docker rm -f "$container" >/dev/null 2>&1 || true
  done
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
docker run -d --name "$prefix-coder" --network "$network" --network-alias coder --entrypoint /opt/coder -e "CODER_PG_CONNECTION_URL=$database_uri" -e CODER_ACCESS_URL=http://coder:8080 -e CODER_HTTP_ADDRESS=0.0.0.0:8080 -e CODER_OIDC_ISSUER_URL=http://oidc:8080/ -e CODER_OIDC_CLIENT_ID=acceptance -e CODER_DISABLE_PASSWORD_AUTH=true -e CODER_OIDC_ALLOW_SIGNUPS=false -e CODER_TELEMETRY_ENABLE=false -e CODER_PROVISIONER_DAEMONS=1 ghcr.io/coder/coder:v2.36.7 server --oauth2-github-default-provider-enable=false --external-auth-github-default-provider-enable=false >/dev/null

run_phase() {
  docker run --rm --network "$network" --cap-drop ALL --security-opt no-new-privileges --entrypoint python3 -e "TEST_PHASE=$1" -e "TEST_DATABASE_URI=$database_uri" -e CODER_BOOTSTRAP_GENERATION=acceptance-g1 --mount "type=bind,src=$scratch/home,dst=/data" --mount "type=bind,src=$scratch/template,dst=/opt/lab-template" --mount "type=bind,src=$repo_root/apps/workloads/coder/base/bootstrap.py,dst=/scripts/bootstrap.py,readonly" --mount "type=bind,src=$repo_root/.github/scripts/test-coder-bootstrap.py,dst=/acceptance.py,readonly" "$image" -u /acceptance.py
}
query() {
  docker exec "$prefix-postgres" psql -XAt -U coder_test -d coder -c "$1"
}

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
