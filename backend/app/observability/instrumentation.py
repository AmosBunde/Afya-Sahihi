"""Auto-instrumentation wiring.

Each instrumentor is optional — imports are guarded so a developer on a
dev-deps-only install can still run the app. In production all three
libraries are present (fastapi, httpx, asyncpg) and we wire them up.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def instrument_fastapi(app: Any) -> None:
    """Add FastAPI server-span auto-instrumentation."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        logger.info("fastapi instrumentation not installed; skipping")
        return
    FastAPIInstrumentor.instrument_app(app)  # type: ignore[no-untyped-call]


def instrument_httpx() -> None:
    """Add httpx client-span auto-instrumentation.

    Does nothing if the httpx instrumentor is absent. Call once per
    process because the instrumentor patches the httpx module globally.
    """
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    except ImportError:
        logger.info("httpx instrumentation not installed; skipping")
        return
    HTTPXClientInstrumentor().instrument()  # type: ignore[no-untyped-call]


def instrument_asyncpg() -> None:
    """Add asyncpg query-span auto-instrumentation."""
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
    except ImportError:
        logger.info("asyncpg instrumentation not installed; skipping")
        return
    AsyncPGInstrumentor().instrument()  # type: ignore[no-untyped-call]
