# ADR-0006: Inspect AI with three-tier eval harness as the center of gravity

**Status:** Accepted
**Date:** 2026-04-16
**Deciders:** Ezra O'Marley

## Context

The single strongest lesson from Afya Gemma v1 was that evaluation was treated as a nice-to-have rather than as the product. Regressions reached production because the CI pipeline had no evaluator that could catch "the model now says the wrong drug dose for this well-known scenario."

Andrej Karpathy's repeated observation that LLM apps are 10 percent model and 90 percent eval harness applies with extra force in clinical settings. In the PhD research arc (three papers on calibration, conformal prediction, and active learning), the eval harness is not just a quality gate; it is the data collection infrastructure for every paper.

## Decision

Inspect AI (UK AI Safety Institute) is the canonical eval framework. We build a three-tier harness:

**Tier 1 — Unit evals (runs on every commit)**
- 500 curated query-response pairs with exact-match scoring on key facts (drug name, dose, route, frequency)
- Target runtime: under 2 minutes
- Gate: any regression blocks the PR

**Tier 2 — Regression evals (runs nightly and pre-deploy)**
- 2000 queries with adversarial rephrasing, English-Swahili code-switching, common misspellings
- Scored on coverage, calibration (ECE), prediction set efficiency, and topic coherence
- Gate: any metric dropping more than 2 percent blocks promotion to production

**Tier 3 — Clinician-in-the-loop evals (weekly)**
- A Streamlit labeling UI where clinical reviewers grade 20 responses per week on a 5-point rubric (accuracy, safety, guideline alignment, local appropriateness, clarity)
- Results feed back into the calibration set for the conformal layer
- Acquisition strategy for these 20 queries is itself a research variable (Paper 3)

All three tiers run as Inspect AI tasks against the same system under test (the orchestrator module from ADR-0003). Results land in Postgres in the `eval_runs` table. Grafana dashboards render tier-1 pass/fail, tier-2 metric trends, and tier-3 reviewer-by-reviewer grade distributions.

## Consequences

**Positive**

- Every PR is gated by real clinical correctness checks, not just unit test green lights.
- Research data collection and production quality gating share a single infrastructure.
- Inspect AI's scoring primitives (exact_match, model_graded_qa, etc.) cover our needs and avoid us rolling yet another eval runner.
- The harness is the system's memory. A regression in month 18 is caught against the same test cases as a regression in month 2.
- Papers 1, 2, and 3 all draw their experimental data from this harness.

**Negative**

- Tier 1 and tier 2 require an initial curation investment. We budget 3 weeks of part-time clinician time to build the initial 500-case tier 1 set.
- Tier 3 is clinician-time-expensive. We negotiate this as part of the Uzima-DS agreement.
- Inspect AI is still evolving; we pin a version and upgrade deliberately.

**Neutral**

- LangSmith and LangFuse are not used. They solve related problems but bind us to LangChain.
- We use Arize Phoenix for live LLM tracing (not eval), which complements Inspect AI rather than competing with it.

## Gate thresholds (initial, will tune)

| Tier | Metric | Threshold | Action on breach |
|------|--------|-----------|------------------|
| 1 | exact-match pass rate | >= 95% | Block PR |
| 2 | ECE | <= 0.08 | Block deploy |
| 2 | marginal coverage | 1 - alpha ± 0.03 | Block deploy |
| 2 | mean prediction set size | no increase > 15% | Warn |
| 3 | Clinician rubric average | >= 4.0 / 5.0 | Warn, trigger review |
| 3 | Inter-rater kappa | >= 0.7 | Retrain raters |

## Alternatives considered

- **LangSmith**: rejected, LangChain-bound.
- **LangFuse**: better than LangSmith but same category.
- **Promptfoo**: CLI-first, less flexible for research needs.
- **Rolling our own**: considered for 24 hours. Reversed after acknowledging that we would spend a year rebuilding Inspect AI badly.
- **DeepEval**: promising, smaller community. Revisit annually.

## Compliance and references

- Inspect AI version pinned in `eval/requirements.txt`
- Tier 1 dataset at `eval/datasets/tier1_golden.jsonl`, version-controlled
- Tier 2 dataset at `eval/datasets/tier2_regression.jsonl`, quarterly refresh
- Tier 3 UI at `labeling/streamlit_app.py`, protected by OIDC
- Related: ADR-0003 (system under test is the orchestrator)
