"""Tests for scripts/ingest_preresolved_contacts.py."""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ingest_preresolved_contacts import (  # noqa: E402
    INITIAL_STATUS,
    PRE_RESOLVED_ICP_SCORE,
    PRE_RESOLVED_ICP_TIER,
    SOURCE_NAME,
    _row_to_contact,
    ingest_preresolved,
    main,
)


# ── Fake Supabase client ─────────────────────────────────────────────────────

@dataclass
class _FakeResult:
    data: list[dict[str, Any]] = field(default_factory=list)


class _FakeQuery:
    def __init__(self, parent: "FakeSupabase", table_name: str) -> None:
        self._parent = parent
        self._table = table_name
        self._op: str | None = None
        self._upsert_payload: dict[str, Any] | None = None
        self._on_conflict: str | None = None

    def upsert(
        self, payload: dict[str, Any], on_conflict: str | None = None
    ) -> "_FakeQuery":
        self._op = "upsert"
        self._upsert_payload = payload
        self._on_conflict = on_conflict
        return self

    def execute(self) -> _FakeResult:
        if self._op == "upsert":
            assert self._upsert_payload is not None
            self._parent._upsert_calls.append(
                {
                    "table": self._table,
                    "payload": self._upsert_payload,
                    "on_conflict": self._on_conflict,
                }
            )
            return _FakeResult(data=[self._upsert_payload])
        raise RuntimeError(f"Unknown op: {self._op}")


class FakeSupabase:
    def __init__(self) -> None:
        self._upsert_calls: list[dict[str, Any]] = []

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self, name)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_row() -> dict[str, str]:
    return {
        "company": "Wildish & Co.",
        "domain": "wildishandco.co.uk",
        "linkedin_url": "https://www.linkedin.com/in/janedoe",
        "first_name": "Jane",
        "last_name": "Doe",
        "title": "Head of Growth",
        "email": "jane@wildishandco.co.uk",
        "short_company_name": "Wildish",
        "niche": "cro_growth_ugc_agency",
        "notes": "Mentioned new VP of Marketing hired last month.",
    }


# ── _row_to_contact ───────────────────────────────────────────────────────────

def test_happy_path_payload_shape(sample_row: dict[str, str]) -> None:
    payload = _row_to_contact(sample_row, client_id="client-zero")
    assert payload is not None

    # top-level identity
    assert payload["client_id"] == "client-zero"
    assert payload["source"] == SOURCE_NAME
    assert payload["source"] == "manual_pre_resolved"
    assert payload["source_id"] == "jane@wildishandco.co.uk"
    assert payload["first_name"] == "Jane"
    assert payload["last_name"] == "Doe"
    assert payload["title"] == "Head of Growth"
    assert payload["email"] == "jane@wildishandco.co.uk"
    assert payload["linkedin_url"] == "https://www.linkedin.com/in/janedoe"
    assert payload["company"] == "Wildish & Co."
    assert payload["company_domain"] == "wildishandco.co.uk"
    assert payload["niche"] == "cro_growth_ugc_agency"

    # stage gating
    assert payload["status"] == INITIAL_STATUS == "screened"
    assert payload["icp_score"] == PRE_RESOLVED_ICP_SCORE == 75
    assert payload["icp_tier"] == PRE_RESOLVED_ICP_TIER == "A"

    # enriched_at must NOT be in the payload (enrich filter is IS NULL)
    assert "enriched_at" not in payload

    # research_data shape
    rd = payload["research_data"]
    assert rd["short_company_name"] == "Wildish"
    assert rd["citable_details"] == []

    # raw_data has operator_notes
    assert payload["raw_data"]["operator_notes"] == (
        "Mentioned new VP of Marketing hired last month."
    )


def test_row_missing_email_returns_none(sample_row: dict[str, str]) -> None:
    sample_row["email"] = ""
    assert _row_to_contact(sample_row, client_id="c1") is None


def test_row_missing_email_whitespace_returns_none(sample_row: dict[str, str]) -> None:
    sample_row["email"] = "   "
    assert _row_to_contact(sample_row, client_id="c1") is None


def test_row_missing_first_name_returns_none(sample_row: dict[str, str]) -> None:
    sample_row["first_name"] = ""
    assert _row_to_contact(sample_row, client_id="c1") is None


def test_row_missing_first_name_whitespace_returns_none(
    sample_row: dict[str, str],
) -> None:
    sample_row["first_name"] = "  "
    assert _row_to_contact(sample_row, client_id="c1") is None


def test_empty_notes_omits_operator_notes(sample_row: dict[str, str]) -> None:
    sample_row["notes"] = ""
    payload = _row_to_contact(sample_row, client_id="c1")
    assert payload is not None
    assert "operator_notes" not in payload["raw_data"]


def test_empty_short_company_name_omits_from_research(
    sample_row: dict[str, str],
) -> None:
    sample_row["short_company_name"] = ""
    payload = _row_to_contact(sample_row, client_id="c1")
    assert payload is not None
    assert "short_company_name" not in payload["research_data"]
    # citable_details placeholder is still there for enrich stage to populate
    assert payload["research_data"]["citable_details"] == []


