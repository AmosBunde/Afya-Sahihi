"""Orchestration tests for the conformal service — in-memory repo fake."""

from __future__ import annotations

import pytest

from conformal.predictor import Candidate
from conformal.scores import ScoreInputs
from conformal.service import ConformalService
from conformal.settings import ConformalSettings


class _FakeRepo:
    def __init__(self, scores_by_stratum: dict[str, list[float]]) -> None:
        self._by_stratum = scores_by_stratum

    async def fetch_scores(self, *, score_type: str, stratum: str, max_size: int) -> list[float]:
        return list(self._by_stratum.get(stratum, []))[:max_size]


def _settings(**overrides: object) -> ConformalSettings:
    base: dict[str, object] = {
        "pg_host": "localhost",
        "pg_password": "x",
        "cp_alpha": 0.10,
        "calibration_set_min_size_per_stratum": 100,
        "nonconformity_score": "nll",
    }
    base.update(overrides)
    return ConformalSettings(**base)  # type: ignore[arg-type]


def _candidates(scores: list[float]) -> list[Candidate]:
    return [Candidate(label=f"cand-{i}", score=s) for i, s in enumerate(scores)]


@pytest.mark.asyncio
async def test_service_refuses_when_calibration_undersized() -> None:
    # 50 calibration samples but min is 100 → refuse
    repo = _FakeRepo({"en:dosing": [float(i) for i in range(50)]})
    service = ConformalService(settings=_settings(), repository=repo)
    outcome = await service.construct_set(
        candidates=_candidates([0.1, 0.5, 2.0]),
        stratum="en:dosing",
        score_inputs=ScoreInputs(avg_logprob=-0.5),
    )
    assert outcome.prediction_set is None
    assert "calibration_undersized" in outcome.refusal_reason


@pytest.mark.asyncio
async def test_service_constructs_set_when_calibration_sufficient() -> None:
    # 200 scores 0..199; alpha=0.10 → k = ceil(201 * 0.9) - 1 = 181 - 1 = 180
    # Sorted[180] = 180. Candidates with score <= 180 are included.
    repo = _FakeRepo({"en:dosing": [float(i) for i in range(200)]})
    service = ConformalService(settings=_settings(), repository=repo)
    outcome = await service.construct_set(
        candidates=_candidates([50.0, 100.0, 181.0, 200.0]),
        stratum="en:dosing",
        score_inputs=ScoreInputs(avg_logprob=-0.5),
    )
    assert outcome.prediction_set is not None
    # 50 and 100 are below q_hat=180; 181 and 200 are not.
    assert outcome.prediction_set.set_size == 2
    assert outcome.prediction_set.labels == ("cand-0", "cand-1")
    assert outcome.prediction_set.target_coverage_met is True


@pytest.mark.asyncio
async def test_service_empty_candidates_yields_unmet_coverage() -> None:
    repo = _FakeRepo({"en:dosing": [float(i) for i in range(200)]})
    service = ConformalService(settings=_settings(), repository=repo)
    outcome = await service.construct_set(
        candidates=[],
        stratum="en:dosing",
        score_inputs=ScoreInputs(avg_logprob=-0.5),
    )
    assert outcome.prediction_set is not None
    assert outcome.prediction_set.set_size == 0
    assert outcome.prediction_set.target_coverage_met is False


@pytest.mark.asyncio
async def test_service_stratified_q_hats_differ() -> None:
    # Two strata with different score distributions → different q_hat,
    # so the same candidate score can be in-set for one and out-of-set
    # for the other. This is the whole point of stratification.
    repo = _FakeRepo(
        {
            "en:dosing": [float(i) for i in range(200)],  # q_hat=180
            "sw:general_info": [float(i) / 10 for i in range(200)],  # q_hat=18.0
        }
    )
    service = ConformalService(settings=_settings(), repository=repo)

    candidate_score = 100.0

    out_en = await service.construct_set(
        candidates=_candidates([candidate_score]),
        stratum="en:dosing",
        score_inputs=ScoreInputs(avg_logprob=-0.5),
    )
    out_sw = await service.construct_set(
        candidates=_candidates([candidate_score]),
        stratum="sw:general_info",
        score_inputs=ScoreInputs(avg_logprob=-0.5),
    )

    assert out_en.prediction_set is not None
    assert out_sw.prediction_set is not None
    # 100 <= 180 in en → included
    assert out_en.prediction_set.set_size == 1
    # 100 > 18 in sw → excluded
    assert out_sw.prediction_set.set_size == 0


@pytest.mark.asyncio
async def test_service_uses_override_score_name() -> None:
    repo = _FakeRepo({"en:dosing": [float(i) for i in range(200)]})
    service = ConformalService(
        settings=_settings(nonconformity_score="nll"),  # default
        repository=repo,
    )
    outcome = await service.construct_set(
        candidates=_candidates([50.0]),
        stratum="en:dosing",
        score_inputs=ScoreInputs(avg_logprob=-0.5, classified_intent="dosing"),
        score_name="clinical_harm_weighted",
    )
    assert outcome.score_type_used == "clinical_harm_weighted"
