from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.core.config import settings
from app.db import models  # noqa: F401  (registers the mappings)
from app.db.base import QUANT_SCHEMA, WEB_SCHEMA, Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# The ingestion pipeline owns `public`; migrations here must never touch it.
MANAGED_SCHEMAS = {WEB_SCHEMA, QUANT_SCHEMA}


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    schema = getattr(obj, "schema", None)
    if type_ == "table":
        return schema in MANAGED_SCHEMAS
    if type_ == "index" and getattr(obj, "table", None) is not None:
        return obj.table.schema in MANAGED_SCHEMAS
    return True


def _configure(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object,
        compare_type=True,
        version_table_schema=WEB_SCHEMA,
    )


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_object=include_object,
        version_table_schema=WEB_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    # Alembic writes its version table into WEB_SCHEMA, and it does so before
    # the first revision runs. On a fresh database that schema does not exist
    # yet, so create it here. Revision 0001 repeats this with IF NOT EXISTS,
    # which keeps both paths idempotent.
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{WEB_SCHEMA}"'))
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
