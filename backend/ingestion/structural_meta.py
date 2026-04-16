"""Structural metadata schema for ingested chunks.

ADR-0004 defines the JSONB payload shape that every chunk carries. This
module is the single source of truth for that shape — the Pydantic models
here are used both to serialize chunker output into Postgres and to
deserialize it in the retrieval service.

All models are `strict=True, frozen=True` per SKILL.md §1 so a schema
drift surfaces as a validation error, not a silently-malformed row.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_STRICT_FROZEN = ConfigDict(strict=True, frozen=True, extra="forbid")


class VisualEmphasis(StrEnum):
    """Canonical names for visual emphasis signals the chunker recognises."""

    BOLD = "bold"
    ITALIC = "italic"
    UNDERLINE = "underline"
    RED_BOX = "red_box"
    YELLOW_HIGHLIGHT = "yellow_highlight"
    LARGE_FONT = "large_font"


class BoundingBox(BaseModel):
    """A single rectangular region on a source PDF page.

    Coordinates follow Docling's convention: x0,y0 is top-left, in the
    PDF coordinate space. Used to render the provenance highlight in the
    clinician UI.
    """

    model_config = _STRICT_FROZEN

    page: int = Field(ge=1)
    x0: float = Field(ge=0)
    y0: float = Field(ge=0)
    x1: float = Field(ge=0)
    y1: float = Field(ge=0)


class SourceMeta(BaseModel):
    """Where this chunk came from in the source PDF."""

    model_config = _STRICT_FROZEN

    document_id: str = Field(min_length=1, max_length=512)
    document_hash: str = Field(min_length=1, max_length=128)
    page_range: tuple[int, int] = Field(description="inclusive (first, last)")
    bounding_boxes: tuple[BoundingBox, ...] = ()


class StructureMeta(BaseModel):
    """Visual/structural properties of the chunk within the source."""

    model_config = _STRICT_FROZEN

    section_path: tuple[str, ...] = ()
    heading_level: int = Field(default=0, ge=0, le=10)
    parent_table_id: str | None = None
    visual_emphasis: tuple[VisualEmphasis, ...] = ()
    list_depth: int = Field(default=0, ge=0, le=10)
    is_contraindication: bool = False


class StructuralMeta(BaseModel):
    """Top-level JSONB payload stored on every row of `chunks`.

    The schema name is the key of the JSONB column; the fields below are
    ADR-0004 §Decision verbatim. Any change to this model requires a new
    ADR that supersedes 0004.
    """

    model_config = _STRICT_FROZEN

    source: SourceMeta
    structure: StructureMeta
    content_type: Literal["text", "table", "figure", "caption"] = "text"
    language: str = Field(default="en", min_length=2, max_length=10)
    extraction_version: str = Field(min_length=1, max_length=32)


def detect_contraindication(emphasis: tuple[VisualEmphasis, ...]) -> bool:
    """Promote red-box visual emphasis to `is_contraindication=True`.

    ADR-0004 §Context: "Bold red boxes mark contraindications." This
    helper is the one place that mapping lives so the rule is easy to
    audit and modify. Called from the Docling adapter when building
    StructureMeta.
    """
    return VisualEmphasis.RED_BOX in emphasis
