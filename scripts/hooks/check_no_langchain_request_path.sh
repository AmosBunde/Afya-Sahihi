#!/usr/bin/env bash
# ADR-0003 enforcement: no LangChain/LangGraph/LlamaIndex on the request path.
set -euo pipefail
FORBIDDEN='^from (langchain|langgraph|llama_index)|^import (langchain|langgraph|llama_index)'
RC=0
for f in "$@"; do
  if grep -EHn "$FORBIDDEN" "$f"; then
    echo "❌ $f imports a forbidden framework on the request path." >&2
    echo "   See docs/adr/0003-explicit-state-machine-over-langgraph.md" >&2
    RC=1
  fi
done
exit $RC
