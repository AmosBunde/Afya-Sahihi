"""Tests for the OpenInference-compatible LLM span helpers."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.observability.attributes import AfyaAttr
from app.observability.llm_spans import (
    MAX_TOKEN_EVENTS,
    OI,
    SPAN_KIND_LLM,
    LLMUsage,
    is_llm_span,
    record_token_event,
    set_llm_result,
    start_llm_span,
)


def _tracer_exporter() -> tuple[TracerProvider, InMemorySpanExporter]:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_start_llm_span_sets_openinference_attributes() -> None:
    provider, exporter = _tracer_exporter()
    tracer = provider.get_tracer("test")

    with start_llm_span(
        tracer=tracer,
        name="vllm.generate",
        model="medgemma-27b-it",
        query_id="q-1",
        invocation_parameters={"temperature": 0.1, "seed": 42},
    ):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "vllm.generate"
    assert span.attributes[OI.SPAN_KIND] == SPAN_KIND_LLM
    assert span.attributes[OI.LLM_SYSTEM] == "vllm"
    assert span.attributes[OI.LLM_MODEL_NAME] == "medgemma-27b-it"
    assert span.attributes[AfyaAttr.QUERY_ID] == "q-1"
    assert span.attributes[f"{OI.LLM_INVOCATION_PARAMETERS}.temperature"] == pytest.approx(0.1)
    assert span.attributes[f"{OI.LLM_INVOCATION_PARAMETERS}.seed"] == 42


def test_start_llm_span_without_invocation_parameters() -> None:
    provider, exporter = _tracer_exporter()
    tracer = provider.get_tracer("test")

    with start_llm_span(
        tracer=tracer, name="vllm.prefilter", model="medgemma-4b-it", query_id="q-2"
    ):
        pass

    [span] = exporter.get_finished_spans()
    assert span.attributes[OI.LLM_MODEL_NAME] == "medgemma-4b-it"
    # No invocation params means no keys under that prefix.
    for key in span.attributes:
        assert not key.startswith(f"{OI.LLM_INVOCATION_PARAMETERS}.")


def test_record_token_event_attaches_event_with_logprob() -> None:
    provider, exporter = _tracer_exporter()
    tracer = provider.get_tracer("test")

    with start_llm_span(tracer=tracer, name="vllm.generate", model="m", query_id="q") as span:
        record_token_event(
            span,
            index=0,
            token="Aspirin",
            logprob=-0.1,
            top_logprobs=(("Aspirin", -0.1), ("Ibuprofen", -2.3)),
        )

    [sp] = exporter.get_finished_spans()
    assert len(sp.events) == 1
    event = sp.events[0]
    assert event.name == "token"
    attrs = event.attributes
    assert attrs["token.index"] == 0
    assert attrs["token.text"] == "Aspirin"
    assert attrs["token.logprob"] == pytest.approx(-0.1)
    assert attrs["token.top.0.text"] == "Aspirin"
    assert attrs["token.top.1.text"] == "Ibuprofen"


def test_record_token_event_caps_at_max() -> None:
    provider, exporter = _tracer_exporter()
    tracer = provider.get_tracer("test")

    with start_llm_span(tracer=tracer, name="vllm.generate", model="m", query_id="q") as span:
        for i in range(MAX_TOKEN_EVENTS + 50):
            record_token_event(span, index=i, token="x", logprob=-1.0)

    [sp] = exporter.get_finished_spans()
    assert len(sp.events) == MAX_TOKEN_EVENTS


def test_set_llm_result_populates_usage_and_output() -> None:
    provider, exporter = _tracer_exporter()
    tracer = provider.get_tracer("test")

    with start_llm_span(tracer=tracer, name="vllm.generate", model="m", query_id="q") as span:
        set_llm_result(
            span,
            completion="Take 300mg aspirin stat.",
            usage=LLMUsage(prompt_tokens=120, completion_tokens=8),
        )

    [sp] = exporter.get_finished_spans()
    assert sp.attributes[OI.LLM_OUTPUT_VALUE] == "Take 300mg aspirin stat."
    assert sp.attributes[OI.LLM_TOKEN_COUNT_PROMPT] == 120
    assert sp.attributes[OI.LLM_TOKEN_COUNT_COMPLETION] == 8
    assert sp.attributes[OI.LLM_TOKEN_COUNT_TOTAL] == 128
    assert sp.attributes[OI.LLM_OUTPUT_MIME_TYPE] == "text/plain"


def test_is_llm_span_true_for_llm_span() -> None:
    provider, exporter = _tracer_exporter()
    tracer = provider.get_tracer("test")

    with start_llm_span(tracer=tracer, name="vllm.generate", model="m", query_id="q"):
        pass

    [sp] = exporter.get_finished_spans()
    assert is_llm_span(sp) is True


def test_is_llm_span_false_for_plain_span() -> None:
    provider, exporter = _tracer_exporter()
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("orchestrator.retrieve"):
        pass

    [sp] = exporter.get_finished_spans()
    assert is_llm_span(sp) is False


def test_llm_usage_total_tokens() -> None:
    usage = LLMUsage(prompt_tokens=100, completion_tokens=25)
    assert usage.total_tokens == 125


def test_oi_constants_use_expected_names() -> None:
    # Sanity: the OI constants match OpenInference spec keys used by Phoenix.
    assert OI.SPAN_KIND == "openinference.span.kind"
    assert OI.LLM_MODEL_NAME == "llm.model_name"
    assert OI.LLM_TOKEN_COUNT_PROMPT == "llm.token_count.prompt"
