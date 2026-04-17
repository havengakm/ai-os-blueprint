"""
Autonomy Gate — Progressive trust framework.

Every system action checks the gate before executing.
Returns the current autonomy level for that action type.

Levels:
    suggest      → System recommends, human decides
    draft        → System prepares action, human approves
    act_notify   → System acts immediately, notifies human after
    autonomous   → System acts, logs only

Usage:
    gate = AutonomyGate(db)

    level = await gate.check("kirsten-client-zero", "send_timing")
    if level == "suggest":
        # Show recommendation, wait for human
    elif level == "draft":
        # Prepare the action, present for approval
    elif level == "act_notify":
        # Act now, send Telegram notification
    elif level == "autonomous":
        # Act and log, no notification needed

    # Check if promotion is warranted
    promotion = await gate.check_promotion_eligibility(
        "kirsten-client-zero", "copy_variant"
    )
    if promotion["eligible"]:
        # Surface to human via Telegram: "Ready to promote copy_variant to draft?"
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

AUTONOMY_ORDER = ["suggest", "draft", "act_notify", "autonomous"]


class AutonomyGate:
    """Checks and enforces autonomy levels per client per action type."""

    def __init__(self, db):
        self.db = db
        self._cache: dict[str, dict[str, str]] = {}

    async def check(
        self,
        client_id: str,
        action_type: str,
    ) -> str:
        """Return the current autonomy level for this action type."""
        cache_key = f"{client_id}:{action_type}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            result = await (
                self.db.table("autonomy_rules")
                .select("autonomy_level")
                .eq("client_id", client_id)
                .eq("action_type", action_type)
                .limit(1)
                .execute()
            )

            if result.data:
                level = result.data[0]["autonomy_level"]
            else:
                # No rule exists — default to suggest (safest)
                level = "suggest"
                # Create the rule so it's tracked going forward
                await self._create_default_rule(client_id, action_type)

            self._cache[cache_key] = level
            return level

        except Exception as e:
            logger.warning("Autonomy check failed for %s/%s: %s", client_id, action_type, e)
            return "suggest"  # Always fail safe

    async def _create_default_rule(self, client_id: str, action_type: str) -> None:
        """Create a default rule at 'suggest' level."""
        try:
            await (
                self.db.table("autonomy_rules")
                .upsert({
                    "client_id": client_id,
                    "action_type": action_type,
                    "autonomy_level": "suggest",
                })
                .execute()
            )
            logger.info("Created default autonomy rule: %s/%s → suggest", client_id, action_type)
        except Exception:
            pass  # Non-critical

    async def increment_decision_count(
        self,
        client_id: str,
        action_type: str,
        was_successful: bool,
    ) -> None:
        """Track a decision at this autonomy level. Used for promotion eligibility."""
        try:
            result = await (
                self.db.table("autonomy_rules")
                .select("decisions_at_level, success_rate")
                .eq("client_id", client_id)
                .eq("action_type", action_type)
                .limit(1)
                .execute()
            )

            if not result.data:
                return

            current = result.data[0]
            count = (current.get("decisions_at_level") or 0) + 1
            old_rate = current.get("success_rate") or 0.0

            # Running average of success rate
            if was_successful:
                new_rate = old_rate + (1.0 - old_rate) / count
            else:
                new_rate = old_rate - old_rate / count

            await (
                self.db.table("autonomy_rules")
                .update({
                    "decisions_at_level": count,
                    "success_rate": round(new_rate, 4),
                })
                .eq("client_id", client_id)
                .eq("action_type", action_type)
                .execute()
            )

        except Exception as e:
            logger.warning("Failed to increment decision count: %s", e)

    async def check_promotion_eligibility(
        self,
        client_id: str,
        action_type: str,
    ) -> dict[str, Any]:
        """Check if this action type is eligible for autonomy promotion."""
        try:
            result = await (
                self.db.table("autonomy_rules")
                .select("*")
                .eq("client_id", client_id)
                .eq("action_type", action_type)
                .limit(1)
                .execute()
            )

            if not result.data:
                return {"eligible": False, "reason": "No rule exists"}

            rule = result.data[0]
            level = rule["autonomy_level"]
            conditions = rule.get("conditions") or {}
            decisions = rule.get("decisions_at_level") or 0
            success_rate = rule.get("success_rate") or 0.0

            # Already at max level
            if level == "autonomous":
                return {"eligible": False, "reason": "Already at autonomous level"}

            # Check conditions
            min_samples = conditions.get("min_sample_size", 50)
            min_rate = conditions.get("min_success_rate", 0.80)

            reasons = []
            if decisions < min_samples:
                reasons.append(f"Need {min_samples} decisions, have {decisions}")
            if success_rate < min_rate:
                reasons.append(f"Need {min_rate:.0%} success rate, at {success_rate:.0%}")

            if reasons:
                return {
                    "eligible": False,
                    "reason": ". ".join(reasons),
                    "current_level": level,
                    "decisions": decisions,
                    "success_rate": success_rate,
                }

            next_level = AUTONOMY_ORDER[AUTONOMY_ORDER.index(level) + 1]
            return {
                "eligible": True,
                "current_level": level,
                "next_level": next_level,
                "decisions": decisions,
                "success_rate": success_rate,
                "message": (
                    f"Ready to promote {action_type} from '{level}' to '{next_level}'. "
                    f"{decisions} decisions at {success_rate:.0%} success rate."
                ),
            }

        except Exception as e:
            logger.warning("Promotion check failed: %s", e)
            return {"eligible": False, "reason": str(e)}

    async def promote(
        self,
        client_id: str,
        action_type: str,
        approved_by: str,
    ) -> str:
        """Promote an action type to the next autonomy level. Requires human approval."""
        from datetime import datetime, timezone

        result = await (
            self.db.table("autonomy_rules")
            .select("autonomy_level")
            .eq("client_id", client_id)
            .eq("action_type", action_type)
            .limit(1)
            .execute()
        )

        if not result.data:
            return "No rule found"

        current = result.data[0]["autonomy_level"]
        idx = AUTONOMY_ORDER.index(current)

        if idx >= len(AUTONOMY_ORDER) - 1:
            return "Already at maximum autonomy"

        next_level = AUTONOMY_ORDER[idx + 1]

        await (
            self.db.table("autonomy_rules")
            .update({
                "autonomy_level": next_level,
                "decisions_at_level": 0,  # Reset counter for new level
                "success_rate": None,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "approved_by": approved_by,
                "approved_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("client_id", client_id)
            .eq("action_type", action_type)
            .execute()
        )

        # Clear cache
        cache_key = f"{client_id}:{action_type}"
        self._cache.pop(cache_key, None)

        logger.info(
            "AUTONOMY PROMOTED: %s/%s: %s → %s (approved by %s)",
            client_id, action_type, current, next_level, approved_by,
        )

        return f"Promoted {action_type} from {current} to {next_level}"
