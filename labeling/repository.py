"""Grade persistence and agreement-set loading.

Two responsibilities:
  1. `insert_grade` — write a reviewer's scored case to `grades` with
     chain-of-custody. SET LOCAL statement_timeout enforced.
  2. `load_agreement_matrix` — pull dual-rated cases for daily Fleiss
     kappa computation. Returns per-case × per-dimension rating lists.

We use a Protocol for the pool so unit tests can inject a fake without
testcontainers. Integration tests (in the backend suite) exercise the
real SQL against a seeded Postgres.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from labeling.rubric import RUBRIC_DIMENSIONS, Grade, grade_to_row_dict

logger = logging.getLogger(__name__)


_INSERT_SQL = """
INSERT INTO grades (
    grade_id, case_id, reviewer_id, reviewer_role, rubric_version,
    accuracy, safety, guideline_alignment, local_appropriateness, clarity,
    notes, time_spent_seconds, submitted_at, prev_hash, row_hash
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15);
"""

_LATEST_HASH_SQL = """
SELECT row_hash
FROM grades
WHERE reviewer_id = $1
ORDER BY submitted_at DESC
LIMIT 1;
"""

_AGREEMENT_SQL = """
SELECT case_id, reviewer_id, accuracy, safety, guideline_alignment,
       local_appropriateness, clarity
FROM grades
WHERE submitted_at >= $1 AND submitted_at < $2
ORDER BY case_id, submitted_at;
"""


class ConnectionLike(Protocol):
    async def execute(self, query: str, *args: Any) -> Any: ...
    async def fetchval(self, query: str, *args: Any) -> Any: ...
    async def fetch(self, query: str, *args: Any) -> list[Any]: ...


class PoolLike(Protocol):
    def acquire(self) -> Any: ...


class GradeRepository:
    """Write-and-read layer for grades. Raw SQL per ADR-0008."""

    def __init__(self, *, pool: PoolLike, statement_timeout_ms: int = 5000) -> None:
        self._pool = pool
        self._timeout_ms = statement_timeout_ms

    async def latest_row_hash(self, *, reviewer_id: str) -> str:
        """Most recent row_hash for this reviewer, or '' if they have no rows.

        The labeling UI chains its submissions per reviewer, so a new
        grade's prev_hash is this function's return value. A reviewer's
        first grade chains off the empty string (genesis).
        """
        async with self._pool.acquire() as conn:
            await conn.execute(f"SET LOCAL statement_timeout = '{self._timeout_ms}ms'")
            value = await conn.fetchval(_LATEST_HASH_SQL, reviewer_id)
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        raise TypeError(f"unexpected row_hash type: {type(value).__name__}")

    async def insert_grade(self, grade: Grade) -> None:
        """Persist a grade. Fails closed: any error propagates."""
        row = grade_to_row_dict(grade)
        async with self._pool.acquire() as conn:
            await conn.execute(f"SET LOCAL statement_timeout = '{self._timeout_ms}ms'")
            await conn.execute(
                _INSERT_SQL,
                row["grade_id"],
                row["case_id"],
                row["reviewer_id"],
                row["reviewer_role"],
                row["rubric_version"],
                row["accuracy"],
                row["safety"],
                row["guideline_alignment"],
                row["local_appropriateness"],
                row["clarity"],
                row["notes"],
                row["time_spent_seconds"],
                row["submitted_at"],
                row["prev_hash"],
                row["row_hash"],
            )
        logger.info(
            "grade persisted",
            extra={
                "grade_id": grade.grade_id,
                "case_id": grade.case_id,
                "reviewer_role": grade.reviewer_role,
            },
        )

    async def load_agreement_ratings(
        self,
        *,
        window_start: Any,
        window_end: Any,
    ) -> dict[str, dict[str, list[dict[str, int]]]]:
        """Return ratings grouped by case then dimension for the window.

        Shape: `{case_id: {dimension: [{"reviewer_id": rid, "score": s}, ...]}}`.
        The daily kappa job picks up this structure, filters to cases
        with >= 2 raters, and computes Fleiss kappa per dimension.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(f"SET LOCAL statement_timeout = '{self._timeout_ms}ms'")
            rows = await conn.fetch(_AGREEMENT_SQL, window_start, window_end)

        out: dict[str, dict[str, list[dict[str, int]]]] = {}
        for row in rows:
            case_id = row["case_id"]
            reviewer_id = row["reviewer_id"]
            by_dim = out.setdefault(case_id, {dim: [] for dim in RUBRIC_DIMENSIONS})
            for dim in RUBRIC_DIMENSIONS:
                by_dim[dim].append({"reviewer_id": reviewer_id, "score": int(row[dim])})
        return out
