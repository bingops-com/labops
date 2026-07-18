#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CREDENTIALS_FILE="${REPO_ROOT}/capi/credentials.env"
EXPECTED_CONTEXT="labmgmt"
ASSUME_YES=false
WAIT=true
API_WAIT_TIMEOUT_SECONDS=600
API_RETRY_INTERVAL_SECONDS=10

usage() {
  cat <<'EOF'
Install the pinned Cluster API providers on the LabOps management cluster.

Usage:
  hacks/capi-init.sh [options]

Options:
      --credentials PATH  Credentials file (default: capi/credentials.env)
      --context NAME      Required kubectl context (default: labmgmt)
  -y, --yes               Skip the interactive confirmation
      --no-wait           Do not wait for provider deployments
  -h, --help              Show this help

The credentials file must define PROXMOX_URL, PROXMOX_TOKEN, and
PROXMOX_SECRET. It is sourced as shell syntax, so only use a file you control.
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

while (($# > 0)); do
  case "$1" in
    --credentials)
      (($# >= 2)) || die "$1 requires a path"
      CREDENTIALS_FILE="$2"
      shift 2
      ;;
    --context)
      (($# >= 2)) || die "$1 requires a context name"
      EXPECTED_CONTEXT="$2"
      shift 2
      ;;
    -y|--yes)
      ASSUME_YES=true
      shift
      ;;
    --no-wait)
      WAIT=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1 (use --help)"
      ;;
  esac
done

require_command clusterctl
require_command kubectl
require_command stat

[[ -f "${CREDENTIALS_FILE}" ]] || die \
  "credentials file not found: ${CREDENTIALS_FILE} (copy capi/credentials.env.example)"

credentials_mode="$(stat -c '%a' "${CREDENTIALS_FILE}")"
case "${credentials_mode}" in
  600|400) ;;
  *) die "credentials file must have mode 600 or 400 (found ${credentials_mode})" ;;
esac

# shellcheck disable=SC1090
source "${CREDENTIALS_FILE}"
: "${PROXMOX_URL:?missing PROXMOX_URL in credentials file}"
: "${PROXMOX_TOKEN:?missing PROXMOX_TOKEN in credentials file}"
: "${PROXMOX_SECRET:?missing PROXMOX_SECRET in credentials file}"
export PROXMOX_URL PROXMOX_TOKEN PROXMOX_SECRET
export CLUSTERCTL_CONFIG="${REPO_ROOT}/capi/clusterctl.yaml"

current_context="$(kubectl config current-context 2>/dev/null)" || \
  die "kubectl has no current context"
[[ "${current_context}" == "${EXPECTED_CONTEXT}" ]] || die \
  "current kubectl context is ${current_context}; expected ${EXPECTED_CONTEXT}"

printf 'Kubernetes context: %s\n' "${current_context}"
printf 'Proxmox endpoint: %s\n' "${PROXMOX_URL}"
printf 'Proxmox token ID: %s\n' "${PROXMOX_TOKEN}"
printf 'Clusterctl config: %s\n' "${CLUSTERCTL_CONFIG}"

printf 'Waiting up to %ss for the Kubernetes API to become ready...\n' \
  "${API_WAIT_TIMEOUT_SECONDS}"
api_wait_deadline=$((SECONDS + API_WAIT_TIMEOUT_SECONDS))
until kubectl --request-timeout=5s get --raw=/readyz >/dev/null 2>&1; do
  if ((SECONDS >= api_wait_deadline)); then
    die "Kubernetes API did not become ready within ${API_WAIT_TIMEOUT_SECONDS}s"
  fi

  printf 'Kubernetes API is not ready; retrying in %ss...\n' \
    "${API_RETRY_INTERVAL_SECONDS}"
  sleep "${API_RETRY_INTERVAL_SECONDS}"
done
printf 'Kubernetes API is ready.\n'

if [[ "${ASSUME_YES}" == false ]]; then
  read -r -p "Install or update the pinned CAPI providers on ${current_context}? [y/N] " reply
  [[ "${reply}" == y || "${reply}" == Y ]] || die "cancelled"
fi

clusterctl init \
  --core cluster-api:v1.12.9 \
  --bootstrap talos:v0.6.12 \
  --control-plane talos:v0.5.13 \
  --infrastructure proxmox:v0.9.0 \
  --ipam in-cluster:v1.1.0

if [[ "${WAIT}" == true ]]; then
  kubectl wait \
    --for=condition=Available \
    --timeout=5m \
    deployment --all -A
fi
