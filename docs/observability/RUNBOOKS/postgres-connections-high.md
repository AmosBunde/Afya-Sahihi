# Runbook: PostgresConnectionsNearLimit

**Alert:** `PostgresConnectionsNearLimit` · **Severity:** warning · **Fires when:** active connections / max_connections > 0.85 for 15m.

## Impact

If connections hit max, new queries on the request path block until a slot frees. Clinical queries start to stack behind whoever is holding connections. Request-path timeouts kick in after 30s; fail-closed refusals follow.

## Triage

1. **Infrastructure** dashboard → the "Postgres active connections" panel, grouped by state. Idle-in-transaction is the usual culprit.
2. `kubectl exec -n afya-sahihi postgres-0 -- psql -c "SELECT state, count(*) FROM pg_stat_activity GROUP BY state;"`
3. Identify which service is holding the most: `SELECT application_name, count(*) FROM pg_stat_activity WHERE state != 'idle' GROUP BY application_name ORDER BY 2 DESC;`

## Containment

- Most common cause: a transaction left open by a crashed handler. `pg_terminate_backend(pid)` on the long-running idle-in-transaction rows.
- Check if the `pg_pool_max` setting on the culprit service is overscaled — cut it by half and redeploy.
- If connection pressure is load-driven: the fix is horizontal scale, not vertical. Add gateway replicas; the asyncpg pool per-replica is already conservative.

## Verify

- Connection % on the infra dashboard below 50% sustained.
- No new idle-in-transaction rows accumulating.
