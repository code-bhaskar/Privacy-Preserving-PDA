from logging.config import fileConfig
import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.models.base import Base
# Import models to ensure all tables are registered on Base.metadata
import app.models.user
import app.models.consent
import app.models.calendar_event
import app.models.reminder
import app.models.message
import app.models.audit_log
import app.models.model_update

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url") or settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Honour explicit connection passed into config.attributes
    connection = config.attributes.get("connection", None)

    if connection is not None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        configuration = config.get_section(config.config_ini_section) or {}
        configuration["sqlalchemy.url"] = settings.DATABASE_URL
        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as conn:
            context.configure(
                connection=conn,
                target_metadata=target_metadata,
            )

            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
