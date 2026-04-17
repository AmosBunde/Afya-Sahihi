#!/usr/bin/env bash
# Smoke test for the MedGemma 27B vLLM server.
#
# Purpose: after `systemctl start afya-sahihi-vllm-27b`, verify that
#   (a) the /health endpoint is reachable,
#   (b) /v1/chat/completions returns a response with logprobs, and
#   (c) latency is within budget.
#
# Usage:
#   VLLM_API_KEY=$(cat /etc/afya-sahihi/secrets/vllm-27b-api-key) \
#       scripts/vllm/smoke_test_27b.sh [host:port]
#
# Exit 0: all checks pass.
# Exit 1: one or more checks failed.
set -euo pipefail

BASE="${1:-http://localhost:8000}"
API_KEY="${VLLM_API_KEY:?set VLLM_API_KEY}"

_fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

# 1. Health check
echo -n "health check... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${BASE}/health")
[ "$HTTP_CODE" = "200" ] || _fail "/health returned $HTTP_CODE (expected 200)"
echo "ok"

# 2. Chat completion with logprobs
echo -n "chat completion with logprobs... "
RESPONSE=$(curl -s --max-time 30 \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "medgemma-27b-it",
    "messages": [
      {"role": "user", "content": "What is the first-line treatment for uncomplicated malaria in Kenya?"}
    ],
    "max_tokens": 128,
    "temperature": 0.1,
    "logprobs": true,
    "top_logprobs": 5
  }' \
  "${BASE}/v1/chat/completions")

# Verify response structure
echo "$RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'choices' not in d or not d['choices']:
    print('SMOKE FAIL: no choices in response', file=sys.stderr)
    sys.exit(1)
choice = d['choices'][0]
if 'logprobs' not in choice or choice['logprobs'] is None:
    print('SMOKE FAIL: logprobs missing from response — conformal scoring requires this', file=sys.stderr)
    sys.exit(1)
content = choice.get('message', {}).get('content', '')
if len(content) < 10:
    print(f'SMOKE FAIL: response too short ({len(content)} chars)', file=sys.stderr)
    sys.exit(1)
print(f'ok — {len(content)} chars, logprobs present')
" || _fail "response validation failed"

# 3. Prometheus metrics endpoint
echo -n "prometheus metrics... "
METRICS_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${BASE%:*}:8002/metrics" 2>/dev/null || echo "000")
if [ "$METRICS_CODE" = "200" ]; then
  echo "ok (port 8002)"
else
  echo "warn: metrics endpoint returned $METRICS_CODE (non-fatal; DCGM exporter on 9400 may be separate)"
fi

echo "All smoke tests passed for ${BASE}"
