"""Tests for the prefilter dataset loader. Pure Python, uses a temp JSONL."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from training.prefilter.config import PrefilterTrainConfig
from training.prefilter.data import load_dataset


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _rows(n: int = 200) -> list[dict[str, object]]:
    return [
        {
            "query_text": f"query {i}",
            "intent": f"intent_{i % 5}",
            "safety_flag": i % 7 == 0,
            "language": "en",
            "source": "test",
        }
        for i in range(n)
    ]


def test_load_splits_deterministically() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "train.jsonl"
        _write_jsonl(path, _rows(200))
        config = PrefilterTrainConfig(
            dataset_path=str(path),
            source_bucket="x",
            source_manifest_path="x",
            pg_host="x",
            pg_database="x",
            pg_user="x",
            pg_password="x",
        )
        split1 = load_dataset(config)
        split2 = load_dataset(config)

    assert len(split1.train) + len(split1.val) == 200
    assert split1.train[0].query_text == split2.train[0].query_text


def test_load_rejects_too_few_rows() -> None:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "train.jsonl"
        _write_jsonl(path, _rows(50))
        config = PrefilterTrainConfig(
            dataset_path=str(path),
            source_bucket="x",
            source_manifest_path="x",
            pg_host="x",
            pg_database="x",
            pg_user="x",
            pg_password="x",
        )
        with pytest.raises(ValueError, match="minimum 100"):
            load_dataset(config)


def test_load_raises_on_missing_file() -> None:
    config = PrefilterTrainConfig(
        dataset_path="/nonexistent/path.jsonl",
        source_bucket="x",
        source_manifest_path="x",
        pg_host="x",
        pg_database="x",
        pg_user="x",
        pg_password="x",
    )
    with pytest.raises(FileNotFoundError, match="not committed"):
        load_dataset(config)
