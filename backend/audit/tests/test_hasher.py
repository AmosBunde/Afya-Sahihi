"""Hash chain unit tests — pure Python, deterministic."""

from __future__ import annotations

from audit.hasher import row_hash, verify_chain


def _payload(query_text: str = "what is malaria?") -> dict[str, object]:
    return {
        "query_id": "q1",
        "trace_id": "t1",
        "query_text": query_text,
        "pipeline_status": "succeeded",
        "corpus_version": "v1.0",
        "created_at": "2026-04-17T00:00:00+00:00",
    }


def test_row_hash_is_deterministic() -> None:
    h1 = row_hash(prev_hash="", payload=_payload())
    h2 = row_hash(prev_hash="", payload=_payload())
    assert h1 == h2


def test_row_hash_changes_with_different_prev_hash() -> None:
    h1 = row_hash(prev_hash="", payload=_payload())
    h2 = row_hash(prev_hash="abc", payload=_payload())
    assert h1 != h2


def test_row_hash_changes_with_different_payload() -> None:
    h1 = row_hash(prev_hash="", payload=_payload("what is malaria?"))
    h2 = row_hash(prev_hash="", payload=_payload("what is TB?"))
    assert h1 != h2


def test_verify_chain_passes_on_valid_chain() -> None:
    h0 = row_hash(prev_hash="", payload=_payload("q1"))
    h1 = row_hash(prev_hash=h0, payload=_payload("q2"))

    rows = [
        {"id": 1, "prev_hash": "", "row_hash": h0, **_payload("q1")},
        {"id": 2, "prev_hash": h0, "row_hash": h1, **_payload("q2")},
    ]
    assert verify_chain(rows) == []


def test_verify_chain_detects_tampered_row() -> None:
    h0 = row_hash(prev_hash="", payload=_payload("q1"))

    rows = [
        {"id": 1, "prev_hash": "", "row_hash": h0, **_payload("q1")},
        {"id": 2, "prev_hash": h0, "row_hash": "tampered", **_payload("q2")},
    ]
    broken = verify_chain(rows)
    assert broken == [2]


def test_verify_chain_detects_broken_prev_link() -> None:
    h0 = row_hash(prev_hash="", payload=_payload("q1"))

    rows = [
        {"id": 1, "prev_hash": "", "row_hash": h0, **_payload("q1")},
        {"id": 2, "prev_hash": "wrong_prev", "row_hash": "x", **_payload("q2")},
    ]
    broken = verify_chain(rows)
    assert 2 in broken
