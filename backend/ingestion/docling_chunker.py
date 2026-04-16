"""Docling adapter — turn a `SourceDocument` into `RawChunk`s.

Docling is a heavy optional dependency (PyTorch, multiple models). The
import sits inside the constructor so importing this module does not fail
on a machine that has only the runtime Python deps installed. Unit tests
use the `ingestion.protocols.Chunker` protocol directly with a fake and
never trigger this import path.

Version pinned to 2.9.0 per ADR-0004 and env/ingestion.env.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from ingestion.protocols import Chunker, RawChunk, SourceDocument
from ingestion.settings import IngestionSettings
from ingestion.structural_meta import (
    BoundingBox,
    SourceMeta,
    StructuralMeta,
    StructureMeta,
    VisualEmphasis,
    detect_contraindication,
)


class DoclingChunker(Chunker):
    """Concrete `Chunker` backed by Docling's HybridChunker.

    The real Docling types are imported lazily so test environments can
    instantiate the module without a PyTorch install.
    """

    def __init__(self, *, settings: IngestionSettings) -> None:
        self._settings = settings
        # Lazy import — keeps Docling out of the dep graph for tests and
        # for pyright running against the pure-Python modules.
        from docling.chunking import HybridChunker  # type: ignore[import-untyped]
        from docling.document_converter import DocumentConverter  # type: ignore[import-untyped]

        self._converter = DocumentConverter()
        self._chunker = HybridChunker(
            tokenizer=settings.chunker_tokenizer,
            max_tokens=settings.chunker_max_tokens,
            overlap_tokens=settings.chunker_overlap_tokens,
            merge_peers=settings.chunker_merge_peers,
        )

    def chunk(self, document: SourceDocument) -> Sequence[RawChunk]:
        # Docling reads from a path; stream the in-memory bytes to a
        # tempfile so the converter's file-based API is happy. This is
        # intentionally sync — ingestion is offline and doing async work
        # just to read a bytes buffer would add complexity with no gain.
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(document.pdf_bytes)
            f.flush()
            converted = self._converter.convert(f.name)

        out: list[RawChunk] = []
        for chunk in self._chunker.chunk(converted.document):
            meta = _build_structural_meta(
                document=document,
                chunk=chunk,
                extraction_version=f"docling-{self._settings.docling_version}",
            )
            out.append(
                RawChunk(
                    text=chunk.text,
                    meta=meta,
                    token_count=_estimate_tokens(chunk.text, self._settings),
                )
            )
        return out


def _build_structural_meta(
    *,
    document: SourceDocument,
    chunk: object,
    extraction_version: str,
) -> StructuralMeta:
    """Bridge Docling's chunk object to our strict `StructuralMeta`.

    Isolated from `DoclingChunker` so the mapping is unit-testable
    without instantiating the Docling converter. The `chunk: object`
    annotation is deliberate — we duck-type on the Docling 2.9 API
    surface (prov, text, section_path, visual_emphasis) without
    importing its types into the public API here.
    """
    prov_pages = _safe_attr(chunk, "prov_pages", ())
    bboxes = tuple(BoundingBox(page=p.page, x0=p.x0, y0=p.y0, x1=p.x1, y1=p.y1) for p in prov_pages)
    page_range = _page_range(prov_pages)

    section_path = tuple(_safe_attr(chunk, "section_path", ()))
    visual_emphasis = tuple(
        _visual_emphasis_from_docling(e)
        for e in _safe_attr(chunk, "visual_emphasis", ())
        if _visual_emphasis_from_docling(e) is not None
    )

    return StructuralMeta(
        source=SourceMeta(
            document_id=document.document_id,
            document_hash=document.document_hash,
            page_range=page_range,
            bounding_boxes=bboxes,
        ),
        structure=StructureMeta(
            section_path=section_path,
            heading_level=_safe_attr(chunk, "heading_level", 0),
            parent_table_id=_safe_attr(chunk, "parent_table_id", None),
            visual_emphasis=tuple(e for e in visual_emphasis if e is not None),
            list_depth=_safe_attr(chunk, "list_depth", 0),
            is_contraindication=detect_contraindication(
                tuple(e for e in visual_emphasis if e is not None)
            ),
        ),
        content_type=_safe_attr(chunk, "content_type", "text"),
        language=_safe_attr(chunk, "language", "en"),
        extraction_version=extraction_version,
    )


_VISUAL_EMPHASIS_MAP: dict[str, VisualEmphasis] = {
    "bold": VisualEmphasis.BOLD,
    "italic": VisualEmphasis.ITALIC,
    "underline": VisualEmphasis.UNDERLINE,
    "red_box": VisualEmphasis.RED_BOX,
    "yellow_highlight": VisualEmphasis.YELLOW_HIGHLIGHT,
    "large_font": VisualEmphasis.LARGE_FONT,
}


def _visual_emphasis_from_docling(raw: object) -> VisualEmphasis | None:
    if not isinstance(raw, str):
        return None
    return _VISUAL_EMPHASIS_MAP.get(raw)


def _page_range(prov_pages: object) -> tuple[int, int]:
    pages = [_safe_attr(p, "page", 0) for p in (prov_pages or ())]
    pages = [p for p in pages if isinstance(p, int) and p >= 1]
    if not pages:
        return (0, 0)
    return (min(pages), max(pages))


def _safe_attr(obj: object, name: str, default: object) -> object:
    return getattr(obj, name, default)


def _estimate_tokens(text: str, settings: IngestionSettings) -> int:
    """Whitespace-split token estimate; good enough for the quality gate.

    The real tokenizer lives inside Docling's HybridChunker (BAAI/bge-m3),
    but re-running it here just to count tokens would double the work
    and not add precision — the gate is checking 'is this chunk roughly
    the size we expect,' which whitespace count answers. A future
    refinement could use the chunker's own token_count when Docling
    exposes it.
    """
    return max(len(text.split()), 1)


def document_hash_from_bytes(pdf_bytes: bytes) -> str:
    """Canonical content hash for `SourceDocument.document_hash`."""
    return "sha256:" + hashlib.sha256(pdf_bytes).hexdigest()
