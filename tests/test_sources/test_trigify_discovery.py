"""Tests for TrigifyDiscoverySource — Task 1.5.9b.

Mirrors the httpx.MockTransport pattern from test_trigify_monitors.py. No
FakeTrigifyClient: real AsyncClient + MockTransport so we assert on method /
path / headers / body.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from systems.scout.sources.trigify_discovery import (
    DEFAULT_MAX_LEADS_PER_RUN,
    DEFAULT_MIN_ENGAGEMENT_TO_PULL,
    DiscoveryConfig,
    TrigifyDiscoverySource,
    _build_source_id,
    _infer_monitor_type_from_name_remainder,
    _linkedin_slug,
)


# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                            #
# --------------------------------------------------------------------------- #

@pytest.fixture
def _env(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.setenv("TRIGIFY_API_KEY", "trig-test-key")
    from config.settings import get_settings
    get_settings.cache_clear()


class FakeDiscoveryStorage:
    """In-memory DiscoveryStorage for tests."""

    def __init__(
        self,
        *,
        search_ids: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._search_ids = list(search_ids or [])
        self._config: dict[str, Any] = dict(config or {})
        self.decision_log: list[dict[str, Any]] = []

    async def get_trigify_search_ids(self, client_id: str) -> list[str]:
        return list(self._search_ids)

    async def get_discovery_config(self, client_id: str) -> dict[str, Any]:
        return dict(self._config)

    async def log_decision(
        self, client_id: str, *,
        decision_type: str, decision: str, context: dict[str, Any],
        reasoning: str | None = None, confidence: float | None = None,
    ) -> None:
        self.decision_log.append({
            "client_id": client_id,
            "decision_type": decision_type,
            "decision": decision,
            "context": context,
            "reasoning": reasoning,
            "confidence": confidence,
        })


class _RouteRecorder:
    """Records every request and routes via per-path handlers."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []  # (method, path, query)
        self._searches_body: dict | list = {"searches": []}
        self._results_bodies: dict[str, dict | list] = {}  # search_id -> body
        self._engagers_bodies: dict[str, dict | list] = {}  # post_id -> body
        self._results_errors: dict[str, int] = {}
        self._engagers_errors: dict[str, int] = {}

    def set_searches(self, body: dict | list) -> None:
        self._searches_body = body

    def set_results(self, search_id: str, body: dict | list) -> None:
        self._results_bodies[search_id] = body

    def set_engagers(self, post_id: str, body: dict | list) -> None:
        self._engagers_bodies[post_id] = body

    def set_results_error(self, search_id: str, status: int) -> None:
        self._results_errors[search_id] = status

    def set_engagers_error(self, post_id: str, status: int) -> None:
        self._engagers_errors[post_id] = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        query = dict(parse_qs(request.url.query))
        self.calls.append((request.method, path, query))

        if request.method == "GET" and path == "/v1/searches":
            return httpx.Response(200, json=self._searches_body)

        if request.method == "GET" and path.startswith("/v1/searches/"):
            # /v1/searches/{id}/results
            parts = path.split("/")
            if len(parts) >= 5 and parts[4] == "results":
                sid = parts[3]
                if sid in self._results_errors:
                    return httpx.Response(
                        self._results_errors[sid],
                        json={"error": "boom"},
                    )
                body = self._results_bodies.get(sid, {"results": []})
                return httpx.Response(200, json=body)

        if request.method == "GET" and path.startswith("/v1/posts/"):
            # /v1/posts/{post_id}/engagers
            parts = path.split("/")
            if len(parts) >= 5 and parts[4] == "engagers":
                pid = parts[3]
                if pid in self._engagers_errors:
                    return httpx.Response(
                        self._engagers_errors[pid],
                        json={"error": "boom"},
                    )
                body = self._engagers_bodies.get(pid, {"engagers": []})
                return httpx.Response(200, json=body)

        return httpx.Response(404, json={"error": "not_mocked", "path": path})


def _make_mock_client(recorder: _RouteRecorder) -> httpx.AsyncClient:
    transport = httpx.MockTransport(recorder)
    return httpx.AsyncClient(transport=transport)


