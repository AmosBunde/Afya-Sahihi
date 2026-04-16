#!/usr/bin/env bash
# Every repository module that executes SQL must SET LOCAL statement_timeout.
set -euo pipefail
RC=0
for f in "$@"; do
  if grep -q 'pool.acquire\|conn.fetch\|conn.execute' "$f"; then
    if ! grep -q 'SET LOCAL statement_timeout' "$f"; then
      echo "❌ $f uses asyncpg but no 'SET LOCAL statement_timeout' found." >&2
      echo "   See docs/skills/afya-sahihi-principal/SKILL.md §7" >&2
      RC=1
    fi
  fi
done
exit $RC
