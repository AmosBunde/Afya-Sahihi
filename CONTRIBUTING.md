# Contributing to Afya Sahihi

Thank you for considering a contribution. Because this system supports clinical decision-making in a production setting, the bar for changes is high. This document explains what that bar looks like in practice.

If after reading this you are not sure whether your change is welcome, open an issue first and we will discuss it.

---

## Before you start

1. Read the top-level `README.md`.
2. Read `skills/afya-sahihi-principal/SKILL.md`. It is the engineering playbook.
3. If you are reviewing a PR, also read `skills/afya-sahihi-review/SKILL.md`.
4. Skim the ADRs under `docs/adr/`. Knowing the existing decisions helps you avoid duplicating them.

---

## One-time setup per clone

```bash
git clone git@github.com:AmosBunde/Afya-Sahihi.git
cd Afya-Sahihi

# Install Python 3.12 and uv if you do not have them.
# macOS: brew install python@3.12 uv
# Linux: see https://docs.astral.sh/uv/

# Install pinned dev tooling and activate all hook types.
# The wrapper installs pre-commit + detect-secrets at the exact versions
# CI uses (see tools/requirements-dev.txt), then wires up the three hook
# types the repo expects (pre-commit, pre-push, commit-msg).
scripts/dev_install.sh

# Install backend dependencies
cd backend
uv sync --all-extras

# Install frontend dependencies
cd ../frontend
npm ci
```

After this, every commit and push is gated by the hooks. If a hook blocks you, read its message carefully before reaching for `--no-verify`.

---

## Opening an issue

Pick the right template:

- **Feature** — a new capability. Requires acceptance criteria.
- **Bug** — something broken. Requires reproduction steps.
- **ADR proposal** — a decision that changes architecture. Open this issue *before* writing the ADR PR.

If the issue involves PHI or security, do not use GitHub. See `SECURITY.md`.

---

## Branching

- Branch from `main`.
- Naming:
  - `feat/<area>-<short-description>` for features
  - `fix/<short-description>` for bugfixes
  - `adr/<nnnn>-<title>` for ADRs
  - `chore/<short-description>` for maintenance
  - `docs/<short-description>` for documentation

Keep branches short-lived. A branch alive for more than a week usually indicates a PR that should have been split.

---

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/). The `commit-msg` hook enforces this.

Format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`, `security`.

Subject: imperative, lowercase, no trailing period. Under 72 characters.

Good examples:

```
feat(orchestrator): add strict review stage for dosing queries
fix(retrieval): correct RRF constant in hybrid fusion
docs(adr): record decision to prefer Postgres over ChromaDB
security(audit): scrub MRN from log format string
```

Body: the "why", not the "what". The diff already shows what.

Footer: reference issues (`Closes #123`, `Refs #456`) and any breaking-change marker (`BREAKING CHANGE: ...`).

---

## Pull requests

### Size

PRs over 1,000 changed lines are rejected by automation. Aim for under 400 lines. A 50-line PR is reviewable in 10 minutes; a 500-line PR requires an hour of focused attention.

If your change is genuinely large, split it across multiple PRs stacked on each other. The first PR lands the scaffolding, the second adds behavior, the third adds tests, and so on.

### Description

Use the PR template. It has five sections the author fills out and a reviewer checklist we both use.

Required:

- A one-paragraph summary answering "what" and "why"
- A link to the issue or ADR this PR addresses
- A test plan (what you ran locally, what the CI will verify)
- Deployment notes (new env var? new migration? new secret?)

### CI must be green

Every PR runs:

- Pre-commit hooks on all files
- Gitleaks secret scan
- Semgrep, Bandit, CodeQL, Trivy (SAST)
- pip-audit, npm audit (dependency audit)
- Backend unit + integration tests
- Tier 1 Inspect AI evals
- Frontend lint + typecheck + tests
- Container build + Trivy vuln scan
- k3s manifest validation via kubeconform

If any check fails, fix it. Do not merge with failing checks.

### Review process

CODEOWNERS automatically requests reviewers. Expect at least one review before merge.

If you touch any of these, expect extra scrutiny:

