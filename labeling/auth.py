"""OIDC role gate for the labeling UI.

The gateway already validates the OIDC JWT (backend/app/api/middleware.py).
Streamlit sits behind the same ingress and receives the validated claims
via the `X-Forwarded-Claims` header the gateway sets for downstream
services. We re-validate the claims signature here because defence in
depth is cheap and the labeling app hosts PHI-adjacent data (grades that
reference case ids).

Only `clinical_reviewer` and `senior_clinician` roles may grade. A user
with neither role gets a 403-equivalent page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger(__name__)


ALLOWED_ROLES: Final = frozenset({"clinical_reviewer", "senior_clinician"})


@dataclass(frozen=True, slots=True)
class AuthorizedReviewer:
    """What the app needs from the JWT — no more, no less."""

    user_id: str
    role: str
    display_name: str


class UnauthorizedError(Exception):
    """Caller lacks a valid role. Mapped to 403 by the Streamlit shell."""


def authorize_reviewer(claims: dict[str, object]) -> AuthorizedReviewer:
    """Extract reviewer identity from JWT claims; fail closed on any gap.

    We require: `sub` (stable user id), a role in ALLOWED_ROLES, and a
    display name (`preferred_username` or `name`). Missing `sub` is a
    misconfigured IdP; we refuse rather than invent a synthetic id.
    """
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise UnauthorizedError("missing sub claim")

    role = _extract_role(claims)
    if role not in ALLOWED_ROLES:
        # Log user_id (opaque) but never log claim payload (may contain email).
        logger.info(
            "labeling access refused",
            extra={"user_id": sub, "reason": "role_not_allowed"},
        )
        raise UnauthorizedError(f"role {role!r} not in {sorted(ALLOWED_ROLES)}")

    display = claims.get("preferred_username") or claims.get("name") or sub
    if not isinstance(display, str):
        display = sub

    return AuthorizedReviewer(user_id=sub, role=role, display_name=display)


def _extract_role(claims: dict[str, object]) -> str:
    """Pull role from claims. Preference: `role` string, then `roles` list.

    Keycloak convention is `realm_access.roles` — we also support that
    format by flattening. Returns "" when no role present (triggers a
    refusal in the caller).
    """
    role = claims.get("role")
    if isinstance(role, str) and role:
        return role

    roles = claims.get("roles")
    if isinstance(roles, list):
        for r in roles:
            if isinstance(r, str) and r in ALLOWED_ROLES:
                return r

    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        realm_roles = realm_access.get("roles")
        if isinstance(realm_roles, list):
            for r in realm_roles:
                if isinstance(r, str) and r in ALLOWED_ROLES:
                    return r

    return ""
