#!/usr/bin/env bash
# check_env_documented.sh
#
# Purpose: every field declared on `class Settings` in backend/app/settings.py
#   must appear (upper-cased) in at least one of the service env files under
#   env/. Prevents a runtime field being referenced by code without a
#   documented value, which is how production outages start.
#
# Inputs:   reads backend/app/settings.py and env/*.env; takes no arguments.
# Exit 0:   either settings.py is absent (pre-backend repo state), or every
#           field is present in at least one env/ file.
# Exit 1:   one or more fields declared but not documented in env/.
# Example:  adding `redis_url: str` to Settings without adding `REDIS_URL=` to
#           env/gateway.env fails the hook with the missing field name.
set -euo pipefail
SETTINGS="backend/app/settings.py"
[[ -f "$SETTINGS" ]] || exit 0

# Extract the Settings field names from settings.py
PY_FIELDS=$(python3 -c "
import ast, sys
try:
    src = open('$SETTINGS').read()
    tree = ast.parse(src)
except Exception:
    sys.exit(0)
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == 'Settings':
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                print(stmt.target.id.upper())
")

# Collect all env var names from env/ files. Use nullglob so a fresh repo
# (env/ empty or missing one of the two glob patterns) does not cause grep
# to fail on a literal pattern and tank the hook with exit 2.
ENV_NAMES=""
shopt -s nullglob
ENV_FILES=(env/*.env env/.env.*)
shopt -u nullglob
if [ "${#ENV_FILES[@]}" -gt 0 ]; then
  ENV_NAMES=$(grep -hE '^[A-Z_][A-Z0-9_]*=' "${ENV_FILES[@]}" 2>/dev/null \
               | awk -F= '{print $1}' | sort -u)
fi

MISSING=0
for field in $PY_FIELDS; do
  if ! grep -qxF "$field" <<<"$ENV_NAMES"; then
    echo "❌ settings.py declares '$field' but it is absent from env/" >&2
    MISSING=1
  fi
done
exit $MISSING
