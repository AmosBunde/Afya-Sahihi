#!/usr/bin/env bash
# Run Inspect AI Tier 1 evals before push. Must complete in <120s.
set -euo pipefail
if [[ -z "${AFYA_SAHIHI_SKIP_TIER1:-}" ]]; then
  cd eval
  if [[ -f tier1/golden_set.py ]]; then
    timeout 120 uv run inspect eval tier1/golden_set.py --model afya-sahihi --limit 50 \
      || { echo "❌ Tier 1 evals failed or timed out." >&2; exit 1; }
  else
    echo "⚠️  eval/tier1/golden_set.py not present yet. Skipping."
  fi
else
  echo "⚠️  AFYA_SAHIHI_SKIP_TIER1 set, skipping Tier 1 evals."
fi
