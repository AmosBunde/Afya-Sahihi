"""Grades table with hash-chain chain-of-custody.

Revision ID: 0004_grades
Revises: 0003_audit_chain
Create Date: 2026-04-18

Stores the Tier 3 clinician reviewer grades per case. The rubric has
five dimensions, each a 1-5 Likert integer (enforced via CHECK). Each
row carries `prev_hash` and `row_hash` that form a chain per reviewer:
a reviewer's next grade's prev_hash must equal the previous grade's
row_hash, making tampering detectable offline.

Unlike `queries_audit`, `grades` permits UPDATE (raters occasionally
correct clerical errors on their own grades) — but every UPDATE breaks
the hash chain from that point forward. A chain-verification script
(scripts/labeling/verify_grade_chain.py, landing with issue #29) walks
the chain per reviewer and flags the first broken row.

Companion to issue #29.
"""

from __future__ import annotations

from alembic import op

revision: str = "0004_grades"
down_revision: str | None = "0003_audit_chain"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


_UPGRADE_SQL = """
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
    'SHA-256 over canonical payload + prev_hash. Computed in labeling.rubric.compute_row_hash.';

-- A reviewer should not grade the same case twice. Unique index enforces this.
CREATE UNIQUE INDEX grades_reviewer_case_unique ON grades (reviewer_id, case_id);

-- Agreement queries filter by submitted_at window and group by case.
CREATE INDEX grades_submitted_at ON grades (submitted_at);
CREATE INDEX grades_case_id ON grades (case_id);
CREATE INDEX grades_reviewer_submitted_at ON grades (reviewer_id, submitted_at DESC);

-- Least-privilege role: the labeling app reads and inserts but never deletes.
-- Corrections go through a compensating INSERT + manual DB task.
GRANT SELECT, INSERT, UPDATE ON grades TO afya_sahihi_app;
"""

_DOWNGRADE_SQL = """
DROP INDEX IF EXISTS grades_reviewer_submitted_at;
DROP INDEX IF EXISTS grades_case_id;
DROP INDEX IF EXISTS grades_submitted_at;
DROP INDEX IF EXISTS grades_reviewer_case_unique;
DROP TABLE IF EXISTS grades;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
