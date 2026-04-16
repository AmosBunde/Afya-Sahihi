# Afya Sahihi Runbooks

Operational procedures for on-call engineers. Each runbook is scoped to a single
named scenario (bootstrap, rollback, incident response for a given alert). Read
the top of the file before paging anyone — the first three commands are usually
all you need.

## Index

| Runbook | Purpose |
|---------|---------|
| [bootstrap.md](./bootstrap.md) | First-time cluster bootstrap from bare metal to first green canary |

## Authoring guidelines

- Start with a one-paragraph summary: when to use, expected duration, blast radius.
- List prerequisites (access, secrets, dependencies) before any commands.
- Commands must be copy-pasteable. No placeholders without a clearly-flagged `<FILL_ME>` marker.
- Every irreversible step has a pre-flight verification and a rollback section.
- End with a "verify" checklist.
- Link the Grafana dashboards, Prometheus alerts, or log queries that prove each step worked.

Changes to any runbook require review from CODEOWNERS for the affected area.
