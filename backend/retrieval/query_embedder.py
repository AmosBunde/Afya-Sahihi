"""Query embedder with Redis caching.

Embeds a query string to a dense vector using BGE-M3 with matryoshka
truncation. Caches the result in Redis keyed on a normalized form of
the query so repeated/similar queries skip the model call entirely.

The embedder satisfies the `retrieval.service.QueryEmbedder` Protocol
from issue #18. Heavy deps (sentence-transformers, torch) are lazy-
imported so the module is importable without them for tests.

Redis connection is optional: when unavailable, the embedder still
works — it just skips the cache (warn, not fail). This matches the
fail-open-on-cache principle: a Redis outage degrades latency but
does not break retrieval.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata

from retrieval.settings import RetrievalSettings

logger = logging.getLogger(__name__)


class CachedQueryEmbedder:
    """BGE-M3 embedder with Redis caching. Satisfies `QueryEmbedder` Protocol."""

    def __init__(
        self,
        *,
        settings: RetrievalSettings,
        redis_client: object | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis_client
        self._dim = 1024

        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        self._model = SentenceTransformer(
            settings.query_embedder_model_path
            if hasattr(settings, "query_embedder_model_path")
            else "BAAI/bge-m3",
            device=settings.reranker_device,
        )
        logger.info("query embedder loaded", extra={"device": settings.reranker_device})

    def embed(self, text: str) -> tuple[float, ...]:
        """Embed a single query. Check cache first; compute on miss."""
        normalized = normalize_query(text)
        cache_key = _cache_key(normalized)

        # Cache read
        if self._redis is not None:
            try:
                cached = self._redis.get(cache_key)  # type: ignore[union-attr]
                if cached is not None:
                    return tuple(json.loads(cached))
            except Exception:
                logger.warning("redis cache read failed; computing embedding", exc_info=True)

        # Compute
        vector = self._model.encode(
            normalized,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        truncated = tuple(float(x) for x in vector[: self._dim])

        # Cache write
        if self._redis is not None:
            try:
                self._redis.setex(  # type: ignore[union-attr]
                    cache_key,
                    self._settings.query_cache_ttl_seconds,
                    json.dumps(truncated),
                )
            except Exception:
                logger.warning("redis cache write failed", exc_info=True)

        return truncated


def normalize_query(text: str) -> str:
    """Normalize query text for cache-key stability.

    Lowercases, strips accents, removes punctuation, collapses whitespace.
    Two queries that differ only in casing/punctuation/whitespace will
    produce the same embedding — and the same cache key.
    """
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _cache_key(normalized_text: str) -> str:
    """SHA-256 of normalized query → Redis key.

    Fixed-length keys keep Redis memory predictable regardless of query
    length.
    """
    h = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    return f"afya:qemb:{h}"
