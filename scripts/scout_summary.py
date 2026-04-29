"""Scout pipeline summary — render + post the day's enriched contacts.

Per the 2026-04-29 operator request: after a Scout pipeline run, post a
summary of new enriched contacts (decision-makers + emails) to a
notification channel — Telegram for operator-side review (per
``feedback_client_ux``: Telegram is operator-only) OR Slack via webhook
when ``SLACK_WEBHOOK_URL`` is configured. Defaults to stdout when
neither is set.

CSV file is always written to ``data/captures/scout_e2e/`` for audit.
The Telegram path can ALSO upload the CSV as a document attachment via
``--csv-attach``; Slack webhooks can't attach files, so the CSV path is
included as text instead.

Usage:
    uv run python scripts/scout_summary.py --client-id=<id>
        [--since-hours=24] [--channel=telegram|slack|stdout]
        [--csv-attach]

Designed to be cron-able and idempotent — re-running produces a fresh
summary; no DB writes.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


CAPTURE_DIR = _REPO_ROOT / "data" / "captures" / "scout_e2e"

# Columns written to the CSV. Order matters — first columns are the
# operator-facing essentials.
CSV_COLUMNS: tuple[str, ...] = (
    "company", "company_domain", "first_name", "last_name", "title",
    "email", "email_verified", "linkedin_url", "city", "state",
    "geography", "industry", "employees", "icp_score", "icp_tier",
    "status", "source", "source_id", "enriched_at", "created_at",
)


def _get_supabase_client() -> Any:
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit(
            "SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY required in env"
        )
    return create_client(url, key)


def _fetch_recent_enriched(
    client_id: str, since_hours: int,
) -> list[dict[str, Any]]:
    c = _get_supabase_client()
    since = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=since_hours)
    ).isoformat()
    resp = (
        c.table("contacts")
        .select("*")
        .eq("client_id", client_id)
        .gte("created_at", since)
        .order("source")
        .order("created_at")
        .execute()
    )
    return list(resp.data or [])


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            for col in CSV_COLUMNS:
                v = row.get(col)
                if isinstance(v, (dict, list)):
                    row[col] = json.dumps(v)
            w.writerow(row)


def _render_summary(
    rows: list[dict[str, Any]],
    *,
    client_id: str,
    since_hours: int,
    csv_path: Path,
) -> str:
    """Markdown-flavoured summary suitable for Telegram or Slack."""
    if not rows:
        return (
            f"*Scout summary — {client_id}*\n"
            f"No new contacts in the last {since_hours}h."
        )

    enriched = [r for r in rows if r.get("status") == "enriched"]
    archived = [r for r in rows if r.get("status") == "archived"]
    other = [r for r in rows if r.get("status") not in ("enriched", "archived")]

    lines: list[str] = []
    lines.append(f"*Scout summary — {client_id}*")
    lines.append(
        f"_last {since_hours}h: {len(rows)} contacts pulled, "
        f"{len(enriched)} enriched, {len(archived)} archived, "
        f"{len(other)} other_"
    )
    lines.append("")

    if enriched:
        lines.append(f"*✓ {len(enriched)} enriched (decision-makers found):*")
        for r in enriched:
            name = (
                f"{r.get('first_name') or ''} {r.get('last_name') or ''}"
            ).strip() or "(no name)"
            title = r.get("title") or "(no title)"
            email = r.get("email") or "(no email)"
            verified = "✓" if r.get("email_verified") else "?"
            score = r.get("icp_score") or "-"
            tier = r.get("icp_tier") or "-"
            lines.append(
                f"  • *{r.get('company') or '?'}* "
                f"({r.get('city') or '-'}, {r.get('state') or '-'}, "
                f"{r.get('employees') or '-'} emp) — "
                f"{name}, _{title}_ — {email} {verified} — "
                f"score {score}/{tier}"
            )
        lines.append("")

    if archived:
        lines.append(f"*✗ {len(archived)} archived:*")
        for r in archived:
            reason_hint = (
                f"{r.get('employees') or '-'} emp"
                if r.get("employees") and r.get("employees", 0) > 50
                else "(below score floor)"
            )
            lines.append(
                f"  • {r.get('company') or '?'} "
                f"({r.get('city') or '-'}) — {reason_hint}"
            )
        lines.append("")

    lines.append(f"_CSV: `{csv_path}`_")
    return "\n".join(lines)


async def _post_telegram(message: str, csv_path: Path | None) -> None:
    """Post via Telegram bot. Reads TELEGRAM_BOT_TOKEN +
    TELEGRAM_ALLOWED_USER_IDS (first id used as chat_id)."""
    import httpx

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_ids_raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").strip()
    if not token or not chat_ids_raw:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USER_IDS required"
        )
    chat_id = chat_ids_raw.split(",")[0].strip()

    base = f"https://api.telegram.org/bot{token}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Telegram MarkdownV2 has many escapes; use plain "Markdown" for simpler
        # formatting tolerance. Fallback to plain text on failure.
        resp = await client.post(
            f"{base}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
        )
        if resp.status_code != 200:
            # Retry without parse_mode in case of escaping issue
            resp = await client.post(
                f"{base}/sendMessage",
                json={"chat_id": chat_id, "text": message},
            )
        resp.raise_for_status()
        print(f"telegram: posted summary to chat {chat_id}")

        if csv_path and csv_path.exists():
            with csv_path.open("rb") as f:
                files = {"document": (csv_path.name, f, "text/csv")}
                data = {"chat_id": chat_id}
                resp = await client.post(
                    f"{base}/sendDocument", data=data, files=files,
                )
                resp.raise_for_status()
                print(f"telegram: uploaded {csv_path.name}")


async def _post_slack(message: str) -> None:
    """Post to Slack via SLACK_WEBHOOK_URL. Webhooks can't attach files,
    so the CSV path is included as text in the message."""
    import httpx

    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        raise SystemExit("SLACK_WEBHOOK_URL required")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json={"text": message})
        resp.raise_for_status()
        print("slack: posted summary")


async def _run(args: argparse.Namespace) -> int:
    rows = _fetch_recent_enriched(args.client_id, args.since_hours)

    date = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    csv_path = CAPTURE_DIR / f"{date}-{args.client_id}-summary.csv"
    _write_csv(rows, csv_path)

    summary = _render_summary(
        rows, client_id=args.client_id,
        since_hours=args.since_hours, csv_path=csv_path,
    )

    channel = args.channel
    if channel == "auto":
        if os.environ.get("TELEGRAM_BOT_TOKEN"):
            channel = "telegram"
        elif os.environ.get("SLACK_WEBHOOK_URL"):
            channel = "slack"
        else:
            channel = "stdout"

    if channel == "stdout":
        print(summary)
        print(f"\nCSV written to: {csv_path}")
    elif channel == "telegram":
        attach = csv_path if args.csv_attach else None
        await _post_telegram(summary, attach)
    elif channel == "slack":
        await _post_slack(summary)
    else:
        raise SystemExit(f"unknown channel: {channel}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render + post a Scout pipeline summary",
    )
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--since-hours", type=int, default=24)
    parser.add_argument(
        "--channel",
        choices=("auto", "telegram", "slack", "stdout"),
        default="auto",
        help="auto picks telegram if TELEGRAM_BOT_TOKEN set, else slack if "
        "SLACK_WEBHOOK_URL set, else stdout.",
    )
    parser.add_argument(
        "--csv-attach",
        action="store_true",
        help="Telegram only: also upload the CSV as a document.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
