#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"
HOOK="$HOOKS_DIR/check_asyncpg_timeouts.sh"

# Green: file with no asyncpg calls at all.
case_start "green: file with no asyncpg usage is accepted"
D=$(mktmp_dir)
cat > "$D/ok.py" <<'PY'
def not_db():
    return 42
PY
set +e
"$HOOK" "$D/ok.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 0 "$rc" && pass

# Green: asyncpg call WITH SET LOCAL statement_timeout.
case_start "green: asyncpg call with SET LOCAL statement_timeout is accepted"
cat > "$D/ok2.py" <<'PY'
async def q(pool):
    async with pool.acquire() as conn:
        await conn.execute("SET LOCAL statement_timeout = '5s'")
        return await conn.fetch("SELECT 1")
PY
set +e
"$HOOK" "$D/ok2.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 0 "$rc" && pass

# Red: asyncpg call without statement_timeout.
case_start "red: asyncpg call without SET LOCAL statement_timeout is rejected"
cat > "$D/bad.py" <<'PY'
async def q(pool):
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT 1")
PY
set +e
"$HOOK" "$D/bad.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 1 "$rc" && pass

finish
