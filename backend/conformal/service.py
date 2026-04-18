"""Conformal prediction service.

Ties the pieces together: score candidates, fetch calibration from the
stratum, compute q_hat, construct the prediction set. Exposes a single
entrypoint for the orchestrator's `construct_set` call.

Per SKILL.md §0.1 every failure mode is fail-closed: an undersized
calibration stratum, an unreachable DB, a missing score input — all
return a ConformalOutcome with target_coverage_met=False and a reason
string that the orchestrator's error handler maps to a refusal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from conformal.calibration import q_hat_from_scores
from conformal.predictor import Candidate, PredictionSet, construct_prediction_set
from conformal.scores import ScoreInputs, ScoreName, compute_score
from conformal.settings import ConformalSettings

logger = logging.getLogger(__name__)


class CalibrationRepo(Protocol):
    """Narrow protocol for the calibration repository.

    The concrete implementation is `conformal.repository.CalibrationRepository`;
    tests inject an in-memory fake.
    """

    async def fetch_scores(
        self, *, score_type: str, stratum: str, max_size: int
    ) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class ConformalOutcome:
    """Result returned to the orchestrator.

    `prediction_set` is None when the service refused (undersized
    calibration, empty candidates, etc); the orchestrator treats that
    as a PipelineError downstream.
    """

    prediction_set: PredictionSet | None
    refusal_reason: str = ""
    score_type_used: str = ""


class ConformalService:
    """Orchestrates score → calibration lookup → set construction."""

    def __init__(self, *, settings: ConformalSettings, repository: CalibrationRepo) -> None:
        self._settings = settings
        self._repo = repository

    async def construct_set(
        self,
        *,
        candidates: list[Candidate],
        stratum: str,
        score_inputs: ScoreInputs,
        score_name: ScoreName | None = None,
    ) -> ConformalOutcome:
        """Construct the prediction set for one (query, retrieval, generation).

        `candidates` already carry their scores — the caller decides how
        to score each candidate (per-chunk, per-answer-token, etc). The
        service uses `score_inputs` + `score_name` to compute a
        response-level score for logging/monitoring (issue #26).
        """
        name = score_name or self._settings.nonconformity_score  # type: ignore[assignment]
        response_score = compute_score(name, score_inputs, self._settings)  # type: ignore[arg-type]

        cal_scores = await self._repo.fetch_scores(
            score_type=name,
            stratum=stratum,
            max_size=self._settings.calibration_set_max_size,
        )

        if len(cal_scores) < self._settings.calibration_set_min_size_per_stratum:
            logger.warning(
                "calibration stratum undersized; refusing",
                extra={
                    "stratum": stratum,
                    "score_type": name,
                    "n_calibration": len(cal_scores),
                    "min_required": self._settings.calibration_set_min_size_per_stratum,
                },
            )
            return ConformalOutcome(
                prediction_set=None,
                refusal_reason=f"calibration_undersized:{len(cal_scores)}<{self._settings.calibration_set_min_size_per_stratum}",
                score_type_used=str(name),
            )

        q_hat = q_hat_from_scores(cal_scores, alpha=self._settings.cp_alpha)
        prediction_set = construct_prediction_set(
            candidates=candidates,
            q_hat=q_hat,
            stratum=stratum,
        )

        logger.info(
            "conformal set constructed",
            extra={
                "stratum": stratum,
                "score_type": name,
                "response_score": round(response_score, 4)
                if response_score != float("inf")
                else "inf",
                "q_hat": round(q_hat, 4) if q_hat != float("inf") else "inf",
                "set_size": prediction_set.set_size,
                "target_coverage_met": prediction_set.target_coverage_met,
            },
        )
        return ConformalOutcome(
            prediction_set=prediction_set,
            score_type_used=str(name),
        )
