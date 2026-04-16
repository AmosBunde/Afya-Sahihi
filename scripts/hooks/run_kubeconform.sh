#!/usr/bin/env bash
set -euo pipefail
if command -v kubeconform >/dev/null 2>&1; then
  kubeconform -strict -ignore-missing-schemas deploy/k3s/
else
  echo "kubeconform not installed, skipping. See https://github.com/yannh/kubeconform"
fi
