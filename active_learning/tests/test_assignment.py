"""Tests for treatment/control arm assignment."""

from __future__ import annotations

import pytest

from active_learning.assignment import (
    _hash_01,
    assign_arm,
    build_assignments,
    partition,
)


def test_hash_is_in_unit_interval() -> None:
    for parts in [("a",), ("a", "b"), ("a", "b", "c")]:
        v = _hash_01(*parts)
        assert 0.0 <= v < 1.0


def test_hash_is_deterministic() -> None:
    a = _hash_01("seed", "2026-W16", "case-1")
    b = _hash_01("seed", "2026-W16", "case-1")
    assert a == b


def test_hash_changes_with_inputs() -> None:
    a = _hash_01("seed", "2026-W16", "case-1")
    b = _hash_01("seed", "2026-W16", "case-2")
    c = _hash_01("seed", "2026-W17", "case-1")
    d = _hash_01("different-seed", "2026-W16", "case-1")
    assert len({a, b, c, d}) == 4


def test_assign_arm_deterministic_for_same_triple() -> None:
    a = assign_arm(case_id="c-1", week_iso="2026-W16", seed="s", control_ratio=0.3)
    b = assign_arm(case_id="c-1", week_iso="2026-W16", seed="s", control_ratio=0.3)
    assert a == b


def test_assign_arm_ratio_near_30pct_over_sample() -> None:
    # 10k cases, control_ratio=0.3 → observed control share within ±5pp.
    n = 10000
    controls = sum(
        1
        for i in range(n)
        if assign_arm(
            case_id=f"case-{i}",
            week_iso="2026-W16",
            seed="replication",
            control_ratio=0.3,
        )
        == "control"
    )
    ratio = controls / n
    assert 0.25 < ratio < 0.35, f"observed control share {ratio:.3f} outside band"


def test_assign_arm_rejects_degenerate_ratio() -> None:
    with pytest.raises(ValueError, match="0, 1"):
        assign_arm(case_id="c-1", week_iso="w", seed="s", control_ratio=0.0)
    with pytest.raises(ValueError, match="0, 1"):
        assign_arm(case_id="c-1", week_iso="w", seed="s", control_ratio=1.0)
    with pytest.raises(ValueError, match="0, 1"):
        assign_arm(case_id="c-1", week_iso="w", seed="s", control_ratio=-0.1)


def test_build_assignments_labels_control_arm_as_random() -> None:
    # Regardless of the treatment acquisition function, control-arm
    # cases record "random" — the analysis table must be
    # self-describing.
    assignments = build_assignments(
        case_ids=[f"c-{i}" for i in range(200)],
        week_iso="2026-W16",
        seed="seed",
        control_ratio=0.3,
        acquisition_function_name="clinical_harm_weighted",
    )
    for a in assignments:
        if a.arm == "control":
            assert a.acquisition_function == "random"
        else:
            assert a.acquisition_function == "clinical_harm_weighted"


def test_build_assignments_empty_returns_empty() -> None:
    assignments = build_assignments(
        case_ids=[],
        week_iso="2026-W16",
        seed="seed",
        control_ratio=0.3,
        acquisition_function_name="random",
    )
    assert assignments == []


def test_partition_splits_by_arm() -> None:
    assignments = build_assignments(
        case_ids=[f"c-{i}" for i in range(50)],
        week_iso="2026-W16",
        seed="partition-test",
        control_ratio=0.3,
        acquisition_function_name="uncertainty_entropy",
    )
    treatment, control = partition(assignments)
    # Sets should be disjoint; union covers every input case_id.
    assert set(treatment).isdisjoint(set(control))
    assert set(treatment) | set(control) == {a.case_id for a in assignments}
