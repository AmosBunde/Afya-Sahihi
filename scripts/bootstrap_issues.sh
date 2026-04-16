#!/usr/bin/env bash
# =====================================================================
# Afya Sahihi - GitHub issues bootstrap script
# =====================================================================
# Run once against an empty repo to stamp out labels, milestones, and
# a full issue backlog that covers every architectural workstream.
#
# Requirements:
#   - gh CLI authenticated (`gh auth login`)
#   - Repo must exist (blank is fine)
#   - Run from repo root: `bash scripts/bootstrap_issues.sh`
#
# Idempotency: gh create commands will fail loudly if a label/milestone
# already exists. The script uses `|| true` on setup and fresh issue
# creates on issues. Re-running will produce duplicate issues; to
# re-run safely, first close the old milestone.
# =====================================================================

set -euo pipefail

REPO="${REPO:-AmosBunde/Afya-Sahihi}"

echo "==> Target repo: $REPO"
echo "==> Verifying gh auth..."
gh auth status
echo ""

# =====================================================================
# 1. LABELS
# =====================================================================
echo "==> Creating labels..."

create_label() {
  local name="$1" color="$2" desc="$3"
  gh label create "$name" --repo "$REPO" --color "$color" --description "$desc" 2>/dev/null \
    || gh label edit "$name" --repo "$REPO" --color "$color" --description "$desc" 2>/dev/null \
    || true
}

# Type labels
create_label "type/feature"         "0E8A16" "New capability"
create_label "type/bug"             "D73A4A" "Defect"
create_label "type/adr"             "5319E7" "Architecture decision"
create_label "type/chore"           "FEF2C0" "Maintenance"
create_label "type/docs"            "0075CA" "Documentation"
create_label "type/security"        "B60205" "Security-related"
create_label "type/research"        "BFD4F2" "PhD / research work"

# Priority labels
create_label "priority/P0"          "B60205" "Blocker"
create_label "priority/P1"          "D93F0B" "This sprint"
create_label "priority/P2"          "FBCA04" "This quarter"
create_label "priority/P3"          "C2E0C6" "Someday"

# Area labels
create_label "area/backend"         "0052CC" "Backend services"
create_label "area/frontend"        "0052CC" "React frontend"
create_label "area/labeling-ui"     "0052CC" "Streamlit labeling UI"
create_label "area/eval"            "0052CC" "Inspect AI eval harness"
create_label "area/orchestrator"    "006B75" "Pipeline orchestrator"
create_label "area/retrieval"       "006B75" "Retrieval service"
create_label "area/conformal"       "006B75" "Conformal prediction"
create_label "area/ingestion"       "006B75" "Docling ingestion"
create_label "area/audit"           "006B75" "Audit service"
create_label "area/docs"            "0075CA" "Documentation"
create_label "area/adr"             "5319E7" "Architecture decisions"
create_label "area/deploy"          "1D76DB" "Deploy (k3s, systemd)"
create_label "area/env"             "1D76DB" "Environment config"
create_label "area/ci"              "1D76DB" "CI/CD, hooks, automation"
create_label "area/schema"          "1D76DB" "Database schema, migrations"
create_label "area/observability"   "1D76DB" "OTel, Prometheus, logs"

# Status / workflow labels
create_label "status/blocked"       "E99695" "Blocked on something"
create_label "status/in-progress"   "FBCA04" "Actively being worked"
create_label "status/needs-review"  "0E8A16" "Ready for review"
create_label "status/needs-triage"  "D4C5F9" "Awaits prioritization"
create_label "needs-adr"            "5319E7" "Requires a new ADR"
create_label "touches-request-path" "D93F0B" "Changes the request pipeline"
create_label "touches-security"     "B60205" "Security implications"
create_label "touches-phi"          "B60205" "Touches PHI handling"

# Size labels (filled by automation)
create_label "size/xs"              "BFE5BF" ""
create_label "size/s"               "BFE5BF" ""
create_label "size/m"               "FEF2C0" ""
create_label "size/l"               "F9D0C4" ""
create_label "size/xl"              "D73A4A" "Too big, split"

# Good first issue + help wanted
create_label "good-first-issue"     "7057FF" "Good starter task"
create_label "help-wanted"          "008672" "External contributors welcome"

echo "==> Labels done."
echo ""

# =====================================================================
# 2. MILESTONES
# =====================================================================
echo "==> Creating milestones..."

create_milestone() {
  local title="$1" desc="$2" due="$3"
  gh api "repos/$REPO/milestones" -f title="$title" -f description="$desc" -f due_on="$due" \
    >/dev/null 2>&1 || echo "   (milestone '$title' may already exist)"
}

