#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"
HOOK="$HOOKS_DIR/check_span_per_transition.sh"

case_start "green: missing orchestrator.py exits 0 (no-op)"
D=$(mktmp_dir)
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 0 "$rc" && pass

case_start "green: every private async step calls start_as_current_span"
mkdir -p "$D/backend/app"
cat > "$D/backend/app/orchestrator.py" <<'PY'
class Orchestrator:
    async def _step(self, state):
        with tracer.start_as_current_span("orchestrator.step"):
            return state
PY
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 0 "$rc" && pass

case_start "red: private async step missing start_as_current_span is rejected and names SKILL.md §10"
cat > "$D/backend/app/orchestrator.py" <<'PY'
class Orchestrator:
    async def _step(self, state):
        return state
PY
run_hook_capture bash -c "cd '$D' && '$HOOK'"
assert_rc 1 "$CAPTURED_RC" && assert_stderr_contains "SKILL.md §10" && pass

finish
