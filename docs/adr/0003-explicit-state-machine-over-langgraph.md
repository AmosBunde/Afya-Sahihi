# ADR-0003: Explicit Python state machine over LangGraph for pipeline orchestration

**Status:** Accepted
**Date:** 2026-04-16
**Deciders:** Ezra O'Marley

## Context

Afya Gemma v1 used LangGraph to orchestrate the two-stage pipeline (Gemini Flash pre-filter then MedGemma generation). During a production incident in which the system returned malaria dosing for an adrenaline query, we spent three days tracing the topic mismatch. The debugging experience was the core problem: LangGraph's node-and-edge abstraction hid the state transitions behind framework machinery. We could not simply add a `print(state)` and see what happened.

For a clinical system, debuggability is a safety property, not a developer-experience concern. A bug that takes three days to diagnose is a bug that stays in production for three days.

The revised architecture makes orchestration legible by construction.

## Decision

The inference pipeline is a plain Python module implementing a typed state machine:

```python
@dataclass(frozen=True, slots=True)
class PipelineState:
    query: Query
    validated: bool = False
    prefilter_result: PrefilterResult | None = None
    retrieval_result: RetrievalResult | None = None
    generation_result: GenerationResult | None = None
    strict_review_result: StrictReviewResult | None = None
    conformal_result: ConformalResult | None = None
    errors: tuple[PipelineError, ...] = ()
```

Transitions are pure functions of the form `State -> State`. They are composed in a single `orchestrate` function whose body is readable top-to-bottom. Every transition emits an OpenTelemetry span. The entire orchestrator lives in one file under 400 lines.

LangGraph, LangChain, and LlamaIndex are not permitted on the critical path.

## Consequences

**Positive**

- A failed query can be debugged by pickling the PipelineState at the failure point and inspecting it locally. No framework knowledge required.
- Every state transition is a function signature, which makes unit testing trivial.
- New pipeline stages are added by adding a field to the dataclass and a transition function. No DAG rewiring.
- OTel spans map one-to-one with transitions, which makes Grafana Tempo timelines readable.
- We do not inherit LangChain's churn (it reorganizes its module structure roughly every quarter).

**Negative**

- We reimplement retry and backoff logic that LangGraph provides out of the box. This is roughly 80 lines of code in `shared/retry.py` and is a one-time cost.
- We cannot use LangGraph's visual graph UI. We do not miss it.
- Onboarding new engineers means reading our code rather than reading LangGraph's docs. We consider this an advantage because our code is the truth.

**Neutral**

- LangChain is still permitted in offline utility scripts (for example, the golden dataset extraction pipeline) where its convenience outweighs its opacity. It is not permitted in the request path.

## Alternatives considered

- **LangGraph**: the status quo, rejected on debuggability grounds.
- **Burr (DAGWorks)**: cleaner than LangGraph but still adds a framework layer.
- **Temporal**: overkill for synchronous request-response pipelines, well-suited for longer async workflows (we use it for training orchestration, separately).
- **Prefect / Airflow**: for batch, not for request-path.

## Compliance and references

- Orchestrator lives at `backend/app/orchestrator.py` and must not exceed 400 lines
- Every transition must have a passing unit test before merge
- Related: ADR-0006 (Inspect AI harness uses the orchestrator as its system under test)
