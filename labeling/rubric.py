"""Rubric and grade value objects.

The rubric has five dimensions, each scored on a 1-5 integer scale
(Likert-like). A `Grade` bundles those five scores with chain-of-custody
fields (reviewer id, timestamps, row_hash) so downstream analysis can
detect tampering without trusting the application layer.

Pure value objects. No I/O. Tests in `tests/test_rubric.py`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Final

RUBRIC_DIMENSIONS: Final = (
    "accuracy",
    "safety",
    "guideline_alignment",
    "local_appropriateness",
    "clarity",
)
SCALE_MIN: Final = 1
SCALE_MAX: Final = 5


@dataclass(frozen=True, slots=True)
class RubricScores:
    """Per-dimension scores. Every dimension mandatory; enforced in __post_init__."""

    accuracy: int
    safety: int
    guideline_alignment: int
    local_appropriateness: int
    clarity: int

    def __post_init__(self) -> None:
        for dim in RUBRIC_DIMENSIONS:
            value = getattr(self, dim)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{dim} must be int, got {type(value).__name__}")
            if value < SCALE_MIN or value > SCALE_MAX:
                raise ValueError(
                    f"{dim}={value} out of range [{SCALE_MIN}, {SCALE_MAX}]"
                )

    def to_dict(self) -> dict[str, int]:
        return {dim: getattr(self, dim) for dim in RUBRIC_DIMENSIONS}


@dataclass(frozen=True, slots=True)
class Grade:
    """A single reviewer's grade for a single case, with chain-of-custody.

    `row_hash` is computed by `compute_row_hash` from the canonicalised
    payload plus `prev_hash`. Tampering with any field invalidates the
    hash chain — verifiable offline by re-running `compute_row_hash`.
    """

    grade_id: str
    case_id: str
    reviewer_id: str
    reviewer_role: str
    rubric_version: str
    scores: RubricScores
    notes: str  # Scrubbed of PHI before passing here.
    time_spent_seconds: int
    submitted_at: datetime
    prev_hash: str
    row_hash: str

    def __post_init__(self) -> None:
        if self.time_spent_seconds < 0:
            raise ValueError("time_spent_seconds must be >= 0")
        if len(self.notes) > 2000:
            raise ValueError("notes exceeds 2000 chars")


def compute_row_hash(
    *,
    grade_id: str,
    case_id: str,
    reviewer_id: str,
    reviewer_role: str,
    rubric_version: str,
    scores: RubricScores,
    notes: str,
    time_spent_seconds: int,
    submitted_at: datetime,
    prev_hash: str,
) -> str:
    """SHA-256 over the canonical payload. Deterministic.

    submitted_at is serialised as ISO-8601 UTC with microsecond precision.
    Any change to any input — including reordering scores — changes the
    hash, so the chain detects tampering at any field granularity.
    """
    if submitted_at.tzinfo is None:
        raise ValueError("submitted_at must be timezone-aware")
    payload = {
        "grade_id": grade_id,
        "case_id": case_id,
        "reviewer_id": reviewer_id,
        "reviewer_role": reviewer_role,
        "rubric_version": rubric_version,
        "scores": scores.to_dict(),
        "notes": notes,
        "time_spent_seconds": time_spent_seconds,
        "submitted_at": submitted_at.astimezone(timezone.utc).isoformat(
            timespec="microseconds"
        ),
        "prev_hash": prev_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_grade(
    *,
    grade_id: str,
    case_id: str,
    reviewer_id: str,
    reviewer_role: str,
    rubric_version: str,
    scores: RubricScores,
    notes: str,
    time_spent_seconds: int,
    submitted_at: datetime,
    prev_hash: str,
) -> Grade:
    """Construct a Grade with computed row_hash. Factory for callers."""
    row_hash = compute_row_hash(
        grade_id=grade_id,
        case_id=case_id,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        rubric_version=rubric_version,
        scores=scores,
        notes=notes,
        time_spent_seconds=time_spent_seconds,
        submitted_at=submitted_at,
        prev_hash=prev_hash,
    )
    return Grade(
        grade_id=grade_id,
        case_id=case_id,
        reviewer_id=reviewer_id,
        reviewer_role=reviewer_role,
        rubric_version=rubric_version,
        scores=scores,
        notes=notes,
        time_spent_seconds=time_spent_seconds,
        submitted_at=submitted_at,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )


def grade_to_row_dict(grade: Grade) -> dict[str, object]:
    """Flat dict for asyncpg INSERT. scores splatted into columns."""
    base = asdict(grade)
    scores = base.pop("scores")
    base.update(scores)
    return base
