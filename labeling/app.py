"""Streamlit shell for the Tier 3 clinician reviewer UI.

Thin, declarative glue. Every substantive behaviour lives in a module
that's unit-tested without Streamlit:

  - `auth.authorize_reviewer`          — OIDC claim → role gate
  - `jwt_validator.validate_oidc_jwt`  — JWKS signature / aud / iss check
  - `queue.ReviewerCaseQueue`          — Redis reserve/release/complete
  - `repository.insert_next_grade`     — chained grade insert (one txn)
  - `rubric.build_grade`               — row_hash assembly
  - `pdf_viewer.build_viewer_url`      — iframe deep-link builder
  - `phi.scrub`                        — PHI scrubber (fails closed)
  - `kappa.fleiss_kappa`               — agreement metric (cron-only)

`main()` wires these together. Streamlit runs this module top-to-bottom
on every interaction; we call `main(st, request_headers)` from the
script body (guarded) so the auth gate fires before any UI renders.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from labeling.auth import AuthorizedReviewer, UnauthorizedError, authorize_reviewer
from labeling.jwt_validator import InvalidTokenError, OidcValidator
from labeling.pdf_viewer import BoundingBox, build_viewer_url
from labeling.phi import scrub
from labeling.rubric import RUBRIC_DIMENSIONS, SCALE_MAX, SCALE_MIN, RubricScores

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RubricSubmission:
    scores: RubricScores
    notes: str


def render_forbidden(st: Any, reason: str) -> None:
    """Show a 403-equivalent page for users without the reviewer role."""
    st.set_page_config(page_title="Afya Sahihi — Labeling")
    st.title("Access denied")
    st.error(
        "You do not have permission to grade cases. "
        "Contact your clinical lead to be assigned the reviewer role."
    )
    st.caption(f"Reason: {reason}")


def extract_bearer_token(headers: dict[str, str]) -> str:
    """Pull the Bearer token from the Authorization header. '' if absent."""
    raw = headers.get("Authorization") or headers.get("authorization") or ""
    if not raw.startswith("Bearer "):
        return ""
    return raw[7:]


def resolve_reviewer(
    *,
    headers: dict[str, str],
    validator: OidcValidator | None,
) -> AuthorizedReviewer:
    """Full auth pipeline: JWT → claims → role gate.

    If `validator` is None (dev mode, empty OIDC_ISSUER_URL), we fall
    back to parsing the pre-validated `X-Forwarded-Claims` header set
    by the gateway ingress — documented mode for environments where
    OIDC is not yet wired. In production the validator is always set.
    """
    if validator is None:
        raw = headers.get("X-Forwarded-Claims") or headers.get("x-forwarded-claims")
        if not raw:
            raise UnauthorizedError("no X-Forwarded-Claims header (dev mode)")
        try:
            claims = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UnauthorizedError("X-Forwarded-Claims not valid JSON") from exc
        if not isinstance(claims, dict):
            raise UnauthorizedError("X-Forwarded-Claims must be a JSON object")
        return authorize_reviewer(claims)

    token = extract_bearer_token(headers)
    if not token:
        raise UnauthorizedError("missing Bearer token")
    try:
        claims = validator.validate(token)
    except InvalidTokenError as exc:
        raise UnauthorizedError(f"invalid token: {exc}") from exc
    return authorize_reviewer(claims)


def render_rubric_form(
    st: Any,
    *,
    reviewer: AuthorizedReviewer,
    case_id: str,
) -> RubricSubmission | None:
    """Render the 5-dimension form. Returns scores + notes on submission.

    Every slider defaults to 3 (mid-scale) so the reviewer must act
    rather than rubber-stamp. Notes are scrubbed of PHI before being
    returned; a scrub failure surfaces as an error and blocks submit.
    """
    with st.form(f"rubric-{case_id}", clear_on_submit=True):
        st.subheader(f"Case {case_id}")
        st.caption(f"Reviewer: {reviewer.display_name} ({reviewer.role})")

        scores: dict[str, int] = {}
        for dim in RUBRIC_DIMENSIONS:
            scores[dim] = st.slider(
                label=dim.replace("_", " ").title(),
                min_value=SCALE_MIN,
                max_value=SCALE_MAX,
                value=3,
                key=f"{case_id}-{dim}",
            )
        notes_raw = st.text_area(
            "Notes (no PHI — will be automatically scrubbed)",
            max_chars=2000,
            key=f"{case_id}-notes",
        )
        submitted = st.form_submit_button("Submit grade")

    if not submitted:
        return None

    scrub_result = scrub(notes_raw)
    if scrub_result.failed:
        st.error("Notes could not be processed; please remove special characters.")
        logger.warning("notes scrub failed", extra={"reviewer_id": reviewer.user_id})
        return None
    if scrub_result.hits:
        logger.info(
            "notes redacted",
            extra={
                "reviewer_id": reviewer.user_id,
                "patterns": list(scrub_result.hits),
            },
        )

    logger.info(
        "rubric submitted",
        extra={"case_id": case_id, "reviewer_id": reviewer.user_id},
    )
    return RubricSubmission(
        scores=RubricScores(**scores),
        notes=scrub_result.scrubbed,
    )


def render_provenance_panel(
    st: Any,
    *,
    viewer_base_url: str,
    document_id: str,
    bbox_raw: dict[str, float] | None,
    highlight: bool,
) -> None:
    """Embed the provenance viewer in an iframe for the active case."""
    bbox = None
    if bbox_raw is not None:
        bbox = BoundingBox(
            page=int(bbox_raw["page"]),
            x0=float(bbox_raw["x0"]),
            y0=float(bbox_raw["y0"]),
            x1=float(bbox_raw["x1"]),
            y1=float(bbox_raw["y1"]),
        )
    url = build_viewer_url(
        base_url=viewer_base_url,
        document_id=document_id,
        bbox=bbox,
        highlight=highlight,
    )
    st.markdown(f"[Open PDF in new tab]({url})")
    st.components.v1.iframe(src=url, height=600, scrolling=True)


def main(
    st: Any,
    *,
    request_headers: dict[str, str],
    validator: OidcValidator | None,
) -> None:
    """Entry point. Resolves reviewer identity, dispatches views."""
    try:
        reviewer = resolve_reviewer(headers=request_headers, validator=validator)
    except UnauthorizedError as exc:
        render_forbidden(st, reason=str(exc))
        return

    st.set_page_config(page_title="Afya Sahihi — Grade cases", layout="wide")
    st.title("Afya Sahihi clinician review")
    st.caption(
        f"Signed in as {reviewer.display_name} ({reviewer.role}) · "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    )
    # The case-loading loop (queue.reserve_next → render form →
    # repository.insert_next_grade → queue.complete) is orchestrated
    # by `labeling.runner` (not yet wired — lands with the container
    # build in issue #34).
    st.info(
        "Fetch the next assigned case from the sidebar. "
        "Each grade is chained to your previous grade via a SHA-256 hash."
    )


def _bootstrap() -> None:  # pragma: no cover - runtime-only wiring
    """Streamlit runtime entry. Imports inside the function so unit tests
    that import `labeling.app` do not pull in streamlit."""
    import streamlit as st  # type: ignore[import-not-found]

    from labeling.settings import LabelingSettings

    settings = LabelingSettings()

    validator: OidcValidator | None = None
    if settings.oidc_issuer_url and settings.oidc_jwks_uri:
        validator = OidcValidator.from_uri(
            jwks_uri=settings.oidc_jwks_uri,
            issuer=settings.oidc_issuer_url,
            audience=settings.oidc_audience,
        )

    # Streamlit exposes incoming request headers via st.context.headers.
    headers: dict[str, str] = {}
    ctx_headers = getattr(getattr(st, "context", None), "headers", None)
    if ctx_headers is not None:
        headers = dict(ctx_headers)

    main(st, request_headers=headers, validator=validator)


if __name__ == "__main__":  # pragma: no cover
    # Streamlit runs `streamlit run labeling/app.py` which loads this
    # module with __name__ == "__main__" and re-executes top-to-bottom
    # on every user event. Unit tests import `labeling.app` (name !=
    # __main__) so the bootstrap does not fire during pytest.
    _bootstrap()
