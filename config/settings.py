"""Typed, env-backed application settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Client identity ---
    client_id: str = Field(..., description="Short machine-readable client ID")
    client_display_name: str = Field(default="", description="Human-readable client name")

    # --- Database ---
    supabase_url: str
    supabase_service_role_key: str
    supabase_anon_key: str = ""

    # --- AI ---
    anthropic_api_key: str
    voyage_api_key: str = ""

    # --- Email sending (Plan 2) ---
    smartlead_api_key: str = ""
    smartlead_webhook_secret: str = ""

    # --- Enrichment ---
    apollo_api_key: str = ""
    anymail_finder_api_key: str = ""
    zerobounce_api_key: str = ""

    # --- Lead stack (mobile phone, per 2026-04-20 architecture) ---
    lusha_api_key: str = ""         # mobile phone lookup (score >= 50 only)

    # --- Lead stack (escalation — enable only when triggers fire) ---
    hunter_api_key: str = ""        # second-pass email finder (escalation)
    cognism_api_key: str = ""       # compliance-grade mobile (escalation)

    # --- Communication (Plan 3) ---
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""
    calendly_webhook_secret: str = ""

    # --- Internal ---
    cron_secret: str
    api_public_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    environment: str = "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance. Call cache_clear() in tests to reset."""
    return Settings()
