"""Tests for the synthetic shift generator."""

from __future__ import annotations

import math
import random

import pytest

from research.paper_p2.synthetic_shift import (
    analytical_likelihood_ratio,
    sample_source,
    sample_target,
)


def test_sample_source_produces_requested_count() -> None:
    rng = random.Random(42)
    samples = sample_source(n=100, alpha=0.1, rng=rng)
    assert len(samples) == 100
    for s in samples:
        assert s.source_or_target == "source"


def test_sample_source_in_set_rate_matches_alpha() -> None:
    rng = random.Random(42)
    samples = sample_source(n=10_000, alpha=0.1, rng=rng)
    covered = sum(1 for s in samples if s.truth_in_set)
    # ~90% covered (1 - α) within ±2pp at n=10k.
    assert 0.88 < covered / len(samples) < 0.92


def test_sample_target_shift_increases_miscoverage() -> None:
    rng = random.Random(42)
    target = sample_target(n=10_000, shift_mean=1.0, alpha=0.1, rng=rng)
    # With shift_mean=1, target_miscov = 0.1 * 2 = 0.2, so ~80% covered.
    covered = sum(1 for s in target if s.truth_in_set)
    ratio = covered / len(target)
    assert 0.78 < ratio < 0.82


def test_sample_source_is_reproducible_under_same_seed() -> None:
    a = sample_source(n=50, alpha=0.1, rng=random.Random(7))
    b = sample_source(n=50, alpha=0.1, rng=random.Random(7))
    assert [s.x for s in a] == [s.x for s in b]
    assert [s.truth_in_set for s in a] == [s.truth_in_set for s in b]


def test_analytical_likelihood_ratio_equals_one_at_zero_shift() -> None:
    for x in [-2.0, -1.0, 0.0, 1.0, 2.0]:
        assert analytical_likelihood_ratio(x=x, shift_mean=0.0) == pytest.approx(
            1.0, abs=1e-9
        )


def test_analytical_likelihood_ratio_is_monotone_in_x() -> None:
    # For positive shift_mean, the ratio grows with x (target mode is right of source).
    xs = [-1.0, 0.0, 0.5, 1.0, 2.0]
    ratios = [analytical_likelihood_ratio(x=x, shift_mean=1.0) for x in xs]
    for prev, curr in zip(ratios, ratios[1:], strict=False):
        assert curr > prev


def test_analytical_likelihood_ratio_closed_form() -> None:
    # At x=1, shift_mean=1, σ=1:
    # log_ratio = (2·1·1 − 1²) / (2·1²) = 1/2
    # ratio = exp(0.5) ≈ 1.6487
    assert analytical_likelihood_ratio(
        x=1.0, shift_mean=1.0, sigma=1.0
    ) == pytest.approx(math.exp(0.5), abs=1e-9)
