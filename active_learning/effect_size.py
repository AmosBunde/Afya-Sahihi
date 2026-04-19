"""Coverage-improvement-per-label estimation.

Paper P3 primary outcome: does the acquisition function's treatment
arm improve conformal coverage faster per-label than the control arm?
Measured weekly by computing the coverage delta (post-label coverage
minus pre-label coverage) for each labelled case and comparing the
distributions across arms.

For a weekly round of ~20 cases per facility, frequentist t-tests on
tiny samples are noise. Instead we compute a posterior over the
difference in coverage-per-label between arms, assuming Gaussian
observations with unknown variance and a weakly informative prior.
The output is the posterior mean + a 95% highest-density interval
(HDI). If the HDI excludes zero, the treatment is meaningfully
different.

Pure stdlib math — no scipy. The posterior for μ_T − μ_C under a
reference prior reduces to Welch's t distribution; we report the
posterior's mean and HDI rather than a p-value. Clinicians read
"probability of benefit" better than they read p-values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArmStats:
    n: int
    mean: float
    variance: float  # sample variance (n-1 denominator)


@dataclass(frozen=True, slots=True)
class EffectSize:
    delta_mean: float  # treatment − control
    hdi_95_low: float
    hdi_95_high: float
    p_benefit: float  # posterior P(treatment > control)
    n_treatment: int
    n_control: int


def _mean_var(xs: list[float]) -> ArmStats:
    n = len(xs)
    if n == 0:
        return ArmStats(n=0, mean=0.0, variance=0.0)
    mean = sum(xs) / n
    if n == 1:
        return ArmStats(n=1, mean=mean, variance=0.0)
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    return ArmStats(n=n, mean=mean, variance=var)


def _t_quantile(df: float, p: float) -> float:
    """Approximate inverse-CDF of Student's t. Good enough for HDI labels.

    Uses the Cornish-Fisher-ish normal expansion + 1/(4·df) correction.
    For df >= 30 this is accurate to 3 decimals; small df HDIs are
    wider than normal (conservative), which is the right direction
    of error for a safety-conscious report.
    """
    if p <= 0 or p >= 1:
        raise ValueError("p must be in (0, 1)")
    z = _inv_normal_cdf(p)
    if df <= 0:
        return z
    correction = z * (z * z + 1) / (4 * df)
    return z + correction


def _inv_normal_cdf(p: float) -> float:
    """Beasley-Springer-Moro approximation for Φ⁻¹(p).

    Accurate to ~1e-7 across (0, 1). Stdlib-only (no scipy).
    """
    if p <= 0 or p >= 1:
        raise ValueError("p must be in (0, 1)")
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
        ) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
    )


def _t_cdf(t: float, df: float) -> float:
    """Student's t CDF via the regularised incomplete beta identity.

    P(T <= t) = 1 - 0.5 * I(df/(df + t²); df/2, 1/2)   for t > 0
              = 0.5 * I(df/(df + t²); df/2, 1/2)       for t < 0
    """
    if df <= 0:
        raise ValueError("df must be > 0")
    x = df / (df + t * t)
    ibeta = _regularised_incomplete_beta(x, df / 2.0, 0.5)
    return 1.0 - 0.5 * ibeta if t >= 0 else 0.5 * ibeta


def _regularised_incomplete_beta(x: float, a: float, b: float) -> float:
    """I_x(a, b) via a Lentz-style continued fraction; ~1e-8 accuracy."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a
    # Symmetry: use the smaller-tail form for convergence.
    if x > (a + 1) / (a + b + 2):
        return 1.0 - _regularised_incomplete_beta(1 - x, b, a)
    # Lentz's method
    fpmin = 1e-300
    qab = a + b
    qap = a + 1
    qam = a - 1
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        del_ = d * c
        h *= del_
        if abs(del_ - 1.0) < 3e-7:
            break
    return front * h


def effect_size(
    *,
    treatment_deltas: list[float],
    control_deltas: list[float],
) -> EffectSize:
    """Posterior estimate of (treatment mean − control mean) per label.

    Uses Welch's approximation for degrees of freedom under a reference
    prior. Returns (delta, 95% HDI, P(benefit)).
    """
    if not treatment_deltas and not control_deltas:
        return EffectSize(0.0, 0.0, 0.0, 0.5, 0, 0)

    t = _mean_var(treatment_deltas)
    c = _mean_var(control_deltas)
    delta = t.mean - c.mean
    # Welch's approximation of the posterior variance.
    se2 = (t.variance / max(t.n, 1)) + (c.variance / max(c.n, 1))
    se = math.sqrt(se2) if se2 > 0 else 0.0

    if se == 0.0 or t.n + c.n < 3:
        # Not enough data for an HDI; return point estimate with
        # a wide placeholder interval so callers don't mistake low
        # sample size for strong evidence.
        return EffectSize(
            delta_mean=delta,
            hdi_95_low=float("-inf"),
            hdi_95_high=float("inf"),
            p_benefit=0.5,
            n_treatment=t.n,
            n_control=c.n,
        )

    # Welch-Satterthwaite df.
    num = se2**2
    denom = 0.0
    if t.n > 1:
        denom += (t.variance / t.n) ** 2 / (t.n - 1)
    if c.n > 1:
        denom += (c.variance / c.n) ** 2 / (c.n - 1)
    df = num / denom if denom > 0 else float(t.n + c.n - 2)

    t_quant = _t_quantile(df=df, p=0.975)
    hdi_low = delta - t_quant * se
    hdi_high = delta + t_quant * se

    # P(treatment > control) under the posterior = 1 - CDF_t(-delta/se; df)
    p_benefit = 1.0 - _t_cdf(-delta / se, df)

    return EffectSize(
        delta_mean=delta,
        hdi_95_low=hdi_low,
        hdi_95_high=hdi_high,
        p_benefit=p_benefit,
        n_treatment=t.n,
        n_control=c.n,
    )
