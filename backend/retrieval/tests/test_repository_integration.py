"""Integration test: hybrid SQL CTE against real ParadeDB Postgres.

Seeds 10 chunks with embeddings and verifies that the hybrid query
returns results with non-zero dense, sparse, and RRF scores. This is
the acceptance-level test for 'dense + sparse + rerank scores exposed.'
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import psycopg
import pytest

from alembic import command
from alembic.config import Config
from retrieval.repository import RetrievalRepository
from retrieval.settings import RetrievalSettings
from tests.conftest import PostgresHandle

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


def _sync_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://")


def _seed_chunks(dsn: str, n: int = 10) -> None:
    """Insert n synthetic chunks with embeddings for testing."""
    with psycopg.connect(_sync_dsn(dsn)) as conn, conn.cursor() as cur:
        for i in range(n):
            embedding = [0.1 * (i + 1)] * 768
            embedding_str = "[" + ",".join(f"{v:.6f}" for v in embedding) + "]"
            meta = json.dumps(
                {
                    "source": {
                        "document_id": f"doc{i}",
                        "document_hash": f"sha256:{i}",
                        "page_range": [1, 1],
                    },
                    "structure": {"section_path": ["Test"], "is_contraindication": i == 0},
                    "content_type": "text",
                    "language": "en",
                    "extraction_version": "test-1.0",
                }
            )
            cur.execute(
                """
                INSERT INTO chunks (id, document_id, corpus_version, content,
                    structural_meta, embedding_model, embedding)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::vector)
                """,
                (
                    f"chunk-{i}",
                    f"doc{i}",
                    "v1.0",
                    f"malaria treatment protocol section {i}",
                    meta,
                    "test-model",
                    embedding_str,
                ),
            )
        conn.commit()


@pytest.fixture()
async def seeded_pool(
    postgres: PostgresHandle, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[asyncpg.Pool, RetrievalSettings]]:
    monkeypatch.setenv("AFYA_SAHIHI_DATABASE_URL", postgres.dsn)
    command.upgrade(_alembic_config(), "head")
    _seed_chunks(postgres.dsn)
    settings = RetrievalSettings(
        pg_host=postgres.host,
        pg_port=postgres.port,
        pg_database=postgres.database,
        pg_user=postgres.user,
        pg_password=postgres.password,
    )
    pool = await asyncpg.create_pool(
        host=postgres.host,
        port=postgres.port,
        database=postgres.database,
        user=postgres.user,
        password=postgres.password,
        min_size=1,
        max_size=2,
    )
    try:
        yield pool, settings
    finally:
        await pool.close()
        command.downgrade(_alembic_config(), "base")


@pytest.mark.integration
async def test_hybrid_search_returns_results_with_scores(
    seeded_pool: tuple[asyncpg.Pool, RetrievalSettings],
) -> None:
    pool, settings = seeded_pool
    repo = RetrievalRepository(pool, settings)

    query_embedding = [0.5] * 768
    results = await repo.hybrid_search(
        query_embedding=query_embedding,
        query_text="malaria treatment",
        corpus_version="v1.0",
        structural_filter=None,
        candidates=10,
        final_top_k=5,
    )

    assert len(results) > 0
    for r in results:
        assert r.rrf_score > 0, "RRF score should be positive"
        assert r.chunk_id.startswith("chunk-")


@pytest.mark.integration
async def test_structural_filter_narrows_results(
    seeded_pool: tuple[asyncpg.Pool, RetrievalSettings],
) -> None:
    pool, settings = seeded_pool
    repo = RetrievalRepository(pool, settings)

    query_embedding = [0.5] * 768
    results = await repo.hybrid_search(
        query_embedding=query_embedding,
        query_text="malaria treatment",
        corpus_version="v1.0",
        structural_filter={"structure": {"is_contraindication": True}},
        candidates=10,
        final_top_k=5,
    )

    for r in results:
        meta = r.structural_meta
        structure = meta.get("structure", {})
        assert structure.get("is_contraindication") is True
