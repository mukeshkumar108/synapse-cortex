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

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENV == "development",
    future=True,
    **_ENGINE_KWARGS,
)

async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False  # type: ignore
)


async def init_db() -> None:
    """Initialize database tables for development/testing."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing async database session."""
    async with async_session_maker() as session:  # type: ignore
        yield session
