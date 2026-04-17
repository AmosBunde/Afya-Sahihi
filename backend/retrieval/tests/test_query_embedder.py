"""Tests for query normalization + cache key stability. Pure Python."""

from __future__ import annotations

import json

from retrieval.query_embedder import _cache_key, normalize_query

# ---- Normalization ----


def test_normalize_lowercases() -> None:
    assert normalize_query("What Is MALARIA?") == "what is malaria"


def test_normalize_strips_punctuation() -> None:
    assert normalize_query("dose? for: child!!") == "dose for child"


def test_normalize_collapses_whitespace() -> None:
    assert normalize_query("  multiple   spaces  ") == "multiple spaces"


def test_normalize_strips_accents() -> None:
    assert normalize_query("café résumé") == "cafe resume"


def test_normalize_handles_empty_string() -> None:
    assert normalize_query("") == ""


def test_normalize_preserves_swahili_words() -> None:
    assert normalize_query("Dawa ya malaria ni nini?") == "dawa ya malaria ni nini"


# ---- Cache key stability ----


def test_cache_key_deterministic() -> None:
    k1 = _cache_key("what is malaria")
    k2 = _cache_key("what is malaria")
    assert k1 == k2


def test_cache_key_different_for_different_queries() -> None:
    k1 = _cache_key("what is malaria")
    k2 = _cache_key("what is tb")
    assert k1 != k2


def test_cache_key_has_prefix() -> None:
    k = _cache_key("test")
    assert k.startswith("afya:qemb:")


def test_equivalent_queries_produce_same_key() -> None:
    q1 = normalize_query("What is MALARIA?")
    q2 = normalize_query("what is malaria")
    assert _cache_key(q1) == _cache_key(q2)


# ---- Fake Redis for embedder cache logic ----


class _FakeRedis:
    """In-memory Redis stand-in for unit tests."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value


def test_fake_redis_round_trips() -> None:
    r = _FakeRedis()
    vec = (0.1, 0.2, 0.3)
    key = _cache_key("test")
    r.setex(key, 900, json.dumps(vec))
    assert json.loads(r.get(key)) == list(vec)  # type: ignore[arg-type]
