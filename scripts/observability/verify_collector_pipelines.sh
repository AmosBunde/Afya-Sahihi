#!/usr/bin/env bash
# Verify OTel Collector pipeline wiring hasn't inverted the filter processors.
#
# Specifically: the Tempo branch must carry filter/non_llm_only (drops LLM
# spans), and the Phoenix branch must carry filter/llm_only (drops non-LLM
# spans). A review caught this being backwards once; this script is the
# regression guard so it cannot drift silently.
#
# Usage:
#   scripts/observability/verify_collector_pipelines.sh \
#     deploy/k3s/60-observability/10-otel-collector.yaml
#
# Exits 1 on any inversion.

set -euo pipefail

config="${1:-deploy/k3s/60-observability/10-otel-collector.yaml}"
if [ ! -f "$config" ]; then
  echo "collector config not found: $config" >&2
  exit 2
fi

fail=0

# Extract the processors list under each pipeline. A brittle grep is fine
# here — the YAML shape is stable and a proper YAML parser would add a
# dependency for a 20-line check.
tempo_block=$(awk '/traces\/tempo:/,/exporters:/' "$config")
phoenix_block=$(awk '/traces\/phoenix:/,/exporters:/' "$config")

if ! echo "$tempo_block" | grep -qE "^\s+-\s+filter/non_llm_only\s*$"; then
  echo "FAIL: traces/tempo pipeline missing filter/non_llm_only" >&2
  fail=1
fi
if echo "$tempo_block" | grep -qE "^\s+-\s+filter/llm_only\s*$"; then
  echo "FAIL: traces/tempo pipeline must NOT use filter/llm_only" >&2
  fail=1
fi

if ! echo "$phoenix_block" | grep -qE "^\s+-\s+filter/llm_only\s*$"; then
  echo "FAIL: traces/phoenix pipeline missing filter/llm_only" >&2
  fail=1
fi
if echo "$phoenix_block" | grep -qE "^\s+-\s+filter/non_llm_only\s*$"; then
  echo "FAIL: traces/phoenix pipeline must NOT use filter/non_llm_only" >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "OK: Collector pipeline filters correctly routed."
fi
exit "$fail"
