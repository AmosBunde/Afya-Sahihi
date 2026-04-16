#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/helpers.sh"
HOOK="$HOOKS_DIR/check_no_langchain_request_path.sh"

# Green: clean file with no forbidden imports.
case_start "green: file without langchain imports is accepted"
D=$(mktmp_dir)
cat > "$D/ok.py" <<'PY'
from fastapi import FastAPI
import httpx

app = FastAPI()
PY
set +e
"$HOOK" "$D/ok.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 0 "$rc" && pass

# Red 1: top-level `from langchain` import is rejected.
case_start "red: 'from langchain' import is rejected"
cat > "$D/bad1.py" <<'PY'
from langchain.agents import AgentExecutor
PY
set +e
"$HOOK" "$D/bad1.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 1 "$rc" && pass

# Red 2: `import langgraph` is rejected.
case_start "red: 'import langgraph' is rejected"
cat > "$D/bad2.py" <<'PY'
import langgraph
PY
set +e
"$HOOK" "$D/bad2.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 1 "$rc" && pass

# Red 3: `import llama_index` is rejected.
case_start "red: 'import llama_index' is rejected"
cat > "$D/bad3.py" <<'PY'
import llama_index.core
PY
set +e
"$HOOK" "$D/bad3.py" >/dev/null 2>&1; rc=$?
set -e
assert_rc 1 "$rc" && pass

finish
