"""Audit hash chaining and tamper-evident trigger.

Revision ID: 0003_audit_chain
Revises: 0002_ingestion
Create Date: 2026-04-17

Adds the hash-chain columns (`prev_hash`, `row_hash`) to `queries_audit`
and installs a trigger that prevents UPDATE and DELETE on the table.
Together these make the audit log append-only and tamper-evident: any
modification to an existing row breaks the chain, and any deletion
triggers a hard error that the application cannot suppress.

The 7-year retention policy (AUDIT_RETENTION_DAYS=2555) is documented
here but not enforced via pg_cron because pg_cron's database-name
configuration is not available in all environments (see 0001 notes).
Production retention is handled by the k3s CronJob landing with
issue #14.

Companion to issue #13.
"""

from __future__ import annotations

from alembic import op

revision: str = "0003_audit_chain"
down_revision: str | None = "0002_ingestion"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


_ADD_COLUMNS_SQL = """
ALTER TABLE queries_audit
    ADD COLUMN prev_hash TEXT NOT NULL DEFAULT '',
    ADD COLUMN row_hash  TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN queries_audit.prev_hash IS
    'SHA-256 hash of the preceding row, or empty string for the genesis row.';
COMMENT ON COLUMN queries_audit.row_hash IS
    'SHA-256 of (prev_hash || canonical row payload). Verifiable via '
    'scripts/audit/verify_chain.py.';

CREATE INDEX queries_audit_row_hash ON queries_audit (row_hash);
"""


_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION audit_prevent_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'queries_audit is append-only. % is forbidden. '
        'If you need to correct a record, INSERT a correction row '
        'with a reference to the original query_id.',
        TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_no_update
    BEFORE UPDATE ON queries_audit
    FOR EACH ROW
    EXECUTE FUNCTION audit_prevent_mutation();

CREATE TRIGGER trg_audit_no_delete
    BEFORE DELETE ON queries_audit
    FOR EACH ROW
    EXECUTE FUNCTION audit_prevent_mutation();
"""


def upgrade() -> None:
    op.execute(_ADD_COLUMNS_SQL)
    op.execute(_TRIGGER_SQL)


_DOWNGRADE_SQL = """
DROP TRIGGER IF EXISTS trg_audit_no_delete ON queries_audit;
DROP TRIGGER IF EXISTS trg_audit_no_update ON queries_audit;
DROP FUNCTION IF EXISTS audit_prevent_mutation();

ALTER TABLE queries_audit
    DROP COLUMN IF EXISTS row_hash,
    DROP COLUMN IF EXISTS prev_hash;
"""


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
