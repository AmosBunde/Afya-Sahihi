"""Fail-closed exception handlers for the gateway API.

Maps each PipelineError subclass to an appropriate HTTP status code and
a stable user-facing JSON shape. The shape is always:

    {"error": {"code": "<snake_case>", "message": "<safe string>"}}

The message NEVER includes file paths, stack traces, SQL, or internal
detail objects. Those go to the structured logger only, keyed by
trace_id so on-call can correlate without exposing internals to the
client. SKILL.md §6, review SKILL §3.1.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.errors import (
    ConformalFailed,
    GenerationFailed,
    PipelineError,
    PrefilterRejected,
    RetrievalFailed,
    StrictReviewRejected,
    ValidationFailed,
)

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[type[PipelineError], int] = {
    ValidationFailed: 422,
    PrefilterRejected: 422,
    RetrievalFailed: 502,
    GenerationFailed: 502,
    StrictReviewRejected: 422,
    ConformalFailed: 502,
}

_CODE_MAP: dict[type[PipelineError], str] = {
    ValidationFailed: "validation_failed",
    PrefilterRejected: "prefilter_rejected",
    RetrievalFailed: "retrieval_failed",
    GenerationFailed: "generation_failed",
    StrictReviewRejected: "strict_review_rejected",
    ConformalFailed: "conformal_failed",
}

_SAFE_MESSAGES: dict[type[PipelineError], str] = {
    ValidationFailed: "The query could not be validated. Please check the input and retry.",
    PrefilterRejected: (
        "This query was not recognized as a clinical question the system can answer. "
        "Please rephrase or escalate to a human clinician."
    ),
    RetrievalFailed: (
        "The system could not retrieve relevant clinical evidence. "
        "Please try again or escalate to a human clinician."
    ),
    GenerationFailed: (
        "The system could not generate a response. "
        "Please try again or escalate to a human clinician."
    ),
    StrictReviewRejected: (
        "The generated response did not pass the safety review for this query category. "
        "Please escalate to a human clinician."
    ),
    ConformalFailed: (
        "The system could not compute a confidence set for this response. "
        "Please try again or escalate to a human clinician."
    ),
}


def _error_response(exc: PipelineError, request: Request) -> JSONResponse:
    """Build the stable error JSON and log the internal detail."""
    exc_type = type(exc)
    status = _STATUS_MAP.get(exc_type, 500)
    code = _CODE_MAP.get(exc_type, "internal_error")
    message = _SAFE_MESSAGES.get(
        exc_type, "An internal error occurred. Please escalate to a human clinician."
    )

    trace_id = getattr(request.state, "request_id", "unknown")

    logger.error(
        "pipeline error",
        extra={
            "error_code": code,
            "error_reason": exc.reason,
            "trace_id": trace_id,
            "status": status,
        },
    )

    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for non-PipelineError exceptions. Never leak internals."""
    trace_id = getattr(request.state, "request_id", "unknown")

    logger.error(
        "unhandled exception",
        extra={
            "error_class": type(exc).__name__,
            "trace_id": trace_id,
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An internal error occurred. Please escalate to a human clinician.",
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """Wire all exception handlers into the FastAPI app."""
    for exc_class in _STATUS_MAP:
        app.add_exception_handler(exc_class, _error_response)  # type: ignore[arg-type]

    app.add_exception_handler(Exception, _unhandled_error)  # type: ignore[arg-type]
