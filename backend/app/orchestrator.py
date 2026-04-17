"""Typed, explicit pipeline. No framework magic.

Every step is a method on this class. Each method takes a PipelineState,
does one thing, and returns a new PipelineState. The `run` method composes
them in a fixed order. To debug, pickle the state at any step and inspect.

ADR-0003: explicit state machine over LangGraph. SKILL.md §3.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Final, Protocol

from opentelemetry import trace

from app.errors import (
    ConformalFailed,
    GenerationFailed,
    PipelineError,
    PrefilterRejected,
    RetrievalFailed,
    StrictReviewRejected,
)
from app.state import (
    ConformalResult,
    GenerationResult,
    PipelineState,
    PrefilterResult,
    RetrievalResult,
    StrictReviewResult,
    ValidatedQuery,
)

tracer = trace.get_tracer(__name__)

STRICT_REVIEW_CATEGORIES: Final = frozenset(
    {"dosing", "contraindication", "pediatric", "pregnancy"}
)


# ---- Client protocols (concrete impls land with issue #22) ---- #


class VLLMClient(Protocol):
    async def prefilter(self, text: str) -> PrefilterResult: ...
    async def generate(
        self,
        *,
        query: ValidatedQuery,
        retrieved_chunks: object,
        request_logprobs: bool,
    ) -> GenerationResult: ...
    async def strict_review(
        self,
        *,
        generation: GenerationResult,
        categories: list[str],
    ) -> StrictReviewResult: ...


class RetrievalClient(Protocol):
    async def search(
        self,
        *,
        query_text: str,
        query_embedding: object,
        top_k: int,
        filters: object,
    ) -> RetrievalResult: ...


class ConformalClient(Protocol):
    async def construct_set(
        self,
        *,
        query: ValidatedQuery,
        generation: GenerationResult,
        retrieval: RetrievalResult,
    ) -> ConformalResult: ...


# ---- Orchestrator ---- #


class Orchestrator:
    """Typed, explicit pipeline. No framework magic.

    Every arrow on the C4 Level 3 component diagram corresponds to a
    method here. No DAG framework, no hidden behavior, no inheritance
    hierarchy.
    """

    def __init__(
        self,
        *,
        vllm_27b: VLLMClient,
        vllm_4b: VLLMClient,
        retrieval: RetrievalClient,
        conformal: ConformalClient,
        prefilter_threshold: float,
        strict_review_enabled: bool,
        fail_closed: bool,
    ) -> None:
        self.vllm_27b = vllm_27b
        self.vllm_4b = vllm_4b
        self.retrieval = retrieval
        self.conformal = conformal
        self.prefilter_threshold = prefilter_threshold
        self.strict_review_enabled = strict_review_enabled
        self.fail_closed = fail_closed

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
            try:
                result = await self.retrieval.search(
                    query_text=state.query.text,
                    query_embedding=None,
                    top_k=6,
                    filters=state.query.retrieval_filters,
                )
            except Exception as e:
                raise RetrievalFailed(reason=str(e)) from e
            span.set_attribute("retrieval.n_chunks", len(result.chunks))
            span.set_attribute("retrieval.top1_similarity", result.top1_similarity)
            return replace(state, retrieval_result=result)

    async def _generate(self, state: PipelineState) -> PipelineState:
        with tracer.start_as_current_span("orchestrator.generate") as span:
            if state.retrieval_result is None:  # noqa: SIM108
                raise GenerationFailed(reason="retrieval_result missing; pipeline out of order")
            try:
                result = await self.vllm_27b.generate(
                    query=state.query,
                    retrieved_chunks=state.retrieval_result.chunks,
                    request_logprobs=True,
                )
            except Exception as e:
                raise GenerationFailed(reason=str(e)) from e
            span.set_attribute("generation.n_tokens", result.n_tokens)
            span.set_attribute("generation.avg_logprob", result.avg_logprob)
            return replace(state, generation_result=result)

    async def _strict_review(self, state: PipelineState) -> PipelineState:
        if not self.strict_review_enabled:
            return state
        if state.generation_result is None:
            raise StrictReviewRejected(reason="generation_result missing; pipeline out of order")

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
                raise StrictReviewRejected(reason=result.reason or "review_failed", detail=result)
            return replace(state, strict_review_result=result)

    async def _conformal(self, state: PipelineState) -> PipelineState:
        with tracer.start_as_current_span("orchestrator.conformal") as span:
            if state.generation_result is None or state.retrieval_result is None:
                raise ConformalFailed(
                    reason="generation or retrieval result missing; pipeline out of order"
                )
            try:
                result = await self.conformal.construct_set(
                    query=state.query,
                    generation=state.generation_result,
                    retrieval=state.retrieval_result,
                )
            except Exception as e:
                raise ConformalFailed(reason=str(e)) from e
            span.set_attribute("conformal.set_size", result.set_size)
            span.set_attribute("conformal.covered", result.target_coverage_met)
            return replace(state, conformal_result=result)
