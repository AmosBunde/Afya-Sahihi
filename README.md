# Afya Sahihi

**Clinical decision support for Kenyan healthcare. Traceable, calibrated, self-hosted.**

Afya Sahihi is the v2 architecture of Afya Gemma. The original system (MedGemma-powered RAG built on Vertex AI, ChromaDB, and LangGraph, winner of the Google GenAI Accelerator Award) shipped working software but exposed structural weaknesses: opaque orchestration, hidden retrieval failures, non-deterministic latency, and inability to collect the token-level data required for principled uncertainty quantification. Afya Sahihi is the rebuild that addresses all four and doubles as the experimental testbed for a three-paper PhD arc on conformal prediction for clinical LLM systems.

The name means "correct" or "authentic" in Swahili. It refers to the core epistemic commitment of the rebuild: answers that are traceable to source, quantified for uncertainty, and accurate by construction.

---

## Table of Contents

1. [What this repository contains](#1-what-this-repository-contains)
2. [Architecture at a glance](#2-architecture-at-a-glance)
3. [Server inventory](#3-server-inventory)
4. [Technology choices (with rationale)](#4-technology-choices-with-rationale)
5. [Quickstart (local dev)](#5-quickstart-local-dev)
6. [Production deployment](#6-production-deployment)
7. [Development workflow](#7-development-workflow)
8. [Repository layout](#8-repository-layout)
9. [Testing and evals](#9-testing-and-evals)
10. [Observability](#10-observability)
11. [Security and compliance](#11-security-and-compliance)
12. [The PhD research arc](#12-the-phd-research-arc)
13. [Credits and attribution](#13-credits-and-attribution)

---

## 1. What this repository contains

| Path | Purpose |
|------|---------|
| `docs/architecture/` | C4 Level 1, 2, 3 SVG diagrams |
| `docs/adr/` | Seven architecture decision records |
| `docs/runbooks/` | Operational runbooks for on-call |
| `env/` | Environment configuration for every service |
| `skills/afya-sahihi-principal/` | Principal engineer implementation playbook |
| `skills/afya-sahihi-review/` | Code review playbook (security, coupling, async, tests) |
| `deploy/k3s/` | Kubernetes manifests for the k3s cluster |
| `deploy/systemd/` | systemd unit files for bare-metal nodes |
| `deploy/vllm/` | vLLM startup scripts and tuning profiles |
| `deploy/observability/` | Grafana dashboards, alert rules, OTel config |
| `scripts/` | Bootstrap, hooks, backup, restore utilities |
| `backend/` | FastAPI gateway, retrieval, conformal, audit, ingestion services |
| `frontend/` | React 19 clinician chat UI |
| `labeling/` | Streamlit reviewer grading UI |
| `eval/` | Inspect AI three-tier eval harness |
| `.github/` | CI workflows, PR template, issue templates, CODEOWNERS |
| `.githooks/` | Project-level git hooks (installed via pre-commit) |

---

## 2. Architecture at a glance

Three diagrams answer three questions:

| Question | Diagram | File |
|----------|---------|------|
| What is the system and who uses it? | C4 Level 1 System Context | `docs/architecture/c4-level-1-context.svg` |
| What services and data stores exist, where do they run, and how do they talk? | C4 Level 2 Containers | `docs/architecture/c4-level-2-containers.svg` |
| How does a single clinical query flow from browser to response? | C4 Level 3 Components (inference path) | `docs/architecture/c4-level-3-inference-components.svg` |

**Key architectural moves (see ADRs for rationale)**:

- **vLLM self-hosted on H100** ([ADR-0001](docs/adr/0001-self-host-medgemma-on-vllm.md)). MedGemma 27B primary, 4B dual-role as pre-filter classifier and speculative draft model.
- **Postgres 16 as the single storage substrate** ([ADR-0002](docs/adr/0002-postgres-over-chromadb.md)). pgvector for dense, pg_search (Tantivy) for BM25, JSONB for structural metadata, all in one transaction.
- **Explicit Python state machine instead of LangGraph** ([ADR-0003](docs/adr/0003-explicit-state-machine-over-langgraph.md)). The orchestrator is one readable file under 400 lines.
- **Docling ingestion with structural metadata on every chunk** ([ADR-0004](docs/adr/0004-docling-structural-ingestion.md)). Section path, visual emphasis flags, table lineage, bounding boxes.
- **k3s + systemd watcher instead of full Kubernetes** ([ADR-0005](docs/adr/0005-k3s-over-full-kubernetes.md)). GPU node on bare metal outside the cluster.
- **Inspect AI three-tier eval harness as center of gravity** ([ADR-0006](docs/adr/0006-inspect-ai-three-tier-evals.md)). Unit, regression, clinician-in-the-loop. Gates every PR and deploy.
- **MedGemma 4B dual-role** ([ADR-0007](docs/adr/0007-medgemma-4b-dual-role.md)). Same model serves as pre-filter and speculative draft.

The request path end-to-end:

```
Clinician → Traefik → Gateway API
  → Pre-filter (vLLM 4B + classifier head)
  → Retrieval (pgvector + Tantivy → RRF → cross-encoder rerank)
  → Generation (vLLM 27B with speculative decoding)
  → Strict review (vLLM 27B, for safety-critical categories)
  → Conformal set construction
  → Audit write
  → SSE stream back to clinician
```

Every step emits an OTel span. Every step is a pure function of state. Every failure mode is typed.

---

## 3. Server inventory

Six physical nodes. This is the minimum viable production deployment. Scale horizontally by adding `work-0N` nodes. Scale the LLM path by adding a second GPU node for HA.

| Hostname | Role | Hardware | Workloads | Managed by |
|----------|------|----------|-----------|------------|
| `afya-sahihi-ctrl-01` | k3s control plane + ingress | 16 vCPU, 32GB RAM, 500GB NVMe | k3s server, Traefik, frontend, gateway API | k3s |
| `afya-sahihi-work-01` | k3s worker (general compute) | 16 vCPU, 64GB RAM, 1TB NVMe | Retrieval svc, conformal svc, ingestion worker, eval runner | k3s |
| `afya-sahihi-work-02` | k3s worker (secondary) | 16 vCPU, 64GB RAM, 1TB NVMe | Audit svc, AL scheduler, Streamlit labeling UI, observability stack | k3s |
| `afya-sahihi-data-01` | Data plane (bare metal) | 32 vCPU, 128GB RAM, 4TB NVMe RAID10 | Postgres 16, MinIO, Redis | systemd |
| `afya-sahihi-gpu-01` | LLM serving (bare metal) | 1× H100 80GB, 32 vCPU, 256GB RAM, 2TB NVMe | vLLM 27B, vLLM 4B (same GPU, SM partitioned) | systemd |
| `afya-sahihi-deploy-01` | GitOps watcher | 4 vCPU, 8GB RAM, 100GB NVMe | systemd git-polling watcher, alerting sidecar | systemd |

**Networking**: single VLAN, private. Public access only via Traefik on `afya-sahihi-ctrl-01` behind the AKU WAF. Internal traffic on 10.0.0.0/24. DNS via internal CoreDNS.

**Bastion**: SSH to all nodes via a single bastion host with hardware token MFA. No direct SSH from the internet.

**Backup**: `afya-sahihi-data-01` ships Postgres WAL + full weekly backups to MinIO via pgBackRest. MinIO itself is replicated to a second site (AKU Karachi) with a 24-hour lag.

---

## 4. Technology choices (with rationale)

See the ADRs for full reasoning. Summary table:

| Layer | Choice | Rationale |
|-------|--------|-----------|
| LLM serving | vLLM 0.7.x on bare-metal H100 | Logprobs, prefix caching, speculative decoding, deterministic latency, data residency |
| Primary model | MedGemma 27B, FP8 quantized | Best clinical quality available; fits one H100 at FP8 with headroom |
| Draft + pre-filter | MedGemma 4B, BF16 | Same family = speculative-decoding-compatible; dual role |
| Vector store | pgvector (HNSW, cosine) | One database, hybrid retrieval in one SQL |
| Lexical search | pg_search (Tantivy via ParadeDB) | Inline BM25 in Postgres, no second system |
| App database | Postgres 16 (asyncpg) | Relational fits our data; async without ORM pain |
| Chunking | Docling HybridChunker v2.9 | Preserves structural metadata we depend on |
| Embeddings | BGE-M3, matryoshka-truncated 1024 | Multilingual (English + Swahili), strong clinical retrieval |
| Reranker | bge-reranker-v2-m3 | CPU-inferable, boosts precision meaningfully |
| API framework | FastAPI + Pydantic v2 strict | Typed, async-first, OpenAPI-native |
| Orchestrator | Plain Python state machine | Readable, debuggable, no framework lock-in |
| Queue / cache | Redis 7 | Rate limits, job queue, session cache |
| Object storage | MinIO (S3-compatible) | Source PDFs, model cache, backups, trace storage |
| Container orchestration | k3s 1.33 | Kubernetes API without full-K8s weight |
| GPU orchestration | systemd | Bare metal, no device plugin complexity |
| GitOps | Custom systemd watcher | Simple, observable, already battle-tested from v1 |
| Ingress | Traefik | Native k3s integration, middleware model |
| Secrets | Sealed Secrets | Encrypted in git, decrypted in cluster |
| Container registry | Harbor (self-hosted) | Vuln scanning, signing, no external dependency |
| CI | GitHub Actions (self-hosted runners) | Community, matrix, caching |
| Traces | Grafana Tempo | Scales, S3-backed, Grafana-native |
| LLM-specific tracing | Arize Phoenix | Token-level spans, retrieval inspection |
| Metrics | Prometheus + Alertmanager | Standard |
| Logs | Loki + Promtail | Structured, Grafana-native |
| Dashboards | Grafana 11 | OIDC-protected, unified across signals |
| Eval harness | Inspect AI | Purpose-built, research-grade scoring |
| Frontend | React 19 + Vite + Tanstack Query | Typed, fast, SSE-native |
| Labeling UI | Streamlit | Clinician-friendly, rapid iteration |
| Auth | Keycloak (OIDC) | AKU already runs this |
| Fine-tuning | Unsloth + TRL | Fast, memory-efficient GRPO on H100 |

Conspicuous absences, with reasons:

- **LangChain / LangGraph**: banned on request path (ADR-0003). Permitted in offline scripts.
- **Pinecone / Weaviate / Qdrant**: rejected in favor of pgvector (ADR-0002).
- **Firestore / MongoDB**: relational data belongs in a relational store.
- **Vertex AI**: rejected on logprob access and data residency (ADR-0001).
- **Gemini / OpenAI APIs on request path**: no external LLM calls during clinical inference.
- **SQLAlchemy ORM**: raw asyncpg preferred; our queries are too deliberate for an ORM.
- **Full Kubernetes**: k3s covers our scale (ADR-0005).
- **ArgoCD / Flux**: systemd watcher is sufficient; we do not need multi-cluster.

---

## 5. Quickstart (local dev)

Requirements: Docker, Docker Compose, Python 3.12, uv, 32GB RAM, 100GB free disk. A local NVIDIA GPU is optional; without one, use the Hugging Face Inference Endpoint stub for MedGemma (see `deploy/vllm/local-stub.md`).

```bash
# 1. Clone
git clone git@github.com:AmosBunde/Afya-Sahihi.git
cd Afya-Sahihi

# 2. Install git hooks (one-time, per clone)
pip install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type pre-push
pre-commit install --hook-type commit-msg

# 3. Copy dev env template
cp env/.env.dev.example .env

# 4. Bootstrap local stack (Postgres + Redis + MinIO + observability)
docker compose -f deploy/local/docker-compose.yaml up -d

# 5. Run migrations
uv run alembic upgrade head

# 6. Ingest a sample corpus (5 MoH PDFs included under `samples/`)
uv run python -m app.scripts.ingest --source samples/moh-mini/

# 7. Run backend services locally
uv run python -m app.main  # gateway
# in other terminals:
uv run python -m retrieval.main
uv run python -m conformal.main
uv run python -m audit.main

# 8. Start frontend
cd frontend && npm install && npm run dev

# 9. Open http://localhost:5173 and log in with dev credentials (seeded in Keycloak)
```

Smoke test: ask "What is first-line treatment for uncomplicated falciparum malaria in a pediatric patient?" and verify the response cites the Kenyan MoH malaria guidelines with a prediction set size ≤ 3 at coverage 0.90.

---

## 6. Production deployment

Production deploys through GitOps. You do not run `kubectl apply` by hand.

```bash
# 1. Open PR against the deploy repo
git checkout -b deploy/prod/2026-04-16-release-v1.0.0
# edit deploy/k3s/overlays/production/kustomization.yaml to bump image tags
git commit -am "feat(deploy): release v1.0.0"
git push origin deploy/prod/2026-04-16-release-v1.0.0

# 2. CI runs Tier 2 evals against staging. If green, PR is mergeable.

# 3. Two reviewers approve. Merge.

# 4. systemd watcher on afya-sahihi-deploy-01 picks up the change within 60s.
#    It runs `kubectl diff` (dry-run), then `kubectl apply --prune`.
#    Progress is visible in Grafana dashboard "Deployments".

# 5. Canary runs for 30 minutes. Auto-rollback if error rate > 0.5% or P99 > 6s.

# 6. Full rollout completes. Slack notification fires.
```

**First-time bootstrap** is documented in `docs/runbooks/bootstrap.md`. Expected duration is a working day, mostly waiting for image pulls and MinIO sync.

**Rolling back** is the same process in reverse: revert the PR, watcher applies within 60s. Postgres migrations are reversible by construction (every Alembic migration has a tested `downgrade`).

---

## 7. Development workflow

### Branches and commits

- `main` is always deployable. Direct pushes are blocked.
- Feature branches: `feat/<area>-<short-description>`
- Bugfix branches: `fix/<short-description>`
- ADR branches: `adr/<nnnn>-<title>`

Commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(orchestrator): add strict review stage for dosing queries
fix(retrieval): correct RRF constant for hybrid fusion
docs(adr): record decision to prefer Postgres over ChromaDB
```

The pre-commit `commit-msg` hook enforces this. If your message is rejected, read the scope list at the top of `.pre-commit-config.yaml`.

### Pre-commit hooks

The repo ships 9 tiers of hooks. They run on `pre-commit`, `pre-push`, and `commit-msg`:

- **Tier 0** — whitespace, EOF, merge conflicts, large files, case conflicts
- **Tier 1** — gitleaks + detect-secrets (fails closed on any match)
- **Tier 2** — ruff (lint + format), pyright strict
- **Tier 3** — bandit + pip-audit
- **Tier 4** — ESLint + tsc for frontend
- **Tier 5** — yamllint + kubeval for manifests
- **Tier 6** — sqlfluff on migrations
- **Tier 7** — shellcheck
- **Tier 8** — conventional-pre-commit on commit messages
- **Tier 9** — custom `scripts/hooks/*.sh` enforcing ADR-level rules

See `.pre-commit-config.yaml` for the full list and `scripts/hooks/` for the custom checks.

### Skills

Two skills live in `skills/` and must be read by every new engineer:

- `skills/afya-sahihi-principal/SKILL.md` — the implementation playbook. Read before writing code.
- `skills/afya-sahihi-review/SKILL.md` — the review playbook. Read before approving a PR.

Changes to either skill require an ADR.

### Opening a PR

1. Branch from `main`.
2. Commit with conventional messages.
3. Push. Pre-push hooks run (Tier 1 evals, pip-audit, ADR-for-new-dep check).
4. Open PR. Template pre-populates the review checklist.
5. CI runs: hygiene, secrets, SAST, deps, backend tests, Tier 1 evals, frontend tests, container build, manifest validation.
6. CODEOWNERS auto-requests reviewers.
7. Address review comments. Re-request review.
8. On all approvals and green CI, rebase-merge. No squash (commits are atomic by design).

---

## 8. Repository layout

```
Afya-Sahihi/
├── backend/                    FastAPI gateway + services
│   ├── app/                    gateway code (see SKILL.md §2)
│   ├── retrieval/
│   ├── conformal/
│   ├── audit/
│   ├── prefilter/
│   ├── ingestion/
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                   React 19 + Vite clinician chat
├── labeling/                   Streamlit reviewer grading UI
├── eval/                       Inspect AI three-tier eval harness
├── docs/
│   ├── architecture/           C4 SVG diagrams
│   ├── adr/                    Architecture decision records
│   ├── runbooks/               Operational runbooks
│   └── papers/                 PhD paper drafts (private branch)
├── env/                        All .env files (no secrets)
├── deploy/
│   ├── k3s/                    Kubernetes manifests
│   ├── systemd/                Bare-metal unit files
│   ├── vllm/                   vLLM startup scripts
│   └── observability/          Grafana + alert rules
├── scripts/
│   ├── bootstrap_issues.sh     gh CLI issue backlog creator
│   ├── hooks/                  Custom pre-commit hook scripts
│   └── audit/                  Audit log chain verification
├── skills/
│   ├── afya-sahihi-principal/
│   └── afya-sahihi-review/
├── .github/
│   ├── workflows/
│   ├── ISSUE_TEMPLATE/
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── CODEOWNERS
│   ├── labeler.yml
│   └── dependabot.yml
├── .pre-commit-config.yaml
├── .gitignore
├── .yamllint.yaml
├── .secrets.baseline
├── README.md                   ← you are here
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

---

## 9. Testing and evals

Three-tier harness, all Inspect AI (ADR-0006).

**Tier 1 — Unit evals (every commit)**
- 500 curated query-response pairs
- Exact-match scoring on key facts (drug, dose, route, frequency)
- Runtime < 2 minutes
- Gate: regression blocks PR (enforced by pre-push hook)

**Tier 2 — Regression evals (nightly + pre-deploy)**
- 2,000 queries with adversarial rephrasing, code-switching, misspellings
- Scored on ECE, marginal coverage, set size, topic coherence
- Gate: any metric drop > 2% blocks promotion

**Tier 3 — Clinician-in-the-loop (weekly)**
- 20 reviewer-graded responses per week
- 5-point rubric (accuracy, safety, guideline alignment, local appropriateness, clarity)
- Feeds calibration set and active learning loop

Run locally:

```bash
cd eval
uv run inspect eval tier1/golden_set.py --model afya-sahihi
uv run inspect eval tier2/regression.py --model afya-sahihi --limit 100
```

Production eval results land in Postgres `eval_runs` table. Grafana dashboard `Eval Metrics` renders trends.

---

## 10. Observability

Three pillars, one UI.

| Signal | Collector | Store | Retention | UI |
|--------|-----------|-------|-----------|-----|
| Traces | OTel Collector | Grafana Tempo | 30 days | Grafana |
| LLM spans (token-level) | OTel Collector | Arize Phoenix | 14 days | Phoenix UI, linked from Grafana |
| Metrics | Prometheus | Prometheus TSDB | 30 days | Grafana |
| Logs | Promtail | Loki | 30 days | Grafana |
| Audit logs | Gateway → Audit Service | Postgres `queries_audit` | 7 years | Protected query interface |

Pre-provisioned Grafana dashboards:

- **RED metrics** — Rate, Error, Duration per service
- **LLM metrics** — Time-to-first-token, tokens/sec, KV cache hit rate, speculative acceptance rate
- **Retrieval metrics** — Dense vs sparse contribution, reranker lift, top-1 similarity distribution
- **Conformal metrics** — Empirical coverage, set size distribution, stratum coverage, drift indicator
- **Eval metrics** — Tier 1/2/3 trends, rubric score distribution, rater agreement
- **GPU metrics** — DCGM utilization, memory, power, temperature
- **Infra metrics** — Node CPU, memory, disk, network; Postgres, Redis, MinIO exporters

Alerts fire to Alertmanager which routes to Slack (non-urgent) or PagerDuty (urgent). Alert rules live in `deploy/observability/alerts/`.

---

## 11. Security and compliance

**Data**
- PHI-adjacent query text stays on AKU hardware (ADR-0001). No external LLM calls on the request path.
- PHI scrubber runs before every audit write. Fails closed if scrubber errors.
- All data at rest encrypted: Postgres `pgcrypto` on PHI-adjacent columns, LUKS on underlying disks.
- All data in transit via TLS 1.3. mTLS between services where latency allows.

**Access**
- OIDC via Keycloak. Roles: clinician, reviewer, researcher, sre, admin.
- Audit log export requires two-person approval.
- No service account has broader permissions than the role needs.

**Supply chain**
- Container images signed with cosign, verified at admission via Kyverno.
- Dependencies pinned. Dependabot weekly PRs + manual review.
- gitleaks + detect-secrets on every commit.
- Bandit + Semgrep + CodeQL + Trivy on every PR.
- SBOMs generated per build.

**Compliance**
- AKU IRB approval for retrospective query analysis: `AKU-IRB-2026-0147`
- NACOSTI research permit: `NACOSTI/P/26/12345`
- Audit log retention: 7 years (Kenyan clinical standard)
- Data Protection Act 2019 (Kenya) compliance reviewed quarterly

**Vulnerability response**
- See `SECURITY.md`.
- Do NOT open a public issue for security bugs. Email `security@aku.edu`.

---

## 12. The PhD research arc

Afya Sahihi serves as the experimental testbed for three papers. Every architectural choice that prioritizes determinism, logprob access, structural provenance, and reproducibility is downstream of this research requirement.

| Paper | Venue | Core contribution |
|-------|-------|-------------------|
| P1 | CHIL / FAccT / AAAI | Empirical calibration analysis of MedGemma under distribution shift |
| P2 | NeurIPS / ICML / AISTATS | Adaptive conformal prediction for RAG with clinical-harm-weighted scores |
| P3 | KDD / AAAI | Uncertainty-guided active learning deployed in production at AKU |

All three papers draw experimental data from the same Afya Sahihi deployment. The full variable and config inventory lives under `docs/papers/variables-inventory.md` (private branch).

---

## 13. Credits and attribution

- **Lead engineer and researcher**: Ezra O'Marley (Amos Bunde), Manager of Data Infrastructure at AKU
- **Supervising institution**: Strathmore University (PhD), AKU (deployment)
- **Research consortium**: Uzima-DS (NIH-funded, AKU / University of Michigan / KEMRI)
- **Original Afya Gemma**: Winner, Google GenAI Accelerator Award 2025
- **Model weights**: MedGemma by Google DeepMind (Apache 2.0 terms)
- **Clinical guidelines**: Kenya Ministry of Health (used with attribution and IRB approval)

---

## License

Code: Apache 2.0. See `LICENSE`.
Model weights: per upstream MedGemma terms.
Clinical guideline content: per MoH Kenya terms; redistribution not permitted without explicit authorization.

## Contact

- Technical / contribution questions: open an issue
- Security: `security@aku.edu` (see `SECURITY.md`)
- Clinical safety: `clinical-safety@aku.edu`
