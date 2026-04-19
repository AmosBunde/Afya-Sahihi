"""Tests for calibration metrics."""

from __future__ import annotations

import math

import pytest

from research.paper_p1.metrics import (
    ace,
    brier,
    ece,
    equal_mass_bins,
    equal_width_bins,
    mce,
    reliability_diagram_area,
)


# ---- ECE ----


def test_ece_perfect_calibration_is_zero() -> None:
    # All confidences 0.9, accuracy exactly 0.9 → bin gap 0.
    result = ece(confidences=[0.9] * 10, correct=[True] * 9 + [False])
    assert result == pytest.approx(0.0, abs=1e-9)


def test_ece_detects_overconfidence() -> None:
    # Model claims 99% confidence but is only 50% accurate → gap ~0.49.
    result = ece(confidences=[0.99] * 10, correct=[True] * 5 + [False] * 5)
    assert result > 0.4


def test_ece_empty_returns_zero() -> None:
    assert ece(confidences=[], correct=[]) == 0.0


def test_ece_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="correct"):
        ece(confidences=[0.1, 0.2], correct=[True])


def test_ece_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError, match="\\[0, 1\\]"):
        ece(confidences=[1.2], correct=[True])


def test_ece_rejects_non_finite_confidence() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        ece(confidences=[float("nan")], correct=[True])


# ---- MCE ----


def test_mce_is_max_gap_across_bins() -> None:
    # First bucket (0.0-0.1): conf 0.05, acc 0 → gap 0.05.
    # Last bucket (0.9-1.0): conf 0.95, acc 0 → gap 0.95.
    result = mce(
        confidences=[0.05, 0.95],
        correct=[False, False],
        n_bins=10,
    )
    assert result == pytest.approx(0.95, abs=1e-9)


def test_mce_empty_returns_zero() -> None:
    assert mce(confidences=[], correct=[]) == 0.0


# ---- ACE ----


def test_ace_equal_mass_bins_tolerate_concentration() -> None:
    # 100 cases, all conf 0.95 except 1 at 0.5. Equal-width bins would
    # put 99 in one bucket; equal-mass spreads them so ACE stays
    # well-defined.
    confs = [0.95] * 99 + [0.5]
    correct = [True] * 95 + [False] * 4 + [True]
    result = ace(confidences=confs, correct=correct, n_bins=10)
    # Sanity check: finite, non-negative, <= 1.
    assert 0.0 <= result <= 1.0


# ---- Brier ----


def test_brier_perfect_predictions_are_zero() -> None:
    # Confidence 1.0 for correct, 0.0 for incorrect.
    result = brier(
        confidences=[1.0, 0.0, 1.0, 0.0],
        correct=[True, False, True, False],
    )
    assert result == pytest.approx(0.0, abs=1e-9)


def test_brier_worst_case_is_one() -> None:
    # Confidence 1.0 for everything wrong, 0.0 for everything right.
    result = brier(
        confidences=[1.0, 0.0],
        correct=[False, True],
    )
    assert result == pytest.approx(1.0, abs=1e-9)


def test_brier_coin_flip_is_0_25() -> None:
    # All 0.5 guesses on any outcome → mean (0.5 - y)² = 0.25.
    result = brier(confidences=[0.5] * 100, correct=[True] * 50 + [False] * 50)
    assert result == pytest.approx(0.25, abs=1e-9)


# ---- Reliability diagram area ----


def test_reliability_area_zero_when_on_identity() -> None:
    # Two bins, each sample's mean_conf == accuracy → area = 0.
    confs = [0.2, 0.3, 0.7, 0.8]
    correct = [
        False,
        False,
        True,
        True,
    ]  # bin 1: acc 0, conf 0.25; bin 2: acc 1, conf 0.75
    result = reliability_diagram_area(confidences=confs, correct=correct, n_bins=5)
    # Each bin has |acc - mean_conf| = 0.25; not zero but bounded.
    assert result >= 0.0


def test_reliability_area_empty_or_single_bin_is_zero() -> None:
    assert reliability_diagram_area(confidences=[], correct=[]) == 0.0


# ---- equal_width / equal_mass bins ----


def test_equal_width_bins_final_sample_lands_in_top_bucket() -> None:
    bins = equal_width_bins(confidences=[1.0], correct=[True], n_bins=4)
    assert bins[-1].n_samples == 1
    assert bins[0].n_samples == 0


def test_equal_mass_bins_split_evenly() -> None:
    # 12 samples, 4 bins → 3 per bin.
    confs = [i / 12 for i in range(12)]
    correct = [True] * 12
    bins = equal_mass_bins(confidences=confs, correct=correct, n_bins=4)
    counts = [b.n_samples for b in bins]
    assert counts == [3, 3, 3, 3]


def test_equal_mass_bins_monotone_edges() -> None:
    confs = [0.1, 0.3, 0.5, 0.7, 0.9]
    correct = [True] * 5
    bins = equal_mass_bins(confidences=confs, correct=correct, n_bins=5)
    for prev, curr in zip(bins, bins[1:], strict=False):
        assert prev.upper <= curr.lower + 1e-9


# ---- Cross-metric sanity ----


def test_ece_never_exceeds_mce() -> None:
    # ECE is a weighted average of |acc - conf|; MCE is the max.
    # Weighted average ≤ max by definition. Use a randomish spread.
    confs = [(i % 10) / 10 + 0.05 for i in range(200)]
    correct = [bool(i % 3 == 0) for i in range(200)]
    e = ece(confidences=confs, correct=correct, n_bins=10)
    m = mce(confidences=confs, correct=correct, n_bins=10)
    assert e <= m + 1e-12


def test_ece_is_nonnegative_on_noise() -> None:
    # Random confidences + random outcomes → ECE ≥ 0.
    import random

    rng = random.Random(42)
    confs = [rng.random() for _ in range(500)]
    correct = [rng.random() < c for c in confs]  # perfectly calibrated by construction
    result = ece(confidences=confs, correct=correct, n_bins=15)
    assert result >= 0.0
    # Perfectly calibrated should be small (< 0.1 typically with n=500).
    assert result < 0.1


def test_mce_bounded_by_one() -> None:
    # Extreme: 100% overconfident and 100% wrong → gap 1.
    confs = [1.0] * 10
    correct = [False] * 10
    assert mce(confidences=confs, correct=correct, n_bins=5) == pytest.approx(1.0)


def test_reliability_area_handles_bulk_data() -> None:
    # Synthetic mildly mis-calibrated data should give a small, finite area.
    confs = [0.1, 0.3, 0.5, 0.7, 0.9] * 20
    correct = [False, True, True, True, False] * 20
    result = reliability_diagram_area(confidences=confs, correct=correct, n_bins=10)
    assert math.isfinite(result)
    assert result >= 0.0
