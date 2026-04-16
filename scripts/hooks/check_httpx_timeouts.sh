#!/usr/bin/env bash
# check_httpx_timeouts.sh
#
# Purpose: every `httpx.AsyncClient(...)` (or bare `AsyncClient(...)` when
#   imported from httpx) constructor call must pass `timeout=` explicitly.
#   A request-path client without a timeout hangs the request forever when
#   the upstream stalls, violating the "every external call has a timeout"
#   non-negotiable in SKILL.md §0 and the pattern in §5.
#
# Inputs:   file paths passed as arguments by pre-commit (one per changed file).
# Exit 0:   no AsyncClient constructor call without timeout= is found.
# Exit 1:   at least one AsyncClient(...) without timeout= found; file:line
#           printed on stdout (the Python block inside does `print`, not
#           stderr — acceptable for a linter because pre-commit surfaces it).
# Example:  `httpx.AsyncClient(base_url="...")` fails; adding
#           `timeout=httpx.Timeout(10)` fixes it.
set -euo pipefail
RC=0
for f in "$@"; do
  # Find httpx.AsyncClient constructor invocations without timeout=
  if python3 -c "
import ast, sys
src = open('$f').read()
try:
    tree = ast.parse(src)
except SyntaxError:
    sys.exit(0)
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        # Match httpx.AsyncClient(...) or AsyncClient(...)
        func = node.func
        name = None
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name == 'AsyncClient':
            kws = {k.arg for k in node.keywords}
            if 'timeout' not in kws:
                print(f'$f:{node.lineno}: httpx.AsyncClient without explicit timeout=')
                sys.exit(1)
sys.exit(0)
  " 2>&1; then
    :
  else
    RC=1
  fi
done
exit $RC
