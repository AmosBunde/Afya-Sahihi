#!/usr/bin/env bash
# Verify the AlwaysFiring synthetic alert is loaded in Prometheus and
# routed to the deadman receiver in Alertmanager.
#
# Two stages:
#   1. Parse the prometheus-rules ConfigMap and confirm AlwaysFiring
#      is present with the expected labels.
#   2. Parse the alertmanager-config ConfigMap and confirm a
#      severity=deadman route + a `deadman` receiver exist.
#
# Run without cluster access — static manifest check. For live-cluster
# verification use smoke_test.sh step 4.

set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
prom_file="$repo_root/deploy/k3s/60-observability/40-prometheus.yaml"
am_file="$repo_root/deploy/k3s/60-observability/45-alertmanager.yaml"

fail=0

# --- Prometheus side ---------------------------------------------------

if grep -q "alert: AlwaysFiring" "$prom_file"; then
  echo "OK: AlwaysFiring alert defined in prometheus-rules"
else
  echo "FAIL: AlwaysFiring alert missing from $prom_file" >&2
  fail=1
fi

if grep -A5 "alert: AlwaysFiring" "$prom_file" | grep -q "severity: deadman"; then
  echo "OK: AlwaysFiring labeled severity=deadman"
else
  echo "FAIL: AlwaysFiring must carry severity=deadman label" >&2
  fail=1
fi

if grep -A5 "alert: AlwaysFiring" "$prom_file" | grep -q 'expr: vector(1)'; then
  echo "OK: AlwaysFiring uses vector(1) so it always fires"
else
  echo "FAIL: AlwaysFiring must use expr: vector(1)" >&2
  fail=1
fi

# --- Alertmanager side -------------------------------------------------

if grep -q "receiver: deadman" "$am_file"; then
  echo "OK: deadman route present in Alertmanager config"
else
  echo "FAIL: deadman route missing from $am_file" >&2
  fail=1
fi

if grep -A3 "receivers:" "$am_file" | grep -q "name: deadman"; then
  echo "OK: deadman receiver defined"
else
  # receivers: list is several lines long; broaden the grep.
  if awk '/^    receivers:/,/^    inhibit_rules:/' "$am_file" | grep -q "name: deadman"; then
    echo "OK: deadman receiver defined"
  else
    echo "FAIL: deadman receiver missing from $am_file" >&2
    fail=1
  fi
fi

# --- Runbook link sanity -----------------------------------------------

if grep -q "runbooks/observability.md" "$prom_file"; then
  echo "OK: AlwaysFiring runbook_url points to docs/runbooks/observability.md"
else
  echo "FAIL: AlwaysFiring runbook_url not set to docs/runbooks/observability.md" >&2
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo ""
  echo "Synthetic alert configuration verified."
fi
exit "$fail"
