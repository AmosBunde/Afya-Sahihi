"""Tests for the Redis-backed queue. Uses an in-memory fake."""

from __future__ import annotations

import pytest

from labeling.queue import QueueKeys, ReviewerCaseQueue


class FakeRedis:
    """Minimal in-memory Redis stand-in covering the methods used."""

    def __init__(self) -> None:
        self._lists: dict[str, list[str]] = {}
        self._sets: dict[str, set[str]] = {}

    async def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        items = self._lists.get(key, [])
        stop = len(items) if end == -1 else end + 1
        return [item.encode("utf-8") for item in items[start:stop]]

    async def lrem(self, key: str, count: int, value: str) -> int:
        items = self._lists.get(key, [])
        removed = 0
        target = count if count > 0 else len(items)
        new_items: list[str] = []
        for item in items:
            if item == value and removed < target:
                removed += 1
                continue
            new_items.append(item)
        self._lists[key] = new_items
        return removed

    async def rpush(self, key: str, *values: str) -> int:
        bucket = self._lists.setdefault(key, [])
        bucket.extend(values)
        return len(bucket)

    async def sadd(self, key: str, *values: str) -> int:
        bucket = self._sets.setdefault(key, set())
        added = 0
        for v in values:
            if v not in bucket:
                bucket.add(v)
                added += 1
        return added

    async def smembers(self, key: str) -> set[bytes]:
        return {v.encode("utf-8") for v in self._sets.get(key, set())}

    async def scard(self, key: str) -> int:
        return len(self._sets.get(key, set()))


@pytest.fixture
def keys() -> QueueKeys:
    return QueueKeys.for_reviewer(
        base_key="test:labeling:q",
        reviewer_id="u-1",
        iso_week="2026-W16",
    )


@pytest.fixture
async def queue(keys: QueueKeys) -> ReviewerCaseQueue:
    redis = FakeRedis()
    # Seed pending cases for the reviewer.
    await redis.rpush(keys.pending, "case-1", "case-2", "case-3")
    return ReviewerCaseQueue(redis=redis, keys=keys)


async def test_queue_keys_namespacing() -> None:
    keys = QueueKeys.for_reviewer(
        base_key="afya:lbl",
        reviewer_id="u-42",
        iso_week="2026-W16",
    )
    assert keys.pending == "afya:lbl:u-42:2026-W16:pending"
    assert keys.in_flight == "afya:lbl:u-42:2026-W16:in_flight"
    assert keys.completed == "afya:lbl:u-42:2026-W16:completed"


async def test_list_pending_returns_cases(queue: ReviewerCaseQueue) -> None:
    pending = await queue.list_pending()
    assert pending == ["case-1", "case-2", "case-3"]


async def test_reserve_next_moves_head_to_in_flight(
    queue: ReviewerCaseQueue,
) -> None:
    first = await queue.reserve_next()
    assert first == "case-1"
    remaining = await queue.list_pending()
    assert remaining == ["case-2", "case-3"]


async def test_reserve_next_on_empty_queue_returns_none(keys: QueueKeys) -> None:
    q = ReviewerCaseQueue(redis=FakeRedis(), keys=keys)
    assert await q.reserve_next() is None


async def test_complete_moves_in_flight_to_completed_set(
    queue: ReviewerCaseQueue,
) -> None:
    await queue.reserve_next()  # reserves case-1
    returned = await queue.complete("case-1")
    assert returned is True
    assert await queue.completed_count() == 1


async def test_complete_of_unreserved_returns_false(
    queue: ReviewerCaseQueue,
) -> None:
    returned = await queue.complete("case-99")
    assert returned is False
    # Still recorded as completed in the set (idempotent analytics).
    assert await queue.completed_count() == 1


async def test_release_returns_case_to_pending(queue: ReviewerCaseQueue) -> None:
    await queue.reserve_next()  # reserves case-1
    released = await queue.release("case-1")
    assert released is True
    pending = await queue.list_pending()
    # case-1 returned to tail, ordering: case-2, case-3, case-1.
    assert pending == ["case-2", "case-3", "case-1"]


async def test_release_of_unreserved_returns_false(
    queue: ReviewerCaseQueue,
) -> None:
    released = await queue.release("case-never-reserved")
    assert released is False


async def test_reserve_next_race_returns_none_on_lost_lrem(
    keys: QueueKeys,
) -> None:
    # Fake a Redis where LREM reports 0 (another reviewer grabbed it).
    class RacyFake(FakeRedis):
        async def lrem(self, key: str, count: int, value: str) -> int:
            # Simulate the other reviewer winning: pretend nothing was removed.
            return 0

    r = RacyFake()
    await r.rpush(keys.pending, "case-1")
    q = ReviewerCaseQueue(redis=r, keys=keys)
    assert await q.reserve_next() is None


async def test_complete_rejects_empty_case_id(queue: ReviewerCaseQueue) -> None:
    with pytest.raises(ValueError, match="case_id"):
        await queue.complete("")


async def test_release_rejects_empty_case_id(queue: ReviewerCaseQueue) -> None:
    with pytest.raises(ValueError, match="case_id"):
        await queue.release("")
