"""Shared FastAPI dependencies (DB session, system wiring)."""
from __future__ import annotations

from supabase import acreate_client, AsyncClient

from config.settings import get_settings


async def get_supabase() -> AsyncClient:
    """Return a new Supabase async client per call.

    TODO(plan-2-lifespan): Replace with a FastAPI lifespan-managed singleton
    stored on app.state so we don't pay acreate_client overhead per request.
    Safe to leave as-is for Plan 1 because no route in Plan 1 actually calls
    this — Task 8's trigger endpoint is a stub.
    """
    settings = get_settings()
    return await acreate_client(settings.supabase_url, settings.supabase_service_role_key)
