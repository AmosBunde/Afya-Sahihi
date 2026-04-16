# Runbook: First-time cluster bootstrap

**When to use**: bringing up a fresh Afya Sahihi environment from bare hardware
to the first green canary. Expected duration: one working day, mostly waiting
for image pulls and MinIO sync.

**Blast radius**: creates new infrastructure; does not affect any existing
environment. Safe to run in parallel with production.

**Prerequisites**:
- SSH access to the target hosts with `sudo` rights.
- Sealed-Secrets keys available in the operator bastion (do not commit).
- Harbor registry credentials loaded into the operator's keyring.
- The target hosts have been provisioned per `deploy/systemd/bootstrap/README`
  and pass `deploy/systemd/bootstrap/preflight.sh`.

## 1. Verify prerequisites

```bash
deploy/systemd/bootstrap/preflight.sh
```

The script must exit `0`. Do not proceed on any failure; each check guards a
downstream assumption (kernel version, NVIDIA driver, storage layout).

## 2. Bring up k3s

Follow [ADR-0005](../adr/0005-k3s-over-full-kubernetes.md). The systemd units
in `deploy/systemd/` install and start the k3s server on the control-plane host
and join every worker.

```bash
sudo systemctl enable --now k3s-server
# On each worker:
sudo systemctl enable --now k3s-agent
```

Verify with `kubectl get nodes`. All nodes should report `Ready` within 5 minutes.

## 3. Seal and apply secrets

Secrets are deployed via `SealedSecret` objects, never raw `Secret`s. See
`deploy/k3s/40-sealed-secrets/README.md` for the exact `kubeseal` invocation
per secret. Never paste an unencrypted secret into a commit message, issue, or
chat.

## 4. Apply the manifests

```bash
kubectl apply -k deploy/k3s/
```

The Kustomize overlay applies namespaces, CRDs, services, and deployments in
dependency order. Expected completion: ~15 minutes for image pulls.

## 5. Seed the database

The ingestion pipeline runs as a one-shot `Job`. Trigger with:

```bash
kubectl -n afya-sahihi apply -f deploy/k3s/50-jobs/ingestion-seed.yaml
kubectl -n afya-sahihi logs -f job/ingestion-seed
```

Expected duration: ~2 hours for the initial corpus. The job is idempotent; if
it fails, delete and re-apply.

## 6. Run the first canary

```bash
curl -H "Authorization: Bearer $CANARY_TOKEN" \
     https://afya-sahihi.aku.edu/healthz
```

Verify the Grafana "Deployments" dashboard shows green for 30 minutes before
declaring bootstrap complete.

## Rollback

Bootstrap is non-destructive to existing environments. To abandon a failed
bootstrap:

```bash
kubectl delete ns afya-sahihi
sudo systemctl disable --now k3s-server k3s-agent
```

Storage volumes are reclaimed manually; confirm the PVs are released before
reusing the hardware.

## Verify checklist

- [ ] `kubectl get pods -n afya-sahihi` reports all pods `Running` or `Completed`
- [ ] `curl /healthz` returns `200` from inside and outside the cluster
- [ ] Grafana "RED metrics" dashboard shows non-zero request rate
- [ ] Audit log `queries_audit` has at least one row from the canary query
- [ ] Prometheus `up{job="gateway"} == 1` for every replica
