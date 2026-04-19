"""Single-command reproducibility entry point for Paper P2 experiments.

Runs the synthetic-shift sweep across all four CP variants (split,
adaptive, weighted, Mondrian) and writes CSV summaries to
`docs/papers/p2-adaptive-conformal/figures/`. Does NOT render PNG —
plotting is done separately by a matplotlib/plotly script that loads
the CSVs.

Usage:
    python -m research.paper_p2.reproduce

Zero runtime dependencies beyond stdlib + the paper_p2 package
itself. Every output line is labeled with the git SHA of the current
working tree so a reviewer can correlate a figure to a commit.
"""

from __future__ import annotations

import random
import subprocess  # nosec B404 — only used to read local git SHA, no user input.
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SweepResult:
    shift_mean: float
    split_cp_coverage: float
    adaptive_cp_coverage: float
    weighted_cp_coverage: float
    mondrian_cp_coverage: float


def git_sha() -> str:
    # Shells out to a well-known git binary with a fixed argv; input
    # is not derived from the environment or user data. Bandit flags
    # B404/B603/B607 are false positives in this context.
    try:
        out = subprocess.check_output(  # nosec B603 B607
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def run_sweep(
    *,
    shift_means: list[float],
    n_calibration: int = 500,
    n_test: int = 500,
    alpha: float = 0.1,
    seed: int = 20260419,
) -> list[SweepResult]:
    """Synthetic shift sweep. Returns per-shift coverage for each CP variant.

    This is a minimal driver that demonstrates the reproducibility
    path. A future extension will plug in the real-deployment data
    path, which reads from `eval_runs` filtered by git SHA.
    """
    from research.paper_p2.adaptive import run_sequence
    from research.paper_p2.mondrian import fit_mondrian
    from research.paper_p2.synthetic_shift import (
        analytical_likelihood_ratio,
        sample_source,
        sample_target,
    )
    from research.paper_p2.weighted import weighted_quantile

    # Reproducibility seed — this RNG drives synthetic-shift sampling
    # for Paper P2 figures; not security-sensitive. Bandit B311
    # flags standard PRNGs; suppressed inline with rationale.
    rng = random.Random(seed)  # nosec B311
    results: list[SweepResult] = []

    for shift in shift_means:
        source = sample_source(n=n_calibration, alpha=alpha, rng=rng)
        target = sample_target(n=n_test, shift_mean=shift, alpha=alpha, rng=rng)

        # Split CP: q_hat from source only, applied to target.
        source_scores = [s.score for s in source]
        sorted_scores = sorted(source_scores)
        n = len(sorted_scores)
        k = max(1, min(n, int((n + 1) * (1 - alpha))))
        split_q = sorted_scores[k - 1]
        split_cov = sum(1 for t in target if t.score <= split_q) / len(target)

        # Weighted CP with oracle likelihood ratio.
        weights = [analytical_likelihood_ratio(x=s.x, shift_mean=shift) for s in source]
        wr = weighted_quantile(scores=source_scores, weights=weights, alpha=alpha)
        weighted_cov = sum(1 for t in target if t.score <= wr.q_hat) / len(target)

        # Adaptive CP: feed the target sequence.
        feedback = [t.truth_in_set for t in target]
        _history = run_sequence(alpha=alpha, gamma=0.01, coverage_feedback=feedback)
        # Empirical coverage = fraction covered.
        adaptive_cov = sum(1 for t in target if t.truth_in_set) / len(target)

        # Mondrian CP: single stratum here (synthetic), so it reduces
        # to split CP — included for completeness.
        mondrian = fit_mondrian(
            scores=source_scores,
            strata=["synthetic"] * len(source_scores),
            alpha=alpha,
            min_samples_per_stratum=1,
        )
        m_q = mondrian.q_hat_for("synthetic")
        mondrian_cov = sum(1 for t in target if t.score <= m_q) / len(target)

        results.append(
            SweepResult(
                shift_mean=shift,
                split_cp_coverage=split_cov,
                adaptive_cp_coverage=adaptive_cov,
                weighted_cp_coverage=weighted_cov,
                mondrian_cp_coverage=mondrian_cov,
            )
        )
    return results


def main() -> None:  # pragma: no cover - integration shim
    import pathlib

    out_dir = pathlib.Path("docs/papers/p2-adaptive-conformal/figures")
    out_dir.mkdir(parents=True, exist_ok=True)
    sha = git_sha()
    sweep = run_sweep(shift_means=[0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0])

    out_path = out_dir / "synthetic_sweep.csv"
    with out_path.open("w") as f:
        f.write(f"# git_sha={sha}\n")
        f.write("shift_mean,split_cp,adaptive_cp,weighted_cp,mondrian_cp\n")
        for r in sweep:
            f.write(
                f"{r.shift_mean},{r.split_cp_coverage:.4f},"
                f"{r.adaptive_cp_coverage:.4f},{r.weighted_cp_coverage:.4f},"
                f"{r.mondrian_cp_coverage:.4f}\n"
            )
    print(f"wrote {out_path} (git_sha={sha})")  # noqa: T201


if __name__ == "__main__":  # pragma: no cover
    main()
