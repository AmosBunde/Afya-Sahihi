"""Weekly AL round orchestration.

One public function: `run_round`. It:
  1. Pulls the candidate pool from the repository.
  2. Scores with the configured acquisition function.
  3. Picks top `batch_size / (1 - control_ratio)` treatment-eligible
     cases so that after arm assignment we end up with ≈ batch_size
     assignments across both arms.
  4. Builds Assignments via `build_assignments` (deterministic hash
     on case_id+week+seed → arm).
  5. Persists and pushes the batch onto the labeling Redis queue.

Kept as a pure async function so tests drive it with fakes. The
runtime wiring (APScheduler trigger, Postgres pool, Redis client)
lives in `_bootstrap()` below.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from active_learning.acquisition import (
    CandidateCase,
    resolve as resolve_acquisition,
    top_k,
)
from active_learning.assignment import Assignment, build_assignments

logger = logging.getLogger(__name__)


class RepositoryLike(Protocol):
    async def load_candidates(
        self, *, ingested_since: Any, max_rows: int
    ) -> list[CandidateCase]: ...

    async def persist_assignments(self, assignments: list[Assignment]) -> int: ...


class QueuePusherLike(Protocol):
    async def push_batch(self, *, case_ids: list[str], week_iso: str) -> None: ...


@dataclass(frozen=True, slots=True)
class RoundResult:
    week_iso: str
    acquisition_function: str
    n_candidates: int
    n_assignments: int
    n_treatment: int
    n_control: int


def iso_week(now: datetime) -> str:
    """ISO year-week string, e.g. '2026-W16'. tz-aware input only."""
    if now.tzinfo is None:
        raise ValueError("now must be tz-aware")
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


async def run_round(
    *,
    repository: RepositoryLike,
    queue: QueuePusherLike,
    acquisition_function_name: str,
    batch_size: int,
    control_ratio: float,
    seed: str,
    now: datetime,
    candidate_window_days: int = 7,
    rng_seed: int | None = None,
) -> RoundResult:
    """One AL round. Deterministic given (now, seed, pool).

    `rng_seed` is the random.Random seed used by the random and
    random-arm acquisition functions. Paper P3 fixes it to
    hash(seed + week) so replays are reproducible.
    """
    import random
    from datetime import timedelta

    if not (0.0 < control_ratio < 1.0):
        raise ValueError("control_ratio must be in (0, 1)")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    week = iso_week(now)
    since = now - timedelta(days=candidate_window_days)

    # Over-sample the pool so top_k has room to pick after we reserve
    # a portion for the control arm. A 2x multiplier gives headroom.
    pool_limit = max(batch_size * 4, 50)
    candidates = await repository.load_candidates(
        ingested_since=since, max_rows=pool_limit
    )

    # RNG used for acquisition-function scoring reproducibility (Paper P3
    # replays). NOT security-sensitive — arm assignment uses SHA-256 via
    # active_learning.assignment.
    effective_seed = (
        rng_seed if rng_seed is not None else hash(f"{seed}|{week}") & 0xFFFFFFFF
    )
    rng = random.Random(effective_seed)  # nosec B311

    fn = resolve_acquisition(acquisition_function_name)
    scores = fn.score(candidates=candidates, rng=rng)
    picked = top_k(candidates=candidates, scores=scores, k=batch_size)
    case_ids = [c.case_id for c in picked]

    assignments = build_assignments(
        case_ids=case_ids,
        week_iso=week,
        seed=seed,
        control_ratio=control_ratio,
        acquisition_function_name=acquisition_function_name,
    )
    await repository.persist_assignments(assignments)
    await queue.push_batch(case_ids=case_ids, week_iso=week)

    n_t = sum(1 for a in assignments if a.arm == "treatment")
    n_c = sum(1 for a in assignments if a.arm == "control")
    result = RoundResult(
        week_iso=week,
        acquisition_function=acquisition_function_name,
        n_candidates=len(candidates),
        n_assignments=len(assignments),
        n_treatment=n_t,
        n_control=n_c,
    )
    logger.info(
        "al round complete",
        extra={
            "week": week,
            "acquisition": acquisition_function_name,
            "n_candidates": result.n_candidates,
            "n_assignments": result.n_assignments,
            "n_treatment": n_t,
            "n_control": n_c,
        },
    )
    return result


async def _main() -> int:  # pragma: no cover — integration shim
    import asyncpg  # type: ignore[import-not-found]

    from active_learning.repository import ALRepository
    from active_learning.settings import ActiveLearningSettings

    settings = ActiveLearningSettings()  # type: ignore[call-arg]
    if not settings.al_enabled:
        logger.info("AL disabled; exiting")
        return 0

    pool = await asyncpg.create_pool(
        host=settings.pg_host,
        port=settings.pg_port,
        database=settings.pg_database,
        user=settings.pg_user,
        password=settings.pg_password,
        min_size=settings.pg_pool_min,
        max_size=settings.pg_pool_max,
    )
    try:
        repo = ALRepository(
            pool=pool, statement_timeout_ms=settings.pg_statement_timeout_ms
        )

        class _RedisQueue:
            async def push_batch(self, *, case_ids: list[str], week_iso: str) -> None:
                import redis.asyncio as aioredis  # type: ignore[import-untyped]

                client = aioredis.Redis(
                    host=settings.redis_host, port=settings.redis_port
                )
                try:
                    async with asyncio.timeout(5):
                        pipe = client.pipeline()
                        for cid in case_ids:
                            pipe.rpush(f"{settings.labeling_queue_key}:{week_iso}", cid)
                        await pipe.execute()
                finally:
                    await client.aclose()

        await run_round(
            repository=repo,
            queue=_RedisQueue(),
            acquisition_function_name=settings.al_acquisition_function,
            batch_size=settings.al_batch_size,
            control_ratio=settings.al_control_arm_ratio,
            seed=settings.al_seed,
            now=datetime.now(timezone.utc),
        )
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(asyncio.run(_main()))
