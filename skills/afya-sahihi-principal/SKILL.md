---
name: afya-sahihi-implementation
description: Principal engineer implementation playbook for Afya Sahihi. Use when writing or reviewing any code in the backend, retrieval, conformal, ingestion, or orchestration modules. Covers code patterns, testing discipline, observability hooks, error handling, async patterns, and the non-negotiables for a clinical AI system. Load this skill whenever touching the critical inference path.
---

# Afya Sahihi — Principal Implementation Skill

This is the playbook a senior engineer joining the Afya Sahihi team reads on day one. It is opinionated, it is enforced in code review, and it is the source of truth when a pattern is disputed.

## 0. Non-negotiables

These rules exist because we have been bitten by each of them in production. They are not style preferences.

1. **Every code path that touches a clinical query fails closed.** If a dependency is unavailable, if a timeout fires, if validation fails, the system returns a refusal response that includes a recommendation to escalate to a human clinician. It never silently partially-succeeds.
2. **No LangChain or LangGraph on the request path.** They are permitted in offline utility scripts only. The request path uses plain Python. See ADR-0003.
3. **Every external call is wrapped in an OTel span and an async timeout.** No exceptions. A call without a timeout is a bug.
4. **Every stored row that touches PHI is scrubbed before write, not after.** The scrubber runs synchronously and fails closed.
5. **Every state transition in the orchestrator emits a structured log event.** The audit trail is a product requirement, not a debugging aid.
6. **Postgres writes on the critical path use explicit transactions with statement timeouts.** Never implicit autocommit.
7. **No mutable global state.** Dependencies are injected via FastAPI Depends or constructor injection.
8. **Type-check in CI with pyright strict.** A missing annotation blocks merge.

## 1. Language and runtime

- Python 3.12 (pinned). We use PEP 695 type syntax where it reads better.
- `asyncio` natively. No `nest_asyncio`, no `trio` bridges.
- `uv` for dependency management. `pyproject.toml` is the source of truth.
- Ruff for lint and format. Pyright for type checking. Both in strict mode.
- Pydantic v2 strict mode everywhere. Models are `frozen=True, strict=True` by default.
- Alembic for schema migrations. Every migration is reversible and tested against a seeded DB.

## 2. Project layout

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory, lifespan, DI wiring
│   ├── settings.py             # Pydantic BaseSettings, reads .env
│   ├── orchestrator.py         # THE state machine (ADR-0003). < 400 lines.
│   ├── state.py                # PipelineState dataclass and friends
│   ├── errors.py               # Typed error hierarchy
│   ├── api/
│   │   ├── chat.py             # POST /chat, SSE streaming
│   │   ├── health.py           # /healthz, /readyz
│   │   └── middleware.py       # Auth, request id, CORS, rate limit
│   ├── clients/
│   │   ├── vllm.py             # OpenAI-compatible clients (27B, 4B)
│   │   ├── retrieval.py        # HTTP client for retrieval service
│   │   ├── conformal.py        # HTTP client for conformal service
│   │   └── audit.py            # HTTP client for audit service
│   ├── validation/
│   │   ├── query.py            # Pydantic models, PHI scrubber
│   │   └── phi.py              # Local regex patterns, never external
│   ├── observability/
│   │   ├── tracing.py          # OTel setup
│   │   ├── metrics.py          # Prom counters, histograms
│   │   └── logging.py          # Structured JSON logging
│   └── repository/
│       ├── base.py             # asyncpg pool lifecycle
│       ├── queries.py          # Typed query repository
│       └── chunks.py           # Retrieval repository (read-only from gateway)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── alembic/
│   └── versions/
├── pyproject.toml
├── uv.lock
├── Dockerfile
└── README.md
```

One file per responsibility. If a file grows past 400 lines, it is almost always doing too much.

## 3. The orchestrator pattern

The orchestrator is the heart of the system. It must be readable top-to-bottom by someone who has never seen the code before.

```python
# backend/app/orchestrator.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Final

from opentelemetry import trace

from app.clients.conformal import ConformalClient
from app.clients.retrieval import RetrievalClient
from app.clients.vllm import VLLMClient
from app.errors import PipelineError, PrefilterRejected, StrictReviewRejected
from app.state import (
    GenerationResult,
    PipelineState,
    PrefilterResult,
    RetrievalResult,
    StrictReviewResult,
    ConformalResult,
)
from app.validation.query import ValidatedQuery

tracer = trace.get_tracer(__name__)

