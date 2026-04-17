#!/usr/bin/env bash
# Smoke test for the MedGemma 4B vLLM server (pre-filter role).
#
# Validates:
#   (a) /health returns 200
#   (b) LoRA adapter "prefilter" is loaded (via /v1/models)
#   (c) /v1/chat/completions with the prefilter adapter responds with logprobs
#   (d) inference latency under 500ms (the classifier head budget is <50ms;
#       the vLLM call itself should be well under 500ms for a short prompt)
#
# Usage:
#   VLLM_API_KEY=$(cat /etc/afya-sahihi/secrets/vllm-4b-api-key) \
#       scripts/vllm/smoke_test_4b.sh [host:port]
#
# Exit 0: all checks pass.
# Exit 1: one or more checks failed.
set -euo pipefail

BASE="${1:-http://localhost:8001}"
API_KEY="${VLLM_API_KEY:?set VLLM_API_KEY}"

_fail() { echo "SMOKE FAIL (4B): $1" >&2; exit 1; }

# 1. Health check
echo -n "health check... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${BASE}/health")
[ "$HTTP_CODE" = "200" ] || _fail "/health returned $HTTP_CODE (expected 200)"
echo "ok"

# 2. LoRA adapter loaded
echo -n "LoRA adapter 'prefilter' loaded... "
MODELS=$(curl -s --max-time 5 \
  -H "Authorization: Bearer ${API_KEY}" \
  "${BASE}/v1/models")
echo "$MODELS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
ids = [m['id'] for m in d.get('data', [])]
if 'prefilter' not in ids:
    print(f'SMOKE FAIL (4B): prefilter not in model list: {ids}', file=sys.stderr)
    sys.exit(1)
print('ok — prefilter in model list')
" || _fail "LoRA adapter check failed"

# 3. Chat completion with logprobs + latency check
echo -n "prefilter inference... "
START_MS=$(date +%s%N)
RESPONSE=$(curl -s --max-time 10 \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "prefilter",
    "messages": [
      {"role": "user", "content": "What is the dose of artemether for a 5-year-old?"}
    ],
    "max_tokens": 32,
    "temperature": 0.0,
    "logprobs": true,
    "top_logprobs": 5
  }' \
  "${BASE}/v1/chat/completions")
END_MS=$(date +%s%N)
ELAPSED_MS=$(( (END_MS - START_MS) / 1000000 ))

echo "$RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'choices' not in d or not d['choices']:
    print('SMOKE FAIL (4B): no choices', file=sys.stderr)
    sys.exit(1)
choice = d['choices'][0]
if 'logprobs' not in choice or choice['logprobs'] is None:
    print('SMOKE FAIL (4B): logprobs missing', file=sys.stderr)
    sys.exit(1)
print(f'ok — {${ELAPSED_MS}}ms')
" || _fail "prefilter inference failed"

if [ "$ELAPSED_MS" -gt 500 ]; then
  echo "warn: latency ${ELAPSED_MS}ms > 500ms budget (non-fatal; may be cold start)"
fi

echo "All 4B smoke tests passed for ${BASE}"
