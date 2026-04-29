---
name: Build a Scout source adapter for a Cloudflare-protected directory
description: Reusable pattern for scraping sites behind Cloudflare IUAM ("Just a moment..." JS challenge) — Clutch, DesignRush, GoodFirms, and similar B2B directories. Uses Playwright + playwright-stealth + headed Chrome + ICP-tuned wait timing. Vanilla httpx and vanilla headless Playwright BOTH fail. Canonical reference implementation is `systems/scout/sources/clutch.py`.
when-to-use: Adding a new pull-stage `CompanySourceAdapter` for a directory whose listing pages are protected by Cloudflare's "Just a moment..." JavaScript challenge OR that returns HTTP 403 to plain httpx. Verify the block first with the diagnostic curl in step 1 — if the site responds 200 to plain curl, use plain httpx; the heavyweight Playwright path is reserved for Cloudflare-protected sources.
trigger: Operator authoring a new source adapter; OR Slice 14 of 2026-04-29 surfacing the same 403 pattern on a different directory.
---

# Build a Scout source adapter for a Cloudflare-protected directory

Cloudflare's "I'm Under Attack Mode" / Bot Fight Mode protects most modern B2B
directories (Clutch, DesignRush, GoodFirms, etc.). It serves a `Just a moment...`
JavaScript challenge that:

- Returns HTTP 403 to any non-browser TLS fingerprint (httpx, requests, plain curl).
- Returns HTTP 403 + a 30KB challenge page to vanilla **headless** Playwright too.
- Resolves cleanly when a real Chrome browser receives it — but only when the
  automation flags are masked (stealth) and the browser runs **headed** (visible
  window or xvfb-virtual display).

This playbook captures the four-ingredient pattern that bypasses it.

---

## Preconditions

Before invoking, verify:

1. `playwright>=1.48.0` and `playwright-stealth>=2.0.0` in `pyproject.toml`.
2. Playwright browsers installed locally: `uv run playwright install chromium`.
3. A real or virtual display available:
   - Operator workstation: `echo $DISPLAY` returns a value (e.g. `:0`).
   - Server / cron: wrap the runtime in `xvfb-run` (Linux) — see Server Use below.
4. A reference implementation to mirror: `systems/scout/sources/clutch.py`.

If any precondition fails: halt and resolve before writing code.

---

## Step 1: Diagnose the block (read-only, ~2 minutes)

Confirm Cloudflare is the actual reason — don't assume. Run three curl probes
against the target listing page:

```bash
URL="https://example-directory.com/agencies/web-development?page=0"

# Bare User-Agent
curl -s -o /dev/null -w "HTTP %{http_code} | %{size_download} bytes\n" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  "$URL"

# Full Chrome-like headers
curl -s -o /dev/null -w "HTTP %{http_code} | %{size_download} bytes\n" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  -H "Accept-Language: en-US,en;q=0.9" \
  -H "Sec-Fetch-Dest: document" \
  -H "Sec-Fetch-Mode: navigate" \
  --compressed "$URL"

# Body-keyword probe
curl -s -H "User-Agent: Mozilla/5.0 ..." "$URL" \
  | grep -oE "(cloudflare|Just a moment|cf-challenge|cf_chl_|attention-required)" | sort -u
```

**Interpretation**:

- **All three return 403** + the body-keyword probe surfaces `cloudflare` /
  `Just a moment` / `cf_chl_` → confirmed Cloudflare IUAM. Use this playbook.
- **HTTP 200 + empty body or layout drift** → not Cloudflare, probably HTML
  changed. Use plain httpx; fix the parsing regexes instead.
- **HTTP 200 + real listings** → no protection. Plain httpx is sufficient.

---

## Step 2: Implement the adapter

Mirror `systems/scout/sources/clutch.py`. Concretely:

### 2a. Constructor signature

```python
def __init__(
    self,
    category_path: str,
    http_client: httpx.AsyncClient | None = None,  # test-injection seam
    throttle_seconds: float = 4.0,
    playwright_headless: bool = False,             # default headed
    playwright_challenge_wait_ms: int = 5_000,
) -> None:
```

