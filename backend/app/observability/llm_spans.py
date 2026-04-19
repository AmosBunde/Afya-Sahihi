"""LLM span helpers conforming to OpenInference semantic conventions.

Phoenix ingests spans whose attributes follow OpenInference (the Arize
spec that extends OTel semantic conventions for LLM observability). We
emit those attributes directly rather than pulling the full
openinference-instrumentation package — the instrumentors wrap openai,
anthropic, langchain, etc., none of which we use on the request path.

Three public functions:
  - `start_llm_span(tracer, model, ...)` — returns a span configured
    as an LLM invocation (routes to Phoenix via the Collector filter).
  - `record_token_event(span, token, logprob, top_logprobs)` — attach
    a per-token event. Cardinality-bounded: we cap the event count.
  - `set_llm_result(span, completion, usage)` — set the output
    attributes once generation is complete.

Do not put raw query text here. The Collector scrubs `llm.input.value`
and `llm.output.value` from traces destined for Tempo (where they'd be
cross-referenced by trace_id); they are allowed in Phoenix because
Phoenix's Postgres backend is in the PHI-approved boundary.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

from opentelemetry import trace
from opentelemetry.trace import Span, Tracer

from app.observability.attributes import AfyaAttr

logger = logging.getLogger(__name__)


# OpenInference semantic conventions (trimmed to what we use).
# Full spec: https://github.com/Arize-ai/openinference
class OI:
    SPAN_KIND: Final = "openinference.span.kind"
    LLM_SYSTEM: Final = "llm.system"
    LLM_MODEL_NAME: Final = "llm.model_name"
    LLM_INVOCATION_PARAMETERS: Final = "llm.invocation_parameters"
    LLM_INPUT_MESSAGES_COUNT: Final = "llm.input_messages.count"
    LLM_OUTPUT_VALUE: Final = "output.value"
    LLM_OUTPUT_MIME_TYPE: Final = "output.mime_type"
    LLM_TOKEN_COUNT_PROMPT: Final = "llm.token_count.prompt"
    LLM_TOKEN_COUNT_COMPLETION: Final = "llm.token_count.completion"
    LLM_TOKEN_COUNT_TOTAL: Final = "llm.token_count.total"


SPAN_KIND_LLM: Final = "LLM"

# Cap how many per-token events we attach to a single span. Generation
# spans with 4000 events destabilise Phoenix's UI for no practical gain;
# the first 128 tokens' logprobs are what a clinician needs for
# calibration review. Matches OTel SDK's default `max_events` limit —
# raising this requires tuning BatchSpanProcessor limits too.
MAX_TOKEN_EVENTS: Final = 128


@dataclass(frozen=True, slots=True)
class LLMUsage:
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@contextmanager
def start_llm_span(
    *,
    tracer: Tracer,
    name: str,
    model: str,
    query_id: str,
    invocation_parameters: dict[str, str | int | float | bool] | None = None,
    system: str = "vllm",
) -> Iterator[Span]:
    """Start a span tagged for Phoenix routing.

    `name` should be stable: `vllm.generate`, `vllm.prefilter`,
    `vllm.strict_review`. Invocation parameters (temperature, seed,
    max_tokens) are serialised as flat dot-keyed attributes so Phoenix
    can index them.
    """
    with tracer.start_as_current_span(name) as span:
        span.set_attribute(OI.SPAN_KIND, SPAN_KIND_LLM)
        span.set_attribute(OI.LLM_SYSTEM, system)
        span.set_attribute(OI.LLM_MODEL_NAME, model)
        span.set_attribute(AfyaAttr.QUERY_ID, query_id)
        if invocation_parameters:
            for key, value in invocation_parameters.items():
                span.set_attribute(f"{OI.LLM_INVOCATION_PARAMETERS}.{key}", value)
        yield span


def record_token_event(
    span: Span,
    *,
    index: int,
    token: str,
    logprob: float,
    top_logprobs: tuple[tuple[str, float], ...] = (),
) -> None:
    """Attach a per-token event. No-op past MAX_TOKEN_EVENTS.

    Events (not attributes) because events carry a timestamp and don't
    bloat the attribute-count cardinality used by backend indexes.
    Token strings themselves are OK because generation output is the
    point of Phoenix — the PHI boundary is enforced upstream (query
    text scrubbed before generation; completion text is what Phoenix
    needs to display).
    """
    if index >= MAX_TOKEN_EVENTS:
        return
    if not span.is_recording():
        return
    attrs: dict[str, str | int | float | bool] = {
        "token.index": index,
        "token.text": token,
        "token.logprob": logprob,
    }
    # Flatten top_logprobs into token.top.{i}.{text|logprob} to stay
    # within the flat attribute namespace Phoenix indexes on.
    for i, (alt_text, alt_logprob) in enumerate(top_logprobs):
        attrs[f"token.top.{i}.text"] = alt_text
        attrs[f"token.top.{i}.logprob"] = alt_logprob
    span.add_event("token", attributes=attrs)


def set_llm_result(
    span: Span,
    *,
    completion: str,
    usage: LLMUsage,
    output_mime_type: str = "text/plain",
) -> None:
    """Record the LLM's output on the span.

    Call once, after the stream finishes. Usage totals are derived
    rather than re-computed so caller-side token accounting matches
    billing and Prometheus counters.
    """
    if not span.is_recording():
        return
    span.set_attribute(OI.LLM_OUTPUT_VALUE, completion)
    span.set_attribute(OI.LLM_OUTPUT_MIME_TYPE, output_mime_type)
    span.set_attribute(OI.LLM_TOKEN_COUNT_PROMPT, usage.prompt_tokens)
    span.set_attribute(OI.LLM_TOKEN_COUNT_COMPLETION, usage.completion_tokens)
    span.set_attribute(OI.LLM_TOKEN_COUNT_TOTAL, usage.total_tokens)


def is_llm_span(span: Span) -> bool:
    """Test-side helper: does this span claim to be an LLM span?"""
    try:
        # SDK spans expose attributes; API-only spans don't.
        attrs = span.attributes  # type: ignore[attr-defined]
    except AttributeError:
        return False
    if attrs is None:
        return False
    return attrs.get(OI.SPAN_KIND) == SPAN_KIND_LLM


def tracer_for(name: str) -> Tracer:
    """Convenience: tracer pinned to a stable name for LLM spans."""
    return trace.get_tracer(name)
