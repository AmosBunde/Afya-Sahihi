"""Maximum Mean Discrepancy drift detector.

MMD is a kernel-based two-sample test. Given a reference sample X
(e.g. the last 7d of nonconformity scores) and a current sample Y
(e.g. the last 500 scores), MMD² estimates the squared distance
between the two distributions in a reproducing kernel Hilbert space.

Under the null hypothesis (X and Y from the same distribution),
MMD² is approximately zero. A persistently positive MMD² above
`DRIFT_DETECTOR_THRESHOLD` is the signal that the score distribution
has shifted — which usually means either the corpus has changed or
the generation/retrieval behavior has regressed.

We use the unbiased U-statistic estimator with a Gaussian (RBF)
kernel. The bandwidth is set via the median heuristic — the median
of pairwise distances in the combined sample — which is the standard
choice for 1D kernel-based tests.

Pure Python. For n ≤ 500 the O(n²) cost is ~100ms, which fits the
5-minute metric refresh cadence comfortably. If n grows past ~1000,
swap to numpy without changing the public API.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DriftResult:
    """Outcome of one MMD comparison."""

    mmd_squared: float
    bandwidth: float
    n_reference: int
    n_current: int
    is_drifted: bool


def compute_mmd_squared(
    reference: list[float],
    current: list[float],
    *,
    bandwidth: float | None = None,
) -> DriftResult:
    """Unbiased MMD² estimate with Gaussian kernel.

    Raises ValueError on empty or tiny samples; the caller decides
    whether that is fail-closed (treat as "drifted") or silent skip
    (treat as "not enough data yet"). The coverage monitor chooses
    fail-closed — an inability to compute drift is itself a signal.
    """
    n = len(reference)
    m = len(current)
    if n < 2 or m < 2:
        raise ValueError(f"MMD requires at least 2 samples per side; got n={n}, m={m}")

    ref = [float(x) for x in reference if math.isfinite(x)]
    cur = [float(y) for y in current if math.isfinite(y)]
    if len(ref) < 2 or len(cur) < 2:
        raise ValueError("MMD requires at least 2 finite samples per side")

    sigma = bandwidth if bandwidth is not None else _median_heuristic(ref + cur)
    if sigma <= 0:
        # Degenerate: all inputs identical; by definition MMD² = 0.
        return DriftResult(
            mmd_squared=0.0,
            bandwidth=0.0,
            n_reference=len(ref),
            n_current=len(cur),
            is_drifted=False,
        )

    two_sigma_sq = 2.0 * sigma * sigma

    # Unbiased estimator: diagonal terms dropped.
    sum_xx = 0.0
    nn = len(ref)
    for i in range(nn):
        for j in range(i + 1, nn):
            sum_xx += _rbf(ref[i], ref[j], two_sigma_sq)
    # 2 * sum_xx / (nn * (nn - 1)) is the mean of off-diagonal pairs
    # (multiplied by 2 because we only computed the upper triangle).
    term_xx = 2.0 * sum_xx / (nn * (nn - 1))

    sum_yy = 0.0
    mm = len(cur)
    for i in range(mm):
        for j in range(i + 1, mm):
            sum_yy += _rbf(cur[i], cur[j], two_sigma_sq)
    term_yy = 2.0 * sum_yy / (mm * (mm - 1))

    sum_xy = 0.0
    for x in ref:
        for y in cur:
            sum_xy += _rbf(x, y, two_sigma_sq)
    term_xy = 2.0 * sum_xy / (nn * mm)

    mmd_sq = term_xx + term_yy - term_xy
    # Numerical floor: small negative values are estimator noise, not
    # real signal. Clamp to zero so downstream thresholding is honest.
    if mmd_sq < 0.0:
        mmd_sq = 0.0

    return DriftResult(
        mmd_squared=mmd_sq,
        bandwidth=sigma,
        n_reference=len(ref),
        n_current=len(cur),
        is_drifted=False,  # caller compares against threshold
    )


def detect_drift(
    *,
    reference: list[float],
    current: list[float],
    threshold: float,
    bandwidth: float | None = None,
) -> DriftResult:
    """Compute MMD² and flag drift against `threshold`.

    `threshold` is `DRIFT_DETECTOR_THRESHOLD` from env/conformal.env.
    Default 0.01 is a conservative value; the calibration monitor
    should tune this per-deployment.
    """
    result = compute_mmd_squared(reference, current, bandwidth=bandwidth)
    return DriftResult(
        mmd_squared=result.mmd_squared,
        bandwidth=result.bandwidth,
        n_reference=result.n_reference,
        n_current=result.n_current,
        is_drifted=result.mmd_squared > threshold,
    )


def _rbf(x: float, y: float, two_sigma_sq: float) -> float:
    """RBF (Gaussian) kernel: exp(-||x - y||² / (2σ²))."""
    diff = x - y
    return math.exp(-diff * diff / two_sigma_sq)


def _median_heuristic(samples: list[float]) -> float:
    """Median pairwise distance — the canonical RBF bandwidth choice.

    For n samples this is O(n²) pairs; capped by the caller's n (typ.
    <= 1000). A subsample would be cheaper but the heuristic is
    bandwidth-sensitive enough that we prefer the exact value at this
    scale.
    """
    n = len(samples)
    if n < 2:
        return 0.0
    dists: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            dists.append(abs(samples[i] - samples[j]))
    if not dists:
        return 0.0
    return float(statistics.median(dists))
