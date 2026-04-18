"""Tests for the daily Fleiss kappa job."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import pytest

from labeling.daily_kappa import run_daily_kappa
from labeling.rubric import RUBRIC_DIMENSIONS


class FakeRepository:
    def __init__(self, payload: dict[str, dict[str, list[dict[str, int]]]]):
        self._payload = payload
        self.last_window: tuple[Any, Any] | None = None

    async def load_agreement_ratings(
        self, *, window_start: Any, window_end: Any
    ) -> dict[str, dict[str, list[dict[str, int]]]]:
        self.last_window = (window_start, window_end)
        return self._payload


def _by_dim(
    scores_per_reviewer: list[dict[str, int]],
) -> dict[str, list[dict[str, int]]]:
    """Expand one reviewer-set-per-case into per-dimension lists."""
    out: dict[str, list[dict[str, int]]] = {dim: [] for dim in RUBRIC_DIMENSIONS}
    for reviewer_scores in scores_per_reviewer:
        for dim in RUBRIC_DIMENSIONS:
            out[dim].append(
                {
                    "reviewer_id": reviewer_scores["reviewer_id"],
                    "score": reviewer_scores[dim],
                }
            )
    return out


async def test_run_daily_kappa_alerts_on_low_agreement() -> None:
    # Two cases, 2 reviewers each. Reviewers disagree wildly on accuracy
    # across both cases so agreement < threshold.
    payload = {
        "c-1": _by_dim(
            [
                {
                    "reviewer_id": "u-1",
                    "accuracy": 1,
                    "safety": 3,
                    "guideline_alignment": 3,
                    "local_appropriateness": 3,
                    "clarity": 3,
                },
                {
                    "reviewer_id": "u-2",
                    "accuracy": 5,
                    "safety": 3,
                    "guideline_alignment": 3,
                    "local_appropriateness": 3,
                    "clarity": 3,
                },
            ]
        ),
        "c-2": _by_dim(
            [
                {
                    "reviewer_id": "u-1",
                    "accuracy": 2,
                    "safety": 3,
                    "guideline_alignment": 3,
                    "local_appropriateness": 3,
                    "clarity": 3,
                },
                {
                    "reviewer_id": "u-3",
                    "accuracy": 4,
                    "safety": 3,
                    "guideline_alignment": 3,
                    "local_appropriateness": 3,
                    "clarity": 3,
                },
            ]
        ),
    }
    repo: Any = FakeRepository(payload)
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
    report = await run_daily_kappa(repository=repo, now=now, alert_threshold=0.7)
    assert report.dimension_n_items["accuracy"] == 2
    assert any("accuracy" in alert for alert in report.alerts)
    # Other dims have all 3s across both raters → degenerate (nan).
    assert math.isnan(report.dimension_kappa["safety"])
    # Window spans exactly 24h ending at `now`.
    assert (report.window_end - report.window_start).total_seconds() == 86400


async def test_run_daily_kappa_skips_single_rated_cases() -> None:
    payload = {
        "c-1": _by_dim(
            [
                {
                    "reviewer_id": "u-1",
                    "accuracy": 5,
                    "safety": 5,
                    "guideline_alignment": 5,
                    "local_appropriateness": 5,
                    "clarity": 5,
                },
            ]
        ),
    }
    repo: Any = FakeRepository(payload)
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
    report = await run_daily_kappa(repository=repo, now=now, alert_threshold=0.7)
    # No dual-rated cases → every dim is nan, no alerts.
    for dim in RUBRIC_DIMENSIONS:
        assert math.isnan(report.dimension_kappa[dim])
        assert report.dimension_n_items[dim] == 0
    assert report.alerts == ()


async def test_run_daily_kappa_no_alert_when_kappa_above_threshold() -> None:
    # 4 cases, 2 reviewers; all raters agree on every case for accuracy.
    # Other dims mixed — only accuracy should have kappa == 1.
    payload = {}
    for i, acc in enumerate((1, 2, 3, 4)):
        payload[f"c-{i}"] = _by_dim(
            [
                {
                    "reviewer_id": "u-1",
                    "accuracy": acc,
                    "safety": 3,
                    "guideline_alignment": 3,
                    "local_appropriateness": 3,
                    "clarity": 3,
                },
                {
                    "reviewer_id": "u-2",
                    "accuracy": acc,
                    "safety": 3,
                    "guideline_alignment": 3,
                    "local_appropriateness": 3,
                    "clarity": 3,
                },
            ]
        )
    repo: Any = FakeRepository(payload)
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
    report = await run_daily_kappa(repository=repo, now=now, alert_threshold=0.7)
    # Accuracy: perfect agreement, non-degenerate distribution → kappa == 1.
    assert report.dimension_kappa["accuracy"] == pytest.approx(1.0)
    assert "accuracy" not in " ".join(report.alerts)


async def test_run_daily_kappa_rejects_bad_threshold() -> None:
    repo: Any = FakeRepository({})
    with pytest.raises(ValueError, match="threshold"):
        await run_daily_kappa(
            repository=repo,
            now=datetime(2026, 4, 18, tzinfo=timezone.utc),
            alert_threshold=2.0,
        )
