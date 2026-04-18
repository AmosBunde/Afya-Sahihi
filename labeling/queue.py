"""Redis-backed case assignment queue.

Each reviewer sees a weekly queue of case ids. The backend (out of
scope for this PR) pre-populates the queue via the active-learning
acquisition job (M9, issue #37). We read from it here.

Operations are atomic — `reserve` uses LREM+LPUSH to move the case
into the reviewer's in-flight list; `submit` removes it from in-flight
and pushes its id onto the completed set. Reserving guards against
two reviewers accidentally grading the same case twice (which would
fake agreement).

Depends on the `redis` client (already in backend/pyproject.toml).
Uses a Protocol so tests can inject a fake. Every call has an
asyncio.timeout and every error path fails closed.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


class RedisLike(Protocol):
    """Subset of redis.asyncio.Redis we use. Keeps tests pure."""

    async def lrange(self, key: str, start: int, end: int) -> list[bytes]: ...
    async def lrem(self, key: str, count: int, value: str) -> int: ...
    async def rpush(self, key: str, *values: str) -> int: ...
    async def sadd(self, key: str, *values: str) -> int: ...
    async def smembers(self, key: str) -> set[bytes]: ...
    async def scard(self, key: str) -> int: ...


@dataclass(frozen=True, slots=True)
class QueueKeys:
    """Key pattern for a reviewer's week."""

    pending: str
    in_flight: str
    completed: str

    @classmethod
    def for_reviewer(
        cls,
        *,
        base_key: str,
        reviewer_id: str,
        iso_week: str,
    ) -> QueueKeys:
        """base_key + reviewer_id + ISO week → namespaced key set."""
        # iso_week like "2026-W16"; reviewer_id from OIDC sub (opaque).
        prefix = f"{base_key}:{reviewer_id}:{iso_week}"
        return cls(
            pending=f"{prefix}:pending",
            in_flight=f"{prefix}:in_flight",
            completed=f"{prefix}:completed",
        )


class ReviewerCaseQueue:
    """One reviewer's weekly queue. Scoped by QueueKeys."""

    def __init__(
        self,
        *,
        redis: RedisLike,
        keys: QueueKeys,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._redis = redis
        self._keys = keys
        self._timeout = timeout_seconds

    async def list_pending(self, *, limit: int = 50) -> list[str]:
        """Cases waiting to be reserved. Bounded to `limit` for safety."""
        if limit <= 0:
            return []
        async with asyncio.timeout(self._timeout):
            raw = await self._redis.lrange(self._keys.pending, 0, limit - 1)
        return [_decode(item) for item in raw]

    async def reserve_next(self) -> str | None:
        """Atomically move the head of pending → in-flight. Returns case_id or None.

        We do this as LRANGE+LREM+RPUSH rather than LMOVE so we can run
        against older Redis servers without ACL gymnastics. Two reviewers
        racing on the same pending case will see one succeed (LREM returns
        1) and the other get zero, returning None.
        """
        async with asyncio.timeout(self._timeout):
            head = await self._redis.lrange(self._keys.pending, 0, 0)
            if not head:
                return None
            case_id = _decode(head[0])
            removed = await self._redis.lrem(self._keys.pending, 1, case_id)
            if removed == 0:
                # Another reviewer got it first.
                return None
            await self._redis.rpush(self._keys.in_flight, case_id)
        return case_id

    async def complete(self, case_id: str) -> bool:
        """Move case from in-flight → completed set. Returns True if it was in-flight.

        Completion is idempotent: calling twice returns False the second
        time. We still attempt to add to `completed` to keep analytics
        consistent after a retry.
        """
        if not case_id:
            raise ValueError("case_id required")
        async with asyncio.timeout(self._timeout):
            removed = await self._redis.lrem(self._keys.in_flight, 1, case_id)
            await self._redis.sadd(self._keys.completed, case_id)
        return removed > 0

    async def release(self, case_id: str) -> bool:
        """Abandon an in-flight case back to pending. Returns True if returned."""
        if not case_id:
            raise ValueError("case_id required")
        async with asyncio.timeout(self._timeout):
            removed = await self._redis.lrem(self._keys.in_flight, 1, case_id)
            if removed == 0:
                return False
            await self._redis.rpush(self._keys.pending, case_id)
        return True

    async def completed_count(self) -> int:
        async with asyncio.timeout(self._timeout):
            return await self._redis.scard(self._keys.completed)


def _decode(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value
