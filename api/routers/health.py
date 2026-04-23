"""Health check endpoint."""
from fastapi import APIRouter

from config.settings import get_settings

router = APIRouter()


@router.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "client_id": settings.client_id,
        "environment": settings.environment,
        "version": "0.1.0",
    }
