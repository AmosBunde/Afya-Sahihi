"""Tests for acquisition functions."""

from __future__ import annotations

import math
import random

import pytest

from active_learning.acquisition import (
    ACQUISITION_FUNCTIONS,
    HARM_WEIGHTS,
    CandidateCase,
    ClinicalHarmWeightedAcquisition,
    ConformalSetSizeAcquisition,
    CoverageGapAcquisition,
    RandomAcquisition,
    UncertaintyEntropyAcquisition,
    resolve,
    shannon_entropy_nats,
    top_k,
)


def _case(
    case_id: str = "c-1",
    stratum: str = "general",
    logprobs: tuple[float, ...] = (-0.1, -2.0, -0.5),
    set_size: int = 3,
    coverage_target: float = 0.9,
    truth_in_set: bool | None = None,
) -> CandidateCase:
    return CandidateCase(
        case_id=case_id,
        stratum=stratum,
        token_logprobs=logprobs,
        conformal_set_size=set_size,
        conformal_coverage_target=coverage_target,
        truth_in_set=truth_in_set,
        ingested_at_iso="2026-04-19T00:00:00Z",
    )


# ---- shannon_entropy_nats ----


def test_entropy_uniform_is_log_n() -> None:
    # Three equal logprobs → uniform distribution over 3 → entropy ln(3).
    lp = (math.log(1 / 3), math.log(1 / 3), math.log(1 / 3))
    assert shannon_entropy_nats(lp) == pytest.approx(math.log(3), abs=1e-9)


def test_entropy_degenerate_is_zero() -> None:
    # One log(1)=0 token, rest log(0)=-inf → uniform over a single token.
    lp = (0.0, float("-inf"), float("-inf"))
    assert shannon_entropy_nats(lp) == pytest.approx(0.0, abs=1e-9)


def test_entropy_empty_is_zero() -> None:
    assert shannon_entropy_nats(()) == 0.0


def test_entropy_ignores_nonfinite() -> None:
    lp = (float("nan"), math.log(0.5), math.log(0.5))
    assert shannon_entropy_nats(lp) == pytest.approx(math.log(2), abs=1e-9)


# ---- Acquisition function registry ----


def test_registry_has_all_five_functions() -> None:
    expected = {
        "random",
        "uncertainty_entropy",
        "conformal_set_size",
        "coverage_gap",
        "clinical_harm_weighted",
    }
    assert expected == set(ACQUISITION_FUNCTIONS)


def test_resolve_raises_on_unknown() -> None:
    with pytest.raises(ValueError, match="unknown"):
        resolve("not-a-real-function")


# ---- Per-function behaviour ----


def test_random_is_deterministic_given_rng() -> None:
    rng = random.Random(42)
    scores_a = RandomAcquisition().score(candidates=[_case(), _case("c-2")], rng=rng)
    rng = random.Random(42)
    scores_b = RandomAcquisition().score(candidates=[_case(), _case("c-2")], rng=rng)
    assert scores_a == scores_b


def test_uncertainty_entropy_ranks_uniform_highest() -> None:
    rng = random.Random(0)
    uniform_case = _case("uni", logprobs=(math.log(1 / 3),) * 3)
    peaked_case = _case("peaked", logprobs=(0.0, float("-inf"), float("-inf")))
    scores = UncertaintyEntropyAcquisition().score(
        candidates=[uniform_case, peaked_case], rng=rng
    )
    assert scores[0] > scores[1]


def test_conformal_set_size_is_float_of_set_size() -> None:
    rng = random.Random(0)
    scores = ConformalSetSizeAcquisition().score(
        candidates=[_case("c-1", set_size=1), _case("c-2", set_size=5)], rng=rng
    )
    assert scores == [1.0, 5.0]


def test_coverage_gap_zero_when_truth_in_set() -> None:
    rng = random.Random(0)
    scores = CoverageGapAcquisition().score(
        candidates=[
            _case("in", truth_in_set=True, coverage_target=0.9),
            _case("out", truth_in_set=False, coverage_target=0.9),
        ],
        rng=rng,
    )
    # truth_in_set=True → 0; truth_in_set=False → 1 - 0.9 = 0.1.
    assert scores == [0.0, pytest.approx(0.1)]


def test_coverage_gap_zero_when_truth_unknown() -> None:
    # Production cases (truth_in_set=None) should score 0 so they fall
    # to the bottom of a coverage-gap ranking.
    rng = random.Random(0)
    scores = CoverageGapAcquisition().score(
        candidates=[_case("unknown", truth_in_set=None)], rng=rng
    )
    assert scores == [0.0]


def test_clinical_harm_weighted_multiplies_entropy_by_harm() -> None:
    rng = random.Random(0)
    # Both cases have identical entropy; stratum differs.
    lp = (math.log(1 / 3),) * 3
    scores = ClinicalHarmWeightedAcquisition().score(
        candidates=[
            _case("dosing-case", stratum="dosing", logprobs=lp),
            _case("general-case", stratum="general", logprobs=lp),
        ],
        rng=rng,
    )
    assert scores[0] == pytest.approx(math.log(3) * HARM_WEIGHTS["dosing"])
    assert scores[1] == pytest.approx(math.log(3) * HARM_WEIGHTS["general"])
    assert scores[0] > scores[1]


def test_clinical_harm_weighted_unknown_stratum_uses_default() -> None:
    rng = random.Random(0)
    lp = (math.log(1 / 3),) * 3
    scores = ClinicalHarmWeightedAcquisition().score(
        candidates=[
            _case("unknown-stratum", stratum="not-a-known-stratum", logprobs=lp)
        ],
        rng=rng,
    )
    # Falls back to weight 1.0.
    assert scores[0] == pytest.approx(math.log(3) * 1.0)


# ---- top_k ----


def test_top_k_picks_highest_scores() -> None:
    cs = [_case("a"), _case("b"), _case("c")]
    scores = [1.0, 3.0, 2.0]
    picked = top_k(candidates=cs, scores=scores, k=2)
    assert [c.case_id for c in picked] == ["b", "c"]


def test_top_k_is_stable_on_ties() -> None:
    cs = [_case("b"), _case("a"), _case("c")]
    scores = [1.0, 1.0, 1.0]
    picked = top_k(candidates=cs, scores=scores, k=2)
    # Sort by case_id ascending when tied.
    assert [c.case_id for c in picked] == ["a", "b"]


def test_top_k_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        top_k(candidates=[_case()], scores=[1.0, 2.0], k=1)


def test_top_k_rejects_negative_k() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        top_k(candidates=[_case()], scores=[1.0], k=-1)


def test_top_k_zero_returns_empty() -> None:
    assert top_k(candidates=[_case()], scores=[1.0], k=0) == []
