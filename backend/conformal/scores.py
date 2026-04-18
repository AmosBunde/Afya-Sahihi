"""Five nonconformity score functions.

A nonconformity score s(x, y) quantifies how "unusual" the response y
is for input x. Higher = less conforming = less confident. Split
conformal includes candidates in the prediction set when s <= q_hat.

All functions are pure: given the same inputs, they return the same
float. This is the invariant the calibration set relies on — scores
stored during calibration must be comparable to scores computed at
prediction time.

Math notes:
    - NLL is on the log scale; avg_logprob is already averaged per token.
    - retrieval_weighted divides by retrieval confidence: low retrieval
      similarity inflates the score (less confident).
    - topic_coherence_adjusted multiplies by (2 - topic_score) so a
      topic_score of 1.0 is a no-op and 0.0 doubles the score.
    - ensemble_disagreement needs >= 2 sampled generations; falls back
      to NLL when only one sample is available (documented; caller
      should prefer a different score if ensemble mode is required).
    - clinical_harm_weighted is NLL multiplied by a harm weight keyed
      on the query's classified intent.

SKILL.md §0.1: every code path fails closed. Here that means a score
function that cannot compute (e.g. missing logprobs, empty sample set)
returns float('inf') — the least-conforming possible value — so the
candidate is excluded from the prediction set by construction.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Final, Literal

from conformal.settings import ConformalSettings

ScoreName = Literal[
    "nll",
    "retrieval_weighted",
    "topic_coherence_adjusted",
    "ensemble_disagreement",
    "clinical_harm_weighted",
]


@dataclass(frozen=True, slots=True)
class ScoreInputs:
    """All signals any of the 5 scores may consume.

    Fields are Optional where a score can fall back; None on a required
    field for the chosen score forces the fail-closed +inf path.
    """

    # NLL and most derived scores
    avg_logprob: float | None = None

    # retrieval_weighted
    top1_similarity: float | None = None

    # topic_coherence_adjusted
    topic_score: float | None = None

    # ensemble_disagreement
    sample_avg_logprobs: tuple[float, ...] = ()

    # clinical_harm_weighted
    classified_intent: str | None = None


# Mapping from classified_intent to harm class. The *_weight parameters
# come from ConformalSettings; the mapping is the contract between the
# prefilter's 42-intent taxonomy (issue #17) and the harm taxonomy.
# Unknown intents default to "moderate" — a safe middle-ground that
# keeps coverage honest without over-weighting.
_HARM_CLASS_BY_INTENT: Final[dict[str, str]] = {
    # Catastrophic: wrong answer could kill the patient today
    "dosing": "catastrophic",
    "pediatric_dosing": "catastrophic",
    "contraindication": "catastrophic",
    "drug_interaction": "catastrophic",
    "pregnancy_safety": "catastrophic",
    # Major: wrong answer causes significant harm
    "diagnosis": "major",
    "differential_diagnosis": "major",
    "referral_criteria": "major",
    "red_flags": "major",
    # Moderate: wrong answer causes suboptimal care
    "malaria_treatment": "moderate",
    "tb_treatment": "moderate",
    "hiv_treatment": "moderate",
    "general_info": "moderate",
    # Minor: wrong answer is a style/phrasing issue
    "patient_education": "minor",
    "administrative": "minor",
}


def _nll_from_avg_logprob(avg_logprob: float | None) -> float:
    """Convert an averaged token logprob to NLL. Fail-closed on None."""
    if avg_logprob is None:
        return math.inf
    if not math.isfinite(avg_logprob):
        return math.inf
    return -float(avg_logprob)


def score_nll(inputs: ScoreInputs, settings: ConformalSettings | None = None) -> float:
    """Negative log-likelihood of the generated sequence.

    Pure function of avg_logprob; the simplest baseline score. Used as
    the fallback for every other score when its required signals are
    missing.
    """
    del settings
    return _nll_from_avg_logprob(inputs.avg_logprob)


def score_retrieval_weighted(
    inputs: ScoreInputs, settings: ConformalSettings | None = None
) -> float:
    """NLL weighted by top-1 retrieval similarity.

    s = NLL / max(top1_similarity, epsilon). A retrieval top1 of 0.0
    produces +inf via the epsilon guard; low retrieval similarity
    inflates the score so low-retrieval-confidence responses are
    less likely to be in the prediction set.
    """
    del settings
    nll = _nll_from_avg_logprob(inputs.avg_logprob)
    if inputs.top1_similarity is None:
        return math.inf
    if not math.isfinite(inputs.top1_similarity) or inputs.top1_similarity <= 0.0:
        return math.inf
    epsilon = 1e-3
    return nll / max(float(inputs.top1_similarity), epsilon)


def score_topic_coherence_adjusted(
    inputs: ScoreInputs, settings: ConformalSettings | None = None
) -> float:
    """NLL scaled by (2 - topic_score).

    topic_score=1.0 → factor 1.0 (no adjustment).
    topic_score=0.0 → factor 2.0 (doubles the score).
    Topic score bounded to [0, 1] for the factor to stay in [1, 2].
    """
    del settings
    nll = _nll_from_avg_logprob(inputs.avg_logprob)
    if inputs.topic_score is None:
        return math.inf
    if not math.isfinite(inputs.topic_score):
        return math.inf
    bounded = max(0.0, min(1.0, float(inputs.topic_score)))
    return nll * (2.0 - bounded)


def score_ensemble_disagreement(
    inputs: ScoreInputs, settings: ConformalSettings | None = None
) -> float:
    """Sample standard deviation across a batch of generations.

    Requires at least 2 sampled avg_logprobs. Returns +inf when fewer
    samples are available (fail-closed: the caller explicitly asked for
    ensemble disagreement and cannot produce a valid score).
    """
    del settings
    samples = inputs.sample_avg_logprobs
    if len(samples) < 2:
        return math.inf
    finite = [float(s) for s in samples if math.isfinite(s)]
    if len(finite) < 2:
        return math.inf
    return float(statistics.stdev(finite))


def score_clinical_harm_weighted(
    inputs: ScoreInputs, settings: ConformalSettings | None = None
) -> float:
    """NLL multiplied by a harm weight keyed on classified intent.

    Catastrophic categories (dosing, contraindication, pediatric,
    pregnancy) get weight 10x by default. Unknown intents fall back to
    the 'moderate' weight — not to 'minor' — because under-weighting is
    the failure mode that harms patients. SKILL.md §0.1 (fail closed).
    """
    if settings is None:
        raise ValueError(
            "clinical_harm_weighted requires settings for harm weights; " "caller passed None"
        )
    nll = _nll_from_avg_logprob(inputs.avg_logprob)
    intent = inputs.classified_intent
    harm_class = _HARM_CLASS_BY_INTENT.get(intent or "", "moderate")
    weight = {
        "catastrophic": settings.harm_weight_catastrophic,
        "major": settings.harm_weight_major,
        "moderate": settings.harm_weight_moderate,
        "minor": settings.harm_weight_minor,
    }[harm_class]
    return nll * weight


_SCORERS: Final[dict[ScoreName, object]] = {
    "nll": score_nll,
    "retrieval_weighted": score_retrieval_weighted,
    "topic_coherence_adjusted": score_topic_coherence_adjusted,
    "ensemble_disagreement": score_ensemble_disagreement,
    "clinical_harm_weighted": score_clinical_harm_weighted,
}


def compute_score(
    name: ScoreName, inputs: ScoreInputs, settings: ConformalSettings | None = None
) -> float:
    """Dispatch table. Raises KeyError on unknown name (enum enforces at
    settings load time; this is a defensive guard for programmatic
    callers).
    """
    scorer = _SCORERS[name]
    return scorer(inputs, settings)  # type: ignore[operator]
