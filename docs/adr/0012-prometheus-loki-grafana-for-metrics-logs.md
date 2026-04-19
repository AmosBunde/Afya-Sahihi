# ADR-0012: Prometheus + Alertmanager + Loki + Grafana for metrics, alerts, and logs

**Status:** Accepted
**Date:** 2026-04-19
**Deciders:** Ezra O'Marley

## Context

ADR-0010 put distributed tracing on Tempo and ADR-0011 put LLM-specific span inspection on Phoenix. The remaining observability quadrants — metrics, alerts, and logs — are unaddressed. Issue #32 scopes them; this ADR documents the choices.

## Decision

- **Metrics storage:** Prometheus. Industry default; OTel's `prometheusremotewrite` exporter is mature; our scrape targets (gateway, vLLM, DCGM, Postgres, Redis, node) all speak Prom natively.
- **Metrics retention:** 30 days on a 50 GiB local-path PVC. Target volume ~40 million series; 45 GiB size-based retention (leaves 10% headroom).
- **Alerting:** Alertmanager, routed to PagerDuty for `severity=page` and to Slack for `severity=warning`. Page-vs-warning discipline matters: a page must be actionable within 15 minutes at 03:00 EAT; a warning goes to Slack and waits for business hours.
- **Logs:** Loki with a Promtail DaemonSet. Filesystem storage (TSDB schema v13) on a 50 GiB PVC; 30-day retention. Loki is selected over Elasticsearch because our log volume (6k pods, mostly quiet, 1000 lines/sec peak) does not justify ES operational overhead, and Loki's LogQL `{app="gateway"} | json | trace_id = "..."` query pattern pivots naturally from Tempo.
- **Dashboards + exploration UI:** Grafana with OIDC SSO against the AKU IdP. Role mapping: `ops` → Admin, `senior_clinician` → Editor, everyone else → Viewer. Seven pre-provisioned dashboards (RED, LLM, retrieval, conformal, eval, GPU, infrastructure) mounted from ConfigMap.
- **Exporters:** `node-exporter` DaemonSet, `postgres-exporter` Deployment, `redis-exporter` Deployment, DCGM exporter on the bare-metal GPU node (out-of-cluster, scraped via static config). kube-state-metrics lands with M8 (the systemd watcher ADR references it).
- **Alert routing secrets:** SealedSecret `afya-sahihi-alertmanager-keys` holds PagerDuty routing key and Slack webhook URL. Rotated quarterly via platform team.

## Consequences

**Positive**

- Three observability signals — metrics, logs, traces — correlate on `trace_id` across Prometheus/Loki/Tempo without a commercial APM.
- Alertmanager inhibit-rules prevent a `page`-severity alert from also firing its `warning` sibling on the same service, so on-call isn't pelted during an incident.
- OIDC SSO on Grafana means there is no service-account password to rotate; leaving AKU auto-revokes Grafana access.
- All five exporters deploy in one `deploy/k3s/60-observability/70-exporters.yaml`, one apply to bring them up.
- Five runbooks with runbook_url annotations on every alert — PagerDuty links directly, no muscle-memory required.

**Negative**

- Single-replica Prometheus is the availability ceiling. Thanos or Mimir could shard this out; deferred until our series count or retention requires it (not for the next 18 months).
- Loki's filesystem storage has no replication. A node-loss event loses the active WAL; PersistentVolume restore covers the compacted chunks.
- Grafana dashboards drift in JSON diffs. The source of truth is `docs/observability/dashboards/*.json`; the M8 watcher mirrors them into the `grafana-dashboards-json` ConfigMap at deploy time — not perfect but avoids shipping a 500 KiB ConfigMap in this PR.

**Neutral**

- The OTel Collector's `prometheusremotewrite` exporter (configured but pipeline-disabled in #30) is now wired into the Collector's `metrics` pipeline. Span metrics (request rate, error rate by service, latency histogram) start flowing to Prometheus on deploy.
- DCGM on the GPU node is scraped via static config rather than via a k8s service — the GPU node is bare-metal (not k3s-joined) per ADR-0001.

## Alternatives rejected

- **Elasticsearch / Fluent Bit for logs** — higher operational cost for our volume; JSON parsing at query time (LogQL) is more ergonomic than ES field mapping for our ad-hoc debugging.
- **Datadog / New Relic** — clinical data is covered by AKU data-residency; a hosted APM would require a business-associate agreement we don't have. Also a recurring cost.
- **VictoriaMetrics / M3DB** — more scalable than single-replica Prometheus, but our scale does not justify the operational step-up yet.
- **Embedded Grafana (no OIDC)** with a shared password: vetoed on SKILL.md §0.7 grounds.

## References

- Issue #32 feat(observability): Prometheus + Alertmanager + Loki + Grafana
- ADR-0010 OTel + Tempo
- ADR-0011 Phoenix
- ADR-0005 k3s over full Kubernetes
- SKILL.md §10 observability hooks
- `env/observability.env`
