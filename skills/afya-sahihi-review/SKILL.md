---
name: afya-sahihi-review
description: Code-review playbook for Afya Sahihi pull requests. Use when reviewing any PR against the Afya Sahihi repository. Covers security review, tight coupling detection, secure code patterns, async discipline, and test adequacy. This skill encodes the review bar that the pre-commit hooks cannot enforce on their own.
---

# Afya Sahihi — Code Review Skill

This skill guides human and AI reviewers of pull requests. It pairs with the automated hooks: hooks catch the mechanical failures, this skill covers everything else.

The review bar is higher than a typical SaaS codebase because an incorrect response from this system can harm a patient. A reviewer who hesitates to block a PR is failing the patient, not the author.

---

## 0. Before reading the diff

Read, in order:

1. The PR description. If it is empty or just a title, request a rewrite. A PR without a "why" is a PR without a review.
2. The linked issue or ADR.
3. `docs/skills/afya-sahihi-principal/SKILL.md` §0 (the non-negotiables) if you have not read it in the last week.
4. The files changed. Read the tests before the implementation.

If any of those four are missing, block the PR and say what is needed.

---

## 1. Security review

### 1.1 Data handling

- [ ] **PHI never leaves AKU-controlled hardware**. Any new external HTTP call is a red flag. Read the URL target. If it resolves outside the AKU network, block the PR and ask why.
- [ ] **Query text is never logged.** The logger calls must include `query_id`, `query_length_tokens`, `query_language_detected`. They must never include `query_text` or anything derived from it.
- [ ] **PHI scrubber runs before the audit write, not after.** Check that the call order is validate → scrub → write, never write → scrub. If the order is wrong, block.
- [ ] **Every new database column is evaluated for PHI-ness.** If the column might carry PHI, it must be encrypted at rest via `pgcrypto` and flagged in the schema documentation.
- [ ] **Structured logging keys are on the allow-list.** Confirm the new log call uses only approved keys (see `backend/app/observability/logging.py::ALLOWED_KEYS`).

### 1.2 Authentication and authorization

- [ ] **New endpoints check auth.** Every new FastAPI route has a `Depends(auth)` or an explicit `public=True` marker. Public endpoints require justification in the PR description.
- [ ] **Role checks use the `requires_role` helper**, not raw `if user.role == ...` checks. The helper logs denials; raw checks do not.
- [ ] **Export and admin actions require two-person approval.** Changes to the audit export endpoint or anything in `backend/app/admin/` must preserve the dual-approval pattern.
- [ ] **JWT audience is validated.** Look for `audience=` in any new OIDC client usage. A JWT without audience validation is a bearer token anyone can forge.

### 1.3 Secret handling

- [ ] **No secrets in the diff.** gitleaks will catch most, but review the `env/` changes for anything suspicious. If you see a string that looks like a key, assume it is.
- [ ] **New secrets use SealedSecret** in `deploy/k3s/40-sealed-secrets/`, not plain `Secret`.
- [ ] **LoadCredential** is used on bare-metal systemd units, not `Environment=`.
- [ ] **No secrets in logs, spans, or error messages.** Read every `logger.info(f"...{...}...")` carefully.

### 1.4 Supply chain

- [ ] **New dependency has an ADR.** Run `git diff --cached backend/pyproject.toml`. Any added package needs a corresponding `docs/adr/` file in the same PR. The hook enforces this on push but not on draft PRs.
- [ ] **Dependency is actively maintained.** Look at the package's GitHub: last commit within 6 months, no archived flag, no known CVEs in the current version.
- [ ] **Pin is exact.** `httpx = "0.27.0"`, not `httpx = "^0.27"` for any package that touches the request path.

### 1.5 Input validation

- [ ] **Every Pydantic model uses `strict=True, frozen=True`.**
- [ ] **Every string field has a `max_length`.**
- [ ] **Numeric fields have bounds.** `ge=`, `le=`.
- [ ] **Timestamps are timezone-aware.** `datetime.now(timezone.utc)`, never `datetime.now()` or `datetime.utcnow()`.
- [ ] **SQL is parameterized.** No `f"SELECT ... {user_input}"`. Ever.

### 1.6 Cryptographic primitives

- [ ] **No custom crypto.** If the diff touches `hashlib`, `hmac`, `cryptography`, or `secrets`, triple-check the intent. Prefer library helpers over hand-rolled patterns.
- [ ] **Password hashing uses argon2id or bcrypt.** Never SHA-256.
- [ ] **CSRF tokens have at least 32 bytes of entropy.**

---

## 2. Tight coupling detection

Tight coupling is the hidden enemy of a system that needs to evolve under research pressure. Watch for:

### 2.1 Cross-module reaches

