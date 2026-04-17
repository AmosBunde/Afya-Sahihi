"""/healthz and /readyz endpoints. SKILL.md §2."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(request: Request, response: Response) -> dict[str, object]:
    """Check every dependency the gateway needs to serve traffic."""
    checks: dict[str, str] = {}
    all_ok = True

    # Postgres
    pool = getattr(request.app.state, "pg_pool", None)
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            checks["postgres"] = "ok"
        except Exception:
            checks["postgres"] = "fail"
            all_ok = False
    else:
        checks["postgres"] = "not_configured"

    # Redis
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "fail"
            all_ok = False
    else:
        checks["redis"] = "not_configured"

    if not all_ok:
        response.status_code = 503

    return {"status": "ready" if all_ok else "degraded", "checks": checks}