def _post(post_id: str, likes: int, *, engaged_at: str = "2026-04-21T12:00:00Z",
          extras: dict[str, Any] | None = None) -> dict[str, Any]:
    p: dict[str, Any] = {
        "id": post_id,
        "engagement": {"likes": likes, "comments": 0, "shares": 0},
        "engaged_at": engaged_at,
        "url": f"https://linkedin.com/posts/{post_id}",
    }
    if extras:
        p.update(extras)
    return p


def _engager(
    handle: str, *, employer: str | None = "Acme Co",
    name: str = "Jane Doe", title: str = "VP Marketing",
) -> dict[str, Any]:
    e: dict[str, Any] = {
        "linkedin_url": f"https://linkedin.com/in/{handle}",
        "name": name,
        "title": title,
    }
    if employer is not None:
        e["employer"] = employer
    return e


# --------------------------------------------------------------------------- #
# 1. Happy path                                                                  #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_happy_path_produces_contacts(_env):
    recorder = _RouteRecorder()
    recorder.set_searches({"searches": [
        {"id": "sid-intent", "name": "[c0]-intent-social-signals"},
        {"id": "sid-comp", "name": "[c0]-competitor-clay-com"},
    ]})
    # intent search: 3 posts — 2 above threshold, 1 below.
    recorder.set_results("sid-intent", {"results": [
        _post("p1", 20, engaged_at="2026-04-21T10:00:00Z"),
        _post("p2", 15, engaged_at="2026-04-21T11:00:00Z"),
        _post("p3", 5, engaged_at="2026-04-21T09:00:00Z"),   # below threshold
    ]})
    # competitor search: 2 posts, both above threshold.
    recorder.set_results("sid-comp", {"results": [
        _post("p4", 50, engaged_at="2026-04-21T12:00:00Z"),
        _post("p5", 30, engaged_at="2026-04-21T13:00:00Z"),
    ]})
    recorder.set_engagers("p1", {"engagers": [_engager("a"), _engager("b")]})
    recorder.set_engagers("p2", {"engagers": [_engager("c")]})
    recorder.set_engagers("p4", {"engagers": [_engager("d")]})
    recorder.set_engagers("p5", {"engagers": [_engager("e")]})

    storage = FakeDiscoveryStorage(search_ids=["sid-intent", "sid-comp"])
    client = _make_mock_client(recorder)
    source = TrigifyDiscoverySource(storage=storage, http_client=client)

    contacts = await source.pull("c0", max_companies=100)

    assert source.last_summary is not None
    s = source.last_summary
    assert s.searches_queried == 2
    assert s.posts_scanned == 5
    assert s.posts_below_threshold == 1
    assert s.posts_qualified == 4
    assert s.engagers_extracted == 5
    assert s.engagers_skipped_no_employer == 0
    assert s.leads_returned == 5
    assert len(contacts) == 5
    # raw_data preserves engager info
    for c in contacts:
        assert c.source == "trigify_discovery"
        assert c.company == "Acme Co"
        assert c.raw_data["engager_name"] == "Jane Doe"
    # Below-threshold post engagers NOT fetched.
    eng_paths = [c for c in recorder.calls if c[1].startswith("/v1/posts/")]
    assert all("/p3/" not in c[1] for c in eng_paths)

    await client.aclose()


# --------------------------------------------------------------------------- #
# 2. DiscoveryConfig defaults                                                    #
# --------------------------------------------------------------------------- #

def test_discovery_config_defaults_from_empty_jsonb():
    c = DiscoveryConfig.from_jsonb(None)
    assert c.min_engagement_to_pull == DEFAULT_MIN_ENGAGEMENT_TO_PULL
    assert c.max_leads_per_run == DEFAULT_MAX_LEADS_PER_RUN
    assert c.cook_time_hours == 24
    assert c.search_subsets_enabled == (
        "intent", "competitor", "thought_leader", "brand",
    )

    c2 = DiscoveryConfig.from_jsonb({})
    assert c2.min_engagement_to_pull == DEFAULT_MIN_ENGAGEMENT_TO_PULL


# --------------------------------------------------------------------------- #
# 3. DiscoveryConfig parses partial overrides                                    #
# --------------------------------------------------------------------------- #

def test_discovery_config_partial_override():
    c = DiscoveryConfig.from_jsonb({"min_engagement_to_pull": 25})
    assert c.min_engagement_to_pull == 25
    # Other fields default.
    assert c.max_leads_per_run == DEFAULT_MAX_LEADS_PER_RUN
    assert c.cook_time_hours == 24


