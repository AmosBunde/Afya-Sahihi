#!/usr/bin/env bash
# Every async method on Orchestrator named _<step> must call start_as_current_span.
set -euo pipefail
f="backend/app/orchestrator.py"
[[ -f "$f" ]] || exit 0

python3 <<'PYEOF' "$f"
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
