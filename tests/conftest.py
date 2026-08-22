import os
os.environ.setdefault("SYNAPSE_EXTRACTOR_PROVIDER", "rules")

import pytest
from httpx import AsyncClient, ASGITransport
from sqlmodel import SQLModel
from src.main import app
from src.db import engine, init_db


@pytest.fixture(autouse=True)
async def setup_db():
    """Ensure a clean database schema for every test."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield


@pytest.fixture
async def async_client():
    """Async HTTP client fixture testing FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
