"""Treatment / control arm assignment.

Pre-registered design:
  - 70% of each week's 20 cases come from the configured acquisition
    function (treatment arm).
  - 30% come from uniform-random sampling (control arm).
  - Assignment is decided BEFORE the reviewer sees the case so their
    grade cannot be biased by knowing the arm. The reviewer UI does
    not display the arm; the only leak path would be the case_id
    itself, which we avoid encoding arm information into.
  - Assignment is deterministic given (case_id, week_iso, seed) so a
    replay for the Paper P3 analysis reproduces the same arm split.

The assignment hash uses SHA-256 of "{seed}|{week}|{case_id}" mapped
onto [0,1). A case's arm is decided by whether the hash falls below
control_ratio. SHA-256 over stable inputs means the arm is fixed
regardless of when we run it — useful for replay.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

Arm = Literal["treatment", "control"]


@dataclass(frozen=True, slots=True)
class Assignment:
    case_id: str
    arm: Arm
    week_iso: str
    acquisition_function: str  # "random" when arm == "control"


def _hash_01(*parts: str) -> float:
    """Deterministic float in [0, 1) from a hash of the parts."""
    h = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    # Take the first 8 bytes (64 bits) as a big-endian unsigned int,
    # then divide by 2^64 to land in [0, 1).
    value = int.from_bytes(h[:8], "big", signed=False)
    return value / (1 << 64)


def assign_arm(
    *,
    case_id: str,
    week_iso: str,
    seed: str,
    control_ratio: float,
) -> Arm:
    """Deterministic arm for one (case, week, seed) triple.

    control_ratio must be in (0, 1). A ratio at the boundaries would
    mean all-treatment or all-control, which defeats the causal
    comparison — we refuse both.
    """
    if not (0.0 < control_ratio < 1.0):
        raise ValueError(f"control_ratio must be in (0, 1); got {control_ratio}")
    r = _hash_01(seed, week_iso, case_id)
    return "control" if r < control_ratio else "treatment"


def build_assignments(
    *,
    case_ids: list[str],
    week_iso: str,
    seed: str,
    control_ratio: float,
    acquisition_function_name: str,
) -> list[Assignment]:
    """Compute arm + acquisition metadata for a week's batch."""
    if not case_ids:
        return []
    out: list[Assignment] = []
    for case_id in case_ids:
        arm = assign_arm(
            case_id=case_id,
            week_iso=week_iso,
            seed=seed,
            control_ratio=control_ratio,
        )
        out.append(
            Assignment(
                case_id=case_id,
                arm=arm,
                week_iso=week_iso,
                # Control-arm cases are selected by the random picker
                # upstream, so we record "random" here even when the
                # configured treatment function is something else. This
                # keeps the analysis table self-describing.
                acquisition_function=(
                    "random" if arm == "control" else acquisition_function_name
                ),
            )
        )
    return out


def partition(assignments: list[Assignment]) -> tuple[list[str], list[str]]:
    """Return (treatment_ids, control_ids) preserving input order."""
    t: list[str] = []
    c: list[str] = []
    for a in assignments:
        (t if a.arm == "treatment" else c).append(a.case_id)
    return t, c
