# ADR-0010: OpenTelemetry Collector + Grafana Tempo for distributed tracing

**Status:** Accepted
**Date:** 2026-04-19
**Deciders:** Ezra O'Marley

## Context

SKILL.md §0 point 3 requires every external call to be wrapped in an OpenTelemetry span. The orchestrator (ADR-0003) emits spans but there is currently no backend to send them to — tracer calls today are no-ops. Without end-to-end tracing, on-call has nothing to look at when a request hangs somewhere between browser → gateway → retrieval → vLLM → conformal → audit: the logs show the entry and exit, and nothing in between.

Issue #30 scopes the trace transport: a collector that pod workloads export to, and a backend that stores and queries the spans.

## Decision

- **Export protocol:** OTLP/gRPC on port 4317. The industry default; every OTel SDK supports it out of the box; the Collector speaks it natively.
- **Collector topology:** DaemonSet. Every node runs one Collector; workload pods export to the host-local Collector rather than a central pool. Rationale: a single backend outage (Tempo, Phoenix) cannot backpressure the request path because the Collector's in-memory queue absorbs the failure and drops old spans when full. A central Collector pool would share that queue across all pods and risk correlated backpressure.
- **Trace backend:** Grafana Tempo, single-binary deployment, S3-backed storage against the cluster-local MinIO. Single-binary is appropriate for our span volume (~40k spans/day). Retention: 720h (30 days) matching `TEMPO_RETENTION_DAYS`.
- **Processors in the pipeline:** `memory_limiter` first (rejects spans when memory pressure is high, bounded to 800 MiB), then `k8sattributes` (enriches with pod/node/namespace metadata), then an `attributes` processor that strips known-PHI keys as a last line of defence, then `batch` for network efficiency.
- **Sampling:** `ParentBased(TraceIdRatioBased(ratio))`. `ratio=1.0` in dev, tunable to 0.2 in production via `OTEL_TRACES_SAMPLER_RATIO`. Parent-based means we always keep a trace if the upstream service sampled it — so the frontend deciding to trace a specific user action flows all the way through.
- **Propagation:** W3C `traceparent` only. Legacy B3 support is not needed and avoiding it keeps the header surface small.

## Consequences

**Positive**

- Every request lifecycle is inspectable top-to-bottom, satisfying issue #30's acceptance criterion 1 (5+ service spans visible in a single trace).
- PHI scrubbing lands in two places: application code (MUST NOT set query_text as span attribute) and Collector processor (drops it if it somehow appears). Defence in depth.
- DaemonSet pod-to-host-local export means the slowest link is localhost; a slow Tempo does not push backpressure onto the request path.
- Canonical attribute constants (`AfyaAttr`) in `backend/app/observability/attributes.py` prevent "trace_id" vs "traceId" vs "trace-id" drift as the codebase grows.

**Negative**

- Five new Python dependencies (`opentelemetry-sdk`, OTLP gRPC exporter, three instrumentors). Each pinned. Collectively add ~15 MiB to the gateway image.
- The Collector's `prometheusremotewrite` exporter is configured but stubbed — Prometheus itself lands with issue #32. Until then, span metrics are silently dropped at the Collector. Documented in the Collector ConfigMap.
- MinIO for S3 is acceptable on-cluster but means trace storage durability matches MinIO's replication, not AWS S3's 11 9s. Acceptable for a 30-day retention horizon.

**Neutral**

- Token-level LLM spans (issue #31, Phoenix) attach to the same trace_id but export via a separate pipeline entry (`otlp/phoenix` exporter). The Collector fans out spans by their `span.kind` / `service.namespace` attribute — the LLM bucket lands only in Phoenix, everything else lands only in Tempo. When #31 ships the filtering rules tighten; for now the pipeline shape is right but both destinations receive everything.
- The instrumentors (FastAPI, httpx, asyncpg) are pre-1.0 (`0.48b0`). We pin exact versions; upgrades are Dependabot + manual smoke test.

## Alternatives rejected

- **Jaeger** instead of Tempo: Tempo's S3-first design is a better fit for our MinIO infrastructure; Jaeger prefers Cassandra or Elasticsearch, which would be a second storage backend to run.
- **Sidecar Collector pattern** (one Collector per pod): ~5x the pod overhead for no clear benefit at our scale. Revisit if a single node's workload outgrows the DaemonSet Collector's 1Gi memory limit.
- **Direct pod → Tempo export, no Collector:** skips the processor pipeline, so PHI scrubbing and k8s enrichment would need to live in application code. Violates SKILL.md §0.4 (scrubbing is a shared concern).

## References

- Issue #30 feat(observability): OTel Collector + Grafana Tempo for traces
- ADR-0003 explicit state machine (spans are tested against its step names)
- ADR-0005 k3s over full Kubernetes
- SKILL.md §10 observability hooks
- `env/observability.env`
