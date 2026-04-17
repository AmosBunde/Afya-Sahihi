"""POST /api/chat — SSE streaming endpoint.

Accepts a clinical query, runs it through the orchestrator, and streams
the response tokens + provenance + conformal set via Server-Sent Events.
SSE keepalives fire every `sse_keepalive_interval_seconds` to prevent
Traefik from dropping idle connections.

Auth: requires a valid OIDC token (via `verify_oidc_token` dependency).
Rate limit: checked before pipeline execution; 429 on exhaustion.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sse_starlette.sse import EventSourceResponse  # type: ignore[import-untyped]

from app.api.middleware import RateLimiter, verify_oidc_token
from app.settings import Settings
from app.state import ValidatedQuery

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    query: str = Field(min_length=3, max_length=4000)
    language: str = Field(default="en", min_length=2, max_length=10)
    retrieval_filters: dict[str, object] | None = None


class ChatEvent(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    event: str
    data: dict[str, object]


_oidc_dep = Depends(verify_oidc_token)


@router.post("/api/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    claims: dict[str, Any] = _oidc_dep,  # noqa: B008
) -> EventSourceResponse:
    settings: Settings = request.app.state.settings
    user_id = claims.get("sub", "anonymous")

    # Rate limit
    rate_limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if rate_limiter is not None:
        allowed, retry_after = await rate_limiter.check(user_id)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

    query = ValidatedQuery(
        id=str(uuid.uuid4()),
        text=body.query,
        language=body.language,
        retrieval_filters=body.retrieval_filters,
    )

    orchestrator = request.app.state.orchestrator

    keepalive_interval = settings.sse_keepalive_interval_seconds

    async def event_stream() -> Any:
        try:
            yield _sse("start", {"query_id": query.id})

            state = await orchestrator.run(query)

            if state.errors:
                error = state.errors[0]
                yield _sse(
                    "error",
                    {
                        "reason": getattr(error, "reason", str(error)),
                        "query_id": query.id,
                    },
                )
                return

            if state.generation_result is not None:
                yield _sse(
                    "generation",
                    {
                        "text": state.generation_result.response_text,
                        "model_version": state.generation_result.model_version,
                        "n_tokens": state.generation_result.n_tokens,
                    },
                )

            if state.retrieval_result is not None:
                yield _sse(
                    "provenance",
                    {
                        "n_chunks": len(state.retrieval_result.chunks),
                        "top1_similarity": state.retrieval_result.top1_similarity,
                        "fusion_strategy": state.retrieval_result.fusion_strategy,
                    },
                )

            if state.conformal_result is not None:
                yield _sse(
                    "conformal",
                    {
                        "set_size": state.conformal_result.set_size,
                        "target_coverage_met": state.conformal_result.target_coverage_met,
                        "prediction_set": list(state.conformal_result.prediction_set),
                    },
                )

            yield _sse("done", {"query_id": query.id})

        except asyncio.CancelledError:
            logger.info("client disconnected", extra={"query_id": query.id})
            raise
        except Exception as exc:
            logger.error(
                "chat stream error",
                extra={"query_id": query.id, "error_class": type(exc).__name__},
            )
            yield _sse("error", {"reason": "internal_error", "query_id": query.id})

    return EventSourceResponse(
        event_stream(),
        ping=keepalive_interval,
    )


def _sse(event: str, data: dict[str, object]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, default=str)}