STRICT_REVIEW_CATEGORIES: Final = frozenset({
    "dosing", "contraindication", "pediatric", "pregnancy",
})


@dataclass(frozen=True, slots=True)
class Orchestrator:
    """Typed, explicit pipeline. No framework magic.

    Every step is a method on this class. Each method takes a PipelineState,
    does one thing, and returns a new PipelineState. The `run` method composes
    them in a fixed order. To debug, pickle the state at any step and inspect.
    """

    vllm_27b: VLLMClient
    vllm_4b: VLLMClient
    retrieval: RetrievalClient
    conformal: ConformalClient
    prefilter_threshold: float
    strict_review_enabled: bool
    fail_closed: bool

    async def run(self, query: ValidatedQuery) -> PipelineState:
        state = PipelineState(query=query)

        with tracer.start_as_current_span("orchestrator.run") as span:
            span.set_attribute("query.id", query.id)
            span.set_attribute("query.language", query.language)

            try:
                state = await self._prefilter(state)
                state = await self._retrieve(state)
                state = await self._generate(state)
                state = await self._strict_review(state)
                state = await self._conformal(state)
                return state
            except PipelineError as e:
                # Fail closed. Return a state with errors populated, never
                # a partially-successful state that could be mistaken for
                # a real answer.
                return replace(state, errors=state.errors + (e,))

    async def _prefilter(self, state: PipelineState) -> PipelineState:
        with tracer.start_as_current_span("orchestrator.prefilter") as span:
            result = await self.vllm_4b.prefilter(state.query.text)
            span.set_attribute("prefilter.score", result.topic_score)
            span.set_attribute("prefilter.safety_flag", result.safety_flag)

            if result.topic_score < self.prefilter_threshold or result.safety_flag:
                raise PrefilterRejected(
                    reason="topic_coherence_low" if not result.safety_flag else "safety_flag",
                    detail=result,
                )
            return replace(state, prefilter_result=result)

    async def _retrieve(self, state: PipelineState) -> PipelineState:
        with tracer.start_as_current_span("orchestrator.retrieve") as span:
            result = await self.retrieval.search(
                query_text=state.query.text,
                query_embedding=None,  # retrieval service computes it
                top_k=6,
                filters=state.query.retrieval_filters,
            )
            span.set_attribute("retrieval.n_chunks", len(result.chunks))
            span.set_attribute("retrieval.top1_similarity", result.top1_similarity)
            return replace(state, retrieval_result=result)

    async def _generate(self, state: PipelineState) -> PipelineState:
        with tracer.start_as_current_span("orchestrator.generate") as span:
            assert state.retrieval_result is not None
            result = await self.vllm_27b.generate(
                query=state.query,
                retrieved_chunks=state.retrieval_result.chunks,
                request_logprobs=True,
            )
            span.set_attribute("generation.n_tokens", result.n_tokens)
            span.set_attribute("generation.avg_logprob", result.avg_logprob)
            return replace(state, generation_result=result)

    async def _strict_review(self, state: PipelineState) -> PipelineState:
        if not self.strict_review_enabled:
            return state
        assert state.generation_result is not None

        # Only trigger strict review for safety-critical categories
        categories = set(state.query.classified_categories or ())
        if not (categories & STRICT_REVIEW_CATEGORIES):
            return state

        with tracer.start_as_current_span("orchestrator.strict_review") as span:
            result = await self.vllm_27b.strict_review(
                generation=state.generation_result,
                categories=list(categories & STRICT_REVIEW_CATEGORIES),
            )
            span.set_attribute("strict_review.approved", result.approved)
            if not result.approved:
                raise StrictReviewRejected(reason=result.reason, detail=result)
            return replace(state, strict_review_result=result)

    async def _conformal(self, state: PipelineState) -> PipelineState:
        with tracer.start_as_current_span("orchestrator.conformal") as span:
            assert state.generation_result is not None
            assert state.retrieval_result is not None
            result = await self.conformal.construct_set(
                query=state.query,
                generation=state.generation_result,
                retrieval=state.retrieval_result,
            )
            span.set_attribute("conformal.set_size", result.set_size)
            span.set_attribute("conformal.covered", result.target_coverage_met)
            return replace(state, conformal_result=result)
```

Read that top to bottom. Every arrow on the C4 Level 3 component diagram corresponds to a method here. No DAG framework, no hidden behavior, no inheritance hierarchy.

## 4. The state dataclass

```python
# backend/app/state.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass(frozen=True, slots=True)
class ChunkReference:
    chunk_id: str
    document_id: str
    section_path: tuple[str, ...]
    page_range: tuple[int, int]
    bounding_boxes: tuple[dict, ...]
    similarity_score: float
    rerank_score: float
    content: str

