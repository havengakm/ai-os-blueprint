"""Shared FastAPI dependencies (DB session, system wiring)."""
from __future__ import annotations

from functools import lru_cache

from supabase import acreate_client, AsyncClient

from config.settings import get_settings


@lru_cache(maxsize=1)
def _supabase_client_singleton() -> AsyncClient:
    # Placeholder — replaced with async init in main.py lifespan
    raise RuntimeError("Supabase client not yet initialised — use get_supabase")


async def get_supabase() -> AsyncClient:
    """Return a cached Supabase async client."""
    settings = get_settings()
    # Note: acreate_client is async. Caller responsibility to manage lifecycle.
    return await acreate_client(settings.supabase_url, settings.supabase_service_role_key)
