import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request
import hmac
from src.db import init_db
from src.config import settings
from src.routers import health_router, events_router, context_router, debug_router, cortex_router
from src.services.turn_extractor import extractor_config_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    await init_db()
    status = extractor_config_status()
    if status["degraded"]:
        logging.getLogger(__name__).warning(
            "synapse-cortex starting in degraded extractor state: %s", status["reason"]
        )
    yield


app = FastAPI(
    title="synapse-cortex",
    description="Companion State & JIT Context Sidecar for Honcho & Sophie (V4 Core)",
    version="0.2.0",
    lifespan=lifespan,
)


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
app.include_router(context_router)
app.include_router(cortex_router)
app.include_router(debug_router)
