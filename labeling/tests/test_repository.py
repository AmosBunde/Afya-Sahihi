"""Tests for GradeRepository. Uses a fake asyncpg pool."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import pytest

from labeling.repository import GradeRepository
from labeling.rubric import RubricScores, build_grade


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.fetchval_result: Any = None
        self.fetch_result: list[dict[str, Any]] = []

    async def execute(self, query: str, *args: Any) -> Any:
        self.executed.append((query, args))
        return "OK"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.executed.append((query, args))
        return self.fetchval_result

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.executed.append((query, args))
        return self.fetch_result


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


def _grade() -> Any:
    return build_grade(
        grade_id="g-1",
        case_id="c-1",
        reviewer_id="u-1",
        reviewer_role="clinical_reviewer",
        rubric_version="v1",
        scores=RubricScores(
            accuracy=4,
            safety=5,
            guideline_alignment=4,
            local_appropriateness=3,
            clarity=4,
        ),
        notes="ok",
        time_spent_seconds=90,
        submitted_at=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
        prev_hash="",
    )


async def test_latest_row_hash_empty_returns_empty_string(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    conn.fetchval_result = None
    result = await repo.latest_row_hash(reviewer_id="u-1")
    assert result == ""


async def test_latest_row_hash_returns_value(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    conn.fetchval_result = "abcd1234"
    result = await repo.latest_row_hash(reviewer_id="u-1")
    assert result == "abcd1234"


async def test_insert_grade_sets_statement_timeout(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    await repo.insert_grade(_grade())
    timeout_calls = [
        q for q, _ in conn.executed if q.startswith("SET LOCAL statement_timeout")
    ]
    assert len(timeout_calls) == 1
    assert "1234ms" in timeout_calls[0]


async def test_insert_grade_passes_expected_columns(
    repo: GradeRepository, conn: FakeConnection
) -> None:
    grade = _grade()
    await repo.insert_grade(grade)
    # The INSERT is the second execute call (first is SET LOCAL).
    insert_call = [q for q, _ in conn.executed if q.strip().startswith("INSERT")]
    assert len(insert_call) == 1

    # Find the args for the INSERT
    for q, args in conn.executed:
        if q.strip().startswith("INSERT"):
            assert args[0] == "g-1"  # grade_id
            assert args[1] == "c-1"  # case_id
            assert args[2] == "u-1"  # reviewer_id
            assert args[3] == "clinical_reviewer"  # reviewer_role
            assert args[4] == "v1"  # rubric_version
            assert args[5] == 4  # accuracy
            assert args[6] == 5  # safety
            assert args[7] == 4  # guideline_alignment
            assert args[8] == 3  # local_appropriateness
            assert args[9] == 4  # clarity
            assert args[10] == "ok"  # notes
            assert args[11] == 90  # time_spent_seconds
            assert args[13] == ""  # prev_hash
            assert args[14] == grade.row_hash  # row_hash
            break


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
