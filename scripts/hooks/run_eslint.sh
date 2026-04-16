#!/usr/bin/env bash
set -euo pipefail
if [ -d frontend/node_modules ]; then
  cd frontend && npx eslint --max-warnings=0 "src/**/*.{ts,tsx}"
else
  echo "frontend/node_modules missing, skipping"
fi
