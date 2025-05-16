#!/usr/bin/bash

PREFIX="dev-"

if [[ "${IS_PR}" == "true" ]]; then
  echo "prefix=${PREFIX}" >> $GITHUB_OUTPUT
else
  echo "prefix=" >> $GITHUB_OUTPUT
fi
