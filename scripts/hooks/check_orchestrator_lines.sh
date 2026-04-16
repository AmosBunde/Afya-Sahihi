#!/usr/bin/env bash
# check_orchestrator_lines.sh
#
# Purpose: cap `backend/app/orchestrator.py` at 400 lines. ADR-0003 mandates
#   the orchestrator stays readable top-to-bottom; past 400 lines it starts
#   hiding control flow. When the cap is hit, extract a helper module
#   instead of raising it.
#
# Inputs:   reads backend/app/orchestrator.py; takes no arguments.
# Exit 0:   file missing (pre-backend repo state), or <= 400 lines.
# Exit 1:   > 400 lines. Error names the current line count and the cap,
#           with a pointer to ADR-0003.
# Escape:   do NOT `--no-verify`; write a new ADR that supersedes 0003.
set -euo pipefail
f="backend/app/orchestrator.py"
[[ -f "$f" ]] || exit 0
LINES=$(wc -l < "$f")
if [[ "$LINES" -gt 400 ]]; then
  echo "❌ $f is $LINES lines. Hard cap is 400 (ADR-0003)." >&2
  echo "   Extract a helper module. Do NOT raise the cap without a new ADR." >&2
  exit 1
fi
