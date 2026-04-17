"""
BaseSystem — The contract every pluggable system must follow.

Every system (Scout, Beacon, Ad Copy, Content OS, etc.) extends this class.
The foundation integration is MANDATORY, not optional.

Usage:
    class ScoutSystem(BaseSystem):
        name = "scout"
        display_name = "Outbound Prospecting"
        description = "Finds ideal clients, writes outreach, books meetings"
        enabled = True
        min_tier = "self_drive"

        async def handle(self, message, client_id, user_id, context):
            # 1. Foundation context is already loaded (self.foundation_context)
            # 2. Do your work
            # 3. Log decisions via self.log_decision()
            # 4. Return SystemResult
            ...
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SystemResult:
    """Result returned by a system's handle() method."""
    text: str = ""
    follow_up_actions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    decisions_logged: list[str] = field(default_factory=list)


class BaseSystem:
    """
    Base class for all pluggable systems.
    Provides mandatory foundation integration.
    """

    # ── System identity (override in subclass) ────────────────────────────

    name: str = ""                      # Machine-readable ID (e.g. "scout")
    display_name: str = ""              # Human-readable name (e.g. "Outbound Prospecting")
    description: str = ""               # One-line for routing
    trigger_examples: list[str] = []    # Example phrases that should route here
    enabled: bool = False               # Must be True to handle messages
    min_tier: str = "self_drive"        # Minimum service tier required

    # ── Foundation integration (set by registry at init) ──────────────────

    def __init__(self, memory_store=None, decision_logger=None,
                 pattern_matcher=None, autonomy_gate=None, knowledge_store=None):
        self.memory = memory_store
        self.decisions = decision_logger
        self.patterns = pattern_matcher
        self.autonomy = autonomy_gate
        self.knowledge = knowledge_store
        self.foundation_context: dict[str, Any] = {}

    # ── Mandatory foundation hooks ────────────────────────────────────────

    async def load_foundation(self, client_id: str, task_query: str = "") -> dict[str, Any]:
        """
        Load all foundation context before acting. MANDATORY.
        Every system calls this before doing any work.
        """
        if not self.memory:
            logger.warning("System %s has no memory store connected", self.name)
            return {}

        self.foundation_context = await self.memory.load_full_context(
            client_id=client_id,
            task_query=task_query or self.description,
        )

        logger.info(
            "FOUNDATION LOADED for %s: %d business_context, %d registry, %d facts, %d knowledge, %d decisions",
            self.name,
            len(self.foundation_context.get("business_context", [])),
            len(self.foundation_context.get("context_registry", [])),
            len(self.foundation_context.get("client_facts", [])),
            len(self.foundation_context.get("relevant_knowledge", [])),
            len(self.foundation_context.get("past_decisions", [])),
        )

        return self.foundation_context

    async def check_autonomy(self, client_id: str, action_type: str) -> str:
        """Check autonomy level before acting. Returns: suggest/draft/act_notify/autonomous."""
        if not self.autonomy:
            return "suggest"  # Always fail safe
        return await self.autonomy.check(client_id, action_type)

    async def log_decision(
        self,
        client_id: str,
        decision_type: str,
        context: dict,
        decision: str,
        reasoning: str | None = None,
        confidence: float | None = None,
    ) -> str:
        """Log a decision to the foundation. MANDATORY for significant actions."""
        if not self.decisions:
            logger.warning("System %s has no decision logger connected", self.name)
            return ""
        return await self.decisions.log_decision(
            client_id=client_id,
            decision_type=decision_type,
            context=context,
            decision=decision,
            reasoning=reasoning,
            source="system",
            confidence=confidence,
        )

    async def find_similar_decisions(
        self,
        client_id: str,
        decision_type: str,
        current_context: str,
        limit: int = 5,
    ) -> list[dict]:
        """Query past similar decisions before making a new one."""
        if not self.patterns:
            return []
        return await self.patterns.find_similar(
            client_id=client_id,
            decision_type=decision_type,
            current_context=current_context,
            limit=limit,
        )

    async def retrieve_knowledge(
        self,
        client_id: str,
        query: str,
        source: str | None = None,
    ) -> list[dict]:
        """Retrieve relevant expert knowledge for the current task."""
        if not self.knowledge:
            return []
        return await self.knowledge.retrieve(
            client_id=client_id,
            query=query,
            source=source,
        )

    # ── System entry point (override in subclass) ─────────────────────────

    async def handle(
        self,
        message: str,
        client_id: str,
        user_id: str,
        context: dict[str, Any] | None = None,
    ) -> SystemResult:
        """
        Handle an incoming message or trigger.
        Override in subclass. MUST call load_foundation() first.

        Pattern:
            1. await self.load_foundation(client_id, task_query)
            2. level = await self.check_autonomy(client_id, action_type)
            3. past = await self.find_similar_decisions(client_id, type, context)
            4. knowledge = await self.retrieve_knowledge(client_id, query)
            5. ... do the system's work ...
            6. await self.log_decision(client_id, type, context, decision, reasoning)
            7. return SystemResult(text=...)
        """
        raise NotImplementedError(f"System {self.name} must implement handle()")

    # ── Tease / disabled messages ─────────────────────────────────────────

    def tease_message(self) -> str:
        """Message shown when system is disabled."""
        return (
            f"{self.display_name} isn't installed yet. "
            f"When it's live, it'll {self.description.lower()}. "
            f"Want to know more about what it can do?"
        )

    def tier_block_message(self, client_tier: str) -> str:
        """Message shown when client's tier is too low."""
        return (
            f"{self.display_name} is available on the "
            f"{self.min_tier.replace('_', ' ').title()} plan and above. "
            f"You're currently on {client_tier.replace('_', ' ').title()}. "
            f"Want to know what's included in an upgrade?"
        )

    # ── Utility ───────────────────────────────────────────────────────────

    def summary(self) -> str:
        """One-line summary for system prompt."""
        status = "LIVE" if self.enabled else "coming soon"
        return f"{self.display_name} ({status}): {self.description}"
