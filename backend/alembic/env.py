"""Alembic environment.

Runs migrations synchronously via psycopg (ADR-0008). The DSN is read from
the `AFYA_SAHIHI_DATABASE_URL` env var so the same `alembic upgrade head`
command works identically on an operator workstation, in CI (with the
Postgres service), and in the k3s one-shot `Job`.

The ADR forbids module-level mutable state; the `context` and `config`
globals below are Alembic's own plumbing and are created fresh per
invocation, not per request.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# SQLAlchemy metadata object is required by Alembic even though we do not
# use the ORM. None is valid: we author migrations as raw SQL, so there is
# no declarative metadata to autogenerate against.
target_metadata = None

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    """Fail fast if the DSN is not set.

    Per SKILL.md §0 and §11, configuration reads the environment once at
    startup and a missing value is a fail-closed error, not a silent default.
    """
    url = os.environ.get("AFYA_SAHIHI_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "AFYA_SAHIHI_DATABASE_URL is not set. Alembic refuses to run "
            "against an unspecified database. Set it and retry."
        )
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting. Used for review of the DDL."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and apply migrations in an explicit transaction."""
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