The `http_client` parameter is **kept as a test seam** — production never
provides it. When provided, the httpx code path runs (used by offline parsing
tests with HTML fixtures); when None, the Playwright path runs. Same public
contract; different fetch underneath.

### 2b. `pull()` branches on `http_client`

```python
async def pull(self, client_id, max_companies, dry_run=False, *, max_pages=50):
    if dry_run:
        return []
    if self._http_client is not None:
        return await self._pull_via_httpx(max_companies, max_pages)
    return await self._pull_via_playwright(max_companies, max_pages)
```

### 2c. Playwright fetch — the four ingredients

```python
from playwright.async_api import async_playwright   # lazy import inside the method
from playwright_stealth import Stealth

async with async_playwright() as p:
    browser = await p.chromium.launch(
        headless=self._playwright_headless,           # ← INGREDIENT 1: headed mode
        args=[                                        # ← INGREDIENT 2: Chrome args
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    await Stealth().apply_stealth_async(context)      # ← INGREDIENT 3: stealth patches
    page = await context.new_page()
    # then per-URL: navigate, wait, content
```

### 2d. Per-URL navigation — wait for the challenge to resolve

```python
async def _fetch_via_playwright(self, page, url):
    await page.goto(url, wait_until="networkidle", timeout=30_000)
    # ← INGREDIENT 4: wait at least 5 seconds for the JS challenge
    await page.wait_for_timeout(self._playwright_challenge_wait_ms)
    title = await page.title()
    if "Just a moment" in title or "challenge" in title.lower():
        # Still on the challenge — wait longer
        await page.wait_for_timeout(self._playwright_challenge_wait_ms * 2)
        title = await page.title()
        if "Just a moment" in title:
            try:
                await page.wait_for_url(f"**/{self.category_path}**", timeout=20_000)
            except Exception:
                pass  # downstream parser will detect via empty result
    return await page.content()
```

### 2e. Shared listing-page loop

Extract the parse-and-build logic into `_collect_listings(max_companies, max_pages, fetch_html)`
that takes a fetcher callable. Both `_pull_via_httpx` and `_pull_via_playwright`
call this with their respective fetchers — single source of truth for the
parsing + dedup + RawCompanyContact-row construction.

---

## Step 3: Test strategy — keep parser tests fast and offline

The httpx code path is the test injection seam. Tests construct the adapter
with a mock `http_client`, and a fixture HTML file:

```python
@pytest.mark.asyncio
async def test_directory_adapter_pulls_single_page():
    mock_client = AsyncMock()
    mock_client.get.return_value = _response(_load("directory_page0.html"))
    adapter = NewDirectoryAdapter(
        category_path="agencies/web",
        http_client=mock_client,
        throttle_seconds=0,
    )
    rows = await adapter.pull(client_id="c1", max_companies=10)
    assert rows[0].company == "Acme Co"
    assert rows[0].source == "newdir:agencies/web"
```

Save real fixture HTML (with the Cloudflare challenge bypassed via Playwright
once, then save the rendered HTML) to `tests/test_sources/fixtures/`. Parser
tests stay sub-100ms; the heavy Playwright path only runs in production +
explicit live integration tests.

---

## Step 4: Wire into the factory

In `aios/daemon/adapter_factory.py::_build_pull_adapter`, add a branch:

```python
if name == "newdirectory_agencies":
    return NewDirectoryAdapter(category_path="agencies/web-development")
```

Then add the routing key (here `newdirectory_agencies`) to the client's
`client_config.active_directories` array. The factory now stores adapters
keyed by routing key, not by `adapter.name` — see Slice 12 of 2026-04-29
for the contract details.

---

## Step 5: Live verification

Run the Scout daemon in cap-bounded mode against the live source:

```bash
set -a && . ./.env && set +a && uv run python scripts/run_daemon_once.py \
  --client-id=<client> \
  --stages=pull,score_v1,screen,identity,enrich,score_v2 \
  --max-companies-per-source=5 \
  --json
```

