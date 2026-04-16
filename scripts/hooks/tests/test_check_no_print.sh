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

# Red: bare print() is rejected.
case_start "red: file with print() is rejected"
cat > "$D/bad.py" <<'PY'
def handler():
    print("oops")
PY
set +e
"$HOOK" "$D/bad.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 1 "$rc" && pass

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
