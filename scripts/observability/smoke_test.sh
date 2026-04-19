#!/usr/bin/env bash
# Observability stack smoke test.
#
# Runs after `kubectl apply -k deploy/k3s/kustomize/overlays/<env>/`.
# Verifies:
#   1. Every observability pod is Ready.
#   2. Prometheus scrape targets are UP (gateway, exporters, collector).
#   3. Grafana has the 7 pre-provisioned dashboards.
#   4. Alertmanager has the synthetic AlwaysFiring deadman alert.
#   5. Tempo's ready endpoint responds.
#   6. Loki's ready endpoint responds.
#
# Exits non-zero on any failure. Intended for the CI pipeline's
# staging verification step and for operator runbooks.

set -euo pipefail

: "${KUBECONFIG:=${HOME}/.kube/config}"
: "${NAMESPACE:=observability}"

fail=0
ok()   { echo "OK:   $1"; }
bad()  { echo "FAIL: $1" >&2; fail=1; }

# --- 1. Pods Ready ------------------------------------------------------

echo "[1/6] checking pod readiness in namespace=$NAMESPACE"
not_ready="$(kubectl -n "$NAMESPACE" get pods \
  -o jsonpath='{range .items[?(@.status.phase!="Succeeded")]}{.metadata.name}{"\t"}{range .status.conditions[?(@.type=="Ready")]}{.status}{end}{"\n"}{end}' \
  | awk -F'\t' '$2 != "True" { print $1 }')"
if [ -z "$not_ready" ]; then
  ok "every pod in $NAMESPACE is Ready"
else
  bad "pods not ready: $(echo "$not_ready" | tr '\n' ' ')"
fi

# --- 2. Prometheus scrape targets --------------------------------------

echo "[2/6] checking Prometheus scrape targets"
targets_json="$(kubectl -n "$NAMESPACE" exec deploy/prometheus -c prometheus -- \
  wget -qO- http://localhost:9090/api/v1/targets 2>/dev/null || echo '')"
if [ -z "$targets_json" ]; then
  # StatefulSet, not Deployment. Retry with the pod name.
  pod="$(kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}')"
  targets_json="$(kubectl -n "$NAMESPACE" exec "$pod" -c prometheus -- \
    wget -qO- http://localhost:9090/api/v1/targets 2>/dev/null || echo '')"
fi
if [ -n "$targets_json" ]; then
  # Count targets with health=up vs total active.
  up_count="$(echo "$targets_json" | grep -o '"health":"up"' | wc -l)"
  total="$(echo "$targets_json" | grep -o '"health":"' | wc -l)"
  if [ "$total" -gt 0 ] && [ "$up_count" -eq "$total" ]; then
    ok "Prometheus: $up_count/$total targets healthy"
  else
    bad "Prometheus: only $up_count/$total targets healthy"
  fi
else
  bad "Prometheus: could not query /api/v1/targets"
fi

# --- 3. Grafana dashboards ---------------------------------------------

echo "[3/6] checking Grafana dashboards"
grafana_pod="$(kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].metadata.name}')"
expected_dashboards=(red llm retrieval conformal eval gpu infrastructure)
for uid in "${expected_dashboards[@]}"; do
  if kubectl -n "$NAMESPACE" exec "$grafana_pod" -- \
    wget -qO- "http://localhost:3000/api/dashboards/uid/afya-$uid" 2>/dev/null \
    | grep -q '"title"'; then
    ok "Grafana dashboard afya-$uid loaded"
  else
    bad "Grafana dashboard afya-$uid NOT loaded"
  fi
done

# --- 4. Alertmanager synthetic deadman alert ---------------------------

echo "[4/6] checking Alertmanager has AlwaysFiring deadman alert"
am_pod="$(kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/name=alertmanager -o jsonpath='{.items[0].metadata.name}')"
if kubectl -n "$NAMESPACE" exec "$am_pod" -- \
  wget -qO- http://localhost:9093/api/v2/alerts 2>/dev/null \
  | grep -q '"alertname":"AlwaysFiring"'; then
  ok "Alertmanager: AlwaysFiring deadman present (pipeline healthy)"
else
  bad "Alertmanager: AlwaysFiring deadman absent (alert routing broken)"
fi

# --- 5. Tempo /ready ---------------------------------------------------

echo "[5/6] checking Tempo /ready"
tempo_pod="$(kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/name=tempo -o jsonpath='{.items[0].metadata.name}')"
if kubectl -n "$NAMESPACE" exec "$tempo_pod" -- \
  wget -qO- http://localhost:3200/ready 2>/dev/null | grep -q ready; then
  ok "Tempo: /ready"
else
  bad "Tempo: /ready did not return ready"
fi

# --- 6. Loki /ready ----------------------------------------------------

echo "[6/6] checking Loki /ready"
loki_pod="$(kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/name=loki -o jsonpath='{.items[0].metadata.name}')"
if kubectl -n "$NAMESPACE" exec "$loki_pod" -- \
  wget -qO- http://localhost:3100/ready 2>/dev/null | grep -q ready; then
  ok "Loki: /ready"
else
  bad "Loki: /ready did not return ready"
fi

echo ""
if [ "$fail" -eq 0 ]; then
  echo "Observability smoke test passed."
else
  echo "Observability smoke test FAILED." >&2
fi
exit "$fail"
