"""Tests for scripts/run_trigify_discovery.py."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.run_trigify_discovery as mod  # noqa: E402
from aios.scout.pipeline.pull import PullResult, SourceSummary  # noqa: E402
from aios.scout.sources.base import RawCompanyContact  # noqa: E402
from aios.scout.sources.trigify_discovery import DiscoverySummary  # noqa: E402


class _FakeSource:
    """Stand-in for TrigifyDiscoverySource — records pull() args, returns a canned list."""

    name = "trigify_discovery"

    def __init__(self, contacts: list[RawCompanyContact] | None = None) -> None:
        self._contacts = contacts or []
        self.pull_calls: list[dict[str, Any]] = []
        self.last_summary: DiscoverySummary | None = None

    async def pull(
        self,
        client_id: str,
        max_companies: int,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> list[RawCompanyContact]:
        self.pull_calls.append({
            "client_id": client_id,
            "max_companies": max_companies,
            "dry_run": dry_run,
            "kwargs": dict(kwargs),
        })
        self.last_summary = DiscoverySummary(
            searches_queried=2,
            posts_qualified=3,
            engagers_extracted=len(self._contacts),
            leads_returned=len(self._contacts),
            by_monitor_type={"intent_keyword": len(self._contacts)},
        )
        return list(self._contacts)


class _FakeOrchestrator:
    """Stand-in for PullOrchestrator — records run() args."""

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter
        self.run_calls: list[dict[str, Any]] = []

    async def run(
        self,
        client_id: str,
        *,
        max_companies_per_source: int,
        dry_run: bool,
        source_filter: list[str] | None = None,
        adapter_kwargs: dict[str, dict[str, Any]] | None = None,
    ) -> PullResult:
        self.run_calls.append({
            "client_id": client_id,
            "max_companies_per_source": max_companies_per_source,
            "dry_run": dry_run,
            "source_filter": list(source_filter) if source_filter else None,
            "adapter_kwargs": adapter_kwargs,
        })
        return PullResult(
            client_id=client_id,
            dry_run=dry_run,
            total_pulled=1, total_inserted=1, total_skipped_duplicate=0,
            per_source=[SourceSummary(
                adapter_name=self.adapter.name, pulled=1, inserted=1,
            )],
        )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("TRIGIFY_API_KEY", "test-trigify-key")


def _redirect_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> Path:
    """Force the CLI to write reports under tmp_path, not the real data/reports/."""
    target = tmp_path / "reports"
    monkeypatch.setattr(mod, "_reports_dir", lambda: target)
    return target


def _patch_deps(
    monkeypatch: pytest.MonkeyPatch,
    source: _FakeSource,
    orchestrator: _FakeOrchestrator | None = None,
) -> list[_FakeOrchestrator]:
    """Wire fakes in place of Supabase + TrigifyDiscoverySource + orchestrator."""
    monkeypatch.setattr(mod, "_build_supabase", lambda url, key: object())
    monkeypatch.setattr(
        mod, "TrigifyDiscoverySource",
        lambda storage=None, **_kw: source,
    )
    monkeypatch.setattr(
        mod, "SupabaseDiscoveryStorage", lambda _client: object(),
    )
    monkeypatch.setattr(
        mod, "SupabasePullBackend", lambda _client: object(),
    )
    # Capture orchestrator instances so tests can assert on them.
    created: list[_FakeOrchestrator] = []

    def _factory(adapters: dict[str, Any], storage: Any) -> _FakeOrchestrator:
        # PullOrchestrator now takes a dict[routing_key, adapter]; the
        # production caller in run_trigify_discovery.py passes one entry.
        first_adapter = next(iter(adapters.values()))
        o = orchestrator or _FakeOrchestrator(first_adapter)
        created.append(o)
        return o

    monkeypatch.setattr(mod, "PullOrchestrator", _factory)
    return created


def _contact() -> RawCompanyContact:
    return RawCompanyContact(
        company="Acme Corp", company_domain="acme.com",
        source="trigify_discovery",
        source_id="trigify:post-1:jane-doe",
        raw_data={
            "engager_name": "Jane Doe",
            "engager_title": "VP Marketing",
            "engager_linkedin_url": "https://linkedin.com/in/jane-doe",
            "monitor_type": "intent_keyword",
            "post_engagement_total": 42,
        },
    )


# --------------------------------------------------------------------------- #
# Help                                                                         #
# --------------------------------------------------------------------------- #


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        mod.main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--client-id" in captured.out
    assert "--search-subset" in captured.out
    assert "--max-companies" in captured.out
    assert "--dry-run" in captured.out


# --------------------------------------------------------------------------- #
# Dry-run                                                                      #
# --------------------------------------------------------------------------- #


def test_dry_run_writes_report_and_skips_orchestrator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    reports_dir = _redirect_reports(monkeypatch, tmp_path)
    source = _FakeSource(contacts=[_contact()])
    orchestrators = _patch_deps(monkeypatch, source)

    rc = mod.main([
        "--client-id=c1",
        "--dry-run",
    ])

    assert rc == 0
    # source.pull called with dry_run=True, search_subset NOT in kwargs.
    assert len(source.pull_calls) == 1
    call = source.pull_calls[0]
    assert call["dry_run"] is True
    assert "search_subset" not in call["kwargs"]

    # No PullOrchestrator ever instantiated on a dry-run.
    assert orchestrators == []

    # Report file exists and mentions the summary.
    report_files = list(reports_dir.glob("trigify-discovery-*.md"))
    assert len(report_files) == 1
    content = report_files[0].read_text()
    assert "Trigify discovery report" in content
    assert "leads_returned: 1" in content
    assert "Acme Corp" in content


# --------------------------------------------------------------------------- #
# Search-subset forwarding                                                     #
# --------------------------------------------------------------------------- #


def test_search_subset_forwarded_to_source_pull(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    _redirect_reports(monkeypatch, tmp_path)
    source = _FakeSource(contacts=[_contact()])
    _patch_deps(monkeypatch, source)

    rc = mod.main([
        "--client-id=c1",
        "--search-subset=intent",
        "--dry-run",
    ])

    assert rc == 0
    assert source.pull_calls[0]["kwargs"].get("search_subset") == "intent"


# --------------------------------------------------------------------------- #
# Live run hits PullOrchestrator                                               #
# --------------------------------------------------------------------------- #


def test_live_run_calls_orchestrator_with_source_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    reports_dir = _redirect_reports(monkeypatch, tmp_path)
    source = _FakeSource(contacts=[_contact()])
    orchestrators = _patch_deps(monkeypatch, source)

    rc = mod.main([
        "--client-id=c1",
        "--max-companies=50",
    ])

    assert rc == 0
    # One orchestrator was created and run.
    assert len(orchestrators) == 1
    orch = orchestrators[0]
    assert len(orch.run_calls) == 1
    run_call = orch.run_calls[0]
    assert run_call["client_id"] == "c1"
    assert run_call["max_companies_per_source"] == 50
    assert run_call["dry_run"] is False
    assert run_call["source_filter"] == [source.name]

    # The source pull was NOT called a second time — orchestrator got the
    # cached adapter wrapping the already-pulled list.
    assert len(source.pull_calls) == 1
    assert source.pull_calls[0]["dry_run"] is False

    # Report still written.
    report_files = list(reports_dir.glob("trigify-discovery-*.md"))
    assert len(report_files) == 1
    content = report_files[0].read_text()
    assert "PullOrchestrator result" in content
    assert "total_inserted: 1" in content


# --------------------------------------------------------------------------- #
# Missing env vars                                                             #
# --------------------------------------------------------------------------- #


def test_missing_trigify_api_key_exits_one(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.delenv("TRIGIFY_API_KEY", raising=False)

    rc = mod.main(["--client-id=c1", "--dry-run"])

    assert rc == 1
    err = capsys.readouterr().err
    assert "TRIGIFY_API_KEY" in err


def test_invalid_search_subset_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _set_env(monkeypatch)
    with pytest.raises(SystemExit) as exc_info:
        mod.main([
            "--client-id=c1",
            "--search-subset=not-a-subset",
            "--dry-run",
        ])
    assert exc_info.value.code != 0
    err = capsys.readouterr().err
    assert "search-subset" in err or "choose from" in err
