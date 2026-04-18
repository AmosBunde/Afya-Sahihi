"""Key-fact exact-match scorer for Tier 1 golden-set evaluation.

Each Tier 1 case has a `key_facts` dict with the clinical
particulars that MUST appear in a correct response:

    {
        "drug": "artemether-lumefantrine",
        "dose": "20/120 mg",
        "route": "oral",
        "frequency": "twice daily",
        "duration": "3 days"
    }

A response passes only when every required key-fact appears in the
text after normalization (lowercase, whitespace-collapsed, accent-
stripped). Partial matches do not count — missing one key fact on a
dosing question is the class of error that harms patients, per
SKILL.md §0.

The module is pure Python so tests run without Inspect AI installed.
`golden_set.py` glues this scorer into the Inspect AI task.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KeyFactResult:
    """Per-case outcome from scoring one response."""

    passed: bool
    matched_facts: tuple[str, ...]
    missed_facts: tuple[str, ...]
    n_required: int


def normalize(text: str) -> str:
    """Collapse casing, whitespace, accents for comparison.

    Keeps numeric and dose tokens literal (critical for clinical
    accuracy): "20 mg" stays "20 mg", not "20mg" or "twenty milligrams".
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def score_response(
    *,
    response: str,
    key_facts: dict[str, str],
) -> KeyFactResult:
    """Check that every required key-fact value appears in the response.

    `key_facts` maps fact name (drug/dose/route/...) to expected value.
    A fact is considered matched when its normalized value is a
    substring of the normalized response. Missing values (None, empty)
    are excluded from the required set — a case that doesn't specify
    a duration doesn't require one in the response.
    """
    required = {k: v for k, v in key_facts.items() if v}
    if not required:
        return KeyFactResult(
            passed=True,
            matched_facts=(),
            missed_facts=(),
            n_required=0,
        )

    normalized_response = normalize(response)

    matched: list[str] = []
    missed: list[str] = []
    for fact_name, expected in required.items():
        expected_norm = normalize(expected)
        if expected_norm in normalized_response:
            matched.append(fact_name)
        else:
            missed.append(fact_name)

    return KeyFactResult(
        passed=len(missed) == 0,
        matched_facts=tuple(matched),
        missed_facts=tuple(missed),
        n_required=len(required),
    )


def pass_rate(results: list[KeyFactResult]) -> float:
    """Fraction of cases that passed (every required key-fact matched)."""
    if not results:
        return 0.0
    return sum(1 for r in results if r.passed) / len(results)


def meets_threshold(pass_rate_val: float, threshold: float) -> bool:
    """Gate: does the observed pass rate meet or exceed the threshold?"""
    return pass_rate_val >= threshold