- Orchestrator (`backend/app/orchestrator.py`)
- Request path (`backend/app/api/`, `backend/app/clients/`)
- Auth / security (`backend/app/validation/`, `.github/workflows/`)
- Data layer (`backend/alembic/`, `backend/app/repository/`)
- Conformal prediction (`backend/conformal/`)

Reviewers use `skills/afya-sahihi-review/SKILL.md`. Their checklist is:

1. Does every external call have a timeout?
2. Does every error path fail closed?
3. Does every state transition log a structured event with `query_id` (not `query_text`)?
4. Is there a test that exercises the new code path?
5. Does the change pass Tier 1 evals?
6. Is any new env var added to `env/` AND `backend/app/settings.py`?
7. Is any new dependency accompanied by an ADR?
8. Does any log statement include PHI? (Hook catches most; reviewer double-checks.)
9. Does any new import add LangChain/LangGraph/LlamaIndex to the request path? (Forbidden.)
10. Are tests deterministic and fast?

### Merging

We rebase-merge. We do not squash. Keep your commits atomic so the history is useful.

---

## Code style

### Python

- Python 3.12 only.
- `uv` for dependency management.
- Ruff for lint and format. Pyright strict for types.
- Pydantic v2 strict mode for all models.
- Raw asyncpg for database access. No ORMs on the request path.
- No LangChain/LangGraph on the request path (ADR-0003).

### TypeScript

- TypeScript strict mode.
- ESLint with `@typescript-eslint/strict` preset.
- No `any`. If you need it, justify it in a comment and file a cleanup issue.
- React 19 with function components only. No class components.

### SQL

- sqlfluff on all migrations.
- Every migration is reversible. If you cannot write a `downgrade`, split the migration.
- Schema changes always get an ADR if they change data contracts.

### YAML

- yamllint with our config (`.yamllint.yaml`).
- Kubernetes manifests validated by kubeval on pre-commit.

### Shell

- Bash, not sh. `#!/usr/bin/env bash`.
- `set -euo pipefail` at the top of every script.
- Shellcheck clean.

---

## Testing

A PR without tests is not mergeable.

- **Unit tests** live next to the module. Mock external clients. Run in under 100ms each.
- **Integration tests** use testcontainers for Postgres and httpserver for stubbed vLLM.
- **Eval tests** (Inspect AI) are a separate category. Changes to retrieval, conformal, or generation must pass Tier 2.

### How to run tests

```bash
# Backend unit + integration
cd backend
uv run pytest tests/unit -v
uv run pytest tests/integration -v

# Tier 1 evals (must pass in under 120 seconds)
cd ../eval
uv run inspect eval tier1/golden_set.py --model afya-sahihi

# Frontend
cd ../frontend
npm run lint
npm run typecheck
npm test -- --run
```

---

## Adding a new dependency

Short answer: do not, unless you open an ADR in the same PR.

The `check_adr_for_new_dep.sh` hook will block a push that changes `pyproject.toml` or `requirements.txt` without a corresponding ADR. This is deliberate. Every dependency is a security, operational, and maintenance liability. We accept those only with deliberation.

Template for a dependency ADR: `docs/adr/NNNN-add-<package>.md`. Use the same format as existing ADRs. Justify:

- Why we need it
- What we considered instead (at least two alternatives)
- What maintenance cost we accept
- Who will own upgrades

---

## Documentation

If your change affects:

- **Behavior** observable to a clinician → update `README.md` and relevant runbooks
- **Public API surface** → update `docs/api/` and the OpenAPI schema
- **Architecture** → add an ADR
- **On-call response** → update or add a runbook

Documentation changes go through the same PR review process as code.

---

## Escalation

If a reviewer and author disagree after two round trips, escalate:

- Architecture disputes → open an ADR
- Security disputes → loop in `security@aku.edu`
- Clinical correctness disputes → loop in `clinical-safety@aku.edu`

It is better to pause a PR for a decision than to merge a compromise that neither side is happy with.

---

## Licensing

By opening a PR, you agree that your contribution is licensed under Apache 2.0 (see `LICENSE`).

If you include code from another source, preserve the original license notice and call out the source in your PR description.
