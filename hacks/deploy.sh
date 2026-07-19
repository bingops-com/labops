#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  ./hacks/deploy.sh diff <test|prod> [--app APP] [--revision REVISION]
  ./hacks/deploy.sh deploy <test|prod> [--app APP] [--revision REVISION]
  ./hacks/deploy.sh status <test|prod> [--app APP]
  ./hacks/deploy.sh restore <test|prod> [--app APP]

Without --app, every Git-backed Application in the environment is targeted.
Without --revision, the current Git branch is used. "dev" aliases "test".
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command '$1' is not available."
}

cleanup() {
  if [[ -n "${argocd_kubeconfig:-}" ]]; then
    rm -f -- "${argocd_kubeconfig}"
  fi
}

prepare_argocd_kubeconfig() {
  argocd_kubeconfig="$(mktemp "${TMPDIR:-/tmp}/labops-argocd-kubeconfig.XXXXXX")"
  chmod 600 "${argocd_kubeconfig}"
  kubectl config view --raw --minify --context "${cluster_context}" >"${argocd_kubeconfig}"
  KUBECONFIG="${argocd_kubeconfig}" kubectl config set-context --current --namespace argocd-system >/dev/null
}

current_branch() {
  local branch
  branch="$(git branch --show-current)"
  [[ -n "${branch}" ]] || die "HEAD is detached; specify --revision."
  printf '%s\n' "${branch}"
}

validate_revision() {
  git check-ref-format --branch "${revision}" >/dev/null 2>&1 || die "Invalid revision '${revision}'."
  git ls-remote --exit-code --heads origin "refs/heads/${revision}" >/dev/null 2>&1 || die "origin/${revision} does not exist; push it first."
}

configure_environment() {
  case "${environment}" in
    dev|test)
      environment="test"
      cluster_context="${LABTEST_CONTEXT:-labtest}"
      suffix="labtest"
      project="labops-labtest"
      baseline="master"
      ;;
    prod)
      cluster_context="${LABPROD_CONTEXT:-labprod}"
      suffix="labprod"
      project="labops-labprod"
      baseline="master"
      ;;
    *)
      die "Environment must be 'test' or 'prod'."
      ;;
  esac
}

load_applications() {
  local applications_json
  applications_json="$(kubectl --context "${cluster_context}" --namespace argocd-system get applications -o json)"

  if [[ -n "${app_name}" ]]; then
    [[ "${app_name}" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || die "Application name must be a lowercase DNS label."
    applications=("${app_name}-${suffix}")
    jq --exit-status --arg name "${applications[0]}" --arg project "${project}" --arg repo "${LABOPS_REPO_URL}" '.items[] | select(.metadata.name == $name and .spec.project == $project and .spec.source.repoURL == $repo)' <<<"${applications_json}" >/dev/null || die "Git-backed Application ${applications[0]} does not exist in ${project}."
    return
  fi

  mapfile -t applications < <(jq --raw-output --arg project "${project}" --arg repo "${LABOPS_REPO_URL}" '.items[] | select(.spec.project == $project and .spec.source.repoURL == $repo) | .metadata.name' <<<"${applications_json}" | sort)
  [[ ${#applications[@]} -gt 0 ]] || die "No Git-backed Applications found for ${project}."
}

run_diff() {
  local label="$1"
  shift
  local result
  echo
  echo "== ${label} =="
  set +e
  "$@"
  result=$?
  set -e
  if [[ ${result} -eq 0 ]]; then
    echo "No changes."
  fi
  [[ ${result} -le 1 ]] || return "${result}"
}

show_diffs() {
  local application
  prepare_argocd_kubeconfig

  for application in "${applications[@]}"; do
    run_diff "${application}" env KUBECONFIG="${argocd_kubeconfig}" KUBECTL_EXTERNAL_DIFF="diff --color=always --unified" argocd --core app diff "${application}" --revision "${revision}"
  done
}

patch_revision() {
  local application="$1" target_revision="$2" annotation_value="$3"
  kubectl --context "${cluster_context}" --namespace argocd-system patch application "${application}" --type merge --patch "$(jq --null-input --arg revision "${target_revision}" --arg annotation "${annotation_value}" '{metadata:{annotations:{"labops.bingops.com/deploy-revision":($annotation | if . == "" then null else . end)}},spec:{source:{targetRevision:$revision}}}')"
}

action="${1:-}"
environment="${2:-}"
if [[ "${action}" == "-h" || "${action}" == "--help" ]]; then
  usage
  exit 0
fi
shift $(( $# >= 2 ? 2 : $# ))
app_name=""
revision=""
LABOPS_REPO_URL="${LABOPS_REPO_URL:-https://github.com/bingops-com/labops.git}"
argocd_kubeconfig=""
declare -a applications=()
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      [[ $# -ge 2 ]] || die "--app requires a value."
      app_name="$2"
      shift 2
      ;;
    --revision)
      [[ $# -ge 2 ]] || die "--revision requires a value."
      revision="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument '$1'."
      ;;
  esac
done

[[ -n "${action}" && -n "${environment}" ]] || { usage; exit 1; }
require_command git
require_command jq
require_command kubectl
configure_environment
load_applications

case "${action}" in
  diff)
    require_command argocd
    revision="${revision:-$(current_branch)}"
    validate_revision
    show_diffs
    ;;
  deploy)
    require_command argocd
    revision="${revision:-$(current_branch)}"
    validate_revision
    show_diffs
    target="${app_name:-all Git-backed applications}"
    confirmation="deploy ${environment}"
    echo
    echo "Target: ${target} on ${environment}"
    read -r -p "Type '${confirmation}' to apply the changes: " answer
    [[ "${answer}" == "${confirmation}" ]] || die "Deployment cancelled."
    for application in "${applications[@]}"; do
      patch_revision "${application}" "${revision}" "${revision}"
    done
    echo "${#applications[@]} application(s) now follow ${revision} on ${environment}."
    ;;
  status)
    [[ -z "${revision}" ]] || die "--revision is not valid with status."
    for application in "${applications[@]}"; do
      kubectl --context "${cluster_context}" --namespace argocd-system get application "${application}" -o custom-columns='APPLICATION:.metadata.name,REVISION:.spec.source.targetRevision,SYNC:.status.sync.status,HEALTH:.status.health.status' --no-headers
    done
    ;;
  restore)
    [[ -z "${revision}" ]] || die "--revision is not valid with restore."
    for application in "${applications[@]}"; do
      patch_revision "${application}" "${baseline}" ""
    done
    echo "${#applications[@]} application(s) restored to ${baseline} on ${environment}."
    ;;
  *)
    usage
    exit 1
    ;;
esac