def test_niche_flows_through_per_row(sample_row: dict[str, str]) -> None:
    sample_row["niche"] = "b2b_saas_founders"
    payload = _row_to_contact(sample_row, client_id="c1")
    assert payload is not None
    assert payload["niche"] == "b2b_saas_founders"


# ── ingest_preresolved ───────────────────────────────────────────────────────

def test_ingest_happy_path_writes_one_upsert(sample_row: dict[str, str]) -> None:
    fake = FakeSupabase()
    summary = ingest_preresolved(fake, [sample_row], client_id="client-zero")

    assert summary == {"loaded": 1, "skipped": 0, "errors": 0}
    assert len(fake._upsert_calls) == 1
    call = fake._upsert_calls[0]
    assert call["table"] == "contacts"
    assert call["on_conflict"] == "client_id,source,source_id"
    assert call["payload"]["source_id"] == "jane@wildishandco.co.uk"
    assert call["payload"]["status"] == "screened"
    assert "enriched_at" not in call["payload"]


def test_ingest_skips_missing_email(sample_row: dict[str, str]) -> None:
    fake = FakeSupabase()
    bad = dict(sample_row, email="")
    summary = ingest_preresolved(fake, [sample_row, bad], client_id="c1")

    assert summary == {"loaded": 1, "skipped": 1, "errors": 0}
    assert len(fake._upsert_calls) == 1


def test_ingest_skips_missing_first_name(sample_row: dict[str, str]) -> None:
    fake = FakeSupabase()
    bad = dict(sample_row, first_name="", email="other@example.com")
    summary = ingest_preresolved(fake, [sample_row, bad], client_id="c1")

    assert summary == {"loaded": 1, "skipped": 1, "errors": 0}
    # only the good row was upserted
    assert len(fake._upsert_calls) == 1
    assert fake._upsert_calls[0]["payload"]["first_name"] == "Jane"


def test_ingest_notes_pass_through(sample_row: dict[str, str]) -> None:
    fake = FakeSupabase()
    ingest_preresolved(fake, [sample_row], client_id="c1")
    payload = fake._upsert_calls[0]["payload"]
    assert payload["raw_data"]["operator_notes"] == (
        "Mentioned new VP of Marketing hired last month."
    )


def test_ingest_dry_run_does_not_write(sample_row: dict[str, str]) -> None:
    fake = FakeSupabase()
    # mix one valid + one skipped to confirm summary accuracy
    bad = dict(sample_row, email="")
    summary = ingest_preresolved(
        fake, [sample_row, bad], client_id="c1", dry_run=True,
    )
    assert summary == {"loaded": 1, "skipped": 1, "errors": 0}
    assert fake._upsert_calls == []


def test_ingest_upsert_error_counted(sample_row: dict[str, str]) -> None:
    class _BoomQuery:
        def upsert(self, *_args: Any, **_kw: Any) -> "_BoomQuery":
            return self
        def execute(self) -> Any:
            raise RuntimeError("db down")

    class _BoomSupabase:
        def table(self, _name: str) -> Any:
            return _BoomQuery()

    summary = ingest_preresolved(_BoomSupabase(), [sample_row], client_id="c1")
    assert summary == {"loaded": 0, "skipped": 0, "errors": 1}


# ── main() CLI surface ───────────────────────────────────────────────────────

def _write_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "preresolved.csv"
    fieldnames = [
        "company", "domain", "linkedin_url", "first_name", "last_name",
        "title", "email", "short_company_name", "niche", "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return path


def test_main_missing_env_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    sample_row: dict[str, str],
) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    csv_path = _write_csv(tmp_path, [sample_row])
    rc = main(["--csv-path", str(csv_path), "--client-id", "c1"])

    assert rc == 2
    captured = capsys.readouterr()
    assert "SUPABASE_URL" in captured.err
    assert "SUPABASE_SERVICE_ROLE_KEY" in captured.err


def test_main_csv_missing_exits_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    missing = tmp_path / "does_not_exist.csv"
    rc = main(["--csv-path", str(missing), "--client-id", "c1"])

    assert rc == 2
    captured = capsys.readouterr()
    assert "CSV not found" in captured.err


def test_main_with_injected_fake_client_returns_0(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    sample_row: dict[str, str],
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")

    fake = FakeSupabase()
    import scripts.ingest_preresolved_contacts as mod
    monkeypatch.setattr(mod, "_build_client", lambda url, key: fake)

    csv_path = _write_csv(tmp_path, [sample_row])
    rc = main(["--csv-path", str(csv_path), "--client-id", "c1"])

    assert rc == 0
    captured = capsys.readouterr()
    assert "1 loaded" in captured.out
    assert "0 skipped" in captured.out
    assert "0 errors" in captured.out
    assert len(fake._upsert_calls) == 1


def test_main_dry_run_does_not_touch_env(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    sample_row: dict[str, str],
) -> None:
    # Even without env, --dry-run must succeed.
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    csv_path = _write_csv(tmp_path, [sample_row])
    rc = main(["--csv-path", str(csv_path), "--client-id", "c1", "--dry-run"])

    assert rc == 0
    captured = capsys.readouterr()
    assert "DRY-RUN" in captured.out
    assert "1 loaded" in captured.out
