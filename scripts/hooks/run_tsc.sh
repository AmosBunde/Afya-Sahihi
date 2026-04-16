#!/usr/bin/env bash
set -euo pipefail
if [ -d frontend/node_modules ]; then
  cd frontend && npx tsc --noEmit
else
  echo "frontend/node_modules missing, skipping"
fi
