"""Ingestion pipeline orchestrator.

For each source document:
    1. Compute idempotency key from (document_id, document_hash,
       chunker_version, corpus_version).
    2. If ingestion_runs already has a succeeded row for that key,
       skip (no-op re-ingest per ADR-0004).
    3. Otherwise, run Docling → StructuralMeta → Embedder → batch insert.
    4. Record the run outcome in ingestion_runs.

Fails closed: any exception inside a document's run records `failed`
with the error class + message and re-raises. The CronJob wrapper
treats any non-zero exit as a retriable failure (backoff configured in
env/ingestion.env).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from ingestion.protocols import (
    Chunker,
    EmbeddedChunk,
    Embedder,
    IngestionRepository,
    RawChunk,
    SourceDocument,
)
from ingestion.settings import IngestionSettings

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Coordinates the five stages per document."""

    def __init__(
        self,
        *,
        settings: IngestionSettings,
        chunker: Chunker,
        embedder: Embedder,
        repository: IngestionRepository,
        chunker_version: str,
    ) -> None:
        self._settings = settings
        self._chunker = chunker
        self._embedder = embedder
        self._repository = repository
        self._chunker_version = chunker_version

    async def run(self, documents: Iterable[SourceDocument]) -> PipelineReport:
        """Ingest every document; return a structured report of outcomes."""
        report = _MutableReport()
        for doc in documents:
            try:
                await self._ingest_one(doc, report)
            except Exception as exc:  # noqa: BLE001 — we re-record then re-raise
                await self._repository.record_run(
                    document_id=doc.document_id,
                    document_hash=doc.document_hash,
                    chunker_version=self._chunker_version,
                    embedder_model=self._settings.embedder_model,
                    corpus_version=self._settings.corpus_version,
                    status="failed",
                    error_class=type(exc).__name__,
                    error_message=str(exc)[:500],
                )
                report.failed.append(doc.document_id)
                logger.error(
                    "ingestion failed",
                    extra={
                        "document_id": doc.document_id,
                        "error_class": type(exc).__name__,
                    },
                )
                raise
        return report.freeze()

    async def _ingest_one(self, doc: SourceDocument, report: _MutableReport) -> None:
        if self._settings.idempotency_skip_if_unchanged and await self._repository.already_ingested(
            document_id=doc.document_id,
            document_hash=doc.document_hash,
            chunker_version=self._chunker_version,
            corpus_version=self._settings.corpus_version,
        ):
            logger.info(
                "ingestion skipped (idempotent)",
                extra={"document_id": doc.document_id},
            )
            report.skipped.append(doc.document_id)
            return

        raw_chunks = self._chunker.chunk(doc)
        self._enforce_quality_gates(doc.document_id, raw_chunks)

        embeddings = self._embedder.embed([c.text for c in raw_chunks])
        if len(embeddings) != len(raw_chunks):
            raise RuntimeError(
                f"embedder returned {len(embeddings)} vectors for "
                f"{len(raw_chunks)} chunks; cardinality mismatch"
            )

        embedded = tuple(
            EmbeddedChunk(
                text=chunk.text,
                meta=chunk.meta,
                token_count=chunk.token_count,
                embedding=embedding,
            )
            for chunk, embedding in zip(raw_chunks, embeddings, strict=True)
        )

        n_written = await self._repository.write_chunks(
            chunks=embedded,
            corpus_version=self._settings.corpus_version,
            embedding_model=self._settings.embedder_model,
        )
        await self._repository.record_run(
            document_id=doc.document_id,
            document_hash=doc.document_hash,
            chunker_version=self._chunker_version,
            embedder_model=self._settings.embedder_model,
            corpus_version=self._settings.corpus_version,
            status="succeeded",
            n_chunks=n_written,
        )
        report.succeeded.append(doc.document_id)
        logger.info(
            "ingestion succeeded",
            extra={"document_id": doc.document_id, "n_chunks": n_written},
        )

    def _enforce_quality_gates(self, document_id: str, chunks: Iterable[RawChunk]) -> None:
        chunks_list = list(chunks)
        n = len(chunks_list)
        s = self._settings

        if n < s.quality_min_chunks_per_doc:
            raise QualityGateFailed(
                document_id=document_id,
                reason="too_few_chunks",
                detail=f"{n} < {s.quality_min_chunks_per_doc}",
            )
        if n > s.quality_max_chunks_per_doc:
            raise QualityGateFailed(
                document_id=document_id,
                reason="too_many_chunks",
                detail=f"{n} > {s.quality_max_chunks_per_doc}",
            )
        if chunks_list:
            avg_tokens = sum(c.token_count for c in chunks_list) / n
            if avg_tokens < s.quality_min_avg_chunk_tokens:
                raise QualityGateFailed(
                    document_id=document_id,
                    reason="avg_tokens_too_low",
                    detail=f"{avg_tokens:.1f} < {s.quality_min_avg_chunk_tokens}",
                )


class QualityGateFailed(Exception):
    """A document's chunker output violated the configured quality gates."""

    def __init__(self, *, document_id: str, reason: str, detail: str) -> None:
        self.document_id = document_id
        self.reason = reason
        self.detail = detail
        super().__init__(f"{document_id}: {reason} ({detail})")


class PipelineReport:
    """Immutable outcome of one pipeline run across many documents."""

    __slots__ = ("succeeded", "skipped", "failed")

    def __init__(
        self,
        *,
        succeeded: tuple[str, ...],
        skipped: tuple[str, ...],
        failed: tuple[str, ...],
    ) -> None:
        self.succeeded = succeeded
        self.skipped = skipped
        self.failed = failed


class _MutableReport:
    """Internal accumulator used during a run."""

    def __init__(self) -> None:
        self.succeeded: list[str] = []
        self.skipped: list[str] = []
        self.failed: list[str] = []

    def freeze(self) -> PipelineReport:
        return PipelineReport(
            succeeded=tuple(self.succeeded),
            skipped=tuple(self.skipped),
            failed=tuple(self.failed),
        )
