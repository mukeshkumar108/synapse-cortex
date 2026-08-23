from fastapi import APIRouter

from src.services.turn_extractor import extractor_config_status

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Basic health check endpoint. Reports extractor degraded state explicitly."""
    return {
        "status": "ok",
        "service": "synapse-cortex",
        "version": "0.1.0",
        "extractor": extractor_config_status(),
    }
