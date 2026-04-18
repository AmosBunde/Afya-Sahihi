"""PDF provenance viewer URL builder.

The labeling UI embeds the gateway's provenance viewer via an iframe.
The viewer supports deep-linking to a specific page + bbox via query
params; we construct the URL here so the Streamlit app stays ignorant
of the viewer's routing.

Pure string building. No I/O. No external calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlencode


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Normalised PDF page coordinates (0..1 in both axes, origin top-left)."""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        for coord_name in ("x0", "y0", "x1", "y1"):
            v = getattr(self, coord_name)
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"{coord_name}={v} outside [0, 1]")
        if self.x0 >= self.x1 or self.y0 >= self.y1:
            raise ValueError(
                "bbox must have x0 < x1 and y0 < y1 "
                f"(got x0={self.x0}, x1={self.x1}, y0={self.y0}, y1={self.y1})"
            )


def build_viewer_url(
    *,
    base_url: str,
    document_id: str,
    bbox: BoundingBox | None,
    highlight: bool = True,
) -> str:
    """Compose a deep link into the provenance viewer.

    When `bbox` is None, the link opens the document at page 1 with no
    highlight. When `highlight=False` we still pass the page so the
    reviewer lands on the right spot.
    """
    if not base_url:
        raise ValueError("base_url is required")
    # Strip trailing slash — the viewer uses `/<doc_id>` as its path.
    base = base_url.rstrip("/")
    doc_path = quote(document_id, safe="")
    params: dict[str, str] = {}
    if bbox is not None:
        params["page"] = str(bbox.page)
        if highlight:
            # Viewer expects `bbox=x0,y0,x1,y1` in normalised coords.
            params["bbox"] = f"{bbox.x0:.4f},{bbox.y0:.4f},{bbox.x1:.4f},{bbox.y1:.4f}"
    query = f"?{urlencode(params)}" if params else ""
    return f"{base}/{doc_path}{query}"
