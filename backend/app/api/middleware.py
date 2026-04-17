"""Auth, rate-limit, and request-ID middleware.

OIDC: validates JWT from Authorization header against the configured
issuer. Audience claim is checked (review SKILL §1.2). Token decoding
uses PyJWT with the JWKS fetched at startup.

Rate limit: Redis-backed sliding window. Returns 429 with Retry-After
header when exhausted. Fails open on Redis errors (warn, not block).

Request ID: injects X-Request-ID into every response for trace
correlation.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.settings import Settings

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


async def verify_oidc_token(request: Request) -> dict[str, Any]:
    """FastAPI dependency: extract and validate the OIDC JWT.

    Checks: signature (via JWKS), expiry, audience. Returns the decoded
    claims dict. Raises 401 on any failure.

    The JWKS client is constructed once at app startup and injected via
    `request.app.state.jwks_client`. If OIDC is not configured (empty
    issuer URL), all requests are allowed — this is the dev/test mode.
    """
    settings: Settings = request.app.state.settings
    if not settings.oidc_issuer_url:
        return {"sub": "dev-user", "aud": settings.oidc_audience}

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth_header[7:]
    try:
        import jwt  # type: ignore[import-untyped]

        jwks_client: Any = request.app.state.jwks_client
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer_url,
        )
        return claims  # type: ignore[no-any-return]
    except Exception as exc:
        logger.warning("OIDC token validation failed", extra={"error": str(exc)})
        raise HTTPException(status_code=401, detail="Invalid token") from exc


class RateLimiter:
    """Redis-backed sliding-window rate limiter.

    Returns (allowed: bool, retry_after: int). Fails open on Redis
    errors — a Redis outage degrades rate enforcement, not availability.
    """

    def __init__(self, redis_client: Any, settings: Settings) -> None:
        self._redis = redis_client
        self._per_minute = settings.rate_limit_per_user_per_minute
        self._per_day = settings.rate_limit_per_user_per_day

    async def check(self, user_id: str) -> tuple[bool, int]:
        if self._redis is None:
            return (True, 0)

        try:
            now = int(time.time())
            minute_key = f"afya:rl:{user_id}:m:{now // 60}"
            day_key = f"afya:rl:{user_id}:d:{now // 86400}"

            pipe = self._redis.pipeline()
            pipe.incr(minute_key)
            pipe.expire(minute_key, 120)
            pipe.incr(day_key)
            pipe.expire(day_key, 172800)
            results = await pipe.execute()

            minute_count = results[0]
            day_count = results[2]

            if minute_count > self._per_minute:
                return (False, 60 - (now % 60))
            if day_count > self._per_day:
                return (False, 86400 - (now % 86400))
            return (True, 0)
        except Exception:
            logger.warning("rate limiter redis error; allowing request", exc_info=True)
            return (True, 0)
