from logging.config import fileConfig

from geoalchemy2 import alembic_helpers
from sqlalchemy import engine_from_config, pool

from alembic import context

# Import settings to get the sync database URL
from civpulse_geo.config import settings

# Import Base and all models to register them with metadata
from civpulse_geo.models.base import Base
from civpulse_geo.models import *  # noqa: F401, F403 — registers all ORM models

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override the database URL with our sync URL from pydantic-settings
# (Alembic requires a synchronous driver; asyncpg is for the app only)
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() here emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # GeoAlchemy2 helpers — required to prevent broken autogenerate migrations
        include_object=alembic_helpers.include_object,
        process_revision_directives=alembic_helpers.writer,
        render_item=alembic_helpers.render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    Uses the synchronous psycopg2 driver — asyncpg cannot be used here.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # GeoAlchemy2 helpers — required to prevent broken autogenerate migrations
            include_object=alembic_helpers.include_object,
            process_revision_directives=alembic_helpers.writer,
            render_item=alembic_helpers.render_item,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
