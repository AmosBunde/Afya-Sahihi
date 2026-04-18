# Runbook: conformal coverage drift

**When to use**: paged by Alertmanager for `ConformalCoverageBelowTarget`,
`ConformalCoverageAboveTarget`, `ConformalDriftDetected`, or
`ConformalSetSizeExploded`. Also appropriate when the Grafana
"Conformal coverage" dashboard shows a sustained deviation from the
target line.

**Blast radius**: a real coverage gap means every clinical query on
the affected stratum is getting a prediction set whose safety
guarantee has been violated. Treat as patient-safety.

**Expected duration**: 10–60 minutes to triage and mitigate; longer
if a calibration-set rebuild is required.

**Prerequisites**: access to Grafana + the conformal service pod logs.

## 1. Confirm the alert is real

```bash
# Grafana: "Afya Sahihi — Conformal" dashboard
open https://afya-sahihi.aku.edu/grafana/d/conformal

# Check the last 24h of coverage per stratum; look for:
#   - sudden step change → likely a deploy; see §2
#   - gradual drift → population shift; see §3
#   - single-stratum anomaly → one language/facility; see §4
```

If the dashboard shows a transient blip that has already recovered
AND `increase(afya_sahihi_conformal_drift_detected_total[1h]) == 0`,
acknowledge and close.

## 2. Coverage deviation from a recent deploy

Most likely cause if the timing aligns with a merge to main.

```bash
# What merged in the last hour?
gh api repos/AmosBunde/Afya-Sahihi/commits?since=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ) \
    --jq '.[] | "\(.sha[:7]) \(.commit.message | split("\n")[0])"'
```

If a retrieval, generation, or conformal-service change landed: roll
back via `kubectl rollout undo deployment/afya-sahihi-gateway -n afya-sahihi`
and verify coverage recovers within 20 minutes. Open an incident PR.

## 3. Gradual drift (MMD alert)

Score distribution has shifted. This is the exchangeability assumption
being broken — the calibration set no longer represents the current
population.

### 3a. Trigger a calibration refresh

```bash
# Issue #37's active-learning scheduler runs a calibration refresh
# on demand via this endpoint (when it lands).
curl -X POST https://afya-sahihi.aku.edu/admin/calibration/refresh \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d '{"stratum": "en:dosing"}'
```

If the endpoint isn't live yet, refresh manually:

```bash
# Connect to the primary Postgres and expand the calibration set for
# the affected stratum from the last 7d of labeled queries.
psql -h afya-sahihi-data-01.internal -U hakika_admin -d afya-sahihi <<SQL
INSERT INTO calibration_set (query_audit_id, nonconformity_score, score_type, stratum, ground_truth_label)
SELECT qa.id, g.score_correctness / 5.0, 'nll', 'en:dosing', g.reviewer_notes
FROM queries_audit qa
JOIN grades g ON g.query_audit_id = qa.id
WHERE qa.created_at > now() - interval '7 days'
  AND qa.query_language = 'en'
  AND qa.classified_intent = 'dosing'
LIMIT 500;
SQL
```

Wait 10 minutes for the quantile cache to refresh (nightly cron is
`QUANTILE_REFRESH_CRON="0 2 * * *"`; force-refresh by restarting the
conformal pod: `kubectl rollout restart deployment/conformal -n afya-sahihi`).

### 3b. If refresh doesn't help

The drift is real and the new distribution isn't represented by
recent labels either. Escalate to the clinical evaluation team to
investigate the underlying change (new corpus version? facility
expansion? language usage shift?). Do NOT silence the alert.

## 4. Single-stratum coverage gap

Usually caused by an undersized calibration stratum.

```bash
# How many calibration samples per stratum?
psql -h afya-sahihi-data-01.internal -U hakika_admin -d afya-sahihi -c "
SELECT stratum, count(*) FROM calibration_set
WHERE score_type = 'clinical_harm_weighted'
GROUP BY stratum ORDER BY count(*) ASC;
"
```

Any stratum with fewer than `CALIBRATION_SET_MIN_SIZE_PER_STRATUM`
(100 by default) will have its queries refused by the service —
check the gateway logs for `calibration_undersized` refusals. Populate
with §3a's manual insert.

## 5. Set-size explosion

Prediction sets are too large to be useful. The acceptance target is
3–5 candidates; above 50 is a degenerate state.

```bash
# Likely causes:
# - q̂ has gone to +inf (stale calibration)
# - scorer is returning 0 for all candidates (check score range in Grafana)
# - candidates list is growing unboundedly (retrieval regression)

# Inspect a recent response via audit log:
psql -h afya-sahihi-data-01.internal -U hakika_admin -d afya-sahihi -c "
SELECT id, query_id, corpus_version, conformal_set
FROM queries_audit
WHERE created_at > now() - interval '10 minutes'
  AND jsonb_array_length(conformal_set) > 50
LIMIT 5;
"
```

Open an incident. Rollback if a recent deploy is implicated.

## Verify checklist

- [ ] Coverage recovered to within 2pp of target on the affected stratum
- [ ] `increase(afya_sahihi_conformal_drift_detected_total[10m]) == 0`
- [ ] Mean set size back in the 3–5 range
- [ ] Incident ticket opened (for any rollback or calibration refresh)
- [ ] Grafana dashboard annotated with the intervention timestamp
