#!/usr/bin/env python3
"""Verify the hash chain in queries_audit.

Connects to Postgres, reads every row ordered by id, recomputes each
row_hash, and reports any breaks. A healthy chain prints "chain intact"
and exits 0. Any broken link prints the row id and exits 1.

Usage:
    AFYA_SAHIHI_DATABASE_URL=postgresql://... python scripts/audit/verify_chain.py

Expected runtime: < 30 s for 100k rows (sequential scan, no index needed
because we read every row). For larger tables, page via LIMIT/OFFSET with
a cursor; not implemented yet because the audit table grows at ~100 rows
per day.
"""

from __future__ import annotations

import os
import sys

# Add backend/ to the path so audit.hasher is importable without install.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import psycopg  # noqa: E402

from audit.hasher import verify_chain  # noqa: E402


def main() -> int:
    dsn = os.environ.get("AFYA_SAHIHI_DATABASE_URL", "")
    if not dsn:
        print("error: set AFYA_SAHIHI_DATABASE_URL", file=sys.stderr)  # noqa: T201
        return 1

    sync_dsn = dsn.replace("postgresql+psycopg://", "postgresql://")

    with psycopg.connect(sync_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, query_id, trace_id, query_text, query_language,
                   classified_intent, prefilter_score, response_text,
                   retrieval_top1, conformal_set, pipeline_status,
                   error_class, latency_ms, corpus_version,
                   model_versions, created_at, prev_hash, row_hash
            FROM queries_audit
            ORDER BY id ASC
            """
        )
        columns = [desc[0] for desc in cur.description or []]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    if not rows:
        print("audit table is empty; nothing to verify")  # noqa: T201
        return 0

    broken = verify_chain(rows)
    if broken:
        print(f"CHAIN BROKEN at row IDs: {broken}", file=sys.stderr)  # noqa: T201
        return 1

    print(f"chain intact: {len(rows)} rows verified")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