@dataclass(frozen=True, slots=True)
class PrefilterResult:
    topic_score: float
    safety_flag: bool
    classified_intent: str
    model_version: str
    latency_ms: int

@dataclass(frozen=True, slots=True)
class RetrievalResult:
    chunks: tuple[ChunkReference, ...]
    top1_similarity: float
    mean_similarity: float
    fusion_strategy: str
    latency_ms: int

@dataclass(frozen=True, slots=True)
class GenerationResult:
    response_text: str
    n_tokens: int
    avg_logprob: float
    token_logprobs: tuple[float, ...]
    top_logprobs: tuple[tuple[tuple[str, float], ...], ...]
    model_version: str
    temperature: float
    seed: int
    latency_ms: int

@dataclass(frozen=True, slots=True)
class StrictReviewResult:
    approved: bool
    reason: str | None
    safety_score: float
    latency_ms: int

@dataclass(frozen=True, slots=True)
class ConformalResult:
    set_size: int
    prediction_set: tuple[str, ...]
    nonconformity_score: float
    q_hat: float
    target_coverage_met: bool
    stratum: str
    latency_ms: int

@dataclass(frozen=True, slots=True)
class PipelineState:
    query: "ValidatedQuery"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    prefilter_result: PrefilterResult | None = None
    retrieval_result: RetrievalResult | None = None
    generation_result: GenerationResult | None = None
    strict_review_result: StrictReviewResult | None = None
    conformal_result: ConformalResult | None = None
    errors: tuple[Exception, ...] = ()
```

Frozen dataclasses mean you never mutate. `replace(state, ...)` is the only way to update. This makes debugging trivial: log the state at each step and you have a perfect trace.

## 5. Clients and timeouts

Every external client follows this pattern:

```python
# backend/app/clients/vllm.py
from __future__ import annotations
import asyncio
import httpx
from opentelemetry import trace
from app.settings import Settings

tracer = trace.get_tracer(__name__)


class VLLMClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(
                connect=5.0,
                read=timeout_seconds,
                write=10.0,
                pool=5.0,
            ),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
        )

    async def generate(self, *, query, retrieved_chunks, request_logprobs: bool = True):
        with tracer.start_as_current_span("vllm.generate") as span:
            payload = self._build_payload(query, retrieved_chunks, request_logprobs)
            span.set_attribute("vllm.model", payload["model"])
            span.set_attribute("vllm.max_tokens", payload["max_tokens"])

            try:
                response = await self._client.post("/chat/completions", json=payload)
                response.raise_for_status()
            except httpx.TimeoutException as e:
                span.record_exception(e)
                raise VLLMTimeoutError(str(e)) from e
            except httpx.HTTPStatusError as e:
                span.record_exception(e)
                raise VLLMHTTPError(status=e.response.status_code, body=e.response.text) from e

            return self._parse_response(response.json())

    async def aclose(self):
        await self._client.aclose()
```

The `httpx.Timeout` split matters. `connect` trips if the server is unreachable, `read` trips if inference stalls, `write` trips if the request body cannot be sent. Lumping them into one timeout hides the root cause.

## 6. Error hierarchy

```python
# backend/app/errors.py

class PipelineError(Exception):
    """Base for any error in the orchestrator pipeline. Always fails closed."""
    def __init__(self, reason: str, detail: object = None):
        self.reason = reason
        self.detail = detail
        super().__init__(reason)

class ValidationFailed(PipelineError): ...
class PrefilterRejected(PipelineError): ...
class RetrievalFailed(PipelineError): ...
class GenerationFailed(PipelineError): ...
class StrictReviewRejected(PipelineError): ...
class ConformalFailed(PipelineError): ...

class VLLMError(Exception): ...
class VLLMTimeoutError(VLLMError): ...
class VLLMHTTPError(VLLMError):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:200]}")
```

Typed errors mean the API layer can map each to an appropriate HTTP response and user-facing message without a big `isinstance` ladder.

## 7. Postgres repository pattern

```python
# backend/app/repository/chunks.py
from __future__ import annotations
import asyncpg
from app.state import ChunkReference

