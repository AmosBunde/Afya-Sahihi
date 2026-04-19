"""Tests for Mondrian CP."""

from __future__ import annotations

import math

import pytest

from research.paper_p2.mondrian import (
    MondrianModel,
    _conformal_quantile,
    fit_mondrian,
    marginal_coverage_by_stratum,
)


def test_conformal_quantile_uses_exchangeability_correction() -> None:
    # n=10 calibration points, α=0.1 → ⌈11 · 0.9⌉ = 10 → 10th order
    # statistic (1-based) = 9th index (0-based).
    scores = [float(i) for i in range(10)]
    q = _conformal_quantile(scores=scores, alpha=0.1)
    assert q == pytest.approx(9.0)


def test_conformal_quantile_empty_returns_inf() -> None:
    q = _conformal_quantile(scores=[], alpha=0.1)
    assert math.isinf(q)


def test_fit_mondrian_per_stratum_quantiles() -> None:
    # Two strata with different score distributions.
    dosing_scores = [float(i) for i in range(25)]  # scores 0..24
    general_scores = [0.5 * i for i in range(25)]  # scores 0..12
    scores = dosing_scores + general_scores
    strata = (["dosing"] * 25) + (["general"] * 25)
    model = fit_mondrian(scores=scores, strata=strata, alpha=0.1)
    # dosing should have a higher q_hat than general.
    assert model.q_hat_by_stratum["dosing"] > model.q_hat_by_stratum["general"]
    assert model.n_samples_by_stratum["dosing"] == 25
    assert model.n_samples_by_stratum["general"] == 25


def test_fit_mondrian_sparse_stratum_falls_back_to_global() -> None:
    # One stratum has only 5 samples — below the default threshold of 20.
    dosing_scores = [float(i) for i in range(25)]  # 25 samples
    rare_scores = [100.0] * 5  # 5 samples, extreme
    scores = dosing_scores + rare_scores
    strata = (["dosing"] * 25) + (["rare"] * 5)
    model = fit_mondrian(
        scores=scores, strata=strata, alpha=0.1, min_samples_per_stratum=20
    )
    # rare inherits the global q_hat (not its own).
    assert model.q_hat_by_stratum["rare"] == model.fallback_q_hat
    # dosing has its own q_hat.
    assert model.q_hat_by_stratum["dosing"] != model.fallback_q_hat


def test_fit_mondrian_rejects_bad_alpha() -> None:
    with pytest.raises(ValueError, match="alpha"):
        fit_mondrian(scores=[1.0], strata=["x"], alpha=0.0)


def test_fit_mondrian_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="strata"):
        fit_mondrian(scores=[1.0, 2.0], strata=["a"], alpha=0.1)


def test_mondrian_model_fallback_on_unseen_stratum() -> None:
    model = MondrianModel(
        q_hat_by_stratum={"dosing": 5.0},
        fallback_q_hat=10.0,
        n_samples_by_stratum={"dosing": 30},
    )
    assert model.q_hat_for("dosing") == 5.0
    assert model.q_hat_for("never-seen") == 10.0


def test_marginal_coverage_by_stratum_counts_hits() -> None:
    # Two strata, 10 test points each; dosing covered 9/10, general 7/10.
    model = MondrianModel(
        q_hat_by_stratum={"dosing": 5.0, "general": 3.0},
        fallback_q_hat=4.0,
        n_samples_by_stratum={"dosing": 100, "general": 100},
    )
    test_scores = [0.0] * 20
    test_strata = (["dosing"] * 10) + (["general"] * 10)
    test_covered = ([True] * 9 + [False]) + ([True] * 7 + [False] * 3)
    result = marginal_coverage_by_stratum(
        model=model,
        test_scores=test_scores,
        test_strata=test_strata,
        test_covered_ground_truth=test_covered,
    )
    assert result["dosing"] == pytest.approx(0.9)
    assert result["general"] == pytest.approx(0.7)


def test_marginal_coverage_rejects_mismatched_lengths() -> None:
    model = MondrianModel(
        q_hat_by_stratum={}, fallback_q_hat=1.0, n_samples_by_stratum={}
    )
    with pytest.raises(ValueError, match="match"):
        marginal_coverage_by_stratum(
            model=model,
            test_scores=[0.1],
            test_strata=["a", "b"],
            test_covered_ground_truth=[True],
        )
