"""Unit tests for the ingestion pipeline orchestration.

Uses in-memory fakes for every Protocol (Chunker, Embedder, Repository)
so the tests run in milliseconds without Postgres or PyTorch. What is
under test here is the orchestration: idempotency checks, quality gate
enforcement, record_run bookkeeping on success AND failure, report
shape on mixed outcomes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from ingestion.pipeline import IngestionPipeline, QualityGateFailed
from ingestion.protocols import (
    Chunker,
    EmbeddedChunk,
    Embedder,
    IngestionRepository,
    RawChunk,
    SourceDocument,
)
from ingestion.settings import IngestionSettings
from ingestion.structural_meta import (
    SourceMeta,
    StructuralMeta,
    StructureMeta,
)

_EMBEDDING_DIM = 8  # small; pipeline does not check dim, only cardinality


# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class _FakeChunker(Chunker):
    def __init__(self, chunks_per_doc: int = 5, token_count: int = 100) -> None:
        self._n = chunks_per_doc
        self._tokens = token_count

    def chunk(self, document: SourceDocument) -> Sequence[RawChunk]:
        meta = StructuralMeta(
            source=SourceMeta(
                document_id=document.document_id,
                document_hash=document.document_hash,
                page_range=(1, 1),
            ),
            structure=StructureMeta(),
            extraction_version="fake-1.0",
        )
        return [RawChunk(text=f"c{i}", meta=meta, token_count=self._tokens) for i in range(self._n)]


class _FakeEmbedder(Embedder):
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return tuple(tuple(float(i) for i in range(_EMBEDDING_DIM)) for _ in texts)


class _BrokenEmbedder(Embedder):
    """Returns one fewer vector than texts, to exercise cardinality check."""

    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return tuple(tuple(0.0 for _ in range(_EMBEDDING_DIM)) for _ in texts[:-1])


@dataclass
class _FakeRepository(IngestionRepository):
    already_ingested_returns: bool = False
    recorded: list[dict[str, object]] = field(default_factory=list)
    written_chunks: list[EmbeddedChunk] = field(default_factory=list)

    async def already_ingested(
        self,
        *,
        document_id: str,
        document_hash: str,
        chunker_version: str,
        corpus_version: str,
    ) -> bool:
        return self.already_ingested_returns

    async def record_run(self, **kwargs: object) -> None:
        self.recorded.append(kwargs)

    async def write_chunks(
        self,
        *,
        chunks: Sequence[EmbeddedChunk],
        corpus_version: str,
        embedding_model: str,
    ) -> int:
        self.written_chunks.extend(chunks)
        return len(chunks)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _settings(**overrides: object) -> IngestionSettings:
    base: dict[str, object] = dict(
        source_bucket="test-bucket",
        source_manifest_path="s3://test/manifest.yaml",
        pg_host="localhost",
        pg_database="afya_sahihi_test",
        pg_user="postgres",
        pg_password="test",
        # Keep quality gates lenient by default
        quality_min_chunks_per_doc=1,
        quality_max_chunks_per_doc=100,
        quality_min_avg_chunk_tokens=1,
    )
    base.update(overrides)
    return IngestionSettings.model_validate(base)


def _doc(doc_id: str = "doc1", doc_hash: str = "sha256:hhh") -> SourceDocument:
    return SourceDocument(document_id=doc_id, document_hash=doc_hash, pdf_bytes=b"%PDF-")


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_happy_path_writes_chunks_and_records_success() -> None:
    repo = _FakeRepository()
    pipeline = IngestionPipeline(
        settings=_settings(),
        chunker=_FakeChunker(chunks_per_doc=3),
        embedder=_FakeEmbedder(),
        repository=repo,
        chunker_version="hybrid-2.9.0",
    )

    report = await pipeline.run([_doc()])

    assert report.succeeded == ("doc1",)
    assert report.skipped == ()
    assert report.failed == ()
    assert len(repo.written_chunks) == 3
    assert repo.recorded[-1]["status"] == "succeeded"
    assert repo.recorded[-1]["n_chunks"] == 3


@pytest.mark.asyncio
async def test_idempotent_skip_when_already_ingested() -> None:
    repo = _FakeRepository(already_ingested_returns=True)
    pipeline = IngestionPipeline(
        settings=_settings(),
        chunker=_FakeChunker(),
        embedder=_FakeEmbedder(),
        repository=repo,
        chunker_version="hybrid-2.9.0",
    )

    report = await pipeline.run([_doc()])

    assert report.skipped == ("doc1",)
    assert repo.written_chunks == []
    # `record_run` is not called on a skip; nothing to record beyond
    # the existing success row that triggered the skip.
    assert repo.recorded == []


@pytest.mark.asyncio
async def test_quality_gate_rejects_too_few_chunks() -> None:
    pipeline = IngestionPipeline(
        settings=_settings(quality_min_chunks_per_doc=10),
        chunker=_FakeChunker(chunks_per_doc=3),
        embedder=_FakeEmbedder(),
        repository=_FakeRepository(),
        chunker_version="hybrid-2.9.0",
    )

    with pytest.raises(QualityGateFailed) as exc:
        await pipeline.run([_doc()])
    assert exc.value.reason == "too_few_chunks"


@pytest.mark.asyncio
async def test_embedder_cardinality_mismatch_fails_closed() -> None:
    repo = _FakeRepository()
    pipeline = IngestionPipeline(
        settings=_settings(),
        chunker=_FakeChunker(chunks_per_doc=3),
        embedder=_BrokenEmbedder(),
        repository=repo,
        chunker_version="hybrid-2.9.0",
    )

    with pytest.raises(RuntimeError, match="cardinality mismatch"):
        await pipeline.run([_doc()])
    # Failure was recorded before the re-raise.
    assert repo.recorded[-1]["status"] == "failed"
    assert repo.recorded[-1]["error_class"] == "RuntimeError"
