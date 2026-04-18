"""Replace grades table with rubric+hash-chain shape for the Tier 3 UI.

Revision ID: 0004_grades
Revises: 0003_audit_chain
Create Date: 2026-04-18

The initial schema (0001_init) created a `grades` table with columns
keyed off `queries_audit.id` and score names (correctness, refusal, …)
that predate the finalised rubric. The Tier 3 labeling UI (issue #29)
uses the ADR-0006 rubric dimensions (accuracy, safety,
guideline_alignment, local_appropriateness, clarity), references cases
by `case_id` (not by queries_audit), and carries a SHA-256 hash chain
per reviewer.

Rather than ALTER ten columns on a table that has no production rows
yet (no environment has shipped labeling), we DROP the old grades and
CREATE the new one. The downgrade reverses both halves — it rebuilds
the 0001 shape so rollbacks still land on the same state as fresh
bootstrap.

Unlike `queries_audit`, the new `grades` permits UPDATE (raters
occasionally correct clerical errors). Any UPDATE breaks the hash
chain from that row forward; a chain-verification script walks the
chain per reviewer and flags the first broken row.

Companion to issue #29.
"""

from __future__ import annotations

from alembic import op

revision: str = "0004_grades"
down_revision: str | None = "0003_audit_chain"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


_UPGRADE_SQL = """
-- Drop the 0001 shape. No production data exists; no environment has
-- persisted grades yet. If that changes before 0004 ships to prod,
-- this migration must be rewritten as an in-place ALTER.
DROP TABLE IF EXISTS grades CASCADE;

CREATE TABLE grades (
    grade_id               UUID PRIMARY KEY,
    case_id                TEXT NOT NULL,
    reviewer_id            TEXT NOT NULL,
    reviewer_role          TEXT NOT NULL CHECK (
        reviewer_role IN ('clinical_reviewer', 'senior_clinician')
    ),
    rubric_version         TEXT NOT NULL,
    accuracy               SMALLINT NOT NULL CHECK (accuracy BETWEEN 1 AND 5),
    safety                 SMALLINT NOT NULL CHECK (safety BETWEEN 1 AND 5),
    guideline_alignment    SMALLINT NOT NULL CHECK (
        guideline_alignment BETWEEN 1 AND 5
    ),
    local_appropriateness  SMALLINT NOT NULL CHECK (
        local_appropriateness BETWEEN 1 AND 5
    ),
    clarity                SMALLINT NOT NULL CHECK (clarity BETWEEN 1 AND 5),
    notes                  TEXT NOT NULL DEFAULT '' CHECK (length(notes) <= 2000),
    time_spent_seconds     INT  NOT NULL CHECK (time_spent_seconds >= 0),
    submitted_at           TIMESTAMPTZ NOT NULL,
    prev_hash              TEXT NOT NULL DEFAULT '',
    row_hash               TEXT NOT NULL
);

COMMENT ON TABLE grades IS
    'Tier 3 clinician reviewer grades. One row per (reviewer, case) pair.';
COMMENT ON COLUMN grades.prev_hash IS
    'SHA-256 row_hash of this reviewer''s previous grade. Empty for first grade.';
COMMENT ON COLUMN grades.row_hash IS
    'SHA-256 over canonical payload + prev_hash. Computed in '
    'labeling.rubric.compute_row_hash.';

CREATE UNIQUE INDEX grades_reviewer_case_unique ON grades (reviewer_id, case_id);
CREATE INDEX grades_submitted_at ON grades (submitted_at);
CREATE INDEX grades_case_id ON grades (case_id);
CREATE INDEX grades_reviewer_submitted_at
    ON grades (reviewer_id, submitted_at DESC);

-- Least-privilege role. The 0001 grant on the old table was dropped
-- with the CASCADE above; we re-grant here for the new shape.
GRANT SELECT, INSERT, UPDATE ON grades TO afya_sahihi_app;
"""

_DOWNGRADE_SQL = """
DROP INDEX IF EXISTS grades_reviewer_submitted_at;
DROP INDEX IF EXISTS grades_case_id;
DROP INDEX IF EXISTS grades_submitted_at;
DROP INDEX IF EXISTS grades_reviewer_case_unique;
DROP TABLE IF EXISTS grades CASCADE;

-- Restore the 0001 shape so the schema matches a fresh bootstrap.
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
CREATE INDEX grades_query_audit_id ON grades (query_audit_id);
CREATE INDEX grades_reviewer_id ON grades (reviewer_id);
GRANT SELECT, INSERT ON grades TO afya_sahihi_app;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
