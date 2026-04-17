"""Unit tests for the orchestrator state machine.

Mocks every external client. Tests the state transitions, fail-closed
behaviour, and prefilter rejection. SKILL.md §8: never test the
orchestrator `run` method with real clients in unit tests.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.errors import PrefilterRejected, StrictReviewRejected
from app.orchestrator import Orchestrator
from app.state import (
    ConformalResult,
    GenerationResult,
    PrefilterResult,
    RetrievalResult,
    StrictReviewResult,
    ValidatedQuery,
)


def _query(**overrides: object) -> ValidatedQuery:
    base: dict[str, object] = {
        "id": "q-001",
        "text": "What is the dose of artemether for a 5-year-old?",
        "language": "en",
    }
    base.update(overrides)
    return ValidatedQuery(**base)  # type: ignore[arg-type]


def _prefilter_ok() -> PrefilterResult:
    return PrefilterResult(
        topic_score=0.9,
        safety_flag=False,
        classified_intent="dosing",
        model_version="v1",
        latency_ms=12,
    )


def _prefilter_low() -> PrefilterResult:
    return PrefilterResult(
        topic_score=0.3,
        safety_flag=False,
        classified_intent="unknown",
        model_version="v1",
        latency_ms=10,
    )


def _retrieval_ok() -> RetrievalResult:
    return RetrievalResult(
        chunks=(),
        top1_similarity=0.85,
        mean_similarity=0.72,
        fusion_strategy="rrf",
        latency_ms=50,
    )


def _generation_ok() -> GenerationResult:
    return GenerationResult(
        response_text="Artemether 20mg per dose.",
        n_tokens=10,
        avg_logprob=-0.3,
        token_logprobs=(-0.2, -0.4),
        top_logprobs=(),
        model_version="27b-v1",
        temperature=0.1,
        seed=42,
        latency_ms=200,
    )


def _strict_review_approved() -> StrictReviewResult:
    return StrictReviewResult(approved=True, reason=None, safety_score=0.95, latency_ms=30)


def _strict_review_rejected() -> StrictReviewResult:
    return StrictReviewResult(
        approved=False, reason="dosing_conflict", safety_score=0.2, latency_ms=30
    )


def _conformal_ok() -> ConformalResult:
    return ConformalResult(
        set_size=3,
        prediction_set=("artemether", "lumefantrine", "quinine"),
        nonconformity_score=0.4,
        q_hat=0.5,
        target_coverage_met=True,
        stratum="dosing",
        latency_ms=15,
    )


def _orchestrator(**overrides: object) -> Orchestrator:
    vllm_4b = AsyncMock()
    vllm_4b.prefilter.return_value = _prefilter_ok()

    vllm_27b = AsyncMock()
    vllm_27b.generate.return_value = _generation_ok()
    vllm_27b.strict_review.return_value = _strict_review_approved()

    retrieval = AsyncMock()
    retrieval.search.return_value = _retrieval_ok()

    conformal = AsyncMock()
    conformal.construct_set.return_value = _conformal_ok()

    defaults: dict[str, object] = {
        "vllm_27b": vllm_27b,
        "vllm_4b": vllm_4b,
        "retrieval": retrieval,
        "conformal": conformal,
        "prefilter_threshold": 0.65,
        "strict_review_enabled": True,
        "fail_closed": True,
    }
    defaults.update(overrides)
    return Orchestrator(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_happy_path_produces_complete_state() -> None:
    orch = _orchestrator()
    state = await orch.run(_query())

    assert state.prefilter_result is not None
    assert state.retrieval_result is not None
    assert state.generation_result is not None
    assert state.conformal_result is not None
    assert state.errors == ()


@pytest.mark.asyncio
async def test_prefilter_rejects_low_topic_score() -> None:
    vllm_4b = AsyncMock()
    vllm_4b.prefilter.return_value = _prefilter_low()
    orch = _orchestrator(vllm_4b=vllm_4b)

    state = await orch.run(_query())

    assert len(state.errors) == 1
    assert isinstance(state.errors[0], PrefilterRejected)
    assert state.errors[0].reason == "topic_coherence_low"
    assert state.retrieval_result is None


@pytest.mark.asyncio
async def test_strict_review_rejects_unsafe_generation() -> None:
    vllm_27b = AsyncMock()
    vllm_27b.generate.return_value = _generation_ok()
    vllm_27b.strict_review.return_value = _strict_review_rejected()

    orch = _orchestrator(vllm_27b=vllm_27b)
    query = _query(classified_categories=("dosing",))
    state = await orch.run(query)

    assert len(state.errors) == 1
    assert isinstance(state.errors[0], StrictReviewRejected)


@pytest.mark.asyncio
async def test_strict_review_skipped_when_disabled() -> None:
    orch = _orchestrator(strict_review_enabled=False)
    query = _query(classified_categories=("dosing",))
    state = await orch.run(query)

    assert state.strict_review_result is None
    assert state.errors == ()


@pytest.mark.asyncio
async def test_strict_review_skipped_for_non_safety_categories() -> None:
    orch = _orchestrator()
    query = _query(classified_categories=("general_info",))
    state = await orch.run(query)

    assert state.strict_review_result is None
    assert state.errors == ()


@pytest.mark.asyncio
async def test_pipeline_fails_closed_on_retrieval_error() -> None:
    retrieval = AsyncMock()
    retrieval.search.side_effect = RuntimeError("connection refused")
    orch = _orchestrator(retrieval=retrieval)

    state = await orch.run(_query())

    assert len(state.errors) == 1
    assert "connection refused" in state.errors[0].reason
    assert state.generation_result is None
