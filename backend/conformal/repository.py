"""asyncpg reader for the calibration_set table.

Calibration scores are written by the labeling pipeline (issue #29)
and the active learning loop (issue #37). This repository is read-only
from the conformal service's perspective — it fetches scores per
(score_type, stratum) tuple to compute q_hat.

SET LOCAL statement_timeout on every call per SKILL.md §7 and the
check_asyncpg_timeouts hook.
"""

from __future__ import annotations

from collections.abc import Sequence

import asyncpg

_CONFORMAL_TIMEOUT = "5s"


class CalibrationRepository:
    """Read scores from calibration_set for a given (score_type, stratum)."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def fetch_scores(
        self,
        *,
        score_type: str,
        stratum: str,
        max_size: int,
    ) -> list[float]:
        """Return up to `max_size` most-recent calibration scores.

        Ordered by `included_at DESC` so the freshest samples dominate
        the quantile — important under covariate shift, where stale
        scores drift away from the current population.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(f"SET LOCAL statement_timeout = '{_CONFORMAL_TIMEOUT}'")
            rows = await conn.fetch(
                """
                SELECT nonconformity_score
                FROM calibration_set
                WHERE score_type = $1
                  AND stratum = $2
                ORDER BY included_at DESC
                LIMIT $3
                """,
                score_type,
                stratum,
                max_size,
            )
        return [float(row["nonconformity_score"]) for row in rows]

    async def count_per_stratum(
        self,
        *,
        score_type: str,
    ) -> dict[str, int]:
        """Count calibration samples per stratum; used by the minimum-size
        guard that refuses to publish a q_hat for an undersized stratum.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(f"SET LOCAL statement_timeout = '{_CONFORMAL_TIMEOUT}'")
            rows = await conn.fetch(
                """
                SELECT stratum, count(*) AS n
                FROM calibration_set
                WHERE score_type = $1
                GROUP BY stratum
                """,
                score_type,
            )
        return {str(row["stratum"]): int(row["n"]) for row in rows}

    async def insert_scores(
        self,
        *,
        entries: Sequence[tuple[int | None, float, str, str, str | None]],
    ) -> int:
        """Append to calibration_set.

        `entries` is a sequence of (query_audit_id, score, score_type,
        stratum, ground_truth_label) tuples. Used by the active learning
        loop to grow the calibration set over time. Returns the number
        of rows inserted.
        """
        if not entries:
            return 0
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(f"SET LOCAL statement_timeout = '{_CONFORMAL_TIMEOUT}'")
            await conn.executemany(
                """
                INSERT INTO calibration_set (
                    query_audit_id, nonconformity_score, score_type,
                    stratum, ground_truth_label
                ) VALUES ($1, $2, $3, $4, $5)
                """,
                entries,
            )
            return len(entries)