HYBRID_SEARCH_SQL = """
WITH dense AS (
    SELECT id, 1 - (embedding <=> $1::vector) AS score
    FROM chunks
    WHERE corpus_version = $2
      AND ($3::jsonb IS NULL OR structural_meta @> $3::jsonb)
    ORDER BY embedding <=> $1::vector
    LIMIT $4
),
sparse AS (
    SELECT id, paradedb.score(id) AS score
    FROM chunks
    WHERE chunks @@@ paradedb.parse($5)
      AND corpus_version = $2
    ORDER BY score DESC
    LIMIT $4
),
fused AS (
    SELECT
        COALESCE(d.id, s.id) AS id,
        COALESCE(1.0 / ($6 + d.rank), 0) * $7
        + COALESCE(1.0 / ($6 + s.rank), 0) * $8 AS rrf_score
    FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank FROM dense) d
    FULL OUTER JOIN (SELECT id, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank FROM sparse) s
        USING (id)
)
SELECT c.id, c.document_id, c.content, c.structural_meta, f.rrf_score
FROM fused f
JOIN chunks c ON c.id = f.id
ORDER BY f.rrf_score DESC
LIMIT $9;
"""


class ChunksRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def hybrid_search(
        self,
        *,
        query_embedding: list[float],
        query_text: str,
        corpus_version: str,
        structural_filter: dict | None,
        candidates: int,
        dense_weight: float,
        sparse_weight: float,
        rrf_k: int,
        final_top_k: int,
    ) -> list[ChunkReference]:
        async with self._pool.acquire() as conn:
            # Statement-level timeout. Never trust global defaults.
            await conn.execute("SET LOCAL statement_timeout = '10s'")
            rows = await conn.fetch(
                HYBRID_SEARCH_SQL,
                query_embedding,
                corpus_version,
                structural_filter,
                candidates,
                query_text,
                rrf_k,
                dense_weight,
                sparse_weight,
                final_top_k,
            )
            return [self._row_to_chunk(r) for r in rows]

    @staticmethod
    def _row_to_chunk(row) -> ChunkReference:
        meta = row["structural_meta"]
        return ChunkReference(
            chunk_id=row["id"],
            document_id=row["document_id"],
            section_path=tuple(meta.get("structure", {}).get("section_path", ())),
            page_range=tuple(meta.get("source", {}).get("page_range", (0, 0))),
            bounding_boxes=tuple(meta.get("source", {}).get("bounding_boxes", ())),
            similarity_score=row["rrf_score"],
            rerank_score=0.0,  # set by reranker stage
            content=row["content"],
        )
```

Raw SQL, parameterized, explicit. No ORM guessing. You can copy this into `psql` and run it. That is the point.

## 8. Testing discipline

Three layers, all required before merge.

**Unit tests** live alongside the module they test. They mock external dependencies (vLLM clients, Postgres pool). They run in under 10 seconds total.

**Integration tests** spin up a real Postgres (testcontainers) and a mock vLLM (httpserver). They test the orchestrator end-to-end against known queries. They run in under 2 minutes.

**Eval tests** are Tier 1 Inspect AI tasks. They run the full pipeline against the golden dataset. They gate PRs.

```python
# Example unit test for orchestrator._prefilter
import pytest
from unittest.mock import AsyncMock
from app.orchestrator import Orchestrator
from app.errors import PrefilterRejected

@pytest.mark.asyncio
async def test_prefilter_rejects_low_topic_score():
    vllm_4b = AsyncMock()
    vllm_4b.prefilter.return_value = PrefilterResult(
        topic_score=0.3, safety_flag=False, classified_intent="unknown",
        model_version="v1", latency_ms=42,
    )
    orch = Orchestrator(
        vllm_27b=AsyncMock(), vllm_4b=vllm_4b,
        retrieval=AsyncMock(), conformal=AsyncMock(),
        prefilter_threshold=0.65, strict_review_enabled=True, fail_closed=True,
    )

    state = PipelineState(query=fake_query())
    with pytest.raises(PrefilterRejected, match="topic_coherence_low"):
        await orch._prefilter(state)
```

Never test the orchestrator `run` method with real clients in unit tests. That is what integration tests are for.

## 9. Async discipline

- Every public function that can block is `async def`. Period.
- Never call `asyncio.run` inside a handler. The event loop is already running.
- Never use `asyncio.create_task` without storing the reference and awaiting it or attaching a done callback. Unhandled task exceptions are the single most common production bug pattern.
- Use `asyncio.TaskGroup` (3.11+) for parallel work, not `gather`.
- Treat every `await` as a potential yield point. Holding a lock across `await` is almost always a bug.

```python
# Good: TaskGroup with explicit error propagation
async def parallel_enrichment(query):
    async with asyncio.TaskGroup() as tg:
        icd_task = tg.create_task(icd_service.classify(query))
        lang_task = tg.create_task(lang_detector.detect(query))
    return icd_task.result(), lang_task.result()
