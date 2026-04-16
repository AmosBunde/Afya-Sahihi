#!/usr/bin/env bash
# ADR-0003: orchestrator.py must stay under 400 lines.
set -euo pipefail
f="backend/app/orchestrator.py"
[[ -f "$f" ]] || exit 0
LINES=$(wc -l < "$f")
if [[ "$LINES" -gt 400 ]]; then
  echo "❌ $f is $LINES lines. Hard cap is 400 (ADR-0003)." >&2
  echo "   Extract a helper module. Do NOT raise the cap without a new ADR." >&2
  exit 1
fi