# --------------------------------------------------------------------------- #
# 4. Below-threshold posts skipped, engager endpoint NOT called                  #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_below_threshold_post_not_fetched(_env):
    recorder = _RouteRecorder()
    recorder.set_searches({"searches": [
        {"id": "sid-i", "name": "[c0]-intent-foo"},
    ]})
    recorder.set_results("sid-i", {"results": [
        _post("low-post", 5),   # < 10 threshold
    ]})
    # Important: don't register engagers for low-post — if code tries to
    # fetch it, recorder returns default empty, but we'll also assert the
    # actual HTTP path wasn't called.
    storage = FakeDiscoveryStorage(search_ids=["sid-i"])
    client = _make_mock_client(recorder)
    source = TrigifyDiscoverySource(storage=storage, http_client=client)

    contacts = await source.pull("c0", max_companies=10)
    assert contacts == []

    s = source.last_summary
    assert s.posts_below_threshold == 1
    assert s.posts_qualified == 0

    # Confirm no GET hit the post-engagers endpoint.
    assert not any(
        c[0] == "GET" and c[1].startswith("/v1/posts/low-post/engagers")
        for c in recorder.calls
    )

    await client.aclose()


# --------------------------------------------------------------------------- #
# 5. Engager without employer skipped + logged                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_engager_without_employer_skipped_and_logged(_env):
    recorder = _RouteRecorder()
    recorder.set_searches({"searches": [
        {"id": "sid-i", "name": "[c0]-intent-foo"},
    ]})
    recorder.set_results("sid-i", {"results": [_post("p1", 20)]})
    # First engager no employer; second has one.
    recorder.set_engagers("p1", {"engagers": [
        _engager("a", employer=None),
        _engager("b", employer="RealCo"),
    ]})

    storage = FakeDiscoveryStorage(search_ids=["sid-i"])
    client = _make_mock_client(recorder)
    source = TrigifyDiscoverySource(storage=storage, http_client=client)

    contacts = await source.pull("c0", max_companies=10)
    assert len(contacts) == 1
    assert contacts[0].company == "RealCo"

    s = source.last_summary
    assert s.engagers_extracted == 2
    assert s.engagers_skipped_no_employer == 1

    # decision_log entry fired
    assert any(
        d["decision"] == "engager_skipped:no_employer"
        for d in storage.decision_log
    )

    await client.aclose()


# --------------------------------------------------------------------------- #
# 6. Monitor-type inference from name prefixes                                   #
# --------------------------------------------------------------------------- #

def test_infer_monitor_type_from_name():
    assert (
        _infer_monitor_type_from_name_remainder("intent-social-signals")
        == "intent_keyword"
    )
    assert (
        _infer_monitor_type_from_name_remainder("competitor-clay-com")
        == "competitor_engagement"
    )
    assert (
        _infer_monitor_type_from_name_remainder("thought-leader-nick-saraev")
        == "thought_leader_engagement"
    )
    assert (
        _infer_monitor_type_from_name_remainder("brand-triggery")
        == "brand_mention"
    )
    assert _infer_monitor_type_from_name_remainder("unknown-foo") is None


# --------------------------------------------------------------------------- #
# 7. Subset filter                                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_subset_filter_only_queries_matching_monitors(_env):
    recorder = _RouteRecorder()
    recorder.set_searches({"searches": [
        {"id": "sid-intent", "name": "[c0]-intent-foo"},
        {"id": "sid-comp", "name": "[c0]-competitor-bar"},
        {"id": "sid-tl", "name": "[c0]-thought-leader-baz"},
        {"id": "sid-brand", "name": "[c0]-brand-qux"},
    ]})
    recorder.set_results("sid-intent", {"results": [_post("p1", 20)]})
    recorder.set_results("sid-comp", {"results": [_post("p2", 20)]})
    recorder.set_results("sid-tl", {"results": [_post("p3", 20)]})
    recorder.set_results("sid-brand", {"results": [_post("p4", 20)]})
    for pid in ("p1", "p2", "p3", "p4"):
        recorder.set_engagers(pid, {"engagers": [_engager(f"h-{pid}")]})

    storage = FakeDiscoveryStorage(
        search_ids=["sid-intent", "sid-comp", "sid-tl", "sid-brand"],
    )
    client = _make_mock_client(recorder)
    source = TrigifyDiscoverySource(storage=storage, http_client=client)

    contacts = await source.pull(
        "c0", max_companies=100, search_subset="intent",
    )

    assert len(contacts) == 1
    # Only the intent search results endpoint was hit (plus 1 GET /searches +
    # 1 GET engagers for p1).
    results_calls = [
        c for c in recorder.calls
        if c[0] == "GET" and "/v1/searches/" in c[1] and c[1].endswith("/results")
    ]
    assert len(results_calls) == 1
    assert "sid-intent" in results_calls[0][1]

    await client.aclose()