```

## 10. Observability hooks

Every service has these, non-negotiable.

**Spans**: one per orchestrator step, one per external call. Named `service.operation`. Span attributes use OTel semantic conventions where they exist.

**Metrics**: RED (Rate, Errors, Duration) per endpoint via Prometheus histograms. Plus domain-specific: `afya-sahihi_retrieval_top1_similarity`, `afya-sahihi_conformal_set_size`, `afya-sahihi_generation_avg_logprob`.

**Logs**: structured JSON only. Keys: `ts`, `level`, `service`, `trace_id`, `span_id`, `query_id`, `msg`, plus domain fields. No `print`. No `f"..."` concatenation into a message. Use the logger's structured API:

```python
logger.info("retrieval complete", extra={
    "query_id": state.query.id,
    "n_chunks": len(result.chunks),
    "top1_similarity": result.top1_similarity,
})
```

## 11. Configuration

Pydantic `BaseSettings` reads from env. The settings object is created once at app startup, injected everywhere, and never mutated.

```python
# backend/app/settings.py
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", frozen=True)

    service_name: str = "afya-sahihi-gateway"
    service_port: int = 8080

    vllm_27b_base_url: str
    vllm_27b_timeout_seconds: float = 60.0
    vllm_4b_base_url: str
    vllm_4b_timeout_seconds: float = 10.0

    pg_host: str
    pg_port: int = 5432
    pg_database: str
    pg_user: str
    pg_password: str = Field(repr=False)
    pg_pool_min: int = 4
    pg_pool_max: int = 20

    pipeline_prefilter_threshold: float = 0.65
    pipeline_generation_temperature: float = 0.1
    pipeline_generation_seed: int = 20260416

    corpus_version: str = "v1.0"

    feature_strict_review_enabled: bool = True
    feature_conformal_enabled: bool = True
```

## 12. Code review checklist

Reviewer asks every time:

- [ ] Does every external call have a timeout?
- [ ] Does every error path fail closed?
- [ ] Does every state transition log a structured event?
- [ ] Is there a unit test that exercises the new code path?
- [ ] Does the change touch the request path? If so, is there an OTel span?
- [ ] Any new Python dependency? Justified? Pinned?
- [ ] Any new env var? Added to all relevant .env files and to `settings.py`?
- [ ] Any new table or column? Alembic migration present and reversible?
- [ ] Does the PR pass Tier 1 evals? (CI enforces, but eyeball the diff.)
- [ ] Does the code read top-to-bottom without needing framework knowledge?

If any answer is no, the PR does not merge.

## 13. What never goes in this system

A deliberately-maintained deny list:

- LangChain or LangGraph on the request path
- `nest_asyncio`
- `requests` (use httpx)
- SQLAlchemy ORM (raw asyncpg only)
- `dotenv` at runtime (settings read env once, at startup)
- `print` (logger only)
- Silent exception handlers (`except: pass`)
- `from X import *`
- Global mutable state
- In-process caches on the hot path that are not explicit, bounded, and TTL-stamped
- Any dependency with unmaintained status or known CVE

## 14. Deployment gates

A change reaches production via:

1. PR opened. CI runs unit + integration + Tier 1 evals.
2. Review approved. Merge to `main`.
3. GitHub Actions builds and signs container image. Pushes to Harbor.
4. Staging deploy via GitOps. Tier 2 evals run automatically.
5. On Tier 2 green, PR against `deploy/prod/manifests.yaml`. Manual approval.
6. systemd watcher picks up the change within 60 seconds. Rollout observed on Grafana.
7. Canary for 30 minutes. Auto-rollback if error rate exceeds 0.5 percent or P99 latency exceeds 6 seconds.

No manual `kubectl apply` in production. Ever.

## 15. On-call playbook

When the pager fires, the first three commands are always the same:

```bash
# 1. Are we healthy?
kubectl -n afya-sahihi get pods
# 2. What is the current error rate?
open https://afya-sahihi.aku.edu/grafana/d/red-metrics
# 3. What changed in the last hour?
kubectl -n afya-sahihi get events --sort-by='.lastTimestamp' | tail -20
```

If those three do not answer the question in 2 minutes, page the secondary.
