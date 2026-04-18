"""Grade persistence and agreement-set loading.

Two responsibilities:
  1. `insert_next_grade` — read latest row_hash, compute new row_hash,
     insert, all inside one SERIALIZABLE transaction per reviewer so
     concurrent submissions cannot fork the hash chain. SET LOCAL
     statement_timeout enforced.
  2. `load_agreement_ratings` — pull grades in a time window grouped by
     case then dimension for daily Fleiss kappa.

We use Protocols for pool/connection so unit tests can inject a fake
without testcontainers. Integration tests (landing with backend's test
suite) exercise the real SQL against a seeded Postgres.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Protocol

from labeling.rubric import (
    RUBRIC_DIMENSIONS,
    RubricScores,
    build_grade,
    grade_to_row_dict,
)

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

# pg_advisory_xact_lock serialises concurrent writes per reviewer so the
# latest_hash → insert read-modify-write cycle is atomic. Using hashtext
# keeps the lock key within int4 regardless of reviewer_id length.
_ADVISORY_LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtext($1));"


class ConnectionLike(Protocol):
    async def execute(self, query: str, *args: Any) -> Any: ...
    async def fetchval(self, query: str, *args: Any) -> Any: ...
    async def fetch(self, query: str, *args: Any) -> list[Any]: ...
    def transaction(self, **kwargs: Any) -> Any: ...


class PoolLike(Protocol):
    def acquire(self) -> Any: ...


class GradeRepository:
    """Write-and-read layer for grades. Raw SQL per ADR-0008."""

    def __init__(self, *, pool: PoolLike, statement_timeout_ms: int = 5000) -> None:
        self._pool = pool
        self._timeout_ms = statement_timeout_ms

    async def insert_next_grade(
        self,
        *,
        grade_id: str,
        case_id: str,
        reviewer_id: str,
        reviewer_role: str,
        rubric_version: str,
        scores: RubricScores,
        notes: str,
        time_spent_seconds: int,
        submitted_at: datetime,
    ) -> str:
        """Atomically chain and insert a grade for `reviewer_id`.

        Inside one transaction:
          1. Take an advisory lock keyed on reviewer_id (serialises
             concurrent writers by that reviewer).
          2. Read the reviewer's most recent row_hash as prev_hash.
          3. Compute row_hash deterministically over the payload.
          4. INSERT.

        Returns the computed row_hash. The caller can verify the chain
        by re-running compute_row_hash over the payload.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"SET LOCAL statement_timeout = '{self._timeout_ms}ms'"
                )
                await conn.execute(_ADVISORY_LOCK_SQL, reviewer_id)

                prev_hash_raw = await conn.fetchval(_LATEST_HASH_SQL, reviewer_id)
                prev_hash = prev_hash_raw if isinstance(prev_hash_raw, str) else ""

                grade = build_grade(
                    grade_id=grade_id,
                    case_id=case_id,
                    reviewer_id=reviewer_id,
                    reviewer_role=reviewer_role,
                    rubric_version=rubric_version,
                    scores=scores,
                    notes=notes,
                    time_spent_seconds=time_spent_seconds,
                    submitted_at=submitted_at,
                    prev_hash=prev_hash,
                )
                row = grade_to_row_dict(grade)
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
                "grade_id": grade_id,
                "case_id": case_id,
                "reviewer_role": reviewer_role,
            },
        )
        return grade.row_hash

    async def load_agreement_ratings(
        self,
        *,
        window_start: Any,
        window_end: Any,
    ) -> dict[str, dict[str, list[dict[str, int]]]]:
        """Return ratings grouped by case then dimension for the window.

        Shape: `{case_id: {dimension: [{"reviewer_id": rid, "score": s}, ...]}}`.
        Read-only so we still open a transaction for the SET LOCAL
        timeout but no lock is taken.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"SET LOCAL statement_timeout = '{self._timeout_ms}ms'"
                )
                rows = await conn.fetch(_AGREEMENT_SQL, window_start, window_end)

        out: dict[str, dict[str, list[dict[str, int]]]] = {}
        for row in rows:
            case_id = row["case_id"]
            reviewer_id = row["reviewer_id"]
            by_dim = out.setdefault(case_id, {dim: [] for dim in RUBRIC_DIMENSIONS})
            for dim in RUBRIC_DIMENSIONS:
                by_dim[dim].append({"reviewer_id": reviewer_id, "score": int(row[dim])})
        return out
