"""Tests for run_round orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from active_learning.acquisition import CandidateCase
from active_learning.assignment import Assignment
from active_learning.scheduler import iso_week, run_round


class FakeRepository:
    def __init__(self, candidates: list[CandidateCase]) -> None:
        self.candidates = candidates
        self.persisted: list[Assignment] = []
        self.load_args: dict[str, Any] = {}

    async def load_candidates(
        self, *, ingested_since: Any, max_rows: int
    ) -> list[CandidateCase]:
        self.load_args = {"ingested_since": ingested_since, "max_rows": max_rows}
        return self.candidates[:max_rows]

    async def persist_assignments(self, assignments: list[Assignment]) -> int:
        self.persisted.extend(assignments)
        return len(assignments)


class FakeQueue:
    def __init__(self) -> None:
        self.pushed: list[tuple[list[str], str]] = []

    async def push_batch(self, *, case_ids: list[str], week_iso: str) -> None:
        self.pushed.append((list(case_ids), week_iso))


def _case(case_id: str, set_size: int) -> CandidateCase:
    return CandidateCase(
        case_id=case_id,
        stratum="general",
        token_logprobs=(-0.1, -2.0),
        conformal_set_size=set_size,
        conformal_coverage_target=0.9,
        truth_in_set=None,
        ingested_at_iso="2026-04-19T00:00:00Z",
    )


def test_iso_week_formats_correctly() -> None:
    now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)
    assert iso_week(now) == "2026-W16"


def test_iso_week_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        iso_week(datetime(2026, 4, 19, 12, 0, 0))


async def test_run_round_picks_highest_set_size_candidates() -> None:
    repo: Any = FakeRepository([_case(f"c-{i}", set_size=i + 1) for i in range(30)])
    queue: Any = FakeQueue()
    now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)

    result = await run_round(
        repository=repo,
        queue=queue,
        acquisition_function_name="conformal_set_size",
        batch_size=5,
        control_ratio=0.3,
        seed="test-seed",
        now=now,
    )

    assert result.week_iso == "2026-W16"
    assert result.n_candidates == 30
    assert result.n_assignments == 5
    assert result.n_treatment + result.n_control == 5
    # Top-5 by set_size should be c-29 ... c-25 in descending order.
    top_ids = {a.case_id for a in repo.persisted}
    assert top_ids == {"c-25", "c-26", "c-27", "c-28", "c-29"}


async def test_run_round_pushes_picked_cases_to_queue() -> None:
    repo: Any = FakeRepository([_case(f"c-{i}", set_size=i + 1) for i in range(20)])
    queue: Any = FakeQueue()
    now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)

    await run_round(
        repository=repo,
        queue=queue,
        acquisition_function_name="conformal_set_size",
        batch_size=5,
        control_ratio=0.3,
        seed="q",
        now=now,
    )

    assert len(queue.pushed) == 1
    pushed_ids, week = queue.pushed[0]
    assert week == "2026-W16"
    assert len(pushed_ids) == 5


async def test_run_round_empty_pool_yields_no_assignments() -> None:
    repo: Any = FakeRepository([])
    queue: Any = FakeQueue()
    now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)

    result = await run_round(
        repository=repo,
        queue=queue,
        acquisition_function_name="random",
        batch_size=5,
        control_ratio=0.3,
        seed="s",
        now=now,
    )
    assert result.n_assignments == 0
    assert queue.pushed == [([], "2026-W16")]


async def test_run_round_is_reproducible_given_same_inputs() -> None:
    candidates = [_case(f"c-{i}", set_size=(i * 7) % 11 + 1) for i in range(30)]
    now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)

    async def run() -> list[str]:
        repo: Any = FakeRepository(list(candidates))
        queue: Any = FakeQueue()
        await run_round(
            repository=repo,
            queue=queue,
            acquisition_function_name="conformal_set_size",
            batch_size=8,
            control_ratio=0.3,
            seed="paper-p3",
            now=now,
            rng_seed=42,
        )
        return [a.case_id for a in repo.persisted]

    a = await run()
    b = await run()
    assert a == b


async def test_run_round_rejects_degenerate_ratio() -> None:
    repo: Any = FakeRepository([])
    queue: Any = FakeQueue()
    now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="control_ratio"):
        await run_round(
            repository=repo,
            queue=queue,
            acquisition_function_name="random",
            batch_size=5,
            control_ratio=0.0,
            seed="s",
            now=now,
        )
