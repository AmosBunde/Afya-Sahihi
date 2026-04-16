"""pytest fixtures shared across unit and integration tests.

Integration tests rely on a live Postgres with the ParadeDB extensions
(pgvector + pg_search). The fixture prefers an externally-provided
\`AFYA_SAHIHI_TEST_DATABASE_URL\` — populated by the CI service container —
and falls back to spinning up a container locally via testcontainers.
Either way, the fixture returns the Alembic-ready DSN and the raw host/
port components the test may need.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass

import pytest


@dataclass(frozen=True, slots=True)
class PostgresHandle:
    """Connection parameters for a test Postgres instance."""

    dsn: str
    host: str
    port: int
    user: str
    password: str
    database: str


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresHandle]:
    """Provide a Postgres instance with pgvector + pg_search loaded.

    - If AFYA_SAHIHI_TEST_DATABASE_URL is set, trust it and yield (CI path).
    - Otherwise, start a testcontainers ParadeDB container (local-dev path).

    The container is scoped to the full test session so extension loading
    and migration replay happens once, not per test.
    """
    external = os.environ.get("AFYA_SAHIHI_TEST_DATABASE_URL")
    if external:
        # CI path: the service container is managed by GitHub Actions.
        # The DSN format follows the standard postgres URL shape; see the
        # DSN set by env/gateway.env AFYA_SAHIHI_DATABASE_URL.
        # We deconstruct it only for the handful of tests that need the
        # parts; most tests use `handle.dsn` unchanged.
        from urllib.parse import urlparse

        parsed = urlparse(external.replace("postgresql+psycopg://", "postgresql://"))
        yield PostgresHandle(
            dsn=external,
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            user=parsed.username or "postgres",
            password=parsed.password or "",
            database=(parsed.path or "/postgres").lstrip("/"),
        )
        return

    # Local-dev path: import testcontainers lazily so CI (which does not
    # need it) does not pay the import cost.
    from testcontainers.postgres import PostgresContainer

    # ParadeDB image bundles pgvector + pg_search against Postgres 16.
    # pgcrypto and pg_stat_statements are in the stock contrib set and
    # available by default. pg_cron needs shared_preload_libraries, which
    # we do not enable here; the migration's CREATE EXTENSION is
    # idempotent and the test only asserts structure, not that cron jobs
    # actually fire.
    container = PostgresContainer(image="paradedb/paradedb:latest-pg16")
    container.start()
    try:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(5432))
        user = container.username
        password = container.password
        database = container.dbname
        dsn = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"
        yield PostgresHandle(
            dsn=dsn,
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
    finally:
        container.stop()
