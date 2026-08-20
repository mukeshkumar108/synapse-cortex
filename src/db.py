from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from src.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENV == "development",
    future=True,
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
