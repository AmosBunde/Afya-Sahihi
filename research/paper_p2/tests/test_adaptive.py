"""Tests for adaptive CP."""

from __future__ import annotations

import random

import pytest

from research.paper_p2.adaptive import (
    AdaptiveState,
    initial_state,
    long_run_miscoverage,
    run_sequence,
    update,
)


def test_initial_state_rejects_bad_alpha() -> None:
    with pytest.raises(ValueError, match="alpha"):
        initial_state(alpha=0.0, gamma=0.01)
    with pytest.raises(ValueError, match="alpha"):
        initial_state(alpha=1.0, gamma=0.01)
    with pytest.raises(ValueError, match="alpha"):
        initial_state(alpha=-0.1, gamma=0.01)


def test_initial_state_rejects_non_positive_gamma() -> None:
    with pytest.raises(ValueError, match="gamma"):
        initial_state(alpha=0.1, gamma=0.0)
    with pytest.raises(ValueError, match="gamma"):
        initial_state(alpha=0.1, gamma=-0.01)


def test_update_on_miscovered_decreases_q_hat() -> None:
    # Gibbs 2021 Algorithm 1 treats q_hat as the current MISCOVERAGE
    # TARGET (a probability), not a score threshold. A miscoverage
    # observation tightens the target → q_hat decreases.
    # Step: q += γ(α − miscov) = 0.05 · (0.1 − 1) = −0.045.
    state = initial_state(alpha=0.1, gamma=0.05, q_hat_0=0.5)
    new_state = update(state, covered=False)
    assert new_state.q_hat < state.q_hat
    assert new_state.q_hat == pytest.approx(0.5 + 0.05 * (0.1 - 1))


def test_update_on_covered_increases_q_hat() -> None:
    # Mirror of the miscovered test: a covered observation loosens
    # the miscoverage target → q_hat increases by γ·α = 0.005.
    state = initial_state(alpha=0.1, gamma=0.05, q_hat_0=0.5)
    new_state = update(state, covered=True)
    assert new_state.q_hat > state.q_hat
    assert new_state.q_hat == pytest.approx(0.5 + 0.05 * 0.1)


def test_update_increments_step() -> None:
    state = initial_state(alpha=0.1, gamma=0.01)
    for i in range(5):
        state = update(state, covered=True)
        assert state.step == i + 1


def test_run_sequence_returns_initial_plus_one_per_step() -> None:
    history = run_sequence(alpha=0.1, gamma=0.01, coverage_feedback=[True, False, True])
    assert len(history) == 4
    # First element is the initial state.
    assert history[0].step == 0
    assert history[-1].step == 3


def test_long_run_miscoverage_converges_to_alpha() -> None:
    # Generate a Bernoulli(α) stream of miscoverage indicators.
    # The average `not covered` across the stream should equal α.
    # Adaptive CP's long-run miscoverage should equal the input rate.
    rng = random.Random(42)
    alpha = 0.1
    n = 10_000
    coverage_stream = [rng.random() > alpha for _ in range(n)]
    history = run_sequence(alpha=alpha, gamma=0.01, coverage_feedback=coverage_stream)
    recovered = long_run_miscoverage(history)
    # Empirical miscoverage should be close to α.
    assert abs(recovered - alpha) < 0.02


def test_run_sequence_zero_length_returns_initial_only() -> None:
    history = run_sequence(alpha=0.1, gamma=0.01, coverage_feedback=[])
    assert len(history) == 1
    assert history[0].step == 0


def test_adaptive_state_is_immutable() -> None:
    state = initial_state(alpha=0.1, gamma=0.01)
    # Dataclass is frozen — attempting to mutate raises FrozenInstanceError.
    with pytest.raises(AttributeError):
        state.q_hat = 0.9  # type: ignore[misc]
    assert isinstance(state, AdaptiveState)
