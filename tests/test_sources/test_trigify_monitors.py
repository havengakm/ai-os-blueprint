"""Tests for TrigifyMonitorCreator — Task 1.5.9a.

Uses httpx.MockTransport so the real AsyncClient builds actual requests and
we can assert on method / path / headers / body. No FakeTrigifyClient.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from systems.scout.sources.trigify_monitors import (
    MonitorSpec,
    TrigifyMonitorCreator,
    _build_specs_from_yaml,
    _slugify,
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


def _full_yaml() -> dict:
    """Five specs: 2 intent + 1 competitor + 1 thought_leader + 1 brand."""
    return {
        "intent_keywords": [
            {
                "phrase": "social signals",
                "scope_terms": ["gtm", "outbound"],
                "platforms": ["linkedin"],
            },
            {
                "phrase": "buying intent data",
            },
        ],
        "competitors": [
            {
                "name": "Clay.com",
                "linkedin_url": "https://linkedin.com/company/clay-labs",
            },
        ],
        "thought_leaders": [
            {
                "name": "Nick Saraev",
                "linkedin_url": "https://linkedin.com/in/nicksaraev",
            },
        ],
        "brand": ["Triggery"],
    }


class _RouteRecorder:
    """Records every request and routes via a handler table."""

    def __init__(
        self,
        list_searches_body: dict | list,
        post_responder,
    ) -> None:
        """list_searches_body: response JSON for GET /v1/searches.
        post_responder: callable(request_body_dict) -> (status_code, resp_body).
        """
        self._list_body = list_searches_body
        self._post_responder = post_responder
        self.calls: list[tuple[str, str, dict]] = []  # (method, path, headers)
        self.post_bodies: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        headers = dict(request.headers)
        self.calls.append((request.method, request.url.path, headers))

        if request.method == "GET" and request.url.path == "/v1/searches":
            return httpx.Response(200, json=self._list_body)

        if request.method == "POST" and request.url.path == "/v1/searches":
            body = json.loads(request.content.decode("utf-8"))
            self.post_bodies.append(body)
            status, resp = self._post_responder(body)
            return httpx.Response(status, json=resp)

        return httpx.Response(404, json={"error": "not_mocked"})


def _make_mock_client(handler: _RouteRecorder) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def _fake_storage() -> AsyncMock:
    storage = AsyncMock()
    storage.update_trigify_search_ids = AsyncMock(return_value=None)
    return storage


# --------------------------------------------------------------------------- #
# 1. Parse YAML → build specs correctly                                         #
# --------------------------------------------------------------------------- #

def test_build_specs_parses_all_sections(_env):
    specs = _build_specs_from_yaml("kirsten-client-zero", _full_yaml())
    assert len(specs) == 5

    # Preserve section order: intent_keywords first, then competitors, etc.
    by_section = [s.source_yaml_section for s in specs]
    assert by_section == [
        "intent_keywords", "intent_keywords",
        "competitors", "thought_leaders", "brand",
    ]

    # Intent keyword #1: scope_terms folded into query, custom platforms.
    s0 = specs[0]
    assert s0.monitor_type == "intent_keyword"
    assert s0.name == "[kirsten-client-zero]-intent-social-signals"
    assert s0.trigify_payload["query"] == "social signals gtm outbound"
    assert s0.trigify_payload["platforms"] == ["linkedin"]

    # Intent keyword #2: default platforms applied.
    s1 = specs[1]
    assert s1.trigify_payload["platforms"] == ["linkedin", "x"]

    # Competitor: payload is target_url only.
    s2 = specs[2]
    assert s2.monitor_type == "competitor_engagement"
    assert s2.name == "[kirsten-client-zero]-competitor-clay-com"
    assert s2.trigify_payload == {
        "target_url": "https://linkedin.com/company/clay-labs",
    }

    # Thought leader:
    s3 = specs[3]
    assert s3.monitor_type == "thought_leader_engagement"
    assert s3.name == "[kirsten-client-zero]-thought-leader-nick-saraev"

    # Brand: payload is query + platforms.
    s4 = specs[4]
    assert s4.monitor_type == "brand_mention"
    assert s4.name == "[kirsten-client-zero]-brand-triggery"
    assert s4.trigify_payload["query"] == "Triggery"


# --------------------------------------------------------------------------- #
# 2. Malformed YAML raises ValueError                                           #
# --------------------------------------------------------------------------- #

def test_malformed_competitor_raises_value_error(_env):
    bad = {
        "competitors": [
            {"name": "Clay.com"},  # missing linkedin_url
        ],
    }
    with pytest.raises(ValueError) as exc:
        _build_specs_from_yaml("c0", bad)
    msg = str(exc.value)
    assert "competitors[0]" in msg
    assert "linkedin_url" in msg


def test_malformed_intent_keyword_raises_value_error(_env):
    bad = {
        "intent_keywords": [
            {"scope_terms": ["gtm"]},  # missing phrase
        ],
    }
    with pytest.raises(ValueError) as exc:
        _build_specs_from_yaml("c0", bad)
    assert "intent_keywords[0]" in str(exc.value)
    assert "phrase" in str(exc.value)


# --------------------------------------------------------------------------- #
# 3. Dry-run does NOT hit Trigify                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dry_run_no_http_calls(_env):
    recorder = _RouteRecorder([], lambda body: (200, {"id": "unused"}))
    client = _make_mock_client(recorder)
    storage = _fake_storage()
    creator = TrigifyMonitorCreator(storage=storage, http_client=client)

    result = await creator.provision_from_yaml(
        "kirsten-client-zero", _full_yaml(), dry_run=True,
    )

    assert recorder.calls == []
    assert result.created == []
    assert result.skipped_existing == []
    assert result.failed == []
    storage.update_trigify_search_ids.assert_not_called()

    await client.aclose()


# --------------------------------------------------------------------------- #
# 4. Dry-run returns dry_run_planned list                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dry_run_returns_planned_specs(_env):
    recorder = _RouteRecorder([], lambda body: (200, {"id": "unused"}))
    client = _make_mock_client(recorder)
    storage = _fake_storage()
    creator = TrigifyMonitorCreator(storage=storage, http_client=client)

    result = await creator.provision_from_yaml(
        "c0", _full_yaml(), dry_run=True,
    )

    assert len(result.dry_run_planned) == 5
    assert all(isinstance(s, MonitorSpec) for s in result.dry_run_planned)
    await client.aclose()


# --------------------------------------------------------------------------- #
# 5. Happy path: all new monitors created                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_happy_path_creates_all_and_persists(_env):
    counter = {"n": 0}

    def _post(body):
        counter["n"] += 1
        return 200, {"id": f"sid-{counter['n']}", "name": body["name"]}

    recorder = _RouteRecorder(
        list_searches_body={"searches": []},
        post_responder=_post,
    )
    client = _make_mock_client(recorder)
    storage = _fake_storage()
    creator = TrigifyMonitorCreator(storage=storage, http_client=client)

    result = await creator.provision_from_yaml("c0", _full_yaml())

    assert len(result.created) == 5
    assert result.skipped_existing == []
    assert result.failed == []
    assert len(result.all_search_ids) == 5
    assert result.all_search_ids == [f"sid-{i}" for i in range(1, 6)]

    # update called exactly once with the full list
    storage.update_trigify_search_ids.assert_called_once_with(
        "c0", [f"sid-{i}" for i in range(1, 6)],
    )

    # GET once + POST five times
    methods = [c[0] for c in recorder.calls]
    assert methods.count("GET") == 1
    assert methods.count("POST") == 5

    await client.aclose()


# --------------------------------------------------------------------------- #
# 6. Idempotency: existing monitors skipped                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_idempotency_skips_existing_matches(_env):
    counter = {"n": 100}

    def _post(body):
        counter["n"] += 1
        return 200, {"id": f"sid-{counter['n']}", "name": body["name"]}

    # Pre-existing: the 1st intent keyword + the competitor.
    existing_list = {
        "searches": [
            {
                "id": "existing-1",
                "name": "[c0]-intent-social-signals",
            },
            {
                "id": "existing-2",
                "name": "[c0]-competitor-clay-com",
            },
        ],
    }
    recorder = _RouteRecorder(
        list_searches_body=existing_list,
        post_responder=_post,
    )
    client = _make_mock_client(recorder)
    storage = _fake_storage()
    creator = TrigifyMonitorCreator(storage=storage, http_client=client)

    result = await creator.provision_from_yaml("c0", _full_yaml())

    assert len(result.skipped_existing) == 2
    skipped_names = {n for n, _ in result.skipped_existing}
    assert skipped_names == {
        "[c0]-intent-social-signals",
        "[c0]-competitor-clay-com",
    }
    assert len(result.created) == 3  # 5 - 2 skipped
    assert result.failed == []
    assert len(result.all_search_ids) == 5

    # Only 3 POSTs fired (the new ones).
    methods = [c[0] for c in recorder.calls]
    assert methods.count("POST") == 3

    await client.aclose()


# --------------------------------------------------------------------------- #
# 7. Partial failure handling                                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_partial_failure_records_failures_commits_successes(_env):
    counter = {"n": 0}

    def _post(body):
        counter["n"] += 1
        # Fail the competitor POST specifically.
        if "competitor" in body["name"]:
            return 500, {"error": "internal_server_error"}
        return 200, {"id": f"sid-{counter['n']}", "name": body["name"]}

    recorder = _RouteRecorder(
        list_searches_body={"searches": []},
        post_responder=_post,
    )
    client = _make_mock_client(recorder)
    storage = _fake_storage()
    creator = TrigifyMonitorCreator(storage=storage, http_client=client)

    result = await creator.provision_from_yaml("c0", _full_yaml())

    # 4 of 5 succeed, 1 fails.
    assert len(result.created) == 4
    assert len(result.failed) == 1
    failed_name = result.failed[0][0]
    assert "competitor" in failed_name
    assert "500" in result.failed[0][1]

    # Storage STILL gets the 4 successful IDs.
    storage.update_trigify_search_ids.assert_called_once()
    _, args, _ = storage.update_trigify_search_ids.mock_calls[0]
    client_arg, ids_arg = args
    assert client_arg == "c0"
    assert len(ids_arg) == 4

    await client.aclose()


# --------------------------------------------------------------------------- #
# 8. Name collisions across clients — other clients' monitors ignored           #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_other_client_monitors_are_filtered_out(_env):
    def _post(body):
        return 200, {"id": "sid-new", "name": body["name"]}

    # Another client's monitor with a name that could "collide" on suffix but
    # has the wrong prefix — must NOT be treated as existing for c0.
    existing_list = {
        "searches": [
            {
                "id": "other-1",
                "name": "[other-client]-intent-social-signals",
            },
        ],
    }
    recorder = _RouteRecorder(
        list_searches_body=existing_list,
        post_responder=_post,
    )
    client = _make_mock_client(recorder)
    storage = _fake_storage()
    creator = TrigifyMonitorCreator(storage=storage, http_client=client)

    result = await creator.provision_from_yaml(
        "c0",
        {
            "intent_keywords": [
                {"phrase": "social signals"},
            ],
        },
    )

    # Not skipped — other-client's monitor is irrelevant to c0.
    assert result.skipped_existing == []
    assert len(result.created) == 1
    assert result.created[0][0] == "[c0]-intent-social-signals"

    await client.aclose()


# --------------------------------------------------------------------------- #
# 9. No API key configured                                                      #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_missing_api_key_raises_environment_error(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "test")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("CRON_SECRET", "test-cron")
    monkeypatch.delenv("TRIGIFY_API_KEY", raising=False)
    from config.settings import get_settings
    get_settings.cache_clear()

    recorder = _RouteRecorder(
        list_searches_body={"searches": []},
        post_responder=lambda b: (200, {"id": "x"}),
    )
    client = _make_mock_client(recorder)
    storage = _fake_storage()
    creator = TrigifyMonitorCreator(storage=storage, http_client=client)

    with pytest.raises(EnvironmentError) as exc:
        await creator.provision_from_yaml("c0", _full_yaml())
    assert "TRIGIFY_API_KEY" in str(exc.value)

    # No HTTP call made, no persistence.
    assert recorder.calls == []
    storage.update_trigify_search_ids.assert_not_called()

    await client.aclose()


# --------------------------------------------------------------------------- #
# 10. Auth header correctness                                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_auth_header_present_on_every_call(_env):
    def _post(body):
        return 200, {"id": "sid-x", "name": body["name"]}

    recorder = _RouteRecorder(
        list_searches_body={"searches": []},
        post_responder=_post,
    )
    client = _make_mock_client(recorder)
    storage = _fake_storage()
    creator = TrigifyMonitorCreator(storage=storage, http_client=client)

    await creator.provision_from_yaml("c0", _full_yaml())

    assert len(recorder.calls) == 6  # 1 GET + 5 POST
    for method, path, headers in recorder.calls:
        assert headers.get("x-api-key") == "trig-test-key", (
            f"auth header missing on {method} {path}"
        )

    await client.aclose()


# --------------------------------------------------------------------------- #
# 11. Slug generation                                                           #
# --------------------------------------------------------------------------- #

def test_slugify_deterministic_and_url_safe():
    assert _slugify("social signals in GTM") == "social-signals-in-gtm"
    assert _slugify("Clay.com") == "clay-com"
    assert _slugify("Nick Saraev") == "nick-saraev"
    assert _slugify("Multiple   spaces") == "multiple-spaces"
    assert _slugify("Leading/trailing!!") == "leading-trailing"
    # Determinism
    assert _slugify("social signals") == _slugify("social signals")


# --------------------------------------------------------------------------- #
# 12. Max 40-char slug truncation, word-boundary preserved                      #
# --------------------------------------------------------------------------- #

def test_slug_truncated_at_word_boundary_under_40():
    long_phrase = "this is a really long intent keyword phrase that exceeds forty chars"
    slug = _slugify(long_phrase)
    assert len(slug) <= 40
    # Must end on a complete word, not mid-word.
    assert not slug.endswith("-")
    # Must be a prefix of the full kebab-cased string.
    full = "this-is-a-really-long-intent-keyword-phrase-that-exceeds-forty-chars"
    assert full.startswith(slug)
    # Next char in full (after slug) must be a dash — proving word boundary.
    assert full[len(slug)] == "-"
