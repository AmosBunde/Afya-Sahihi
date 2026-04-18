"""Prediction-set construction invariants."""

from __future__ import annotations

import math

from conformal.predictor import Candidate, construct_prediction_set


def test_empty_candidates_unmet_coverage() -> None:
    result = construct_prediction_set(candidates=[], q_hat=1.0, stratum="x")
    assert result.set_size == 0
    assert result.target_coverage_met is False
    assert result.top_score == math.inf


def test_all_candidates_below_q_hat_included() -> None:
    candidates = [Candidate("a", 0.1), Candidate("b", 0.5), Candidate("c", 0.9)]
    result = construct_prediction_set(candidates=candidates, q_hat=1.0, stratum="x")
    assert result.labels == ("a", "b", "c")
    assert result.target_coverage_met is True


def test_candidates_above_q_hat_excluded() -> None:
    candidates = [Candidate("a", 0.1), Candidate("b", 1.5)]
    result = construct_prediction_set(candidates=candidates, q_hat=1.0, stratum="x")
    assert result.labels == ("a",)
    assert result.set_size == 1


def test_non_finite_scores_excluded() -> None:
    candidates = [
        Candidate("a", 0.1),
        Candidate("b", math.inf),
        Candidate("c", float("nan")),
    ]
    result = construct_prediction_set(candidates=candidates, q_hat=1.0, stratum="x")
    assert result.labels == ("a",)


def test_order_preserved_in_output() -> None:
    candidates = [Candidate("z", 0.1), Candidate("a", 0.2), Candidate("m", 0.3)]
    result = construct_prediction_set(candidates=candidates, q_hat=1.0, stratum="x")
    # Order from input preserved (not alphabetically sorted)
    assert result.labels == ("z", "a", "m")
