#!/usr/bin/env bash
set -euo pipefail
if ! command -v crictl >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq cri-tools=1.36.0-1.1
  apt-mark hold cri-tools >/dev/null
fi