- [ ] **No module imports another module's internals.** `from app.retrieval._internal import ...` is a bug. If it is needed, promote the symbol to the public API of the importee first.
- [ ] **No downstream module imports an upstream orchestrator class.** The orchestrator imports clients; clients never import the orchestrator.
- [ ] **Repository layer is the only path to the database.** No service calls `asyncpg` directly. If a new service does, block and ask for a repository method.

### 2.2 Shared mutable state

- [ ] **No module-level mutable objects** except for loggers, tracers, and constants. No module-level dicts, lists, caches, or feature-flag overrides.
- [ ] **Settings are injected, not imported.** `def foo(settings: Settings):`, not `from app.settings import settings`. The `settings` global exists only at application factory scope.
- [ ] **Clients are constructed once.** A new `httpx.AsyncClient()` inside a function body is almost always a bug. It should be a singleton at app startup.

### 2.3 Configuration sprawl

- [ ] **New behavior toggles go through the feature flag system**, not through raw `Settings` booleans scattered across modules. If the code reads `settings.feature_foo_enabled` in four places, extract a `FeatureGate`.
- [ ] **New env var is documented.** Present in `env/<service>.env`, `backend/app/settings.py`, and the relevant Kubernetes ConfigMap.

### 2.4 Data coupling

- [ ] **JSONB columns have a Pydantic schema.** If a new JSONB blob is written without a validation model, block. We have been burned by schema drift inside JSONB.
- [ ] **Cross-table joins cross service boundaries with explicit contracts.** A query that joins `queries_audit` with `grades` needs a documented contract about the grade-to-query relationship.
- [ ] **Wire formats are versioned.** The SSE response carries a `schema_version`. Changes to that schema require a new version, never a silent shape change.

### 2.5 Temporal coupling

- [ ] **No ordering assumptions in concurrent code.** If two `asyncio.create_task` calls must complete in a specific order, block and ask for `TaskGroup` with explicit dependency.
- [ ] **No sleep-based synchronization.** `asyncio.sleep(1)` to wait for something is always wrong. Use an event or a condition.

---

## 3. Secure code patterns

### 3.1 Error handling

- [ ] **Every `except` catches a specific exception type.** `except Exception` is a red flag unless paired with a re-raise.
- [ ] **Errors fail closed.** In the orchestrator, an exception in any stage produces a refusal response with provenance metadata. It never returns a partial success.
- [ ] **Errors do not leak internals.** The API returns a stable error shape: `{"error": {"code": "...", "message": "..."}}`. The message must never include a file path, stack trace, or SQL.
- [ ] **Errors are logged before being raised.** The logger captures context the caller will not.

### 3.2 Resource cleanup

- [ ] **Every `await`-able resource is in an `async with` or has a `finally` cleanup.** Database connections, HTTP clients, file handles, task groups.
- [ ] **Streams are closed on cancellation.** SSE streams must have a `finally` that closes the queue.

### 3.3 Deserialization safety

- [ ] **No `pickle` on untrusted input.** Ever.
- [ ] **No `eval`, `exec`, or `compile` on user input.** Ever.
- [ ] **YAML load uses `yaml.safe_load`,** never `yaml.load` without a loader.
- [ ] **JSON bodies are parsed through Pydantic strict models,** not `json.loads` directly.

### 3.4 Integer and size limits

- [ ] **Every loop over user input has a bound.** `for item in request.items` without `len(request.items) < MAX_N` is a DoS vector.
- [ ] **File uploads have a size cap enforced at the ingress layer.** Traefik middleware, not application code.
- [ ] **Pagination is opaque cursor-based**, not `OFFSET/LIMIT`. Deep pagination on indexed tables is DoS-able.

### 3.5 Path traversal

- [ ] **Any filesystem access with a user-controlled component uses `pathlib.Path.resolve()` and checks the prefix.** A bare `open(user_path)` is a bug.

---

## 4. Async discipline

### 4.1 Cancellation

- [ ] **Critical sections are shielded.** If a piece of code must complete once started (e.g. audit write), it is wrapped in `asyncio.shield` or equivalent. The author must justify the shield.
- [ ] **Cancellation is not swallowed.** `except asyncio.CancelledError: pass` is almost always a bug. It should re-raise.
- [ ] **No `asyncio.wait_for` without a matching timeout.** The timeout value must come from settings, not a magic number.

### 4.2 Concurrency primitives

- [ ] **TaskGroup is used for parallel work**, not `gather`. `gather` swallows exceptions in surprising ways.
- [ ] **No bare `create_task`.** Every `create_task` either attaches a done-callback or lives inside a TaskGroup.
- [ ] **Locks are never held across an `await`.** This is the single most common async bug pattern.
- [ ] **Event loop is never blocked.** No `time.sleep`, no synchronous file I/O, no `requests` library.

