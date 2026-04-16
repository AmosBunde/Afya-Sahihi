"""BGE-M3 embedding adapter with matryoshka truncation.

Like `docling_chunker`, this imports `sentence_transformers` lazily so
the module file is safe to import without PyTorch. Tests exercise the
pipeline via the `Embedder` protocol with a deterministic fake.
"""

from __future__ import annotations

from collections.abc import Sequence

from ingestion.protocols import Embedder
from ingestion.settings import IngestionSettings


class BgeM3Embedder(Embedder):
    """Wraps BAAI/bge-m3; truncates to `embedder_matryoshka_dim`.

    BGE-M3 natively supports matryoshka — the first N dimensions of its
    native output form a valid embedding on their own. We pick 1024 by
    default; the pgvector column is declared `vector(768)` in the initial
    migration, so if `embedder_matryoshka_dim` disagrees with the column
    width, the insert will fail at the DB layer rather than silently
    writing a wrong-shaped row. That is the intended fail-closed behaviour.
    """

    def __init__(self, *, settings: IngestionSettings) -> None:
        self._settings = settings
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

        self._model = SentenceTransformer(
            settings.embedder_model,
            device=settings.embedder_device,
        )
        self._dim = settings.embedder_matryoshka_dim

    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        if not texts:
            return ()
        vectors = self._model.encode(
            list(texts),
            batch_size=self._settings.embedder_batch_size,
            normalize_embeddings=self._settings.embedder_normalize,
            show_progress_bar=False,
        )
        # Matryoshka truncate + freeze to tuples for the protocol's
        # immutable return contract.
        return tuple(tuple(float(x) for x in v[: self._dim]) for v in vectors)
