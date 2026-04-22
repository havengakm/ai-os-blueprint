"""
System Registry — Manages all pluggable systems.

Registers, enables/disables, dispatches to, and tier-gates systems.
Every system gets foundation modules injected at registration time.

Usage:
    registry = SystemRegistry()

    # Register systems with foundation modules
    registry.register(ScoutSystem(), memory=store, decisions=logger, ...)
    registry.register(BeaconSystem(), memory=store, decisions=logger, ...)

    # Dispatch a message to the right system
    result = await registry.dispatch("scout", message, client_id, user_id, context)

    # Get summary for system prompt
    summary = registry.systems_summary()
"""
from __future__ import annotations

import logging
from typing import Any

from systems.base import BaseSystem, SystemResult

logger = logging.getLogger(__name__)

TIER_ORDER = {"self_drive": 0, "guided": 1, "managed": 2}


class SystemRegistry:
    """Registry of all pluggable systems."""

    def __init__(self):
        self._systems: dict[str, BaseSystem] = {}

    def register(
        self,
        system: BaseSystem,
        memory=None,
        decisions=None,
        patterns=None,
        autonomy=None,
        knowledge=None,
    ) -> None:
        """Register a system and inject foundation modules."""
        system.memory = memory
        system.decisions = decisions
        system.patterns = patterns
        system.autonomy = autonomy
        system.knowledge = knowledge

        self._systems[system.name] = system
        logger.info(
            "SYSTEM REGISTERED: %s (%s) — %s",
            system.name,
            "enabled" if system.enabled else "disabled",
            system.display_name,
        )

    async def dispatch(
        self,
        system_name: str,
        message: str,
        client_id: str,
        user_id: str,
        context: dict[str, Any] | None = None,
    ) -> SystemResult:
        """Dispatch a message to a specific system."""
        system = self._systems.get(system_name)

        if not system:
            return SystemResult(text=f"System '{system_name}' not found.")

        if not system.enabled:
            return SystemResult(text=system.tease_message())

        # Tier check
        client_tier = (context or {}).get("service_tier", "guided")
        client_level = TIER_ORDER.get(client_tier, 1)
        system_level = TIER_ORDER.get(system.min_tier, 0)

        if client_level < system_level:
            return SystemResult(text=system.tier_block_message(client_tier))

        try:
            return await system.handle(message, client_id, user_id, context)
        except Exception as e:
            logger.error("System %s failed: %s", system_name, e, exc_info=True)
            return SystemResult(
                text=f"Something went wrong with {system.display_name}. I've logged the issue.",
                metadata={"error": str(e)},
            )

    def get(self, name: str) -> BaseSystem | None:
        """Get a system by name."""
        return self._systems.get(name)

    def enabled_systems(self) -> list[BaseSystem]:
        """Return all enabled systems."""
        return [s for s in self._systems.values() if s.enabled]

    def all_systems(self) -> list[BaseSystem]:
        """Return all registered systems."""
        return list(self._systems.values())

    def systems_summary(self) -> str:
        """Generate summary for system prompt."""
        lines = []
        for system in self._systems.values():
            lines.append(system.summary())
        return "\n".join(lines)
