"""Tests for the OIDC role gate."""

from __future__ import annotations

import pytest

from labeling.auth import ALLOWED_ROLES, UnauthorizedError, authorize_reviewer


def test_accepts_clinical_reviewer_via_role_claim() -> None:
    reviewer = authorize_reviewer(
        {"sub": "u-1", "role": "clinical_reviewer", "name": "Dr Ada"}
    )
    assert reviewer.user_id == "u-1"
    assert reviewer.role == "clinical_reviewer"
    assert reviewer.display_name == "Dr Ada"


def test_accepts_senior_clinician_via_roles_list() -> None:
    reviewer = authorize_reviewer(
        {
            "sub": "u-2",
            "roles": ["clinical_reviewer", "senior_clinician"],
            "preferred_username": "aneita@aku.edu",
        }
    )
    assert reviewer.role in ALLOWED_ROLES
    assert reviewer.display_name == "aneita@aku.edu"


def test_accepts_keycloak_realm_access_roles() -> None:
    reviewer = authorize_reviewer(
        {
            "sub": "u-3",
            "realm_access": {"roles": ["senior_clinician", "admin"]},
            "name": "Wanjiru",
        }
    )
    assert reviewer.role == "senior_clinician"


def test_refuses_missing_sub() -> None:
    with pytest.raises(UnauthorizedError, match="sub"):
        authorize_reviewer({"role": "clinical_reviewer"})


def test_refuses_empty_sub() -> None:
    with pytest.raises(UnauthorizedError, match="sub"):
        authorize_reviewer({"sub": "", "role": "clinical_reviewer"})


def test_refuses_non_string_sub() -> None:
    with pytest.raises(UnauthorizedError, match="sub"):
        authorize_reviewer({"sub": 42, "role": "clinical_reviewer"})


def test_refuses_role_not_in_allow_list() -> None:
    with pytest.raises(UnauthorizedError, match="role"):
        authorize_reviewer({"sub": "u-1", "role": "admin"})


def test_refuses_no_role_at_all() -> None:
    with pytest.raises(UnauthorizedError, match="role"):
        authorize_reviewer({"sub": "u-1"})


def test_falls_back_to_sub_when_no_display_name() -> None:
    reviewer = authorize_reviewer({"sub": "u-1", "role": "clinical_reviewer"})
    assert reviewer.display_name == "u-1"


def test_ignores_non_string_display_name() -> None:
    reviewer = authorize_reviewer(
        {"sub": "u-1", "role": "clinical_reviewer", "preferred_username": 42}
    )
    assert reviewer.display_name == "u-1"
