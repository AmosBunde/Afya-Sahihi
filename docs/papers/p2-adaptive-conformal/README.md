# Paper P2: Adaptive conformal prediction for RAG under covariate shift

Working title. NeurIPS / ICML / AISTATS as target venues (methodological track).

## Status

- [x] Adaptive CP (Gibbs & Candès 2021) scalar update — `research/paper_p2/adaptive.py`.
- [x] Weighted CP (Tibshirani et al. 2019) + likelihood-ratio estimator — `research/paper_p2/weighted.py`.
- [x] Mondrian CP (Vovk et al. 2003) per-stratum q_hat — `research/paper_p2/mondrian.py`.
- [x] Synthetic shift generator for sweep experiments — `research/paper_p2/synthetic_shift.py`.
- [x] 37 unit tests covering update rules, quantile under shift, per-stratum coverage.
- [x] Theorem statement (clinical-harm-weighted coverage) — `theorem.md`.
- [ ] Theorem proof.
- [ ] Theorem proof reviewed by one external researcher.
- [ ] Real-deployment experiments on AKU data.
- [ ] Open-source toolkit released (this repo is the toolkit).
- [ ] Paper submission.

## Contributions

1. **Clinical-harm-weighted split CP.** A variant of weighted CP where calibration scores are re-weighted by a harm-severity function of the case category. Theorem (below) establishes marginal coverage AND stratum-wise coverage under the weighted setting.
2. **Empirical comparison under covariate shift.** Adaptive, weighted, and Mondrian CP are benchmarked on synthetic shift sweeps (known ground truth) and on the Afya Sahihi deployment data (real clinical shift).
3. **Open-source toolkit.** Stdlib-only Python that runs without scipy/sklearn on a fresh VM — designed for clinical researchers who cannot install arbitrary CUDA stacks.

## Method overview

The split CP calibration procedure assumes exchangeability of calibration and test data. In clinical RAG the target distribution (AKU ward queries) differs systematically from the pre-training proxy, so the exchangeability assumption fails and the coverage guarantee is lost.

Three remedies:

- **Adaptive CP**: update q_hat online from observed miscoverage. Distribution-free coverage on arbitrary sequences. Needs a feedback channel (human grade of whether truth fell in the set).
- **Weighted CP**: re-weight the calibration scores by the target/source likelihood ratio. Needs a ratio estimator; coverage holds under smooth shift.
- **Mondrian CP**: stratify calibration by category; per-stratum q_hat. Coverage holds within each stratum if exchangeability holds within the stratum (a strictly weaker assumption than global exchangeability).

Each is implemented as a pure Python module with a unit test suite.

## Clinical-harm-weighted coverage theorem

See `theorem.md` for the statement. The proof combines a weighted quantile argument (Tibshirani 2019 §4) with a stratum-decomposition step (Vovk 2003 §3) applied to the harm-weighted distribution. Proof is work in progress.

## Experiments

### Synthetic shift sweep

`synthetic_shift.py` generates source and target samples from mean-shifted Gaussians with a known nonconformity score function. We sweep `shift_mean ∈ [0, 2]` and plot:

- Split CP coverage (baseline) — drops below 0.90 as shift grows.
- Adaptive CP coverage — tracks 0.90 after a warm-up of ~200 steps.
- Weighted CP coverage — holds at 0.90 when the likelihood ratio is known (oracle).
- Mondrian CP coverage — holds within each stratum when stratification aligns with the shift.

### Real deployment experiments

Deployment data from the Afya Sahihi production cluster (`queries_audit` + `eval_runs`). Split by time: train on weeks 1-8, test on weeks 9-12. Compare coverage and prediction-set size across the four variants.

## Reproducibility

The toolkit is designed to reproduce every figure from a single command:

```bash
python -m research.paper_p2.reproduce
```

Outputs land in `docs/papers/p2-adaptive-conformal/figures/`. Every figure's footer carries the git SHA. Since the code has zero runtime dependencies, the reproduction works on any Python 3.12 install — no scipy, sklearn, pytorch, matplotlib (figures are rendered separately; see `reproduce.py` docs).

## References

- Vovk, Gammerman, Shafer. *Algorithmic Learning in a Random World*. 2005.
- Vovk, Nouretdinov, Manokhin, Gammerman. *Conformal Predictive Distributions*. 2003 (Mondrian CP).
- Tibshirani, Foygel Barber, Candès, Ramdas. *Conformal Prediction Under Covariate Shift*. NeurIPS 2019.
- Gibbs, Candès. *Adaptive Conformal Inference Under Distribution Shift*. NeurIPS 2021.
- Sugiyama, Suzuki, Kanamori. *Density Ratio Estimation in Machine Learning*. Cambridge 2012.
- Angelopoulos, Bates. *A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification*. 2021.
