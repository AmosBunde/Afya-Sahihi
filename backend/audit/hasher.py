"""Hash chain computation for the audit log.

Each row's `row_hash` is `sha256(prev_hash || canonical_payload)`. The
canonical payload is a deterministic JSON serialisation of every
business-relevant column (query_id through corpus_version), sorted by
key so the hash is stable across Python dict ordering changes.

The genesis row (first ever entry) uses an empty string as `prev_hash`.
The genesis hash can optionally be read from a file for reproducible
chain roots in multi-environment deployments (env/audit.env
HASH_CHAIN_GENESIS_FILE).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def row_hash(*, prev_hash: str, payload: dict[str, Any]) -> str:
    """Compute the chain hash for one audit row.

    `payload` must contain only JSON-serialisable values. Keys are sorted
    so the hash is deterministic regardless of insertion order.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    preimage = prev_hash + canonical
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def verify_chain(rows: list[dict[str, Any]]) -> list[int]:
    """Walk the chain and return IDs of rows whose hash is broken.

    Each dict in `rows` must have keys: `id`, `prev_hash`, `row_hash`,
    plus all the business columns that `row_hash` was computed from.
    Rows must be ordered by `id ASC`.

    Returns an empty list when the chain is intact.
    """
    broken: list[int] = []
    expected_prev = ""

    for row in rows:
        stored_prev = row["prev_hash"]
        stored_hash = row["row_hash"]

        if stored_prev != expected_prev:
            broken.append(row["id"])
            expected_prev = stored_hash
            continue

        payload = _extract_payload(row)
        expected_hash = row_hash(prev_hash=stored_prev, payload=payload)

        if stored_hash != expected_hash:
            broken.append(row["id"])

        expected_prev = stored_hash

    return broken


_PAYLOAD_KEYS = (
    "query_id",
    "trace_id",
    "query_text",
    "query_language",
    "classified_intent",
    "prefilter_score",
    "response_text",
    "retrieval_top1",
    "conformal_set",
    "pipeline_status",
    "error_class",
    "latency_ms",
    "corpus_version",
    "model_versions",
    "created_at",
)


def _extract_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Pull only the business columns from a full row dict."""
    return {k: row[k] for k in _PAYLOAD_KEYS if k in row}
