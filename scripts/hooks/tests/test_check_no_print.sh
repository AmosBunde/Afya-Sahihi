#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"
HOOK="$HOOKS_DIR/check_no_print.sh"

# Green: logger usage, no print.
case_start "green: file using logger only is accepted"
D=$(mktmp_dir)
cat > "$D/ok.py" <<'PY'
def handler():
    logger.info("done", extra={"query_id": "q1"})
PY
set +e
"$HOOK" "$D/ok.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 0 "$rc" && pass

# Red: bare print() is rejected with an actionable pointer to the logger.
case_start "red: file with print() is rejected and names 'structured logger'"
cat > "$D/bad.py" <<'PY'
def handler():
    print("oops")
PY
run_hook_capture "$HOOK" "$D/bad.py"
assert_rc 1 "$CAPTURED_RC" && assert_stderr_contains "structured logger" && pass

# Green-with-noqa: print() with '# noqa: T201' is tolerated.
case_start "green: print() with 'noqa: T201' escape hatch is accepted"
cat > "$D/escape.py" <<'PY'
def tool():
    print("cli output")  # noqa: T201
PY
set +e
"$HOOK" "$D/escape.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 0 "$rc" && pass

finish
