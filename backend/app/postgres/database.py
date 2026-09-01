"""Async PostgreSQL engine and session lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_connected = False


def normalize_postgres_uri(str_uri: str) -> str:
    """Return a SQLAlchemy async URL while accepting common PostgreSQL URLs."""
    str_value = str_uri.strip()
    if str_value.startswith("postgres://"):
        return "postgresql+asyncpg://" + str_value[len("postgres://"):]
    if str_value.startswith("postgresql://"):
        return "postgresql+asyncpg://" + str_value[len("postgresql://"):]
    return str_value


async def connect_postgres() -> None:
    """Create the connection pool and verify that PostgreSQL is reachable."""
    global _engine, _session_factory, _connected
    if not settings.POSTGRES_URI:
        raise RuntimeError("POSTGRES_URI is required when PostgreSQL is enabled.")

    _engine = create_async_engine(
        normalize_postgres_uri(settings.POSTGRES_URI),
        pool_pre_ping=True,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_timeout=settings.POSTGRES_POOL_TIMEOUT,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    try:
        async with _engine.connect() as obj_connection:
            await obj_connection.execute(text("SELECT 1"))
            tuple_tables = tuple((await obj_connection.execute(text(
                "SELECT to_regclass('public.users'), to_regclass('public.sessions'), "
                "to_regclass('public.audit_logs'), to_regclass('public.ip_geo_cache'), "
                "to_regclass('public.case_clinical_info'), "
                "to_regclass('public.audit_integrity_seals'), "
                "to_regclass('public.application_documents'), "
                "to_regclass('public.application_data_migrations')"
            ))).one())
            if any(obj_table is None for obj_table in tuple_tables):
                raise RuntimeError(
                    "PostgreSQL schema is missing. Run 'alembic upgrade head' first."
                )
    except Exception:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        _connected = False
        raise
    _connected = True


async def disconnect_postgres() -> None:
    """Dispose all pooled PostgreSQL connections."""
    global _engine, _session_factory, _connected
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
    _connected = False


def is_postgres_connected() -> bool:
    return _connected


@asynccontextmanager
async def get_postgres_session() -> AsyncIterator[AsyncSession]:
    """Yield a transaction-scoped session and roll back failed work."""
    if _session_factory is None:
        raise RuntimeError("PostgreSQL is not connected.")
    async with _session_factory() as obj_session:
        try:
            yield obj_session
            await obj_session.commit()
        except Exception:
            await obj_session.rollback()
            raise
