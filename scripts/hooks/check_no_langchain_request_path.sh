#!/usr/bin/env bash
# check_no_langchain_request_path.sh
#
# Purpose: enforce ADR-0003 — no LangChain, LangGraph, or LlamaIndex imports
#   anywhere the pre-commit config targets this hook (the request path). The
#   request path uses plain Python; orchestration framework imports are only
#   allowed in offline utility scripts, which .pre-commit-config.yaml excludes.
#
# Inputs:   file paths passed as arguments by pre-commit (one per changed file).
# Exit 0:   none of the provided files contain a forbidden import.
# Exit 1:   at least one forbidden import found; offending file:line printed
#           to stderr with a pointer to docs/adr/0003-....md.
# Example:  adding `from langchain.agents import AgentExecutor` to anything
#           under `backend/app/` fails the hook.
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
