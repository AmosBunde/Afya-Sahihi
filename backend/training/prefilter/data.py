"""Dataset loader for the prefilter training set.

Expects JSONL at `config.dataset_path` with the schema documented in
eval/datasets/README.md. Each row:
    {
        "query_text": "...",
        "intent": "malaria_dosing",
        "safety_flag": false,
        "language": "en",
        "source": "aku_retrospective"
    }

Returns a train/val split deterministically seeded from config.seed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from training.prefilter.config import PrefilterTrainConfig


@dataclass(frozen=True, slots=True)
class LabeledQuery:
    """One labeled example."""

    query_text: str
    intent: str
    safety_flag: bool
    language: str
    source: str


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    """Train and val splits."""

    train: tuple[LabeledQuery, ...]
    val: tuple[LabeledQuery, ...]
    intent_labels: tuple[str, ...]


def load_dataset(config: PrefilterTrainConfig) -> DatasetSplit:
    """Load and split the labeled JSONL."""
    path = Path(config.dataset_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Training dataset not found at {path}. "
            "The dataset is produced from IRB-approved AKU retrospective "
            "logs and is not committed to the repo. See "
            "eval/datasets/README.md for the expected schema."
        )

    rows: list[LabeledQuery] = []
    with path.open() as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"line {line_no}: invalid JSON: {e}") from e
            rows.append(
                LabeledQuery(
                    query_text=d["query_text"],
                    intent=d["intent"],
                    safety_flag=bool(d.get("safety_flag", False)),
                    language=d.get("language", "en"),
                    source=d.get("source", "unknown"),
                )
            )

    if len(rows) < 100:
        raise ValueError(
            f"dataset has {len(rows)} rows; minimum 100 for meaningful " "cross-validation"
        )

    import random

    rng = random.Random(config.seed)  # nosec B311 — deterministic shuffle, not security
    rng.shuffle(rows)  # nosec B311

    split_idx = int(len(rows) * (1 - config.val_fraction))
    train = tuple(rows[:split_idx])
    val = tuple(rows[split_idx:])

    intent_labels = tuple(sorted({r.intent for r in rows}))

    return DatasetSplit(train=train, val=val, intent_labels=intent_labels)
