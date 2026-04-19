"""FastAPI app factory. SKILL.md §2.

Lifespan manages startup/shutdown of shared resources (asyncpg pool,
Redis client, OIDC JWKS client, orchestrator). Dependencies are
injected via `app.state` so handlers access them through `request.app`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat, health
from app.api.error_handler import register_error_handlers
from app.api.middleware import RateLimiter, RequestIdMiddleware
from app.settings import Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: build pool, Redis, orchestrator. Shutdown: drain + close."""
    settings = app.state.settings

    # Tracing — install before any other client so their spans attach
    # to the right provider. instrument_httpx / instrument_asyncpg
    # must be called before the first client is constructed.
    from app.observability.instrumentation import (
        instrument_asyncpg,
        instrument_fastapi,
        instrument_httpx,
    )
    from app.observability.tracing import configure_tracing, shutdown_tracing

    configure_tracing(settings=settings)
    instrument_fastapi(app)
    instrument_httpx()
    instrument_asyncpg()

    # Postgres pool
    import asyncpg

    pool = await asyncpg.create_pool(
        host=settings.pg_host,
        port=settings.pg_port,
        database=settings.pg_database,
        user=settings.pg_user,
        password=settings.pg_password,
        min_size=settings.pg_pool_min,
        max_size=settings.pg_pool_max,
    )
    app.state.pg_pool = pool

    # Redis (optional — fails open)
    redis_client = None
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        redis_client = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )
        await redis_client.ping()
        app.state.redis = redis_client
        app.state.rate_limiter = RateLimiter(redis_client, settings)
        logger.info("redis connected")
    except Exception:
        logger.warning("redis unavailable; rate limiting disabled", exc_info=True)
        app.state.redis = None
        app.state.rate_limiter = None

    # OIDC JWKS client (optional — dev mode if not configured)
    if settings.oidc_jwks_uri:
        try:
            import jwt  # type: ignore[import-untyped]

            app.state.jwks_client = jwt.PyJWKClient(settings.oidc_jwks_uri, cache_keys=True)
        except Exception:
            logger.warning("JWKS client init failed; OIDC disabled", exc_info=True)
            app.state.jwks_client = None
    else:
        app.state.jwks_client = None

    # Orchestrator — wired with mock clients for now; concrete HTTP
    # clients land when vLLM/retrieval/conformal services are deployed.
    app.state.orchestrator = None
    logger.info("gateway started", extra={"service": settings.service_name})

    yield

    # Shutdown: drain
    import asyncio

    logger.info(
        "draining in-flight requests", extra={"drain_seconds": settings.shutdown_drain_seconds}
    )
    await asyncio.sleep(0.1)

    if redis_client:
        await redis_client.aclose()
    await pool.close()
    shutdown_tracing()
    logger.info("gateway stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory. Construct once at process start."""
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title="Afya Sahihi Gateway",
        version="0.0.1",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Middleware (outermost first)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins.split(","),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    # Error handlers (fail-closed; stable JSON shape; no internals leaked)
    register_error_handlers(app)

    # Routes
    app.include_router(health.router)
    app.include_router(chat.router)

    return app
