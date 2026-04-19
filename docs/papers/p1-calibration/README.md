# Paper P1: Calibration analysis of MedGemma under distribution shift

Working title. CHIL / FAccT / AAAI as target venues.

## Status

- [x] Calibration metrics (ECE, MCE, ACE, Brier, reliability-diagram area) implemented in `research/paper_p1/metrics.py`.
- [x] Baseline calibration methods (temperature scaling, Platt, histogram binning, ensemble) in `research/paper_p1/calibration.py`. Stdlib-only fitters so figures reproduce without scipy.
- [x] 40 unit tests covering perfect-calibration, overconfidence, empty inputs, clamp semantics, ECE ≤ MCE invariant.
- [ ] Data collection on 4,300 queries (source / target / adversarial splits). Source = MedGemma pre-training distribution proxy (US-centric clinical questions); target = AKU ward queries; adversarial = the Tier 2 regression set.
- [ ] Clinician-panel ground truth (Fleiss κ ≥ 0.7 required; labelled via the Tier 3 UI).
- [ ] Figures: reliability diagrams per split, per-method ECE table, per-stratum calibration gap.
- [ ] Paper draft.

## Research question

How does MedGemma-27B's calibration degrade under distribution shift from the pre-training distribution to AKU ward queries, and which of {temperature scaling, Platt, histogram binning, ensemble} recovers the most calibration per labelled example?

## Variables (PhD inventory §2)

**Per-case signals** (captured by the orchestrator + audited):
- `top_logprob` — highest token logprob over the first generated token.
- `avg_logprob` — mean logprob across the generated answer.
- `token_entropy` — Shannon entropy over the top-k logprobs (nats).
- `conformal_set_size` — size of the 90%-coverage prediction set.
- `prefilter_score` — topic-coherence probability from the prefilter service.
- `retrieval_top1` — top-1 similarity from hybrid retrieval.

Paper P1 treats `confidence = exp(avg_logprob)` as the single probability predicted by the model, against the clinician-panel ground-truth label.

## Splits (4,300 queries total)

| Split       | N    | Source                                                   |
| ----------- | ---- | -------------------------------------------------------- |
| source      | 1500 | MedQA + MedMCQA + PubMedQA subset (US pre-training proxy) |
| target      | 2000 | AKU ward queries (Tier 1 + Tier 3 accumulated)            |
| adversarial | 800  | Tier 2 regression set (code-switched + rephrased)         |

Stratification: every split oversamples the five safety-critical categories (dosing, contraindication, pediatric, pregnancy, triage) so per-stratum ECE is estimable at < 5% noise.

## Metrics

- **ECE** — equal-width bins, 15 bins (Guo 2017 convention). Primary.
- **MCE** — worst-bin gap; useful for regulatory framing.
- **ACE** — equal-mass bins; robust to confidence concentration near 1.
- **Brier** — proper scoring rule; decomposes into calibration + refinement + uncertainty (Murphy 1973).
- **Reliability-diagram area** — integrated deviation from the identity line via trapezoidal rule over occupied bin midpoints.

All metric values go into `eval_runs.aggregate_scores` JSONB for reproducibility.

## Baselines

- **Identity** (no calibration) — the uncalibrated model.
- **Temperature scaling** — single-parameter softmax temperature, fit by minimising NLL on a held-out calibration split via Newton's method.
- **Platt scaling** — two-parameter logistic over logit(confidence), fit by IRLS with Platt's regularised targets.
- **Histogram binning** — per-bin empirical accuracy; piecewise-constant calibrated probability.
- **Ensemble averaging** — simple mean over K = {2, 3} re-runs of the same query with different `pipeline_generation_seed`.

Each baseline is fit on the target split's training half, evaluated on the held-out half.

## Reproducibility

`scripts/paper_p1/reproduce_figures.sh` (forthcoming) reads from `eval_runs` by git SHA + corpus version, runs the metrics + baselines, emits PNG + CSV into `docs/papers/p1-calibration/figures/`. Every figure carries the git SHA in a footer so a reviewer can regenerate from the cited commit.

## Open questions

- Is avg_logprob a good confidence proxy, or should Paper P1 use `token_entropy`-derived confidence instead? Both are computed; decision defers to early experiments.
- Per-stratum calibration may diverge — do we report one global ECE + five stratum ECEs, or one calibration curve per stratum?
- MedGemma's classifier head (the 4B prefilter) has its own calibration story; in-scope for P1 or deferred to a follow-up?

## References

- Guo, Pleiss, Sun, Weinberger. *On Calibration of Modern Neural Networks.* ICML 2017.
- Nixon, Dusenberry, Zhang, Jerfel, Tran. *Measuring Calibration in Deep Learning.* CVPR Workshop 2019.
- Platt. *Probabilistic Outputs for Support Vector Machines and Comparisons to Regularized Likelihood Methods.* 1999.
- Murphy. *A New Vector Partition of the Probability Score.* J. Appl. Meteor. 1973.
- Zadrozny, Elkan. *Transforming Classifier Scores into Accurate Multiclass Probability Estimates.* KDD 2002.
