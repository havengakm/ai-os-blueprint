"""Tests for the enrich pipeline stage (Task 12d).

Uses in-memory fakes for both storage and orchestrator — no real
adapters or Anthropic SDK needed.
"""
from __future__ import annotations

from typing import Any

from systems.scout.enrich.base import EnrichResult
from systems.scout.enrich.orchestrator import EnrichOrchestratorResult
from systems.scout.pipeline.enrich import (
    EnrichContactRow,
    EnrichStage,
    EnrichStageResult,
    EnrichStorageBackend,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeStorage:
    """In-memory EnrichStorageBackend."""

    def __init__(
        self,
        contacts: list[EnrichContactRow],
        trigify_search_ids: list[str] | None = None,
    ) -> None:
        self.contacts = contacts
        self.trigify_search_ids = trigify_search_ids or []
        self.updates: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        # Per-contact update failure: contact_id -> Exception
        self.update_raises: dict[str, Exception] = {}

    async def get_eligible_contacts_for_enrich(
        self,
        client_id: str,
        *,
        archive_floor: int,
        limit: int | None = None,
    ) -> list[EnrichContactRow]:
        return self.contacts[:limit] if limit is not None else list(self.contacts)

    async def get_client_trigify_search_ids(self, client_id: str) -> list[str]:
        return list(self.trigify_search_ids)

    async def update_contact_enrich_data(
        self,
        client_id: str,
        contact_id: str,
        *,
        research_data_patch: dict[str, Any],
        email_verified: bool | None,
        email_catch_all: bool | None,
        enriched_at_utc: str,
    ) -> None:
        if contact_id in self.update_raises:
            raise self.update_raises[contact_id]
        self.updates.append(
            {
                "client_id": client_id,
                "contact_id": contact_id,
                "research_data_patch": research_data_patch,
                "email_verified": email_verified,
                "email_catch_all": email_catch_all,
                "enriched_at_utc": enriched_at_utc,
            }
        )

    async def log_decision(
        self,
        client_id: str,
        *,
        decision_type: str,
        decision: str,
        context: dict[str, Any],
        reasoning: str | None = None,
        confidence: float | None = None,
    ) -> None:
        self.decisions.append(
            {
                "client_id": client_id,
                "decision_type": decision_type,
                "decision": decision,
                "context": context,
                "reasoning": reasoning,
                "confidence": confidence,
            }
        )


class FakeOrchestrator:
    """Stand-in EnrichOrchestrator returning pre-programmed responses.

    ``set_response(contact_id, response)`` scripts the output for a given
    contact. Unset contacts get a blank result (no adapters ran).
    """

    def __init__(self) -> None:
        self._responses: dict[str, EnrichOrchestratorResult] = {}
        self.calls: list[dict[str, Any]] = []

    def set_response(
        self,
        contact_id: str,
        response: EnrichOrchestratorResult,
    ) -> None:
        self._responses[contact_id] = response

    async def enrich_contact(
        self,
        client_id: str,
        contact: dict[str, Any],
        tier: str,
        *,
        dry_run: bool = False,
    ) -> EnrichOrchestratorResult:
        self.calls.append(
            {
                "client_id": client_id,
                "contact": contact,
                "tier": tier,
                "dry_run": dry_run,
            }
        )
        cid = str(contact.get("contact_id", "<unknown>"))
        return self._responses.get(
            cid,
            EnrichOrchestratorResult(
                contact_id=cid,
                tier=tier,
                adapter_results={},
                skipped={},
                total_cost_cents=0,
                budget_exhausted=False,
            ),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


CLIENT = "client-abc"


def mk_contact(
    contact_id: str,
    *,
    tier: str = "A",
    company: str = "Acme",
    email: str | None = "buyer@acme.com",
    domain: str | None = "acme.com",
    linkedin: str | None = None,
    industry: str | None = "B2B SaaS",
    existing: dict[str, Any] | None = None,
) -> EnrichContactRow:
    return EnrichContactRow(
        contact_id=contact_id,
        icp_tier=tier,
        email=email,
        company=company,
        company_domain=domain,
        linkedin_url=linkedin,
        industry=industry,
        existing_research_data=existing or {},
    )


def mk_er(
    name: str,
    *,
    ok: bool = True,
    data: dict[str, Any] | None = None,
    cost: int = 0,
    reason: str = "ok",
) -> EnrichResult:
    return EnrichResult(
        adapter_name=name,
        ok=ok,
        data=data or {},
        cost_cents=cost,
        reason=reason,
    )


def mk_orc(
    contact_id: str,
    tier: str,
    *,
    adapter_results: dict[str, EnrichResult] | None = None,
    skipped: dict[str, str] | None = None,
    total_cost_cents: int = 0,
    budget_exhausted: bool = False,
) -> EnrichOrchestratorResult:
    return EnrichOrchestratorResult(
        contact_id=contact_id,
        tier=tier,
        adapter_results=adapter_results or {},
        skipped=skipped or {},
        total_cost_cents=total_cost_cents,
        budget_exhausted=budget_exhausted,
    )


# ---------------------------------------------------------------------------
# Sanity: Protocol + Result shape
# ---------------------------------------------------------------------------


def test_fake_storage_conforms_to_protocol():
    # Structural check — FakeStorage should satisfy the Protocol.
    storage: EnrichStorageBackend = FakeStorage([])
    assert storage is not None


def test_result_default_shape():
    result = EnrichStageResult(client_id=CLIENT, dry_run=False)
    assert result.total_eligible == 0
    assert result.total_enriched == 0
    assert result.total_errored == 0
    assert result.total_budget_paused == 0
    assert result.total_cost_cents == 0
    assert result.by_tier == {"A": 0, "B": 0, "C": 0, "D": 0}
    assert result.by_adapter_hit == {}
    assert result.by_adapter_skip == {}


# ---------------------------------------------------------------------------
# 1. Happy path — multi-tier fan-out
# ---------------------------------------------------------------------------


async def test_happy_path_multi_tier():
    contacts = [
        mk_contact("c1", tier="A", company="Alpha"),
        mk_contact("c2", tier="B", company="Beta"),
        mk_contact("c3", tier="D", company="Delta"),
    ]
    storage = FakeStorage(contacts)
    orc = FakeOrchestrator()

    orc.set_response(
        "c1",
        mk_orc(
            "c1",
            "A",
            adapter_results={
                "zerobounce": mk_er(
                    "zerobounce",
                    data={"email_verified": True, "email_catch_all": False},
                    cost=1,
                ),
                "claude_deep_research": mk_er(
                    "claude_deep_research",
                    data={"citable_details": [{"type": "news", "detail": "hired CMO"}]},
                    cost=200,
                ),
            },
            total_cost_cents=201,
        ),
    )
    orc.set_response(
        "c2",
        mk_orc(
            "c2",
            "B",
            adapter_results={
                "zerobounce": mk_er(
                    "zerobounce",
                    data={"email_verified": False, "email_catch_all": False},
                    cost=1,
                ),
            },
            total_cost_cents=1,
        ),
    )
    orc.set_response(
        "c3",
        mk_orc(
            "c3",
            "D",
            adapter_results={
                "claude_research": mk_er(
                    "claude_research",
                    data={"company_summary": "small agency"},
                    cost=5,
                ),
            },
            total_cost_cents=5,
        ),
    )

    stage = EnrichStage(orc, storage)
    result = await stage.run(CLIENT)

    assert result.total_eligible == 3
    assert result.total_enriched == 3
    assert result.total_errored == 0
    assert result.total_cost_cents == 207
    assert result.by_tier == {"A": 1, "B": 1, "C": 0, "D": 1}
    # Hits: zerobounce twice, claude_deep_research once, claude_research once
    assert result.by_adapter_hit == {
        "zerobounce": 2,
        "claude_deep_research": 1,
        "claude_research": 1,
    }

    # Patch content for c1 — email_verified/catch_all lifted out, citable_details remain.
    c1_update = next(u for u in storage.updates if u["contact_id"] == "c1")
    assert c1_update["email_verified"] is True
    assert c1_update["email_catch_all"] is False
    assert "email_verified" not in c1_update["research_data_patch"]
    assert "email_catch_all" not in c1_update["research_data_patch"]
    assert c1_update["research_data_patch"]["citable_details"] == [
        {"type": "news", "detail": "hired CMO"}
    ]


# ---------------------------------------------------------------------------
# 2. Dry-run — no persistence, counters + summary still emitted
# ---------------------------------------------------------------------------


async def test_dry_run_skips_persistence_but_counts_and_summarises():
    contact = mk_contact("c1", tier="A")
    storage = FakeStorage([contact])
    orc = FakeOrchestrator()
    orc.set_response(
        "c1",
        mk_orc(
            "c1",
            "A",
            adapter_results={
                "zerobounce": mk_er(
                    "zerobounce",
                    data={"email_verified": True, "email_catch_all": False},
                    cost=1,
                )
            },
            total_cost_cents=1,
        ),
    )

    stage = EnrichStage(orc, storage)
    result = await stage.run(CLIENT, dry_run=True)

    assert result.dry_run is True
    assert result.total_enriched == 1
    assert result.total_cost_cents == 1
    assert storage.updates == []

    summaries = [d for d in storage.decisions if d["decision"] == "enrich_stage_summary"]
    assert len(summaries) == 1
    assert summaries[0]["context"]["dry_run"] is True

    # Orchestrator should have been invoked with dry_run=True.
    assert orc.calls[0]["dry_run"] is True


# ---------------------------------------------------------------------------
# 3. Empty pool — summary still emitted
# ---------------------------------------------------------------------------


async def test_empty_pool_still_summarises():
    storage = FakeStorage([])
    orc = FakeOrchestrator()
    stage = EnrichStage(orc, storage)

    result = await stage.run(CLIENT)

    assert result.total_eligible == 0
    assert result.total_enriched == 0
    assert result.total_errored == 0
    assert result.total_budget_paused == 0
    assert result.total_cost_cents == 0
    assert result.by_adapter_hit == {}
    assert result.by_adapter_skip == {}
    assert orc.calls == []

    summaries = [d for d in storage.decisions if d["decision"] == "enrich_stage_summary"]
    assert len(summaries) == 1
    ctx = summaries[0]["context"]
    assert ctx["total_eligible"] == 0
    assert ctx["total_enriched"] == 0


# ---------------------------------------------------------------------------
# 4. Limit respected
# ---------------------------------------------------------------------------


async def test_limit_caps_batch():
    contacts = [mk_contact(f"c{i}", tier="A") for i in range(5)]
    storage = FakeStorage(contacts)
    orc = FakeOrchestrator()
    stage = EnrichStage(orc, storage)

    result = await stage.run(CLIENT, limit=2)

    assert result.total_eligible == 2
    assert len(orc.calls) == 2
    dispatched = {c["contact"]["contact_id"] for c in orc.calls}
    assert dispatched == {"c0", "c1"}


# ---------------------------------------------------------------------------
# 5. Persistence failure — one contact errors, others unaffected
# ---------------------------------------------------------------------------


async def test_persistence_failure_does_not_abort_stage():
    contacts = [mk_contact("c1"), mk_contact("c2"), mk_contact("c3")]
    storage = FakeStorage(contacts)
    storage.update_raises["c2"] = RuntimeError("boom")

    orc = FakeOrchestrator()
    for cid in ("c1", "c2", "c3"):
        orc.set_response(
            cid,
            mk_orc(
                cid,
                "A",
                adapter_results={
                    "zerobounce": mk_er(
                        "zerobounce",
                        data={"email_verified": True, "email_catch_all": False},
                        cost=1,
                    )
                },
                total_cost_cents=1,
            ),
        )

    stage = EnrichStage(orc, storage)
    result = await stage.run(CLIENT)

    # c2 errored; c1 and c3 persisted.
    assert result.total_errored == 1
    assert result.total_enriched == 3  # all three produced useful data pre-persist
    assert {u["contact_id"] for u in storage.updates} == {"c1", "c3"}

    # A persist_failed decision was logged for c2.
    fails = [
        d for d in storage.decisions
        if str(d["decision"]).startswith("enrich_stage:persist_failed:")
    ]
    assert len(fails) == 1
    assert fails[0]["decision"].endswith(":c2")


# ---------------------------------------------------------------------------
# 6. Budget exhausted mid-stage
# ---------------------------------------------------------------------------


async def test_budget_exhausted_increments_paused_counter():
    contacts = [mk_contact("c1"), mk_contact("c2")]
    storage = FakeStorage(contacts)
    orc = FakeOrchestrator()

    # c1 runs partial: zerobounce hit, deep research skipped for budget.
    orc.set_response(
        "c1",
        mk_orc(
            "c1",
            "A",
            adapter_results={
                "zerobounce": mk_er(
                    "zerobounce",
                    data={"email_verified": True, "email_catch_all": False},
                    cost=1,
                ),
            },
            skipped={"claude_deep_research": "budget_exhausted"},
            total_cost_cents=1,
            budget_exhausted=True,
        ),
    )
    # c2 runs normally.
    orc.set_response(
        "c2",
        mk_orc(
            "c2",
            "A",
            adapter_results={
                "zerobounce": mk_er(
                    "zerobounce",
                    data={"email_verified": True, "email_catch_all": False},
                    cost=1,
                ),
            },
            total_cost_cents=1,
        ),
    )

    stage = EnrichStage(orc, storage)
    result = await stage.run(CLIENT)

    assert result.total_budget_paused == 1
    assert result.total_enriched == 2  # both had at least one adapter succeed
    assert result.by_adapter_hit == {"zerobounce": 2}
    assert result.by_adapter_skip == {"claude_deep_research": 1}
    assert result.total_cost_cents == 2


# ---------------------------------------------------------------------------
# 7. trigify_search_ids attached to every contact dict
# ---------------------------------------------------------------------------


async def test_trigify_search_ids_attached_to_contact_dict():
    contacts = [mk_contact("c1"), mk_contact("c2")]
    search_ids = ["sid-1", "sid-2"]
    storage = FakeStorage(contacts, trigify_search_ids=search_ids)
    orc = FakeOrchestrator()
    stage = EnrichStage(orc, storage)

    await stage.run(CLIENT)

    assert len(orc.calls) == 2
    for call in orc.calls:
        assert call["contact"]["trigify_search_ids"] == search_ids


async def test_trigify_search_ids_fetched_once_per_run():
    """Verify the stage fetches search IDs ONCE even across many contacts.

    Catches per-contact re-fetch regressions.
    """

    class CountingStorage(FakeStorage):
        def __init__(self, contacts, trigify_search_ids):
            super().__init__(contacts, trigify_search_ids=trigify_search_ids)
            self.trigify_fetch_calls = 0

        async def get_client_trigify_search_ids(self, client_id):
            self.trigify_fetch_calls += 1
            return list(self.trigify_search_ids)

    contacts = [mk_contact(f"c{i}") for i in range(5)]
    storage = CountingStorage(contacts, ["sid-1"])
    orc = FakeOrchestrator()
    stage = EnrichStage(orc, storage)

    await stage.run(CLIENT)

    assert storage.trigify_fetch_calls == 1


# ---------------------------------------------------------------------------
# 8. already_complete fields mapped (company_* → bare)
# ---------------------------------------------------------------------------


async def test_already_complete_fields_mapped_to_bare_keys():
    contact = mk_contact(
        "c1",
        industry="B2B SaaS",
        existing={
            "company_revenue_usd": 5_000_000,
            "company_employees": 50,
            "company_founded_year": 2015,
            "irrelevant": "ignored",
        },
    )
    storage = FakeStorage([contact])
    orc = FakeOrchestrator()
    stage = EnrichStage(orc, storage)

    await stage.run(CLIENT)

    call = orc.calls[0]
    contact_dict = call["contact"]
    assert contact_dict["revenue_usd"] == 5_000_000
    assert contact_dict["employees"] == 50
    assert contact_dict["founded_year"] == 2015
    assert contact_dict["industry"] == "B2B SaaS"
    # Bare keys — NOT the company_* variants.
    assert "company_revenue_usd" not in contact_dict


async def test_missing_existing_research_fields_map_to_none():
    contact = mk_contact("c1", industry=None, existing={})
    storage = FakeStorage([contact])
    orc = FakeOrchestrator()
    stage = EnrichStage(orc, storage)

    await stage.run(CLIENT)

    contact_dict = orc.calls[0]["contact"]
    assert contact_dict["revenue_usd"] is None
    assert contact_dict["employees"] is None
    assert contact_dict["founded_year"] is None
    assert contact_dict["industry"] is None


# ---------------------------------------------------------------------------
# 9. Merge logic — lists extended (and deduped)
# ---------------------------------------------------------------------------


async def test_merge_extends_lists_across_adapters():
    contact = mk_contact("c1", tier="A")
    storage = FakeStorage([contact])
    orc = FakeOrchestrator()

    orc.set_response(
        "c1",
        mk_orc(
            "c1",
            "A",
            adapter_results={
                "claude_web_triggers": mk_er(
                    "claude_web_triggers",
                    data={
                        "trigger_events": [
                            {"type": "funding", "detail": "Series A"},
                            {"type": "hire", "detail": "hired CMO"},
                        ],
                    },
                ),
                "trigify": mk_er(
                    "trigify",
                    data={
                        "trigger_events": [
                            {"type": "job_post", "detail": "hiring SDR"},
                            # Duplicate with claude_web_triggers — should dedupe.
                            {"type": "hire", "detail": "hired CMO"},
                        ],
                    },
                ),
            },
        ),
    )

    stage = EnrichStage(orc, storage)
    await stage.run(CLIENT)

    patch = storage.updates[0]["research_data_patch"]
    events = patch["trigger_events"]
    assert len(events) == 3
    # First two from claude_web_triggers, then trigify's unique entry.
    assert events[0] == {"type": "funding", "detail": "Series A"}
    assert events[1] == {"type": "hire", "detail": "hired CMO"}
    assert events[2] == {"type": "job_post", "detail": "hiring SDR"}


async def test_merge_deep_merges_dicts_and_overwrites_scalars():
    contact = mk_contact("c1", tier="A")
    storage = FakeStorage([contact])
    orc = FakeOrchestrator()

    orc.set_response(
        "c1",
        mk_orc(
            "c1",
            "A",
            adapter_results={
                "apollo_enrich": mk_er(
                    "apollo_enrich",
                    data={
                        "company_employees": 50,
                        "company_tech": {"crm": "hubspot"},
                        "company_industry": "saas",
                    },
                ),
                "claude_deep_research": mk_er(
                    "claude_deep_research",
                    data={
                        # Scalar overwrite: later wins.
                        "company_industry": "b2b-saas",
                        # Dict deep-merge.
                        "company_tech": {"email": "outreach"},
                    },
                ),
            },
        ),
    )

    stage = EnrichStage(orc, storage)
    await stage.run(CLIENT)

    patch = storage.updates[0]["research_data_patch"]
    assert patch["company_employees"] == 50
    assert patch["company_industry"] == "b2b-saas"
    assert patch["company_tech"] == {"crm": "hubspot", "email": "outreach"}


# ---------------------------------------------------------------------------
# 10. email fields lifted to top-level + removed from patch
# ---------------------------------------------------------------------------


async def test_email_fields_lifted_from_patch_to_columns():
    contact = mk_contact("c1", tier="A")
    storage = FakeStorage([contact])
    orc = FakeOrchestrator()
    orc.set_response(
        "c1",
        mk_orc(
            "c1",
            "A",
            adapter_results={
                "zerobounce": mk_er(
                    "zerobounce",
                    data={
                        "email_verified": True,
                        "email_catch_all": False,
                        "deliverability_score": 95,
                    },
                    cost=1,
                )
            },
            total_cost_cents=1,
        ),
    )

    stage = EnrichStage(orc, storage)
    await stage.run(CLIENT)

    update = storage.updates[0]
    assert update["email_verified"] is True
    assert update["email_catch_all"] is False
    patch = update["research_data_patch"]
    assert "email_verified" not in patch
    assert "email_catch_all" not in patch
    # Other zerobounce fields remain.
    assert patch["deliverability_score"] == 95


async def test_email_fields_none_when_absent():
    contact = mk_contact("c1", tier="A")
    storage = FakeStorage([contact])
    orc = FakeOrchestrator()
    orc.set_response(
        "c1",
        mk_orc(
            "c1",
            "A",
            adapter_results={
                "claude_research": mk_er(
                    "claude_research",
                    data={"company_summary": "agency"},
                )
            },
        ),
    )

    stage = EnrichStage(orc, storage)
    await stage.run(CLIENT)

    update = storage.updates[0]
    assert update["email_verified"] is None
    assert update["email_catch_all"] is None


# ---------------------------------------------------------------------------
# 11. Per-adapter hit/skip counts
# ---------------------------------------------------------------------------


async def test_per_adapter_hit_and_skip_counts():
    contacts = [mk_contact("c1"), mk_contact("c2")]
    storage = FakeStorage(contacts)
    orc = FakeOrchestrator()

    orc.set_response(
        "c1",
        mk_orc(
            "c1",
            "A",
            adapter_results={
                "zerobounce": mk_er(
                    "zerobounce",
                    data={"email_verified": True, "email_catch_all": False},
                    cost=1,
                ),
                "trigify": mk_er("trigify", data={"trigger_events": []}),
            },
            skipped={},
            total_cost_cents=1,
        ),
    )
    orc.set_response(
        "c2",
        mk_orc(
            "c2",
            "A",
            adapter_results={
                "zerobounce": mk_er(
                    "zerobounce",
                    data={"email_verified": True, "email_catch_all": False},
                    cost=1,
                ),
            },
            skipped={"trigify": "no_monitors_configured"},
            total_cost_cents=1,
        ),
    )

    stage = EnrichStage(orc, storage)
    result = await stage.run(CLIENT)

    assert result.by_adapter_hit["zerobounce"] == 2
    assert result.by_adapter_hit["trigify"] == 1
    assert result.by_adapter_skip["trigify"] == 1
    assert result.by_adapter_skip.get("zerobounce", 0) == 0


# ---------------------------------------------------------------------------
# 12. Summary log fires on exception path
# ---------------------------------------------------------------------------


async def test_summary_logged_even_when_every_contact_errors():
    contacts = [mk_contact("c1"), mk_contact("c2")]
    storage = FakeStorage(contacts)
    storage.update_raises["c1"] = RuntimeError("one")
    storage.update_raises["c2"] = RuntimeError("two")

    orc = FakeOrchestrator()
    for cid in ("c1", "c2"):
        orc.set_response(
            cid,
            mk_orc(
                cid,
                "A",
                adapter_results={
                    "zerobounce": mk_er(
                        "zerobounce",
                        data={"email_verified": True, "email_catch_all": False},
                        cost=1,
                    )
                },
                total_cost_cents=1,
            ),
        )

    stage = EnrichStage(orc, storage)
    result = await stage.run(CLIENT)

    assert result.total_errored == 2
    summaries = [d for d in storage.decisions if d["decision"] == "enrich_stage_summary"]
    assert len(summaries) == 1
    ctx = summaries[0]["context"]
    assert ctx["total_eligible"] == 2
    assert ctx["total_errored"] == 2


# ---------------------------------------------------------------------------
# Extra: dropped data from failed adapters does NOT pollute the patch
# ---------------------------------------------------------------------------


async def test_failed_adapter_data_ignored_in_merge():
    """Adapter with ok=False has its data ignored during merge, even if
    the orchestrator handed back a non-empty data dict (e.g. a partial
    response on a timeout retry path).
    """
    contact = mk_contact("c1", tier="A")
    storage = FakeStorage([contact])
    orc = FakeOrchestrator()
    orc.set_response(
        "c1",
        mk_orc(
            "c1",
            "A",
            adapter_results={
                "zerobounce": mk_er(
                    "zerobounce",
                    ok=False,
                    data={"email_verified": False, "should_not_persist": True},
                    reason="unsafe:invalid",
                    cost=1,
                ),
                "claude_research": mk_er(
                    "claude_research",
                    data={"company_summary": "agency"},
                ),
            },
            total_cost_cents=1,
        ),
    )

    stage = EnrichStage(orc, storage)
    result = await stage.run(CLIENT)

    # Only claude_research contributed to the patch.
    update = storage.updates[0]
    assert update["email_verified"] is None  # zerobounce was not ok → not lifted
    assert "should_not_persist" not in update["research_data_patch"]
    assert update["research_data_patch"]["company_summary"] == "agency"

    # Hit count: only claude_research counts as a hit.
    assert result.by_adapter_hit == {"claude_research": 1}
    assert result.total_enriched == 1


# ---------------------------------------------------------------------------
# Extra: tier counter is kept even when orchestrator returns nothing
# ---------------------------------------------------------------------------


async def test_total_enriched_only_counts_contacts_with_useful_data():
    """total_enriched increments only when at least one adapter returned
    ok=True AND non-empty data. A contact whose orchestrator returned
    zero adapter_results does NOT count as enriched.
    """
    contacts = [
        mk_contact("c1", tier="A"),
        mk_contact("c2", tier="B"),
        # Contact with an unknown tier "Z" — orchestrator returns empty,
        # stage's by_tier counter must ignore unknown tiers.
        mk_contact("c3", tier="Z"),
    ]
    storage = FakeStorage(contacts)
    orc = FakeOrchestrator()

    # c1: useful data
    orc.set_response(
        "c1",
        mk_orc(
            "c1",
            "A",
            adapter_results={
                "claude_research": mk_er("claude_research", data={"summary": "x"})
            },
        ),
    )
    # c2: adapter ok but empty data
    orc.set_response(
        "c2",
        mk_orc(
            "c2",
            "B",
            adapter_results={
                "claude_research": mk_er("claude_research", data={}, reason="empty")
            },
        ),
    )
    # c3: no adapter_results at all (unknown_tier from orchestrator)
    orc.set_response(
        "c3",
        mk_orc("c3", "Z", adapter_results={}),
    )

    stage = EnrichStage(orc, storage)
    result = await stage.run(CLIENT)

    assert result.total_enriched == 1
    # Only A + B counted; tier "Z" is untouched for unknown tiers.
    assert result.by_tier == {"A": 1, "B": 1, "C": 0, "D": 0}


# ---------------------------------------------------------------------------
# Extra: summary decision uses the right decision_type + shape
# ---------------------------------------------------------------------------


async def test_summary_decision_type_and_context_shape():
    storage = FakeStorage([])
    orc = FakeOrchestrator()
    stage = EnrichStage(orc, storage)

    await stage.run(CLIENT)

    summaries = [d for d in storage.decisions if d["decision"] == "enrich_stage_summary"]
    assert len(summaries) == 1
    entry = summaries[0]
    assert entry["decision_type"] == "enrichment_choice"
    ctx = entry["context"]
    for key in (
        "client_id",
        "dry_run",
        "total_eligible",
        "total_enriched",
        "total_errored",
        "total_budget_paused",
        "total_cost_cents",
        "by_tier",
        "by_adapter_hit",
        "by_adapter_skip",
    ):
        assert key in ctx


# ---------------------------------------------------------------------------
# Extra: archive_floor threshold passed through to storage
# ---------------------------------------------------------------------------


async def test_archive_floor_passed_to_storage():
    class FloorCapture(FakeStorage):
        def __init__(self, contacts):
            super().__init__(contacts)
            self.floor_seen: int | None = None

        async def get_eligible_contacts_for_enrich(self, client_id, *, archive_floor, limit=None):
            self.floor_seen = archive_floor
            return await super().get_eligible_contacts_for_enrich(
                client_id, archive_floor=archive_floor, limit=limit
            )

    storage = FloorCapture([])
    orc = FakeOrchestrator()
    stage = EnrichStage(orc, storage, archive_floor=50)

    await stage.run(CLIENT)

    assert storage.floor_seen == 50
