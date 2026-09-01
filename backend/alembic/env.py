"""Alembic environment for the MeDIAuto PostgreSQL schema."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncConnection, async_engine_from_config

from app.config import settings
from app.postgres.base import Base
from app.postgres.database import normalize_postgres_uri
from app.postgres import models  # noqa: F401


obj_config = context.config
if obj_config.config_file_name:
    fileConfig(obj_config.config_file_name)

target_metadata = Base.metadata


def _postgres_uri() -> str:
    if not settings.POSTGRES_URI:
        raise RuntimeError("POSTGRES_URI is required to run PostgreSQL migrations.")
    return normalize_postgres_uri(settings.POSTGRES_URI)


def run_migrations_offline() -> None:
    context.configure(
        url=_postgres_uri(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(obj_connection) -> None:
    context.configure(
        connection=obj_connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_migrations_online() -> None:
    dict_section = obj_config.get_section(obj_config.config_ini_section) or {}
    dict_section["sqlalchemy.url"] = _postgres_uri()
    obj_connectable = async_engine_from_config(
        dict_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with obj_connectable.connect() as obj_connection:
        obj_connection: AsyncConnection
        await obj_connection.run_sync(_run_migrations)
    await obj_connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_migrations_online())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
