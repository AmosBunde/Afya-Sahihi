"""Active-learning candidate pool view + labeled pool table.

Revision ID: 0005_al_tables
Revises: 0004_grades
Create Date: 2026-04-19

Two objects land here:

1. `al_candidate_pool_v` — a view that joins queries_audit (production
   case history) with the most recent conformal result per case.
   `truth_in_set` is NULL for production cases; Tier 2 replay rows
   (written by the eval-runner) set it based on golden-set ground
   truth. The view is the single source of read candidates for the
   AL scheduler.

2. `al_labeled_pool` — the assignment ledger. One row per
   (case_id, week_iso) tuple: which arm a case belongs to, which
   acquisition function picked it, and when it was assigned. `arm`
   is a CHECK-constrained enum of {treatment, control}. Unique on
   (case_id, week_iso) so re-running the same week's scheduler is
   idempotent.

Companion to issue #37 (Paper P3).
"""

from __future__ import annotations

from alembic import op

revision: str = "0005_al_tables"
down_revision: str | None = "0004_grades"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


_UPGRADE_SQL = """
CREATE TABLE al_labeled_pool (
    case_id               TEXT NOT NULL,
    arm                   TEXT NOT NULL CHECK (arm IN ('treatment', 'control')),
    week_iso              TEXT NOT NULL,
    acquisition_function  TEXT NOT NULL,
    assigned_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, week_iso)
);

COMMENT ON TABLE al_labeled_pool IS
    'Active-learning arm assignments. Row per (case, week) pair.';
COMMENT ON COLUMN al_labeled_pool.arm IS
    'treatment = picked by acquisition_function; control = random.';
COMMENT ON COLUMN al_labeled_pool.acquisition_function IS
    'Recorded "random" for control-arm rows regardless of the week''s '
    'configured treatment function, so the table is self-describing.';

CREATE INDEX al_labeled_pool_week_iso ON al_labeled_pool (week_iso);
CREATE INDEX al_labeled_pool_arm ON al_labeled_pool (arm, week_iso);

-- Candidate pool view. The scheduler reads this; writers populate
-- queries_audit (gateway) and eval_runs (Tier 2) independently.
-- coalesce() defaults let the view survive missing joins during
-- early-deployment windows when eval_runs is empty.
CREATE OR REPLACE VIEW al_candidate_pool_v AS
SELECT
    q.query_id                    AS case_id,
    COALESCE(q.primary_category, 'general')              AS stratum,
    COALESCE(q.token_logprobs, ARRAY[]::DOUBLE PRECISION[])
                                  AS token_logprobs,
    COALESCE(q.conformal_set_size, 0)                    AS conformal_set_size,
    COALESCE(q.conformal_coverage_target, 0.9)           AS conformal_coverage_target,
    NULL::BOOLEAN                 AS truth_in_set,
    q.created_at                  AS ingested_at
FROM queries_audit q
WHERE q.conformal_set_size IS NOT NULL;

COMMENT ON VIEW al_candidate_pool_v IS
    'Read-only candidate pool for the AL scheduler. Production cases '
    'only (truth_in_set=NULL). Tier 2 replay rows with truth_in_set '
    'set are joined via a separate path landing with issue #38.';

GRANT SELECT              ON al_candidate_pool_v TO afya_sahihi_app;
GRANT SELECT, INSERT      ON al_labeled_pool    TO afya_sahihi_app;
"""


_DOWNGRADE_SQL = """
DROP INDEX IF EXISTS al_labeled_pool_arm;
DROP INDEX IF EXISTS al_labeled_pool_week_iso;
DROP VIEW IF EXISTS al_candidate_pool_v;
DROP TABLE IF EXISTS al_labeled_pool;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
