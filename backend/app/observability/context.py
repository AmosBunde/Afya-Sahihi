"""Span context extraction helpers.

Small utilities to thread the active span's trace_id into logs and
response headers without sprinkling OTel imports across handlers.
"""

from __future__ import annotations

from opentelemetry import trace


def current_trace_id_hex() -> str:
    """Return the active span's trace_id as 32-char hex, or '' if none.

    FastAPI handlers can inject this into response headers
    (`X-Trace-ID`) so the frontend can deep-link into the Grafana
    Tempo UI for a given request.
    """
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid:
        return ""
    return f"{ctx.trace_id:032x}"


def current_span_id_hex() -> str:
    """Return the active span_id as 16-char hex, or ''."""
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx or not ctx.is_valid:
        return ""
    return f"{ctx.span_id:016x}"


def set_span_attributes(
    *,
    attributes: dict[str, str | int | float | bool],
) -> None:
    """Set attributes on the current span. No-op if no active span."""
    span = trace.get_current_span()
    if span is None:
        return
    for key, value in attributes.items():
        span.set_attribute(key, value)
