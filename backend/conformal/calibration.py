"""Split conformal quantile computation.

Given n calibration scores and target miscoverage alpha, the finite-
sample marginal coverage guarantee of split conformal is:

    P(y ∈ C(x)) >= 1 - alpha

when C(x) = { y : s(x, y) <= q_hat } and q_hat is the
ceil((n + 1) * (1 - alpha)) / n empirical quantile of the calibration
scores (Vovk et al. 2005). The +1 in the numerator is essential — it
accounts for exchangeability with the test point and is what separates
this from a naive empirical quantile.

This module is pure math with no I/O. Repository reads from the
calibration_set table live elsewhere; tests here use synthetic inputs.
"""

from __future__ import annotations

import math


def q_hat_from_scores(scores: list[float], alpha: float) -> float:
    """Compute the split-conformal quantile.

    `scores` is the list of nonconformity scores on the calibration set.
    `alpha` is the target miscoverage (e.g. 0.10 for 90% coverage).

    Returns the ceil((n+1) * (1-alpha))/n empirical quantile. Returns
    +inf when the calibration set is too small to compute any
    meaningful quantile — this is the fail-closed path: an infinite
    q_hat makes the prediction set contain every candidate, which is
    safer than an under-estimated q_hat that excludes the truth.
    """
    if alpha <= 0.0 or alpha >= 1.0:
        raise ValueError(f"alpha must be in (0, 1); got {alpha}")

    finite_scores = sorted(float(s) for s in scores if math.isfinite(s))
    n = len(finite_scores)
    if n == 0:
        return math.inf

    # The smallest q such that ceil((n+1) * (1-alpha)) / n-th score is
    # the quantile. Equivalently: index k = ceil((n+1) * (1-alpha)) - 1
    # into the sorted list, saturating at n - 1.
    k = math.ceil((n + 1) * (1.0 - alpha)) - 1
    if k >= n:
        # The formula overshoots when n * alpha < 1, i.e. the sample is
        # too small to resolve the requested quantile. Return +inf to
        # trigger fail-closed (the calibration set needs to grow).
        return math.inf
    if k < 0:
        k = 0
    return finite_scores[k]


def empirical_coverage(scores: list[float], q_hat: float) -> float:
    """Fraction of held-out scores that satisfy s <= q_hat.

    Used by tests and by the coverage monitor (issue #26) to verify the
    marginal guarantee holds in practice.
    """
    if not scores:
        return 0.0
    covered = sum(1 for s in scores if math.isfinite(s) and s <= q_hat)
    return covered / len(scores)
