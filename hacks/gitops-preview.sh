#!/usr/bin/env bash

set -euo pipefail

usage() {
  echo "Usage: $0 up <app-name> <remote-feature-branch> | down <app-name>" >&2
}

action="${1:-}"
app_name="${2:-}"
revision="${3:-}"
kubeconfig="${LABTEST_KUBECONFIG:-${HOME}/.kube/lab_test}"
repo_url="${LABOPS_REPO_URL:-https://github.com/bingops-com/labops.git}"

if [[ ! "${app_name}" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]]; then
  echo "Application name must be a valid lowercase DNS label." >&2
  usage
  exit 1
fi

application_name="${app_name}-preview"

case "${action}" in
  up)
    if [[ -z "${revision}" ]]; then
      usage
      exit 1
    fi

    if ! git ls-remote --exit-code --heads origin "refs/heads/${revision}" >/dev/null; then
      echo "Remote feature branch origin/${revision} does not exist; push it before creating the preview." >&2
      exit 1
    fi

    if [[ ! -f "apps/workloads/${app_name}/clusters/labtest/kustomization.yaml" ]]; then
      echo "Missing apps/workloads/${app_name}/clusters/labtest/kustomization.yaml in the working tree." >&2
      exit 1
    fi

    KUBECONFIG="${kubeconfig}" kubectl apply -f - <<EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: ${application_name}
  namespace: argocd-system
  finalizers:
    - resources-finalizer.argocd.argoproj.io
  labels:
    app.kubernetes.io/managed-by: labops-preview
    labops.bingops.com/environment: labtest
spec:
  project: labops-labtest
  source:
    repoURL: ${repo_url}
    targetRevision: ${revision}
    path: apps/workloads/${app_name}/clusters/labtest
  destination:
    server: https://kubernetes.default.svc
    namespace: ${app_name}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
EOF
    echo "Preview ${application_name} now follows ${revision} on labtest."
    ;;
  down)
    if [[ -n "${revision}" ]]; then
      usage
      exit 1
    fi

    KUBECONFIG="${kubeconfig}" kubectl delete application "${application_name}" --namespace argocd-system --ignore-not-found --wait=true
    echo "Preview ${application_name} and its managed resources have been removed from labtest."
    ;;
  *)
    usage
    exit 1
    ;;
esac
