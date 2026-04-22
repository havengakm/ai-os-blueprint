"""Tests for ``aios/daemon/client_registry.py``."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aios.daemon.client_registry import (
    fetch_client_config,
    list_active_clients,
)


def _fake_registry_with_rows(rows: list[dict]) -> MagicMock:
    """Build a registry whose pull_backend._client.table(...).select(...).
    eq(...).execute() returns ``rows``."""
    exec_resp = MagicMock()
    exec_resp.data = rows

    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.execute.return_value = exec_resp

    client = MagicMock()
    client.table.return_value = chain

    backend = MagicMock()
    backend._client = client

    registry = MagicMock()
    registry.pull_backend = backend
    return registry


@pytest.mark.asyncio
async def test_list_active_clients_returns_ids():
    registry = _fake_registry_with_rows(
        [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}],
    )
    ids = await list_active_clients(registry)
    assert ids == ["c1", "c2", "c3"]


@pytest.mark.asyncio
async def test_list_active_clients_empty_returns_empty_list():
    registry = _fake_registry_with_rows([])
    ids = await list_active_clients(registry)
    assert ids == []


@pytest.mark.asyncio
async def test_list_active_clients_handles_query_exception():
    registry = _fake_registry_with_rows([])
    registry.pull_backend._client.table.side_effect = RuntimeError("db down")
    # Defensive path: log + return [].
    ids = await list_active_clients(registry)
    assert ids == []


@pytest.mark.asyncio
async def test_fetch_client_config_returns_row():
    registry = _fake_registry_with_rows(
        [{"client_id": "c1", "active_directories": ["apollo"]}],
    )
    config = await fetch_client_config(registry, "c1")
    assert config is not None
    assert config["active_directories"] == ["apollo"]


@pytest.mark.asyncio
async def test_fetch_client_config_none_when_missing():
    registry = _fake_registry_with_rows([])
    config = await fetch_client_config(registry, "ghost")
    assert config is None


@pytest.mark.asyncio
async def test_fetch_client_config_none_on_query_exception():
    registry = _fake_registry_with_rows([])
    registry.pull_backend._client.table.side_effect = RuntimeError("db down")
    config = await fetch_client_config(registry, "c1")
    assert config is None
