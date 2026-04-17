"""Unit tests for the retrieval service — fakes for embedder/reranker/repo."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from retrieval.models import ChunkResult, RetrievalResponse
from retrieval.service import _boost_contraindications
from retrieval.settings import RetrievalSettings

# ---- Fakes ----


class _FakeEmbedder:
    def embed(self, text: str) -> tuple[float, ...]:
        return tuple(0.1 for _ in range(768))


class _FakeReranker:
    def rerank(self, query: str, passages: Sequence[str]) -> Sequence[float]:
        return tuple(1.0 / (i + 1) for i in range(len(passages)))


def _chunk(
    chunk_id: str = "c1",
    rrf: float = 0.5,
    is_contra: bool = False,
) -> ChunkResult:
    structure = {"is_contraindication": is_contra}
    return ChunkResult(
        chunk_id=chunk_id,
        document_id="doc1",
        content="text",
        structural_meta={"structure": structure},
        dense_score=0.8,
        sparse_score=0.6,
        rrf_score=rrf,
    )


def _settings(**overrides: object) -> RetrievalSettings:
    base: dict[str, object] = dict(
        pg_host="localhost",
        pg_database="test",
        pg_user="postgres",
        pg_password="test",
    )
    base.update(overrides)
    return RetrievalSettings.model_validate(base)


# ---- Tests ----


def test_boost_contraindications_increases_score() -> None:
    chunks = [_chunk("c1", rrf=0.5), _chunk("c2", rrf=0.8, is_contra=True)]
    boosted = _boost_contraindications(chunks, boost=1.5)
    contra = next(c for c in boosted if c.chunk_id == "c2")
    assert contra.rrf_score == pytest.approx(0.8 * 1.5)


def test_boost_contraindications_reorders() -> None:
    chunks = [
        _chunk("normal", rrf=0.9),
        _chunk("contra", rrf=0.7, is_contra=True),
    ]
    boosted = _boost_contraindications(chunks, boost=1.5)
    assert boosted[0].chunk_id == "contra"


def test_boost_no_op_when_no_contraindications() -> None:
    chunks = [_chunk("c1", rrf=0.5), _chunk("c2", rrf=0.8)]
    boosted = _boost_contraindications(chunks, boost=2.0)
    assert boosted[0].chunk_id == "c2"
    assert boosted[0].rrf_score == pytest.approx(0.8)


def test_response_model_shape() -> None:
    resp = RetrievalResponse(
        chunks=(_chunk(),),
        top1_similarity=0.9,
        mean_similarity=0.7,
        n_dense_candidates=3,
        n_sparse_candidates=2,
        latency_ms=42,
    )
    assert len(resp.chunks) == 1
    assert resp.fusion_strategy == "rrf"
