import logging
import os

# The application's own loggers (llm_usage lines, budget refusals, agency passes) were silently dropped: nothing configured logging, so everything below WARNING vanished.
# INFO for our own modules, third-party libraries stay at WARNING so the log stays readable.
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("src").setLevel(os.getenv("APP_LOG_LEVEL", "INFO").upper())
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request
import hmac
from src.db import init_db
from src.config import settings
from src.routers import health_router, events_router, debug_router, cortex_router, world_router, world_delta_router
from src.routers.v1_executive import router as executive_router
from src.routers.v1_ops import router as ops_router
from src.services.turn_extractor import extractor_config_status


def validate_service_token_config() -> None:
    if (
        settings.ENV.strip().lower() in {"production", "prod", "staging"}
        and not settings.SYNAPSE_CORTEX_API_TOKEN.strip()
    ):
        raise RuntimeError(
            "SYNAPSE_CORTEX_API_TOKEN is required outside development/test"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_service_token_config()
    # Initialize DB tables on startup
    await init_db()
    status = extractor_config_status()
    if status["degraded"]:
        logging.getLogger(__name__).warning(
            "synapse-cortex starting in degraded extractor state: %s", status["reason"]
        )
    import asyncio
    from src.services import executive_loop
    task = asyncio.create_task(executive_loop.run_forever())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="synapse-cortex",
    description="Companion State & JIT Context Sidecar for Honcho & Sophie (V4 Core)",
    version="0.2.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def bind_call_context(request: Request, call_next):
    """The caller's account of whose turn this work serves (see src/call_context.py); absent for anything Cortex starts itself."""
    from src import call_context
    token = call_context.CTX.set(call_context.parse_header(request.headers.get("x-call-context")) or None)
    try:
        return await call_next(request)
    finally:
        call_context.CTX.reset(token)


@app.middleware("http")
async def require_service_token(request: Request, call_next):
    token = settings.SYNAPSE_CORTEX_API_TOKEN
    if token and request.url.path != "/health":
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(supplied, expected):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)

app.include_router(health_router)
app.include_router(events_router)
app.include_router(cortex_router)
app.include_router(debug_router)
app.include_router(world_router)
app.include_router(world_delta_router)
app.include_router(executive_router)
app.include_router(ops_router)
