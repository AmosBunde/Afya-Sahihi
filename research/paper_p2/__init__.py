"""Paper P2: adaptive conformal prediction for RAG under covariate shift.

Methodological contribution. Three CP variants beyond split conformal:

  - `adaptive`: online q_hat update (Gibbs & Candès 2021). Target
    coverage α is the *only* hyperparameter; the q_hat is adjusted
    each step proportional to the miscoverage indicator, giving
    distribution-free coverage on arbitrary sequences including
    adversarial shifts.
  - `weighted`: covariate-shift-weighted CP (Tibshirani et al. 2019).
    Calibration scores are re-weighted by the target/source
    likelihood ratio before taking the quantile.
  - `mondrian`: per-stratum CP (Vovk et al. 2003). The calibration
    set is partitioned by category (stratum), a separate q_hat
    fitted per stratum, then applied to test points in that stratum.

Synthetic shift experiments in `synthetic_shift` generate covariate
shifts of known magnitude to test each variant's coverage under known
ground truth.

The theorem (clinical-harm-weighted coverage) lives in the paper
draft under `docs/papers/p2-adaptive-conformal/theorem.md`. The proof
is out of scope for this PR; the STATEMENT is committed so the
experiments can target it.

Stdlib only — same reproducibility discipline as Paper P1 (#38).
"""
