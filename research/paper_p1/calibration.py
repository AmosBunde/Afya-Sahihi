"""Baseline calibration methods.

Three families:
  - temperature_scaling: single-parameter softmax temperature (Guo 2017).
  - platt_scaling: two-parameter logistic over confidences.
  - histogram_binning: piecewise-constant accuracy estimate per bin.

Each returns a calibrated probability for any new confidence via a
fitted model. Inputs are the same list[float] + list[bool] shape as
the metrics module. Fitting uses stdlib-only optimisation:
  - Newton's method for temperature (1-d convex on NLL).
  - Iteratively reweighted least squares for Platt (2-d logistic).
  - Empirical bin means for histogram (closed form).

Pure Python: we run on commodity CPUs without scipy/sklearn. The
scale is a few thousand points per Paper P1 split, so Python loops
are acceptable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TemperatureModel:
    temperature: float

    def apply(self, confidence: float) -> float:
        # softmax-over-{p, 1-p} with temperature T: re-scale logit.
        if confidence <= 0.0:
            return 0.0
        if confidence >= 1.0:
            return 1.0
        logit = math.log(confidence / (1.0 - confidence))
        scaled = logit / self.temperature
        return 1.0 / (1.0 + math.exp(-scaled))


@dataclass(frozen=True, slots=True)
class PlattModel:
    a: float
    b: float

    def apply(self, confidence: float) -> float:
        # P(y=1 | conf) = σ(a * logit(conf) + b)
        if confidence <= 0.0:
            return 1.0 / (1.0 + math.exp(-(self.b + self.a * -50.0)))
        if confidence >= 1.0:
            return 1.0 / (1.0 + math.exp(-(self.b + self.a * 50.0)))
        logit = math.log(confidence / (1.0 - confidence))
        return 1.0 / (1.0 + math.exp(-(self.a * logit + self.b)))


@dataclass(frozen=True, slots=True)
class HistogramModel:
    edges: tuple[float, ...]  # n_bins + 1
    accuracies: tuple[float, ...]  # n_bins, None-free

    def apply(self, confidence: float) -> float:
        if not math.isfinite(confidence):
            raise ValueError("confidence must be finite")
        conf = max(0.0, min(1.0, confidence))
        n_bins = len(self.accuracies)
        idx = int(conf * n_bins)
        if idx == n_bins:
            idx = n_bins - 1
        return self.accuracies[idx]


# ---- Temperature scaling ----


def fit_temperature(
    *,
    confidences: list[float],
    correct: list[bool],
    max_iter: int = 50,
    tol: float = 1e-6,
) -> TemperatureModel:
    """Minimise NLL with respect to a single temperature T.

    NLL(T) = -Σ [ y log σ(z/T) + (1-y) log (1 - σ(z/T)) ]
    where z = logit(confidence). d/dT and d²/dT² computed analytically,
    solved via damped Newton. Step size halves on non-decrease to
    keep the iteration well-behaved even on tiny fits.
    """
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct must have the same length")
    if not confidences:
        return TemperatureModel(temperature=1.0)

    # Clamp confidences away from {0, 1} so logit stays finite.
    eps = 1e-6
    z = [
        math.log(max(eps, min(1 - eps, c)) / (1 - max(eps, min(1 - eps, c))))
        for c in confidences
    ]
    y = [1.0 if r else 0.0 for r in correct]

    def nll(t: float) -> float:
        total = 0.0
        for zi, yi in zip(z, y, strict=True):
            si = 1.0 / (1.0 + math.exp(-zi / t))
            # clip to avoid log(0)
            si = max(eps, min(1 - eps, si))
            total -= yi * math.log(si) + (1 - yi) * math.log(1 - si)
        return total

    def grad_hess(t: float) -> tuple[float, float]:
        # d/dT of NLL, d²/dT² of NLL. σ'(x) = σ(x)(1-σ(x)).
        g = 0.0
        h = 0.0
        for zi, yi in zip(z, y, strict=True):
            u = zi / t
            si = 1.0 / (1.0 + math.exp(-u))
            si_c = 1.0 - si
            # dNLL/dT for a single sample: (si - yi) * (-zi / t^2)
            g += (si - yi) * (-zi / (t * t))
            # d²NLL/dT² = dsi/dT · (-zi/t²) + (si-yi) · 2zi/t³
            dsi_dT = si * si_c * (-zi / (t * t))
            h += dsi_dT * (-zi / (t * t)) + (si - yi) * (2 * zi / (t**3))
        return g, h

    t = 1.0
    prev = nll(t)
    for _ in range(max_iter):
        g, h = grad_hess(t)
        if abs(g) < tol:
            break
        if h <= 0:
            step = -g  # fall back to gradient descent
        else:
            step = -g / h
        # Damping: halve until NLL decreases.
        new_t = t + step
        damp = 1.0
        while new_t <= eps or nll(new_t) > prev:
            damp *= 0.5
            new_t = t + damp * step
            if damp < 1e-8:
                new_t = t
                break
        if abs(new_t - t) < tol:
            t = new_t
            break
        t = new_t
        prev = nll(t)
    return TemperatureModel(temperature=max(t, eps))


# ---- Platt scaling ----


def fit_platt(
    *,
    confidences: list[float],
    correct: list[bool],
    max_iter: int = 100,
    tol: float = 1e-6,
) -> PlattModel:
    """IRLS for the two-parameter logistic P(y=1|z) = σ(a·z + b).

    Input features z = logit(confidence). Uses regularised targets
    per Platt 1999: (N+ + 1)/(N+ + 2) for positives, 1/(N- + 2) for
    negatives, to avoid overconfidence at extremes.
    """
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct must have the same length")
    if not confidences:
        return PlattModel(a=1.0, b=0.0)

    eps = 1e-6
    n_pos = sum(1 for r in correct if r)
    n_neg = len(correct) - n_pos
    t_pos = (n_pos + 1) / (n_pos + 2) if n_pos > 0 else 0.5
    t_neg = 1.0 / (n_neg + 2) if n_neg > 0 else 0.5

    z = [
        math.log(max(eps, min(1 - eps, c)) / (1 - max(eps, min(1 - eps, c))))
        for c in confidences
    ]
    t = [t_pos if r else t_neg for r in correct]

    a = 1.0
    b = 0.0
    for _ in range(max_iter):
        # Predictions and gradient/Hessian over the regularised loss.
        p = [1.0 / (1.0 + math.exp(-(a * zi + b))) for zi in z]
        # Residuals
        r = [pi - ti for pi, ti in zip(p, t, strict=True)]
        # Weights
        w = [pi * (1 - pi) for pi in p]

        g_a = sum(ri * zi for ri, zi in zip(r, z, strict=True))
        g_b = sum(r)
        h_aa = sum(wi * zi * zi for wi, zi in zip(w, z, strict=True))
        h_ab = sum(wi * zi for wi, zi in zip(w, z, strict=True))
        h_bb = sum(w)

        det = h_aa * h_bb - h_ab * h_ab
        if abs(det) < 1e-12:
            break
        da = -(h_bb * g_a - h_ab * g_b) / det
        db = -(-h_ab * g_a + h_aa * g_b) / det
        a_new = a + da
        b_new = b + db
        if abs(da) < tol and abs(db) < tol:
            a, b = a_new, b_new
            break
        a, b = a_new, b_new
    return PlattModel(a=a, b=b)


# ---- Histogram binning ----


def fit_histogram(
    *,
    confidences: list[float],
    correct: list[bool],
    n_bins: int = 15,
) -> HistogramModel:
    """Empirical per-bin accuracy. Closed-form fit.

    Bins with no samples inherit the nearest-bin accuracy so the
    model can score any confidence on test; a uniform 0.5 fallback
    would bias toward chance on low-data bins.
    """
    if n_bins <= 0:
        raise ValueError("n_bins must be > 0")
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct must have the same length")
    edges = tuple(i / n_bins for i in range(n_bins + 1))
    buckets: list[list[bool]] = [[] for _ in range(n_bins)]
    for c, r in zip(confidences, correct, strict=True):
        if c < 0.0 or c > 1.0 or not math.isfinite(c):
            raise ValueError(f"confidence {c!r} out of [0, 1]")
        idx = int(c * n_bins)
        if idx == n_bins:
            idx = n_bins - 1
        buckets[idx].append(r)

    accs: list[float | None] = []
    for bucket in buckets:
        accs.append(sum(1 for r in bucket if r) / len(bucket) if bucket else None)

    # Fill empty bins by linear interpolation between neighbours;
    # leading/trailing empties inherit the first/last non-empty.
    filled = _interpolate_empty(accs)
    return HistogramModel(edges=edges, accuracies=tuple(filled))


def _interpolate_empty(vals: list[float | None]) -> list[float]:
    """Linear-interpolate None entries; fallback to 0.5 if all None."""
    n = len(vals)
    # Collect non-empty (index, value) pairs so subsequent lookups don't
    # need to re-narrow Optional[float] to float via assert (bandit B101).
    non_empty: list[tuple[int, float]] = [
        (i, v) for i, v in enumerate(vals) if v is not None
    ]
    if not non_empty:
        return [0.5] * n
    out: list[float] = []
    for i, v in enumerate(vals):
        if v is not None:
            out.append(v)
            continue
        # Nearest non-empty to the left and right.
        left_matches = [(j, vj) for j, vj in non_empty if j < i]
        right_matches = [(j, vj) for j, vj in non_empty if j > i]
        left = left_matches[-1] if left_matches else None
        right = right_matches[0] if right_matches else None
        if left is None and right is not None:
            out.append(right[1])
        elif right is None and left is not None:
            out.append(left[1])
        elif left is not None and right is not None:
            w = (i - left[0]) / (right[0] - left[0])
            out.append((1 - w) * left[1] + w * right[1])
        else:
            out.append(0.5)
    return out


# ---- Ensemble averaging ----


def ensemble_mean(confidences_per_model: list[list[float]]) -> list[float]:
    """Simple average of K model confidences, one list per model.

    All lists must be the same length (one row per case); raises
    ValueError otherwise. Accepts K ≥ 1; single-model "ensemble" is
    a no-op passthrough, useful for the baseline.
    """
    if not confidences_per_model:
        raise ValueError("need >= 1 model in ensemble")
    n_cases = len(confidences_per_model[0])
    for i, row in enumerate(confidences_per_model):
        if len(row) != n_cases:
            raise ValueError(f"model {i} has {len(row)} cases; expected {n_cases}")
    k = len(confidences_per_model)
    return [
        sum(confidences_per_model[m][i] for m in range(k)) / k for i in range(n_cases)
    ]