A successful run produces:

- `decision_log` row: `decision_type='source_selection'`, `decision='source_adapter_pulled'`,
  `reasoning='pulled=N inserted=N skipped=K'` with N > 0.
- New `contacts` rows with `source='<adapter.name>'` matching the pattern.
- Pull-stage timing > 15 seconds (cold-start the browser + wait for Cloudflare).
  A < 5 second pull stage means the adapter no-op'd; check the decision_log
  for `source_adapter_failed` with a 403 traceback.

---

## Common gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `decision='source_adapter_not_registered'` | Routing key in `active_directories` doesn't match factory dispatch | Update `_build_pull_adapter` to recognize the exact `active_directories` string |
| Pull stage takes <5s, returns 0 | Adapter is no-op'ing — check `dry_run` and `http_client` paths | Verify `http_client=None` in production wiring |
| `ClutchSuspiciousEmptyError` (or equivalent) raised | Cloudflare challenge didn't resolve OR HTML layout changed | Bump `playwright_challenge_wait_ms` to 10000+; update parser regex against fresh fixture |
| Browser launches but immediately closes | Wrong `DISPLAY` value or no display | Set `DISPLAY=:0` (workstation) or use `xvfb-run` (server) |
| `playwright_stealth` import fails | Module not in venv | `uv add playwright-stealth>=2.0.0` and `uv sync` |
| Headless works locally but fails in cron | Cron runs without a TTY/display | Wrap the cron line in `xvfb-run --server-args="-screen 0 1920x1080x24"` |

---

## Server Use (cron-side automation)

Headed mode requires a display. On a Linux server without a real display,
use **xvfb-run** to create a virtual one:

```cron
0 3 * * * cd /path/to/repo && set -a && . ./.env && set +a && \
  xvfb-run --server-args="-screen 0 1920x1080x24" \
  /home/user/.local/bin/uv run python scripts/run_daemon_once.py \
  --client-id=<client> --stages=pull --max-companies-per-source=50 \
  >> logs/cron.log 2>&1
```

Alternatively, set `playwright_headless=True` and accept that some sites'
challenges won't resolve. Quality vs ops trade-off: headed-via-xvfb is more
reliable; headless is simpler but breaks more often when Cloudflare updates.

---

## Why these four ingredients matter

| Ingredient | Without it | Why it matters |
|---|---|---|
| `playwright-stealth` | `navigator.webdriver=true` exposed → instant CF flag | Patches dozens of automation-leak signals |
| Headed (`headless=False`) | Headless-Chrome user-agent fingerprint detected | Real-browser TLS handshake + window manager signals fool the heuristic |
| `--disable-blink-features=AutomationControlled` | Blink exposes "automation controlled" notice in DevTools — CF reads it | Removes the most obvious tell |
| 5+ second wait after `networkidle` | Page returns with challenge HTML, parser sees no listings | The JS challenge takes seconds to compute; rushing returns the challenge page itself |

Skip any one and Cloudflare wins. The combo, validated against Clutch on
2026-04-29 and the standalone `clutch.co-scraper` project, is the floor —
not a starting point.

---

## When this stops working

Cloudflare updates its detection. The pattern above has worked for ~12
months at the time of writing (2026-04-29). When it breaks — symptoms:
all four ingredients in place but `Just a moment` persists past 30 seconds
of waiting — escalate to one of:

1. **Bump stealth version**: `uv lock --upgrade-package playwright-stealth`. The
   library's maintainers track CF heuristics; a release often restores capability.
2. **FlareSolverr sidecar**: self-hosted bypass service running undetected_chromedriver.
   Heavier ops; works when stealth alone can't.
3. **Paid bypass service**: ScraperAPI, ZenRows, Bright Data Web Unlocker. ~$0.001-0.01/request.
   Lowest dev friction; ongoing per-request cost.

Capture the failure mode + chosen mitigation in a new memory entry
(`feedback_cloudflare_bypass_v2.md`) so the next person hitting it doesn't
re-run this triage from scratch.
