#!/usr/bin/env bash

if [[ "${GITHUB_EVENT_NAME}" == "repository_dispatch" ]]; then
  echo "::notice:: Triggered by repository_dispatch. Using image from payload."
  echo "{\"include\":[{\"image\":\"${IMAGE_NAME}\",\"is_pr\":\"${IS_PR}\"}]}" > matrix.json
else
  echo "::notice:: Triggered by push/PR. Detecting modified docker contexts..."

  BEFORE_SHA="${GITHUB_EVENT_BEFORE}"
  if [ -z "$BEFORE_SHA" ] || ! git cat-file -e "$BEFORE_SHA^{commit}" 2>/dev/null; then
    BEFORE_SHA=$(git rev-parse HEAD~1)
  fi

  echo "::notice:: Comparing commits: $BEFORE_SHA → ${GITHUB_SHA}"
  modified_dirs=$(git diff --name-only "$BEFORE_SHA" "${GITHUB_SHA}" | grep '^docker/' | cut -d/ -f2 | sort -u)

  if [ -z "$modified_dirs" ]; then
    echo "::warning:: No modified Docker contexts detected."
    echo '{"include":[]}' > matrix.json
  else
    if [[ "$GITHUB_EVENT_NAME" == "pull_request" ]]; then
      IS_PR_FLAG=true
    else
      IS_PR_FLAG=false
    fi

    json_output="{\"include\":["
    first=true
    for dir in $modified_dirs; do
      if [ "$first" = false ]; then
        json_output+=","
      fi
      json_output+="{\"image\":\"$dir\",\"is_pr\":\"$IS_PR_FLAG\"}"
      first=false
    done
    json_output+="]}"
    echo "$json_output" > matrix.json
  fi
fi

cat matrix.json
echo "matrix=$(cat matrix.json)" >> $GITHUB_OUTPUT
