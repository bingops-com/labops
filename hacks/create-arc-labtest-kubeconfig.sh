#!/usr/bin/env bash

set -euo pipefail

context=${LABTEST_CONTEXT:-labtest}
namespace=argocd-system
service_account=labtest-pr-deployer
token_secret=labtest-pr-deployer-token
output=${1:-${XDG_CONFIG_HOME:-$HOME/.config}/labops/arc-labtest-kubeconfig}

for command in kubectl jq base64; do
  command -v "$command" >/dev/null 2>&1 || { echo "Required command '$command' is unavailable." >&2; exit 1; }
done

kubectl config get-contexts "$context" >/dev/null 2>&1 || { echo "kubectl context $context does not exist." >&2; exit 1; }
kubectl --context "$context" --namespace "$namespace" get serviceaccount "$service_account" >/dev/null
kubectl --context "$context" --namespace "$namespace" get secret "$token_secret" >/dev/null

cluster=$(kubectl --context "$context" config view --raw --flatten --minify -o json)
server=$(jq --exit-status --raw-output '.clusters[0].cluster.server' <<<"$cluster")
certificate_authority_data=$(jq --exit-status --raw-output '.clusters[0].cluster["certificate-authority-data"]' <<<"$cluster")
token_data=$(kubectl --context "$context" --namespace "$namespace" get secret "$token_secret" -o json)
token=$(jq --exit-status --raw-output '.data.token' <<<"$token_data" | base64 --decode)

mkdir -p "$(dirname "$output")"
umask 077
temporary=$(mktemp "${output}.tmp.XXXXXX")
trap 'rm -f "$temporary"' EXIT
printf '%s\n' 'apiVersion: v1' 'kind: Config' 'clusters:' '- name: labtest' '  cluster:' "    server: $server" "    certificate-authority-data: $certificate_authority_data" 'contexts:' '- name: labtest' '  context:' '    cluster: labtest' "    namespace: $namespace" "    user: $service_account" 'current-context: labtest' 'users:' "- name: $service_account" '  user:' "    token: $token" >"$temporary"
mv "$temporary" "$output"
trap - EXIT

KUBECONFIG="$output" kubectl auth can-i patch applications.argoproj.io --namespace "$namespace" | grep -qx yes
if KUBECONFIG="$output" kubectl auth can-i get secrets --namespace "$namespace" | grep -qx yes; then
  echo "Generated credential can read Secrets; refusing to keep it." >&2
  rm -f "$output"
  exit 1
fi

echo "Created least-privilege kubeconfig at $output (mode 0600)."
echo "Store the complete file as the Bitwarden labprod secret arc-labtest-kubeconfig, then securely remove the local file."
