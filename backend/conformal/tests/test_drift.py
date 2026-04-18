"""Tests for the MMD drift detector."""

from __future__ import annotations

import random

import pytest

from conformal.drift import compute_mmd_squared, detect_drift


def test_mmd_rejects_tiny_samples() -> None:
    with pytest.raises(ValueError):
        compute_mmd_squared([1.0], [1.0, 2.0, 3.0])


def test_mmd_near_zero_on_identical_samples() -> None:
    ref = [0.1, 0.2, 0.3, 0.4, 0.5, 0.1, 0.2, 0.3, 0.4, 0.5]
    cur = list(ref)
    result = compute_mmd_squared(ref, cur)
    # Identical samples → MMD² rounds to 0 within numerical noise.
    assert result.mmd_squared < 1e-9


def test_mmd_positive_on_shifted_distribution() -> None:
    rng = random.Random(42)
    ref = [rng.gauss(0.0, 1.0) for _ in range(100)]
    # Shift by 2σ
    cur = [rng.gauss(2.0, 1.0) for _ in range(100)]
    result = compute_mmd_squared(ref, cur)
    assert result.mmd_squared > 0.05, f"MMD² = {result.mmd_squared} too small for a 2σ shift"


def test_mmd_small_on_same_distribution() -> None:
    rng = random.Random(100)
    ref = [rng.gauss(0.0, 1.0) for _ in range(100)]
    cur = [rng.gauss(0.0, 1.0) for _ in range(100)]
    result = compute_mmd_squared(ref, cur)
    # Same distribution → MMD² should be small, well below typical
    # drift thresholds. 0.05 is generous for n=100.
    assert result.mmd_squared < 0.05


def test_detect_drift_flags_when_above_threshold() -> None:
    rng = random.Random(7)
    ref = [rng.gauss(0.0, 1.0) for _ in range(100)]
    cur = [rng.gauss(3.0, 1.0) for _ in range(100)]
    result = detect_drift(reference=ref, current=cur, threshold=0.01)
    assert result.is_drifted is True


def test_detect_drift_not_flagged_below_threshold() -> None:
    rng = random.Random(7)
    ref = [rng.gauss(0.0, 1.0) for _ in range(100)]
    cur = [rng.gauss(0.0, 1.0) for _ in range(100)]
    # High threshold → even real differences don't trigger.
    result = detect_drift(reference=ref, current=cur, threshold=1.0)
    assert result.is_drifted is False


def test_mmd_filters_nonfinite() -> None:
    ref = [0.1, 0.2, float("nan"), 0.3, 0.4]
    cur = [0.5, 0.6, float("inf"), 0.7, 0.8]
    # Both sides have finite count >= 2 after filtering; should compute.
    result = compute_mmd_squared(ref, cur)
    assert result.n_reference == 4
    assert result.n_current == 4


def test_mmd_degenerate_zero_bandwidth() -> None:
    # All-identical inputs → median pairwise distance is 0 → degenerate
    # path returns MMD²=0, not NaN or crash.
    result = compute_mmd_squared([1.0, 1.0, 1.0], [1.0, 1.0, 1.0])
    assert result.mmd_squared == 0.0
    assert result.bandwidth == 0.0
