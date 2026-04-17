"""Evaluation harness for the prefilter classifier.

Computes intent classification F1 (macro-averaged) and safety-flag
recall on the held-out validation set. Reports are printed as
structured JSON and written to `{output_dir}/eval_report.json`.

The targets (F1 > 0.85, safety recall > 0.95) are from ADR-0007 and
issue #17. The report includes per-intent F1 so the research team can
identify which intents drag the macro average down.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from training.prefilter.data import LabeledQuery


@dataclass(frozen=True, slots=True)
class EvalReport:
    """Evaluation metrics for one model checkpoint."""

    intent_f1_macro: float
    safety_recall: float
    safety_precision: float
    n_val: int
    per_intent_f1: dict[str, float]
    meets_targets: bool


def evaluate(
    *,
    predictions: list[dict[str, object]],
    ground_truth: tuple[LabeledQuery, ...],
    target_f1: float,
    target_safety_recall: float,
    output_dir: str | None = None,
) -> EvalReport:
    """Compare predicted intents + safety flags against ground truth.

    `predictions` must be a list of dicts with keys `intent` (str) and
    `safety_flag` (bool), one per element in `ground_truth`, same order.
    """
    if len(predictions) != len(ground_truth):
        raise ValueError(f"predictions ({len(predictions)}) != ground_truth ({len(ground_truth)})")

    # Intent F1 (macro)
    intents_true = [gt.intent for gt in ground_truth]
    intents_pred = [str(p["intent"]) for p in predictions]
    labels = sorted(set(intents_true))
    per_intent = {}
    for label in labels:
        tp = sum(
            1 for t, p in zip(intents_true, intents_pred, strict=False) if t == label and p == label
        )
        fp = sum(
            1 for t, p in zip(intents_true, intents_pred, strict=False) if t != label and p == label
        )
        fn = sum(
            1 for t, p in zip(intents_true, intents_pred, strict=False) if t == label and p != label
        )
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_intent[label] = round(f1, 4)

    macro_f1 = sum(per_intent.values()) / len(per_intent) if per_intent else 0.0

    # Safety recall + precision
    safety_true = [gt.safety_flag for gt in ground_truth]
    safety_pred = [bool(p.get("safety_flag", False)) for p in predictions]
    safety_tp = sum(1 for t, p in zip(safety_true, safety_pred, strict=False) if t and p)
    safety_fp = sum(1 for t, p in zip(safety_true, safety_pred, strict=False) if not t and p)
    safety_fn = sum(1 for t, p in zip(safety_true, safety_pred, strict=False) if t and not p)
    safety_recall = safety_tp / (safety_tp + safety_fn) if (safety_tp + safety_fn) > 0 else 1.0
    safety_precision = safety_tp / (safety_tp + safety_fp) if (safety_tp + safety_fp) > 0 else 1.0

    report = EvalReport(
        intent_f1_macro=round(macro_f1, 4),
        safety_recall=round(safety_recall, 4),
        safety_precision=round(safety_precision, 4),
        n_val=len(ground_truth),
        per_intent_f1=per_intent,
        meets_targets=macro_f1 >= target_f1 and safety_recall >= target_safety_recall,
    )

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        with (out / "eval_report.json").open("w") as f:
            json.dump(
                {
                    "intent_f1_macro": report.intent_f1_macro,
                    "safety_recall": report.safety_recall,
                    "safety_precision": report.safety_precision,
                    "n_val": report.n_val,
                    "per_intent_f1": report.per_intent_f1,
                    "meets_targets": report.meets_targets,
                },
                f,
                indent=2,
            )

    return report
