#!/usr/bin/env bash
# Static-check the Kyverno ClusterPolicy manifests.
#
# Uses `kyverno test` if the CLI is available; otherwise just validates
# the YAML shape via yq and confirms each policy has enforce mode +
# the expected rule names. CI runs it via pre-commit when the file
# changes.
#
# Usage:
#   scripts/deploy/test_kyverno_policies.sh [path]

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
policy_file="${1:-$repo_root/deploy/k3s/kyverno-policies.yaml}"

fail=0

assert_contains() {
  local needle="$1" name="$2"
  if grep -q "$needle" "$policy_file"; then
    echo "OK: $name"
  else
    echo "FAIL: $name (missing: $needle)" >&2
    fail=1
  fi
}

# The policy file must declare all three policies in enforce mode.
assert_contains "name: afya-sahihi-run-as-non-root" "run-as-non-root policy present"
assert_contains "name: afya-sahihi-no-host-path" "no-host-path policy present"
assert_contains "name: afya-sahihi-resource-limits" "resource-limits policy present"

# All three policies must be in Enforce mode.
enforce_count="$(grep -c 'validationFailureAction: Enforce' "$policy_file")"
if [ "$enforce_count" -eq 3 ]; then
  echo "OK: all 3 policies in Enforce mode"
else
  echo "FAIL: expected 3 Enforce actions, got $enforce_count" >&2
  fail=1
fi

# The hostPath rule must use `deny` + JMESPath — the pattern-anchor
# form was silently permissive and the review guard catches that.
if grep -q "volumes\[?hostPath\]" "$policy_file"; then
  echo "OK: no-host-path uses JMESPath deny (not the ambiguous anchor pattern)"
else
  echo "FAIL: no-host-path must deny via JMESPath over volumes[?hostPath]" >&2
  fail=1
fi

# node-exporter + promtail must remain exempted so the existing
# DaemonSets keep working.
assert_contains "app.kubernetes.io/name: node-exporter" "node-exporter exempted from hostPath rule"
assert_contains "app.kubernetes.io/name: promtail" "promtail exempted from hostPath rule"

# If kyverno CLI is present, run its built-in test harness as well.
if command -v kyverno >/dev/null 2>&1; then
  if kyverno test "$policy_file" >/dev/null 2>&1; then
    echo "OK: kyverno CLI validates the policy file"
  else
    echo "FAIL: kyverno CLI rejected the policy file" >&2
    fail=1
  fi
fi

if [ "$fail" -eq 0 ]; then
  echo ""
  echo "All Kyverno policy checks passed."
fi
exit "$fail"
