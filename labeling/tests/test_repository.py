"""Tests for GradeRepository. Uses a fake asyncpg pool + transaction."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import pytest

from labeling.repository import GradeRepository
from labeling.rubric import RubricScores


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.fetchval_result: Any = None
        self.fetch_result: list[dict[str, Any]] = []
        self.transaction_entered: int = 0

    async def execute(self, query: str, *args: Any) -> Any:
        self.executed.append((query, args))
        return "OK"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.executed.append((query, args))
        return self.fetchval_result

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.executed.append((query, args))
        return self.fetch_result

    def transaction(self, **_: Any) -> Any:
        @asynccontextmanager
        async def _cm() -> Any:
            self.transaction_entered += 1
            yield

        return _cm()


class FakePool:
    def __init__(self, conn: FakeConnection) -> None:
        self._conn = conn

    def acquire(self) -> Any:
        conn = self._conn

        @asynccontextmanager
        async def _cm() -> Any:
            yield conn

        return _cm()


@pytest.fixture
def conn() -> FakeConnection:
    return FakeConnection()


@pytest.fixture
def repo(conn: FakeConnection) -> GradeRepository:
    return GradeRepository(pool=FakePool(conn), statement_timeout_ms=1234)


def _scores() -> RubricScores:
    return RubricScores(
        accuracy=4,
        safety=5,
        guideline_alignment=4,
        local_appropriateness=3,
        clarity=4,
    )


async def test_insert_next_grade_runs_inside_transaction(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    await repo.insert_next_grade(
        grade_id="g-1",
        case_id="c-1",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=_scores(),
        notes="ok",
        time_spent_seconds=90,
        submitted_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert conn.transaction_entered == 1


async def test_insert_next_grade_sets_statement_timeout(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    await repo.insert_next_grade(
        grade_id="g-1",
        case_id="c-1",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=_scores(),
        notes="ok",
        time_spent_seconds=90,
        submitted_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    timeout_calls = [
        q for q, _ in conn.executed if q.startswith("SET LOCAL statement_timeout")
    ]
    assert len(timeout_calls) == 1
    assert "1234ms" in timeout_calls[0]


async def test_insert_next_grade_takes_advisory_lock(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    await repo.insert_next_grade(
        grade_id="g-1",
        case_id="c-1",
        reviewer_id="u-42",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=_scores(),
        notes="ok",
        time_spent_seconds=90,
        submitted_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    lock_calls = [
        (q, args) for q, args in conn.executed if "pg_advisory_xact_lock" in q
    ]
    assert len(lock_calls) == 1
    assert lock_calls[0][1] == ("u-42",)


async def test_insert_next_grade_chains_on_prev_hash(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    conn.fetchval_result = "previoushash123"
    row_hash = await repo.insert_next_grade(
        grade_id="g-2",
        case_id="c-2",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=_scores(),
        notes="ok",
        time_spent_seconds=90,
        submitted_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert row_hash
    assert len(row_hash) == 64  # SHA-256 hex

    # The INSERT args include prev_hash=fetchval_result
    insert_args = next(
        args for q, args in conn.executed if q.strip().startswith("INSERT")
    )
    assert insert_args[13] == "previoushash123"  # prev_hash
    assert insert_args[14] == row_hash


async def test_insert_next_grade_genesis_uses_empty_prev_hash(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    conn.fetchval_result = None
    await repo.insert_next_grade(
        grade_id="g-1",
        case_id="c-1",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=_scores(),
        notes="ok",
        time_spent_seconds=90,
        submitted_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
    )
    insert_args = next(
        args for q, args in conn.executed if q.strip().startswith("INSERT")
    )
    assert insert_args[13] == ""  # prev_hash


async def test_load_agreement_runs_inside_transaction(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    conn.fetch_result = []
    window_start = datetime(2026, 4, 17, 0, 0, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 4, 18, 0, 0, 0, tzinfo=timezone.utc)
    await repo.load_agreement_ratings(window_start=window_start, window_end=window_end)
    assert conn.transaction_entered == 1


async def test_load_agreement_groups_ratings_by_case_and_dimension(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    conn.fetch_result = [
        {
            "case_id": "c-1",
            "reviewer_id": "u-1",
            "accuracy": 5,
            "safety": 4,
            "guideline_alignment": 5,
            "local_appropriateness": 4,
            "clarity": 5,
        },
        {
            "case_id": "c-1",
            "reviewer_id": "u-2",
            "accuracy": 4,
            "safety": 4,
            "guideline_alignment": 5,
            "local_appropriateness": 3,
            "clarity": 4,
        },
        {
            "case_id": "c-2",
            "reviewer_id": "u-1",
            "accuracy": 2,
            "safety": 3,
            "guideline_alignment": 2,
            "local_appropriateness": 3,
            "clarity": 3,
        },
    ]
    window_start = datetime(2026, 4, 17, 0, 0, 0, tzinfo=timezone.utc)
    window_end = datetime(2026, 4, 18, 0, 0, 0, tzinfo=timezone.utc)
    result = await repo.load_agreement_ratings(
        window_start=window_start, window_end=window_end
    )
    assert set(result.keys()) == {"c-1", "c-2"}
    assert len(result["c-1"]["accuracy"]) == 2
    assert result["c-1"]["accuracy"][0] == {"reviewer_id": "u-1", "score": 5}
    assert result["c-1"]["accuracy"][1] == {"reviewer_id": "u-2", "score": 4}
    assert len(result["c-2"]["safety"]) == 1
