"""Mondrian conformal prediction (Vovk et al. 2003).

Per-stratum q_hat: partition the calibration set by a categorical
variable (stratum), fit a separate q_hat per partition, then apply
the stratum-specific q_hat to each test point.

For clinical RAG the stratum is the case category: dosing,
contraindication, pediatric, pregnancy, etc. Heterogeneous coverage
is the motivation — a global q_hat wastes calibration signal on the
easy categories and under-covers the hard ones.

Coverage guarantee (Vovk Thm 2): marginal coverage within each
stratum holds at 1 − α, provided exchangeability within each stratum.
This is a strictly stronger guarantee than split CP's overall
marginal 1 − α.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MondrianModel:
    """Per-stratum q_hat table plus a fallback for unseen strata."""

    q_hat_by_stratum: dict[str, float]
    fallback_q_hat: float
    n_samples_by_stratum: dict[str, int]

    def q_hat_for(self, stratum: str) -> float:
        """Look up q_hat. Unknown stratum → fallback (global q_hat)."""
        return self.q_hat_by_stratum.get(stratum, self.fallback_q_hat)


def fit_mondrian(
    *,
    scores: list[float],
    strata: list[str],
    alpha: float,
    min_samples_per_stratum: int = 20,
) -> MondrianModel:
    """Fit one q_hat per stratum.

    Strata with fewer than `min_samples_per_stratum` calibration
    points inherit the global q_hat — too-sparse strata would give
    a noisy per-stratum estimate that hurts coverage more than it
    helps. Paper P2 reports the stratum-count threshold alongside
    the per-stratum q_hat.

    The quantile uses the exchangeability-corrected formula
        q_hat = ⌈(n + 1)(1 − α)⌉ / n-th order statistic
    matching split CP's convention.
    """
    if len(scores) != len(strata):
        raise ValueError(f"scores ({len(scores)}) != strata ({len(strata)})")
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1); got {alpha}")

    global_q = _conformal_quantile(scores=scores, alpha=alpha)

    by_stratum: dict[str, list[float]] = {}
    for s, st in zip(scores, strata, strict=True):
        by_stratum.setdefault(st, []).append(s)

    q_by_stratum: dict[str, float] = {}
    n_by_stratum: dict[str, int] = {}
    for stratum, stratum_scores in by_stratum.items():
        n = len(stratum_scores)
        n_by_stratum[stratum] = n
        if n < min_samples_per_stratum:
            # Too sparse — fall back to global.
            q_by_stratum[stratum] = global_q
        else:
            q_by_stratum[stratum] = _conformal_quantile(
                scores=stratum_scores, alpha=alpha
            )
    return MondrianModel(
        q_hat_by_stratum=q_by_stratum,
        fallback_q_hat=global_q,
        n_samples_by_stratum=n_by_stratum,
    )


def _conformal_quantile(*, scores: list[float], alpha: float) -> float:
    """q_hat = ⌈(n+1)(1−α)⌉ / n-th order statistic (split CP convention)."""
    if not scores:
        return float("inf")
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    # Index is 1-based in the formula; Python is 0-based so subtract 1.
    k = math.ceil((n + 1) * (1 - alpha))
    # Clamp to [1, n]: with small n and alpha near 1, k may exceed n.
    k = max(1, min(n, k))
    return sorted_scores[k - 1]


def marginal_coverage_by_stratum(
    *,
    model: MondrianModel,
    test_scores: list[float],
    test_strata: list[str],
    test_covered_ground_truth: list[bool],
) -> dict[str, float]:
    """Per-stratum empirical coverage on held-out test data.

    For each stratum s, compute the fraction of test points in s where
    the prediction set (threshold = model.q_hat_for(s)) covered the
    ground truth. Strata present in test but not in the model inherit
    the fallback q_hat. Strata with no test points don't appear in
    the output.

    The `test_covered_ground_truth` input is the per-test-point
    indicator of whether the truth label fell in the prediction set
    at threshold model.q_hat_for(stratum) — the caller computes this
    (the ground-truth lookup is not our concern). We just aggregate.
    """
    if not (len(test_scores) == len(test_strata) == len(test_covered_ground_truth)):
        raise ValueError("test_scores, test_strata, test_covered must all match length")

    hits_by_stratum: dict[str, int] = {}
    n_by_stratum: dict[str, int] = {}
    for _score, stratum, covered in zip(
        test_scores, test_strata, test_covered_ground_truth, strict=True
    ):
        n_by_stratum[stratum] = n_by_stratum.get(stratum, 0) + 1
        if covered:
            hits_by_stratum[stratum] = hits_by_stratum.get(stratum, 0) + 1

    return {
        stratum: hits_by_stratum.get(stratum, 0) / n
        for stratum, n in n_by_stratum.items()
        if n > 0
    }
