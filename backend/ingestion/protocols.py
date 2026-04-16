"""Protocol interfaces for the heavy components of the ingestion pipeline.

Docling and BGE-M3 are heavy optional dependencies (PyTorch, transformers,
~2 GB of models). Tests and the non-runtime path should not need them
installed. Define Protocols here; the real implementations live in
`docling_chunker.py` and `embedder.py` and are imported lazily in
`__main__.py`. Unit tests supply in-memory fakes.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from ingestion.structural_meta import StructuralMeta


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """One PDF plus its content hash, read from the corpus bucket."""

    document_id: str
    document_hash: str
    pdf_bytes: bytes


@dataclass(frozen=True, slots=True)
class RawChunk:
    """Chunker output: text + structural metadata, no embedding yet."""

    text: str
    meta: StructuralMeta
    token_count: int


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """Chunker output plus its dense embedding."""

    text: str
    meta: StructuralMeta
    token_count: int
    embedding: tuple[float, ...]


class PdfSource(Protocol):
    """Iterates the source bucket and yields `SourceDocument`s.

    Implementations: S3Source for production (reads from MinIO via the
    manifest), LocalSource for `samples/moh-mini/` integration runs.
    """

    def __iter__(self) -> Iterable[SourceDocument]: ...


class Chunker(Protocol):
    """Turn one PDF into a sequence of `RawChunk`s with structural metadata.

    The real implementation wraps Docling's HybridChunker. A fake can
    return deterministic chunks for unit tests without loading Docling.
    """

    def chunk(self, document: SourceDocument) -> Sequence[RawChunk]: ...


class Embedder(Protocol):
    """Embed a batch of chunks to dense vectors.

    The real implementation wraps BGE-M3 with matryoshka truncation to the
    configured `embedder_matryoshka_dim`. A fake returns a fixed vector
    for unit tests.
    """

    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]: ...


class IngestionRepository(Protocol):
    """Persist ingested chunks and idempotency state.

    The real implementation uses asyncpg; the contract is small enough
    that a sync in-memory fake is viable for unit tests.
    """

    async def already_ingested(
        self,
        *,
        document_id: str,
        document_hash: str,
        chunker_version: str,
        corpus_version: str,
    ) -> bool: ...

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
    ) -> None: ...

    async def write_chunks(
        self,
        *,
        chunks: Sequence[EmbeddedChunk],
        corpus_version: str,
        embedding_model: str,
    ) -> int: ...
