#!/usr/bin/env bash
# Every httpx.AsyncClient instantiation must set timeout= explicitly.
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
