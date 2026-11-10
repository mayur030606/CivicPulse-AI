"""Alembic environment for CivicPulse AI.

The database URL comes from the application settings (``DATABASE_URL`` or the
``DB_*`` fallback), never from ``alembic.ini``.
"""

from logging.config import fileConfig

from alembic import context

from app.core.config import get_settings
from app.database import Base, engine
from app import models  # noqa: F401  (register model metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = get_settings()
    context.configure(
        url=settings.sqlalchemy_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
