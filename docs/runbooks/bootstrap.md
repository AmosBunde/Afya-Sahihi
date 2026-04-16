# Runbook: First-time cluster bootstrap

**When to use**: bringing up a fresh Afya Sahihi environment from bare hardware
to the first green canary. Expected duration: one working day, mostly waiting
for image pulls and MinIO sync.

**Blast radius**: creates new infrastructure; does not affect any existing
environment. Safe to run in parallel with production.

**Status**: this runbook tracks the bootstrap sequence planned by the M0–M8
milestones. Steps are marked "**Today**" if the referenced scripts/manifests
exist in this commit, or "**Scheduled**" with the issue number that will land
the missing artefacts. Do not rely on a "Scheduled" step until the linked issue
is closed; the runbook will be updated in the same PR that lands each step.

**Prerequisites**:
- SSH access to the target hosts with `sudo` rights.
- Sealed-Secrets keys available in the operator bastion (do not commit).
- Harbor registry credentials loaded into the operator's keyring.
- Target hosts provisioned per `deploy/systemd/` (see issue #33 for the
  preflight automation; until then, the checks in §1 are performed manually).

## 1. Verify prerequisites (**Scheduled**, issue #33)

The `deploy/systemd/bootstrap/preflight.sh` script is produced by issue #33
(k3s cluster bootstrap). Until it exists, run the manual equivalent:

```bash
# kernel >= 6.1 for cgroup v2 support required by k3s + containerd
uname -r

# NVIDIA driver >= 550 for H100 (vLLM)
nvidia-smi --query-gpu=driver_version --format=csv,noheader

# At least 2 TiB free on the storage pool dedicated to Postgres + MinIO
df -h /var/lib/rancher /var/lib/afya-sahihi
```

Stop on any failure; each check guards a downstream assumption (cgroup v2,
GPU driver, storage layout).

## 2. Bring up k3s (**Scheduled**, issue #33)

Follow [ADR-0005](../adr/0005-k3s-over-full-kubernetes.md). Once issue #33
lands, systemd units under `deploy/systemd/` install and start the k3s server
on the control-plane host and join every worker:

```bash
sudo systemctl enable --now k3s-server
# On each worker:
sudo systemctl enable --now k3s-agent
```

Verify with `kubectl get nodes`. All nodes should report `Ready` within 5
minutes.

## 3. Seal and apply secrets (**Scheduled**, issue #34)

Secrets are deployed via `SealedSecret` objects, never raw `Secret`s. The
`deploy/k3s/40-sealed-secrets/` overlay and its README are produced by issue
#34 (k3s manifests per service). Never paste an unencrypted secret into a
commit message, issue, or chat.

## 4. Apply the manifests (**Partially today**, completed by issue #34)

The `deploy/k3s/` directory contains the namespace and gateway manifests
today (`00-namespace.yaml`, `10-gateway.yaml`). Issue #34 lands the
per-service manifests and the Kustomize wiring. Once issue #34 is closed,
the full bootstrap is:

```bash
kubectl apply -k deploy/k3s/
```

Expected completion: ~15 minutes for image pulls on a warm Harbor mirror.

## 5. Seed the database (**Scheduled**, issues #11 and #12)

Postgres schema bootstrap (issue #11) and the Docling ingestion pipeline
(issue #12) together produce a one-shot `Job`:

```bash
kubectl -n afya-sahihi apply -f deploy/k3s/50-jobs/ingestion-seed.yaml
kubectl -n afya-sahihi logs -f job/ingestion-seed
```

Expected duration: ~2 hours for the initial corpus. The job is idempotent;
if it fails, delete and re-apply.

## 6. Run the first canary (**Today**)

The canary token is issued by AKU IdP. Export it from the operator's
secret store before running; never hard-code.

```bash
# Replace <FILL_ME> with the operator-scoped canary token from the
# AKU password manager (op://afya-sahihi/canary/token).
: "${CANARY_TOKEN:?set CANARY_TOKEN before running; see docs/runbooks/bootstrap.md §6}"

curl -H "Authorization: Bearer ${CANARY_TOKEN}" \
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
