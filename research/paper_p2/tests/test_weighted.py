"""Tests for weighted CP."""

from __future__ import annotations

import math

import pytest

from research.paper_p2.weighted import (
    likelihood_ratio_from_logits,
    weighted_quantile,
)


def test_weighted_quantile_equals_unweighted_under_equal_weights() -> None:
    scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    weights = [1.0] * 10
    result = weighted_quantile(scores=scores, weights=weights, alpha=0.1)
    # With uniform weights and α=0.1, the CDF crosses 0.9 at the 9th
    # sorted score (0.9).
    assert result.q_hat == pytest.approx(0.9)
    # ESS = 1 / Σ(1/10)² = 10. Full ESS when weights are uniform.
    assert result.effective_sample_size == pytest.approx(10.0, abs=1e-9)


def test_weighted_quantile_concentrates_on_higher_weights() -> None:
    # Weight the extremes 10x higher; the quantile shifts accordingly.
    scores = [0.1, 0.3, 0.5, 0.7, 0.9]
    weights = [10.0, 1.0, 1.0, 1.0, 10.0]
    result = weighted_quantile(scores=scores, weights=weights, alpha=0.1)
    # Heavy weight on 0.9 pulls the quantile toward the upper tail.
    assert result.q_hat == pytest.approx(0.9)


def test_weighted_quantile_ess_drops_with_weight_skew() -> None:
    # Highly skewed weights → low ESS.
    scores = [0.1, 0.2, 0.3, 0.4, 0.5]
    equal_weights = [1.0] * 5
    skewed_weights = [100.0, 1.0, 1.0, 1.0, 1.0]
    r_equal = weighted_quantile(scores=scores, weights=equal_weights, alpha=0.1)
    r_skewed = weighted_quantile(scores=scores, weights=skewed_weights, alpha=0.1)
    assert r_skewed.effective_sample_size < r_equal.effective_sample_size


def test_weighted_quantile_empty_returns_inf() -> None:
    result = weighted_quantile(scores=[], weights=[], alpha=0.1)
    assert math.isinf(result.q_hat)
    assert result.n_samples == 0


def test_weighted_quantile_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="weights"):
        weighted_quantile(scores=[0.1, 0.2], weights=[1.0], alpha=0.1)


def test_weighted_quantile_rejects_bad_alpha() -> None:
    with pytest.raises(ValueError, match="alpha"):
        weighted_quantile(scores=[0.1], weights=[1.0], alpha=0.0)
    with pytest.raises(ValueError, match="alpha"):
        weighted_quantile(scores=[0.1], weights=[1.0], alpha=1.0)


def test_weighted_quantile_rejects_negative_weights() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        weighted_quantile(scores=[0.1, 0.2], weights=[1.0, -0.5], alpha=0.1)


def test_weighted_quantile_all_zero_weights_returns_inf() -> None:
    result = weighted_quantile(
        scores=[0.1, 0.2, 0.3], weights=[0.0, 0.0, 0.0], alpha=0.1
    )
    assert math.isinf(result.q_hat)


# ---- likelihood_ratio_from_logits ----


def test_likelihood_ratio_uniform_logits_gives_unit_weight() -> None:
    # source and target logits identical → z = 0 → weight = 1.
    weights = likelihood_ratio_from_logits(
        source_logits=[0.0, 0.5, -0.5],
        target_logits=[0.0, 0.5, -0.5],
    )
    assert all(w == pytest.approx(1.0, abs=1e-9) for w in weights)


def test_likelihood_ratio_handles_positive_drift() -> None:
    weights = likelihood_ratio_from_logits(
        source_logits=[0.0, 0.0, 0.0],
        target_logits=[1.0, 2.0, 3.0],
    )
    # All weights > 1; monotonic in target - source.
    assert weights[0] < weights[1] < weights[2]


def test_likelihood_ratio_clips_extreme_drift() -> None:
    # Raw z = 100 would blow up exp. Clip at ±20 → exp(20) ≈ 5e8.
    weights = likelihood_ratio_from_logits(
        source_logits=[0.0],
        target_logits=[100.0],
    )
    assert weights[0] == pytest.approx(math.exp(20.0))


def test_likelihood_ratio_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="length"):
        likelihood_ratio_from_logits(source_logits=[0.0, 1.0], target_logits=[1.0])
