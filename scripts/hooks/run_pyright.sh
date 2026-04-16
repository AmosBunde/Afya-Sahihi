#!/usr/bin/env bash
set -euo pipefail
if command -v pyright >/dev/null 2>&1; then
  pyright --project backend/pyproject.toml
else
  echo "pyright not installed, skipping. Install: pipx install pyright"
fi