create_milestone "M0 Foundation"           "Repo setup, hooks, skills, CI, docs scaffolding"          "2026-05-01T00:00:00Z"
create_milestone "M1 Data plane"            "Postgres 16, pgvector, pg_search, ingestion, schema"      "2026-05-22T00:00:00Z"
create_milestone "M2 LLM serving"           "vLLM 27B + 4B on H100, speculative decoding, classifier"  "2026-06-12T00:00:00Z"
create_milestone "M3 Retrieval"             "Hybrid dense + BM25, reranker, structural metadata"       "2026-07-03T00:00:00Z"
create_milestone "M4 Orchestrator"          "Explicit state machine, gateway, error handling"          "2026-07-24T00:00:00Z"
create_milestone "M5 Conformal"             "Prediction sets, coverage monitoring, drift"              "2026-08-14T00:00:00Z"
create_milestone "M6 Eval + Labeling"       "Inspect AI 3-tier harness, Streamlit reviewer UI"         "2026-09-04T00:00:00Z"
create_milestone "M7 Observability"         "OTel, Tempo, Loki, Prometheus, Grafana, Phoenix"          "2026-09-25T00:00:00Z"
create_milestone "M8 Deploy + Frontend"     "k3s, systemd watcher, React chat UI, go-live"             "2026-10-16T00:00:00Z"
create_milestone "M9 Active Learning"       "AL scheduler, online deployment, P3 paper data"           "2026-12-01T00:00:00Z"

echo "==> Milestones done."
echo ""

# =====================================================================
# 3. ISSUES
# =====================================================================
echo "==> Creating issues..."

create_issue() {
  local title="$1"
  local body="$2"
  local labels="$3"
  local milestone="$4"

  gh issue create \
    --repo "$REPO" \
    --title "$title" \
    --body "$body" \
    --label "$labels" \
    --milestone "$milestone" \
    >/dev/null
  echo "   ✔ $title"
}

# ---------------------------------------------------------------------
# M0 FOUNDATION
# ---------------------------------------------------------------------

create_issue \
  "feat(ci): install pre-commit framework and configure default hooks" \
'## Problem
We need pre-commit enforcement across Python, frontend, YAML, SQL, shell, and commit messages from day one so that the hooks described in `.pre-commit-config.yaml` actually run.

## Proposal
- Install `pre-commit` as a dev dependency
- Document `pre-commit install --install-hooks --hook-type pre-push --hook-type commit-msg` in CONTRIBUTING
- Verify all hooks pass on a clean checkout

## Acceptance
- [ ] `pre-commit run --all-files` passes on main
- [ ] CONTRIBUTING.md documents the install ritual
- [ ] CI runs `pre-commit run --all-files --show-diff-on-failure`

## Refs
- `.pre-commit-config.yaml`
- `docs/skills/afya-sahihi-principal/SKILL.md` §0
' \
  "type/chore,area/ci,priority/P0" \
  "M0 Foundation"

create_issue \
  "feat(ci): add custom hook scripts for Afya-Sahihi-specific rules" \
'## Problem
The pre-commit config references custom scripts under `scripts/hooks/` that enforce ADR-level rules (no LangChain on request path, line cap on orchestrator, PHI-free logs, etc). These scripts ship in this repo and must be kept green.

## Proposal
Implement and verify the 10 custom hooks:
- `check_no_langchain_request_path.sh`
- `check_no_print.sh`
- `check_httpx_timeouts.sh`
- `check_asyncpg_timeouts.sh`
- `check_orchestrator_lines.sh`
- `check_env_documented.sh`
- `check_adr_for_new_dep.sh`
- `run_tier1_evals.sh`
- `check_no_phi_in_logs.sh`
- `check_span_per_transition.sh`

## Acceptance
- [ ] Each hook has a unit test (green path + at least one red path)
- [ ] Each hook documented in a comment block at the top of the file
- [ ] Hook failures produce actionable error messages

## Refs
- `.pre-commit-config.yaml`
- `scripts/hooks/`' \
  "type/chore,area/ci,priority/P0" \
  "M0 Foundation"

create_issue \
  "docs: commit architecture documentation (README, ADRs, C4 diagrams, skills)" \
'## Problem
The repo must ship with the complete architecture documentation before any code lands. New engineers should be able to onboard from `README.md` alone.

## Proposal
Commit the following, already prepared:
- `README.md` (top-level, extensive)
- `docs/adr/0001` through `0007`
- `docs/adr/README.md` (index)
- `docs/architecture/c4-level-{1,2,3}-*.svg`
- `skills/afya-sahihi-principal/SKILL.md`
- `skills/afya-sahihi-review/SKILL.md`

## Acceptance
- [ ] All listed files present
- [ ] SVGs render in GitHub preview
- [ ] ADR index links resolve
- [ ] README references every ADR
- [ ] Both skills are discoverable from README' \
  "type/docs,area/docs,area/adr,priority/P0" \
  "M0 Foundation"

create_issue \
  "feat(ci): set up GitHub Actions CI workflow" \
'## Problem
CI gates every PR. Without it, the pre-commit hooks can be bypassed locally.

## Proposal
The `.github/workflows/ci.yml` defines nine jobs: hygiene, secrets, sast, deps, backend-tests, tier1-evals, frontend-tests, container-build, manifest-validate. Wire them up, verify they run on a fresh PR.

## Acceptance
- [ ] All CI jobs run on a trivial PR
- [ ] Required status checks configured in branch protection
- [ ] Codecov integration working
- [ ] SARIF uploads to GitHub Security tab' \
  "type/chore,area/ci,priority/P0" \
  "M0 Foundation"

