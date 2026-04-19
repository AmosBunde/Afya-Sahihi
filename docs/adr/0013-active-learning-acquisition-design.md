# ADR-0013: Active-learning acquisition-function scheduler design (Paper P3)

**Status:** Accepted
**Date:** 2026-04-19
**Deciders:** Ezra O'Marley

## Context

Paper P3 asks whether acquisition-function-guided labeling improves conformal coverage faster than random labeling, in a clinical RAG setting where labeling is scarce and expensive. The experiment runs as a weekly AL round at two AKU pilot sites over a 3-month window. Every week, the scheduler picks 20 cases per facility for Tier 3 clinician review; the grades flow back into the calibration set; coverage is re-measured and the effect size (treatment minus control mean coverage-per-label) is reported as a posterior interval.

The ethics of online human-subjects research require:
- **Pre-registration** on OSF before any labels are collected. The OSF URL gates startup in `active_learning/settings.py`.
- **Arm assignment opaque to the reviewer** so their grade is not biased by knowing which arm produced the case. Our assignment module decides arm from a SHA-256 hash of `(seed, week_iso, case_id)` before the case reaches the labeling queue; the reviewer UI never displays arm.
- **30% control arm** — uniform random selection. Large enough to estimate arm-difference with reasonable power (~20 per site per week × 12 weeks × 2 sites × 0.3 ≈ 144 control labels); small enough that the treatment arm still accumulates the paper's main sample.

## Decision

### Acquisition function suite

Five canonical functions, matching Settles (2012) categories:

1. `random` — uniform sampling. Used for both the control arm and as an ablation baseline.
2. `uncertainty_entropy` — Shannon entropy of token logprobs (nats). Classic uncertainty sampling.
3. `conformal_set_size` — prediction-set size. Model-specific signal; set size 5 means the calibrator has five plausible answers for this case.
4. `coverage_gap` — |observed miss − target|. Validation-set feedback; non-zero only for replayed Tier 2 cases where ground truth is known.
5. `clinical_harm_weighted` — entropy × stratum harm weight (dosing/contra/pediatric/pregnancy/diagnosis/triage/general). Paper P3's **primary** acquisition function.

Harm weights (`HARM_WEIGHTS` in `acquisition.py`) are fixed per the pre-registered tier table. Changing them in production is a protocol amendment that requires an OSF update, so they're constants in code, not env vars.

### Assignment

Deterministic SHA-256 hash of `(seed, week_iso, case_id)` → [0, 1) → arm by comparison against `control_ratio`. Properties:

- **Reproducibility.** The Paper P3 analysis replays the 12 weeks with the same inputs and lands on the same arms. Statisticians double-check the analysis by regenerating the table from `case_id` alone.
- **Opacity.** The reviewer UI shows only the case content. Deriving arm from `case_id` requires the scheduler's seed, which is operator-scoped.
- **Stratification across acquisition-function picks and random picks.** Control-arm cases are a uniform subsample of the weekly candidate pool; treatment-arm cases are the acquisition-function top-k. Both are then arm-hashed — so a treatment-function pick that hashes into the control bucket is recorded as control, and vice versa. This prevents the acquisition function from accidentally dominating the arm split.

`al_control_arm_ratio` is validated to `0 < ratio < 1` at startup; 0 or 1 defeats the causal comparison and is refused.

### Effect-size estimator

Bayesian posterior over `μ_treatment − μ_control` under a reference prior, using Welch's approximation for degrees of freedom. Reports delta, 95% HDI, and `P(treatment > control)`. Clinicians read "probability of benefit: 0.82" better than "p = 0.04"; the HDI communicates precision without the p-value fetish.

Weekly reporting: `effect_size.effect_size()` on per-case coverage deltas across each arm, emitted as Prometheus metrics for the conformal dashboard.

### Storage

- `al_labeled_pool` table: primary key `(case_id, week_iso)`, so re-running a week is idempotent. `arm` is a CHECK-constrained enum of {treatment, control}. `acquisition_function` records "random" for control-arm rows regardless of the week's configured treatment function — the table is self-describing for the paper's analysis.
- `al_candidate_pool_v` view: joins `queries_audit` (production cases) with conformal metadata. Tier 2 replay cases (with `truth_in_set` set) land via a separate path in #38.

### Pre-registration enforcement

`ActiveLearningSettings.al_preregistration_url` is a Pydantic `HttpUrl` with two custom validators:
1. Must be on `osf.io`.
2. Must not equal the env-template placeholder `https://osf.io/xxxxx`.

Startup fails if either check fails. An operator deploying without pre-registration hits the error before the scheduler runs its first round.

## Consequences

**Positive**
- Paper P3 analysis is reproducible from the `al_labeled_pool` table + the original seed; no non-deterministic state.
- The design refuses to operate without pre-registration — research ethics enforced by code.
- All acquisition functions are pure and unit-tested; swapping the primary function is a one-env-var change for a pre-registered secondary.
- Control arm is a real random sample, not a degenerate "non-picked" set. Needed for the Paper P3 causal inference.

**Negative**
- The effect-size module ships a stdlib-only Student's t CDF approximation rather than pulling in scipy. Accuracy is ~1e-7 for the regularised incomplete beta, enough for effect-size confidence intervals but not for publication-grade p-values. The paper's statistical analysis will be re-run in R for the final submission.
- The hash-based arm assignment is not adaptive (no re-balancing if one arm runs dry). For 12 weeks × 20 cases × 30% control = 72 expected controls; with variance, a run could land at 62 or 82. Pre-registered as a fixed-design experiment, so no re-balancing needed.

**Neutral**
- APScheduler in-process is fine for one weekly round per facility. If we scale to multiple sites with staggered rounds we may switch to a k3s CronJob fan-out, but for 2 sites × 1/week the in-process approach is simpler.

## Alternatives rejected

- **Thompson sampling / UCB multi-armed bandit over acquisition functions**: violates pre-registration (treatment is a single function, not a policy); defer to follow-up paper.
- **Random permutation test for effect size**: works but requires stored per-case data for every permutation; Welch t-posterior is closed-form and reports the same signal.
- **Reviewer-visible arm**: rejected on experimental-design grounds (blinding is a P3 invariant).

## References

- Issue #37 research(active-learning): acquisition-function scheduler and online deployment
- ADR-0006 three-tier evals
- Settles 2012 "Active Learning" survey
- PhD variables inventory §4
- `env/eval.env` §AL_
