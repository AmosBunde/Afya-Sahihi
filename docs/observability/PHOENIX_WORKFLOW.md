# Phoenix debugging workflow

Last updated: 2026-04-19.

Phoenix answers "why did the model say that?" — token by token, with logprobs, against the same trace_id the gateway logs emit. Tempo (ADR-0010) handles "where did the request go?"; Phoenix handles "what did the model see and produce?".

## Access

- URL: https://afya-sahihi.aku.edu/phoenix
- Auth: OIDC via the shared Traefik middleware.
- Role gate: `senior_clinician` or `ops`. Reviewers (`clinical_reviewer`) do NOT have Phoenix access — a Tier 3 rubric grade is a different cognitive task than calibration inspection.

If you need access and don't have the role: your clinical lead grants `senior_clinician`; the platform team grants `ops`.

## Retrieval debugging: walking a case

The most common workflow is "this answer looks wrong, what happened upstream?".

1. **Get the query_id.** From the labeling UI's case detail, the chat UI's trace header (`X-Trace-ID` response header), or the audit log (`queries_audit.query_id`).
2. **Find the trace in Tempo.** Grafana → Explore → Tempo data source → `{ afya_sahihi.query.id = "<query_id>" }`. You get the full top-to-bottom span tree.
3. **Open Phoenix for the LLM spans.** In Phoenix, filter by `afya_sahihi.query.id` (same attribute name as Tempo — the LLM spans carry it). You see three spans for a single request: `vllm.prefilter`, `vllm.generate`, and optionally `vllm.strict_review`.
4. **For the generate span, expand `llm.output.value` and the token event list.** Each token has `logprob` and up to N `top_logprobs` alternatives. If the model said "ibuprofen" with logprob -0.9 but "aspirin" was second at -1.1, that's a calibration finding worth flagging to the active-learning queue.
5. **Cross-reference retrieval quality.** In Tempo, the `orchestrator.retrieve` child span has `afya_sahihi.retrieval.top1_similarity` and `...n_chunks`. A wrong answer with top1_similarity < 0.5 is a retrieval miss, not a generation miss — file a retrieval bug, not a model issue.

## Calibration review: finding low-confidence answers

1. In Phoenix, filter on `llm.token_count.completion > 0` (exclude refusals) and sort by the per-case mean logprob (a custom column, configured in the saved view "Calibration inbox").
2. Low mean-logprob answers are candidates for Tier 3 review — they're either hallucinated (low confidence → hallucinating fluently is rare) or genuinely hard (the model is honestly uncertain).
3. Export the list of query_ids; they feed the M9 acquisition-function scheduler.

## Incident triage: "a whole model batch went wrong"

1. In Phoenix, group by `llm.model_name` + `service.version`. If the bad window correlates with a version rollout, open a GitHub incident and roll back via the systemd watcher (see ADR-0005).
2. Tempo's `service.version` resource attribute (set from `GIT_SHA` at image build) tells you exactly which binary the Collector ingested from.

## What Phoenix is NOT for

- **PHI-sensitive clinician notes.** Notes live in `grades.notes` after the scrubber; they are never emitted as spans. Phoenix does not have Tier 3 grading data.
- **Business metrics.** RED (Rate, Errors, Duration) and coverage/ECE go to Prometheus + Grafana (issue #32), not here.
- **Log search.** Phoenix is a span viewer, not a log aggregator. Loki (issue #32) is the log search UI.

## Extending the LLM span emitter

Add new attributes in `backend/app/observability/llm_spans.py` following OpenInference conventions (`llm.*`, `output.*`, `input.*`). Document the attribute in `SPAN_ATTRIBUTES.md` under the Generation section. Add a unit test that verifies the attribute lands on the span after `set_llm_result` (or wherever it's set).
