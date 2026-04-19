"""Calibration metrics. All pure Python — no numpy / no scipy.

ECE is the weighted mean per-bin |accuracy − confidence| (Guo 2017).
MCE is the worst-case per-bin gap.
ACE is the ECE with equal-MASS bins instead of equal-width; handles
    confidence distributions concentrated near 1.
Brier is mean squared error (confidence − correct).
Reliability-diagram area is the integrated absolute deviation from
    the identity line — an ECE-like summary that treats reliability
    as a continuous curve instead of a histogram.

Functions take parallel lists of confidences (∈ [0, 1]) and correct
booleans. Non-finite confidences are filtered out with a
`ValueError` rather than silently dropped; a paper figure should
never be rendered from data we partially discarded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower: float
    upper: float
    n_samples: int
    mean_confidence: float
    accuracy: float
    gap: float  # |accuracy - mean_confidence|


def _validate_inputs(confidences: list[float], correct: list[bool]) -> None:
    if len(confidences) != len(correct):
        raise ValueError(
            f"confidences ({len(confidences)}) != correct ({len(correct)})"
        )
    for c in confidences:
        if not math.isfinite(c):
            raise ValueError(f"non-finite confidence {c!r}")
        if c < 0.0 or c > 1.0:
            raise ValueError(f"confidence {c!r} outside [0, 1]")


def equal_width_bins(
    *,
    confidences: list[float],
    correct: list[bool],
    n_bins: int = 15,
) -> tuple[ReliabilityBin, ...]:
    """Partition samples into n_bins equal-width buckets over [0, 1].

    A sample with confidence == 1.0 lands in the top bin (inclusive
    right edge); otherwise bins are half-open [lower, upper).
    """
    _validate_inputs(confidences, correct)
    if n_bins <= 0:
        raise ValueError("n_bins must be > 0")
    edges = [i / n_bins for i in range(n_bins + 1)]
    # Bucket assignment
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for conf, is_correct in zip(confidences, correct, strict=True):
        idx = int(conf * n_bins)
        if idx == n_bins:
            idx = n_bins - 1
        buckets[idx].append((conf, is_correct))

    out: list[ReliabilityBin] = []
    for i, bucket in enumerate(buckets):
        if bucket:
            n = len(bucket)
            mean_conf = sum(c for c, _ in bucket) / n
            acc = sum(1 for _, c in bucket if c) / n
            gap = abs(acc - mean_conf)
        else:
            n = 0
            mean_conf = 0.0
            acc = 0.0
            gap = 0.0
        out.append(
            ReliabilityBin(
                lower=edges[i],
                upper=edges[i + 1],
                n_samples=n,
                mean_confidence=mean_conf,
                accuracy=acc,
                gap=gap,
            )
        )
    return tuple(out)


def equal_mass_bins(
    *,
    confidences: list[float],
    correct: list[bool],
    n_bins: int = 15,
) -> tuple[ReliabilityBin, ...]:
    """Partition samples into n_bins quantile buckets (equal mass).

    Used for ACE (Nixon 2019). When the model's confidence is heavily
    concentrated (say near 1.0) equal-width bins leave most buckets
    empty and ECE is dominated by one bucket; equal-mass bins spread
    the signal out.
    """
    _validate_inputs(confidences, correct)
    if n_bins <= 0:
        raise ValueError("n_bins must be > 0")
    n = len(confidences)
    if n == 0:
        return tuple(ReliabilityBin(0.0, 1.0, 0, 0.0, 0.0, 0.0) for _ in range(n_bins))

    pairs = sorted(zip(confidences, correct, strict=True), key=lambda p: p[0])
    bucket_size = n / n_bins  # float; indices round
    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for i, p in enumerate(pairs):
        idx = int(i / bucket_size)
        if idx == n_bins:
            idx = n_bins - 1
        buckets[idx].append(p)

    out: list[ReliabilityBin] = []
    for bucket in buckets:
        if not bucket:
            out.append(ReliabilityBin(0.0, 1.0, 0, 0.0, 0.0, 0.0))
            continue
        confs = [c for c, _ in bucket]
        lower = min(confs)
        upper = max(confs)
        bn = len(bucket)
        mean_conf = sum(confs) / bn
        acc = sum(1 for _, c in bucket if c) / bn
        gap = abs(acc - mean_conf)
        out.append(ReliabilityBin(lower, upper, bn, mean_conf, acc, gap))
    return tuple(out)


def ece(
    *,
    confidences: list[float],
    correct: list[bool],
    n_bins: int = 15,
) -> float:
    """Expected Calibration Error (Guo 2017). Equal-width bins."""
    if not confidences:
        return 0.0
    bins = equal_width_bins(confidences=confidences, correct=correct, n_bins=n_bins)
    n_total = sum(b.n_samples for b in bins)
    if n_total == 0:
        return 0.0
    return sum((b.n_samples / n_total) * b.gap for b in bins)


def mce(
    *,
    confidences: list[float],
    correct: list[bool],
    n_bins: int = 15,
) -> float:
    """Maximum Calibration Error — the worst per-bin gap."""
    if not confidences:
        return 0.0
    bins = equal_width_bins(confidences=confidences, correct=correct, n_bins=n_bins)
    # Only consider bins with samples; an empty bin has gap 0 trivially
    # but that's not a real calibration signal.
    occupied = [b.gap for b in bins if b.n_samples > 0]
    return max(occupied) if occupied else 0.0


def ace(
    *,
    confidences: list[float],
    correct: list[bool],
    n_bins: int = 15,
) -> float:
    """Adaptive Calibration Error (Nixon 2019). Equal-mass bins."""
    if not confidences:
        return 0.0
    bins = equal_mass_bins(confidences=confidences, correct=correct, n_bins=n_bins)
    n_total = sum(b.n_samples for b in bins)
    if n_total == 0:
        return 0.0
    return sum((b.n_samples / n_total) * b.gap for b in bins)


def brier(*, confidences: list[float], correct: list[bool]) -> float:
    """Brier score = mean((confidence − {0,1})²).

    Lower is better. Unlike ECE this is a proper scoring rule — it
    decomposes into calibration + refinement + uncertainty (Murphy
    1973) but the scalar alone is a useful summary.
    """
    _validate_inputs(confidences, correct)
    if not confidences:
        return 0.0
    n = len(confidences)
    total = sum(
        (c - (1.0 if r else 0.0)) ** 2
        for c, r in zip(confidences, correct, strict=True)
    )
    return total / n


def reliability_diagram_area(
    *,
    confidences: list[float],
    correct: list[bool],
    n_bins: int = 15,
) -> float:
    """Integrated area between the reliability curve and the y=x line.

    Approximates the integral via the trapezoidal rule over bin
    midpoints. Occupied bins only — empty bins contribute zero width.
    """
    if not confidences:
        return 0.0
    bins = equal_width_bins(confidences=confidences, correct=correct, n_bins=n_bins)
    midpoints: list[tuple[float, float]] = []
    for b in bins:
        if b.n_samples == 0:
            continue
        midpoints.append((b.mean_confidence, b.accuracy))
    if len(midpoints) < 2:
        return 0.0
    midpoints.sort(key=lambda p: p[0])
    area = 0.0
    for (x0, y0), (x1, y1) in zip(midpoints, midpoints[1:], strict=False):
        width = x1 - x0
        # Absolute deviation from y=x at each endpoint.
        d0 = abs(y0 - x0)
        d1 = abs(y1 - x1)
        area += 0.5 * (d0 + d1) * width
    return area
