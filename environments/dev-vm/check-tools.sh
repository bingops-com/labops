#!/bin/bash
set -euo pipefail
export CLUSTERCTL_DISABLE_VERSIONCHECK=true
export DISABLE_AUTOUPDATER=1
export PATH="/opt/dev-vm/venv/bin:/usr/lib/postgresql/18/bin:$PATH"
codex --version
claude --version
terraform version
kubectl version --client
helm version --short
talosctl version --client
clusterctl version
yq --version
actionlint --version
tflint --version
task --version
kubeseal --version
crane version
trivy --version
node --version
go version
ansible --version
ansible-lint --version
yamllint --version
pytest --version
psql --version
pg_dump --version
pg_restore --version
python3 -c 'import matplotlib,numpy,pandas,yaml'
/opt/dev-vm/venv/bin/python -c 'import requests,proxmoxer,pytest,bitwarden_sdk'
test "$(locale charmap)" = UTF-8
test "$(fc-match --format '%{family}' 'DejaVu Sans Mono')" = 'DejaVu Sans Mono'
test "$(fc-match --format '%{family}' 'Liberation Sans')" = 'Liberation Sans'
test "$(fc-match --format '%{family}' emoji)" = 'Noto Color Emoji'
git --version
gh --version
docker --version
aws --version
npm --version
chromium --version
shellcheck --version
screen --version
tmux -V
command -v bwrap >/dev/null
echo 'Native development tools verified without production or model requests'
