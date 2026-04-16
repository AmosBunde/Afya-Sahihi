"""Tests for the JSONB schema that every chunk carries.

Pure-Python tests — no Docling, no Postgres. Verifies that ADR-0004's
contract is enforced by the Pydantic models: rejecting out-of-range
values, enforcing the red-box → is_contraindication promotion, refusing
unexpected fields. These are the guardrails a future change to the
schema is forced to acknowledge before touching.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ingestion.structural_meta import (
    BoundingBox,
    SourceMeta,
    StructuralMeta,
    StructureMeta,
    VisualEmphasis,
    detect_contraindication,
)


def _valid_meta(**overrides: object) -> StructuralMeta:
    base: dict[str, object] = dict(
        source=SourceMeta(
            document_id="moh-malaria-v7",
            document_hash="sha256:abc123",
            page_range=(42, 43),
            bounding_boxes=(BoundingBox(page=42, x0=72.0, y0=120.0, x1=540.0, y1=310.0),),
        ),
        structure=StructureMeta(
            section_path=("Malaria", "Treatment", "Pediatric"),
            heading_level=3,
            visual_emphasis=(VisualEmphasis.RED_BOX,),
            is_contraindication=True,
        ),
        content_type="text",
        language="en",
        extraction_version="docling-2.9.0",
    )
    base.update(overrides)
    return StructuralMeta(**base)


def test_valid_meta_accepted() -> None:
    meta = _valid_meta()
    assert meta.structure.is_contraindication is True


def test_red_box_emphasis_promotes_to_contraindication() -> None:
    assert detect_contraindication((VisualEmphasis.RED_BOX,)) is True
    assert detect_contraindication((VisualEmphasis.BOLD,)) is False
    assert detect_contraindication(()) is False


def test_bounding_box_page_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        BoundingBox(page=0, x0=0.0, y0=0.0, x1=1.0, y1=1.0)


def test_structural_meta_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _valid_meta(unexpected="oops")  # type: ignore[arg-type]


def test_heading_level_bounded() -> None:
    with pytest.raises(ValidationError):
        _valid_meta(structure=StructureMeta(heading_level=11))


def test_visual_emphasis_rejects_unknown_string() -> None:
    # Pydantic v2 strict: enum values outside the set fail at parse time.
    with pytest.raises(ValidationError):
        StructureMeta(visual_emphasis=("unknown",))  # type: ignore[arg-type]


def test_structural_meta_is_frozen() -> None:
    meta = _valid_meta()
    with pytest.raises(ValidationError):
        meta.content_type = "table"  # type: ignore[misc]


def test_valid_meta_round_trips_json() -> None:
    meta = _valid_meta()
    as_json = meta.model_dump_json()
    recovered = StructuralMeta.model_validate_json(as_json)
    assert recovered == meta
