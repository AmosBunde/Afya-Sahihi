"""Inspect AI Tier 1 task: 500 curated clinical cases.

Runs every commit via `scripts/hooks/run_tier1_evals.sh` (pre-push) and
the backend-tests CI job. Target runtime: < 120s. Acceptance: pass
rate >= 0.95 on the current model, AND no regression against the
baseline recorded in `eval/tier1/baseline.json`.

Dataset: `eval/datasets/tier1_golden.jsonl` — one JSON object per line
with fields: `id`, `query`, `key_facts`, `language`, `intent`.

The scorer lives in `eval/tier1/scorer.py` so tests can run without
Inspect AI. This file is the glue that Inspect AI discovers.
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
    """Construct the Inspect AI Task. Lazy-imported so pytest can import
    this module without inspect-ai installed.
    """
    from inspect_ai import Task  # type: ignore[import-untyped]
    from inspect_ai.dataset import Sample  # type: ignore[import-untyped]
    from inspect_ai.scorer import Score, Target, scorer  # type: ignore[import-untyped]
    from inspect_ai.scorer import accuracy  # type: ignore[import-untyped]
    from inspect_ai.solver import TaskState  # type: ignore[import-untyped]

    from eval.tier1.scorer import score_response

    dataset_path = (
        Path(__file__).resolve().parents[1] / "datasets" / "tier1_golden.jsonl"
    )
    raw_cases = load_cases(dataset_path)

    samples = [
        Sample(
            id=case["id"],
            input=case["query"],
            target=json.dumps(case.get("key_facts", {})),
            metadata={
                "language": case.get("language", "en"),
                "intent": case.get("intent", "unknown"),
                "key_facts": case.get("key_facts", {}),
            },
        )
        for case in raw_cases
    ]

    @scorer(metrics=[accuracy()])
    def key_fact_match():  # type: ignore[no-untyped-def]
        async def score(state: TaskState, target: Target) -> Score:
            key_facts = state.metadata.get("key_facts", {})
            result = score_response(
                response=state.output.completion,
                key_facts=key_facts,
            )
            return Score(
                value=1 if result.passed else 0,
                answer=state.output.completion[:500],
                explanation=(
                    f"matched: {list(result.matched_facts)}; "
                    f"missed: {list(result.missed_facts)}"
                ),
                metadata={
                    "matched_facts": list(result.matched_facts),
                    "missed_facts": list(result.missed_facts),
                    "n_required": result.n_required,
                },
            )

        return score

    return Task(
        dataset=samples,
        scorer=key_fact_match(),
    )


# Inspect AI looks for module-level functions decorated with @task.
# We guard the decorator behind the lazy import so pytest can collect
# this module without requiring inspect-ai.
try:
    from inspect_ai import task  # type: ignore[import-untyped]

    @task
    def tier1_golden_set() -> object:
        return _inspect_task()
except ImportError:
    # inspect-ai not installed (tests or pre-install). The scorer is
    # still importable and testable via eval/tier1/scorer.py.
    pass
