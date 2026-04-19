# Runbook: HighErrorRate

**Alert:** `HighErrorRate` · **Severity:** page · **Fires when:** 5xx rate > 1% for 10m on any service.

## Clinical impact

Clinicians are getting refused or broken responses on a fraction of queries. Fail-closed semantics (SKILL.md §0.1) mean the system is returning a refusal, not incorrect advice — but repeated refusals damage trust in the tool. Time-sensitive queries (dosing, contraindication) are the worst case.

## Triage (first 5 minutes)

1. Open the **RED** dashboard; pick the firing service. Confirm whether errors cluster on one endpoint or spread across all.
2. Open **Tempo**. Filter spans for `service.name = <service>` and `status = error`. Pick one; look at which child span failed.
3. Common root causes:
   - **Downstream timeout** (vLLM, retrieval, conformal) — check each downstream's RED panel.
   - **Database pool exhaustion** — infra dashboard's "Postgres active connections" panel.
   - **OIDC / JWKS cache expired** — `gateway` logs for "jwt validation failed".

## Containment

- If the issue is in a single version: look at recent deploys via `kubectl -n afya-sahihi rollout history deployment/<service>` and roll back with `kubectl rollout undo deployment/<service>`.
- If the issue is load-driven: scale the service replicas up; verify Redis rate-limiter pressure is not driving refusals.
- If the issue is clinical (wrong fail-closed reason code): escalate to the on-call PhD researcher.

## Verify resolution

- Wait for the alert to clear (Alertmanager sends a resolve notification).
- Confirm the P99 latency panel is back to baseline.
- Add a post-incident note in `docs/incidents/YYYY-MM-DD-<slug>.md` with the root cause and the fix.
