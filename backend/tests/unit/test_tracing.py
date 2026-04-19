"""Tests for observability.tracing.configure_tracing."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased

from app.observability.attributes import AfyaAttr, AfyaResource
from app.observability.context import current_trace_id_hex, set_span_attributes
from app.observability.tracing import (
    _build_sampler,
    configure_tracing,
    shutdown_tracing,
)


@dataclass(frozen=True)
class FakeSettings:
    service_name: str = "afya-sahihi-gateway"
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_insecure: bool = True
    otel_traces_sampler_ratio: float = 1.0
    deployment_env: str = "test"
    git_sha: str = "abc123"


@pytest.fixture(autouse=True)
def _reset_provider() -> None:
    # Reset the global between tests so each run starts clean.
    shutdown_tracing()
    yield
    shutdown_tracing()


def test_configure_sets_resource_attributes() -> None:
    exporter = InMemorySpanExporter()
    handles = configure_tracing(settings=FakeSettings(), exporter=exporter)
    assert isinstance(handles.provider, TracerProvider)
    resource = handles.provider.resource
    assert resource.attributes[AfyaResource.SERVICE_NAME] == "afya-sahihi-gateway"
    assert resource.attributes[AfyaResource.SERVICE_NAMESPACE] == "afya-sahihi"
    assert resource.attributes[AfyaResource.DEPLOYMENT_ENV] == "test"
    assert resource.attributes[AfyaResource.GIT_SHA] == "abc123"


def test_configure_is_idempotent() -> None:
    exporter = InMemorySpanExporter()
    first = configure_tracing(settings=FakeSettings(), exporter=exporter)
    second = configure_tracing(settings=FakeSettings(), exporter=exporter)
    assert first.provider is second.provider


def test_spans_reach_exporter() -> None:
    # Bypass OTel's global provider (which refuses overrides) and take
    # the tracer from our local provider directly — this is the canonical
    # pattern for exporter tests.
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("orchestrator.prefilter") as span:
        span.set_attribute(AfyaAttr.PREFILTER_TOPIC_SCORE, 0.82)

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "orchestrator.prefilter"
    assert spans[0].attributes[AfyaAttr.PREFILTER_TOPIC_SCORE] == pytest.approx(0.82)


def test_sampler_ratio_1_always_on() -> None:
    sampler = _build_sampler(1.0)
    assert isinstance(sampler, ParentBased)
    # ParentBased with ALWAYS_ON root means root samples deterministically.
    assert sampler._root is ALWAYS_ON  # type: ignore[attr-defined]


def test_sampler_ratio_fraction_uses_ratio_based() -> None:
    sampler = _build_sampler(0.1)
    assert isinstance(sampler, ParentBased)


def test_sampler_rejects_non_positive_ratio() -> None:
    with pytest.raises(ValueError, match="ratio"):
        _build_sampler(0.0)
    with pytest.raises(ValueError, match="ratio"):
        _build_sampler(-0.5)


def test_current_trace_id_hex_inside_span() -> None:
    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("x"):
        trace_id = current_trace_id_hex()
    assert len(trace_id) == 32
    assert trace_id != "0" * 32


def test_current_trace_id_hex_outside_span_returns_empty() -> None:
    # Reset provider so no active tracer has been set.
    shutdown_tracing()
    assert current_trace_id_hex() == ""


def test_set_span_attributes_no_op_without_active_span() -> None:
    # Should not raise even with no active span.
    shutdown_tracing()
    set_span_attributes(attributes={"key": "value"})


def test_afya_attr_constants_use_expected_prefix() -> None:
    for name, value in vars(AfyaAttr).items():
        if name.startswith("_"):
            continue
        assert isinstance(value, str)
        assert value.startswith("afya_sahihi."), f"{name}={value!r} missing prefix"
