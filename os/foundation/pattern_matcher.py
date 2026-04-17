"""
Pattern Matcher — Learn from past decisions.

Before making a decision, query past similar decisions and their outcomes.
Include these in the prompt so the AI makes better choices over time.

Usage:
    matcher = PatternMatcher(db, embedder)

    # Before generating outreach copy
    past_decisions = await matcher.find_similar(
        client_id="kirsten-client-zero",
        decision_type="copy_variant",
        current_context="agency_founder, CRO niche, no signal, website has case studies",
        limit=5,
    )

    # Returns list of past decisions with outcomes:
    # [
    #   {"decision": "Used AIDA with case study icebreaker", "outcome": "positive", "confidence": 0.82},
    #   {"decision": "Used PAS without signal", "outcome": "negative", "confidence": 0.65},
    # ]
    #
    # Include in Haiku prompt: "Here are similar past decisions and their outcomes: ..."
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PatternMatcher:
    """Finds similar past decisions to inform current decisions."""

    def __init__(self, db, embedder=None):
        self.db = db
        self.embedder = embedder

    async def find_similar(
        self,
        client_id: str,
        decision_type: str,
        current_context: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find past decisions similar to the current context."""
        if not self.embedder:
            logger.debug("No embedder configured, skipping pattern matching")
            return []

        try:
            embedding = await self.embedder(current_context)
        except Exception as e:
            logger.warning("Failed to embed context for pattern matching: %s", e)
            return []

        try:
            result = await self.db.rpc(
                "match_decisions",
                {
                    "query_embedding": embedding,
                    "client_id_filter": client_id,
                    "decision_type_filter": decision_type,
                    "match_count": limit,
                },
            ).execute()

            matches = result.data or []

            if matches:
                logger.info(
                    "PATTERN MATCH: %d similar %s decisions found for %s",
                    len(matches), decision_type, client_id,
                )

            return [
                {
                    "id": m["id"],
                    "decision": m["decision"],
                    "reasoning": m.get("reasoning"),
                    "outcome": m.get("outcome"),
                    "outcome_data": m.get("outcome_data", {}),
                    "confidence": m.get("confidence"),
                    "similarity": m.get("similarity"),
                }
                for m in matches
            ]

        except Exception as e:
            logger.warning("Pattern matching query failed: %s", e)
            return []

    def format_for_prompt(self, past_decisions: list[dict]) -> str:
        """Format past decisions for inclusion in an AI prompt."""
        if not past_decisions:
            return ""

        lines = ["## Past similar decisions and their outcomes:\n"]
        for i, d in enumerate(past_decisions, 1):
            outcome = d.get("outcome", "pending")
            confidence = d.get("confidence")
            conf_str = f" (confidence: {confidence:.0%})" if confidence else ""

            lines.append(f"{i}. Decision: {d['decision']}")
            if d.get("reasoning"):
                lines.append(f"   Reasoning: {d['reasoning']}")
            lines.append(f"   Outcome: {outcome}{conf_str}")

            outcome_data = d.get("outcome_data", {})
            if outcome_data:
                metrics = ", ".join(f"{k}={v}" for k, v in outcome_data.items() if v)
                if metrics:
                    lines.append(f"   Metrics: {metrics}")
            lines.append("")

        lines.append("Use these outcomes to inform your current decision. ")
        lines.append("Prefer approaches that led to positive outcomes. ")
        lines.append("Avoid approaches that led to negative outcomes.")

        return "\n".join(lines)
