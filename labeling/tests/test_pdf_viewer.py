"""Tests for the PDF viewer URL builder."""

from __future__ import annotations

import pytest

from labeling.pdf_viewer import BoundingBox, build_viewer_url


def test_build_viewer_url_no_bbox() -> None:
    url = build_viewer_url(
        base_url="https://x.aku.edu/provenance",
        document_id="doc-1",
        bbox=None,
        highlight=True,
    )
    assert url == "https://x.aku.edu/provenance/doc-1"


def test_build_viewer_url_with_bbox_and_highlight() -> None:
    bbox = BoundingBox(page=3, x0=0.1, y0=0.2, x1=0.5, y1=0.4)
    url = build_viewer_url(
        base_url="https://x.aku.edu/provenance",
        document_id="doc-1",
        bbox=bbox,
        highlight=True,
    )
    assert url == (
        "https://x.aku.edu/provenance/doc-1?"
        "page=3&bbox=0.1000%2C0.2000%2C0.5000%2C0.4000"
    )


def test_build_viewer_url_with_bbox_no_highlight_still_includes_page() -> None:
    bbox = BoundingBox(page=2, x0=0.0, y0=0.0, x1=0.5, y1=0.5)
    url = build_viewer_url(
        base_url="https://x.aku.edu/provenance",
        document_id="doc-1",
        bbox=bbox,
        highlight=False,
    )
    assert url == "https://x.aku.edu/provenance/doc-1?page=2"


def test_build_viewer_url_strips_trailing_slash() -> None:
    url = build_viewer_url(
        base_url="https://x.aku.edu/provenance/",
        document_id="doc-1",
        bbox=None,
        highlight=True,
    )
    assert url == "https://x.aku.edu/provenance/doc-1"


def test_build_viewer_url_encodes_document_id() -> None:
    url = build_viewer_url(
        base_url="https://x.aku.edu/provenance",
        document_id="doc 1/with?chars",
        bbox=None,
        highlight=True,
    )
    assert url == "https://x.aku.edu/provenance/doc%201%2Fwith%3Fchars"


def test_build_viewer_url_rejects_empty_base() -> None:
    with pytest.raises(ValueError, match="base_url"):
        build_viewer_url(
            base_url="",
            document_id="doc-1",
            bbox=None,
            highlight=True,
        )


# ---- BoundingBox validation ----


def test_bbox_rejects_non_positive_page() -> None:
    with pytest.raises(ValueError, match="page"):
        BoundingBox(page=0, x0=0.1, y0=0.2, x1=0.5, y1=0.4)


def test_bbox_rejects_out_of_range_coord() -> None:
    with pytest.raises(ValueError, match="outside"):
        BoundingBox(page=1, x0=-0.1, y0=0.0, x1=0.5, y1=0.4)
    with pytest.raises(ValueError, match="outside"):
        BoundingBox(page=1, x0=0.0, y0=0.0, x1=1.5, y1=0.4)


def test_bbox_rejects_inverted_coords() -> None:
    with pytest.raises(ValueError, match="x0 < x1"):
        BoundingBox(page=1, x0=0.5, y0=0.1, x1=0.2, y1=0.4)
    with pytest.raises(ValueError, match="x0 < x1"):
        BoundingBox(page=1, x0=0.1, y0=0.5, x1=0.2, y1=0.4)
