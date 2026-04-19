"""OpenTelemetry tracing + metrics wiring for Afya Sahihi.

Import `observability.tracing.configure_tracing(settings)` once at
startup. It idempotently installs a TracerProvider with:

  - Resource attributes (service.name, service.version, git_sha,
    deployment.environment) that let Tempo group spans by service.
  - An OTLP/gRPC exporter targeting the local OTel Collector at
    OTEL_COLLECTOR_ENDPOINT (default port 4317 on the node the pod
    runs on, via DaemonSet).
  - A BatchSpanProcessor tuned for typical clinical query volume
    (2000/day across all tiers) so memory overhead is negligible.
  - Auto-instrumentation for FastAPI, httpx, asyncpg where the libs
    are installed.

Every application-authored span should use canonical attribute names
from `observability.attributes` — lower case, dot-delimited, prefixed
`afya_sahihi.`. No free-form strings in span attributes.
"""