### 4.3 Backpressure

- [ ] **Queues are bounded.** `asyncio.Queue()` without `maxsize` is unbounded memory growth.
- [ ] **Concurrent HTTP has a semaphore.** If the code calls an external service in a loop, it uses `asyncio.Semaphore` to cap parallelism.
- [ ] **Retries use exponential backoff with jitter**, not a fixed sleep.

### 4.4 Streaming

- [ ] **SSE endpoints send keepalives.** Traefik drops idle connections at 30s.
- [ ] **SSE endpoints handle client disconnect.** The server stops generating tokens when the client goes away. Check for `await request.is_disconnected()` or equivalent.
- [ ] **Every chunk emitted includes the schema_version.**

---

## 5. Test adequacy

A PR without tests is a PR that cannot be reviewed.

### 5.1 Unit tests

- [ ] **Every new function has a test.** Including private helpers if they are non-trivial.
- [ ] **Every branch is covered.** If the function has a guard clause, the test exercises the failure case.
- [ ] **Mocks are minimal.** Prefer faking (a small in-memory substitute) over mocking (assert-based patching).
- [ ] **Parametrized tests are used for edge cases.** English, Swahili, code-switched, empty, max length.

### 5.2 Integration tests

- [ ] **Any PR that touches the request path has an integration test** that runs against the real Postgres (testcontainers) and a stubbed vLLM (httpserver).
- [ ] **Integration tests use a fresh database per test.** No test depends on another's state.
- [ ] **Integration tests verify the audit log row** for every query they issue. If the audit row is missing, the test fails.

### 5.3 Eval tests

- [ ] **Changes to retrieval, conformal, or generation trigger Tier 2 evals** in CI. The reviewer checks the linked Tier 2 report.
- [ ] **Coverage and set size stay within thresholds.** A change that improves accuracy but blows out set size is a problem. The author must explain the trade-off.

### 5.4 Regression tests for fixed bugs

- [ ] **Every bug fix has a test that fails without the fix.** If the fix landed without such a test, block and ask for one.

### 5.5 Test quality

- [ ] **Assertions test behavior, not implementation.** `assert result.set_size < 5`, not `assert mock_client.call_count == 3`.
- [ ] **Tests are deterministic.** No reliance on ordering of dict iteration, no reliance on system time, no sleeps.
- [ ] **Tests are fast.** A single unit test takes under 100ms. If it does not, it is probably an integration test misfiled.
- [ ] **Tests have clear names.** `test_prefilter_rejects_low_topic_score`, not `test_prefilter_1`.

---

## 6. Reviewer communication

### 6.1 How to leave a comment

- Be specific. "This is wrong" is not a review. "This violates ADR-0003 because the import adds LangChain to the request path; see §2 of the ADR" is a review.
- Tag severity. `(nit)` for style, `(question)` when unsure, `(blocking)` when the PR must not merge.
- Propose a fix, not just a problem. A review that only identifies bugs is half a review.
- Cite the ADR, SKILL.md, or runbook that supports your comment. Reviews backed by written policy are harder to argue with.

### 6.2 When to block

Block the PR if any of:

- A non-negotiable from SKILL.md §0 is violated.
- The PR would expose PHI to an external service.
- The PR adds a dependency without an ADR.
- Tests are absent or inadequate.
- The PR touches the request path but lacks OTel spans.
- The PR removes a security control without a superseding ADR.

### 6.3 When to approve

Approve when:

- You understand every line you are approving.
- The author has addressed every blocking and question-level comment.
- CI is fully green.
- The PR checklist is filled in.
- The relevant ADR exists, if required.

If you do not understand a line, you do not approve. "I trust the author" is not a review.

### 6.4 When to escalate

Escalate to a second reviewer or the principal if:

- The change touches the conformal prediction layer or any PhD-sensitive experimental surface.
- The change touches IRB or audit compliance.
- The change is larger than 500 lines of meaningful code (hook will warn, this is a second gate).
- You and the author disagree after two round trips.

---

## 7. Reviewer quick-reference

The minimum pass for a PR touching the request path:

1. PR description: problem, change, tests. Three paragraphs at most.
2. Linked issue or ADR.
3. Every non-negotiable honored.
4. Tests present and pass.
5. Tier 1 evals green. Tier 2 green if retrieval/conformal/generation changed.
6. Checklist in PR template fully checked.
7. No PHI in logs.
8. No new coupling between modules that did not already talk.
9. Every external call has a timeout.
10. Every state transition emits a span.

If all ten, approve. If any one fails, block and explain which.

---

*Last updated: 2026-04-16. Changes to this skill require an ADR.*
