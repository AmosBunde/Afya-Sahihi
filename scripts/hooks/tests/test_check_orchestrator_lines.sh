#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"
HOOK="$HOOKS_DIR/check_orchestrator_lines.sh"

# Run hook from a fake working directory containing backend/app/orchestrator.py.
# The hook reads a fixed relative path, so we cd into the fixture dir.

case_start "green: missing orchestrator.py exits 0 (no-op)"
D=$(mktmp_dir)
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 0 "$rc" && pass

case_start "green: 399-line orchestrator.py is accepted"
mkdir -p "$D/backend/app"
python3 -c "print('x = 1\n' * 399, end='')" > "$D/backend/app/orchestrator.py"
# Confirm line count
if [ "$(wc -l < "$D/backend/app/orchestrator.py")" -ne 399 ]; then
  fail "fixture line count setup wrong"
fi
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 0 "$rc" && pass

case_start "red: 401-line orchestrator.py is rejected"
python3 -c "print('x = 1\n' * 401, end='')" > "$D/backend/app/orchestrator.py"
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 1 "$rc" && pass

finish
