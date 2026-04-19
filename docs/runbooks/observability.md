# Runbook: Observability stack

**When to use:** bringing up the observability stack for the first time, verifying a green canary post-deploy, or debugging a specific observability component (Prometheus silent, Grafana missing a dashboard, Alertmanager not paging).

**Companion references:**
- `deploy/k3s/60-observability/` — manifests shipped by issues #30, #31, #32.
- `docs/observability/SPAN_ATTRIBUTES.md` — canonical OTel attribute catalog.
- `docs/observability/PHOENIX_WORKFLOW.md` — LLM debugging flows.
- `docs/observability/RUNBOOKS/*.md` — five alert-specific runbooks linked from `runbook_url` annotations.

## 1. Deploy order (first-time bring-up)

The `observability` namespace is created by `00-namespace.yaml`; every other manifest lands once the Kyverno controller and SealedSecrets controller are running (they validate the security baseline and decrypt `afya-sahihi-tempo-s3`, `afya-sahihi-phoenix-db`, `afya-sahihi-alertmanager-keys`, `afya-sahihi-grafana-oidc`, `afya-sahihi-postgres-exporter`).

```bash
# 1. Apply the full stack (via the watcher's kustomize overlay, or
# once-off during bootstrap).
kubectl apply -k deploy/k3s/kustomize/overlays/production

# 2. Seed the Grafana dashboards ConfigMap (empty stub in the manifest
# until this script runs).
scripts/observability/build_dashboards_configmap.sh | kubectl apply -f -

# 3. Wait for every pod to be Ready.
kubectl -n observability rollout status statefulset/prometheus --timeout=5m
kubectl -n observability rollout status statefulset/tempo --timeout=5m
kubectl -n observability rollout status statefulset/loki --timeout=5m
kubectl -n observability rollout status deployment/grafana --timeout=5m
kubectl -n observability rollout status deployment/alertmanager --timeout=5m
kubectl -n observability rollout status deployment/phoenix --timeout=5m

# 4. Run the smoke test.
KUBECONFIG=/etc/afya-sahihi/kubeconfig.yaml scripts/observability/smoke_test.sh
```

## 2. Synthetic alert: the deadman

`prometheus-rules` ships an `AlwaysFiring` alert with `expr: vector(1)` and `severity: deadman`. It always fires, routes to the `deadman` receiver in Alertmanager, and is silently swallowed — **no page, no Slack**. Its presence in `/api/v2/alerts` is the smoke test signal that the entire alert pipeline (Prometheus rule evaluation → Alertmanager route match → receiver group) works.

Verify manually:

```bash
# From a control-plane shell with kubectl access:
kubectl -n observability exec -it statefulset/prometheus -- \
  wget -qO- http://localhost:9090/api/v1/alerts | grep AlwaysFiring

kubectl -n observability exec -it deployment/alertmanager -- \
  wget -qO- http://localhost:9093/api/v2/alerts | grep AlwaysFiring
```

If the alert is missing from Prometheus, the rule group didn't load — check `kubectl logs statefulset/prometheus`. If it's in Prometheus but missing from Alertmanager, the alert pipeline is broken — Prometheus can't reach Alertmanager, or the route chain rejected the alert. This is the single most important observability invariant; if `AlwaysFiring` is not firing, *no other alert can*.

## 3. Grafana dashboard audit

Grafana reads dashboards from the `grafana-dashboards-json` ConfigMap, populated by `scripts/observability/build_dashboards_configmap.sh` from `docs/observability/dashboards/*.json`. The seven expected UIDs are:

| UID                 | Dashboard                 |
| ------------------- | ------------------------- |
| `afya-red`          | RED (rate/errors/duration) |
| `afya-llm`          | LLM (vLLM internals)       |
| `afya-retrieval`    | Retrieval                  |
| `afya-conformal`    | Conformal                  |
| `afya-eval`         | Eval (Tier 1/2/3)          |
| `afya-gpu`          | GPU (DCGM)                 |
| `afya-infra`        | Infrastructure             |

A missing dashboard usually means the ConfigMap wasn't rebuilt after `docs/observability/dashboards/` changed. Re-run the generator:

```bash
scripts/observability/build_dashboards_configmap.sh | kubectl apply -f -
# Grafana picks up the change within ~30s (updateIntervalSeconds on the provider).
```

## 4. NetworkPolicy perimeter

`05-networkpolicy.yaml` installs the default-deny + explicit-allow set for the observability namespace. Key rules:

- **default-deny**: every pod starts fully locked.
- **allow-otlp-from-workloads**: otel-collector accepts OTLP on 4317/4318 from afya-sahihi + kube-system.
- **allow-intra-namespace**: pods within observability talk to each other (Grafana → Prometheus/Tempo/Loki, Prometheus → Alertmanager, Tempo's metrics generator → Prometheus remote-write).
- **allow-egress-to-data-node**: Tempo → MinIO :9000, Phoenix + postgres-exporter → Postgres :5432, scoped by workload label.
- **allow-alertmanager-egress**: Alertmanager can reach PagerDuty + Slack on :443.
- **allow-grafana-oidc-egress**: Grafana can reach auth.aku.edu on :443 for OIDC.

If a new observability component needs network access, add an explicit NetworkPolicy rather than weakening the perimeter.

## 5. Tracing — specific debugging flows

- Tempo service-graph: `docs/observability/PHOENIX_WORKFLOW.md` §"Retrieval debugging".
- Phoenix per-token: `docs/observability/PHOENIX_WORKFLOW.md` §"Calibration review".
- Logs by trace_id: Grafana → Explore → Loki → `{namespace="afya-sahihi"} | json | trace_id = "abc..."`. Works because Promtail extracts `trace_id` from structured logs (pipeline_stages in `50-loki.yaml`).

## 6. Common issues

- **Prometheus /targets shows `scrape timeout`** — usually a target pod's security context blocks the metrics port; check the ServiceMonitor + target pod's NetworkPolicy.
- **Grafana "Unknown data source"** — datasources ConfigMap didn't mount, usually because Grafana rolled back to a previous ReplicaSet. `kubectl rollout restart deployment/grafana -n observability`.
- **Alertmanager pages flooding** — check inhibit_rules in the ConfigMap. A page on `service=gateway` inhibits warnings on the same service so a single incident doesn't trigger both channels.
- **Tempo 500 on search** — MinIO unreachable. Check `kubectl get events -n observability` for PVC binding failures or S3 credential errors.

## 7. Rotating the observability secrets

All five SealedSecrets rotate on a 90-day cadence via platform team:

```bash
# Fetch the current cert.
kubeseal --fetch-cert --controller-namespace=kube-system > pub.pem

# Re-seal each secret with the new key.
kubeseal --cert pub.pem < /path/to/new-secret.yaml > sealed.yaml

# Apply and wait for Alertmanager + Grafana + Phoenix + Tempo + postgres-exporter to pick up the rotated key on their next reconcile.
```
