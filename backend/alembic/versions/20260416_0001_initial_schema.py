"""Initial schema: extensions, roles, core tables, retrieval indexes.

Revision ID: 0001_init
Revises:
Create Date: 2026-04-16

Companion to ADR-0002 (Postgres 16 with pgvector and pg_search) and
issue #11. The migration is intentionally raw SQL via `op.execute` so the
DDL can be copy-pasted into `psql` verbatim for debugging.

Extensions loaded:
    pgvector            — dense vector storage + HNSW index
    pg_search           — BM25 lexical index (ParadeDB)
    pgcrypto            — gen_random_uuid and column-level encryption
    pg_stat_statements  — query-level telemetry
    pg_cron             — scheduled maintenance

pg_cron additionally requires `shared_preload_libraries='pg_cron'` at
Postgres startup; that configuration lives in the k3s ConfigMap/StatefulSet
(issue #14) and is not something a migration can set.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


# --------------------------------------------------------------------------- #
# Upgrade                                                                     #
# --------------------------------------------------------------------------- #


_EXTENSIONS_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_search;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
-- pg_cron requires shared_preload_libraries='pg_cron' at server start.
-- The CREATE EXTENSION succeeds regardless; job rows added later only
-- execute when the server is correctly configured.
CREATE EXTENSION IF NOT EXISTS pg_cron;
"""

# Least-privilege application role. Owns no objects; has only SELECT +
# INSERT/UPDATE on the named tables. Granted fresh here so the role is
# recreated idempotently if dropped.
_APP_ROLE_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'afya_sahihi_app') THEN
        CREATE ROLE afya_sahihi_app LOGIN
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
    END IF;
