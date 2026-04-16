"""Ingestion idempotency tracking.

Revision ID: 0002_ingestion
Revises: 0001_init
Create Date: 2026-04-16

Companion to issue #12. Adds the `ingestion_runs` table so the pipeline
can decide, before running Docling, whether a (document_id, document_hash,
chunker_version) tuple has already been ingested into the current
`corpus_version`. This is the "Re-ingest is a no-op on unchanged input"
acceptance item.

The migration also grants INSERT/UPDATE/SELECT on `ingestion_runs` to
`afya_sahihi_app`. Ingestion still runs as an offline CronJob (ADR-0004
keeps ingestion off the request path), but the CronJob authenticates as
the same role to honour least-privilege.
"""

from __future__ import annotations

from alembic import op

revision: str = "0002_ingestion"
down_revision: str | None = "0001_init"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


_INGESTION_RUNS_SQL = """
CREATE TABLE ingestion_runs (
    id                  BIGSERIAL PRIMARY KEY,
    document_id         TEXT NOT NULL,
    document_hash       TEXT NOT NULL,
    chunker_version     TEXT NOT NULL,
    embedder_model      TEXT NOT NULL,
    corpus_version      TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN (
        'pending', 'running', 'succeeded', 'failed', 'skipped'
    )),
    n_chunks            INTEGER,
    error_class         TEXT,
    error_message       TEXT,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    UNIQUE (document_id, document_hash, chunker_version, corpus_version)
);
COMMENT ON TABLE ingestion_runs IS
    'One row per (document, hash, chunker, corpus) attempt. The UNIQUE '
    'constraint is the idempotency guard — the pipeline reads this table '
    'before calling Docling and skips when a succeeded row exists.';

CREATE INDEX ingestion_runs_document_id ON ingestion_runs (document_id);
CREATE INDEX ingestion_runs_status_started_at
    ON ingestion_runs (status, started_at DESC);
"""

_GRANTS_SQL = """
GRANT SELECT, INSERT, UPDATE ON ingestion_runs TO afya_sahihi_app;
GRANT USAGE, SELECT ON SEQUENCE ingestion_runs_id_seq TO afya_sahihi_app;
"""


def upgrade() -> None:
    op.execute(_INGESTION_RUNS_SQL)
    op.execute(_GRANTS_SQL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_runs CASCADE;")
