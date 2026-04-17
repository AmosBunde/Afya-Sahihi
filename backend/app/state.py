"""PipelineState and stage-result dataclasses.

Frozen dataclasses so you never mutate. `dataclasses.replace(state, ...)`
is the only way to update. This makes debugging trivial: log the state at
each step and you have a perfect trace. SKILL.md §4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class ValidatedQuery:
    """A query that has passed input validation."""

    id: str
    text: str
    language: str = "en"
    classified_categories: tuple[str, ...] | None = None
    retrieval_filters: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class PrefilterResult:
    topic_score: float
    safety_flag: bool
    classified_intent: str
    model_version: str
    latency_ms: int


@dataclass(frozen=True, slots=True)
class ChunkReference:
    chunk_id: str
    document_id: str
    section_path: tuple[str, ...]
    page_range: tuple[int, int]
    bounding_boxes: tuple[dict[str, object], ...]
    similarity_score: float
    rerank_score: float
    content: str


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
    query: ValidatedQuery
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    prefilter_result: PrefilterResult | None = None
    retrieval_result: RetrievalResult | None = None
    generation_result: GenerationResult | None = None
    strict_review_result: StrictReviewResult | None = None
    conformal_result: ConformalResult | None = None
    errors: tuple[Exception, ...] = ()
