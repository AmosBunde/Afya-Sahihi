"""Cross-encoder reranker wrapping bge-reranker-v2-m3.

Heavy dep (sentence-transformers + torch) — imported lazily so the
retrieval module is importable without PyTorch for tests that use the
`Reranker` Protocol with a fake. CPU inference is intentional: the
reranker is a 568M-param model, batch 16 × 512 tokens fits in ~4 GB
RAM, and the GPU is reserved for the two vLLM servers.

ADR-0002: reranking is part of the retrieval stage, not the request
path's orchestrator. The retrieval service calls this; the orchestrator
never imports it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from retrieval.settings import RetrievalSettings

logger = logging.getLogger(__name__)


class BgeReranker:
    """Concrete Reranker backed by bge-reranker-v2-m3.

    Satisfies the `retrieval.service.Reranker` Protocol.
    """

    def __init__(self, *, settings: RetrievalSettings) -> None:
        self._settings = settings
        from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]

        self._model = CrossEncoder(
            settings.reranker_model_path or "BAAI/bge-reranker-v2-m3",
            device=settings.reranker_device,
            max_length=512,
        )
        logger.info(
            "reranker loaded",
            extra={
                "model": settings.reranker_model_path,
                "device": settings.reranker_device,
            },
        )

    def rerank(self, query: str, passages: Sequence[str]) -> Sequence[float]:
        """Score each (query, passage) pair; higher = more relevant.

        Returns one float per passage in the same order as `passages`.
        """
        if not passages:
            return ()

        pairs = [[query, p] for p in passages]
        scores = self._model.predict(
            pairs,
            batch_size=self._settings.reranker_batch_size,
            show_progress_bar=False,
        )
        return tuple(float(s) for s in scores)
