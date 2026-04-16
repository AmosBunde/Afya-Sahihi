# Runbook: configure CI branch protection and Codecov

**When to use**: after the CI workflow (`.github/workflows/ci.yml`) is stable
enough that every check passes or cleanly skips on a trivial PR. Until then,
enabling required status checks would block every PR while the scaffolding
catches up.

**Blast radius**: affects merges to `main`. Incorrect settings can block all
merges (safe-fail) or let unchecked PRs land (safety hole). Verify both ways
on a throwaway PR before declaring done.

**Who runs this**: repository admin. The `gh` commands below require a token
with the `repo` scope on `AmosBunde/Afya-Sahihi`.

## 1. Required status checks

The checks that must be green before merge to `main`:

| Check name (from the workflow) | Gate reason |
|---|---|
| `Preflight — detect repo layout` | detects which sub-components exist; downstream jobs key off its outputs |
| `Hygiene & hooks` | pre-commit + custom hook unit tests |
| `Gitleaks secret scan` | catches committed secrets |
| `SAST (Semgrep + Bandit + CodeQL)` | static analysis |
| `Dependency audit` | pip-audit + npm audit (self-skips pre-backend) |
| `Backend unit + integration` | pytest + coverage (self-skips pre-backend) |
| `Tier 1 evals (Inspect AI)` | golden-set regression (self-skips pre-M6) |
| `Frontend lint + typecheck + tests` | self-skips until #35 lands |
| `Validate k3s manifests` | kubeconform + kyverno |

`Container build + vulnerability scan` is intentionally omitted — it only
runs on `push` after merge, so it cannot be a merge gate.

Enable via `gh`:

```bash
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  repos/AmosBunde/Afya-Sahihi/branches/main/protection \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=Preflight — detect repo layout' \
  -f 'required_status_checks[contexts][]=Hygiene & hooks' \
  -f 'required_status_checks[contexts][]=Gitleaks secret scan' \
  -f 'required_status_checks[contexts][]=SAST (Semgrep + Bandit + CodeQL)' \
  -f 'required_status_checks[contexts][]=Dependency audit' \
  -f 'required_status_checks[contexts][]=Backend unit + integration' \
  -f 'required_status_checks[contexts][]=Tier 1 evals (Inspect AI)' \
  -f 'required_status_checks[contexts][]=Frontend lint + typecheck + tests' \
  -f 'required_status_checks[contexts][]=Validate k3s manifests' \
  -f 'enforce_admins=true' \
  -f 'required_pull_request_reviews[required_approving_review_count]=1' \
  -f 'required_pull_request_reviews[dismiss_stale_reviews]=true' \
  -f 'required_pull_request_reviews[require_code_owner_reviews]=true' \
  -f 'restrictions=' \
  -f 'allow_force_pushes=false' \
  -f 'allow_deletions=false' \
  -f 'required_linear_history=true'
```

A job that self-skips via a preflight-output `if:` is reported by GitHub as
status `neutral`, which branch protection treats as success. This is why
the checks above can all be marked required today even though most of them
are no-ops until the relevant issue lands.

## 2. Codecov integration

The `backend-tests` job uploads `backend/coverage.xml` via `codecov/codecov-action@v4`.
For public repos this works token-less; for private, set `CODECOV_TOKEN` in
repo secrets:

```bash
gh secret set CODECOV_TOKEN \
  --repo AmosBunde/Afya-Sahihi \
  --body "$(op read op://afya-sahihi/codecov/upload_token)"
```

Then verify:

```bash
gh workflow run ci.yml --ref main
# Wait for backend-tests to finish, then check:
open https://app.codecov.io/gh/AmosBunde/Afya-Sahihi
```

## 3. SARIF uploads

`SAST` uploads `bandit.sarif` (under category `bandit`); `container-build`
uploads `trivy-<service>.sarif` (category `trivy-<service>`). Both land in
`Security → Code scanning` on the repo. No admin action needed; the
`security-events: write` permission in the workflow is sufficient.

## Verify checklist

- [ ] A trivial docs-only PR completes with every required check green or
      cleanly skipped — no red checks.
- [ ] A PR that deliberately adds `print("x")` to a backend Python file is
      blocked by `Hygiene & hooks`.
- [ ] `Security → Code scanning` shows Bandit and Trivy results after a
      post-merge `push` run.
- [ ] `https://app.codecov.io/gh/AmosBunde/Afya-Sahihi` displays a coverage
      trend for the most recent `backend-tests` run.
- [ ] Direct push to `main` is rejected with "branch protection rule".
