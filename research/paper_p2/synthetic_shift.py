"""Synthetic covariate-shift generator for Paper P2 experiments.

The source distribution is a Gaussian centred at 0 with σ=1; target
is a Gaussian centred at `shift_mean` with the same σ. Nonconformity
scores are a deterministic function of x (absolute residual after
a fixed linear model fit on source). Ground-truth "in-set" labels
are sampled so the empirical miscoverage on source is exactly α.

Uses Python's `random.Random` for reproducibility — Paper P2 replays
the same shift sweep across revisions of the paper, so the stream is
deterministic given (seed, shift_mean, n).

No numpy. All distributions sampled via the stdlib random module's
`gauss(mu, sigma)` (Box-Muller under the hood).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SyntheticSample:
    x: float
    score: float
    truth_in_set: bool
    source_or_target: str  # "source" | "target"


def _score_from_x(x: float) -> float:
    """Nonconformity score = |x - 0.5| — a V-shape over x.

    Tuned so a symmetric shift in x does not keep the score
    distribution identical (the shift is visible to the conformal
    estimator).
    """
    return abs(x - 0.5)


def sample_source(
    *,
    n: int,
    alpha: float,
    rng: random.Random,
) -> list[SyntheticSample]:
    """Draw n source samples. 1 − α fraction are in-set by construction."""
    out: list[SyntheticSample] = []
    for _ in range(n):
        x = rng.gauss(0.0, 1.0)
        score = _score_from_x(x)
        # In-set iff an independent Bernoulli(1 - α) flip is 1.
        truth_in_set = rng.random() < (1.0 - alpha)
        out.append(
            SyntheticSample(
                x=x, score=score, truth_in_set=truth_in_set, source_or_target="source"
            )
        )
    return out


def sample_target(
    *,
    n: int,
    shift_mean: float,
    alpha: float,
    rng: random.Random,
) -> list[SyntheticSample]:
    """Draw n target samples under a mean-shift covariate shift.

    Under the shift the empirical miscoverage on the source-calibrated
    q_hat is HIGHER than α for positive shift_mean (the target is
    further from 0 → larger scores on average → truth more likely
    outside the set). The paper's experiments fit each CP variant on
    a growing target set and plot coverage vs. target N.
    """
    # Per-point miscoverage bumps up with shift magnitude — we use a
    # logistic weighting so the effect is bounded in (0, 1).
    out: list[SyntheticSample] = []
    for _ in range(n):
        x = rng.gauss(shift_mean, 1.0)
        score = _score_from_x(x)
        # Target miscoverage is α * (1 + |shift_mean|). Clamp to (0, 1).
        target_miscov = max(0.001, min(0.999, alpha * (1.0 + abs(shift_mean))))
        truth_in_set = rng.random() < (1.0 - target_miscov)
        out.append(
            SyntheticSample(
                x=x, score=score, truth_in_set=truth_in_set, source_or_target="target"
            )
        )
    return out


def analytical_likelihood_ratio(
    *,
    x: float,
    shift_mean: float,
    sigma: float = 1.0,
) -> float:
    """Closed-form p_target(x) / p_source(x) for mean-shift Gaussians.

    Both distributions are N(mu, sigma²); the ratio of their densities
    reduces to a log-linear-in-x term. Used as the oracle weight in
    `weighted_quantile` for the sanity check that the implementation
    recovers target coverage under known ground-truth weights.
    """
    # log p_t - log p_s = (x²/(2σ²)) − ((x − m)²/(2σ²))
    #                   = (2mx − m²) / (2σ²)
    log_ratio = (2 * shift_mean * x - shift_mean * shift_mean) / (2 * sigma * sigma)
    return math.exp(log_ratio)
