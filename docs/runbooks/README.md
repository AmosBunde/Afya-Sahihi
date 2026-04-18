# Afya Sahihi Runbooks

Operational procedures for on-call engineers. Each runbook is scoped to a single
named scenario (bootstrap, rollback, incident response for a given alert). Read
the top of the file before paging anyone — the first three commands are usually
all you need.

## Index

| Runbook | Purpose |
|---------|---------|
| [bootstrap.md](./bootstrap.md) | First-time cluster bootstrap from bare metal to first green canary |
| [ci-branch-protection.md](./ci-branch-protection.md) | Configure CI branch protection and Codecov integration |
| [ci-dependabot.md](./ci-dependabot.md) | Enable Dependabot vulnerability alerts and weekly triage procedure |
| [backup-restore.md](./backup-restore.md) | pgBackRest backup verification and restore rehearsal on standby |
| [vllm-operations.md](./vllm-operations.md) | Start/stop/debug the MedGemma 27B + 4B vLLM servers on the GPU host |
| [coverage-drift.md](./coverage-drift.md) | Triage conformal coverage deviation and MMD drift alerts |

## Authoring guidelines

- Start with a one-paragraph summary: when to use, expected duration, blast radius.
- List prerequisites (access, secrets, dependencies) before any commands.
- Commands must be copy-pasteable. No placeholders without a clearly-flagged `<FILL_ME>` marker.
- Every irreversible step has a pre-flight verification and a rollback section.
- End with a "verify" checklist.
- Link the Grafana dashboards, Prometheus alerts, or log queries that prove each step worked.

Changes to any runbook require review from CODEOWNERS for the affected area.
