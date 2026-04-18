"""Prediction-set construction from candidates + q_hat.

Given a set of candidate labels and the q_hat from the calibration
stratum, the prediction set is { candidate : score(candidate) <= q_hat }.

For a RAG system, "candidates" are typically the top-k retrieved chunk
IDs (scored by their own nonconformity contribution to the generated
answer). This module does not assume that shape — candidates are
opaque strings; the caller decides what they represent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Candidate:
    """One element that may end up in the prediction set."""

    label: str
    score: float


@dataclass(frozen=True, slots=True)
class PredictionSet:
    """Outcome of conformal set construction."""

    labels: tuple[str, ...]
    set_size: int
    top_score: float
    q_hat: float
    target_coverage_met: bool
    stratum: str


def construct_prediction_set(
    *,
    candidates: list[Candidate],
    q_hat: float,
    stratum: str,
) -> PredictionSet:
    """Build the set from scored candidates.

    Invariants:
        - Empty candidates → empty set, top_score = +inf, target_coverage
          NOT met (cannot provide coverage when the universe is empty).
        - Every candidate with score <= q_hat is included.
        - Labels in the returned tuple preserve the input order of the
          *included* candidates (deterministic for testing).
    """
    if not candidates:
        return PredictionSet(
            labels=(),
            set_size=0,
            top_score=math.inf,
            q_hat=q_hat,
            target_coverage_met=False,
            stratum=stratum,
        )

    included = [c for c in candidates if math.isfinite(c.score) and c.score <= q_hat]
    labels = tuple(c.label for c in included)
    top_score = min((c.score for c in candidates if math.isfinite(c.score)), default=math.inf)

    # Coverage is "met" when the set is non-empty — a non-empty set
    # carries the marginal coverage guarantee from the split-CP theorem.
    # An empty set has no guarantee and must be treated as a refusal
    # upstream (the orchestrator's fail-closed handler).
    target_coverage_met = len(labels) > 0

    return PredictionSet(
        labels=labels,
        set_size=len(labels),
        top_score=top_score,
        q_hat=q_hat,
        target_coverage_met=target_coverage_met,
        stratum=stratum,
    )
