"""Tracer provider setup for the gateway.

Lives behind a `configure_tracing(settings)` function so the same setup
is reused by the retrieval, conformal, and labeling services. The
function is idempotent: calling it twice does not install two
providers (later calls are no-ops).

The OTel Collector runs as a DaemonSet on port 4317 — every pod
exports to its node-local Collector, which handles fan-out to Tempo /
Prometheus / Phoenix. Direct-to-Tempo export is avoided so one Tempo
outage does not backpressure the request path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from opentelemetry import trace
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_ON,
    ParentBased,
    Sampler,
    TraceIdRatioBased,
)
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from app.observability.attributes import AfyaResource

logger = logging.getLogger(__name__)


# Hold a reference to the provider we installed so idempotent calls
# return the same handles. OTel's global set_tracer_provider refuses
# to overwrite, so we cannot rely on trace.get_tracer_provider() after
# a shutdown + reconfigure.
#
# SKILL.md §0.7 disallows mutable global state except loggers, tracers,
# and constants. TracerProvider is process-scoped by OTel design (the
# spec requires a single global); this variable is the sanctioned
# tracer exception, not a new one.
_PROVIDER: TracerProvider | None = None


class TracingSettingsLike(Protocol):
    service_name: str
    otel_exporter_otlp_endpoint: str
    otel_exporter_otlp_insecure: bool
    otel_traces_sampler_ratio: float
    deployment_env: str
    git_sha: str


@dataclass(frozen=True, slots=True)
class TracingHandles:
    """What the caller needs back — useful for shutdown + testing."""

    provider: TracerProvider
    exporter: SpanExporter | None


def configure_tracing(
    *,
    settings: TracingSettingsLike,
    exporter: SpanExporter | None = None,
) -> TracingHandles:
    """Install a TracerProvider. Idempotent.

    `exporter` override is the testing seam — tests pass an
    InMemorySpanExporter to capture spans without a live Collector.
    When None, we construct an OTLP/gRPC exporter pointed at the
    settings-supplied endpoint.
    """
    global _PROVIDER

    if _PROVIDER is not None:
        return TracingHandles(provider=_PROVIDER, exporter=None)

    resource = Resource.create(
        {
            AfyaResource.SERVICE_NAME: settings.service_name,
            AfyaResource.SERVICE_VERSION: "0.0.1",
            AfyaResource.SERVICE_NAMESPACE: "afya-sahihi",
            AfyaResource.DEPLOYMENT_ENV: settings.deployment_env,
            AfyaResource.GIT_SHA: settings.git_sha,
        }
    )

    sampler = _build_sampler(settings.otel_traces_sampler_ratio)
    provider = TracerProvider(resource=resource, sampler=sampler)

    exp: SpanExporter | None = exporter
    if exp is None and settings.otel_exporter_otlp_endpoint:
        exp = _build_otlp_exporter(
            endpoint=settings.otel_exporter_otlp_endpoint,
            insecure=settings.otel_exporter_otlp_insecure,
        )

    if exp is not None:
        provider.add_span_processor(BatchSpanProcessor(exp))

    trace.set_tracer_provider(provider)

    # W3C tracecontext + baggage is the default; extra propagators
    # would go here. We keep it to tracecontext to match Tempo and
    # the frontend fetch-polyfill instrumentation.
    set_global_textmap(CompositePropagator([TraceContextTextMapPropagator()]))

    _PROVIDER = provider
    logger.info(
        "tracing configured",
        extra={
            "service_name": settings.service_name,
            "endpoint": settings.otel_exporter_otlp_endpoint or "<in-memory>",
            "sampler_ratio": settings.otel_traces_sampler_ratio,
        },
    )
    return TracingHandles(provider=provider, exporter=exp)


def _build_sampler(ratio: float) -> Sampler:
    """Parent-based sampler with a head-sampled ratio for root spans.

    Parent-based means: if a parent span (from the upstream service)
    was sampled, we sample. If it wasn't, we don't. Root spans (no
    upstream context) fall through to the ratio sampler, so we can
    set ratio<1 in production to cap trace storage cost.
    """
    if ratio <= 0:
        raise ValueError("sampler ratio must be > 0")
    if ratio >= 1.0:
        return ParentBased(root=ALWAYS_ON)
    return ParentBased(root=TraceIdRatioBased(ratio))


def _build_otlp_exporter(*, endpoint: str, insecure: bool) -> SpanExporter:
    """Construct the OTLP/gRPC exporter. Imported lazily so unit tests
    don't pull in grpcio."""
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,
    )

    return OTLPSpanExporter(endpoint=endpoint, insecure=insecure)


def shutdown_tracing() -> None:
    """Flush and shut down the provider. Call from FastAPI lifespan."""
    global _PROVIDER
    if _PROVIDER is not None:
        _PROVIDER.shutdown()
    _PROVIDER = None
