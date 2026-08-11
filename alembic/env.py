"""
Alembic environment.

Reads the DB URL from `app.config.settings.database_url` so migrations always
target the same database the app talks to — no separate config file to keep
in sync. Metadata is bound to `app.models.Base` so `alembic revision
--autogenerate` sees the User / ChatSession / Turn / BotExecution tables.

Starter-data tables (customers, orders, riders, etc.) are intentionally NOT
in Base.metadata — they're loaded from data/app.db by the seed script and
should stay outside Alembic's world.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.models import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Never trust alembic.ini's sqlalchemy.url — always take runtime URL.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout — useful for reviewing migrations before running."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
