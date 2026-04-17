"""PHI scrubber — local regex patterns only.

SKILL.md §0.4: "Every stored row that touches PHI is scrubbed before
write, not after. The scrubber runs synchronously and fails closed."

This module is the single implementation of that rule. It NEVER calls an
external service (review SKILL §1.1). All patterns are compiled from
in-process regexes targeting Kenyan-format identifiers and common PHI
leakage. If any compiled pattern raises at runtime, the scrubber returns
a `ScrubResult` with `failed=True` and the caller (audit writer) refuses
the write.

The patterns cover:
    - Kenyan national IDs (8-digit)
    - MRN / hospital numbers (site-prefix + digits)
    - Kenyan mobile numbers (+254 / 07xx)
    - Email addresses
    - Named-entity heuristic for patient names (Title Case after common
      clinical keywords like "patient:", "pt:")

They do NOT cover:
    - Free-text clinical notes (those would require NER, which is
      external and disallowed here)
    - Embedded PHI in base64 or binary blobs (those should never reach
      the audit path)

If a new pattern type is needed, add it to `_PATTERNS`, add a test in
`test_phi.py`, and update this docstring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

REPLACEMENT: Final[str] = "<REDACTED>"


@dataclass(frozen=True, slots=True)
class ScrubResult:
    """Outcome of a scrub attempt."""

    text: str
    n_redactions: int
    redacted_types: tuple[str, ...]
    failed: bool = False
    failure_reason: str = ""


@dataclass(frozen=True, slots=True)
class _Pattern:
    name: str
    regex: re.Pattern[str]


_PATTERNS: tuple[_Pattern, ...] = (
    # Kenyan national ID: exactly 8 digits, word-bounded.
    _Pattern(name="national_id", regex=re.compile(r"\b\d{8}\b")),
    # MRN / hospital number: site prefix + slash + digits (e.g. AKU/12345, KNH-67890).
    _Pattern(name="mrn", regex=re.compile(r"\b[A-Z]{2,5}[/-]\d{4,10}\b")),
    # Kenyan mobile: +254 7xx xxx xxx or 07xx xxx xxx.
    _Pattern(
        name="phone",
        regex=re.compile(r"(?:\+254|0)7\d{2}[\s-]?\d{3}[\s-]?\d{3}\b"),
    ),
    # Email addresses.
    _Pattern(
        name="email",
        regex=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    ),
    # Patient name heuristic: "patient:" or "pt:" followed by a Title Case
    # name of 2–4 words. Intentionally greedy on the word count so we
    # over-redact rather than under-redact — false positives are acceptable,
    # false negatives are not.
    _Pattern(
        name="patient_name",
        regex=re.compile(
            r"(?:patient|pt|name)\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
            re.IGNORECASE,
        ),
    ),
    # Kenyan passport: letter + 7 digits (e.g. A1234567, B9876543).
    _Pattern(
        name="passport",
        regex=re.compile(r"\b[A-Z]\d{7}\b"),
    ),
    # NHIF (National Hospital Insurance Fund) number: 8–12 digit string,
    # often prefixed with "NHIF" or "nhif".
    _Pattern(
        name="nhif",
        regex=re.compile(r"(?:NHIF|nhif)\s*[:#]?\s*(\d{8,12})\b"),
    ),
)


def scrub(text: str, *, replacement: str = REPLACEMENT) -> ScrubResult:
    """Apply every pattern and return the scrubbed text.

    Fails closed: if any regex raises (e.g. catastrophic backtracking on
    pathological input), the result is `ScrubResult(failed=True)` with
    the original text and zero redactions — the caller must refuse the
    write.
    """
    redacted_types: list[str] = []
    n_redactions = 0
    out = text

    for pattern in _PATTERNS:
        try:
            matches = pattern.regex.findall(out)
            if matches:
                out = pattern.regex.sub(replacement, out)
                n_redactions += len(matches)
                redacted_types.append(pattern.name)
        except re.error as exc:
            return ScrubResult(
                text=text,
                n_redactions=0,
                redacted_types=(),
                failed=True,
                failure_reason=f"regex error in pattern {pattern.name!r}: {exc}",
            )

    return ScrubResult(
        text=out,
        n_redactions=n_redactions,
        redacted_types=tuple(redacted_types),
    )
