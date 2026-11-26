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
/opt/dev-vm/venv/bin/python -c 'import requests,proxmoxer,pytest'
