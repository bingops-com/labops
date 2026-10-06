#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

TERRAFORM_DIR="${REPO_ROOT}/terraform/proxmox"
CONFIG_DIR="${HOME}/.kube"
CONFIG_PREFIX="lab_"
TALOS_DIR="${HOME}/.talos"
BASHRC="${HOME}/.bashrc"
MANAGEMENT_CLUSTER="labmgmt"
NAMESPACE="capi-workloads"
WORKLOAD_CLUSTER="labprod"
INSTALL_WORKLOAD=true
REQUIRE_WORKLOAD=false
UPDATE_BASHRC=true

usage() {
  cat <<'EOF'
Install Kubernetes and Talos client access for LabOps.

Usage:
  hacks/cluster-setup.sh [options]

Options:
      --config-dir PATH      Kubeconfig directory (default: ~/.kube)
      --talos-dir PATH       Talos configuration directory (default: ~/.talos)
      --prefix PREFIX        Kubeconfig filename prefix (default: lab_)
      --bashrc PATH          Bash startup file to update (default: ~/.bashrc)
      --no-bashrc            Do not update a Bash startup file
      --terraform-dir PATH   Terraform root containing the management state
      --management NAME      Management cluster output key (default: labmgmt)
  -n, --namespace NAME       CAPI workload namespace (default: capi-workloads)
  -w, --workload NAME        Require the sole workload cluster (labprod)
      --management-only      Retrieve only the management cluster
  -h, --help                 Show this help

Without --workload, labprod is discovered automatically and is skipped until
its CAPI Cluster resource exists and its kubeconfig is ready. Any workload
name other than labprod is rejected.
Per-cluster files are installed with mode 0600. Kubernetes configurations are
flattened into ~/.kube/config and Talos contexts into ~/.talos/config, so both
clients work without environment variables. Bash exports are also maintained.
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
    --config-dir)
      (($# >= 2)) || die "$1 requires a path"
      CONFIG_DIR="$2"
      shift 2
      ;;
    --talos-dir)
      (($# >= 2)) || die "$1 requires a path"
      TALOS_DIR="$2"
      shift 2
      ;;
    --prefix)
      (($# >= 2)) || die "$1 requires a prefix"
      CONFIG_PREFIX="$2"
      shift 2
      ;;
    --bashrc)
      (($# >= 2)) || die "$1 requires a path"
      BASHRC="$2"
      shift 2
      ;;
    --no-bashrc)
      UPDATE_BASHRC=false
      shift
      ;;
    --terraform-dir)
      (($# >= 2)) || die "$1 requires a path"
      TERRAFORM_DIR="$2"
      shift 2
      ;;
    --management)
      (($# >= 2)) || die "$1 requires a cluster name"
      MANAGEMENT_CLUSTER="$2"
      shift 2
      ;;
    -n|--namespace)
      (($# >= 2)) || die "$1 requires a namespace"
      NAMESPACE="$2"
      shift 2
      ;;
    -w|--workload)
      (($# >= 2)) || die "$1 requires a cluster name"
      [[ "$2" == "${WORKLOAD_CLUSTER}" ]] || die "the only workload cluster is ${WORKLOAD_CLUSTER}"
      REQUIRE_WORKLOAD=true
      shift 2
      ;;
    --management-only)
      INSTALL_WORKLOAD=false
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

require_command terraform
require_command kubectl
require_command jq
require_command talosctl
require_command base64
if [[ "${INSTALL_WORKLOAD}" == true ]]; then
  require_command clusterctl
fi

[[ -d "${TERRAFORM_DIR}" ]] || die "Terraform directory not found: ${TERRAFORM_DIR}"
mkdir -p -- "${CONFIG_DIR}"
mkdir -p -- "${TALOS_DIR}"

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf -- "${TMP_DIR}"
}
trap cleanup EXIT

rename_current_context() {
  local config="$1"
  local desired_name="$2"
  local current_context

  current_context="$(kubectl --kubeconfig "${config}" config current-context)"
  if [[ "${current_context}" != "${desired_name}" ]]; then
    kubectl --kubeconfig "${config}" config rename-context \
      "${current_context}" "${desired_name}" >/dev/null
  fi
}

install_config() {
  local source="$1"
  local cluster="$2"
  local filename_cluster="${cluster}"
  if [[ "${CONFIG_PREFIX}" == "lab_" && "${cluster}" == lab* ]]; then
    filename_cluster="${cluster#lab}"
  fi
  local destination="${CONFIG_DIR}/${CONFIG_PREFIX}${filename_cluster}"
  local destination_tmp

  destination_tmp="$(mktemp "${CONFIG_DIR}/.${CONFIG_PREFIX}${filename_cluster}.XXXXXX")"
  install -m 0600 "${source}" "${destination_tmp}"
  mv -f -- "${destination_tmp}" "${destination}"
  CONFIG_PATHS+=("${destination}")
}

MANAGEMENT_CONFIG="${TMP_DIR}/${MANAGEMENT_CLUSTER}.yaml"
terraform -chdir="${TERRAFORM_DIR}" output -json kubeconfigs \
  | jq -er --arg cluster "${MANAGEMENT_CLUSTER}" '.[$cluster]' \
  >"${MANAGEMENT_CONFIG}" \
  || die "cannot read kubeconfig for ${MANAGEMENT_CLUSTER} from Terraform state"
rename_current_context "${MANAGEMENT_CONFIG}" "${MANAGEMENT_CLUSTER}"

CONFIG_PATHS=()
install_config "${MANAGEMENT_CONFIG}" "${MANAGEMENT_CLUSTER}"

MANAGEMENT_TALOS_CONFIG="${TMP_DIR}/${MANAGEMENT_CLUSTER}.talosconfig"
terraform -chdir="${TERRAFORM_DIR}" output -json talosconfigs \
  | jq -er --arg cluster "${MANAGEMENT_CLUSTER}" '.[$cluster]' \
  >"${MANAGEMENT_TALOS_CONFIG}" \
  || die "cannot read talosconfig for ${MANAGEMENT_CLUSTER} from Terraform state"
TALOS_CONFIGS=("${MANAGEMENT_TALOS_CONFIG}")

if [[ "${INSTALL_WORKLOAD}" == true ]]; then
  cluster="${WORKLOAD_CLUSTER}"
  if [[ "${REQUIRE_WORKLOAD}" == false ]] && \
     ! kubectl --kubeconfig "${MANAGEMENT_CONFIG}" \
       --namespace "${NAMESPACE}" get cluster "${cluster}" >/dev/null 2>&1; then
    printf 'Skipping %s: CAPI Cluster resource does not exist yet.\n' "${cluster}"
  else
    config="${TMP_DIR}/${cluster}.yaml"
    if ! clusterctl get kubeconfig "${cluster}" \
      --namespace "${NAMESPACE}" \
      --kubeconfig "${MANAGEMENT_CONFIG}" >"${config}"; then
      if [[ "${REQUIRE_WORKLOAD}" == true ]]; then
        die "cannot retrieve kubeconfig for ${cluster}"
      fi
      printf 'Skipping %s: its kubeconfig is not ready yet.\n' "${cluster}" >&2
    elif [[ ! -s "${config}" ]]; then
      if [[ "${REQUIRE_WORKLOAD}" == true ]]; then
        die "clusterctl returned an empty kubeconfig for ${cluster}"
      fi
      printf 'Skipping %s: clusterctl returned an empty kubeconfig.\n' "${cluster}" >&2
    else
      rename_current_context "${config}" "${cluster}"
      install_config "${config}" "${cluster}"

      talos_config="${TMP_DIR}/${cluster}.talosconfig"
      if kubectl --kubeconfig "${MANAGEMENT_CONFIG}" --namespace "${NAMESPACE}" \
        get secret "${cluster}-talosconfig" -o jsonpath='{.data.talosconfig}' \
        | base64 --decode >"${talos_config}" && [[ -s "${talos_config}" ]]; then
        TALOS_CONFIGS+=("${talos_config}")
      elif [[ "${REQUIRE_WORKLOAD}" == true ]]; then
        die "cannot retrieve talosconfig from Secret ${cluster}-talosconfig"
      else
        printf 'Skipping Talos access for %s: its talosconfig Secret is not ready.\n' "${cluster}" >&2
        rm -f -- "${talos_config}"
      fi
    fi
  fi
fi

# Preserve unrelated contexts while replacing LabOps contexts with fresh data.
KUBE_DEFAULT="${CONFIG_DIR}/config"
KUBE_MERGED="${TMP_DIR}/kubeconfig"
KUBE_SOURCES=("${CONFIG_PATHS[@]}")
[[ ! -s "${KUBE_DEFAULT}" ]] || KUBE_SOURCES+=("${KUBE_DEFAULT}")
KUBECONFIG="$(IFS=:; printf '%s' "${KUBE_SOURCES[*]}")" \
  kubectl config view --raw --flatten >"${KUBE_MERGED}"
kubectl --kubeconfig "${KUBE_MERGED}" config use-context "${MANAGEMENT_CLUSTER}" >/dev/null
install -m 0600 "${KUBE_MERGED}" "${KUBE_DEFAULT}"

TALOS_DEFAULT="${TALOS_DIR}/config"
TALOS_MERGED="${TMP_DIR}/talosconfig"
cp -- "${TALOS_CONFIGS[0]}" "${TALOS_MERGED}"
TALOS_CONFIGS_TO_MERGE=("${TALOS_CONFIGS[@]:1}")
for talos_config in "${TALOS_CONFIGS_TO_MERGE[@]}"; do
  talosctl --talosconfig "${TALOS_MERGED}" config merge "${talos_config}" >/dev/null
done
talosctl --talosconfig "${TALOS_MERGED}" config context "${MANAGEMENT_CLUSTER}" >/dev/null
install -m 0600 "${TALOS_MERGED}" "${TALOS_DEFAULT}"

if [[ "${UPDATE_BASHRC}" == true ]]; then
  touch "${BASHRC}"
  BASHRC_TMP="$(mktemp "$(dirname -- "${BASHRC}")/.bashrc.labops.XXXXXX")"
  awk '
    $0 == "# BEGIN LABOPS KUBECONFIG" { skip = 1; next }
    $0 == "# END LABOPS KUBECONFIG"   { skip = 0; next }
    !skip { print }
  ' "${BASHRC}" >"${BASHRC_TMP}"
  {
    printf '\n# BEGIN LABOPS KUBECONFIG\n'
    printf 'export KUBECONFIG=%q\n' "${KUBE_DEFAULT}"
    printf 'export TALOSCONFIG=%q\n' "${TALOS_DEFAULT}"
    printf '# END LABOPS KUBECONFIG\n'
  } >>"${BASHRC_TMP}"
  chmod --reference="${BASHRC}" "${BASHRC_TMP}"
  mv -f -- "${BASHRC_TMP}" "${BASHRC}"
fi

printf 'Installed kubeconfigs:\n'
printf '  %s\n' "${CONFIG_PATHS[@]}"
printf '\nDefault Kubernetes config: %s\n' "${KUBE_DEFAULT}"
printf 'Default Talos config: %s\n' "${TALOS_DEFAULT}"
if [[ "${UPDATE_BASHRC}" == true ]]; then
  printf 'Updated %s; run: source %q\n' "${BASHRC}" "${BASHRC}"
else
  printf 'kubectl and talosctl will use their default configuration paths.\n'
fi
