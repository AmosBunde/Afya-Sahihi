#!/usr/bin/env bash
# check_asyncpg_timeouts.sh
#
# Purpose: every repository file that uses asyncpg (calls `pool.acquire`,
#   `conn.fetch`, or `conn.execute`) must also call
#   `SET LOCAL statement_timeout`. Without it, a bad query runs until the
#   connection drops, holding a pool slot and starving the rest of the
#   service. See SKILL.md §0 non-negotiable #6 and §7 repository pattern.
#
# Inputs:   file paths passed as arguments by pre-commit (one per changed file).
# Exit 0:   no asyncpg usage in the file, or every file that uses asyncpg
#           also contains a SET LOCAL statement_timeout string.
# Exit 1:   asyncpg usage present without a matching SET LOCAL statement_timeout;
#           file printed to stderr with a pointer to SKILL.md §7.
# Example:  `await conn.fetch("SELECT 1")` without a preceding
#           `await conn.execute("SET LOCAL statement_timeout = '5s'")` fails.
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
