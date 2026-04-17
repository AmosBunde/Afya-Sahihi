"""Integration tests: trigger enforcement + audit writer against real Postgres."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import asyncpg
import psycopg
import pytest

from alembic import command
from alembic.config import Config
from audit.writer import AuditWriter
from tests.conftest import PostgresHandle

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


def _sync_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture()
async def migrated_pool(
    postgres: PostgresHandle,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[asyncpg.Pool]:
    monkeypatch.setenv("AFYA_SAHIHI_DATABASE_URL", postgres.dsn)
    command.upgrade(_alembic_config(), "head")
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
        yield pool
    finally:
        await pool.close()
        command.downgrade(_alembic_config(), "base")


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "query_id": str(uuid4()),
        "trace_id": "trace-001",
        "query_text": "What is the dosing for artemether?",
        "query_language": "en",
        "classified_intent": "dosing",
        "prefilter_score": 0.92,
        "response_text": "Artemether 20mg per dose.",
        "retrieval_top1": 0.87,
        "conformal_set": None,
        "pipeline_status": "succeeded",
        "error_class": None,
        "latency_ms": 320,
        "corpus_version": "v1.0",
        "model_versions": {"27b": "v1"},
    }
    base.update(overrides)
    return base


# ---- Trigger enforcement ----


@pytest.mark.integration
def test_update_on_queries_audit_raises(
    postgres: PostgresHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AFYA_SAHIHI_DATABASE_URL", postgres.dsn)
    command.upgrade(_alembic_config(), "head")
    sync = _sync_dsn(postgres.dsn)
    with psycopg.connect(sync) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO queries_audit (
                trace_id, query_text, pipeline_status, corpus_version,
                prev_hash, row_hash
            ) VALUES ('t', 'text', 'succeeded', 'v1.0', '', 'h')
            """
        )
        conn.commit()
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cur.execute("UPDATE queries_audit SET query_text = 'tampered' WHERE id = 1")
    command.downgrade(_alembic_config(), "base")


@pytest.mark.integration
def test_delete_on_queries_audit_raises(
    postgres: PostgresHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AFYA_SAHIHI_DATABASE_URL", postgres.dsn)
    command.upgrade(_alembic_config(), "head")
    sync = _sync_dsn(postgres.dsn)
    with psycopg.connect(sync) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO queries_audit (
                trace_id, query_text, pipeline_status, corpus_version,
                prev_hash, row_hash
            ) VALUES ('t', 'text', 'succeeded', 'v1.0', '', 'h')
            """
        )
        conn.commit()
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            cur.execute("DELETE FROM queries_audit WHERE id = 1")
    command.downgrade(_alembic_config(), "base")


# ---- Audit writer with hash chain ----


@pytest.mark.integration
async def test_writer_inserts_with_hash_chain(migrated_pool: asyncpg.Pool) -> None:
    writer = AuditWriter(migrated_pool)
    await writer.write(payload=_payload())
    await writer.write(payload=_payload())

    async with migrated_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, prev_hash, row_hash FROM queries_audit ORDER BY id")

    assert len(rows) == 2
    assert rows[0]["prev_hash"] == ""
    assert rows[0]["row_hash"] != ""
    assert rows[1]["prev_hash"] == rows[0]["row_hash"]


@pytest.mark.integration
async def test_writer_scrubs_phi_before_insert(migrated_pool: asyncpg.Pool) -> None:
    writer = AuditWriter(migrated_pool)
    payload = _payload(query_text="patient: John Kamau, ID 12345678")
    row_id = await writer.write(payload=payload)

    async with migrated_pool.acquire() as conn:
        text = await conn.fetchval("SELECT query_text FROM queries_audit WHERE id = $1", row_id)

    assert "John Kamau" not in text
    assert "12345678" not in text
    assert "<REDACTED>" in text
