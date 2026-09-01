"""PostgreSQL application database facade and event-loop helpers."""

import asyncio


_main_loop: asyncio.AbstractEventLoop | None = None


def is_db_connected() -> bool:
    """Return PostgreSQL readiness for application-state callers."""
    from app.postgres.database import is_postgres_connected

    return is_postgres_connected()


def get_main_loop() -> asyncio.AbstractEventLoop | None:
    """Return the main event loop used for thread-safe async DB calls."""
    return _main_loop


def initialize_main_loop() -> None:
    """Record the FastAPI event loop for worker-thread callbacks."""
    global _main_loop
    _main_loop = asyncio.get_running_loop()


def get_db():
    """Return the PostgreSQL-backed application document facade."""
    from app.postgres.database import is_postgres_connected
    from app.repositories.application_store import get_application_db

    if not is_postgres_connected():
        raise RuntimeError("PostgreSQL is not connected.")
    return get_application_db()
