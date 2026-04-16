"""Verify the initial schema migration applies and rolls back cleanly.

The migration is raw DDL (no autogen), so these tests assert behaviour we
actually care about: tables exist with the right columns, indexes are
queryable, the least-privilege role is created, and `downgrade` then
`upgrade` again is idempotent. They run against a real Postgres — the
ParadeDB image bundles pgvector + pg_search so `CREATE EXTENSION` for
both succeeds.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from alembic import command
from alembic.config import Config
from tests.conftest import PostgresHandle

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic_config(dsn: str) -> Config:
    """Return an Alembic Config pointed at the repo's alembic.ini + DSN."""
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    # env.py reads AFYA_SAHIHI_DATABASE_URL from the environment; the
    # fixtures below set it. The Config's sqlalchemy.url is ignored by
    # env.py on purpose so there is a single source of truth.
    return cfg


def _sync_dsn(dsn: str) -> str:
    """Strip the driver prefix so psycopg.connect accepts the URL."""
    return dsn.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture()
def alembic_env(postgres: PostgresHandle, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Provide an Alembic Config whose env.py will read the test DSN."""
    monkeypatch.setenv("AFYA_SAHIHI_DATABASE_URL", postgres.dsn)
    return _alembic_config(postgres.dsn)


@pytest.mark.integration
def test_upgrade_head_creates_every_core_table(
    alembic_env: Config, postgres: PostgresHandle
) -> None:
    command.upgrade(alembic_env, "head")

    with psycopg.connect(_sync_dsn(postgres.dsn)) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
        tables = {row[0] for row in cur.fetchall()}

    expected = {"chunks", "queries_audit", "calibration_set", "grades", "eval_runs"}
    missing = expected - tables
    assert not missing, f"upgrade did not create: {missing}"


@pytest.mark.integration
def test_upgrade_head_loads_extensions(alembic_env: Config, postgres: PostgresHandle) -> None:
    command.upgrade(alembic_env, "head")

    with psycopg.connect(_sync_dsn(postgres.dsn)) as conn, conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension")
        extensions = {row[0] for row in cur.fetchall()}

    # pg_cron may not load in a container without shared_preload_libraries;
    # the migration's CREATE EXTENSION IF NOT EXISTS tolerates that, and
    # the test asserts only the extensions that are mandatory for data
    # operations to succeed.
    required = {"vector", "pg_search", "pgcrypto"}
    missing = required - extensions
    assert not missing, f"missing extensions: {missing}"


@pytest.mark.integration
def test_chunks_hnsw_and_bm25_indexes_exist(alembic_env: Config, postgres: PostgresHandle) -> None:
    command.upgrade(alembic_env, "head")

    with psycopg.connect(_sync_dsn(postgres.dsn)) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'chunks'
            """
        )
        indexes = {name: defn for name, defn in cur.fetchall()}

    assert "chunks_embedding_hnsw" in indexes, "HNSW index missing"
    assert "hnsw" in indexes["chunks_embedding_hnsw"].lower()
    assert "chunks_content_bm25" in indexes, "BM25 index missing"
    assert "chunks_structural_meta_gin" in indexes, "JSONB GIN index missing"


@pytest.mark.integration
def test_least_privilege_role_is_created(alembic_env: Config, postgres: PostgresHandle) -> None:
    command.upgrade(alembic_env, "head")

    with psycopg.connect(_sync_dsn(postgres.dsn)) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT rolsuper, rolcreatedb, rolcreaterole
            FROM pg_roles WHERE rolname = 'afya_sahihi_app'
            """
        )
        row = cur.fetchone()

    assert row is not None, "afya_sahihi_app role was not created"
    rolsuper, rolcreatedb, rolcreaterole = row
    assert not rolsuper, "app role must not be superuser"
    assert not rolcreatedb, "app role must not create databases"
    assert not rolcreaterole, "app role must not create other roles"


@pytest.mark.integration
def test_downgrade_then_upgrade_is_idempotent(
    alembic_env: Config, postgres: PostgresHandle
) -> None:
    command.upgrade(alembic_env, "head")
    command.downgrade(alembic_env, "base")

    with psycopg.connect(_sync_dsn(postgres.dsn)) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
              -- Exclude tables that belong to Alembic's own bookkeeping
              -- and to extensions the image ships with by default
              -- (ParadeDB bundles PostGIS, which creates spatial_ref_sys).
              AND tablename NOT IN ('alembic_version', 'spatial_ref_sys')
            """
        )
        assert not cur.fetchall(), "downgrade left tables behind"

    # Re-apply; idempotency of CREATE EXTENSION IF NOT EXISTS plus the
    # role guard means this must succeed without manual cleanup.
    command.upgrade(alembic_env, "head")
