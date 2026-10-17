# PHX2 Dashboard — read-only artifact viewer

The Claude-Design Phoenix dashboard (high-fidelity handoff) wired to **real
PHX2 artifacts**. It observes the free-tier private producer and the live
paper-trading engine by reading their artifact files. It commands nothing.

## Hard safety properties

- **Read-only.** The server answers GET/HEAD only (anything else → 405).
  The adapter opens allowlisted artifact filenames only, never writes,
  never locks, never truncates.
- **Localhost only.** Binds `127.0.0.1`. No deploy, no tunnel, no public hosting.
- **No secrets.** `.env` files are never opened. Every string emitted by the
  adapter passes a redaction filter (webhook URLs, `api-key=` params, bearer
  tokens, secret-named JSON keys). Webhook/API-key values are never displayed.
- **No bot surface.** No dispatch, no Discord sends, no wallet, no signing,
  no trading, no ledger mutation (the dedupe ledger is line-counted only).

## Run

```powershell
cd C:\Users\BalaC\Downloads\Phoenix_PHX2
.\.venv\Scripts\python.exe -m PHX2.dashboard.server
```

Then open http://127.0.0.1:8642/ in a browser.

Configured artifact sources (see `config.json`, overridable via CLI). Point these at the **per-run**
producer/paper subdirs — one pair per run (e.g. `live_private_03` / `live_free_tier_private_03`),
matching the producer `--out-dir` and paper `--inputs`:

- producer: `C:\Users\BalaC\phx2_live_free_tier\out\live_private_03`
- paper:    `C:\Users\BalaC\phx2_paper_trading\live_free_tier_private_03`
- ledger (line-count only): `C:\Users\BalaC\phx2_live_free_tier\ping_dedupe.jsonl`

Override example:

```powershell
.\.venv\Scripts\python.exe -m PHX2.dashboard.server --port 8642 `
  --producer-dir "C:\Users\BalaC\phx2_live_free_tier\out\live_private_03" `
  --paper-dir "C:\Users\BalaC\phx2_paper_trading\live_free_tier_private_03"
```

### Manual Helius credit panel (optional; operator-entered, never auto-read)

The dashboard **cannot** read Helius credits (no API key, no account access, no scrape). To see
burn/hour, burn/day and credits/ping, read the before/after credit totals off your Helius dashboard
by hand and add a `helius_credits` block to `config.json` (there is no CLI flag and it is never a
secret):

```json
{
  "producer_dir": "C:\\Users\\BalaC\\phx2_live_free_tier\\out\\live_private_03",
  "paper_dir": "C:\\Users\\BalaC\\phx2_paper_trading\\live_free_tier_private_03",
  "ledger_path": "C:\\Users\\BalaC\\phx2_live_free_tier\\ping_dedupe.jsonl",
  "helius_credits": { "before": 94000, "after": 110000, "window_seconds": 7200,
                      "as_of_utc": "2026-07-11T00:00:00Z" }
}
```

The credit panel (`bundle.credit_panel`) always shows the observed producer counters — discovery
mode, raw-WS msg count (labelled **not** Helius credits), polling tx count, market HTTP calls, sent
pings. When `helius_credits` is present it also derives `credits_used`, `credits_per_hour`,
`credits_per_day`, `credits_per_ping` and `days_to_exhaust`; when absent it shows a one-line hint on
how to enable them.

## What's where

- `adapter.py` — artifact → dashboard-contract mapping (pure, testable).
- `server.py` — stdlib GET-only server: static UI + `/api/xdata` + `/api/health`.
- `config.json` — artifact dir configuration.
- `static/` — the design handoff, visually unchanged, with:
  - `data-adapter.jsx` — polls `/api/xdata` every 10 s; pages fall back to the
    design mock **only** when no artifact bundle is available, and the fixed
    bottom-right badge labels the mode (`LIVE ARTIFACTS` vs `MOCK DATA`).
  - `paper-page.jsx` — the new **Paper** tab ("Paper Trading / Live Pings").
  - `vendor/` — React 18.3.1 + Babel standalone served locally (no CDN).

Tabs: Live, **Paper**, Candidates, Decisions, Outcomes, Calibration (local-only
demo), Runs, Research (future/demo). Portfolio and XScanner from the original
design are hidden (not designed in the handoff).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest PHX2/tests/dashboard -q --basetemp .pytest_basetmp_dashboard
```

(`--basetemp` inside the repo is the project convention — the default pytest
temp root is not writable in this environment.)
