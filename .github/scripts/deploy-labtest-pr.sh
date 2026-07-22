#!/usr/bin/env bash

set -euo pipefail

action=${1:-}
context=${LABTEST_CONTEXT:-labtest}
namespace=argocd-system
root_application=labops-labtest
project=labops-labtest
repository_url=https://github.com/bingops-com/labops.git
baseline=master
owner_annotation=labops.bingops.com/deployed-pr
sha_annotation=labops.bingops.com/deployed-sha
revision_annotation=labops.bingops.com/deploy-revision
timeout_seconds=${LABTEST_DEPLOY_TIMEOUT_SECONDS:-600}

die() {
  echo "Error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command '$1' is unavailable."
}

application_annotation() {
  local application=$1 annotation=$2
  kubectl --context "$context" --namespace "$namespace" get application "$application" -o json | jq --raw-output --arg annotation "$annotation" '.metadata.annotations[$annotation] // ""'
}

patch_application() {
  local application=$1 revision=$2 owner=$3 sha=$4
  local patch
  patch=$(jq --null-input --arg revision "$revision" --arg owner_annotation "$owner_annotation" --arg sha_annotation "$sha_annotation" --arg revision_annotation "$revision_annotation" --arg owner "$owner" --arg sha "$sha" '{metadata:{annotations:{($owner_annotation):($owner | if . == "" then null else . end),($sha_annotation):($sha | if . == "" then null else . end),($revision_annotation):($revision | if . == "master" then null else . end)}},spec:{source:{targetRevision:$revision}}}')
  kubectl --context "$context" --namespace "$namespace" patch application "$application" --type merge --patch "$patch" >/dev/null
}

wait_for_application() {
  local application=$1 revision=$2 require_healthy=$3
  local deadline=$((SECONDS + timeout_seconds))
  local state sync health resolved target
  while (( SECONDS < deadline )); do
    state=$(kubectl --context "$context" --namespace "$namespace" get application "$application" -o json)
    sync=$(jq --raw-output '.status.sync.status // "Unknown"' <<<"$state")
    health=$(jq --raw-output '.status.health.status // "Unknown"' <<<"$state")
    resolved=$(jq --raw-output '.status.sync.revision // ""' <<<"$state")
    target=$(jq --raw-output '.spec.source.targetRevision // ""' <<<"$state")
    if [[ "$sync" == Synced && "$target" == "$revision" && ( ! "$revision" =~ ^[0-9a-f]{40}$ || "$resolved" == "$revision" ) && ( "$require_healthy" == false || "$health" == Healthy ) ]]; then
      return
    fi
    sleep 5
  done
  die "$application did not reach revision $revision (target=$target sync=$sync health=$health resolved=$resolved)."
}

git_backed_applications() {
  kubectl --context "$context" --namespace "$namespace" get applications -o json | jq --raw-output --arg project "$project" --arg repository_url "$repository_url" '.items[] | select(.spec.project == $project and .spec.source.repoURL == $repository_url) | .metadata.name' | sort
}

comment() {
  gh pr comment "$LABTEST_PR_NUMBER" --repo "$GITHUB_REPOSITORY" --body "$1" >/dev/null
}

validate_input() {
  [[ ${LABTEST_PR_NUMBER:-} =~ ^[1-9][0-9]*$ ]] || die "LABTEST_PR_NUMBER must be numeric."
  [[ ${LABTEST_HEAD_SHA:-} =~ ^[0-9a-f]{40}$ ]] || die "LABTEST_HEAD_SHA must be a full commit SHA."
  [[ ${LABTEST_HEAD_REF:-} == feat/* || ${LABTEST_HEAD_REF:-} == fix/* ]] || die "Only feat/* and fix/* branches may use labtest."
  [[ ${GITHUB_REPOSITORY:-} == bingops-com/labops ]] || die "Unexpected repository ${GITHUB_REPOSITORY:-unset}."
}

deploy() {
  local previous_owner
  local -a applications=()
  previous_owner=$(application_annotation "$root_application" "$owner_annotation")

  patch_application "$root_application" "$LABTEST_HEAD_SHA" "$LABTEST_PR_NUMBER" "$LABTEST_HEAD_SHA"
  wait_for_application "$root_application" "$LABTEST_HEAD_SHA" false

  mapfile -t applications < <(git_backed_applications)
  [[ ${#applications[@]} -gt 0 ]] || die "No Git-backed labtest Applications were found."
  for application in "${applications[@]}"; do
    patch_application "$application" "$LABTEST_HEAD_SHA" "$LABTEST_PR_NUMBER" "$LABTEST_HEAD_SHA"
  done
  for application in "${applications[@]}"; do
    wait_for_application "$application" "$LABTEST_HEAD_SHA" false
  done
  wait_for_application "$root_application" "$LABTEST_HEAD_SHA" true

  if [[ -n "$previous_owner" && "$previous_owner" != "$LABTEST_PR_NUMBER" ]]; then
    gh pr comment "$previous_owner" --repo "$GITHUB_REPOSITORY" --body "labtest was reassigned to PR #$LABTEST_PR_NUMBER at commit \`$LABTEST_HEAD_SHA\`." >/dev/null || true
  fi
  comment "labtest is deployed from \`$LABTEST_HEAD_SHA\` and the root Application is Synced/Healthy. This PR currently owns the shared test slot."
}

restore() {
  local current_owner
  local -a applications=()
  current_owner=$(application_annotation "$root_application" "$owner_annotation")
  if [[ "$current_owner" != "$LABTEST_PR_NUMBER" ]]; then
    comment "No labtest restore was needed: the shared slot is not owned by this PR."
    return
  fi

  mapfile -t applications < <(git_backed_applications)
  for application in "${applications[@]}"; do
    if [[ $(application_annotation "$application" "$owner_annotation") == "$LABTEST_PR_NUMBER" ]]; then
      patch_application "$application" "$baseline" "" ""
    fi
  done
  patch_application "$root_application" "$baseline" "" ""
  wait_for_application "$root_application" "$baseline" true
  comment "labtest was restored to \`master\` because this PR released the shared test slot."
}

require_command gh
require_command jq
require_command kubectl
validate_input

case "$action" in
  deploy) deploy ;;
  restore) restore ;;
  *) die "Usage: $0 <deploy|restore>" ;;
esac
