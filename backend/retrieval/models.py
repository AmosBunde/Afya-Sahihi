"""Request/response models for the retrieval service.

All models are strict+frozen per SKILL.md §1.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_CFG = ConfigDict(strict=True, frozen=True, extra="forbid")


class RetrievalRequest(BaseModel):
    model_config = _CFG

    query_text: str = Field(min_length=1, max_length=4000)
    query_embedding: tuple[float, ...] | None = None
    top_k: int = Field(default=6, ge=1, le=50)
    corpus_version: str = "v1.0"
    structural_filter: dict[str, object] | None = None


class ChunkResult(BaseModel):
    model_config = _CFG

    chunk_id: str
    document_id: str
    content: str
    structural_meta: dict[str, object]
    dense_score: float
    sparse_score: float
    rrf_score: float
    rerank_score: float = 0.0


class RetrievalResponse(BaseModel):
    model_config = _CFG

    chunks: tuple[ChunkResult, ...]
    top1_similarity: float
    mean_similarity: float
    fusion_strategy: str = "rrf"
    n_dense_candidates: int = 0
    n_sparse_candidates: int = 0
    latency_ms: int = 0
