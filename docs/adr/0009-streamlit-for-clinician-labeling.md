# ADR-0009: Streamlit for the Tier 3 clinician labeling UI

**Status:** Accepted
**Date:** 2026-04-18
**Deciders:** Ezra O'Marley

## Context

Tier 3 evaluation (ADR-0006) requires a clinician reviewer UI: grading 20 cases per week on a 5-dimension rubric, backed by a Redis work queue and persisted to a `grades` table with chain-of-custody. The target audience is 6–12 clinicians at AKUH who split time between wards and reviewing. Bedside devices include phones; desktops are the minority. We need something they can open on a phone between rounds and complete in under 60 minutes/week of total focused time.

The alternatives considered:

1. **Embed in the existing React 19 chat app (M8, issue #35).** Would share auth and ingress, but ties the rollout of Tier 3 to the frontend team's schedule and pulls rubric-UI complexity into a codebase that otherwise only renders chat. The clinician review surface is different enough (queue view, PDF provenance iframe, grade history, 5-slider rubric form) that it becomes its own route with its own state machine. Also — the frontend hasn't shipped as of 2026-04 (#35 still open).
2. **Build a small FastAPI + HTMX surface.** Keeps the stack thin but we'd still be writing templates, form handlers, and CSS from scratch for a tool that a dozen people will use.
3. **Streamlit.** Declarative form rendering, built-in session state, built-in auth-header pass-through, works on mobile out of the box, and deploys as a single container. The data-scientist stack at AKU already uses Streamlit for internal dashboards, so operators know how to run it.

## Decision

Use Streamlit for the Tier 3 labeling UI. Package it in a new `labeling/` module, not inside `backend/`, because:

- The labeling UI does not need vLLM/retrieval/conformal clients.
- It has its own k3s deploy (separate container, separate ingress path).
- Unit-testable core (rubric validation, kappa math, queue protocol, PDF URL builder) imports without streamlit so CI runs pure-python on it.

Streamlit stays behind the same Traefik ingress as the gateway. The ingress forwards the validated OIDC claims as an `X-Forwarded-Claims` header; `labeling/auth.py` re-runs the role check so a misconfigured ingress cannot silently grant grading access.

## Consequences

**Positive**

- Zero frontend code. Five sliders + a submit button renders in 30 lines.
- Mobile works by default (Streamlit's layout reflows).
- Shipping decoupled from the React app; Tier 3 evals can start gathering labels before M8 completes.
- Reviewer identity comes from the existing OIDC provider; no new user store.

**Negative**

- Streamlit's script-rerun model is unusual. Contributors need to understand `st.session_state` and form semantics before editing.
- Custom styling (bounding-box overlay on the PDF viewer) is awkward; we defer the full overlay to a v2 and ship with an iframe deep-link for v1.
- Streamlit does not expose a first-class way to inspect the raw HTTP request. We rely on the `X-Forwarded-Claims` header the ingress sets — documented in the deploy manifest.

**Neutral**

- Streamlit pinned at 1.39.0. Upgrades gated on the Dependabot PR + Tier 3 manual smoke test.
- The daily Fleiss kappa job is a k3s CronJob that imports `labeling.daily_kappa` and runs a single query + a small amount of CPU math; no Streamlit dependency.

## Alternatives rejected

- **Shadcn/Next.js admin app** — too much scaffolding for 12 users and a 5-slider form.
- **Jupyter-based labeling** — no per-reviewer queue, no OIDC, no hash chain, not mobile.
- **Google Forms / Airtable** — PHI-adjacent data out of the AKU network is not acceptable to compliance.

## References

- ADR-0006 three-tier evals
- Issue #29 feat(labeling): Streamlit clinician reviewer UI with 5-point rubric
- `env/labeling.env`
- SKILL.md §13 (no dependency without an ADR)