# --------------------------------------------------------------------------- #
# 8. Dedup within run — first-by-engaged_at-asc wins                             #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dedup_within_run_keeps_first_by_engaged_at(_env):
    recorder = _RouteRecorder()
    recorder.set_searches({"searches": [
        {"id": "sid-i", "name": "[c0]-intent-foo"},
    ]})
    # Two posts in the same search, same engager on both.
    recorder.set_results("sid-i", {"results": [
        _post("p-late", 20, engaged_at="2026-04-21T15:00:00Z"),
        _post("p-early", 20, engaged_at="2026-04-21T09:00:00Z"),
    ]})
    # Same linkedin URL on both posts, with different employer to prove which
    # post won the dedup race.
    recorder.set_engagers("p-late", {"engagers": [
        _engager("jane", employer="LateCo"),
    ]})
    recorder.set_engagers("p-early", {"engagers": [
        _engager("jane", employer="EarlyCo"),
    ]})

    storage = FakeDiscoveryStorage(search_ids=["sid-i"])
    client = _make_mock_client(recorder)
    source = TrigifyDiscoverySource(storage=storage, http_client=client)

    contacts = await source.pull("c0", max_companies=10)

    # After dedup only one; must be the EARLIER one (p-early).
    assert len(contacts) == 1
    assert contacts[0].company == "EarlyCo"
    assert contacts[0].raw_data["post_id"] == "p-early"

    await client.aclose()


# --------------------------------------------------------------------------- #
# 9. source_id format                                                            #
# --------------------------------------------------------------------------- #

def test_source_id_format():
    assert _linkedin_slug("https://linkedin.com/in/jane-doe/") == "jane-doe"
    assert _linkedin_slug("https://linkedin.com/in/jane-doe") == "jane-doe"
    assert _linkedin_slug("https://linkedin.com/company/acme-co/") == "acme-co"
    assert _build_source_id("post-123", "https://linkedin.com/in/jane-doe/") == (
        "trigify:post-123:jane-doe"
    )


# --------------------------------------------------------------------------- #
# 10. raw_data preservation — all 10 fields present                              #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_raw_data_has_all_expected_fields(_env):
    recorder = _RouteRecorder()
    recorder.set_searches({"searches": [
        {"id": "sid-i", "name": "[c0]-intent-social-signals"},
    ]})
    # Post with an intent-keyword query surfaced in `monitor.query`.
    post = _post("p1", 20, engaged_at="2026-04-21T10:00:00Z")
    post["monitor"] = {"query": "social signals"}
    post["url"] = "https://linkedin.com/posts/p1"
    recorder.set_results("sid-i", {"results": [post]})
    recorder.set_engagers("p1", {"engagers": [
        _engager("jane", employer="Acme", name="Jane Q", title="VP Ops"),
    ]})

    storage = FakeDiscoveryStorage(search_ids=["sid-i"])
    client = _make_mock_client(recorder)
    source = TrigifyDiscoverySource(storage=storage, http_client=client)

    contacts = await source.pull("c0", max_companies=10)
    assert len(contacts) == 1

    rd = contacts[0].raw_data
    expected_fields = {
        "engager_linkedin_url", "engager_name", "engager_title",
        "post_id", "post_url", "post_topic", "post_engagement_total",
        "monitor_type", "monitor_search_id", "engaged_at",
    }
    assert expected_fields.issubset(rd.keys())
    assert rd["engager_linkedin_url"] == "https://linkedin.com/in/jane"
    assert rd["engager_name"] == "Jane Q"
    assert rd["engager_title"] == "VP Ops"
    assert rd["post_id"] == "p1"
    assert rd["post_url"] == "https://linkedin.com/posts/p1"
    assert rd["post_topic"] == "social signals"
    assert rd["post_engagement_total"] == 20
    assert rd["monitor_type"] == "intent_keyword"
    assert rd["monitor_search_id"] == "sid-i"
    assert rd["engaged_at"] == "2026-04-21T10:00:00Z"

    await client.aclose()


