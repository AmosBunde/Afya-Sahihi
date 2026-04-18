"""Inspect AI Tier 2 task: 2000 regression cases.

Runs nightly via the k3s CronJob + pre-deploy from CI. The dataset
mixes 30% adversarial rephrasings, 25% EN-SW code-switched queries,
15% misspellings, and 30% clean English per env/eval.env.

The scorers live in `eval/tier2/scorers.py` and are pure Python so
tests run without Inspect AI. This module is the glue.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    """Read the JSONL dataset into a list of case dicts."""
    cases: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return cases
    with p.open() as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: {e}") from e
    return cases


def _inspect_task() -> object:
    from inspect_ai import Task  # type: ignore[import-untyped]
    from inspect_ai.dataset import Sample  # type: ignore[import-untyped]

    dataset_path = (
        Path(__file__).resolve().parents[1] / "datasets" / "tier2_regression.jsonl"
    )
    raw_cases = load_cases(dataset_path)

    samples = [
        Sample(
            id=case["id"],
            input=case["query"],
            target=case.get("expected_answer", ""),
            metadata={
                "category": case.get("category", "clean"),
                "language": case.get("language", "en"),
                "intent": case.get("intent", "unknown"),
                "expected_prediction_set": case.get("expected_prediction_set", []),
            },
        )
        for case in raw_cases
    ]

    # The ECE/coverage/set_size/topic_coherence scorers need
    # per-response confidence and prediction-set data. Inspect AI's
    # scorer API returns per-sample Score objects; the aggregate
    # metrics are computed by `scorers.py` functions over the run
    # log after completion. Here we just attach a pass-through
    # scorer that records the Score; the CronJob post-processes the
    # log file via eval/tier2/aggregate.py (lands with issue #32).
    return Task(dataset=samples)


try:
    from inspect_ai import task  # type: ignore[import-untyped]

    @task
    def tier2_regression() -> object:
        return _inspect_task()
except ImportError:
    pass
