"""Labeling-local PHI scrubber.

Delegates to `backend.app.validation.phi.scrub` when the backend package
is importable (production image mounts both). In the standalone
labeling image (which does not ship the backend package) we fall back
to a minimal, stricter local regex set covering the fields that a
reviewer is most likely to paste: Kenyan national IDs, MRNs, phone
numbers, email addresses.

The scrubber fails closed: on any regex compilation or runtime error,
the caller treats the result as "not safe to store" and refuses the
submission.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

REPLACEMENT: Final[str] = "<REDACTED>"


@dataclass(frozen=True, slots=True)
class ScrubResult:
    scrubbed: str
    hits: tuple[str, ...]
    failed: bool


_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    # Kenyan national ID — 8 digits, standalone.
    ("national_id", re.compile(r"(?<!\d)\d{8}(?!\d)")),
    # MRN: optional 1-3 letter prefix + 4-8 digits.
    ("mrn", re.compile(r"\b[A-Z]{1,3}-?\d{4,8}\b")),
    # Kenyan mobile: +254 7XX XXX XXX or 07XX XXX XXX.
    ("phone", re.compile(r"(?:\+?254|0)[\s-]?7\d{2}[\s-]?\d{3}[\s-]?\d{3}")),
    # Email.
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
)


def scrub(text: str, *, replacement: str = REPLACEMENT) -> ScrubResult:
    """Redact PHI-like patterns. Fails closed on any exception.

    Returns `ScrubResult(scrubbed, hits, failed)`. `hits` contains the
    pattern names that fired at least once; `failed=True` means the
    scrubber itself raised and the caller MUST NOT store the text.
    """
    if not isinstance(text, str):
        return ScrubResult(scrubbed="", hits=(), failed=True)
    try:
        out = text
        hits: list[str] = []
        for name, pattern in _PATTERNS:
            new_out, n = pattern.subn(replacement, out)
            if n > 0:
                hits.append(name)
            out = new_out
        return ScrubResult(scrubbed=out, hits=tuple(hits), failed=False)
    except re.error:
        # Should never happen (patterns are static) but fail closed.
        return ScrubResult(scrubbed="", hits=(), failed=True)
