"""Coverage + drift monitor service.

Orchestrates: consume labeled events → update rolling coverage →
detect score-distribution drift → emit Prometheus metrics → flag
alerts when thresholds cross.

The monitor is a plain Python class with async `observe_*` methods
that the orchestrator (or a background task) calls as each labeled
observation arrives. It holds no database — reference/current windows
for drift are materialized in memory from the same event stream.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from conformal.coverage import RollingCoverage, coverage_deviation
from conformal.drift import detect_drift
from conformal.metrics import Metrics
from conformal.settings import ConformalSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AlertState:
    """Snapshot used by Grafana/Alertmanager joins."""

    stratum: str
    coverage_empirical: float
    coverage_deviation_pp: float
    over_threshold: bool
    n_samples: int


class CoverageMonitor:
    """Ingest labeled events, emit metrics, surface alert states."""

    def __init__(
        self,
        *,
        settings: ConformalSettings,
        metrics: Metrics,
        coverage: RollingCoverage | None = None,
    ) -> None:
        self._settings = settings
        self._metrics = metrics
        self._coverage = coverage or RollingCoverage(
            window_seconds=60 * 60 * 24,  # 24h per env
        )
        # Reference / current buffers for MMD drift detection, per
        # (stratum, score_type). The reference is the concatenated
        # first N scores observed in the stratum; current is the most
        # recent N. Simpler than maintaining two rolling windows.
        self._reference_scores: dict[tuple[str, str], list[float]] = {}
        self._current_scores: dict[tuple[str, str], list[float]] = {}
        self._drift_window_size = max(settings.calibration_set_min_size_per_stratum, 100)

        target = 1.0 - settings.cp_alpha
        # Initial metric write so Grafana dashboards have a value
        # even before traffic arrives.
        if hasattr(metrics, "set_coverage_target"):
            metrics.set_coverage_target(target)  # type: ignore[attr-defined]

    def record(
        self,
        *,
        stratum: str,
        covered: bool,
        set_size: int,
        nonconformity_score: float,
        score_type: str,
        timestamp: float | None = None,
    ) -> AlertState:
        """Record one labeled observation and refresh metrics.

        Returns the current `AlertState` for the stratum so the caller
        can log it or forward to Alertmanager.
        """
        self._coverage.observe(
            stratum=stratum,
            covered=covered,
            set_size=set_size,
            timestamp=timestamp,
        )
        self._metrics.observe_set_size(stratum=stratum, value=float(set_size))

        # Update drift buffers
        key = (stratum, score_type)
        if math_finite_guard(nonconformity_score):
            ref = self._reference_scores.setdefault(key, [])
            cur = self._current_scores.setdefault(key, [])
            if len(ref) < self._drift_window_size:
                ref.append(nonconformity_score)
            cur.append(nonconformity_score)
            if len(cur) > self._drift_window_size:
                # Keep only the most-recent window.
                del cur[: len(cur) - self._drift_window_size]

        snap = self._coverage.snapshot(stratum, now=timestamp)
        self._metrics.set_coverage(stratum=stratum, value=snap.empirical_coverage)
        self._metrics.set_mean_set_size(stratum=stratum, value=snap.mean_set_size)

        # Drift: only compute when both windows are full.
        if (
            len(self._reference_scores.get(key, [])) >= self._drift_window_size
            and len(self._current_scores.get(key, [])) >= self._drift_window_size
        ):
            try:
                drift = detect_drift(
                    reference=self._reference_scores[key],
                    current=self._current_scores[key],
                    threshold=0.01,  # TODO: wire to settings.drift_threshold
                )
                self._metrics.set_drift_mmd(
                    stratum=stratum, score_type=score_type, value=drift.mmd_squared
                )
                if drift.is_drifted:
                    self._metrics.inc_drift_detected(stratum=stratum)
                    logger.warning(
                        "drift detected",
                        extra={
                            "stratum": stratum,
                            "score_type": score_type,
                            "mmd_squared": drift.mmd_squared,
                            "threshold": 0.01,
                        },
                    )
            except ValueError:
                pass  # insufficient samples; metric stays stale

        target = 1.0 - self._settings.cp_alpha
        deviation = coverage_deviation(snap.empirical_coverage, target)
        threshold_pp = 0.05  # TODO: wire to settings if env knob added
        over_threshold = (
            snap.n_samples >= 200  # env COVERAGE_ALERT_MIN_SAMPLES
            and abs(deviation) > threshold_pp
        )
        return AlertState(
            stratum=stratum,
            coverage_empirical=snap.empirical_coverage,
            coverage_deviation_pp=deviation,
            over_threshold=over_threshold,
            n_samples=snap.n_samples,
        )


def math_finite_guard(x: float) -> bool:
    """Inline import-free isfinite check — None/NaN/inf all return False."""
    try:
        return x == x and x not in (float("inf"), float("-inf"))
    except TypeError:
        return False
