"""Active-client loader for the daemon (Task 16.6).

The daemon iterates over a list of client_ids on each nightly cycle.
``list_active_clients`` queries ``clients`` (status='active') and returns
the ids. A separate ``fetch_client_config`` pulls the per-client config
row for adapter wiring.

Schema assumption (documented in Plan 1 Task 16.6):
    clients.status = 'active' is the gate. There is NO ``client_config.active``
    column. If a future schema change adds one, this module is the seam
    to update.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aios.foundation.registry import SystemRegistry

logger = logging.getLogger(__name__)


async def list_active_clients(registry: "SystemRegistry") -> list[str]:
    """Return client_ids where ``clients.status = 'active'``.

    Defensive behaviour:
    - On query error (table missing / connection failure): log + return [].
      The daemon logs a warning and skips the cycle rather than crashing.
    - On empty table: info log + return [].
    """
    # We reach into the shared Supabase client via any backend; each backend
    # holds ``self._client``. Pull it from pull_backend (arbitrary choice,
    # every backend in the registry shares the same client).
    client = _get_shared_supabase(registry)
    if client is None:
        logger.error(
            "list_active_clients: could not locate shared Supabase client on registry",
        )
        return []

    try:
        resp = (
            client.table("clients")
            .select("id")
            .eq("status", "active")
            .execute()
        )
    except Exception:
        logger.exception(
            "list_active_clients: query failed — returning empty list",
        )
        return []

    rows = resp.data or []
    client_ids = [str(r["id"]) for r in rows if r.get("id")]
    logger.info("list_active_clients: %d active client(s)", len(client_ids))
    return client_ids


async def fetch_client_config(
    registry: "SystemRegistry", client_id: str,
) -> dict[str, Any] | None:
    """Fetch the client_config row for ``client_id``.

    Returns ``None`` when the row is missing — caller logs and skips that
    client rather than crashing the daemon. On query failure, also returns
    None with an exception logged.
    """
    client = _get_shared_supabase(registry)
    if client is None:
        logger.error("fetch_client_config: no shared Supabase client on registry")
        return None

    try:
        resp = (
            client.table("client_config")
            .select("*")
            .eq("client_id", client_id)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.exception(
            "fetch_client_config: query failed client_id=%s", client_id,
        )
        return None

    rows = resp.data or []
    if not rows:
        logger.warning(
            "fetch_client_config: no client_config row for client_id=%s", client_id,
        )
        return None
    return dict(rows[0])


def _get_shared_supabase(registry: "SystemRegistry") -> Any:
    """Retrieve the shared Supabase client from any backend.

    Every backend in the registry is constructed with the same client —
    pull it off ``pull_backend._client`` since that's the first concrete
    backend built in ``build_registry``.
    """
    backend = getattr(registry, "pull_backend", None)
    if backend is None:
        return None
    return getattr(backend, "_client", None)
