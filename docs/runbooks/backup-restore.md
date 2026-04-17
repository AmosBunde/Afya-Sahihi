# Runbook: pgBackRest backup and restore rehearsal

**When to use**: weekly to verify the backup pipeline is healthy, and
on-demand when a restore is needed (data corruption, accidental
truncation, or disaster recovery). Run the restore rehearsal on
`afya-sahihi-data-02` (standby) — never on the primary unless the
primary is already lost.

**Blast radius**: a RESTORE overwrites the entire Postgres cluster on
the target host. Running it on the primary while the primary is live
destroys production data. The standby is disposable by design; the
rehearsal exists to prove the backup is restorable before you need it
under pressure.

**Expected duration**: full restore of a 50 GB database takes ~20 min
on the internal 10 Gbps link to MinIO. PITR replay adds 1–5 min
depending on WAL volume since the last full backup.

**Prerequisites**:
- SSH access to `afya-sahihi-data-02` with `sudo` rights.
- pgBackRest installed and configured (`/etc/pgbackrest/pgbackrest.conf`
  matches `deploy/systemd/pgbackrest.conf`).
- MinIO credentials loaded into the systemd credential store (same
  `LoadCredential` paths as the backup timers).
- Postgres 16 installed but **stopped** on the standby.

## 1. Verify the latest backup exists

```bash
sudo -u postgres pgbackrest --stanza=afya-sahihi info
```

Expected output includes at least one `full backup` with status `ok` and
a timestamp within the last 7 days. If no full backup exists, run one on
the primary first:

```bash
# ON THE PRIMARY (afya-sahihi-data-01) ONLY
sudo systemctl start afya-sahihi-pgbackrest-full.service
sudo journalctl -u afya-sahihi-pgbackrest-full.service -f
```

## 2. Stop Postgres on the standby

```bash
sudo systemctl stop postgresql
```

Confirm with `pg_isready`; it should report "no response."

## 3. Restore to the standby

### Option A: latest backup (most common)

```bash
sudo -u postgres pgbackrest --stanza=afya-sahihi \
    --delta \
    restore
```

`--delta` only transfers changed files, which is faster than a full
re-copy when the standby was recently synced.

### Option B: point-in-time recovery

```bash
sudo -u postgres pgbackrest --stanza=afya-sahihi \
    --delta \
    --type=time \
    --target="2026-04-17 06:00:00+03" \
    restore
```

Replace the timestamp with the desired recovery target. The target must
fall between the oldest retained WAL segment and the latest archived
segment.

## 4. Start Postgres and verify

```bash
sudo systemctl start postgresql
sudo -u postgres psql -d afya-sahihi -c "SELECT count(*) FROM queries_audit;"
```

Compare the count with the primary:

```bash
# ON THE PRIMARY
sudo -u postgres psql -d afya-sahihi -c "SELECT count(*) FROM queries_audit;"
```

The standby count should match (for latest-backup restore) or be
slightly less (for PITR to a past timestamp).

## 5. Verify the audit hash chain on the restored data

```bash
AFYA_SAHIHI_DATABASE_URL=postgresql://hakika_admin@afya-sahihi-data-02:5432/afya-sahihi \
    python scripts/audit/verify_chain.py
```

Expected: "chain intact: N rows verified." A broken chain after restore
indicates a backup corruption or a PITR target that landed mid-write;
investigate the WAL archive before declaring the restore trustworthy.

## 6. Tear down the standby restore

After confirming the backup is good, stop Postgres on the standby so it
does not accidentally serve traffic:

```bash
sudo systemctl stop postgresql
```

The standby's data directory can be left as-is for the next rehearsal
(the `--delta` flag makes it incremental) or wiped if disk is needed.

## Scheduled rehearsal cadence

The backup-restore rehearsal should run **monthly**, ideally the first
Monday after the full backup window. Add to the team calendar:

```
First Monday of each month, 10:00 Africa/Nairobi
Operator: run backup-restore rehearsal on afya-sahihi-data-02
Duration: 30 min
Escalation: if restore fails, page secondary and open incident
```

## Verify checklist

- [ ] `pgbackrest info` shows a full backup within the last 7 days
- [ ] Restore completes without error on the standby
- [ ] `SELECT count(*) FROM queries_audit` matches the primary (or is
      consistent with the PITR target)
- [ ] `scripts/audit/verify_chain.py` reports "chain intact"
- [ ] Postgres is **stopped** on the standby after the rehearsal
- [ ] Rehearsal outcome logged in the team's ops channel
