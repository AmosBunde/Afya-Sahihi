# Afya Sahihi Span Attribute Conventions

Last updated: 2026-04-19. Single source of truth in `backend/app/observability/attributes.py`.

Every application-authored span attribute is defined in the `AfyaAttr` class. **Never** pass a raw string into `span.set_attribute` — use the constant. A CI hook can grep for that pattern and fail the build.

## Prefix

All attributes are under the `afya_sahihi.` namespace. Upstream OTel semantic conventions (`http.*`, `db.*`, `rpc.*`, `server.*`) are used as-is via the `opentelemetry.semconv` package when they exist; prefer those.

## Identity (set on every span)

| Constant            | Key                          | Shape        | Notes |
| ------------------- | ---------------------------- | ------------ | ----- |
| `AfyaAttr.QUERY_ID` | `afya_sahihi.query.id`       | UUID string  | Opaque. **Never** set `query.text` — PHI. |
| `AfyaAttr.USER_ID`  | `afya_sahihi.user.id`        | OIDC `sub`   | Opaque. |
| `AfyaAttr.REQUEST_ID` | `afya_sahihi.request.id`   | UUID string  | From `X-Request-ID` header. |
| `AfyaAttr.CORPUS_VERSION` | `afya_sahihi.corpus.version` | `v1.0` | Tied to the deployed `corpus_version` setting. |

## Orchestrator (one span per step, all named `orchestrator.<step>`)

| Constant                        | Key                                     | Shape        |
| ------------------------------- | --------------------------------------- | ------------ |
| `AfyaAttr.ORCH_STEP`            | `afya_sahihi.orchestrator.step`         | enum string  |
| `AfyaAttr.ORCH_FAIL_CLOSED`     | `afya_sahihi.orchestrator.fail_closed`  | bool         |

Orchestrator span names (the `ORCH_STEP` enum values): `prefilter`, `retrieve`, `generate`, `strict_review`, `conformal`.

## Prefilter

`afya_sahihi.prefilter.topic_score` (float 0-1), `...safety_flag` (bool), `...classified_intent` (enum).

## Retrieval

`afya_sahihi.retrieval.n_chunks` (int), `...top1_similarity` (float 0-1), `...fusion_strategy` (enum: `rrf`, `dense_only`, etc.).

## Generation (will link to Phoenix via `span.kind=LLM`)

`afya_sahihi.generation.model`, `...n_tokens`, `...avg_logprob`, `...temperature`, `...seed`.

Token-level logprobs go to Phoenix as span events — **not** as attributes on the span. Spans are for cardinality-bounded data; per-token logprobs would explode attribute size.

## Strict review

`afya_sahihi.strict_review.approved` (bool), `...reason` (enum when not approved; unset when approved).

## Conformal

`afya_sahihi.conformal.set_size` (int), `...q_hat` (float), `...covered` (bool), `...stratum` (enum: `dosing`, `contraindication`, ...).

## Labeling (Tier 3 UI)

`afya_sahihi.labeling.case_id`, `...reviewer_role`, `...rubric_version`.

## Result

`afya_sahihi.result.error_kind` (enum from `app.errors` class names: `PrefilterRejected`, `RetrievalFailed`, ...). Set only when the pipeline did not produce a normal answer.

## What never goes in a span attribute

- Query text, note text, or any free-form user input — PHI.
- Raw SQL or template literals with parameter values — PHI.
- Full prompt / full completion — use Phoenix span events instead.
- JWT tokens, passwords, API keys.
- Stack traces — use `span.record_exception(e)` which maps to OTel semantic conventions.

The OTel Collector runs an `attributes` processor that deletes
`afya_sahihi.query.text`, `http.request.body`, and `db.statement` as a
last line of defence. **Never rely on it** — application code is the
primary guard.

## Adding a new attribute

1. Add a constant to `AfyaAttr` in `backend/app/observability/attributes.py`.
2. Document it here.
3. Ensure the name is snake_dot and starts with `afya_sahihi.`.
4. If the attribute could be high-cardinality (per-token, per-chunk, per-user-string), store as a span event with `span.add_event(name, attributes={...})` rather than a span attribute.
