# ADR-0011: Arize Phoenix for LLM-specific span inspection

**Status:** Accepted
**Date:** 2026-04-19
**Deciders:** Ezra O'Marley

## Context

ADR-0010 put distributed tracing in place via OTel + Tempo. Tempo is excellent for service-graph debugging — "which service is slow, where did the request fail" — but it is not tuned for LLM internals: token-level logprobs, prompt/completion pairs, generation-parameter variation. Clinical calibration review needs those, and so does the active-learning acquisition function (M9, issue #37) that will pick which cases to send to Tier 3 reviewers.

The paper-1 research arc (calibration analysis of MedGemma under distribution shift) depends on being able to pull up, for a given query, the exact per-token logprob distribution the model emitted when it generated its answer. Tempo can't do this without us inventing our own UI.

## Decision

Deploy Arize Phoenix (OSS) alongside Tempo. Phoenix ingests OTel spans that follow the OpenInference semantic convention (e.g., `llm.model_name`, `openinference.span.kind=LLM`, `token` events with per-token logprobs) and exposes a UI optimised for LLM observability: prompt/completion diff views, token-probability plots, span filtering by model version and by generation parameters.

The OTel Collector runs two parallel trace pipelines:

- `traces/tempo` — receives everything EXCEPT spans where `openinference.span.kind == "LLM"`. These go to Tempo with the existing attribute-scrubbing defences.
- `traces/phoenix` — receives ONLY LLM spans. Phoenix gets the full output value and token events because clinical calibration review cannot happen without them; the PHI boundary is enforced upstream (the Python `llm_spans` helpers never receive raw query text — the scrubber has run before generation).

Phoenix's Postgres backend (`phoenix` database on the same data-plane Postgres) is inside the existing PHI boundary. The UI is OIDC-protected at Traefik via a middleware that restricts to `senior_clinician` and `ops` roles — reviewers (`clinical_reviewer`) are not authorised because token-level logprobs reveal generation internals beyond what a rubric reviewer needs.

Phoenix python instrumentation (`openinference-instrumentation-*` packages) wraps openai, anthropic, langchain, etc. — we use none of these on the request path (ADR-0002, no LangChain). Instead we emit OpenInference-compatible spans directly from a small `backend/app/observability/llm_spans.py` helper. Two functions (`start_llm_span`, `record_token_event`) cover every production LLM call we make.

## Consequences

**Positive**

- Per-token logprob data is a click away in the UI, not a pgvector ad-hoc query.
- Tempo's service-graph view stays uncluttered; no 4000-event spans from a verbose generation blow up its block storage.
- Paper-1 and paper-3 both draw from Phoenix queryable history.
- PHI segregation made explicit: Tempo scrubs; Phoenix receives full completions (which are model outputs, not user inputs), and its access is gated behind a stricter OIDC role than the labeling UI.

**Negative**

- One more stateful service to operate. Phoenix uses SQLite or Postgres; we use Postgres so backup + point-in-time-recovery lands with the data plane.
- The `arizephoenix/phoenix` image is ~800 MiB. Acceptable for a single-replica Deployment.
- OpenInference semantic conventions are still evolving. We pin Phoenix at a known-good version (`version-4.30.0`) and upgrade Dependabot-driven.

**Neutral**

- We do not ship the `openinference-instrumentation` Python package; the LLM spans we emit are canonical enough to render in Phoenix without it. This keeps backend/pyproject.toml unchanged.
- The filter processor adds ~0.1ms per-span Collector overhead. Below the noise floor of our 2000-query/day volume.

## Alternatives rejected

- **Langfuse** — self-hosted OSS, similar feature set, but it requires ClickHouse (a second new datastore) and its telemetry opt-out is less well-documented. Phoenix's out-of-the-box PostgreSQL backend matches our existing data plane.
- **Helicone** — prefers a hosted backend; self-host path is not stable as of 2026-04.
- **Roll our own Grafana dashboard over Tempo spans** — doable but loses the prompt/completion-diff UI; that view is the point of this deploy.

## References

- Issue #31 feat(observability): Arize Phoenix for LLM-specific span inspection
- ADR-0006 three-tier evals (Phoenix is the calibration-review surface for Tier 3 data)
- ADR-0010 OTel + Tempo (split pipeline, filter processor)
- OpenInference spec: https://github.com/Arize-ai/openinference
- SKILL.md §10 observability hooks
- `env/observability.env`
