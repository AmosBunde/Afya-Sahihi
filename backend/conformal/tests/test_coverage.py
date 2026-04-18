"""Tests for the rolling-coverage calculator."""

from __future__ import annotations

import pytest

from conformal.coverage import RollingCoverage, coverage_deviation


def test_rolling_empty_snapshot() -> None:
    rc = RollingCoverage(window_seconds=86400)
    snap = rc.snapshot("en:dosing")
    assert snap.n_samples == 0
    assert snap.empirical_coverage == 0.0
    assert snap.mean_set_size == 0.0


def test_rolling_coverage_simple() -> None:
    rc = RollingCoverage(window_seconds=86400)
    # 3 covered, 1 not-covered; mean set size 2.5
    rc.observe(stratum="en:dosing", covered=True, set_size=2, timestamp=1000.0)
    rc.observe(stratum="en:dosing", covered=True, set_size=3, timestamp=1001.0)
    rc.observe(stratum="en:dosing", covered=True, set_size=2, timestamp=1002.0)
    rc.observe(stratum="en:dosing", covered=False, set_size=3, timestamp=1003.0)

    snap = rc.snapshot("en:dosing", now=1010.0)
    assert snap.n_samples == 4
    assert snap.empirical_coverage == pytest.approx(0.75)
    assert snap.mean_set_size == pytest.approx(2.5)


def test_rolling_expires_old_events() -> None:
    rc = RollingCoverage(window_seconds=100)
    rc.observe(stratum="s", covered=True, set_size=1, timestamp=0.0)
    rc.observe(stratum="s", covered=False, set_size=1, timestamp=50.0)
    rc.observe(stratum="s", covered=True, set_size=1, timestamp=150.0)

    # Window 100s ending at 200; cutoff is t=100 so t=0 and t=50 expire.
    snap = rc.snapshot("s", now=200.0)
    assert snap.n_samples == 1
    assert snap.empirical_coverage == pytest.approx(1.0)


def test_rolling_independent_strata() -> None:
    rc = RollingCoverage(window_seconds=86400)
    rc.observe(stratum="en:dosing", covered=True, set_size=1, timestamp=1.0)
    rc.observe(stratum="sw:general", covered=False, set_size=1, timestamp=2.0)

    en = rc.snapshot("en:dosing", now=10.0)
    sw = rc.snapshot("sw:general", now=10.0)
    assert en.empirical_coverage == pytest.approx(1.0)
    assert sw.empirical_coverage == pytest.approx(0.0)


def test_rolling_capacity_bounded() -> None:
    rc = RollingCoverage(window_seconds=86400, max_samples_per_stratum=5)
    for i in range(10):
        rc.observe(stratum="s", covered=True, set_size=1, timestamp=float(i))
    snap = rc.snapshot("s", now=10.0)
    assert snap.n_samples == 5


def test_rolling_rejects_bad_window() -> None:
    with pytest.raises(ValueError):
        RollingCoverage(window_seconds=0)


def test_coverage_deviation_sign() -> None:
    assert coverage_deviation(0.93, 0.90) == pytest.approx(0.03)
    assert coverage_deviation(0.85, 0.90) == pytest.approx(-0.05)
