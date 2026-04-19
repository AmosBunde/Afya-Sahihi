"""Tests for posterior effect-size estimation."""

from __future__ import annotations

import math

import pytest

from active_learning.effect_size import _inv_normal_cdf, _t_cdf, effect_size


def test_inv_normal_cdf_standard_quantiles() -> None:
    # Reference: standard normal quantiles.
    assert _inv_normal_cdf(0.5) == pytest.approx(0.0, abs=1e-6)
    assert _inv_normal_cdf(0.975) == pytest.approx(1.959964, abs=1e-3)
    assert _inv_normal_cdf(0.025) == pytest.approx(-1.959964, abs=1e-3)


def test_inv_normal_cdf_rejects_boundary() -> None:
    with pytest.raises(ValueError):
        _inv_normal_cdf(0.0)
    with pytest.raises(ValueError):
        _inv_normal_cdf(1.0)


def test_t_cdf_symmetry_at_zero() -> None:
    # P(T <= 0) = 0.5 for any df.
    assert _t_cdf(0.0, df=5) == pytest.approx(0.5, abs=1e-6)
    assert _t_cdf(0.0, df=100) == pytest.approx(0.5, abs=1e-6)


def test_t_cdf_large_df_converges_to_normal() -> None:
    # With df=1000, t-CDF at 1.96 should be close to Φ(1.96) ≈ 0.975.
    assert _t_cdf(1.96, df=1000) == pytest.approx(0.975, abs=1e-3)


def test_effect_size_no_data() -> None:
    result = effect_size(treatment_deltas=[], control_deltas=[])
    assert result.n_treatment == 0
    assert result.n_control == 0
    assert result.p_benefit == 0.5


def test_effect_size_small_sample_returns_placeholder_hdi() -> None:
    # n < 3 → not enough data for an HDI; expect -inf..+inf.
    result = effect_size(treatment_deltas=[0.1, 0.2], control_deltas=[])
    assert math.isinf(result.hdi_95_low)
    assert math.isinf(result.hdi_95_high)
    assert result.p_benefit == 0.5


def test_effect_size_detects_clear_treatment_benefit() -> None:
    # Treatment coverage improvements concentrated around 0.05;
    # control near 0.0. Expect delta ~0.05, HDI excluding zero.
    treatment = [0.05, 0.06, 0.04, 0.05, 0.07, 0.05, 0.04, 0.06]
    control = [0.00, -0.01, 0.01, 0.00, 0.01, -0.01, 0.00, 0.00]
    result = effect_size(treatment_deltas=treatment, control_deltas=control)
    assert result.delta_mean == pytest.approx(0.05, abs=0.02)
    assert result.hdi_95_low > 0  # zero excluded from below
    assert result.p_benefit > 0.99


def test_effect_size_zero_difference_centres_on_zero() -> None:
    # Matched distributions → delta ~0, p_benefit ~0.5.
    treatment = [0.01, 0.02, 0.01, 0.00, 0.02, 0.01, 0.00, 0.01]
    control = [0.00, 0.02, 0.01, 0.01, 0.02, 0.00, 0.01, 0.01]
    result = effect_size(treatment_deltas=treatment, control_deltas=control)
    assert abs(result.delta_mean) < 0.01
    assert 0.3 < result.p_benefit < 0.7


def test_effect_size_negative_treatment_effect() -> None:
    # Treatment is WORSE than control. HDI should exclude zero from above.
    treatment = [-0.05, -0.04, -0.06, -0.05, -0.05, -0.04, -0.06, -0.05]
    control = [0.00, 0.01, -0.01, 0.00, 0.00, 0.01, 0.00, 0.00]
    result = effect_size(treatment_deltas=treatment, control_deltas=control)
    assert result.delta_mean < 0
    assert result.hdi_95_high < 0
    assert result.p_benefit < 0.01
