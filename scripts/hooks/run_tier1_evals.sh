#!/usr/bin/env bash
# run_tier1_evals.sh
#
# Purpose: run the Inspect AI Tier 1 unit eval suite before `git push`.
#   Tier 1 is the pre-push gate that catches regressions in the golden
#   retrieval/generation set. See ADR-0006 and issue #27.
#
# Inputs:   none. Expected fixture: eval/tier1/golden_set.py.
# Env:      AFYA_SAHIHI_SKIP_TIER1 — set to any value to short-circuit
#           the run (e.g. for WIP branches). CI does not honor this.
# Exit 0:   eval suite passed, or the golden set is not yet present
#           (pre-M6 repo state; the hook warns and proceeds).
# Exit 1:   eval suite failed or timed out (120s cap).
# Runtime:  must complete in under 120 seconds; enforced via `timeout`.
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
