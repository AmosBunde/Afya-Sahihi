# ADR-0008: Initial backend data-plane dependency stack

**Status:** Accepted
**Date:** 2026-04-16
**Deciders:** Amos Bunde, initial scaffold for issue #11

## Context

Issue #11 lands the first backend Python code: an Alembic migration that
bootstraps the Postgres 16 schema. Standing up that migration pulls in the
first real backend Python dependencies. This ADR documents the choices so
future changes (adding ORMs, swapping drivers, upgrading Alembic) land
against a written baseline rather than a drift-prone set of imports.

The dependencies introduced by issue #11 are:

| Package             | Version  | Why                                                      |
|---------------------|----------|----------------------------------------------------------|
| `alembic`           | 1.13.2   | Schema migration engine; the only runner we use for DDL. |
| `sqlalchemy`        | 2.0.36   | Alembic depends on SQLAlchemy's metadata layer.          |
| `psycopg[binary]`   | 3.2.3    | Synchronous driver for Alembic (init + migrations).      |
| `asyncpg`           | 0.30.0   | Async driver for the request path (SKILL.md §1, §7).     |
| `pgvector`          | 0.3.6    | Python bindings + Alembic type for `vector` columns.     |
| `pydantic`          | 2.9.2    | Strict models (SKILL.md §1).                             |
| `pydantic-settings` | 2.6.1    | `BaseSettings` reads env (SKILL.md §11).                 |

## Decision

Use **Alembic for migrations, asyncpg on the request path, psycopg only for
Alembic's synchronous needs**. We do not adopt SQLAlchemy ORM; it is a
transitive dependency of Alembic and is not imported from application code.
Every runtime query goes through a repository method backed by raw asyncpg
per SKILL.md §7.

### Runtime vs tooling split

- **Runtime (asyncpg)**: the gateway and downstream services execute every
  query via `asyncpg.Pool`. `SET LOCAL statement_timeout` is mandatory on
  every connection checkout (enforced by `scripts/hooks/check_asyncpg_timeouts.sh`).
- **Tooling (Alembic + psycopg)**: migrations run synchronously from the
  operator's workstation or a one-shot `Job` in k3s. They use `psycopg[binary]`
  because Alembic's ecosystem is sync-first and we gain nothing by forcing
  asyncpg through it.

### Why not asyncpg for Alembic

Asyncpg does not expose a DBAPI; Alembic's `run_migrations_online` expects a
DBAPI connection. The async-friendly `alembic ext.asyncio` path exists but
introduces complexity (event loop setup per migration) for no benefit on a
CLI tool that runs a few times per day at most.

### Why psycopg 3 and not psycopg2

Psycopg 2 is feature-complete but in maintenance-only mode upstream. Psycopg
3 is the same project's successor, supports prepared statements natively,
and shares a maintainer with the `asyncpg` community. The `[binary]` extra
installs a prebuilt wheel so we avoid a libpq-dev build-time dependency.

### Pin strategy

All versions are pinned **exact**. SKILL.md §13 forbids `^` or `~` ranges
for anything on the request path. Dependabot opens weekly PRs grouped by
ecosystem; the operator reviews and lands or defers individually per the
ci-dependabot runbook.

## Consequences

### Positive

- One migration tool, one async driver, one sync driver. Clear separation
  of which path runs when.
- No ORM on the runtime path. Raw SQL is readable top-to-bottom.
- Every dep has a pin, so CI is reproducible.

### Negative

- Two drivers in the dep tree (asyncpg + psycopg). Both must be kept
  working against the same Postgres version on upgrade.
- SQLAlchemy is a transitive we do not use directly. A future contributor
  may be tempted to `from sqlalchemy import select`; the review skill §2.1
  explicitly blocks this.

### Neutral

- Alembic is operated via `uv run alembic ...`; the command stays identical
  whether developers use uv or a plain venv.

## Alternatives considered

1. **Raw `psql` + numbered `*.sql` files**: simpler, but loses Alembic's
   dependency-graph + online-migration support. The rollback story for a
   multi-step migration becomes manual.
2. **Django-style migrations with SQLAlchemy declarative**: couples the
   schema to the ORM, which we explicitly rejected in SKILL.md §13.
3. **asyncpg + custom migration runner**: reinvents Alembic. Not worth the
   maintenance burden for the modest volume of migrations we expect.

## References

- ADR-0002: Postgres 16 with pgvector and pg_search over ChromaDB
- SKILL.md §1 (language/runtime), §7 (repository pattern), §11 (config),
  §13 (deny list)
- Issue #11: feat(schema): bootstrap Postgres 16 with pgvector, pg_search,
  pgcrypto, pg_cron
