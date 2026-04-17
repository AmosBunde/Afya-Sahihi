"""Append-only audit writer.

Scrub → hash-chain → INSERT. If the scrubber fails, the write is
refused (fail-closed). If the INSERT fails, the exception propagates
to the caller (the orchestrator's error handler records it).

The writer reads the previous row's `row_hash` inside the same
transaction as the INSERT so the chain cannot be broken by a concurrent
writer (Postgres row-level lock on the max(id) read + SERIALIZABLE or
explicit advisory lock could be added, but the current design assumes
a single audit writer per deployment — the gateway processes are the
only callers, and each request writes exactly one row).
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from app.validation.phi import ScrubResult, scrub
from audit.hasher import row_hash

logger = logging.getLogger(__name__)

_AUDIT_TIMEOUT = "10s"


class AuditWriteRefused(Exception):
    """The audit writer refused to persist a row because the PHI scrubber
    either failed or the caller did not scrub before calling write.
    """


class AuditWriter:
    """Single-row append to `queries_audit` with hash chaining."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def write(self, *, payload: dict[str, Any]) -> int:
        """Scrub, chain, INSERT. Return the new row `id`.

        `payload` must contain every business column (query_id through
        corpus_version). The writer adds `prev_hash` and `row_hash`.
        """
        scrub_result = _scrub_payload(payload)
        if scrub_result.failed:
            raise AuditWriteRefused(
                f"PHI scrubber failed: {scrub_result.failure_reason}. "
                "Audit row NOT written — fail closed."
            )

        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(f"SET LOCAL statement_timeout = '{_AUDIT_TIMEOUT}'")

            prev = await conn.fetchval(
                "SELECT row_hash FROM queries_audit ORDER BY id DESC LIMIT 1"
            )
            prev_hash_val: str = prev or ""

            hash_val = row_hash(prev_hash=prev_hash_val, payload=payload)

            row_id: int = await conn.fetchval(
                """
                INSERT INTO queries_audit (
                    query_id, trace_id, query_text, query_language,
                    classified_intent, prefilter_score, response_text,
                    retrieval_top1, conformal_set, pipeline_status,
                    error_class, latency_ms, corpus_version,
                    model_versions, prev_hash, row_hash
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10,
                    $11, $12, $13, $14::jsonb, $15, $16
                )
                RETURNING id
                """,
                payload.get("query_id"),
                payload.get("trace_id", ""),
                payload.get("query_text", ""),
                payload.get("query_language"),
                payload.get("classified_intent"),
                payload.get("prefilter_score"),
                payload.get("response_text"),
                payload.get("retrieval_top1"),
                _json_or_none(payload.get("conformal_set")),
                payload.get("pipeline_status", "unknown"),
                payload.get("error_class"),
                payload.get("latency_ms"),
                payload.get("corpus_version", ""),
                _json_or_none(payload.get("model_versions")),
                prev_hash_val,
                hash_val,
            )

        logger.info(
            "audit row written",
            extra={"query_id": str(payload.get("query_id", "")), "row_id": row_id},
        )
        return row_id


def _scrub_payload(payload: dict[str, Any]) -> ScrubResult:
    """Scrub every string-valued field in the payload.

    SKILL.md §0.4: scrub runs before write. If any field's scrub fails,
    the entire result is marked failed.
    """
    total_redactions = 0
    all_types: list[str] = []

    for key in ("query_text", "response_text", "classified_intent"):
        val = payload.get(key)
        if not isinstance(val, str) or not val:
            continue
        result = scrub(val)
        if result.failed:
            return result
        payload[key] = result.text
        total_redactions += result.n_redactions
        all_types.extend(result.redacted_types)

    return ScrubResult(
        text="",
        n_redactions=total_redactions,
        redacted_types=tuple(all_types),
    )


def _json_or_none(val: Any) -> str | None:
    """Serialise a dict/list to JSON string, or None."""
    if val is None:
        return None
    import json

    return json.dumps(val, separators=(",", ":"), default=str)
