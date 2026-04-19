# Runbook: ConformalCoverageBelowTarget

**Alert:** `ConformalCoverageBelowTarget` · **Severity:** warning · **Fires when:** 1h-avg coverage < 0.87 (target 0.90).

## Clinical impact

Prediction sets are under-covering — the true answer is falling outside the set more often than the conformal guarantee promises. Clinicians who trust the set as an upper bound on clinical options may miss a correct one. This is a calibration bug, not a safety-refusal bug; fail-closed semantics are unaffected.

## Triage

1. **Conformal** dashboard → which stratum is the coverage drop concentrated in (dosing, contraindication, pediatric, …).
2. Check the **Drift MMD²** panel on the same dashboard. A sharp step-up in MMD² correlates with a data distribution shift that broke the calibration assumption.
3. Check eval-run history: did Tier 2 pass on the most recent deploy? If Tier 2 passed but prod coverage dropped, the prod distribution has diverged from the Tier 2 golden set.

## Containment

This is not a page-the-oncall situation — coverage drift is a research-team problem, not an ops problem:

- Open a Linear issue in `CONFORMAL` project with the affected stratum, the drift MMD² timeseries, and the last known-good coverage window.
- Kick off a calibration-set refresh: run `uv run -m conformal.recompute_q_hat --corpus-version=<current>` from the backend repo on an operator workstation.
- Monitor coverage after q_hat push. Alert auto-resolves once 1h-avg returns > 0.89.

## Paging

Do not page on this alert. If coverage drops below 0.85 for 6h, escalate to the senior conformal researcher via Slack DM.
