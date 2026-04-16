#!/usr/bin/env bash
# If settings.py changes, every new field must appear in at least one env/ file.
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

# Collect all env var names from env/ files
ENV_NAMES=$(grep -hE '^[A-Z_][A-Z0-9_]*=' env/*.env env/.env.* 2>/dev/null \
             | awk -F= '{print $1}' | sort -u)

MISSING=0
for field in $PY_FIELDS; do
  if ! grep -qxF "$field" <<<"$ENV_NAMES"; then
    echo "❌ settings.py declares '$field' but it is absent from env/" >&2
    MISSING=1
  fi
done
exit $MISSING
