import os
import os
os.environ["SYNAPSE_EXTRACTOR_PROVIDER"] = "rules"
# Tests must NEVER touch a configured store (Neon/production). pydantic
# settings give real env vars precedence over .env, so forcing this here
# guarantees a throwaway database regardless of the developer environment.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/synapse_test.db"

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
