"""Hybrid retrieval SQL — the single query from SKILL.md §7.

Dense (pgvector cosine) + sparse (pg_search BM25) fused via Reciprocal
Rank Fusion in one CTE. Structural metadata filters compose in the
WHERE clause of each arm so the index can push them down.

Every call sets SET LOCAL statement_timeout (enforced by
scripts/hooks/check_asyncpg_timeouts.sh).
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import asyncpg

from retrieval.models import ChunkResult
from retrieval.settings import RetrievalSettings

_RETRIEVAL_TIMEOUT = "5s"

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
ranked_dense AS (
    SELECT id, score, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank
    FROM dense
),
ranked_sparse AS (
    SELECT id, score, ROW_NUMBER() OVER (ORDER BY score DESC) AS rank
    FROM sparse
),
fused AS (
    SELECT
        COALESCE(d.id, s.id) AS id,
        COALESCE(d.score, 0) AS dense_score,
        COALESCE(s.score, 0) AS sparse_score,
        COALESCE(1.0 / ($6 + d.rank), 0) * $7
        + COALESCE(1.0 / ($6 + s.rank), 0) * $8 AS rrf_score
    FROM ranked_dense d
    FULL OUTER JOIN ranked_sparse s USING (id)
)
SELECT c.id, c.document_id, c.content, c.structural_meta,
       f.dense_score, f.sparse_score, f.rrf_score
FROM fused f
JOIN chunks c ON c.id = f.id
ORDER BY f.rrf_score DESC
LIMIT $9;
"""


class RetrievalRepository:
    """Execute the hybrid CTE against asyncpg."""

    def __init__(self, pool: asyncpg.Pool, settings: RetrievalSettings) -> None:
        self._pool = pool
        self._settings = settings

    async def hybrid_search(
        self,
        *,
        query_embedding: Sequence[float],
        query_text: str,
        corpus_version: str,
        structural_filter: dict[str, object] | None,
        candidates: int,
        final_top_k: int,
    ) -> list[ChunkResult]:
        s = self._settings
        embedding_literal = "[" + ",".join(format(float(v), ".6f") for v in query_embedding) + "]"
        filter_json = json.dumps(structural_filter) if structural_filter else None

        async with self._pool.acquire() as conn:
            await conn.execute(f"SET LOCAL statement_timeout = '{_RETRIEVAL_TIMEOUT}'")
            rows = await conn.fetch(
                HYBRID_SEARCH_SQL,
                embedding_literal,
                corpus_version,
                filter_json,
                candidates,
                query_text,
                s.rrf_k_constant,
                s.fusion_dense_weight,
                s.fusion_sparse_weight,
                final_top_k,
            )

        return [
            ChunkResult(
                chunk_id=row["id"],
                document_id=row["document_id"],
                content=row["content"],
                structural_meta=json.loads(row["structural_meta"])
                if isinstance(row["structural_meta"], str)
                else dict(row["structural_meta"]),
                dense_score=float(row["dense_score"]),
                sparse_score=float(row["sparse_score"]),
                rrf_score=float(row["rrf_score"]),
            )
            for row in rows
        ]
