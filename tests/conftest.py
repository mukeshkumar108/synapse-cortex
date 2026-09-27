import os
import os
os.environ["SYNAPSE_EXTRACTOR_PROVIDER"] = "rules"
# Tests must NEVER touch a configured store (Neon/production). pydantic
# settings give real env vars precedence over .env, so forcing this here
# guarantees a throwaway database regardless of the developer environment.
#
# Parallel-safety: every pytest process gets its OWN SQLite file
# (PID + random suffix). A single shared /tmp/synapse_test.db caused
# cross-process schema contention (interleaved DROP/CREATE/INSERT across
# concurrent agents -> "no such table", wild counts). The file is removed
# best-effort at session end; a crashed run can only litter its own file,
# never corrupt another process's database.
import uuid as _uuid

_TEST_DB_PATH = f"/tmp/synapse_test_{os.getpid()}_{_uuid.uuid4().hex[:8]}.db"
try:
    if os.path.exists(_TEST_DB_PATH):
        os.remove(_TEST_DB_PATH)
except OSError:
    pass
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"


def pytest_sessionfinish(session, exitstatus):
    """Best-effort cleanup of this process's isolated test database."""
    try:
        if os.path.exists(_TEST_DB_PATH):
            os.remove(_TEST_DB_PATH)
    except OSError:
        pass

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