create_issue \
  "feat(ci): PR automation workflow (labels, size, checklist, title lint)" \
'## Problem
We want PR discipline enforced in automation, not left to reviewer memory.

## Proposal
The `.github/workflows/pr-automation.yml` handles:
- Auto-labeling via `.github/labeler.yml`
- PR size cap (>1000 lines blocks)
- Checklist completeness check
- Conventional commit title lint
- Welcome comment with checklist reminder

## Acceptance
- [ ] All automation runs on a new draft PR
- [ ] Labels apply correctly per file path
- [ ] `size/xl` blocks merge
- [ ] Non-conventional titles are flagged' \
  "type/chore,area/ci,priority/P0" \
  "M0 Foundation"

create_issue \
  "docs: commit CODEOWNERS, PR template, issue templates, SECURITY.md, CONTRIBUTING.md" \
'## Problem
Issue and PR hygiene starts with templates. SECURITY.md tells external parties how to report vulnerabilities.

## Proposal
Commit:
- `.github/CODEOWNERS`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/*.yml`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `LICENSE` (Apache 2.0)

## Acceptance
- [ ] New issues open with the appropriate template picker
- [ ] New PRs pre-populate the review checklist
- [ ] CODEOWNERS rules route reviews correctly
- [ ] SECURITY.md linked from README' \
  "type/docs,area/docs,priority/P0" \
  "M0 Foundation"

create_issue \
  "feat(ci): Dependabot for Python, npm, GitHub Actions, Docker" \
'## Problem
Supply chain drift is a security risk. Dependabot should PR updates weekly.

## Proposal
Add `.github/dependabot.yml` configured for:
- `pip` in `/backend`
- `npm` in `/frontend`
- `github-actions` in root
- `docker` for any Dockerfiles

Group security updates separately from version bumps. Auto-label with `area/ci` and `needs-adr` where applicable.

## Acceptance
- [ ] Dependabot opens at least one PR against the new config
- [ ] Security alerts fire on GitHub
- [ ] ADR-requiring updates correctly flagged' \
  "type/chore,area/ci,priority/P1" \
  "M0 Foundation"

# ---------------------------------------------------------------------
# M1 DATA PLANE
# ---------------------------------------------------------------------

create_issue \
  "feat(schema): bootstrap Postgres 16 with pgvector, pg_search, pgcrypto, pg_cron" \
'## Problem
Postgres is the single storage substrate (ADR-0002). We need the extensions loaded, a role/privileges model set up, and the initial schema applied.

## Proposal
Alembic migration `0001_init.sql` creates:
- Role `afya_sahihi_app` with least privilege
- Extensions: pgvector, pg_search, pgcrypto, pg_stat_statements, pg_cron
- Initial tables: `chunks`, `queries_audit`, `calibration_set`, `grades`, `eval_runs`
- HNSW index on chunks.embedding with params m=16, ef_construction=64
- BM25 index on chunks.content via pg_search
- JSONB GIN index on chunks.structural_meta

## Acceptance
- [ ] `alembic upgrade head` succeeds on a fresh PG16 instance
- [ ] `SELECT * FROM chunks` returns with correct types
- [ ] HNSW and BM25 indexes queryable
- [ ] Migration is reversible

## Refs
- ADR-0002' \
  "type/feature,area/schema,touches-request-path,priority/P0" \
  "M1 Data plane"

create_issue \
  "feat(ingestion): Docling-based PDF ingestion pipeline with structural metadata" \
'## Problem
Per ADR-0004, every chunk must carry structural metadata (section path, visual emphasis, table lineage, bounding boxes). Afya Gemma v1 flattened PDFs and lost exactly these signals.

## Proposal
Build `backend/ingestion/`:
- Docling 2.9 HybridChunker with `max_tokens=512, overlap=64, merge_peers=True`
- Extract `structural_meta` per chunk (schema in ADR-0004)
- Embed with BGE-M3, matryoshka-truncated to 1024 dims
- Batch insert into `chunks` with `corpus_version` stamping
- Idempotent: `document_hash` dedupes re-ingests

## Acceptance
- [ ] Ingest 5 sample MoH PDFs from `samples/moh-mini/`
- [ ] Every chunk has non-null `structural_meta`
- [ ] Contraindication detection: red-box text gets `is_contraindication: true`
- [ ] Re-ingest is a no-op on unchanged input
- [ ] Ingestion runs as CronJob in k3s (manifest in deploy/)

## Refs
- ADR-0004
- `env/ingestion.env`' \
  "type/feature,area/ingestion,priority/P0" \
  "M1 Data plane"

create_issue \
  "feat(schema): audit log with hash chaining and PHI scrubber" \
'## Problem
Audit log is a regulatory requirement. It must be append-only, tamper-evident, and PHI-scrubbed.

## Proposal
- `queries_audit` table with trigger preventing UPDATE and DELETE
- Hash chain: each row stores hash(prev_hash || row_payload)
- PHI scrubber runs BEFORE write, fails closed if scrubber errors
- 7-year retention policy enforced via `pg_cron`

## Acceptance
- [ ] UPDATE/DELETE on `queries_audit` raises
- [ ] Hash chain verifiable with a script under `scripts/audit/verify_chain.py`
- [ ] PHI scrubber regex tests cover patient names, MRNs, phone numbers
- [ ] Export endpoint requires two-person approval

## Refs
- ADR-0002
- `env/audit.env`' \
  "type/feature,area/audit,touches-phi,touches-security,priority/P0" \
  "M1 Data plane"

create_issue \
  "feat(data): Redis cluster setup and pgBackRest backup configuration" \
'## Problem
Redis handles rate limits, job queue, and session cache. pgBackRest does point-in-time recovery to MinIO.

## Proposal
- systemd units for Redis on `afya-sahihi-data-01`
- pgBackRest configuration: Sunday full, daily diff, 4-week retention
- MinIO bucket `afya-sahihi-backups` with versioning enabled
- Verify restore on `afya-sahihi-data-02` (standby)

## Acceptance
- [ ] Redis accessible from k3s nodes with TLS
- [ ] `pgbackrest backup --type=full` succeeds
- [ ] Restore rehearsal documented in `docs/runbooks/backup-restore.md`' \
  "type/feature,area/deploy,priority/P1" \
  "M1 Data plane"

# ---------------------------------------------------------------------
# M2 LLM SERVING
# ---------------------------------------------------------------------

create_issue \
  "feat(vllm): vLLM MedGemma 27B on H100 via systemd" \
'## Problem
Self-hosted MedGemma 27B is the primary generator (ADR-0001). Vertex AI endpoints lack logprob access needed for conformal prediction.

## Proposal
- Deploy `afya-sahihi-vllm-27b.service` systemd unit on `afya-sahihi-gpu-01`
- Configuration via `env/vllm-27b.env`: FP8, prefix caching, max_model_len=8192
- Health endpoint `/health` responding in <100ms
- Prometheus metrics on port 8002

## Acceptance
- [ ] `systemctl start afya-sahihi-vllm-27b` succeeds with weights loaded in under 300s
- [ ] `curl /v1/chat/completions` returns a response with `logprobs`
- [ ] P50 latency <2s, P99 <4s for 512-token completions
- [ ] Restarts cleanly on SIGTERM
- [ ] DCGM exporter reports GPU metrics to Prometheus

## Refs
- ADR-0001
- `deploy/systemd/afya-sahihi-vllm-27b.service`
- `deploy/vllm/afya-sahihi-vllm-27b-launch`' \
  "type/feature,area/deploy,priority/P0" \
  "M2 LLM serving"

create_issue \
  "feat(vllm): vLLM MedGemma 4B with classifier head (dual role)" \
'## Problem
The 4B serves two roles: pre-filter classifier head and speculative draft for the 27B (ADR-0007).

## Proposal
- Deploy `afya-sahihi-vllm-4b.service` systemd unit sharing the H100 with the 27B
- LoRA adapter loading for the classifier head (`prefilter` module)
- SM partitioning: 15% GPU memory to 4B
- `services/prefilter/` FastAPI wrapper that calls vLLM and runs the head

## Acceptance
- [ ] `systemctl start afya-sahihi-vllm-4b` succeeds
- [ ] LoRA adapter `prefilter` loads at startup
- [ ] Classifier head inference <50ms
- [ ] Speculative decoding acceptance rate >60% on clinical queries
- [ ] No contention with 27B under load test

## Refs
- ADR-0007
- `env/vllm-4b.env`' \
  "type/feature,area/deploy,priority/P0" \
  "M2 LLM serving"

create_issue \
  "research(prefilter): fine-tune classifier head on 2000-5000 labeled clinical intents" \
'## Problem
The classifier head needs training data. ADR-0007 budgets 3 weeks of curation.

## Proposal
- Extract 2000-5000 queries from AKU retrospective logs (IRB-approved)
- Label with 42 intents (malaria, TB, HIV, etc.) + binary safety flag
- Train LoRA adapter with Unsloth + TRL
- Cross-validate on held-out 20%
- Target: intent F1 >0.85, safety recall >0.95

## Acceptance
- [ ] Labeled dataset published under `eval/datasets/prefilter_train.jsonl`
- [ ] Training script reproducible: `python -m training.prefilter`
- [ ] Model card in `docs/models/prefilter-v1.md`
- [ ] Adapter uploaded to MinIO
- [ ] Evaluation report shows target metrics met

## Refs
- ADR-0007
- IRB approval: AKU-IRB-2026-0147' \
  "type/research,area/eval,priority/P1" \
  "M2 LLM serving"

# ---------------------------------------------------------------------
# M3 RETRIEVAL
# ---------------------------------------------------------------------

create_issue \
  "feat(retrieval): hybrid dense + BM25 retrieval with RRF fusion" \
'## Problem
ADR-0002 mandates hybrid retrieval in a single SQL query using pgvector for dense and pg_search for BM25.

## Proposal
- Retrieval service under `backend/retrieval/`
- Single SQL CTE combining dense + BM25 with Reciprocal Rank Fusion (k=60)
- Cross-encoder rerank via bge-reranker-v2-m3 on CPU
- Structural metadata filters (ICD-10, section, language)

## Acceptance
- [ ] P50 retrieval latency <200ms, P99 <400ms on 15k-chunk corpus
- [ ] Dense + sparse + rerank scores exposed in response for debugging
- [ ] Structural filters compose in the same query
- [ ] Integration tests cover malaria, TB, pediatric, contraindication queries

## Refs
- ADR-0002
- `env/retrieval.env`' \
  "type/feature,area/retrieval,touches-request-path,priority/P0" \
  "M3 Retrieval"

create_issue \
  "feat(retrieval): cross-encoder reranker with harm-weighted boosting" \
'## Problem
Reranking dramatically improves top-1 accuracy but must respect structural metadata (contraindications are worth boosting).

## Proposal
- `backend/retrieval/reranker.py` wrapping bge-reranker-v2-m3
- Batch size 16, max length 512, CPU inference
- Post-rerank boost: is_contraindication=1.5x, is_pediatric for pediatric query=2x
- Config in `env/retrieval.env`

## Acceptance
- [ ] Reranking adds <100ms to retrieval latency
- [ ] Boosting measurably improves precision@1 in Tier 2 evals
- [ ] Boosting is feature-flagged (off = pure rerank scores)' \
  "type/feature,area/retrieval,touches-request-path,priority/P1" \
  "M3 Retrieval"

create_issue \
  "feat(retrieval): query embedder service with caching" \
'## Problem
Every query is embedded before dense search. Cache on normalized query text to avoid re-embedding repeated queries.

## Proposal
- Query embedder using BGE-M3, matryoshka to 1024 dims
- Normalize: lowercase, strip punctuation, collapse whitespace
- Redis cache, 15-minute TTL, max 10k keys
- Eviction: LRU

## Acceptance
- [ ] Warm cache hit <5ms
- [ ] Cold embedding <150ms on CPU
- [ ] Cache hit rate >30% in production-like load test' \
  "type/feature,area/retrieval,priority/P1" \
  "M3 Retrieval"

# ---------------------------------------------------------------------
# M4 ORCHESTRATOR
# ---------------------------------------------------------------------

create_issue \
  "feat(orchestrator): explicit state machine under 400 lines" \
'## Problem
ADR-0003 mandates an explicit Python state machine, not LangGraph. The file must stay under 400 lines (hook-enforced).

## Proposal
- `backend/app/orchestrator.py` implementing Orchestrator class
- Frozen dataclass PipelineState with one field per stage result
- Pure state-transition methods: `_prefilter`, `_retrieve`, `_generate`, `_strict_review`, `_conformal`
- Every method emits one OTel span (hook-enforced)
- Fails closed on any exception

## Acceptance
- [ ] `orchestrator.py` compiles and types under pyright strict
- [ ] Under 400 lines (hook enforces)
- [ ] Every method has an OTel span (hook enforces)
- [ ] Every method has a unit test with mocked clients
- [ ] Integration test: full pipeline end-to-end against test DB + stub vLLM

## Refs
- ADR-0003
- `skills/afya-sahihi-principal/SKILL.md` §3' \
  "type/feature,area/orchestrator,touches-request-path,priority/P0" \
  "M4 Orchestrator"

create_issue \
  "feat(gateway): FastAPI gateway API with OIDC auth, SSE streaming, rate limits" \
'## Problem
The gateway is the external face. It authenticates clinicians, rate-limits, and streams responses via SSE.

## Proposal
- FastAPI app with Pydantic v2 strict models
- OIDC middleware via Keycloak
- Per-user rate limits (Redis-backed): 30/min, 500/day, burst 10
- SSE endpoint `POST /api/chat` streaming tokens + provenance + conformal set
- Health: `/healthz` (liveness), `/readyz` (checks DB, Redis, vLLM)

## Acceptance
- [ ] OIDC happy path tested with Keycloak container in CI
- [ ] Rate limit exhaustion returns 429 with `Retry-After`
- [ ] SSE stream includes keepalives every 15s
- [ ] Graceful shutdown drains in-flight requests within 15s

## Refs
- `env/gateway.env`' \
  "type/feature,area/backend,touches-request-path,touches-security,priority/P0" \
  "M4 Orchestrator"

create_issue \
  "feat(backend): typed error hierarchy and fail-closed response handler" \
'## Problem
Per SKILL.md §6, every error path must fail closed with a typed exception and a stable user-facing shape.

## Proposal
- `backend/app/errors.py`: PipelineError hierarchy
- API error handler maps each typed error to an appropriate status code
- User-facing messages never include stack traces, SQL, or internal paths
- Every error logged with trace_id before raising

## Acceptance
- [ ] Every error type has a handler test
- [ ] Response body shape `{"error": {"code": "...", "message": "..."}}`
- [ ] No internals leak on any error path (tested with adversarial inputs)' \
  "type/feature,area/backend,touches-security,priority/P0" \
  "M4 Orchestrator"

create_issue \
  "feat(backend): PHI scrubber with local-regex patterns only" \
'## Problem
PHI must be scrubbed before audit write, before logging, before external calls. Scrubber never calls external services (SKILL.md §0).

## Proposal
- `backend/app/validation/phi.py` with patterns for Kenyan IDs, phone, email, patient names, MRNs
- Run before audit write, before every log call, before embedding
- Fails closed: if scrubber raises, the surrounding operation fails

## Acceptance
- [ ] Patterns exhaustive across Kenyan formats (ID, phone, passport, NHIF)
- [ ] Benchmarked under 10ms on 1000-token query
- [ ] Red-team test set with 50 adversarial PHI samples
- [ ] Hook `check_no_phi_in_logs.sh` validates logger usage' \
  "type/feature,area/backend,touches-phi,touches-security,priority/P0" \
  "M4 Orchestrator"

# ---------------------------------------------------------------------
# M5 CONFORMAL
# ---------------------------------------------------------------------

create_issue \
  "feat(conformal): prediction set construction service with 5 nonconformity scores" \
'## Problem
Conformal prediction is the paper contribution and the production trust signal. Set sizes and coverage gaps feed the active learning loop.

## Proposal
Under `backend/conformal/`, implement:
- Five nonconformity scores: NLL, retrieval-weighted, topic-coherence-adjusted, ensemble-disagreement, clinical-harm-weighted
- Split conformal as baseline, weighted CP for covariate shift, adaptive CP for online
- Per-stratum quantile cache in Redis (refreshed nightly)
- Prediction set endpoint returning set + coverage + stratum

## Acceptance
- [ ] Marginal coverage within 3pp of target on held-out test set
- [ ] Per-stratum (language, domain, facility) coverage tracked
- [ ] `clinical_harm_weighted` score measurably reduces catastrophic errors in Tier 2
- [ ] Integration tested with a frozen calibration set for reproducibility

## Refs
- ADR-0007 notes
- `env/conformal.env`
- PhD variables inventory §3' \
  "type/research,area/conformal,touches-request-path,priority/P0" \
  "M5 Conformal"

create_issue \
  "feat(conformal): coverage monitor with drift detection and Prometheus alerts" \
'## Problem
Coverage drift is a deployment-safety signal. If empirical coverage deviates from the target by more than 5pp over a 24h window, on-call pages.

## Proposal
- Rolling coverage calculation per stratum, 24h window
- MMD-based drift detector on nonconformity score distribution
- Prometheus metrics: `afya_sahihi_conformal_coverage_empirical`, `...set_size_mean`, `...drift_mmd`
- Alert rules in `deploy/observability/alerts/conformal.yaml`

## Acceptance
- [ ] Grafana dashboard renders coverage by stratum
- [ ] Synthetic drift injection triggers alert in under 10 minutes
- [ ] Runbook `docs/runbooks/coverage-drift.md` published' \
  "type/feature,area/conformal,area/observability,priority/P1" \
  "M5 Conformal"

# ---------------------------------------------------------------------
# M6 EVAL + LABELING
# ---------------------------------------------------------------------

create_issue \
  "feat(eval): Inspect AI Tier 1 unit evals (500 curated cases)" \
'## Problem
Tier 1 gates every commit. 500 curated query-response pairs with exact-match scoring on key facts (ADR-0006).

## Proposal
- Curate 500 cases with clinician panel
- Key fact extraction: drug, dose, route, frequency, duration
- Inspect AI task in `eval/tier1/golden_set.py`
- CI integration via `run_tier1_evals.sh` hook
- Target runtime: <120s

## Acceptance
- [ ] 500-case dataset committed to `eval/datasets/tier1_golden.jsonl`
- [ ] `inspect eval tier1/golden_set.py` runs in under 120s
- [ ] Pass rate >=95% on current best model
- [ ] CI fails PR if pass rate drops below baseline

## Refs
- ADR-0006
- `env/eval.env`' \
  "type/feature,area/eval,priority/P0" \
  "M6 Eval + Labeling"

create_issue \
  "feat(eval): Tier 2 regression evals with adversarial and code-switched queries" \
'## Problem
Tier 2 is the nightly and pre-deploy gate: 2000 cases with ECE, marginal coverage, set size, topic coherence scoring.

## Proposal
- 2000-case dataset with 30% adversarial rephrasing, 25% EN-SW code-switch, 15% misspellings
- Scorers: ECE, marginal_coverage, set_size, topic_coherence (Inspect AI)
- Thresholds: ECE <= 0.08, coverage dev <= 0.03, set size increase <= 15%
- Runs nightly via k3s CronJob

## Acceptance
- [ ] 2000-case dataset committed
- [ ] Nightly CronJob posts results to Slack
- [ ] Pre-deploy gate blocks promotion on threshold breach
- [ ] Grafana dashboard renders trend for each metric

## Refs
- ADR-0006
- `env/eval.env`' \
  "type/feature,area/eval,priority/P1" \
  "M6 Eval + Labeling"

create_issue \
  "feat(labeling): Streamlit clinician reviewer UI with 5-point rubric" \
'## Problem
Tier 3 is the weekly clinician-in-the-loop review. Clinicians need a fast, low-friction grading UI that shows provenance (section, page, bounding box).

## Proposal
- Streamlit app under `labeling/`
- OIDC-protected, role gate: `clinical_reviewer` or `senior_clinician`
- Queue of 20 assigned cases per week, Redis-backed
- Rubric: accuracy, safety, guideline_alignment, local_appropriateness, clarity (1-5 each)
- PDF provenance viewer with bounding-box highlight

## Acceptance
- [ ] Each reviewer can grade 20 cases per week under 60 minutes total
- [ ] Agreement (Fleiss kappa) computed daily across dual-rated cases
- [ ] Grades persisted to `grades` table with chain-of-custody metadata
- [ ] UI accessible on mobile for bedside use

## Refs
- `env/labeling.env`
- `skills/afya-sahihi-principal/SKILL.md`' \
  "type/feature,area/labeling-ui,priority/P1" \
  "M6 Eval + Labeling"

# ---------------------------------------------------------------------
# M7 OBSERVABILITY
# ---------------------------------------------------------------------

create_issue \
  "feat(observability): OTel Collector + Grafana Tempo for traces" \
'## Problem
End-to-end tracing from browser through orchestrator through vLLM is required for debugging. Every span must carry trace_id and query_id.

## Proposal
- OTel Collector as DaemonSet with OTLP gRPC on 4317
- Grafana Tempo in k3s with S3-backed storage (MinIO)
- Span attribute conventions documented
- Every service instrumented

## Acceptance
- [ ] Trace view shows full request lifecycle across 5+ services
- [ ] Token-level LLM spans linked to Phoenix (below)
- [ ] Retention 30 days verified

## Refs
- `env/observability.env`' \
  "type/feature,area/observability,priority/P1" \
  "M7 Observability"

create_issue \
  "feat(observability): Arize Phoenix for LLM-specific span inspection" \
'## Problem
OTel traces are great for system-level debugging but do not expose token-level LLM internals. Phoenix does.

## Proposal
- Deploy Phoenix in k3s
- Wire vLLM spans to Phoenix via OTel routing
- Dashboard: retrieval quality by query type, generation logprob distribution, prefix cache hit rate

## Acceptance
- [ ] Phoenix UI accessible at https://afya-sahihi.aku.edu/phoenix
- [ ] Every generation request appears as a Phoenix span with token probabilities
- [ ] Retrieval debugging workflow documented' \
  "type/feature,area/observability,priority/P1" \
  "M7 Observability"

create_issue \
  "feat(observability): Prometheus + Alertmanager + Loki + Grafana" \
'## Problem
Metrics, logs, and alerts close the observability triangle.

## Proposal
- Prometheus with 30-day retention, scraping all services and exporters
- Alertmanager routed to Slack (non-urgent) and PagerDuty (urgent)
- Loki with Promtail DaemonSet
- Grafana with OIDC auth, pre-provisioned dashboards for RED, LLM, retrieval, conformal, eval, GPU, infra

## Acceptance
- [ ] All exporters present: node, DCGM, postgres, redis, nginx
- [ ] 7 pre-provisioned dashboards
- [ ] At least 5 alert rules with runbooks linked
- [ ] Logs queryable by trace_id' \
  "type/feature,area/observability,priority/P1" \
  "M7 Observability"

# ---------------------------------------------------------------------
# M8 DEPLOY + FRONTEND
# ---------------------------------------------------------------------

create_issue \
  "feat(deploy): k3s cluster bootstrap + systemd watcher" \
'## Problem
Bootstrap 3-node k3s cluster (ctrl, work-01, work-02) with GitOps via systemd watcher (ADR-0005).

## Proposal
- k3s install on control node with Traefik and Sealed Secrets
- Worker nodes joined with label-based scheduling
- Watcher on `afya-sahihi-deploy-01` polling every 60s
- Overlays: dev, staging, production

## Acceptance
- [ ] `kubectl get nodes` shows 3 Ready
- [ ] Watcher applies a manifest change within 90s of git push
- [ ] Traefik serves TLS on `afya-sahihi.aku.edu`
- [ ] Runbook `docs/runbooks/bootstrap.md` published

## Refs
- ADR-0005
- `deploy/k3s/`
- `deploy/systemd/afya-sahihi-watcher.service`' \
  "type/feature,area/deploy,priority/P0" \
  "M8 Deploy + Frontend"

create_issue \
  "feat(deploy): k3s manifests for every service (retrieval, conformal, audit, prefilter, al-scheduler, eval-runner)" \
'## Problem
The gateway manifest (`10-gateway.yaml`) is the template. Every other service needs a parallel manifest following the same pattern.

## Proposal
Stamp out manifests following `deploy/k3s/10-gateway.yaml` for:
- 11-retrieval.yaml
- 12-conformal.yaml
- 13-audit.yaml
- 14-prefilter.yaml
- 15-ingestion-cronjob.yaml
- 16-eval-runner.yaml
- 17-al-scheduler.yaml
- 20-frontend.yaml
- 21-labeling.yaml

Every manifest includes: ConfigMap, Deployment, Service, ServiceAccount, PodDisruptionBudget, HPA, NetworkPolicy, ServiceMonitor.

## Acceptance
- [ ] All manifests pass `kubeconform --strict`
- [ ] All services schedule and pass readiness on staging
- [ ] Kyverno policies enforce: no hostPath, runAsNonRoot, resource limits set' \
  "type/feature,area/deploy,priority/P0" \
  "M8 Deploy + Frontend"

create_issue \
  "feat(frontend): React 19 clinician chat UI with provenance panel" \
'## Problem
The frontend is the clinician surface. Must be fast on low-bandwidth, support SSE streaming, show citations with page-and-box provenance.

## Proposal
- React 19 + Vite + Tanstack Query + Tailwind
- SSE streaming of tokens, set, provenance
- Provenance panel: click a citation to see the source PDF region
- Prediction set display: "Top answer: X. Also consider: Y, Z (within 90% coverage)"
- Dark/light, English/Swahili, offline banner

## Acceptance
- [ ] Lighthouse score >90 on throttled Moto G4
- [ ] First-token-visible under 2s on staging
- [ ] Accessible: keyboard navigation, screen reader labels
- [ ] Works on Chrome/Safari/Firefox latest

## Refs
- `env/frontend.env`' \
  "type/feature,area/frontend,priority/P1" \
  "M8 Deploy + Frontend"

create_issue \
  "feat(deploy): observability stack k3s manifests" \
'## Problem
OTel, Tempo, Prometheus, Alertmanager, Loki, Grafana, Phoenix need manifests with the same deploy discipline as app services.

## Proposal
Under `deploy/k3s/50-observability/`:
- OTel Collector DaemonSet
- Tempo StatefulSet with PVC
- Prometheus + Alertmanager
- Loki + Promtail DaemonSet
- Grafana with OIDC
- Phoenix Deployment
- Dashboards as ConfigMaps

## Acceptance
- [ ] All services healthy after apply
- [ ] Grafana dashboards pre-loaded from ConfigMaps
- [ ] Alert rules loaded and tested with a synthetic firing alert' \
  "type/feature,area/deploy,area/observability,priority/P1" \
  "M8 Deploy + Frontend"

# ---------------------------------------------------------------------
# M9 ACTIVE LEARNING
# ---------------------------------------------------------------------

create_issue \
  "research(active-learning): acquisition-function scheduler and online deployment" \
'## Problem
Paper P3 requires a production AL loop. Conformal set size drives acquisition; clinicians grade, updates flow back.

## Proposal
- APScheduler-based `al_scheduler` service
- Weekly batch of 20 cases per facility selected by acquisition function
- 30% control arm (random) for causal comparison
- Pre-registration on OSF before deployment
- Online deployment at 2 AKU pilot sites, 3-month window

## Acceptance
- [ ] Acquisition functions implemented: random, uncertainty_entropy, conformal_set_size, coverage_gap, clinical_harm_weighted
- [ ] Control/treatment assignment is opaque to reviewer
- [ ] Coverage improvement per label measurable
- [ ] Pre-registration URL linked in `env/eval.env`

## Refs
- PhD variables inventory §4
- `env/eval.env`' \
  "type/research,area/eval,priority/P2" \
  "M9 Active Learning"

create_issue \
  "research(paper-p1): calibration analysis of MedGemma under distribution shift" \
'## Problem
Paper P1 is the empirical measurement paper (CHIL/FAccT/AAAI target).

## Proposal
- Instrument Afya Sahihi to capture all signals listed in PhD variables inventory §2
- Collect 4,300 queries across source/target/adversarial splits
- Grade ground truth via clinician panel (Fleiss kappa >= 0.7)
- Score: ECE, MCE, ACE, Brier, reliability-diagram area
- Compare against temperature scaling, Platt, histogram binning, ensemble baselines

## Acceptance
- [ ] Paper draft in `docs/papers/p1-calibration/`
- [ ] Reproduce figures from committed data and code
- [ ] Submit to a venue by end of 2026

## Refs
- PhD variables inventory §2' \
  "type/research,area/eval,priority/P2" \
  "M9 Active Learning"

create_issue \
  "research(paper-p2): adaptive conformal prediction for RAG under covariate shift" \
'## Problem
Paper P2 is the methodological contribution (NeurIPS/ICML/AISTATS).

## Proposal
- Implement all 5 nonconformity scores
- Implement weighted CP, adaptive CP, mondrian CP
- Theorem: coverage guarantee for clinical-harm-weighted score
- Experiments: synthetic shift sweeps + real deployment data
- Open-source toolkit released alongside paper

## Acceptance
- [ ] Theorem proof reviewed by one external researcher
- [ ] Experiments reproduce with one command
- [ ] Paper submitted by mid-2027' \
  "type/research,area/conformal,priority/P2" \
  "M9 Active Learning"

echo ""
echo "==> Issues created."
echo ""
echo "==> Summary:"
gh issue list --repo "$REPO" --state open --limit 50
echo ""
echo "==> Done. Open the repo in the browser to verify."
