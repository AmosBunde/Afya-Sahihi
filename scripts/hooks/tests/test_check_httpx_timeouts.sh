#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"
HOOK="$HOOKS_DIR/check_httpx_timeouts.sh"

# Green: AsyncClient with explicit timeout=.
case_start "green: AsyncClient with timeout= kwarg is accepted"
D=$(mktmp_dir)
cat > "$D/ok.py" <<'PY'
import httpx
client = httpx.AsyncClient(base_url="https://x", timeout=httpx.Timeout(10))
PY
set +e
"$HOOK" "$D/ok.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 0 "$rc" && pass

# Red: AsyncClient without timeout=.
case_start "red: AsyncClient without timeout= is rejected"
cat > "$D/bad.py" <<'PY'
import httpx
client = httpx.AsyncClient(base_url="https://x")
PY
set +e
"$HOOK" "$D/bad.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 1 "$rc" && pass

# Green: bare AsyncClient() (no httpx prefix) with timeout=.
case_start "green: bare AsyncClient() with timeout= is accepted"
cat > "$D/ok2.py" <<'PY'
from httpx import AsyncClient
client = AsyncClient(timeout=5.0)
PY
set +e
"$HOOK" "$D/ok2.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 0 "$rc" && pass

finish
