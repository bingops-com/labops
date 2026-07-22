#!/usr/bin/env bash

set -euo pipefail

usage() {
  echo "Usage: $0 <labtest|labprod>" >&2
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

cluster=$1
case "$cluster" in
  labtest)
    token_variable=BWS_LABTEST_ACCESS_TOKEN
    namespaces=(argocd-system cert-manager postgresql)
    ;;
  labprod)
    token_variable=BWS_LABPROD_ACCESS_TOKEN
    namespaces=(argocd-system authentik cert-manager cloudflare)
    ;;
  *)
    usage
    exit 2
    ;;
esac

if [[ -z ${!token_variable:-} ]]; then
  echo "Required environment variable $token_variable is not set." >&2
  exit 1
fi

if ! kubectl config get-contexts "$cluster" >/dev/null 2>&1; then
  echo "kubectl context $cluster does not exist." >&2
  exit 1
fi

for namespace in "${namespaces[@]}"; do
  if ! kubectl --context "$cluster" get namespace "$namespace" >/dev/null 2>&1; then
    echo "Namespace $namespace does not exist in $cluster; bootstrap GitOps prerequisites first." >&2
    exit 1
  fi
done

for namespace in "${namespaces[@]}"; do
  printf '%s' "${!token_variable}" | kubectl --context "$cluster" --namespace "$namespace" create secret generic bw-auth-token --from-file=token=/dev/stdin --dry-run=client -o yaml | kubectl --context "$cluster" --namespace "$namespace" apply -f - >/dev/null
  echo "Reconciled bw-auth-token in $cluster/$namespace."
done
