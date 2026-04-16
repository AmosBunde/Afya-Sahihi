"""asyncpg implementation of `IngestionRepository`.

Every query sets `SET LOCAL statement_timeout` (enforced by
scripts/hooks/check_asyncpg_timeouts.sh) and uses parameterized SQL per
SKILL.md §7. Writes happen inside an explicit transaction; a partial
batch is rolled back and the ingestion_runs row is marked `failed` so
the next invocation retries.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

import asyncpg

from ingestion.protocols import EmbeddedChunk

_INGESTION_TIMEOUT_MS = "30s"


class AsyncpgIngestionRepository:
    """Concrete repository. Construct once per process from the pool."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def already_ingested(
        self,
        *,
        document_id: str,
        document_hash: str,
        chunker_version: str,
        corpus_version: str,
    ) -> bool:
        async with self._pool.acquire() as conn:
            await conn.execute(f"SET LOCAL statement_timeout = '{_INGESTION_TIMEOUT_MS}'")
            row = await conn.fetchrow(
                """
                SELECT status FROM ingestion_runs
                WHERE document_id = $1
                  AND document_hash = $2
                  AND chunker_version = $3
                  AND corpus_version = $4
                  AND status = 'succeeded'
                LIMIT 1
                """,
                document_id,
                document_hash,
                chunker_version,
                corpus_version,
            )
            return row is not None

    async def record_run(
        self,
        *,
        document_id: str,
        document_hash: str,
        chunker_version: str,
        embedder_model: str,
        corpus_version: str,
        status: str,
        n_chunks: int | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(f"SET LOCAL statement_timeout = '{_INGESTION_TIMEOUT_MS}'")
            await conn.execute(
                """
                INSERT INTO ingestion_runs (
                    document_id, document_hash, chunker_version,
                    embedder_model, corpus_version, status,
                    n_chunks, error_class, error_message, finished_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
                ON CONFLICT (document_id, document_hash, chunker_version, corpus_version)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    n_chunks = EXCLUDED.n_chunks,
                    error_class = EXCLUDED.error_class,
                    error_message = EXCLUDED.error_message,
                    finished_at = EXCLUDED.finished_at
                """,
                document_id,
                document_hash,
                chunker_version,
                embedder_model,
                corpus_version,
                status,
                n_chunks,
                error_class,
                error_message,
            )

    async def write_chunks(
        self,
        *,
        chunks: Sequence[EmbeddedChunk],
        corpus_version: str,
        embedding_model: str,
    ) -> int:
        """Batch-insert chunks in one transaction.

        Returns the count actually written. Deterministic chunk IDs
        derive from (document_hash, chunk_index) so a retry after a
        partial failure writes the same primary keys and either
        succeeds-by-skip (via ON CONFLICT) or re-replaces the row.
        """
        if not chunks:
            return 0

        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(f"SET LOCAL statement_timeout = '{_INGESTION_TIMEOUT_MS}'")
            rows: list[tuple[str, str, str, str, str, str, str]] = []
            for idx, chunk in enumerate(chunks):
                chunk_id = _chunk_id(
                    document_hash=chunk.meta.source.document_hash,
                    chunk_index=idx,
                )
                rows.append(
                    (
                        chunk_id,
                        chunk.meta.source.document_id,
                        corpus_version,
                        chunk.text,
                        chunk.meta.model_dump_json(),
                        embedding_model,
                        _vector_literal(chunk.embedding),
                    )
                )

            # ON CONFLICT keeps re-ingest a no-op when the content did
            # not change; when it did, the deterministic ID still makes
            # the update safe. The `$7::vector` text cast avoids requiring
            # pgvector-python registration on every connection.
            await conn.executemany(
                """
                INSERT INTO chunks (
                    id, document_id, corpus_version, content,
                    structural_meta, embedding_model, embedding
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::vector)
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    structural_meta = EXCLUDED.structural_meta,
                    embedding = EXCLUDED.embedding,
                    embedding_model = EXCLUDED.embedding_model,
                    corpus_version = EXCLUDED.corpus_version
                """,
                rows,
            )
            return len(rows)


def _vector_literal(embedding: Sequence[float]) -> str:
    """Format a float sequence as pgvector's text representation.

    pgvector parses `[0.1,0.2,0.3]`. Using the text form and casting
    with `::vector` inside the SQL avoids requiring every connection
    to have `register_vector(conn)` called first, which is the detail
    that breaks on a pool where connections are recycled.
    """
    return "[" + ",".join(format(float(v), ".6f") for v in embedding) + "]"


def _chunk_id(*, document_hash: str, chunk_index: int) -> str:
    """Deterministic chunk ID: sha256 of (document_hash, chunk_index).

    Stable across re-ingests of the same PDF at the same Docling version,
    which is the property ON CONFLICT relies on for idempotency.
    """
    payload = json.dumps([document_hash, chunk_index], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
