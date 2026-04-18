"""Daily Fleiss kappa job entrypoint.

Reads the previous 24h of grades from the `grades` table, computes
Fleiss kappa per rubric dimension over dual-rated cases, emits a
Prometheus metric, and alerts when any dimension drops below
`kappa_alert_threshold`.

Run as a k3s CronJob at 03:00 Africa/Nairobi (after the labeling UI is
quiet). Idempotent: re-running the same 24h window produces the same
kappa values.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from labeling.kappa import build_counts_matrix, fleiss_kappa
from labeling.repository import GradeRepository
from labeling.rubric import RUBRIC_DIMENSIONS, SCALE_MAX, SCALE_MIN

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KappaReport:
    """Per-dimension kappa with metadata for Slack / Prometheus."""

    window_start: datetime
    window_end: datetime
    dimension_kappa: dict[str, float]
    dimension_n_items: dict[str, int]
    alerts: tuple[str, ...]


_N_CATEGORIES = SCALE_MAX - SCALE_MIN + 1


async def run_daily_kappa(
    *,
    repository: GradeRepository,
    now: datetime,
    alert_threshold: float,
    min_raters_per_item: int = 2,
) -> KappaReport:
    """Compute kappa for the 24h window ending at `now`.

    Cases with fewer than `min_raters_per_item` raters are dropped (kappa
    requires ≥2 raters per item). If *all* cases are single-rated for a
    dimension, kappa is reported as nan and no alert fires — "not enough
    data" is not the same as "poor agreement."
    """
    if alert_threshold < -1.0 or alert_threshold > 1.0:
        raise ValueError("alert_threshold must be in [-1, 1]")

    window_end = now.astimezone(timezone.utc)
    window_start = window_end - timedelta(days=1)

    ratings_by_case = await repository.load_agreement_ratings(
        window_start=window_start,
        window_end=window_end,
    )

    dimension_kappa: dict[str, float] = {}
    dimension_n: dict[str, int] = {}
    alerts: list[str] = []

    for dim in RUBRIC_DIMENSIONS:
        per_item_labels: list[list[int]] = []
        for _case_id, by_dim in ratings_by_case.items():
            ratings = by_dim.get(dim, [])
            if len(ratings) < min_raters_per_item:
                continue
            labels = [r["score"] - SCALE_MIN for r in ratings]
            per_item_labels.append(labels)

        dimension_n[dim] = len(per_item_labels)
        if not per_item_labels:
            dimension_kappa[dim] = float("nan")
            continue

        # Fleiss requires equal rater count per item. Truncate all items
        # to the minimum rater count so we can still report when some
        # cases had 2 reviewers and others had 3.
        min_raters = min(len(row) for row in per_item_labels)
        truncated = [row[:min_raters] for row in per_item_labels]

        counts = build_counts_matrix(
            ratings_per_item=truncated,
            n_categories=_N_CATEGORIES,
        )
        result = fleiss_kappa(item_rater_category_counts=counts)
        dimension_kappa[dim] = result.kappa

        if result.kappa < alert_threshold and not _is_nan(result.kappa):
            alerts.append(
                f"{dim}:{result.kappa:.3f}<{alert_threshold:.2f}"
                f" (n_items={len(truncated)})"
            )

    report = KappaReport(
        window_start=window_start,
        window_end=window_end,
        dimension_kappa=dimension_kappa,
        dimension_n_items=dimension_n,
        alerts=tuple(alerts),
    )
    logger.info(
        "kappa report computed",
        extra={
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "dimension_kappa": dimension_kappa,
            "dimension_n_items": dimension_n,
            "n_alerts": len(alerts),
        },
    )
    return report


def _is_nan(x: float) -> bool:
    return x != x


async def _main() -> int:  # pragma: no cover - thin integration shim
    import os

    import asyncpg  # type: ignore[import-not-found]

    from labeling.settings import LabelingSettings

    settings = LabelingSettings()
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
        repo = GradeRepository(
            pool=pool,
            statement_timeout_ms=settings.pg_statement_timeout_ms,
        )
        report = await run_daily_kappa(
            repository=repo,
            now=datetime.now(timezone.utc),
            alert_threshold=settings.kappa_alert_threshold,
        )
        if report.alerts:
            for alert in report.alerts:
                logger.warning("kappa alert", extra={"alert": alert})
            return 1 if os.environ.get("KAPPA_FAIL_ON_ALERT") == "1" else 0
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(asyncio.run(_main()))
