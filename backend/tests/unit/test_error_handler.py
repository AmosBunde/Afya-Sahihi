"""Tests for the fail-closed error handler.

Every PipelineError subclass is exercised. Adversarial inputs verify
that no internal detail (stack traces, SQL, file paths) leaks into the
response body. SKILL.md §6, review SKILL §3.1.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.error_handler import register_error_handlers
from app.errors import (
    ConformalFailed,
    GenerationFailed,
    PipelineError,
    PrefilterRejected,
    RetrievalFailed,
    StrictReviewRejected,
    ValidationFailed,
)


def _app_raising(exc: Exception) -> FastAPI:
    """Build a minimal FastAPI that raises `exc` on GET /."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/")
    async def root(request: Request) -> None:
        request.state.request_id = "test-trace-001"
        raise exc

    return app


# ---- Every error type maps to the stable shape ----


@pytest.mark.parametrize(
    "exc_class,expected_status,expected_code",
    [
        (ValidationFailed, 422, "validation_failed"),
        (PrefilterRejected, 422, "prefilter_rejected"),
        (RetrievalFailed, 502, "retrieval_failed"),
        (GenerationFailed, 502, "generation_failed"),
        (StrictReviewRejected, 422, "strict_review_rejected"),
        (ConformalFailed, 502, "conformal_failed"),
    ],
)
def test_pipeline_error_returns_stable_shape(
    exc_class: type[PipelineError],
    expected_status: int,
    expected_code: str,
) -> None:
    exc = exc_class(reason="test reason", detail={"internal": "data"})
    client = TestClient(_app_raising(exc), raise_server_exceptions=False)
    resp = client.get("/")

    assert resp.status_code == expected_status
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == expected_code
    assert isinstance(body["error"]["message"], str)
    assert len(body["error"]["message"]) > 0


# ---- No internals leak ----


def test_internal_detail_not_in_response() -> None:
    exc = RetrievalFailed(
        reason="connection refused to pg at /var/run/postgresql/.s.PGSQL.5432",
        detail={"sql": "SELECT * FROM chunks WHERE ...", "traceback": "File /app/..."},
    )
    client = TestClient(_app_raising(exc), raise_server_exceptions=False)
    resp = client.get("/")
    text = resp.text

    assert "/var/run" not in text
    assert "SELECT" not in text
    assert "traceback" not in text.lower()
    assert "File /" not in text


def test_unhandled_exception_returns_500_no_leak() -> None:
    exc = RuntimeError("FATAL: password authentication failed for user 'admin'")
    client = TestClient(_app_raising(exc), raise_server_exceptions=False)
    resp = client.get("/")

    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "internal_error"
    assert "password" not in resp.text
    assert "admin" not in resp.text


def test_adversarial_sql_in_reason_not_leaked() -> None:
    exc = GenerationFailed(
        reason='ERROR: relation "users" does not exist\nLINE 1: SELECT * FROM users'
    )
    client = TestClient(_app_raising(exc), raise_server_exceptions=False)
    resp = client.get("/")

    assert "SELECT" not in resp.text
    assert "users" not in resp.text
    assert "relation" not in resp.text


def test_response_always_has_escalation_message() -> None:
    for exc_class in [
        ValidationFailed,
        PrefilterRejected,
        RetrievalFailed,
        GenerationFailed,
        StrictReviewRejected,
        ConformalFailed,
    ]:
        exc = exc_class(reason="x")
        client = TestClient(_app_raising(exc), raise_server_exceptions=False)
        resp = client.get("/")
        body = resp.json()
        msg = body["error"]["message"].lower()
        assert (
            "clinician" in msg or "retry" in msg
        ), f"{exc_class.__name__} message lacks escalation guidance"
