"""Tests for the Streamlit shell's pure-python wiring.

We don't import streamlit here — everything that depends on it is
shaped to accept `st` as a parameter, or sits behind a `_bootstrap`
call that's only run at Streamlit runtime.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from labeling.app import (
    RubricSubmission,
    extract_bearer_token,
    resolve_reviewer,
)
from labeling.auth import UnauthorizedError
from labeling.jwt_validator import InvalidTokenError


# ---- extract_bearer_token ----


def test_extract_bearer_token_happy_path() -> None:
    assert (
        extract_bearer_token({"Authorization": "Bearer abc.def.ghi"}) == "abc.def.ghi"
    )


def test_extract_bearer_token_lowercase_header() -> None:
    assert extract_bearer_token({"authorization": "Bearer xyz"}) == "xyz"


def test_extract_bearer_token_missing_returns_empty() -> None:
    assert extract_bearer_token({}) == ""


def test_extract_bearer_token_non_bearer_returns_empty() -> None:
    assert extract_bearer_token({"Authorization": "Basic foo"}) == ""


# ---- resolve_reviewer: dev mode (no validator) ----


def test_resolve_reviewer_dev_mode_happy_path() -> None:
    headers = {
        "X-Forwarded-Claims": json.dumps(
            {"sub": "u-1", "role": "clinical_reviewer", "name": "Ada"}
        )
    }
    reviewer = resolve_reviewer(headers=headers, validator=None)
    assert reviewer.user_id == "u-1"
    assert reviewer.display_name == "Ada"


def test_resolve_reviewer_dev_mode_missing_header_refuses() -> None:
    with pytest.raises(UnauthorizedError, match="X-Forwarded-Claims"):
        resolve_reviewer(headers={}, validator=None)


def test_resolve_reviewer_dev_mode_malformed_json_refuses() -> None:
    with pytest.raises(UnauthorizedError, match="JSON"):
        resolve_reviewer(headers={"X-Forwarded-Claims": "not-json{"}, validator=None)


def test_resolve_reviewer_dev_mode_non_dict_json_refuses() -> None:
    with pytest.raises(UnauthorizedError, match="JSON object"):
        resolve_reviewer(
            headers={"X-Forwarded-Claims": json.dumps([1, 2, 3])},
            validator=None,
        )


def test_resolve_reviewer_dev_mode_bad_role_refuses() -> None:
    headers = {"X-Forwarded-Claims": json.dumps({"sub": "u-1", "role": "admin"})}
    with pytest.raises(UnauthorizedError, match="role"):
        resolve_reviewer(headers=headers, validator=None)


# ---- resolve_reviewer: production (with validator) ----


class FakeValidator:
    def __init__(self, claims: dict[str, object] | Exception) -> None:
        self._result = claims

    def validate(self, token: str) -> dict[str, object]:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_resolve_reviewer_prod_mode_happy_path() -> None:
    validator: Any = FakeValidator(
        {"sub": "u-2", "role": "senior_clinician", "name": "Wanjiru"}
    )
    reviewer = resolve_reviewer(
        headers={"Authorization": "Bearer validtoken"},
        validator=validator,
    )
    assert reviewer.user_id == "u-2"
    assert reviewer.role == "senior_clinician"


def test_resolve_reviewer_prod_mode_missing_bearer_refuses() -> None:
    validator: Any = FakeValidator({"sub": "u-1", "role": "clinical_reviewer"})
    with pytest.raises(UnauthorizedError, match="Bearer"):
        resolve_reviewer(headers={}, validator=validator)


def test_resolve_reviewer_prod_mode_invalid_token_refuses() -> None:
    validator: Any = FakeValidator(InvalidTokenError("expired"))
    with pytest.raises(UnauthorizedError, match="invalid token"):
        resolve_reviewer(
            headers={"Authorization": "Bearer expiredtoken"},
            validator=validator,
        )


def test_resolve_reviewer_prod_mode_bad_role_refuses() -> None:
    validator: Any = FakeValidator({"sub": "u-1", "role": "admin"})
    with pytest.raises(UnauthorizedError, match="role"):
        resolve_reviewer(
            headers={"Authorization": "Bearer token"},
            validator=validator,
        )


# ---- RubricSubmission shape ----


def test_rubric_submission_carries_scrubbed_notes() -> None:
    # Smoke: just verify the dataclass is importable and holds both fields.
    from labeling.rubric import RubricScores

    sub = RubricSubmission(
        scores=RubricScores(
            accuracy=4,
            safety=5,
            guideline_alignment=4,
            local_appropriateness=3,
            clarity=4,
        ),
        notes="No PHI here.",
    )
    assert sub.notes == "No PHI here."
    assert sub.scores.accuracy == 4
