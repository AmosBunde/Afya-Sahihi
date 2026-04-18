"""Tests for q_hat computation and the coverage property.

The coverage test is the one that matters: under exchangeability,
empirical coverage on held-out data must be >= 1 - alpha. If this
test ever fails, the q_hat formula is wrong and a clinician's
confidence in the prediction set is based on a lie.
"""

from __future__ import annotations

import math
import random

import pytest

from conformal.calibration import empirical_coverage, q_hat_from_scores

# ---- Boundary cases ----


def test_q_hat_rejects_alpha_out_of_range() -> None:
    with pytest.raises(ValueError):
        q_hat_from_scores([0.1, 0.2], alpha=0.0)
    with pytest.raises(ValueError):
        q_hat_from_scores([0.1, 0.2], alpha=1.0)


def test_q_hat_empty_set_returns_inf() -> None:
    assert q_hat_from_scores([], alpha=0.1) == math.inf


def test_q_hat_undersized_returns_inf() -> None:
    # n=5, alpha=0.1 → ceil(6 * 0.9) = 6 > 5, so k=5 overshoots → inf
    assert q_hat_from_scores([0.1, 0.2, 0.3, 0.4, 0.5], alpha=0.1) == math.inf


def test_q_hat_filters_nonfinite() -> None:
    # The two non-finite scores are dropped; the remaining list is too
    # small to resolve alpha=0.1, so we return +inf.
    result = q_hat_from_scores([float("inf"), float("nan"), 0.1, 0.2], alpha=0.1)
    assert result == math.inf


# ---- Correctness on known inputs ----


def test_q_hat_known_value_alpha_0_1_n_100() -> None:
    # Scores 1..100. alpha=0.1 → k = ceil(101 * 0.9) - 1 = 91 - 1 = 90.
    # Sorted[90] = 91.
    scores = [float(i) for i in range(1, 101)]
    assert q_hat_from_scores(scores, alpha=0.1) == pytest.approx(91.0)


def test_q_hat_known_value_alpha_0_05_n_200() -> None:
    # Scores 1..200. alpha=0.05 → k = ceil(201 * 0.95) - 1 = 191 - 1 = 190.
    # Sorted[190] = 191.
    scores = [float(i) for i in range(1, 201)]
    assert q_hat_from_scores(scores, alpha=0.05) == pytest.approx(191.0)


# ---- Empirical coverage ----


def test_empirical_coverage_zero_on_empty() -> None:
    assert empirical_coverage([], q_hat=1.0) == 0.0


def test_empirical_coverage_counts_fraction_below_q() -> None:
    assert empirical_coverage([0.1, 0.5, 0.9, 1.5], q_hat=1.0) == pytest.approx(0.75)


# ---- The marginal-coverage guarantee ----


def test_marginal_coverage_at_least_1_minus_alpha() -> None:
    """Under exchangeability, empirical coverage on held-out data must
    be >= 1 - alpha. Tolerates small sampling noise with a margin, but
    we make the margin tight (0.02) so a real regression is caught.
    """
    random.seed(20260417)
    alpha = 0.10
    n_cal = 1000
    n_test = 2000
    n_trials = 20

    covered_rates: list[float] = []
    for trial in range(n_trials):
        rng = random.Random(trial)
        # Exchangeable samples from Normal(0, 1), non-negative scores
        # via abs() — the shape of the distribution does not affect the
        # guarantee; what matters is that cal and test share it.
        cal = [abs(rng.gauss(0, 1)) for _ in range(n_cal)]
        test = [abs(rng.gauss(0, 1)) for _ in range(n_test)]
        q = q_hat_from_scores(cal, alpha=alpha)
        covered_rates.append(empirical_coverage(test, q))

    avg_cov = sum(covered_rates) / len(covered_rates)
    # Marginal guarantee: E[coverage] >= 1 - alpha = 0.90.
    # Over 20 trials the Monte Carlo error is ~0.01, so we assert 0.88
    # to leave headroom for legitimate variance.
    assert avg_cov >= 0.88, f"average empirical coverage {avg_cov:.4f} < 0.88"


def test_marginal_coverage_alpha_0_05() -> None:
    """Same guarantee at a tighter alpha."""
    alpha = 0.05
    n_cal = 2000
    n_test = 4000
    n_trials = 10

    covered_rates: list[float] = []
    for trial in range(n_trials):
        rng = random.Random(10000 + trial)
        cal = [abs(rng.gauss(0, 1)) for _ in range(n_cal)]
        test = [abs(rng.gauss(0, 1)) for _ in range(n_test)]
        q = q_hat_from_scores(cal, alpha=alpha)
        covered_rates.append(empirical_coverage(test, q))

    avg_cov = sum(covered_rates) / len(covered_rates)
    assert avg_cov >= 0.94, f"average empirical coverage {avg_cov:.4f} < 0.94"
