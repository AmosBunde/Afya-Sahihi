"""Mathematical unit tests for the 5 nonconformity score functions.

Every function has a fixed-input → fixed-output test (so a later
optimization cannot drift the value silently) plus a fail-closed test
(missing required signal → +inf).
"""

from __future__ import annotations

import math

import pytest

from conformal.scores import (
    ScoreInputs,
    compute_score,
    score_clinical_harm_weighted,
    score_ensemble_disagreement,
    score_nll,
    score_retrieval_weighted,
    score_topic_coherence_adjusted,
)
from conformal.settings import ConformalSettings


def _settings() -> ConformalSettings:
    return ConformalSettings(pg_host="localhost", pg_password="x")


# ---- NLL ----


def test_nll_from_logprob() -> None:
    # avg_logprob of -0.5 → NLL of 0.5
    assert score_nll(ScoreInputs(avg_logprob=-0.5)) == pytest.approx(0.5)


def test_nll_fail_closed_on_none() -> None:
    assert score_nll(ScoreInputs(avg_logprob=None)) == math.inf


def test_nll_fail_closed_on_nan() -> None:
    assert score_nll(ScoreInputs(avg_logprob=float("nan"))) == math.inf


# ---- Retrieval-weighted ----


def test_retrieval_weighted_divides_nll_by_similarity() -> None:
    # NLL 1.0 / top1 0.5 = 2.0
    s = score_retrieval_weighted(ScoreInputs(avg_logprob=-1.0, top1_similarity=0.5))
    assert s == pytest.approx(2.0)


def test_retrieval_weighted_fail_closed_on_missing_similarity() -> None:
    assert score_retrieval_weighted(ScoreInputs(avg_logprob=-0.5, top1_similarity=None)) == math.inf


def test_retrieval_weighted_fail_closed_on_zero_similarity() -> None:
    assert score_retrieval_weighted(ScoreInputs(avg_logprob=-0.5, top1_similarity=0.0)) == math.inf


# ---- Topic-coherence-adjusted ----


def test_topic_coherence_no_op_at_score_one() -> None:
    # NLL 0.5 * (2 - 1.0) = 0.5
    s = score_topic_coherence_adjusted(ScoreInputs(avg_logprob=-0.5, topic_score=1.0))
    assert s == pytest.approx(0.5)


def test_topic_coherence_doubles_at_score_zero() -> None:
    # NLL 0.5 * (2 - 0.0) = 1.0
    s = score_topic_coherence_adjusted(ScoreInputs(avg_logprob=-0.5, topic_score=0.0))
    assert s == pytest.approx(1.0)


def test_topic_coherence_clamps_above_one() -> None:
    # topic_score 1.5 bounded to 1.0 → factor 1.0
    s = score_topic_coherence_adjusted(ScoreInputs(avg_logprob=-0.5, topic_score=1.5))
    assert s == pytest.approx(0.5)


def test_topic_coherence_fail_closed_on_missing() -> None:
    assert (
        score_topic_coherence_adjusted(ScoreInputs(avg_logprob=-0.5, topic_score=None)) == math.inf
    )


# ---- Ensemble disagreement ----


def test_ensemble_disagreement_stdev_of_samples() -> None:
    # stdev of [-1.0, -1.0, -1.0] = 0.0
    s = score_ensemble_disagreement(ScoreInputs(sample_avg_logprobs=(-1.0, -1.0, -1.0)))
    assert s == pytest.approx(0.0)


def test_ensemble_disagreement_positive_on_variance() -> None:
    # stdev of [-0.5, -1.0, -1.5] = 0.5 (sample stdev)
    s = score_ensemble_disagreement(ScoreInputs(sample_avg_logprobs=(-0.5, -1.0, -1.5)))
    assert s == pytest.approx(0.5)


def test_ensemble_disagreement_fail_closed_one_sample() -> None:
    assert score_ensemble_disagreement(ScoreInputs(sample_avg_logprobs=(-0.5,))) == math.inf


def test_ensemble_disagreement_fail_closed_empty() -> None:
    assert score_ensemble_disagreement(ScoreInputs()) == math.inf


# ---- Clinical harm-weighted ----


def test_clinical_harm_catastrophic_weight() -> None:
    # NLL 1.0 * 10.0 (catastrophic) = 10.0
    s = score_clinical_harm_weighted(
        ScoreInputs(avg_logprob=-1.0, classified_intent="dosing"),
        settings=_settings(),
    )
    assert s == pytest.approx(10.0)


def test_clinical_harm_moderate_weight() -> None:
    s = score_clinical_harm_weighted(
        ScoreInputs(avg_logprob=-1.0, classified_intent="malaria_treatment"),
        settings=_settings(),
    )
    assert s == pytest.approx(1.0)


def test_clinical_harm_minor_weight() -> None:
    s = score_clinical_harm_weighted(
        ScoreInputs(avg_logprob=-1.0, classified_intent="patient_education"),
        settings=_settings(),
    )
    assert s == pytest.approx(0.3)


def test_clinical_harm_unknown_intent_falls_back_to_moderate() -> None:
    # SKILL.md §0.1: under-weighting is the failure mode that harms
    # patients. Unknown → moderate, not minor.
    s = score_clinical_harm_weighted(
        ScoreInputs(avg_logprob=-1.0, classified_intent="some_new_intent"),
        settings=_settings(),
    )
    assert s == pytest.approx(1.0)


def test_clinical_harm_none_intent_falls_back_to_moderate() -> None:
    s = score_clinical_harm_weighted(
        ScoreInputs(avg_logprob=-1.0, classified_intent=None),
        settings=_settings(),
    )
    assert s == pytest.approx(1.0)


def test_clinical_harm_requires_settings() -> None:
    with pytest.raises(ValueError, match="requires settings"):
        score_clinical_harm_weighted(
            ScoreInputs(avg_logprob=-1.0, classified_intent="dosing"),
            settings=None,
        )


# ---- Dispatcher ----


def test_compute_score_dispatches_by_name() -> None:
    inputs = ScoreInputs(avg_logprob=-0.5, top1_similarity=0.5)
    assert compute_score("nll", inputs) == pytest.approx(0.5)
    assert compute_score("retrieval_weighted", inputs) == pytest.approx(1.0)


def test_compute_score_rejects_unknown() -> None:
    with pytest.raises(KeyError):
        compute_score("nonexistent", ScoreInputs(avg_logprob=-0.5))  # type: ignore[arg-type]
