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

Two entry points live here:

1. ``handle(message, ...)`` — conversational path (keyword-routed stubs;
   filled in when the operator chat interface lands).
2. ``run_<stage>(client_id, ...)`` — per-stage dispatchers used by the
   pipeline HTTP router and the Scout daemon. Each ``run_<stage>`` wraps
   the corresponding inner orchestrator with the full foundation loop
   (load_foundation → check_autonomy → find_similar_decisions →
   dispatch). Knowledge retrieval is uniform across stages: expert
   content is pulled in via ``memory_store.load_full_context`` inside
   ``load_foundation``, keyed on the stage-specific ``task_query``
   (e.g. "cold outbound copywriting frameworks" for compose). Per-contact
   decisions are logged by the inner orchestrators; the Scout wrapper
   does NOT double-log at stage level.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from systems.base import BaseSystem, SystemResult

if TYPE_CHECKING:
    from aios.foundation.registry import SystemRegistry

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        *,
        memory_store=None,
        decision_logger=None,
        pattern_matcher=None,
        autonomy_gate=None,
        knowledge_store=None,
        pull_stage_factory: Callable[[], Any] | None = None,
        score_stage_factory: Callable[[], Any] | None = None,
        screen_stage_factory: Callable[[], Any] | None = None,
        identity_stage_factory: Callable[[], Any] | None = None,
        enrich_stage_factory: Callable[[], Any] | None = None,
        composer_factory: Callable[[], Any] | None = None,
    ) -> None:
        """Foundation modules match ``BaseSystem``. Stage factories are
        zero-arg callables that return a freshly-built inner orchestrator.
        Tests inject stubs; production wires real stages via
        :meth:`from_registry`.
        """
        super().__init__(
            memory_store=memory_store,
            decision_logger=decision_logger,
            pattern_matcher=pattern_matcher,
            autonomy_gate=autonomy_gate,
            knowledge_store=knowledge_store,
        )
        self._pull_factory = pull_stage_factory
        self._score_factory = score_stage_factory
        self._screen_factory = screen_stage_factory
        self._identity_factory = identity_stage_factory
        self._enrich_factory = enrich_stage_factory
        self._composer_factory = composer_factory

    # ── Factory ────────────────────────────────────────────────────────────

    @classmethod
    def from_registry(cls, registry: "SystemRegistry") -> "ScoutSystem":
        """Build a ScoutSystem wired to production backends from a registry.

        Factories are closures over registry backends so each ``run_<stage>``
        call gets a fresh orchestrator (stage state never leaks across runs).
        Adapter-requiring stages (pull/identity/enrich) build zero-adapter
        orchestrators for now — adapter wiring belongs in the Scout daemon /
        client-config loader (Plan 2). A zero-adapter run is a valid no-op:
        eligible counts are reported and the stage summary is logged.
        """
        from systems.scout.enrich.orchestrator import EnrichOrchestrator
        from systems.scout.identity.orchestrator import IdentityOrchestrator
        from systems.scout.outreach.composer import Composer
        from systems.scout.outreach.research import ResearchSelector
        from systems.scout.pipeline.enrich import EnrichStage
        from systems.scout.pipeline.identity import IdentityStage
        from systems.scout.pipeline.pull import PullOrchestrator
        from systems.scout.pipeline.score_stage import ScoreStage
        from systems.scout.pipeline.screen import ScreenStage

        return cls(
            memory_store=registry.memory_store,
            decision_logger=registry.decision_logger,
            pattern_matcher=registry.pattern_matcher,
            autonomy_gate=registry.autonomy_gate,
            knowledge_store=registry.knowledge_store,
            pull_stage_factory=lambda: PullOrchestrator(
                adapters=[], storage=registry.pull_backend,
            ),
            score_stage_factory=lambda: ScoreStage(storage=registry.score_backend),
            screen_stage_factory=lambda: ScreenStage(storage=registry.screen_backend),
            identity_stage_factory=lambda: IdentityStage(
                orchestrator=IdentityOrchestrator(adapters=[]),
                storage=registry.identity_backend,
            ),
            enrich_stage_factory=lambda: EnrichStage(
                orchestrator=EnrichOrchestrator(
                    adapters=[], budget_tracker=registry.budget_tracker,
                ),
                storage=registry.enrich_backend,
            ),
            composer_factory=lambda: Composer(
                storage=registry.composer_backend,
                research_selector=ResearchSelector(),
            ),
        )

    # ── Stage dispatchers (foundation loop + inner stage.run) ──────────────

    async def _prime_foundation(
        self,
        client_id: str,
        *,
        task_query: str,
        decision_type: str,
        context_label: str,
    ) -> None:
        """Run the three foundation calls (load → autonomy → similar).

        Shared by every ``run_<stage>``. Knowledge comes in via
        ``load_foundation`` — ``memory_store.load_full_context`` runs a
        similarity search on ``task_query`` and populates
        ``foundation_context['relevant_knowledge']``. No separate
        ``retrieve_knowledge`` call needed: the stage-specific
        ``task_query`` is the steering wheel.
        """
        await self.load_foundation(client_id, task_query=task_query)
        await self.check_autonomy(client_id, action_type=decision_type)
        await self.find_similar_decisions(
            client_id,
            decision_type=decision_type,
            current_context=context_label,
            limit=5,
        )
        logger.debug(
            "scout foundation primed client=%s decision_type=%s",
            client_id, decision_type,
        )

    async def run_pull(
        self,
        client_id: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> Any:
        """Dispatch the pull stage with the mandatory foundation loop.

        The ``limit`` parameter is accepted for API parity with other
        stages but NOT forwarded: ``PullOrchestrator.run`` does not
        accept ``limit``. Use ``max_companies_per_source`` on the
        orchestrator instead (daemon path) to cap the batch size. When
        a caller passes ``limit``, a debug log surfaces the silent-drop
        so it isn't mistaken for an enforced cap.
        """
        if limit is not None:
            logger.debug(
                "run_pull received limit=%s but PullOrchestrator doesn't accept limit; "
                "use source-level `max_companies_per_source` to cap batch size",
                limit,
            )
        logger.info("scout.run_pull start client=%s dry_run=%s", client_id, dry_run)
        await self._prime_foundation(
            client_id,
            task_query="pull stage — discover new contacts",
            decision_type="source_selection",
            context_label="pull stage run",
        )
        stage = self._pull_factory()
        return await stage.run(client_id, dry_run=dry_run)

    async def run_score(
        self,
        client_id: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
        phase: str = "v1",
    ) -> Any:
        """Dispatch the score stage. ``phase`` is "v1" (pre-screen) or "v2"
        (post-enrich re-score); caller picks which pass to run."""
        logger.info(
            "scout.run_score start client=%s dry_run=%s phase=%s",
            client_id, dry_run, phase,
        )
        await self._prime_foundation(
            client_id,
            task_query=f"score stage phase={phase}",
            decision_type="score_contact",
            context_label=f"score stage run phase={phase}",
        )
        stage = self._score_factory()
        return await stage.run(client_id, dry_run=dry_run, limit=limit, phase=phase)

    async def run_screen(
        self,
        client_id: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> Any:
        """Dispatch the screen stage (hard-gate fails → archive)."""
        logger.info("scout.run_screen start client=%s dry_run=%s", client_id, dry_run)
        await self._prime_foundation(
            client_id,
            task_query="screen stage — hard-gate eligibility",
            decision_type="screen_contact",
            context_label="screen stage run",
        )
        stage = self._screen_factory()
        return await stage.run(client_id, dry_run=dry_run, limit=limit)

    async def run_identity(
        self,
        client_id: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> Any:
        """Dispatch the identity stage (resolve decision-maker contact)."""
        logger.info(
            "scout.run_identity start client=%s dry_run=%s", client_id, dry_run,
        )
        await self._prime_foundation(
            client_id,
            task_query="identity stage — resolve decision-maker",
            decision_type="identity_lookup",
            context_label="identity stage run",
        )
        stage = self._identity_factory()
        return await stage.run(client_id, dry_run=dry_run, limit=limit)

    async def run_enrich(
        self,
        client_id: str,
        *,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> Any:
        """Dispatch the enrich stage (ZeroBounce / Trigify / etc.)."""
        logger.info("scout.run_enrich start client=%s dry_run=%s", client_id, dry_run)
        await self._prime_foundation(
            client_id,
            task_query="enrich stage — augment identified contacts",
            decision_type="enrich_contact",
            context_label="enrich stage run",
        )
        stage = self._enrich_factory()
        return await stage.run(client_id, dry_run=dry_run, limit=limit)

    async def run_compose(
        self,
        client_id: str,
        contacts: list[dict[str, Any]],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Dispatch the render stage — compose drafts for ``contacts``.

        Unlike the batch stages, compose is per-contact: the composer
        accepts one contact at a time. This method fans out, splits
        outcomes into composed / skipped (``ComposerSkip`` vs
        ``ComposedDraft``), and returns the /api/pipeline/render response
        shape.

        Knowledge pulling is uniform with every other stage: the
        ``task_query`` ("cold outbound copywriting frameworks") passed to
        ``load_foundation`` drives the similarity search inside
        ``memory_store.load_full_context``, which populates
        ``foundation_context['relevant_knowledge']``. ``Composer.compose``
        does not currently consume that field — the populated context is
        observational until composer is wired to consume it.
        """
        from systems.scout.outreach.composer import ComposerSkip

        logger.info(
            "scout.run_compose start client=%s dry_run=%s contacts=%d",
            client_id, dry_run, len(contacts),
        )
        await self._prime_foundation(
            client_id,
            task_query="cold outbound copywriting frameworks",
            decision_type="render_draft",
            context_label="render stage run",
        )

        composer = self._composer_factory()
        composed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for contact in contacts:
            outcome = await composer.compose(client_id, contact, dry_run=dry_run)
            payload = _to_json(outcome)
            bucket = skipped if isinstance(outcome, ComposerSkip) else composed
            bucket.append(payload)
        return {
            "client_id": client_id,
            "dry_run": dry_run,
            "total_eligible": len(contacts),
            "total_composed": len(composed),
            "total_skipped": len(skipped),
            "composed": composed,
            "skipped": skipped,
        }

    # ── Conversational path (unchanged — filled in by the chat interface) ─

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


# --- Module-level helpers --------------------------------------------------


def _to_json(result: Any) -> Any:
    """Convert a dataclass result to a JSON-serialisable dict.

    Mirrors the helper in ``api/routers/pipeline.py``; duplicated here so
    ``run_compose`` stays router-independent. Kept private — the router
    has its own copy.
    """
    from dataclasses import asdict, is_dataclass
    if is_dataclass(result):
        return asdict(result)
    return result
