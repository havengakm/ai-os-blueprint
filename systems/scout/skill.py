"""
Scout System — Outbound Prospecting.

Finds ideal clients, writes personalised outreach, books meetings.
This is the first system installed for every client (immediate ROI).

Extends BaseSystem with mandatory foundation integration:
- Loads ICP, avatar, voice context before generating outreach
- Queries knowledge_base for copywriting frameworks
- Logs copy_variant and send_timing decisions
- Checks autonomy before sending
- Past decision outcomes improve future copy quality

Migration note: Pipeline scripts from base-camp-agents/scripts/ will be
imported here. This file is the entry point that the SystemRegistry calls.
"""
from __future__ import annotations

from systems.base import BaseSystem, SystemResult


class ScoutSystem(BaseSystem):
    name = "scout"
    display_name = "Outbound Prospecting"
    description = "Finds ideal clients, writes personalised outreach, and books meetings into your calendar"
    trigger_examples = [
        "how's outbound going",
        "show me pipeline",
        "any new replies",
        "generate outreach",
        "send emails",
        "review drafts",
        "how many meetings this week",
        "who replied",
        "approve drafts",
        "pull more leads",
    ]
    enabled = True
    min_tier = "self_drive"

    async def handle(self, message, client_id, user_id, context=None):
        """
        Handle Scout-related requests.

        Routes to:
        - Pipeline status queries ("how's outbound going")
        - Draft review ("review drafts", "approve drafts")
        - Lead management ("pull more leads")
        - Performance queries ("how many meetings", "who replied")
        - Outreach generation ("generate outreach")

        TODO: Migrate actual pipeline logic from base-camp-agents.
        Currently returns a placeholder.
        """
        # 1. LOAD FOUNDATION (mandatory)
        await self.load_foundation(client_id, task_query=message)

        # 2. CHECK AUTONOMY
        # Different actions have different autonomy levels
        # e.g. "send outreach" checks send_timing autonomy
        #      "generate outreach" checks copy_variant autonomy

        # 3. ROUTE to appropriate handler
        msg_lower = message.lower()

        if any(kw in msg_lower for kw in ["pipeline", "status", "how's outbound", "what's happening"]):
            return await self._handle_pipeline_status(client_id)

        if any(kw in msg_lower for kw in ["review", "approve", "draft"]):
            return await self._handle_draft_review(client_id, user_id)

        if any(kw in msg_lower for kw in ["replied", "reply", "response"]):
            return await self._handle_replies(client_id)

        if any(kw in msg_lower for kw in ["meeting", "booked", "calendar"]):
            return await self._handle_meetings(client_id)

        # Default: general outbound question
        return SystemResult(
            text=(
                "Scout is live. The outbound system is running. "
                "Ask me about pipeline status, draft reviews, replies, or meetings."
            )
        )

    async def _handle_pipeline_status(self, client_id):
        """Query pipeline numbers."""
        # TODO: Query contacts table for counts by status
        return SystemResult(text="Pipeline status query — to be implemented after migration.")

    async def _handle_draft_review(self, client_id, user_id):
        """Start a draft review session."""
        # TODO: Query outreach_drafts with status='pending_review'
        return SystemResult(text="Draft review — to be implemented after migration.")

    async def _handle_replies(self, client_id):
        """Show recent replies."""
        # TODO: Query activity_log for reply events
        return SystemResult(text="Reply summary — to be implemented after migration.")

    async def _handle_meetings(self, client_id):
        """Show meeting stats."""
        # TODO: Query Calendly or activity_log for meeting events
        return SystemResult(text="Meeting stats — to be implemented after migration.")
