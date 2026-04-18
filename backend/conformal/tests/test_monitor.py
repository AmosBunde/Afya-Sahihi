"""Integration-style tests for the CoverageMonitor with a fake Metrics sink."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import pytest

from conformal.monitor import CoverageMonitor
from conformal.settings import ConformalSettings


@dataclass
class _FakeMetrics:
    """Captures every metric call for assertion."""

    coverage_target: float | None = None
    coverage_values: dict[str, float] = field(default_factory=dict)
    mean_set_sizes: dict[str, float] = field(default_factory=dict)
    set_size_observations: list[tuple[str, float]] = field(default_factory=list)
    drift_values: dict[tuple[str, str], float] = field(default_factory=dict)
    drift_detected_count: dict[str, int] = field(default_factory=dict)

    def set_coverage_target(self, value: float) -> None:
        self.coverage_target = value

    def set_coverage(self, *, stratum: str, value: float) -> None:
        self.coverage_values[stratum] = value

    def set_mean_set_size(self, *, stratum: str, value: float) -> None:
        self.mean_set_sizes[stratum] = value

    def observe_set_size(self, *, stratum: str, value: float) -> None:
        self.set_size_observations.append((stratum, value))

    def set_drift_mmd(self, *, stratum: str, score_type: str, value: float) -> None:
        self.drift_values[(stratum, score_type)] = value

    def inc_drift_detected(self, *, stratum: str) -> None:
        self.drift_detected_count[stratum] = self.drift_detected_count.get(stratum, 0) + 1


def _settings(**overrides: object) -> ConformalSettings:
    base: dict[str, object] = {
        "pg_host": "localhost",
        "pg_password": "x",
        "cp_alpha": 0.10,
        "calibration_set_min_size_per_stratum": 50,
    }
    base.update(overrides)
    return ConformalSettings(**base)  # type: ignore[arg-type]


def test_monitor_initial_target_published() -> None:
    metrics = _FakeMetrics()
    CoverageMonitor(settings=_settings(), metrics=metrics)
    # cp_alpha=0.10 → target 0.90
    assert metrics.coverage_target == pytest.approx(0.90)


def test_monitor_records_coverage_gauge() -> None:
    metrics = _FakeMetrics()
    monitor = CoverageMonitor(settings=_settings(), metrics=metrics)

    # 4 observations, 3 covered
    for covered in [True, True, False, True]:
        monitor.record(
            stratum="en:dosing",
            covered=covered,
            set_size=3,
            nonconformity_score=0.5,
            score_type="nll",
        )

    assert metrics.coverage_values["en:dosing"] == pytest.approx(0.75)
    assert metrics.mean_set_sizes["en:dosing"] == pytest.approx(3.0)


def test_monitor_alert_fires_on_coverage_deviation() -> None:
    metrics = _FakeMetrics()
    monitor = CoverageMonitor(settings=_settings(), metrics=metrics)

    # Simulate 200 observations at 80% coverage — 10pp below target 90%.
    alert: object = None
    for i in range(200):
        alert = monitor.record(
            stratum="en:dosing",
            covered=(i % 10) < 8,  # 80% covered
            set_size=3,
            nonconformity_score=0.5,
            score_type="nll",
        )

    # Last alert should be over threshold
    from conformal.monitor import AlertState

    assert isinstance(alert, AlertState)
    assert alert.over_threshold is True
    assert alert.coverage_deviation_pp < -0.05  # 80% - 90% = -10pp


def test_monitor_alert_not_fired_below_min_samples() -> None:
    metrics = _FakeMetrics()
    monitor = CoverageMonitor(settings=_settings(), metrics=metrics)

    # Only 5 observations at 0% coverage — deviation huge but n_samples tiny.
    alert = None
    for _ in range(5):
        alert = monitor.record(
            stratum="en:dosing",
            covered=False,
            set_size=3,
            nonconformity_score=0.5,
            score_type="nll",
        )

    from conformal.monitor import AlertState

    assert isinstance(alert, AlertState)
    assert alert.over_threshold is False


def test_monitor_drift_detected_on_shift() -> None:
    """Synthetic drift injection — the acceptance scenario.

    Feed 100 stable reference events, then 100 shifted events, and
    verify drift_detected_total increments.
    """
    metrics = _FakeMetrics()
    monitor = CoverageMonitor(settings=_settings(), metrics=metrics)

    rng = random.Random(1)
    # Reference window: scores around 0.5
    for _ in range(100):
        monitor.record(
            stratum="en:dosing",
            covered=True,
            set_size=3,
            nonconformity_score=rng.gauss(0.5, 0.1),
            score_type="nll",
        )
    # Current window: scores shifted to around 2.0
    for _ in range(100):
        monitor.record(
            stratum="en:dosing",
            covered=True,
            set_size=3,
            nonconformity_score=rng.gauss(2.0, 0.1),
            score_type="nll",
        )

    # Drift should have been flagged at least once.
    assert metrics.drift_detected_count.get("en:dosing", 0) > 0
    # And the MMD value gauge was set.
    assert ("en:dosing", "nll") in metrics.drift_values
    assert metrics.drift_values[("en:dosing", "nll")] > 0.01


def test_monitor_nonfinite_score_does_not_crash() -> None:
    metrics = _FakeMetrics()
    monitor = CoverageMonitor(settings=_settings(), metrics=metrics)
    monitor.record(
        stratum="x",
        covered=True,
        set_size=1,
        nonconformity_score=float("inf"),
        score_type="nll",
    )
    # No assertion — the test is that we don't raise.
