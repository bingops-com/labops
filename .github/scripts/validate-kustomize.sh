#!/usr/bin/env bash

set -euo pipefail

mapfile -t kustomizations < <(find apps/gitops/clusters apps/platform apps/workloads -type f -name kustomization.yaml -not -path '*/charts/*' -print | sort)

if [[ ${#kustomizations[@]} -eq 0 ]]; then
  echo "No Kustomize overlays found." >&2
  exit 1
fi

for kustomization in "${kustomizations[@]}"; do
  directory=${kustomization%/kustomization.yaml}
  echo "Rendering $directory"
  kubectl kustomize "$directory" --enable-helm >/dev/null
done
