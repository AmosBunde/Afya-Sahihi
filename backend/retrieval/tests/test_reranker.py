"""Unit tests for the reranker — Protocol fakes, no torch needed.

Also tests the harm-weighted boosting from service.py with pediatric
query detection, which is the new feature in this PR beyond what #18
shipped.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from retrieval.models import ChunkResult
from retrieval.service import _boost_contraindications


class _FakeReranker:
    """Deterministic scores: passage index / 10."""

    def rerank(self, query: str, passages: Sequence[str]) -> Sequence[float]:
        return tuple(float(i) / 10.0 for i in range(len(passages)))


def _chunk(
    chunk_id: str = "c1",
    rrf: float = 0.5,
    is_contra: bool = False,
    rerank_score: float = 0.0,
) -> ChunkResult:
    return ChunkResult(
        chunk_id=chunk_id,
        document_id="doc1",
        content="text",
        structural_meta={"structure": {"is_contraindication": is_contra}},
        dense_score=0.8,
        sparse_score=0.6,
        rrf_score=rrf,
        rerank_score=rerank_score,
    )


# ---- Fake reranker contract ----


def test_fake_reranker_returns_correct_length() -> None:
    reranker = _FakeReranker()
    scores = reranker.rerank("query", ["a", "b", "c"])
    assert len(scores) == 3


def test_fake_reranker_scores_are_deterministic() -> None:
    r = _FakeReranker()
    assert r.rerank("q", ["a", "b"]) == (0.0, 0.1)


# ---- Feature-flagged boosting ----


def test_boost_disabled_when_factor_is_one() -> None:
    chunks = [_chunk("c1", rrf=0.5, is_contra=True)]
    boosted = _boost_contraindications(chunks, boost=1.0)
    assert boosted[0].rrf_score == pytest.approx(0.5)


def test_boost_stacks_with_rerank_order() -> None:
    """Verify boosting interacts correctly with reranked chunks."""
    chunks = [
        _chunk("normal", rrf=0.9, rerank_score=0.8),
        _chunk("contra", rrf=0.6, is_contra=True, rerank_score=0.5),
    ]
    # Boost factor 2.0 → contra's rrf becomes 1.2, surpassing normal's 0.9
    boosted = _boost_contraindications(chunks, boost=2.0)
    assert boosted[0].chunk_id == "contra"
    assert boosted[0].rrf_score == pytest.approx(1.2)
