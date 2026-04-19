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

## 1. Verify prerequisites (**Today**)

Run the preflight check on every target host. It verifies kernel (>= 6.1),
cgroup v2, swap-off, disk headroom, required binaries, and port 6443 availability.
Agent nodes additionally check for the join token; the GPU node checks for the
NVIDIA driver (>= 550).

```bash
# On each control/worker candidate:
sudo ./deploy/systemd/bootstrap/preflight.sh --role=server   # or --role=agent

# On the GPU bare-metal host:
sudo ./deploy/systemd/bootstrap/preflight.sh --role=gpu
```

Stop on any failure; each check guards a downstream assumption.

## 2. Bring up k3s (**Today**)

Follow [ADR-0005](../adr/0005-k3s-over-full-kubernetes.md). The installer
pins k3s to `v1.30.5+k3s1` and writes its kubeconfig to
`/etc/afya-sahihi/kubeconfig.yaml` for the watcher to read.

```bash
# Control node (afya-sahihi-ctrl-01):
sudo ./deploy/systemd/bootstrap/install_k3s_server.sh

# Copy /etc/afya-sahihi/secrets/k3s-token to each worker out-of-band
# (scp via the bastion). Then on each worker:
sudo ./deploy/systemd/bootstrap/install_k3s_agent.sh \
  --server=https://afya-sahihi-ctrl-01.internal:6443
```

Verify with `kubectl get nodes`. All 3 should report `Ready` within 5 minutes.

Install the SealedSecrets controller and its key-pair before the watcher
starts — the watcher refuses to apply manifests with undefined CRDs:

```bash
kubectl apply -f deploy/k3s/sealed-secrets.yaml
# One-time seed of the key-pair. See docs/runbooks/sealed-secrets-rotation.md.
kubeseal --fetch-cert > /etc/afya-sahihi/secrets/sealed-secrets.crt
```

## 3. Seal and apply secrets (**Scheduled**, issue #34)

Secrets are deployed via `SealedSecret` objects, never raw `Secret`s. The
`deploy/k3s/40-sealed-secrets/` overlay and its README are produced by issue
#34 (k3s manifests per service). Never paste an unencrypted secret into a
commit message, issue, or chat.

## 4. Start the watcher (**Today**)

The watcher polls the deploy repo every 60s and `kubectl apply -k` the
environment's kustomize overlay on every new commit. This is the standing
GitOps path — once the watcher is up, every subsequent change lands via
`git push`, not `kubectl apply`.

```bash
# On afya-sahihi-deploy-01:
sudo ./deploy/systemd/bootstrap/install_watcher.sh

# Verify it's polling:
sudo systemctl status afya-sahihi-watcher.service
# Journaled output is structured JSON; tail for change events:
sudo journalctl -u afya-sahihi-watcher.service -f
```

First-time bootstrap apply (before the watcher observes a new push) is the
initial pull, which can take ~15 minutes for image pulls on a warm Harbor
mirror. A manual kick is available via `sudo -u afya-sahihi-deploy
afya-sahihi-watcher reconcile` if needed.

The dashboards ConfigMap must be seeded once before Grafana starts:

```bash
scripts/observability/build_dashboards_configmap.sh | kubectl apply -f -
```

Subsequent dashboard edits flow through the watcher once the dashboard
generator is wired into a CI job (tracked separately).

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
