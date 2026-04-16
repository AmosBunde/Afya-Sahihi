# Runbook: Dependabot activation and triage

**When to use**: on first repo setup to enable vulnerability alerts and
automated security updates, and weekly to triage the batch of Dependabot
PRs that lands Monday 06:00 Africa/Nairobi.

**Blast radius**: toggles are repo-wide. Enabling alerts cannot leak private
information but disabling them silently hides CVE data. Merging a Dependabot
PR that upgrades a load-bearing dependency can break CI; review like any
other PR — the changelog is not a substitute for the test suite.

**Who runs this**: repository admin for §1. Any maintainer for §2.

## 1. One-time admin setup

Dependabot opens update PRs on its own schedule as soon as
`.github/dependabot.yml` is on `main`. GitHub-side vulnerability alerts
and automated security fixes are separate toggles that default to off.

```bash
# Enable vulnerability alerts (GitHub surfaces CVE warnings in PRs and
# the Security tab)
gh api --method PUT \
  /repos/AmosBunde/Afya-Sahihi/vulnerability-alerts

# Enable automated security fixes (Dependabot opens CVE-fix PRs without
# waiting for the weekly schedule)
gh api --method PUT \
  /repos/AmosBunde/Afya-Sahihi/automated-security-fixes
```

Verify:

```bash
# 404 with message "Vulnerability alerts are disabled." means off.
# 204 No Content means on.
gh api /repos/AmosBunde/Afya-Sahihi/vulnerability-alerts
```

## 2. Weekly triage (Monday morning)

Dependabot opens PRs grouped by ecosystem and update type. The repo's
`dependabot.yml` batches:

- `security-updates` — one PR covering every CVE fix across packages.
- `minor-and-patch` — one PR per ecosystem grouping minor and patch bumps.
- `major` (github-actions only) — one PR per major bump because each
  deserves an individual review.

Expected cadence: 1–4 PRs per Monday. A week with more than 4 Dependabot
PRs usually means `dependabot.yml` grouping has broken; check the CI job
log.

### Triage order

1. **Security updates first.** If a `security-updates` PR exists, review
   and merge it the same day unless the upgrade is known to break CI.
2. **Minor-and-patch next.** Group review — if CI is green, merge. The
   `check_adr_for_new_dep.sh` hook fires on any `+` line in
   `backend/pyproject.toml` / `backend/requirements.txt`, so an upgrade PR
   that changes a pinned version will still require an ADR-related
   justification in the PR body. For patch-only bumps, write
   `NO-ADR-NEEDED: version bump within existing ADR window` in the body
   to document the rationale.
3. **Major bumps individually.** Each one gets a full review. Link the
   upstream changelog and the ADR that originally justified the dependency.

### Expected labels on every Dependabot PR

The `actions/labeler@v5` in `pr-automation.yml` applies labels by changed
path:

- `backend/pyproject.toml` / `backend/requirements.txt` → `area/backend`,
  `needs-adr`
- `frontend/package-lock.json` → `area/frontend`
- `.github/workflows/*.yml` → `area/ci`
- `backend/Dockerfile` → `area/deploy`, `touches-security`

The `needs-adr` label fires on every pip-ecosystem Dependabot PR because
the underlying file changed. That is intentional; the PR reviewer should
either cite an existing ADR or mark it NO-ADR-NEEDED as described above.

## 3. Ignored packages

Some packages are pinned for operational reasons; Dependabot will not
open upgrade PRs for them. See `.github/dependabot.yml`:

- `vllm` — pinned for H100 stability; upgrades require planned maintenance.
- `pydantic` — no major-version bumps (v2 API stable).
- `inspect-ai` — no major or minor bumps (reproducibility of eval results).

When any of these needs an upgrade, open a manual PR and link the
reproducibility justification in the body.

## Verify checklist

- [ ] `gh api /repos/AmosBunde/Afya-Sahihi/vulnerability-alerts` returns
      HTTP 204 (enabled).
- [ ] `Security → Dependabot` in the GitHub UI lists zero open alerts OR
      an open PR addressing each.
- [ ] Weekly Dependabot PR count ≤ 4; if higher, grouping is broken.
- [ ] Every Dependabot PR has an assigned reviewer (auto-assigned via
      `reviewers: [AmosBunde]` in `dependabot.yml`).
