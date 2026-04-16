# Afya Sahihi k3s Manifests

GitOps-managed declarative manifests for the Afya Sahihi cluster. Applied by the systemd watcher on `afya-sahihi-deploy-01` (see `deploy/systemd/afya-sahihi-watcher.service`).

## Layout

```
deploy/k3s/
├── 00-namespace.yaml              Namespace, default deny-all, quota
├── 10-gateway.yaml                Gateway API (FastAPI orchestrator) — fully specified
├── 11-retrieval.yaml              Retrieval service (hybrid dense + BM25 + reranker)
├── 12-conformal.yaml              Conformal prediction service
├── 13-audit.yaml                  Audit service (immutable log writer)
├── 14-prefilter.yaml              Pre-filter service (calls vLLM 4B with classifier head)
├── 15-ingestion-cronjob.yaml      Docling ingestion as weekly CronJob
├── 16-eval-runner.yaml            Inspect AI harness Job template
├── 17-al-scheduler.yaml           Active learning scheduler (APScheduler)
├── 20-frontend.yaml               React 19 static build served by nginx
├── 21-labeling.yaml               Streamlit labeling UI
├── 30-middlewares.yaml            Traefik middlewares (OIDC auth, rate limit, security headers)
├── 40-sealed-secrets/             Encrypted secrets (SealedSecret CRs)
├── 50-observability/              OTel, Tempo, Loki, Prometheus, Grafana, Phoenix
├── 90-rbac.yaml                   ServiceAccounts, Roles, RoleBindings
└── kustomization.yaml             Kustomize root
```

## Pattern for application services

Every service manifest in `10-`, `11-`, ... follows the same template. Use `10-gateway.yaml` as the canonical reference and copy the structure. The invariant pieces are:

- `ConfigMap` with non-secret env (pulled from the corresponding `env/*.env` file)
- `SealedSecret` in `40-sealed-secrets/` for sensitive env
- `Deployment` with:
  - non-root `securityContext` (runAsUser 1000, restricted profile, seccomp)
  - read-only root filesystem with explicit writable volumes
  - resource requests and limits
  - liveness / readiness / startup probes
  - topology spread across nodes
  - lifecycle preStop sleep for graceful drain
  - rolling update strategy with `maxUnavailable: 0`
- `Service` (ClusterIP)
- `ServiceAccount` with `automountServiceAccountToken: false`
- `PodDisruptionBudget` (minAvailable: 2 for stateless replicas)
- `HorizontalPodAutoscaler` (CPU + memory targets)
- `NetworkPolicy` with default-deny and explicit ingress/egress
- `ServiceMonitor` for Prometheus scraping

External routing (`IngressRoute`) exists only for services that face clinicians: gateway API, frontend, labeling UI, Grafana.

## Off-cluster bare-metal services

These run outside k3s and are managed by systemd on their respective nodes. See `deploy/systemd/`:

- `afya-sahihi-vllm-27b.service` (on `afya-sahihi-gpu-01`)
- `afya-sahihi-vllm-4b.service` (on `afya-sahihi-gpu-01`)
- `afya-sahihi-watcher.service` (on `afya-sahihi-deploy-01`)
- `postgresql@16-afya-sahihi.service` (on `afya-sahihi-data-01`, standard Debian service with overrides in `deploy/systemd/postgres-overrides/`)
- `minio.service` (on `afya-sahihi-data-01`)
- `redis-server@afya-sahihi.service` (on `afya-sahihi-data-01`)

## Apply order (bootstrap only)

On a greenfield cluster the watcher applies in filename order. For first-time manual bootstrap:

```bash
kubectl apply -f 00-namespace.yaml
kubectl apply -f 40-sealed-secrets/
kubectl apply -f 90-rbac.yaml
kubectl apply -f 30-middlewares.yaml
kubectl apply -f 50-observability/
kubectl apply -f 10-gateway.yaml
kubectl apply -f 11-retrieval.yaml
# ... etc
```

After bootstrap, rely on the watcher. Manual `kubectl apply` in production is grounds for rollback.

## Kustomize overlays

- `overlays/dev/` — single-replica, no PDBs, permissive NetworkPolicies, dev image tags
- `overlays/staging/` — production-like, smaller resource footprint, pre-production image tags
- `overlays/production/` — what is described above

The watcher points at `overlays/production/` in production. CI deploys to `overlays/staging/`.

## Secret rotation

All secrets are `SealedSecret` CRs encrypted with the cluster's controller key. To rotate:

```bash
# Encrypt new value
kubeseal --controller-namespace=kube-system --scope=strict \
  --from-file=POSTGRES_PASSWORD=/dev/stdin < <(openssl rand -base64 32) \
  > 40-sealed-secrets/postgres-password.yaml

# Commit, push, merge. Watcher applies. Controller decrypts to Secret.
# Redeploy pods that consume the secret.
```

See `docs/runbooks/sealed-secret-rotation.md` for the full procedure.
