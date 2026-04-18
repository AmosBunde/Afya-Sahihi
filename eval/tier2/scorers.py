"""Four Tier 2 scorers: ECE, marginal_coverage, set_size, topic_coherence.

All pure Python so tests run without Inspect AI. `tier2/golden_set.py`
wires them into the Inspect AI task with lazy imports.

Math notes:
  - ECE bins samples by confidence into `n_bins` equal-width buckets
    and returns the weighted mean of |accuracy - confidence| per bin.
    Lower is better; < 0.08 is the deployment gate.
  - marginal_coverage is the fraction of cases where the ground-truth
    label is in the prediction set. Target is 1 - alpha (e.g. 0.90);
    deviation > 0.03 blocks promotion.
  - set_size_mean is the average prediction-set size. An increase >15%
    vs baseline is a regression — a larger set means lower precision.
  - topic_coherence is the fraction of cases whose prefilter
    topic_score exceeds the coherence threshold (0.65 by default).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExpectedCalibrationError:
    """ECE + supporting breakdown for debugging."""

    ece: float
    n_samples: int
    n_bins: int
    per_bin_gap: tuple[float, ...]  # |acc - conf| per bin


def expected_calibration_error(
    *,
    confidences: list[float],
    correct: list[bool],
    n_bins: int = 10,
) -> ExpectedCalibrationError:
    """Equal-width-bin ECE.

    ECE = Σ_b (|B_b| / n) × | accuracy(B_b) − confidence(B_b) |
    where B_b is the set of samples with confidence ∈ [b/n, (b+1)/n).
    """
    if n_bins <= 0:
        raise ValueError("n_bins must be positive")
    if len(confidences) != len(correct):
        raise ValueError(
            f"confidences ({len(confidences)}) != correct ({len(correct)})"
        )
    n = len(confidences)
    if n == 0:
        return ExpectedCalibrationError(
            ece=0.0, n_samples=0, n_bins=n_bins, per_bin_gap=tuple([0.0] * n_bins)
        )

    # Assign each sample to a bin
    bin_hits: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for conf, is_correct in zip(confidences, correct, strict=True):
        if not math.isfinite(conf):
            continue
        b = min(int(conf * n_bins), n_bins - 1)
        b = max(0, b)
        bin_hits[b].append((conf, is_correct))

    n_valid = sum(len(b) for b in bin_hits)
    if n_valid == 0:
        return ExpectedCalibrationError(
            ece=0.0,
            n_samples=0,
            n_bins=n_bins,
            per_bin_gap=tuple([0.0] * n_bins),
        )

    ece = 0.0
    per_bin: list[float] = []
    for bucket in bin_hits:
        if not bucket:
            per_bin.append(0.0)
            continue
        acc = sum(1 for _, c in bucket if c) / len(bucket)
        conf = sum(c for c, _ in bucket) / len(bucket)
        gap = abs(acc - conf)
        per_bin.append(gap)
        ece += (len(bucket) / n_valid) * gap

    return ExpectedCalibrationError(
        ece=ece,
        n_samples=n_valid,
        n_bins=n_bins,
        per_bin_gap=tuple(per_bin),
    )


def marginal_coverage(
    *,
    prediction_sets: list[list[str]],
    ground_truths: list[str],
) -> float:
    """Fraction of cases where ground_truth is in prediction_set."""
    if len(prediction_sets) != len(ground_truths):
        raise ValueError(
            f"prediction_sets ({len(prediction_sets)}) != "
            f"ground_truths ({len(ground_truths)})"
        )
    if not ground_truths:
        return 0.0
    covered = sum(
        1 for ps, gt in zip(prediction_sets, ground_truths, strict=True) if gt in ps
    )
    return covered / len(ground_truths)


def set_size_mean(prediction_sets: list[list[str]]) -> float:
    """Mean prediction-set size across cases."""
    if not prediction_sets:
        return 0.0
    return sum(len(ps) for ps in prediction_sets) / len(prediction_sets)


def set_size_change_pct(current: float, baseline: float) -> float:
    """Percent change in mean set size. Positive = grew = regression."""
    if baseline <= 0:
        # Can't compute percent change from zero; signal via inf.
        return math.inf if current > 0 else 0.0
    return (current - baseline) / baseline * 100.0


def topic_coherence(
    *,
    topic_scores: list[float],
    threshold: float = 0.65,
) -> float:
    """Fraction of cases whose prefilter topic_score exceeds threshold."""
    if not topic_scores:
        return 0.0
    above = sum(1 for s in topic_scores if math.isfinite(s) and s >= threshold)
    return above / len(topic_scores)


@dataclass(frozen=True, slots=True)
class Tier2Thresholds:
    """Gate thresholds from env/eval.env."""

    ece_max: float = 0.08
    coverage_deviation_max: float = 0.03
    set_size_increase_max_pct: float = 15.0
    topic_coherence_min: float = 0.80


@dataclass(frozen=True, slots=True)
class Tier2Verdict:
    """Result of a Tier 2 run against thresholds."""

    passed: bool
    ece: float
    coverage: float
    coverage_deviation: float
    set_size_mean: float
    set_size_change_pct: float
    topic_coherence: float
    breaches: tuple[str, ...]


def evaluate_tier2(
    *,
    ece: float,
    coverage: float,
    coverage_target: float,
    set_size_mean_value: float,
    set_size_baseline: float,
    topic_coherence_value: float,
    thresholds: Tier2Thresholds,
) -> Tier2Verdict:
    """Combine metrics against thresholds; return pass/fail + breach list."""
    breaches: list[str] = []

    if ece > thresholds.ece_max:
        breaches.append(f"ece:{ece:.4f}>{thresholds.ece_max}")

    deviation = abs(coverage - coverage_target)
    if deviation > thresholds.coverage_deviation_max:
        breaches.append(
            f"coverage_deviation:{deviation:.4f}>{thresholds.coverage_deviation_max}"
        )

    size_change = set_size_change_pct(set_size_mean_value, set_size_baseline)
    if size_change > thresholds.set_size_increase_max_pct:
        breaches.append(
            f"set_size_increase:{size_change:.2f}%>{thresholds.set_size_increase_max_pct}%"
        )

    if topic_coherence_value < thresholds.topic_coherence_min:
        breaches.append(
            f"topic_coherence:{topic_coherence_value:.4f}<{thresholds.topic_coherence_min}"
        )

    return Tier2Verdict(
        passed=len(breaches) == 0,
        ece=ece,
        coverage=coverage,
        coverage_deviation=deviation,
        set_size_mean=set_size_mean_value,
        set_size_change_pct=size_change,
        topic_coherence=topic_coherence_value,
        breaches=tuple(breaches),
    )
