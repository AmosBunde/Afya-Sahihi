# Runbook: LatencyP99High

**Alert:** `LatencyP99High` · **Severity:** page · **Fires when:** gateway P99 > 6s for 10m.

## Clinical impact

6s is the auto-rollback threshold; clinicians will see queries stall past the SSE keepalive. Usability degrades sharply past 4s so the alert fires before the rollback.

## Triage

1. **RED** dashboard → confirm which stage is slow. Tempo trace view for a slow request exposes per-stage latency.
2. Most common cause is vLLM generation latency — check the **LLM** dashboard's "tokens per second" panel.
3. Second most common: retrieval hybrid query on Postgres — check the **Infrastructure** dashboard for Postgres active connections + CPU.

## Containment

- Slow vLLM: check **GPU** dashboard for temperature (thermal throttle) and memory (queue saturation).
- Slow Postgres: `kubectl exec -n afya-sahihi postgres-0 -- psql -c "SELECT pid, now() - query_start, query FROM pg_stat_activity WHERE state='active' ORDER BY 2 DESC LIMIT 5;"` to find the longest-running query.
- If the systemd watcher has been slow to respond to a known-good version, trigger a rollback manually via `systemctl restart afya-sahihi-watcher` on the infra node.

## Verify

- P99 on the RED dashboard below 4s sustained for 10 minutes.
- Alert auto-resolves.
