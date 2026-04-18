"""Tests for rubric value objects and row_hash chain."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from labeling.rubric import (
    RUBRIC_DIMENSIONS,
    SCALE_MAX,
    SCALE_MIN,
    RubricScores,
    build_grade,
    compute_row_hash,
    grade_to_row_dict,
)


def _fixed_now() -> datetime:
    return datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)


# ---- RubricScores ----


def test_rubric_scores_accepts_valid_range() -> None:
    scores = RubricScores(
        accuracy=1,
        safety=5,
        guideline_alignment=3,
        local_appropriateness=4,
        clarity=2,
    )
    assert scores.accuracy == 1
    assert scores.safety == 5


def test_rubric_scores_rejects_below_min() -> None:
    with pytest.raises(ValueError, match="accuracy=0 out of range"):
        RubricScores(
            accuracy=0,
            safety=3,
            guideline_alignment=3,
            local_appropriateness=3,
            clarity=3,
        )


def test_rubric_scores_rejects_above_max() -> None:
    with pytest.raises(ValueError, match="safety=6 out of range"):
        RubricScores(
            accuracy=3,
            safety=6,
            guideline_alignment=3,
            local_appropriateness=3,
            clarity=3,
        )


def test_rubric_scores_rejects_non_int() -> None:
    with pytest.raises(ValueError, match="accuracy must be int"):
        RubricScores(
            accuracy=3.5,  # type: ignore[arg-type]
            safety=3,
            guideline_alignment=3,
            local_appropriateness=3,
            clarity=3,
        )


def test_rubric_scores_rejects_bool() -> None:
    # bool is an int subclass in Python; we reject it explicitly so
    # True/False don't silently become 1/0.
    with pytest.raises(ValueError, match="accuracy must be int"):
        RubricScores(
            accuracy=True,  # type: ignore[arg-type]
            safety=3,
            guideline_alignment=3,
            local_appropriateness=3,
            clarity=3,
        )


def test_rubric_dimensions_match_env_spec() -> None:
    # env/labeling.env declares these exact five, in this order.
    assert RUBRIC_DIMENSIONS == (
        "accuracy",
        "safety",
        "guideline_alignment",
        "local_appropriateness",
        "clarity",
    )


def test_scale_bounds() -> None:
    assert SCALE_MIN == 1
    assert SCALE_MAX == 5


# ---- row_hash ----


def _scores() -> RubricScores:
    return RubricScores(
        accuracy=4,
        safety=5,
        guideline_alignment=4,
        local_appropriateness=3,
        clarity=4,
    )


def test_row_hash_is_deterministic() -> None:
    kwargs = dict(
        grade_id="g-1",
        case_id="c-1",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=_scores(),
        notes="",
        time_spent_seconds=90,
        submitted_at=_fixed_now(),
        prev_hash="",
    )
    h1 = compute_row_hash(**kwargs)  # type: ignore[arg-type]
    h2 = compute_row_hash(**kwargs)  # type: ignore[arg-type]
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_row_hash_changes_on_score_change() -> None:
    base_kwargs = dict(
        grade_id="g-1",
        case_id="c-1",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=_scores(),
        notes="",
        time_spent_seconds=90,
        submitted_at=_fixed_now(),
        prev_hash="",
    )
    h_base = compute_row_hash(**base_kwargs)  # type: ignore[arg-type]

    altered_scores = RubricScores(
        accuracy=4,
        safety=5,
        guideline_alignment=4,
        local_appropriateness=3,
        clarity=3,  # changed from 4
    )
    h_altered = compute_row_hash(
        **{**base_kwargs, "scores": altered_scores}  # type: ignore[arg-type]
    )
    assert h_base != h_altered


def test_row_hash_requires_tz_aware_datetime() -> None:
    naive = datetime(2026, 4, 18, 12, 0, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_row_hash(
            grade_id="g-1",
            case_id="c-1",
            reviewer_id="u-1",
            reviewer_role="clinical_reviewer",
            rubric_version="v1",
            scores=_scores(),
            notes="",
            time_spent_seconds=90,
            submitted_at=naive,
            prev_hash="",
        )


def test_row_hash_chains_prev_hash() -> None:
    # Two consecutive grades: second's prev_hash = first's row_hash.
    # Changing first's scores should cascade into second's row_hash via
    # the chain.
    first_scores = _scores()
    g1 = build_grade(
        grade_id="g-1",
        case_id="c-1",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=first_scores,
        notes="",
        time_spent_seconds=90,
        submitted_at=_fixed_now(),
        prev_hash="",
    )
    g2 = build_grade(
        grade_id="g-2",
        case_id="c-2",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=_scores(),
        notes="",
        time_spent_seconds=120,
        submitted_at=_fixed_now(),
        prev_hash=g1.row_hash,
    )
    assert g2.prev_hash == g1.row_hash

    tampered_first_scores = RubricScores(
        accuracy=1,  # was 4
        safety=5,
        guideline_alignment=4,
        local_appropriateness=3,
        clarity=4,
    )
    g1_tampered = build_grade(
        grade_id="g-1",
        case_id="c-1",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=tampered_first_scores,
        notes="",
        time_spent_seconds=90,
        submitted_at=_fixed_now(),
        prev_hash="",
    )
    assert g1_tampered.row_hash != g1.row_hash


# ---- Grade validation ----


def test_grade_rejects_negative_time_spent() -> None:
    with pytest.raises(ValueError, match="time_spent_seconds"):
        build_grade(
            grade_id="g-1",
            case_id="c-1",
            reviewer_id="u-1",
            reviewer_role="clinical_reviewer",
            rubric_version="v1",
            scores=_scores(),
            notes="",
            time_spent_seconds=-1,
            submitted_at=_fixed_now(),
            prev_hash="",
        )


def test_grade_rejects_long_notes() -> None:
    with pytest.raises(ValueError, match="notes"):
        build_grade(
            grade_id="g-1",
            case_id="c-1",
            reviewer_id="u-1",
            reviewer_role="clinical_reviewer",
            rubric_version="v1",
            scores=_scores(),
            notes="x" * 2001,
            time_spent_seconds=60,
            submitted_at=_fixed_now(),
            prev_hash="",
        )


def test_grade_to_row_dict_flattens_scores() -> None:
    grade = build_grade(
        grade_id="g-1",
        case_id="c-1",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=_scores(),
        notes="ok",
        time_spent_seconds=60,
        submitted_at=_fixed_now(),
        prev_hash="",
    )
    row = grade_to_row_dict(grade)
    assert row["accuracy"] == 4
    assert row["safety"] == 5
    assert row["clarity"] == 4
    assert "scores" not in row
    assert row["row_hash"] == grade.row_hash
