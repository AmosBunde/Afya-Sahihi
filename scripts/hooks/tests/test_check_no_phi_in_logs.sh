#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"
HOOK="$HOOKS_DIR/check_no_phi_in_logs.sh"

# Green: logs with allowed keys only.
case_start "green: logger call with query_id is accepted"
D=$(mktmp_dir)
cat > "$D/ok.py" <<'PY'
logger.info("retrieval complete", extra={"query_id": q.id, "query_length": 42})
PY
set +e
"$HOOK" "$D/ok.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 0 "$rc" && pass

# Red: logs query_text (PHI). Message must coach the fix: query_id, not text.
case_start "red: logger call with query_text is rejected with 'query_id, not query_text' coaching"
cat > "$D/bad.py" <<'PY'
logger.info("received", extra={"query_text": q.text})
PY
run_hook_capture "$HOOK" "$D/bad.py"
assert_rc 1 "$CAPTURED_RC" && assert_stderr_contains "query_id, not query_text" && pass

# Red: logs patient_name (PHI).
case_start "red: logger call with patient_name is rejected"
cat > "$D/bad2.py" <<'PY'
logger.warning("issue", extra={"patient_name": pt.name})
PY
set +e
"$HOOK" "$D/bad2.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 1 "$rc" && pass

finish
