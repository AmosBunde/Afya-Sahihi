"""Unit tests for the gateway API — health, rate limiting, chat request model."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.chat import ChatRequest
from app.api.middleware import RateLimiter
from app.settings import Settings


def _test_settings() -> Settings:
    return Settings(
        pg_host="localhost",
        pg_database="test",
        pg_user="postgres",
        pg_password="test",
        oidc_issuer_url="",
        redis_host="localhost",
    )


# ---- ChatRequest validation ----


def test_chat_request_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(query="", language="en")


def test_chat_request_rejects_too_long_query() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(query="x" * 4001, language="en")


def test_chat_request_accepts_valid_query() -> None:
    r = ChatRequest(query="What is malaria?", language="en")
    assert r.query == "What is malaria?"


def test_chat_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(query="test", language="en", extra="bad")  # type: ignore[call-arg]


# ---- Rate limiter ----


class _FakeRedis:
    """Async-compatible fake Redis for rate limiter tests."""

    def __init__(self) -> None:
        self._store: dict[str, int] = {}

    def pipeline(self) -> _FakeRedis:
        self._pipe_ops: list[tuple[str, str, int | None]] = []
        return self

    def incr(self, key: str) -> None:
        self._pipe_ops.append(("incr", key, None))

    def expire(self, key: str, ttl: int) -> None:
        self._pipe_ops.append(("expire", key, ttl))

    async def execute(self) -> list[int]:
        results: list[int] = []
        for op, key, _ in self._pipe_ops:
            if op == "incr":
                self._store[key] = self._store.get(key, 0) + 1
                results.append(self._store[key])
            elif op == "expire":
                results.append(0)
        return results


@pytest.mark.asyncio
async def test_rate_limiter_allows_under_limit() -> None:
    settings = _test_settings()
    redis = _FakeRedis()
    limiter = RateLimiter(redis, settings)

    allowed, retry_after = await limiter.check("user1")
    assert allowed is True
    assert retry_after == 0


@pytest.mark.asyncio
async def test_rate_limiter_blocks_over_minute_limit() -> None:
    settings = Settings(
        pg_host="localhost",
        pg_database="test",
        pg_user="postgres",
        pg_password="test",
        rate_limit_per_user_per_minute=2,
        rate_limit_per_user_per_day=500,
        oidc_issuer_url="",
    )
    redis = _FakeRedis()
    limiter = RateLimiter(redis, settings)

    await limiter.check("user1")
    await limiter.check("user1")
    allowed, retry_after = await limiter.check("user1")

    assert allowed is False
    assert retry_after > 0


@pytest.mark.asyncio
async def test_rate_limiter_allows_when_redis_is_none() -> None:
    settings = _test_settings()
    limiter = RateLimiter(None, settings)

    allowed, retry_after = await limiter.check("user1")
    assert allowed is True


# ---- Health endpoint (no lifespan — just route shape) ----


def test_healthz_returns_200() -> None:
    # Use a minimal app without lifespan for route-shape testing
    from fastapi import FastAPI

    from app.api.health import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