# --------------------------------------------------------------------------- #
# 11. max_companies cap applied after dedup                                      #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_max_companies_cap(_env):
    recorder = _RouteRecorder()
    recorder.set_searches({"searches": [
        {"id": "sid-i", "name": "[c0]-intent-foo"},
    ]})
    recorder.set_results("sid-i", {"results": [_post("p1", 20)]})
    # 5 distinct engagers all with employers
    recorder.set_engagers("p1", {"engagers": [
        _engager(f"eng-{i}", employer=f"Co-{i}") for i in range(5)
    ]})

    storage = FakeDiscoveryStorage(search_ids=["sid-i"])
    client = _make_mock_client(recorder)
    source = TrigifyDiscoverySource(storage=storage, http_client=client)

    contacts = await source.pull("c0", max_companies=3)
    assert len(contacts) == 3
    assert source.last_summary.leads_returned == 3

    await client.aclose()


# --------------------------------------------------------------------------- #
# 12. Dry-run — reads happen, decision_log fires with dry_run=True flag          #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dry_run_still_reads_and_logs(_env):
    recorder = _RouteRecorder()
    recorder.set_searches({"searches": [
        {"id": "sid-i", "name": "[c0]-intent-foo"},
    ]})
    recorder.set_results("sid-i", {"results": [_post("p1", 20)]})
    recorder.set_engagers("p1", {"engagers": [_engager("x")]})

    storage = FakeDiscoveryStorage(search_ids=["sid-i"])
    client = _make_mock_client(recorder)
    source = TrigifyDiscoverySource(storage=storage, http_client=client)

    contacts = await source.pull("c0", max_companies=10, dry_run=True)

    # All reads still happened:
    assert any(c[1] == "/v1/searches" for c in recorder.calls)
    assert any("/results" in c[1] for c in recorder.calls)
    assert any("/engagers" in c[1] for c in recorder.calls)
    # Contacts returned — caller decides whether to persist.
    assert len(contacts) == 1
    # pull_completed decision log flagged dry_run=True.
    completed = [
        d for d in storage.decision_log if d["decision"] == "pull_completed"
    ]
    assert completed and completed[0]["context"]["dry_run"] is True

    await client.aclose()


# --------------------------------------------------------------------------- #
# 13. Error handling — one search fails, others continue                         #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_one_search_error_does_not_block_others(_env):
    recorder = _RouteRecorder()
    recorder.set_searches({"searches": [
        {"id": "sid-bad", "name": "[c0]-intent-bad"},
        {"id": "sid-good", "name": "[c0]-intent-good"},
    ]})
    recorder.set_results_error("sid-bad", 500)
    recorder.set_results("sid-good", {"results": [_post("p1", 20)]})
    recorder.set_engagers("p1", {"engagers": [_engager("x")]})

    storage = FakeDiscoveryStorage(search_ids=["sid-bad", "sid-good"])
    client = _make_mock_client(recorder)
    source = TrigifyDiscoverySource(storage=storage, http_client=client)

    contacts = await source.pull("c0", max_companies=10)

    assert len(contacts) == 1
    s = source.last_summary
    assert s.errors == 1
    assert s.searches_queried == 1  # only the good one

    # Error-side decision_log entry present.
    assert any(
        d["decision"] == "search_results_failed" for d in storage.decision_log
    )

    await client.aclose()


# --------------------------------------------------------------------------- #
# 14. Empty trigify_search_ids — zero HTTP calls                                 #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_empty_search_ids_returns_immediately(_env):
    recorder = _RouteRecorder()
    storage = FakeDiscoveryStorage(search_ids=[])
    client = _make_mock_client(recorder)
    source = TrigifyDiscoverySource(storage=storage, http_client=client)

    contacts = await source.pull("c0", max_companies=10)

    assert contacts == []
    assert recorder.calls == []
    assert source.last_summary.searches_queried == 0

    await client.aclose()
