# Pull Request — Afya Sahihi

## Summary

<!-- One paragraph. What does this PR do, and why? If it changes behavior, say so plainly. -->

## Related

- Issue: #
- ADR (if applicable): `docs/adr/XXXX-<title>.md`
- Runbook (if applicable): `docs/runbooks/<name>.md`

---

## Reviewer Checklist (the reviewer fills this out, not the author)

### Correctness

- [ ] Does every external call have an explicit timeout?
- [ ] Does every error path fail closed (never silently partially-succeed)?
- [ ] Does every state transition log a structured event with `query_id` (not `query_text`)?
- [ ] Is there a unit test that exercises the new code path?
- [ ] Do integration tests pass against the real Postgres + mock vLLM in CI?

### Observability

- [ ] If the change touches the request path, is there an OTel span for each new step?
- [ ] Are new Prometheus metrics named with the `afya_sahihi_` prefix?
- [ ] Do logs use the structured logger (no `print`, no f-string concatenation into the message)?

### Security & coupling review

- [ ] No new import of LangChain / LangGraph / LlamaIndex on the request path (ADR-0003)
- [ ] No new direct database access outside the repository layer
- [ ] No new secrets in plain text (use SealedSecret or systemd credentials)
- [ ] No new service-to-service call that bypasses the Gateway
- [ ] No new synchronous I/O in an async path
- [ ] Bandit / Gitleaks checks clean on CI

### Async discipline

- [ ] Every `await` point considered for cancellation safety
- [ ] No `asyncio.create_task` without attached done-callback or awaited
- [ ] No lock held across an `await`
- [ ] Uses `TaskGroup` for parallel work, not `gather`

### Schema & configuration

- [ ] Any new env var is added to `env/` AND to `backend/app/settings.py`
- [ ] Any new table or column has an Alembic migration, and the migration is reversible
- [ ] Any new dependency has an ADR

### Docs & evals

- [ ] Tier 1 eval pass rate unchanged or higher (CI reports)
- [ ] Tier 2 ECE, marginal coverage, set size all within thresholds (CI reports)
- [ ] If the change modifies retrieval, conformal, or generation, Tier 3 (clinician) grading is scheduled for next cycle
- [ ] Runbooks updated if on-call behavior changes

### Release safety

- [ ] Feature flag gate in place if behavior changes meaningfully
- [ ] Rollback plan clear (revert PR = revert behavior)
- [ ] No breaking change to the SSE wire format without versioning

---

## Author additions

<!-- Delete sections that do not apply. Keep the ones that do. -->

### Test plan

<!-- What did you run locally? -->

### Deployment notes

<!-- Anything SRE should know. New env var? New migration? New secret? -->

### Known trade-offs / follow-ups

<!-- Be honest about what you deferred and why. -->

---

*By opening this PR you confirm that you have read `docs/skills/afya-sahihi-principal/SKILL.md` and that the change complies with its non-negotiables.*
