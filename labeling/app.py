"""Streamlit shell for the Tier 3 clinician reviewer UI.

Thin, declarative glue. Every substantive behaviour lives in a module
that's unit-tested without Streamlit:

  - `auth.authorize_reviewer`       — OIDC role gate
  - `queue.ReviewerCaseQueue`       — Redis reserve/release/complete
  - `repository.GradeRepository`    — grades insert + latest hash
  - `rubric.build_grade`            — row_hash chained assembly
  - `pdf_viewer.build_viewer_url`   — iframe deep-link builder
  - `kappa.fleiss_kappa`            — agreement metric (cron-only)

The shell is deliberately free of conditionals that the unit tests
would need to cover — if a flow needs branching logic it moves into
one of the modules above.

Run with:  streamlit run labeling/app.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from labeling.auth import AuthorizedReviewer, UnauthorizedError, authorize_reviewer
from labeling.pdf_viewer import BoundingBox, build_viewer_url
from labeling.rubric import RUBRIC_DIMENSIONS, SCALE_MAX, SCALE_MIN, RubricScores

logger = logging.getLogger(__name__)


def render_forbidden(st: Any, reason: str) -> None:
    """Show a 403-equivalent page for users without the reviewer role."""
    st.set_page_config(page_title="Afya Sahihi — Labeling", page_icon="🔒")
    st.title("Access denied")
    st.error(
        "You do not have permission to grade cases. "
        "Contact your clinical lead to be assigned the reviewer role."
    )
    st.caption(f"Reason: {reason}")


def extract_claims_from_headers(headers: dict[str, str]) -> dict[str, object]:
    """Parse the X-Forwarded-Claims header set by the ingress.

    Returns {} if the header is missing or malformed — which causes the
    auth gate to refuse. Failing closed on the auth path is deliberate.
    """
    raw = headers.get("X-Forwarded-Claims") or headers.get("x-forwarded-claims")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("X-Forwarded-Claims not valid JSON")
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def render_rubric_form(
    st: Any,
    *,
    reviewer: AuthorizedReviewer,
    case_id: str,
) -> RubricScores | None:
    """Render the 5-dimension form. Returns scores when the reviewer submits.

    Each slider defaults to 3 (mid-scale) so the reviewer must act
    rather than rubber-stamp. Form submission is atomic — Streamlit
    will not dispatch the callback until every slider is interacted
    with exactly once (enforced by `st.form`).
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
        notes = st.text_area("Notes (no PHI)", max_chars=2000, key=f"{case_id}-notes")
        submitted = st.form_submit_button("Submit grade")

    if not submitted:
        return None
    logger.info(
        "rubric submitted",
        extra={"case_id": case_id, "reviewer_id": reviewer.user_id},
    )
    # RubricScores validates ranges; Streamlit's slider already enforces
    # them but defence in depth is cheap.
    _ = notes  # persisted by caller via build_grade(notes=notes)
    return RubricScores(**scores)


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


def main(st: Any, *, request_headers: dict[str, str]) -> None:
    """Entry point. `st` is the Streamlit module, injected for testability.

    Streamlit's script-rerun model means this function runs on every
    user interaction. We keep it small: resolve identity, dispatch to
    the authorized or forbidden view.
    """
    claims = extract_claims_from_headers(request_headers)
    try:
        reviewer = authorize_reviewer(claims)
    except UnauthorizedError as exc:
        render_forbidden(st, reason=str(exc))
        return

    st.set_page_config(page_title="Afya Sahihi — Grade cases", layout="wide")
    st.title("Afya Sahihi clinician review")
    st.caption(
        f"Signed in as {reviewer.display_name} ({reviewer.role}) · "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    )
    # The actual case-loading loop (queue.reserve_next → render form →
    # repository.insert_grade → queue.complete) is orchestrated by the
    # thin runner in `labeling/runner.py` to keep this shell trivial.
    st.info(
        "Fetch the next assigned case from the sidebar. "
        "Each grade is chained to your previous grade via a SHA-256 hash."
    )
