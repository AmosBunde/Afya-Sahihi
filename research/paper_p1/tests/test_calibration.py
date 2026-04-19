"""Tests for baseline calibration methods."""

from __future__ import annotations

import random

import pytest

from research.paper_p1.calibration import (
    HistogramModel,
    PlattModel,
    TemperatureModel,
    ensemble_mean,
    fit_histogram,
    fit_platt,
    fit_temperature,
)
from research.paper_p1.metrics import ece


def _overconfident_data(n: int = 200, seed: int = 7) -> tuple[list[float], list[bool]]:
    """Generate data where the model is too confident.

    Sample confidences near 0.9 but flip labels so actual accuracy is
    ~0.7. A well-calibrated fit should push 0.9 → ~0.7 on new samples.
    """
    rng = random.Random(seed)
    confs: list[float] = []
    correct: list[bool] = []
    for _ in range(n):
        c = 0.85 + rng.random() * 0.1  # in [0.85, 0.95]
        confs.append(c)
        correct.append(rng.random() < 0.7)  # true accuracy 70%
    return confs, correct


# ---- TemperatureModel.apply ----


def test_temperature_model_identity_at_t_one() -> None:
    m = TemperatureModel(temperature=1.0)
    assert m.apply(0.3) == pytest.approx(0.3, abs=1e-9)
    assert m.apply(0.7) == pytest.approx(0.7, abs=1e-9)
    assert m.apply(0.5) == pytest.approx(0.5, abs=1e-9)


def test_temperature_model_flattens_on_high_t() -> None:
    # T > 1 pulls extremes toward 0.5.
    m = TemperatureModel(temperature=3.0)
    assert m.apply(0.99) < 0.99
    assert m.apply(0.01) > 0.01


def test_temperature_model_clamps_extremes() -> None:
    m = TemperatureModel(temperature=2.0)
    assert m.apply(0.0) == 0.0
    assert m.apply(1.0) == 1.0


# ---- fit_temperature ----


def test_fit_temperature_on_overconfident_data_increases_t() -> None:
    confs, correct = _overconfident_data(n=300)
    model = fit_temperature(confidences=confs, correct=correct)
    # Overconfident → T > 1.
    assert model.temperature > 1.0


def test_fit_temperature_reduces_ece() -> None:
    confs, correct = _overconfident_data(n=500, seed=11)
    model = fit_temperature(confidences=confs, correct=correct)
    calibrated = [model.apply(c) for c in confs]
    e_before = ece(confidences=confs, correct=correct, n_bins=10)
    e_after = ece(confidences=calibrated, correct=correct, n_bins=10)
    assert e_after < e_before


def test_fit_temperature_empty_is_identity() -> None:
    model = fit_temperature(confidences=[], correct=[])
    assert model.temperature == pytest.approx(1.0)


def test_fit_temperature_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        fit_temperature(confidences=[0.5, 0.6], correct=[True])


# ---- PlattModel ----


def test_platt_model_monotone_in_confidence() -> None:
    m = PlattModel(a=1.5, b=-0.2)
    previous = m.apply(0.01)
    for c in [0.1, 0.3, 0.5, 0.7, 0.9, 0.99]:
        current = m.apply(c)
        assert current > previous
        previous = current


def test_platt_model_clamps_extremes() -> None:
    m = PlattModel(a=1.0, b=0.0)
    assert 0.0 <= m.apply(0.0) <= 1.0
    assert 0.0 <= m.apply(1.0) <= 1.0


def test_fit_platt_reduces_ece() -> None:
    confs, correct = _overconfident_data(n=400, seed=13)
    model = fit_platt(confidences=confs, correct=correct)
    calibrated = [model.apply(c) for c in confs]
    e_before = ece(confidences=confs, correct=correct, n_bins=10)
    e_after = ece(confidences=calibrated, correct=correct, n_bins=10)
    assert e_after < e_before


def test_fit_platt_empty_returns_identity_like() -> None:
    model = fit_platt(confidences=[], correct=[])
    assert isinstance(model, PlattModel)


# ---- HistogramModel + fit_histogram ----


def test_fit_histogram_produces_n_bins_accuracies() -> None:
    confs = [0.1, 0.3, 0.5, 0.7, 0.9]
    correct = [False, True, True, True, True]
    model = fit_histogram(confidences=confs, correct=correct, n_bins=5)
    assert isinstance(model, HistogramModel)
    assert len(model.accuracies) == 5


def test_fit_histogram_interpolates_empty_bins() -> None:
    confs = [0.05, 0.95]
    correct = [False, True]
    model = fit_histogram(confidences=confs, correct=correct, n_bins=5)
    # Middle bins should be interpolated (not None-valued in tuple).
    for v in model.accuracies:
        assert isinstance(v, float)


def test_histogram_model_apply_is_piecewise_constant() -> None:
    model = HistogramModel(
        edges=(0.0, 0.5, 1.0),
        accuracies=(0.2, 0.8),
    )
    assert model.apply(0.1) == pytest.approx(0.2)
    assert model.apply(0.4) == pytest.approx(0.2)
    assert model.apply(0.6) == pytest.approx(0.8)
    assert model.apply(1.0) == pytest.approx(0.8)


def test_histogram_model_rejects_non_finite() -> None:
    model = HistogramModel(edges=(0.0, 1.0), accuracies=(0.5,))
    with pytest.raises(ValueError, match="finite"):
        model.apply(float("nan"))


# ---- Ensemble averaging ----


def test_ensemble_mean_three_models() -> None:
    confs = [
        [0.1, 0.9],
        [0.3, 0.7],
        [0.5, 0.5],
    ]
    avg = ensemble_mean(confs)
    assert avg == pytest.approx([0.3, 0.7], abs=1e-9)


def test_ensemble_mean_single_model_is_passthrough() -> None:
    assert ensemble_mean([[0.1, 0.2, 0.3]]) == [0.1, 0.2, 0.3]


def test_ensemble_mean_rejects_empty() -> None:
    with pytest.raises(ValueError, match=">= 1 model"):
        ensemble_mean([])


def test_ensemble_mean_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="cases"):
        ensemble_mean([[0.1, 0.2], [0.3]])
