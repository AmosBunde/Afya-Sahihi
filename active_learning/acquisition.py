"""Five acquisition functions for weekly case selection.

Each function is pure: a list of CandidateCase → a list of scores
(one per candidate). The scheduler picks top-k by score (higher is
more worth labeling). `ControlArmAcquisition` — the random baseline —
returns uniform scores derived from a seeded RNG so runs are
reproducible.

Non-obvious choices:
  - Entropy uses natural log. Shannon entropy in nats; the ranking is
    invariant to the log base so it doesn't matter for selection, but
    documenting the convention stops future PRs from "fixing" it.
  - Conformal set size bigger → higher score. Intuition: a prediction
    set of size 5 says the model has five plausible answers; labeling
    that case teaches the calibrator more than labeling an easy case
    where the set is {one answer, 99% confident}.
  - Coverage gap is |observed − target|. A case that the conformal
    predictor got wrong (truth fell outside the set) under target
    0.90 has gap 0.10 and gets selected; a case inside the set has
    gap 0. Only works when ground truth is already known (replay
    from Tier 2 eval runs).
  - Clinical harm weighted multiplies uncertainty by the harm weight
    of the case's stratum (dosing > contraindication > …). Harm
    weights come from the Paper P3 pre-registration tier table.

Reference: Settles 2012 "Active Learning" §2-5. Our choice of five
functions covers the canonical spectrum (random, uncertainty, model-
specific=conformal, validation-feedback=coverage, application-weighted).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Final, Protocol

# Harm weights (Paper P3 pre-registered). Higher = more worth
# labeling correctly because a wrong answer costs more clinically.
HARM_WEIGHTS: Final[dict[str, float]] = {
    "dosing": 3.0,
    "contraindication": 3.0,
    "pediatric": 2.5,
    "pregnancy": 2.5,
    "diagnosis": 1.5,
    "triage": 1.5,
    "general": 1.0,
}
DEFAULT_HARM_WEIGHT: Final[float] = 1.0


@dataclass(frozen=True, slots=True)
class CandidateCase:
    """One row of the candidate pool.

    Field names match `al_labeled_pool` columns so the repository
    can map 1-1 on read. `truth_in_set` is None when ground truth is
    unknown (production queries); set True/False for Tier 2 replay
    where the golden answer is recorded.
    """

    case_id: str
    stratum: str
    token_logprobs: tuple[float, ...]
    conformal_set_size: int
    conformal_coverage_target: float
    truth_in_set: bool | None
    ingested_at_iso: str


class AcquisitionFunction(Protocol):
    name: str

    def score(
        self, *, candidates: list[CandidateCase], rng: random.Random
    ) -> list[float]: ...


def shannon_entropy_nats(logprobs: tuple[float, ...]) -> float:
    """H = −Σ p log p from token-level logprobs. Ignores +inf.

    Token logprobs are in nats (OpenAI spec) already, so we exp them
    to probabilities, then compute entropy directly. Empty or all-inf
    token lists return 0 (no signal).
    """
    probs: list[float] = []
    for lp in logprobs:
        if math.isfinite(lp):
            p = math.exp(lp)
            if p > 0:
                probs.append(p)
    total = sum(probs)
    if total <= 0:
        return 0.0
    normalised = [p / total for p in probs]
    return -sum(p * math.log(p) for p in normalised if p > 0)


class RandomAcquisition:
    """Uniform random score. The control-arm generator."""

    name: Final = "random"

    def score(
        self, *, candidates: list[CandidateCase], rng: random.Random
    ) -> list[float]:
        return [rng.random() for _ in candidates]


class UncertaintyEntropyAcquisition:
    """Rank by Shannon entropy of token logprobs (nats)."""

    name: Final = "uncertainty_entropy"

    def score(
        self, *, candidates: list[CandidateCase], rng: random.Random
    ) -> list[float]:
        _ = rng  # unused; kept for Protocol compatibility
        return [shannon_entropy_nats(c.token_logprobs) for c in candidates]


class ConformalSetSizeAcquisition:
    """Rank by prediction-set size. Bigger set → more to learn."""

    name: Final = "conformal_set_size"

    def score(
        self, *, candidates: list[CandidateCase], rng: random.Random
    ) -> list[float]:
        _ = rng
        return [float(c.conformal_set_size) for c in candidates]


class CoverageGapAcquisition:
    """Rank by |observed miss-coverage − target|.

    Only meaningful for replayed Tier 2 cases where `truth_in_set` is
    known. Production cases (truth_in_set=None) score 0 so they fall
    to the bottom of the ranking.
    """

    name: Final = "coverage_gap"

    def score(
        self, *, candidates: list[CandidateCase], rng: random.Random
    ) -> list[float]:
        _ = rng
        out: list[float] = []
        for c in candidates:
            if c.truth_in_set is None:
                out.append(0.0)
                continue
            # If truth is OUT of the set we missed coverage by (1 - target);
            # if IN, gap is 0. Magnitude is the single-case coverage loss.
            gap = 0.0 if c.truth_in_set else 1.0 - c.conformal_coverage_target
            out.append(gap)
        return out


class ClinicalHarmWeightedAcquisition:
    """Uncertainty × stratum-harm weight. Paper P3 primary."""

    name: Final = "clinical_harm_weighted"

    def score(
        self, *, candidates: list[CandidateCase], rng: random.Random
    ) -> list[float]:
        _ = rng
        out: list[float] = []
        for c in candidates:
            entropy = shannon_entropy_nats(c.token_logprobs)
            weight = HARM_WEIGHTS.get(c.stratum, DEFAULT_HARM_WEIGHT)
            out.append(entropy * weight)
        return out


ACQUISITION_FUNCTIONS: Final[dict[str, AcquisitionFunction]] = {
    RandomAcquisition.name: RandomAcquisition(),
    UncertaintyEntropyAcquisition.name: UncertaintyEntropyAcquisition(),
    ConformalSetSizeAcquisition.name: ConformalSetSizeAcquisition(),
    CoverageGapAcquisition.name: CoverageGapAcquisition(),
    ClinicalHarmWeightedAcquisition.name: ClinicalHarmWeightedAcquisition(),
}


def resolve(name: str) -> AcquisitionFunction:
    """Look up an acquisition function by name; ValueError if unknown."""
    try:
        return ACQUISITION_FUNCTIONS[name]
    except KeyError as exc:
        raise ValueError(
            f"unknown acquisition function {name!r}; "
            f"known: {sorted(ACQUISITION_FUNCTIONS)}"
        ) from exc


def top_k(
    *,
    candidates: list[CandidateCase],
    scores: list[float],
    k: int,
) -> list[CandidateCase]:
    """Return the k highest-scoring candidates. Stable on ties (by case_id)."""
    if len(candidates) != len(scores):
        raise ValueError("candidates and scores must have the same length")
    if k < 0:
        raise ValueError("k must be >= 0")
    pairs = list(zip(candidates, scores, strict=True))
    # Sort descending by score; stable on case_id so two runs with the
    # same inputs pick the same cases (reproducibility is a Paper P3
    # requirement).
    pairs.sort(key=lambda p: (-p[1], p[0].case_id))
    return [c for c, _ in pairs[:k]]