END
$$;
"""

_CHUNKS_SQL = """
CREATE TABLE chunks (
    id                TEXT PRIMARY KEY,
    document_id       TEXT NOT NULL,
    corpus_version    TEXT NOT NULL,
    content           TEXT NOT NULL,
    structural_meta   JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding         vector(768),
    embedding_model   TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE chunks IS
    'Retrieval corpus. One row per Docling chunk; see ADR-0004.';
COMMENT ON COLUMN chunks.embedding IS
    'MedGemma text embedding, 768 dims. Model name in embedding_model.';
COMMENT ON COLUMN chunks.structural_meta IS
    'Docling structural metadata. JSON schema in backend/app/state.py.';

-- HNSW index for dense ANN retrieval. Params from SKILL.md §7 and the
-- pgvector HNSW recommendations for a 500k-row corpus.
CREATE INDEX chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- BM25 index for sparse lexical retrieval via ParadeDB's pg_search.
CREATE INDEX chunks_content_bm25
    ON chunks USING bm25 (id, content)
    WITH (key_field='id');

-- JSONB GIN for structural filter pushdown (section_path, source.page_range).
CREATE INDEX chunks_structural_meta_gin
    ON chunks USING gin (structural_meta jsonb_path_ops);

-- Corpus version index for cheap swaps.
CREATE INDEX chunks_corpus_version
    ON chunks (corpus_version);
"""

# Audit log. Hash-chained rows land with issue #13; this table is the
# canonical shape but without the hash_chain column yet (that column is
# added in a later migration so #13's tests can drive its design).
_QUERIES_AUDIT_SQL = """
CREATE TABLE queries_audit (
    id                BIGSERIAL PRIMARY KEY,
    query_id          UUID NOT NULL DEFAULT gen_random_uuid(),
    trace_id          TEXT NOT NULL,
    query_text        TEXT NOT NULL,
    query_language    TEXT,
    classified_intent TEXT,
    prefilter_score   DOUBLE PRECISION,
    response_text     TEXT,
    retrieval_top1    DOUBLE PRECISION,
    conformal_set     JSONB,
    pipeline_status   TEXT NOT NULL,
    error_class       TEXT,
    latency_ms        INTEGER,
    corpus_version    TEXT NOT NULL,
    model_versions    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE queries_audit IS
    'One row per clinical query. query_text is PHI-scrubbed before write; '
    'see backend/app/validation/phi.py (issue #24). A hash_chain column '
    'will be added by issue #13 to detect tampering.';
CREATE INDEX queries_audit_created_at ON queries_audit (created_at DESC);
CREATE INDEX queries_audit_query_id ON queries_audit (query_id);
CREATE INDEX queries_audit_status ON queries_audit (pipeline_status);
"""

# Calibration set for conformal prediction (issue #25).
_CALIBRATION_SET_SQL = """
CREATE TABLE calibration_set (
    id                   BIGSERIAL PRIMARY KEY,
    query_audit_id       BIGINT REFERENCES queries_audit(id) ON DELETE SET NULL,
    nonconformity_score  DOUBLE PRECISION NOT NULL,
    score_type           TEXT NOT NULL,
    stratum              TEXT NOT NULL,
    ground_truth_label   TEXT,
    included_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE calibration_set IS
    'Held-out calibration scores for conformal prediction. '
    'Stratified by stratum (intent category, query language, etc).';
CREATE INDEX calibration_set_score_type_stratum
    ON calibration_set (score_type, stratum);
CREATE INDEX calibration_set_included_at
    ON calibration_set (included_at DESC);
"""

# Clinician grades (issue #29 Streamlit reviewer UI).
_GRADES_SQL = """
CREATE TABLE grades (
    id                BIGSERIAL PRIMARY KEY,
    query_audit_id    BIGINT NOT NULL REFERENCES queries_audit(id)
                        ON DELETE CASCADE,
    reviewer_id       TEXT NOT NULL,
    rubric_version    TEXT NOT NULL,
    score_correctness INTEGER NOT NULL CHECK (score_correctness BETWEEN 1 AND 5),
    score_safety      INTEGER NOT NULL CHECK (score_safety BETWEEN 1 AND 5),
    score_citation    INTEGER NOT NULL CHECK (score_citation BETWEEN 1 AND 5),
    score_clarity     INTEGER NOT NULL CHECK (score_clarity BETWEEN 1 AND 5),
    score_refusal     INTEGER NOT NULL CHECK (score_refusal BETWEEN 1 AND 5),
    reviewer_notes    TEXT,
    graded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE grades IS
    'Clinician grades on the 5-point rubric. One row per (query, reviewer, '
    'rubric_version) tuple; duplicates expected when two clinicians grade '
    'the same query for inter-rater agreement.';
CREATE INDEX grades_query_audit_id ON grades (query_audit_id);
CREATE INDEX grades_reviewer_id ON grades (reviewer_id);
"""

# Eval-run telemetry for Inspect AI tiers (issues #27 and #28).
_EVAL_RUNS_SQL = """
CREATE TABLE eval_runs (
    id               BIGSERIAL PRIMARY KEY,
    tier             TEXT NOT NULL CHECK (tier IN ('tier1', 'tier2', 'tier3')),
    task_name        TEXT NOT NULL,
    git_sha          TEXT NOT NULL,
    corpus_version   TEXT NOT NULL,
    model_versions   JSONB NOT NULL DEFAULT '{}'::jsonb,
    status           TEXT NOT NULL,
    n_samples        INTEGER,
    aggregate_scores JSONB,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ
);
COMMENT ON TABLE eval_runs IS
    'One row per Inspect AI invocation. aggregate_scores is the per-metric '
    'result keyed by metric name (accuracy, coverage, set_size, etc).';
CREATE INDEX eval_runs_tier_started_at ON eval_runs (tier, started_at DESC);
CREATE INDEX eval_runs_git_sha ON eval_runs (git_sha);
"""

# Grant the least-privilege role only what each table needs.
_GRANTS_SQL = """
GRANT USAGE ON SCHEMA public TO afya_sahihi_app;
GRANT SELECT                      ON chunks           TO afya_sahihi_app;
GRANT SELECT, INSERT              ON queries_audit    TO afya_sahihi_app;
GRANT SELECT, INSERT              ON calibration_set  TO afya_sahihi_app;
GRANT SELECT, INSERT              ON grades           TO afya_sahihi_app;
GRANT SELECT, INSERT, UPDATE      ON eval_runs        TO afya_sahihi_app;
-- Sequences backing BIGSERIAL primary keys.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO afya_sahihi_app;
-- Deny by default on future objects; migrations reset grants explicitly.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM afya_sahihi_app;
"""


def upgrade() -> None:
    op.execute(_EXTENSIONS_SQL)
    op.execute(_APP_ROLE_SQL)
    op.execute(_CHUNKS_SQL)
    op.execute(_QUERIES_AUDIT_SQL)
    op.execute(_CALIBRATION_SET_SQL)
    op.execute(_GRADES_SQL)
    op.execute(_EVAL_RUNS_SQL)
    op.execute(_GRANTS_SQL)


# --------------------------------------------------------------------------- #
# Downgrade                                                                   #
# --------------------------------------------------------------------------- #


_DOWNGRADE_SQL = """
DROP TABLE IF EXISTS eval_runs CASCADE;
DROP TABLE IF EXISTS grades CASCADE;
DROP TABLE IF EXISTS calibration_set CASCADE;
DROP TABLE IF EXISTS queries_audit CASCADE;
DROP TABLE IF EXISTS chunks CASCADE;

-- Role teardown. If any object still references the role the drop fails;
-- that is deliberate (fail-closed) because orphan-owning a role is worse
-- than a failed downgrade.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'afya_sahihi_app') THEN
        REVOKE ALL PRIVILEGES ON SCHEMA public FROM afya_sahihi_app;
        DROP ROLE afya_sahihi_app;
    END IF;
END
$$;

-- Extensions remain: CREATE EXTENSION is idempotent and dropping them
-- would break other databases that share the cluster. Downgrade is
-- about schema, not shared infrastructure.
"""


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
