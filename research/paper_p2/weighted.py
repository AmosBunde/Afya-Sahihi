"""Weighted conformal prediction (Tibshirani et al. 2019).

Covariate shift breaks the exchangeability assumption of split CP,
so the unweighted empirical quantile of calibration scores no longer
gives a valid coverage guarantee on the target distribution.
Weighted CP repairs the guarantee by re-weighting each calibration
score by the target/source likelihood ratio:

    w_i = p_target(x_i) / p_source(x_i)

The weighted empirical quantile at level (1 - α) is taken over the
distribution {(s_i, w_i / Σ w_j)}. When w_i ≡ 1 (no shift) we recover
split CP.

The likelihood ratio estimator itself is a nuisance parameter. Paper
P2 uses a logistic-regression-over-features density-ratio estimator
(Sugiyama 2012) in the experiments, but this module ships only the
re-weighted quantile computation — the ratio estimator is a
pluggable input.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WeightedQuantileResult:
    q_hat: float
    n_samples: int
    effective_sample_size: float  # Σw² / Σw_i_normalised²


def weighted_quantile(
    *,
    scores: list[float],
    weights: list[float],
    alpha: float,
) -> WeightedQuantileResult:
    """Weighted empirical quantile at level (1 − α).

    Scores are sorted ascending; we find the smallest threshold τ
    such that Σ_{s_i ≤ τ} w_i / Σ w_j ≥ 1 − α. The result is the
    (1 − α)-quantile under the weighted empirical distribution.

    Effective sample size (Kong 1992): 1 / Σ (w_i_norm)². Low ESS
    means the shift is severe and the guarantee degrades; Paper P2
    reports ESS alongside q_hat for every weighted split.
    """
    if len(scores) != len(weights):
        raise ValueError(f"scores ({len(scores)}) != weights ({len(weights)})")
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"alpha must be in (0, 1); got {alpha}")
    if not scores:
        return WeightedQuantileResult(
            q_hat=float("inf"), n_samples=0, effective_sample_size=0.0
        )

    for w in weights:
        if w < 0.0:
            raise ValueError("weights must be non-negative")

    total_w = sum(weights)
    if total_w == 0.0:
        return WeightedQuantileResult(
            q_hat=float("inf"), n_samples=0, effective_sample_size=0.0
        )

    # Sort score-weight pairs ascending by score.
    pairs = sorted(zip(scores, weights, strict=True), key=lambda p: p[0])

    # Normalise weights then accumulate CDF-style. `eps` guards
    # against float-sum drift — e.g. 10 weights of 1.0/10 add to
    # 0.999... < 1.0, so `cumulative >= target` would incorrectly
    # skip the last bucket.
    target = 1.0 - alpha
    eps = 1e-9
    cumulative = 0.0
    q_hat = pairs[-1][0]
    for s, w in pairs:
        cumulative += w / total_w
        if cumulative >= target - eps:
            q_hat = s
            break

    # Effective sample size
    norm_weights = [w / total_w for w in weights]
    sum_sq = sum(x * x for x in norm_weights)
    ess = 1.0 / sum_sq if sum_sq > 0.0 else 0.0

    return WeightedQuantileResult(
        q_hat=q_hat, n_samples=len(scores), effective_sample_size=ess
    )


def likelihood_ratio_from_logits(
    *,
    source_logits: list[float],
    target_logits: list[float],
) -> list[float]:
    """Convert (logit_target, logit_source) pairs to weights.

    Common setup: a classifier trained to distinguish source vs
    target returns a logit `z = log p_target / p_source` per
    calibration point. The weight is exp(z). Clips at exp(±20) to
    avoid a single outlier dominating the weighted quantile; Paper P2
    flags when clipping fires as a shift-severity proxy.
    """
    if len(source_logits) != len(target_logits):
        raise ValueError("source_logits and target_logits length mismatch")
    import math

    weights: list[float] = []
    clip = 20.0
    for sl, tl in zip(source_logits, target_logits, strict=True):
        z = tl - sl
        z_clipped = max(-clip, min(clip, z))
        weights.append(math.exp(z_clipped))
    return weights
