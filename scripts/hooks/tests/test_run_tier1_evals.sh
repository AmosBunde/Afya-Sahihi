#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"
HOOK="$HOOKS_DIR/run_tier1_evals.sh"

# Green: the golden set does not exist yet — hook prints a warning and exits 0.
# This is the intended behavior until issue #27 lands the eval task.
case_start "green: missing eval/tier1/golden_set.py warns but exits 0"
D=$(mktmp_dir)
mkdir -p "$D/eval"
set +e
( cd "$D" && "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 0 "$rc" && pass

# Green: AFYA_SAHIHI_SKIP_TIER1 env var short-circuits the hook.
case_start "green: AFYA_SAHIHI_SKIP_TIER1=1 exits 0 without running"
set +e
( cd "$D" && AFYA_SAHIHI_SKIP_TIER1=1 "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 0 "$rc" && pass

# Red: golden set present but `uv` resolves to a failing stub — the hook
# should fail. We prepend a fake-bin dir to PATH containing a `uv` that
# exits nonzero; real bash/timeout/coreutils stay resolvable.
case_start "red: golden_set.py present but uv returns nonzero fails with actionable error"
mkdir -p "$D/eval/tier1" "$D/fake_bin"
: > "$D/eval/tier1/golden_set.py"
cat > "$D/fake_bin/uv" <<'STUB'
#!/usr/bin/env bash
exit 1
STUB
chmod +x "$D/fake_bin/uv"
set +e
( cd "$D" && PATH="$D/fake_bin:$PATH" "$HOOK" >/dev/null 2>&1 ); rc=$?
set -e
assert_rc 1 "$rc" && pass

finish
