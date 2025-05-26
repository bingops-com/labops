#!/usr/bin/bash

if [[ "${GITHUB_EVENT_NAME}" == "repository_dispatch" ]]; then
  echo "::notice:: Triggered by repository_dispatch. Using chart from payload."
  echo "{\"include\":[{\"chart\":\"${CHART_NAME}\",\"is_pr\":\"${IS_PR}\"}]}" > matrix.json
else
  echo "::notice:: Triggered by push/PR. Detecting modified Helm charts..."

  BEFORE_SHA="${GITHUB_EVENT_BEFORE:-}"
  if [ -z "$BEFORE_SHA" ] || ! git cat-file -e "$BEFORE_SHA^{commit}" 2>/dev/null; then
    BEFORE_SHA=$(git rev-parse HEAD~1)
  fi

  echo "::notice:: Comparing commits: $BEFORE_SHA → ${GITHUB_SHA}"
  diff_output=$(git diff --name-only "$BEFORE_SHA" "${GITHUB_SHA}")
  modified_charts=$(echo "$diff_output" | grep '^charts/[^/]\+' -o | cut -d/ -f2 | sort -u)

  if [ -z "$modified_charts" ]; then
    echo "::warning:: No modified Helm charts detected."
    echo '{"include":[]}' > matrix.json
  else
    IS_PR_FLAG="false"
    [[ "$GITHUB_EVENT_NAME" == "pull_request" ]] && IS_PR_FLAG="true"

    json_output="{\"include\":["
    first=true
    for chart in $modified_charts; do
      if [ "$first" = false ]; then
        json_output+=","
      fi
      json_output+="{\"chart\":\"$chart\",\"is_pr\":\"$IS_PR_FLAG\"}"
      first=false
    done
    json_output+="]}"
    echo "$json_output" > matrix.json
  fi
fi

cat matrix.json
echo "matrix=$(cat matrix.json)" >> "$GITHUB_OUTPUT"
