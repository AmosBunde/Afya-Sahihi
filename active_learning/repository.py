"""Active-learning Postgres repository.

Reads from the candidate pool (views or batched Tier 2 replay rows),
writes a round's assignments to `al_labeled_pool`. Both operations
run inside explicit transactions with SET LOCAL statement_timeout —
same discipline as the labeling repo from #29.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Protocol

from active_learning.acquisition import CandidateCase
from active_learning.assignment import Assignment

logger = logging.getLogger(__name__)


_CANDIDATE_SQL = """
SELECT case_id, stratum, token_logprobs, conformal_set_size,
       conformal_coverage_target, truth_in_set, ingested_at::text AS ingested_at_iso
FROM al_candidate_pool_v
WHERE ingested_at >= $1
ORDER BY case_id
LIMIT $2;
"""

_INSERT_SQL = """
INSERT INTO al_labeled_pool (
    case_id, arm, week_iso, acquisition_function, assigned_at
) VALUES ($1, $2, $3, $4, now())
ON CONFLICT (case_id, week_iso) DO NOTHING;
"""


class ConnectionLike(Protocol):
    async def execute(self, query: str, *args: Any) -> Any: ...
    async def fetch(self, query: str, *args: Any) -> list[Any]: ...
    def transaction(self, **kwargs: Any) -> Any: ...


class PoolLike(Protocol):
    def acquire(self) -> Any: ...


class ALRepository:
    def __init__(self, *, pool: PoolLike, statement_timeout_ms: int = 5000) -> None:
        self._pool = pool
        self._timeout_ms = statement_timeout_ms

    async def load_candidates(
        self,
        *,
        ingested_since: Any,
        max_rows: int,
    ) -> list[CandidateCase]:
        """Pull the candidate pool. `ingested_since` is a tz-aware datetime."""
        if max_rows <= 0:
            return []
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"SET LOCAL statement_timeout = '{self._timeout_ms}ms'"
                )
                rows = await conn.fetch(_CANDIDATE_SQL, ingested_since, max_rows)
        out: list[CandidateCase] = []
        for row in rows:
            out.append(
                CandidateCase(
                    case_id=row["case_id"],
                    stratum=row["stratum"],
                    token_logprobs=tuple(row["token_logprobs"] or ()),
                    conformal_set_size=int(row["conformal_set_size"]),
                    conformal_coverage_target=float(row["conformal_coverage_target"]),
                    truth_in_set=row["truth_in_set"],
                    ingested_at_iso=row["ingested_at_iso"],
                )
            )
        return out

    async def persist_assignments(self, assignments: list[Assignment]) -> int:
        """Insert one row per assignment. Returns # rows actually inserted.

        ON CONFLICT DO NOTHING means re-running the same week's round
        is idempotent: case_id+week_iso unique key dedups. Returns the
        count of NEW inserts so the caller can log "added 14 of 20".
        """
        if not assignments:
            return 0
        inserted = 0
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"SET LOCAL statement_timeout = '{self._timeout_ms}ms'"
                )
                for a in assignments:
                    row = asdict(a)
                    result = await conn.execute(
                        _INSERT_SQL,
                        row["case_id"],
                        row["arm"],
                        row["week_iso"],
                        row["acquisition_function"],
                    )
                    # asyncpg returns "INSERT 0 1" on an insert, "INSERT 0 0"
                    # on ON CONFLICT skip.
                    if isinstance(result, str) and result.endswith(" 1"):
                        inserted += 1
        logger.info(
            "al assignments persisted",
            extra={
                "total": len(assignments),
                "inserted": inserted,
                "skipped": len(assignments) - inserted,
            },
        )
        return inserted
