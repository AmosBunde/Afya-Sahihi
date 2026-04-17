"""Retrieval service — search, rerank, respond.

Orchestrates: embed query → hybrid SQL → optional rerank → boost
contraindications → build RetrievalResponse. Each step is a separate
method so the service is testable with fakes for the heavy components
(embedder, reranker) and a real Postgres for the SQL.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Protocol

from retrieval.models import ChunkResult, RetrievalRequest, RetrievalResponse
from retrieval.repository import RetrievalRepository
from retrieval.settings import RetrievalSettings

logger = logging.getLogger(__name__)


class QueryEmbedder(Protocol):
    """Embed a single query string to a dense vector."""

    def embed(self, text: str) -> tuple[float, ...]: ...


class Reranker(Protocol):
    """Score (query, chunk) pairs; higher = more relevant."""

    def rerank(self, query: str, passages: Sequence[str]) -> Sequence[float]: ...


class RetrievalService:
    """Core retrieval logic with Protocol-injected heavy deps."""

    def __init__(
        self,
        *,
        settings: RetrievalSettings,
        repository: RetrievalRepository,
        embedder: QueryEmbedder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self._settings = settings
        self._repo = repository
        self._embedder = embedder
        self._reranker = reranker

    async def search(self, request: RetrievalRequest) -> RetrievalResponse:
        t0 = time.monotonic()

        # Embed query if not pre-embedded
        if request.query_embedding is not None:
            embedding = request.query_embedding
        elif self._embedder is not None:
            embedding = self._embedder.embed(request.query_text)
        else:
            raise ValueError("query_embedding is None and no embedder is configured")

        # Hybrid search
        chunks = await self._repo.hybrid_search(
            query_embedding=embedding,
            query_text=request.query_text,
            corpus_version=request.corpus_version,
            structural_filter=request.structural_filter,
            candidates=max(
                self._settings.dense_top_k_candidates,
                self._settings.sparse_top_k_candidates,
            ),
            final_top_k=request.top_k,
        )

        n_dense = sum(1 for c in chunks if c.dense_score > 0)
        n_sparse = sum(1 for c in chunks if c.sparse_score > 0)

        # Rerank
        if self._reranker and self._settings.retrieval_rerank_enabled and chunks:
            rerank_scores = self._reranker.rerank(request.query_text, [c.content for c in chunks])
            chunks = [
                ChunkResult(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    content=c.content,
                    structural_meta=c.structural_meta,
                    dense_score=c.dense_score,
                    sparse_score=c.sparse_score,
                    rrf_score=c.rrf_score,
                    rerank_score=float(s),
                )
                for c, s in zip(chunks, rerank_scores, strict=True)
            ]
            chunks.sort(key=lambda c: c.rerank_score, reverse=True)

        # Boost contraindications
        if self._settings.structural_filters_enabled:
            chunks = _boost_contraindications(
                chunks, self._settings.structural_boost_contraindications
            )

        latency_ms = int((time.monotonic() - t0) * 1000)

        top1 = chunks[0].rrf_score if chunks else 0.0
        mean = sum(c.rrf_score for c in chunks) / len(chunks) if chunks else 0.0

        logger.info(
            "retrieval complete",
            extra={
                "n_results": len(chunks),
                "top1_similarity": round(top1, 4),
                "latency_ms": latency_ms,
            },
        )

        return RetrievalResponse(
            chunks=tuple(chunks),
            top1_similarity=top1,
            mean_similarity=mean,
            n_dense_candidates=n_dense,
            n_sparse_candidates=n_sparse,
            latency_ms=latency_ms,
        )


def _boost_contraindications(chunks: list[ChunkResult], boost: float) -> list[ChunkResult]:
    """Multiply RRF score of contraindication chunks by `boost`.

    ADR-0004: contraindication chunks carry
    `structural_meta.structure.is_contraindication=true`. Harm-weighted
    boosting ensures they surface early for safety-critical queries.
    """
    boosted: list[ChunkResult] = []
    for c in chunks:
        structure = c.structural_meta.get("structure", {})
        if isinstance(structure, dict) and structure.get("is_contraindication"):
            c = ChunkResult(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                content=c.content,
                structural_meta=c.structural_meta,
                dense_score=c.dense_score,
                sparse_score=c.sparse_score,
                rrf_score=c.rrf_score * boost,
                rerank_score=c.rerank_score,
            )
        boosted.append(c)
    boosted.sort(key=lambda c: c.rrf_score, reverse=True)
    return boosted
