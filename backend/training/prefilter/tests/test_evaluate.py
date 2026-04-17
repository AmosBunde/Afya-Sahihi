"""Tests for the prefilter evaluation harness. Pure Python, no GPU."""

from __future__ import annotations

from training.prefilter.data import LabeledQuery
from training.prefilter.evaluate import evaluate


def _gt(intent: str, safety: bool = False) -> LabeledQuery:
    return LabeledQuery(
        query_text="q",
        intent=intent,
        safety_flag=safety,
        language="en",
        source="test",
    )


def test_perfect_predictions_meet_targets() -> None:
    gt = (
        _gt("malaria", safety=True),
        _gt("tb", safety=False),
        _gt("hiv", safety=False),
    )
    preds = [
        {"intent": "malaria", "safety_flag": True},
        {"intent": "tb", "safety_flag": False},
        {"intent": "hiv", "safety_flag": False},
    ]
    report = evaluate(
        predictions=preds,
        ground_truth=gt,
        target_f1=0.85,
        target_safety_recall=0.95,
    )
    assert report.intent_f1_macro == 1.0
    assert report.safety_recall == 1.0
    assert report.meets_targets is True


def test_all_wrong_intent_scores_zero() -> None:
    gt = (_gt("malaria"), _gt("tb"))
    preds = [{"intent": "hiv", "safety_flag": False}, {"intent": "hiv", "safety_flag": False}]
    report = evaluate(
        predictions=preds,
        ground_truth=gt,
        target_f1=0.85,
        target_safety_recall=0.95,
    )
    assert report.intent_f1_macro == 0.0
    assert report.meets_targets is False


def test_safety_recall_zero_when_all_missed() -> None:
    gt = (_gt("malaria", safety=True), _gt("tb", safety=True))
    preds = [
        {"intent": "malaria", "safety_flag": False},
        {"intent": "tb", "safety_flag": False},
    ]
    report = evaluate(
        predictions=preds,
        ground_truth=gt,
        target_f1=0.85,
        target_safety_recall=0.95,
    )
    assert report.safety_recall == 0.0
    assert report.meets_targets is False


def test_per_intent_f1_reported() -> None:
    gt = (_gt("malaria"), _gt("tb"), _gt("malaria"))
    preds = [
        {"intent": "malaria", "safety_flag": False},
        {"intent": "malaria", "safety_flag": False},
        {"intent": "malaria", "safety_flag": False},
    ]
    report = evaluate(
        predictions=preds,
        ground_truth=gt,
        target_f1=0.0,
        target_safety_recall=0.0,
    )
    assert "malaria" in report.per_intent_f1
    assert "tb" in report.per_intent_f1
    assert report.per_intent_f1["tb"] == 0.0
