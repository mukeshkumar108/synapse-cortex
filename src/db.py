from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from src.config import settings


def _engine_kwargs() -> dict:
    """Hosted Postgres (Neon) URLs carry `sslmode=require`, which the asyncpg
    dialect rejects as a connect kwarg. Strip it from the URL and translate
    it into asyncpg's `ssl` connect arg. Returns kwargs AND the cleaned URL."""
    if settings.DATABASE_URL.startswith("postgresql+asyncpg"):
        import ssl as _ssl
        import re as _re
        from urllib.parse import urlsplit, urlunsplit
        match = _re.search(r"sslmode=([a-z\-]+)", settings.DATABASE_URL)
        if not match:
            return {}
        mode = match.group(1)
        parts = urlsplit(settings.DATABASE_URL)
        query = _re.sub(r"([&?]?)sslmode=[a-z\-]+", "", parts.query).lstrip("&")
        settings.DATABASE_URL = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, query, parts.fragment)
        )
        if mode == "disable":
            return {"connect_args": {"ssl": False}}
        return {"connect_args": {"ssl": _ssl.create_default_context()}}
    return {}


_ENGINE_KWARGS = _engine_kwargs()
if __import__("os").environ.get("SYNAPSE_DB_NULLPOOL") == "1":
    # Test harness only: per-test event loops must not share pooled asyncpg connections.
    from sqlalchemy.pool import NullPool
    _ENGINE_KWARGS = {**_ENGINE_KWARGS, "poolclass": NullPool}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENV == "development",
    future=True,
    **_ENGINE_KWARGS,
)

async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False  # type: ignore
)


_ADDITIVE_COLUMNS = (
    ("world_objectives", "durability", "VARCHAR DEFAULT 'unknown'"),
    ("relationship_dimensions", "durability", "VARCHAR DEFAULT 'unknown'"),
    ("producer_runs", "detail_json", "TEXT DEFAULT '{}'"),
    ("continuation_briefs", "scene_json", "TEXT DEFAULT '{}'"),
    ("scene_narratives", "pending_json", "TEXT DEFAULT '[]'"),
    ("world_objectives", "source", "VARCHAR DEFAULT 'extracted'"),
    ("world_objectives", "kind", "VARCHAR"),
    ("world_objectives", "next_move", "TEXT"),
    ("world_objectives", "ready_when", "TEXT"),
    ("world_objectives", "sensitivity", "VARCHAR"),
    ("world_objectives", "expires_at", "TIMESTAMP"),
    ("world_objectives", "offered_count", "INTEGER DEFAULT 0"),
    ("world_objectives", "last_offered_at", "TIMESTAMP"),
    ("world_events", "origin", "VARCHAR DEFAULT 'conversation'"),
    ("world_events", "arrival", "VARCHAR"),
    ("world_events", "detail", "TEXT"),
    ("producer_runs", "started_at", "TIMESTAMP"),
    ("producer_runs", "finished_at", "TIMESTAMP"),
    ("executive_wakes", "detail_json", "TEXT"),
    ("work_items", "kind", "VARCHAR"),
    ("work_items", "wake_at", "TIMESTAMP"),
    ("work_items", "waiting_on", "TEXT"),
    ("work_items", "run_id", "VARCHAR"),
    ("work_items", "tool_json", "TEXT"),
    ("work_items", "receipt_json", "TEXT"),
)


async def init_db() -> None:
    """Initialize database tables for development/testing, plus idempotent additive columns for tables created by an earlier release
    (create_all never alters an existing table)."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        if conn.dialect.name == "postgresql":
            for table, column, ddl in _ADDITIVE_COLUMNS:
                await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing async database session."""
    async with async_session_maker() as session:  # type: ignore
        yield session


async def get_rollback_session() -> AsyncGenerator[AsyncSession, None]:
    """Run a request against real state while rolling every DB effect back.

    Services in this codebase legitimately call ``session.commit()`` while
    compiling state. ``join_transaction_mode='create_savepoint'`` keeps those
    commits inside an outer connection transaction, so the dependency can
    roll the complete request back after producing its evaluation response.
    Evaluation routes must also suppress work scheduled on independent
    sessions, because that work would sit outside this transaction.
    """
    async with engine.connect() as connection:
        outer = await connection.begin()
        # SQLite's driver defers the physical BEGIN until the first write.
        # If that first write happens inside a SAVEPOINT, releasing the
        # savepoint can make it durable before SQLAlchemy's logical outer
        # transaction is rolled back. Force the physical boundary in tests
        # and local SQLite deployments. Postgres begins eagerly already.
        if connection.dialect.name == "sqlite":
            await connection.exec_driver_sql("BEGIN")
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if outer.is_active:
                await outer.rollback()
