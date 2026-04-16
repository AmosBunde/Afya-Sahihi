#!/usr/bin/env bash
# check_span_per_transition.sh
#
# Purpose: every private async method on class Orchestrator in
#   backend/app/orchestrator.py must call `tracer.start_as_current_span(...)`.
#   Enforces the "every state transition emits an OTel span" non-negotiable
#   from SKILL.md §0.5 and §10.
#
# Inputs:   reads backend/app/orchestrator.py; takes no arguments.
# Exit 0:   either orchestrator.py is absent (pre-backend repo state), or
#           every private async method starts an OTel span (or is __init__).
# Exit 1:   one or more private async methods lack a start_as_current_span
#           call. The error message names each offending method + line.
# Example:  adding `async def _new_step(self, state): return state` to
#           Orchestrator without a span fails the hook.
set -euo pipefail
f="backend/app/orchestrator.py"
[[ -f "$f" ]] || exit 0

# NB: `python3 - "$f" <<EOF` — the `-` tells python3 to read the script from
# stdin even though there is a positional arg. Without the dash, python3
# treats "$f" as the script to execute, which is exactly the file under test;
# the check would silently no-op.
python3 - "$f" <<'PYEOF'
import ast, sys
src = open(sys.argv[1]).read()
tree = ast.parse(src)

errs = []
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "Orchestrator":
        for item in node.body:
            if isinstance(item, ast.AsyncFunctionDef) and item.name.startswith("_"):
                if item.name in ("__init__",):
                    continue
                # Search for tracer.start_as_current_span in body
                text = ast.unparse(item)
                if "start_as_current_span" not in text:
                    errs.append(f"{sys.argv[1]}:{item.lineno}: {item.name} does not start an OTel span")

if errs:
    for e in errs:
        print(f"❌ {e}", file=sys.stderr)
    print("   See SKILL.md §10", file=sys.stderr)
    sys.exit(1)
PYEOF
