# P1 outline

Working title: *When the Ward Moves Under the Model: A Calibration Audit of MedGemma Across Distribution Shifts in Clinical RAG*.

## §1 Introduction

- Clinical RAG systems face a specific kind of distribution shift: pre-training data is US-centric, deployment data is ward-local (AKU Nairobi for us). Even when retrieval brings in the right context, the model's confidence may not be calibrated to the ward distribution.
- We audit MedGemma-27B's calibration across three splits (source, target, adversarial), report ECE/MCE/ACE/Brier/reliability-area, and measure how much calibration each of four standard post-hoc methods recovers.
- Contribution: the first empirical calibration study on MedGemma for low-resource clinical RAG, with a reproducible pipeline from query → audit → metric.

## §2 Background

- Calibration in deep learning (Guo 2017) and why ECE is the default.
- Distribution shift in clinical NLP — prior work, what they measured, what they missed.
- Conformal prediction as a *different* framing of the same uncertainty: coverage guarantees at the set level, not calibration at the point level. Paper P2 handles conformal.

## §3 Method

- **Data pipeline.** Tier 1/2/3 from the Afya Sahihi eval harness (ADR-0006). Confidence is `exp(avg_logprob)` for the canonical answer.
- **Splits.** 1500 source, 2000 target, 800 adversarial. Stratified by clinical category.
- **Ground truth.** Clinician panel grades via the Tier 3 UI; Fleiss κ computed daily (issue #29); panel admits cases for Paper P1 only when κ ≥ 0.7 on that week's dual-rated subset.
- **Metrics.** ECE (15 equal-width bins), MCE, ACE, Brier, reliability-diagram area.
- **Baselines.** Identity, temperature scaling (Newton fit on NLL), Platt (IRLS with regularised targets), histogram binning (empirical + interpolation), ensemble averaging over K ∈ {2, 3}.
- **Implementation.** `research/paper_p1/{metrics,calibration}.py` — stdlib only, 40 unit tests.

## §4 Results

Tables + figures placeholder:
- Fig 1: reliability diagrams, one per split × method.
- Tab 1: ECE/MCE/ACE/Brier/area per split × method.
- Fig 2: per-stratum ECE bars (dosing, contraindication, pediatric, pregnancy, triage).
- Fig 3: calibration under sample-size ablation (how many labels to pick off 50% of the ECE drop?).

## §5 Discussion

- Which method recovers the most calibration *per labelled example*? Tie-in to Paper P3's active-learning loop.
- When does calibration fail? Hypothesis: adversarial split reveals MedGemma's confidence at the category boundary.
- Clinical implications: calibrated refusal thresholds save clinician attention; miscalibrated ones erode trust.

## §6 Limitations

- Single institution (AKU). External generalisability unknown.
- Ground truth is clinician-panel, not outcome-based.
- MedGemma versioning: we pin one model revision for the whole study; results do not transfer forward without re-audit.

## §7 Reproducibility

Code: `research/paper_p1/`. Scripts: `scripts/paper_p1/reproduce_figures.sh` (forthcoming). Every figure is regenerable from the committed dataset + the cited git SHA.
