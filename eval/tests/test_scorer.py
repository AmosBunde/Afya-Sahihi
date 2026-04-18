"""Tests for the Tier 1 key-fact scorer. Pure Python."""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.tier1.golden_set import load_cases
from eval.tier1.scorer import (
    KeyFactResult,
    meets_threshold,
    normalize,
    pass_rate,
    score_response,
)


# ---- Normalization ----


def test_normalize_lowercases() -> None:
    assert normalize("ARTEMETHER") == "artemether"


def test_normalize_collapses_whitespace() -> None:
    assert normalize("twice   daily") == "twice daily"


def test_normalize_preserves_dose_tokens() -> None:
    # Critical: 20 mg must stay 20 mg, not 20mg or twenty mg.
    assert normalize("20 mg") == "20 mg"
    assert normalize("15 mg/kg") == "15 mg/kg"


def test_normalize_strips_accents() -> None:
    assert normalize("café") == "cafe"


# ---- Scorer ----


def test_score_all_key_facts_present_passes() -> None:
    result = score_response(
        response="Administer artemether-lumefantrine orally twice daily for 3 days.",
        key_facts={
            "drug": "artemether-lumefantrine",
            "route": "oral",
            "frequency": "twice daily",
            "duration": "3 days",
        },
    )
    assert result.passed is True
    assert result.missed_facts == ()
    assert result.n_required == 4


def test_score_missing_key_fact_fails() -> None:
    result = score_response(
        response="Administer artemether-lumefantrine orally for 3 days.",
        key_facts={
            "drug": "artemether-lumefantrine",
            "route": "oral",
            "frequency": "twice daily",  # missing
            "duration": "3 days",
        },
    )
    assert result.passed is False
    assert "frequency" in result.missed_facts


def test_score_empty_key_facts_passes() -> None:
    # Cases that don't specify any key facts (open-ended questions)
    # pass on any non-empty response.
    result = score_response(response="Any answer", key_facts={})
    assert result.passed is True
    assert result.n_required == 0


def test_score_empty_values_skipped() -> None:
    result = score_response(
        response="Give paracetamol.",
        key_facts={"drug": "paracetamol", "dose": "", "duration": None},  # type: ignore[dict-item]
    )
    assert result.passed is True
    assert result.n_required == 1


def test_score_case_insensitive() -> None:
    result = score_response(
        response="DOLUTEGRAVIR is first-line.",
        key_facts={"drug": "dolutegravir"},
    )
    assert result.passed is True


def test_score_partial_substring_counts() -> None:
    # "artemether-lumefantrine" appears inside a longer brand name —
    # substring match is the intended behavior.
    result = score_response(
        response="Use Coartem (artemether-lumefantrine 20/120 mg tablets).",
        key_facts={"drug": "artemether-lumefantrine"},
    )
    assert result.passed is True


# ---- Pass rate + threshold ----


def test_pass_rate_zero_on_empty() -> None:
    assert pass_rate([]) == 0.0


def test_pass_rate_fractional() -> None:
    results = [
        KeyFactResult(passed=True, matched_facts=(), missed_facts=(), n_required=0),
        KeyFactResult(passed=True, matched_facts=(), missed_facts=(), n_required=0),
        KeyFactResult(passed=False, matched_facts=(), missed_facts=(), n_required=1),
        KeyFactResult(passed=True, matched_facts=(), missed_facts=(), n_required=0),
    ]
    assert pass_rate(results) == pytest.approx(0.75)


def test_meets_threshold() -> None:
    assert meets_threshold(0.95, 0.95) is True
    assert meets_threshold(0.96, 0.95) is True
    assert meets_threshold(0.94, 0.95) is False


# ---- Dataset integration ----


_DATASET = Path(__file__).resolve().parents[1] / "datasets" / "tier1_golden.jsonl"


def test_seed_dataset_loads() -> None:
    cases = load_cases(_DATASET)
    assert len(cases) >= 20, f"seed dataset has {len(cases)} cases; need >= 20"


def test_seed_dataset_every_case_has_required_fields() -> None:
    cases = load_cases(_DATASET)
    for case in cases:
        assert "id" in case
        assert "query" in case
        assert "key_facts" in case
        assert "intent" in case


def test_seed_dataset_ids_unique() -> None:
    cases = load_cases(_DATASET)
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "duplicate ids in seed dataset"


def test_seed_dataset_passes_on_golden_response() -> None:
    """For every case, constructing a response from the key_facts
    concatenated should pass the scorer. This is a sanity check that
    the dataset shape and scorer agree."""
    cases = load_cases(_DATASET)
    for case in cases:
        key_facts = case["key_facts"]
        if not any(v for v in key_facts.values()):
            continue  # open-ended; skip
        golden_response = " ".join(str(v) for v in key_facts.values() if v)
        result = score_response(response=golden_response, key_facts=key_facts)
        assert result.passed, (
            f"case {case['id']} fails on golden response: "
            f"missed={result.missed_facts}"
        )
