"""Integration tests for AsyncpgIngestionRepository against real Postgres."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

from alembic import command
from alembic.config import Config
from ingestion.protocols import EmbeddedChunk
from ingestion.repository import AsyncpgIngestionRepository, _vector_literal
from ingestion.structural_meta import (
    SourceMeta,
    StructuralMeta,
    StructureMeta,
)
from tests.conftest import PostgresHandle

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture()
async def migrated_pool(
    postgres: PostgresHandle,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[asyncpg.Pool]:
    monkeypatch.setenv("AFYA_SAHIHI_DATABASE_URL", postgres.dsn)
    command.upgrade(_alembic_config(), "head")
    try:
        pool = await asyncpg.create_pool(
            host=postgres.host,
            port=postgres.port,
            database=postgres.database,
            user=postgres.user,
            password=postgres.password,
            min_size=1,
            max_size=2,
        )
        yield pool
    finally:
        await pool.close()
        command.downgrade(_alembic_config(), "base")


def _embedded(idx: int, doc_id: str = "doc1", doc_hash: str = "sha256:aaa") -> EmbeddedChunk:
    meta = StructuralMeta(
        source=SourceMeta(
            document_id=doc_id,
            document_hash=doc_hash,
            page_range=(1, 1),
        ),
        structure=StructureMeta(),
        extraction_version="fake-1.0",
    )
    return EmbeddedChunk(
        text=f"chunk {idx}",
        meta=meta,
        token_count=42,
        embedding=tuple(float(i) for i in range(768)),
    )


def test_vector_literal_matches_pgvector_format() -> None:
    lit = _vector_literal((0.0, 0.5, -0.25))
    assert lit == "[0.000000,0.500000,-0.250000]"


@pytest.mark.integration
async def test_already_ingested_returns_false_when_no_row(
    migrated_pool: asyncpg.Pool,
) -> None:
    repo = AsyncpgIngestionRepository(migrated_pool)
    assert (
        await repo.already_ingested(
            document_id="doc1",
            document_hash="sha256:aaa",
            chunker_version="hybrid-2.9.0",
            corpus_version="v1.0",
        )
        is False
    )


@pytest.mark.integration
async def test_record_run_then_already_ingested_true(
    migrated_pool: asyncpg.Pool,
) -> None:
    repo = AsyncpgIngestionRepository(migrated_pool)
    await repo.record_run(
        document_id="doc1",
        document_hash="sha256:aaa",
        chunker_version="hybrid-2.9.0",
        embedder_model="BAAI/bge-m3",
        corpus_version="v1.0",
        status="succeeded",
        n_chunks=3,
    )
    assert (
        await repo.already_ingested(
            document_id="doc1",
            document_hash="sha256:aaa",
            chunker_version="hybrid-2.9.0",
            corpus_version="v1.0",
        )
        is True
    )


@pytest.mark.integration
async def test_write_chunks_is_idempotent_on_replay(
    migrated_pool: asyncpg.Pool,
) -> None:
    repo = AsyncpgIngestionRepository(migrated_pool)
    chunks = [_embedded(i) for i in range(4)]
    first = await repo.write_chunks(
        chunks=chunks, corpus_version="v1.0", embedding_model="BAAI/bge-m3"
    )
    second = await repo.write_chunks(
        chunks=chunks, corpus_version="v1.0", embedding_model="BAAI/bge-m3"
    )
    assert first == 4
    assert second == 4

    async with migrated_pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM chunks WHERE document_id = $1", "doc1")
    # Replay should not create duplicate rows — ON CONFLICT (id) makes the
    # second call an in-place update of the same 4 chunks.
    assert count == 4
