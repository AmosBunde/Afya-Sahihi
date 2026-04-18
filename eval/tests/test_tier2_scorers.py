"""Tests for Tier 2 scorers. Pure Python."""

from __future__ import annotations

import math

import pytest

from eval.tier2.scorers import (
    Tier2Thresholds,
    evaluate_tier2,
    expected_calibration_error,
    marginal_coverage,
    set_size_change_pct,
    set_size_mean,
    topic_coherence,
)


# ---- ECE ----


def test_ece_perfect_calibration_is_zero() -> None:
    # Confidence 0.9, accuracy 0.9 — all in same bin.
    result = expected_calibration_error(
        confidences=[0.9] * 10,
        correct=[True] * 9 + [False],
    )
    # Bin confidence mean = 0.9; bin accuracy = 0.9. Gap = 0.
    assert result.ece == pytest.approx(0.0, abs=1e-9)


def test_ece_detects_overconfidence() -> None:
    # Model claims 100% confidence but is only 50% accurate.
    result = expected_calibration_error(
        confidences=[0.99] * 10,
        correct=[True] * 5 + [False] * 5,
    )
    # Bin conf ~0.99, acc 0.5 → gap ~0.49
    assert result.ece > 0.4


def test_ece_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        expected_calibration_error(confidences=[0.1, 0.2], correct=[True])


def test_ece_empty_returns_zero() -> None:
    result = expected_calibration_error(confidences=[], correct=[])
    assert result.ece == 0.0


def test_ece_rejects_bad_n_bins() -> None:
    with pytest.raises(ValueError):
        expected_calibration_error(confidences=[0.5], correct=[True], n_bins=0)


# ---- Marginal coverage ----


def test_coverage_all_covered() -> None:
    assert marginal_coverage(
        prediction_sets=[["a", "b"], ["c"], ["x", "y", "z"]],
        ground_truths=["a", "c", "y"],
    ) == pytest.approx(1.0)


def test_coverage_none_covered() -> None:
    assert marginal_coverage(
        prediction_sets=[["a"], ["b"]],
        ground_truths=["x", "y"],
    ) == pytest.approx(0.0)


def test_coverage_partial() -> None:
    assert marginal_coverage(
        prediction_sets=[["a"], ["b"], ["c"], ["d"]],
        ground_truths=["a", "b", "x", "y"],
    ) == pytest.approx(0.5)


def test_coverage_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        marginal_coverage(prediction_sets=[["a"]], ground_truths=["a", "b"])


# ---- Set size ----


def test_set_size_mean_simple() -> None:
    assert set_size_mean([["a"], ["b", "c"], ["d", "e", "f"]]) == pytest.approx(2.0)


def test_set_size_mean_empty() -> None:
    assert set_size_mean([]) == 0.0


def test_set_size_change_pct_no_change() -> None:
    assert set_size_change_pct(3.0, 3.0) == pytest.approx(0.0)


def test_set_size_change_pct_increase() -> None:
    assert set_size_change_pct(3.6, 3.0) == pytest.approx(20.0)


def test_set_size_change_pct_decrease() -> None:
    assert set_size_change_pct(2.7, 3.0) == pytest.approx(-10.0)


def test_set_size_change_pct_zero_baseline() -> None:
    assert set_size_change_pct(1.0, 0.0) == math.inf
    assert set_size_change_pct(0.0, 0.0) == 0.0


# ---- Topic coherence ----


def test_topic_coherence_above_threshold() -> None:
    # 3 of 4 scores above 0.65
    assert topic_coherence(topic_scores=[0.7, 0.8, 0.5, 0.9]) == pytest.approx(0.75)


def test_topic_coherence_custom_threshold() -> None:
    assert topic_coherence(
        topic_scores=[0.5, 0.6, 0.7, 0.8], threshold=0.7
    ) == pytest.approx(0.5)


def test_topic_coherence_filters_nonfinite() -> None:
    # Non-finite values counted as below threshold (they're excluded
    # via math.isfinite guard, but the denominator is still all items).
    result = topic_coherence(topic_scores=[float("nan"), 0.9, float("inf")])
    # Only 0.9 is finite and above threshold; denom is 3.
    assert result == pytest.approx(1 / 3)


# ---- Verdict combiner ----


def _pass_thresholds() -> Tier2Thresholds:
    return Tier2Thresholds()


def test_verdict_all_green() -> None:
    v = evaluate_tier2(
        ece=0.05,
        coverage=0.91,
        coverage_target=0.90,
        set_size_mean_value=3.5,
        set_size_baseline=3.5,
        topic_coherence_value=0.85,
        thresholds=_pass_thresholds(),
    )
    assert v.passed is True
    assert v.breaches == ()


def test_verdict_ece_breach() -> None:
    v = evaluate_tier2(
        ece=0.10,  # > 0.08
        coverage=0.91,
        coverage_target=0.90,
        set_size_mean_value=3.5,
        set_size_baseline=3.5,
        topic_coherence_value=0.85,
        thresholds=_pass_thresholds(),
    )
    assert v.passed is False
    assert any("ece" in b for b in v.breaches)


def test_verdict_coverage_breach() -> None:
    v = evaluate_tier2(
        ece=0.05,
        coverage=0.85,  # deviation 0.05 > 0.03
        coverage_target=0.90,
        set_size_mean_value=3.5,
        set_size_baseline=3.5,
        topic_coherence_value=0.85,
        thresholds=_pass_thresholds(),
    )
    assert v.passed is False
    assert any("coverage_deviation" in b for b in v.breaches)


def test_verdict_set_size_breach() -> None:
    v = evaluate_tier2(
        ece=0.05,
        coverage=0.91,
        coverage_target=0.90,
        set_size_mean_value=4.5,  # 28.6% increase
        set_size_baseline=3.5,
        topic_coherence_value=0.85,
        thresholds=_pass_thresholds(),
    )
    assert v.passed is False
    assert any("set_size_increase" in b for b in v.breaches)


def test_verdict_topic_coherence_breach() -> None:
    v = evaluate_tier2(
        ece=0.05,
        coverage=0.91,
        coverage_target=0.90,
        set_size_mean_value=3.5,
        set_size_baseline=3.5,
        topic_coherence_value=0.70,  # < 0.80
        thresholds=_pass_thresholds(),
    )
    assert v.passed is False
    assert any("topic_coherence" in b for b in v.breaches)


def test_verdict_multiple_breaches() -> None:
    v = evaluate_tier2(
        ece=0.10,
        coverage=0.80,
        coverage_target=0.90,
        set_size_mean_value=5.0,
        set_size_baseline=3.5,
        topic_coherence_value=0.50,
        thresholds=_pass_thresholds(),
    )
    assert v.passed is False
    assert len(v.breaches) == 4
