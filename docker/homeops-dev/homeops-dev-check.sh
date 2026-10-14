#!/usr/bin/env bash
# Offline smoke checks: no credentials, cluster changes, or model requests.
set -euo pipefail
test "$(id -u)" = 1000
test -w /home/coder
test "$(readlink -f /opt/homeops)" = /home/coder/projects
codex --version
claude --version
coder version
terraform version
kubectl version --client=true
helm version --short
talosctl version --client
clusterctl version
gh --version
ansible --version
ansible-lint --version
yamllint --version
shellcheck --version
actionlint --version
tflint --version
yq --version
docker --version
aws --version
kubeseal --version
task --version
crane version
trivy --version
node --version
npm --version
go version
psql --version
pg_dump --version
pg_restore --version
chromium --version
python3 -c 'import matplotlib,numpy,pandas,yaml'
/opt/homeops-dev/venv/bin/python -c 'import requests,proxmoxer,pytest'
command -v bwrap >/dev/null
tmux -V
echo 'homeops-dev tools verified without contacting production.'
