#!/usr/bin/env bash
# Opens a pull request that points a workload at the image just published.
# Runs only for images that declare docker/<image>/deploy-target, the manifest
# holding their "image:" line. Merging the pull request is the deployment.

set -euo pipefail

target_file="docker/${IMAGE_NAME}/deploy-target"
target=$(tr -d '[:space:]' < "$target_file")
image="ghcr.io/bingops-com/${IMAGE_NAME}"

# The timestamp tag is the only one unique to this build.
tag=$(grep -oE ':[0-9]{8}-[0-9]{6}$' <<< "$TAGS" | head -n 1 | tr -d ':' || true)
if [[ -z "$tag" ]]; then
  echo "::error::No timestamp tag among the published tags."
  exit 1
fi
if [[ ! -f "$target" ]]; then
  echo "::error::${target_file} points to a missing file: ${target}"
  exit 1
fi

sed -i -E "s|(image: ${image}):[^[:space:]]+|\1:${tag}|" "$target"
if git diff --quiet -- "$target"; then
  echo "::notice::${target} already uses ${image}:${tag}."
  exit 0
fi

branch="deploy/${IMAGE_NAME}-${tag}"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git switch --quiet --create "$branch"
git commit --quiet --all --message "chore(${IMAGE_NAME}): deploy image ${tag}"
git push --quiet origin "$branch"

gh pr create --base master --head "$branch" \
  --title "chore(${IMAGE_NAME}): deploy image ${tag}" \
  --body "Points \`${target}\` at \`${image}:${tag}\`, published by [this run](${RUN_URL}).

Merging deploys it: Argo CD reconciles the workload from \`master\`. Close the pull request to skip this build.

Pull requests opened by the workflow token do not start other workflows, so no checks run here; the change is the single image line."
