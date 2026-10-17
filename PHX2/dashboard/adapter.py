"""PHX2 dashboard artifact adapter — READ-ONLY.

Maps real PHX2 producer / paper-trading artifact files into the data contract
expected by the Phoenix dashboard UI (the mock ``XData`` shapes from the design
handoff README).

Safety properties (hard requirements):
  * Read-only: never writes, renames, truncates, or locks any artifact file.
  * Allowlisted filenames only — never reads ``.env`` or config echoes.
  * Redaction pass over every emitted string (webhooks / api keys / bearer).
  * Tolerates missing files and malformed JSONL lines (skips + counts them).
  * No network, no subprocess, stdlib only.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "phx2_dashboard_adapter_v1"

# Heartbeat cadence: producer ticks ~90s, paper engine ~60s.
PRODUCER_STALE_SECONDS = 300.0
PAPER_STALE_SECONDS = 240.0

# Refuse to slurp anything bigger than this; JSONL readers tail instead.
MAX_JSON_BYTES = 8 * 1024 * 1024
JSONL_TAIL_BYTES = 1024 * 1024

PRODUCER_FILES = [
    "producer_summary.json",
    "producer_heartbeat.json",
    "heartbeat.json",
    "heartbeat.jsonl",
    "discovery_windows.jsonl",
    "activation_events.jsonl",
    "watch_state.jsonl",
    "watch_terminal_history.jsonl",
    "redaction_scan.json",
    "would_ping_records.jsonl",
    "sent_ping_records.jsonl",
    "discord_blocks.jsonl",
    "errors.jsonl",
    "ath_state.json",
    # PHX2-E2E-005 authenticated checkpoint observability.
    "checkpoint_status.json",
    "checkpoint_quarantine.json",
]
PRODUCER_CANDIDATES_SUBDIR = "candidates"

PAPER_FILES = [
    "heartbeat.json",
    "live_monitor.json",
    "paper_summary.json",
    "strategy_comparison.json",
    "paper_open_positions.json",
    "paper_closed_positions.jsonl",
    "paper_positions.jsonl",
    "paper_equity_curve.jsonl",
    "paper_recent_events.jsonl",
    "paper_events.jsonl",
    "paper_errors.jsonl",
    "paper_fills.jsonl",
    "input_checkpoints.json",
]

# ─── redaction ───────────────────────────────────────────────────────────────

_SECRET_KEY_RE = re.compile(
    r"(?i)(webhook[_-]?url|api[_-]?key|apikey|secret|bearer|authorization|password|private[_-]?key|access[_-]?token)"
)
_REDACT_TEXT_PATTERNS = [
    # discord / slack style webhook URLs
    (re.compile(r"https?://[^\s\"'<>]*discord[^\s\"'<>]*/api/webhooks/[^\s\"'<>]*", re.I),
     "[REDACTED_WEBHOOK]"),
    (re.compile(r"https?://hooks\.[^\s\"'<>]+", re.I), "[REDACTED_WEBHOOK]"),
    # key-bearing query params anywhere in a URL-ish string
    (re.compile(r"(?i)([?&#](?:api[-_]?key|apikey|key|token|secret)=)[^\s&\"'<>]+"),
     r"\1[REDACTED]"),
    # bearer tokens
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_.=+/]{8,}"), "Bearer [REDACTED]"),
    # inline kv assignments, e.g. api_key: xyz  /  WEBHOOK_URL=https://...
    (re.compile(
        r"(?i)\b(api[_-]?key|apikey|webhook[_-]?url|secret|authorization|password|private[_-]?key|access[_-]?token)"
        r"(\s*[:=]\s*)[^\s\"',;}{]+"),
     r"\1\2[REDACTED]"),
]


def redact_text(value: str) -> str:
    out = value
    for pattern, repl in _REDACT_TEXT_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redact_value(obj):
    """Deep-redact any JSON-ish structure. Secret-named keys lose their value."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        out = {}
        for key, val in obj.items():
            if isinstance(key, str) and _SECRET_KEY_RE.search(key):
                out[key] = "[REDACTED]"
            else:
                out[key] = redact_value(val)
        return out
    if isinstance(obj, list):
        return [redact_value(v) for v in obj]
    return obj


# ─── tolerant IO ─────────────────────────────────────────────────────────────

def read_json(path: Path):
    """Return (obj, error). Missing / oversized / malformed -> (None, reason)."""
    try:
        if not path.is_file():
            return None, "MISSING"
        if path.stat().st_size > MAX_JSON_BYTES:
            return None, "TOO_LARGE"
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            return None, "EMPTY"
        return json.loads(text), None
    except (OSError, ValueError) as exc:
        return None, f"UNREADABLE: {exc.__class__.__name__}"


def read_jsonl(path: Path, tail_lines: int | None = None):
    """Return (records, skipped, error). Malformed lines are skipped + counted.

    For large files only the last ``JSONL_TAIL_BYTES`` are examined, so a
    growing live artifact can never stall the dashboard.
    """
    try:
        if not path.is_file():
            return [], 0, "MISSING"
        size = path.stat().st_size
        if size == 0:
            return [], 0, None
        with path.open("rb") as fh:
            if size > JSONL_TAIL_BYTES:
                fh.seek(size - JSONL_TAIL_BYTES)
                raw = fh.read()
                # drop the (likely partial) first line
                raw = raw.split(b"\n", 1)[1] if b"\n" in raw else b""
            else:
                raw = fh.read()
        records, skipped = [], 0
        for line in raw.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                skipped += 1
        if tail_lines is not None:
            records = records[-tail_lines:]
        return records, skipped, None
    except OSError as exc:
        return [], 0, f"UNREADABLE: {exc.__class__.__name__}"


def count_lines(path: Path):
    """Cheap line count for small ledgers; None when unavailable."""
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > MAX_JSON_BYTES:
            return None
        with path.open("rb") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return None


# ─── formatting helpers ──────────────────────────────────────────────────────

def parse_iso(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def age_seconds(ts_utc, now):
    dt = parse_iso(ts_utc)
    if dt is None:
        return None
    return max(0.0, (now - dt).total_seconds())


def fmt_age(seconds):
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 90:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 36:
        return f"{hours}h {minutes % 60:02d}m"
    days = hours // 24
    return f"{days}d {hours % 24:02d}h"


def fmt_usd(value):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if num < 0 else ""
    num = abs(num)
    if num >= 1e9:
        return f"{sign}${num / 1e9:.2f}B"
    if num >= 1e6:
        return f"{sign}${num / 1e6:.2f}M"
    if num >= 1e3:
        return f"{sign}${num / 1e3:.1f}K"
    if num >= 1:
        return f"{sign}${num:,.2f}"
    return f"{sign}${num:.8f}".rstrip("0").rstrip(".")


def fmt_money(value):
    """Exact account-money format ($1,234.56) — no K/M abbreviation."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if num < 0 else ""
    return f"{sign}${abs(num):,.2f}"


DEFAULT_STARTING_EQUITY_USD = 1000.0


def fmt_int(value):
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def fmt_pct(value, signed=True):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    plus = "+" if (signed and num > 0) else ""
    return f"{plus}{num:.1f}%"


def short_mint(mint):
    if not mint or not isinstance(mint, str):
        return "—"
    if len(mint) <= 12:
        return mint
    return f"{mint[:4]}…{mint[-4:]}"


def fmt_clock(ts_utc):
    dt = parse_iso(ts_utc)
    return dt.strftime("%H:%M:%S") if dt else "—"


def _now(now=None):
    return now if now is not None else datetime.now(timezone.utc)


# ─── status computation ──────────────────────────────────────────────────────

def compute_status(heartbeat_age_s, stop_reason=None, stale_after=PRODUCER_STALE_SECONDS):
    """RUNNING / STOPPED / STALE / UNKNOWN + a display tone."""
    if stop_reason:
        return "STOPPED", "info"
    if heartbeat_age_s is None:
        return "UNKNOWN", "muted"
    if heartbeat_age_s <= stale_after:
        return "RUNNING", "ok"
    return "STALE", "warn"


# ─── artifact loading ────────────────────────────────────────────────────────

def _file_meta(path: Path, now):
    try:
        if not path.is_file():
            return {"present": False}
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        return {
            "present": True,
            "bytes": stat.st_size,
            "mtime_utc": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "age_s": round(max(0.0, (now - mtime).total_seconds()), 1),
        }
    except OSError:
        return {"present": False}


def load_producer(producer_dir, now):
    root = Path(producer_dir)
    data = {"dir": str(root), "files": {}, "io_errors": {}}
    for name in PRODUCER_FILES:
        data["files"][name] = _file_meta(root / name, now)

    summary, err = read_json(root / "producer_summary.json")
    if err and err != "MISSING":
        data["io_errors"]["producer_summary.json"] = err
    heartbeat, err = read_json(root / "producer_heartbeat.json")
    if err and err != "MISSING":
        data["io_errors"]["producer_heartbeat.json"] = err
    if heartbeat is None:
        heartbeat, err = read_json(root / "heartbeat.json")

    hb_lines, hb_skipped, _ = read_jsonl(root / "heartbeat.jsonl", tail_lines=50)
    windows, win_skipped, _ = read_jsonl(root / "discovery_windows.jsonl", tail_lines=200)
    activation_events, activation_skipped, _ = read_jsonl(
        root / "activation_events.jsonl", tail_lines=500)
    watch_lines, watch_skipped, _ = read_jsonl(root / "watch_state.jsonl", tail_lines=500)
    would_pings, wp_skipped, _ = read_jsonl(root / "would_ping_records.jsonl", tail_lines=100)
    sent_pings, sp_skipped, _ = read_jsonl(root / "sent_ping_records.jsonl", tail_lines=100)
    discord_blocks, db_skipped, _ = read_jsonl(root / "discord_blocks.jsonl", tail_lines=100)
    errors, err_skipped, _ = read_jsonl(root / "errors.jsonl", tail_lines=100)
    redaction, _ = read_json(root / "redaction_scan.json")
    ath_state, ath_err = read_json(root / "ath_state.json")
    if ath_err and ath_err != "MISSING":
        data["io_errors"]["ath_state.json"] = ath_err
    checkpoint_status, _ = read_json(root / "checkpoint_status.json")
    checkpoint_quarantine, _ = read_json(root / "checkpoint_quarantine.json")

    # candidates/*.jsonl — last record per candidate + recheck count
    candidates = {}
    cand_dir = root / PRODUCER_CANDIDATES_SUBDIR
    cand_files = 0
    if cand_dir.is_dir():
        for cand_path in sorted(cand_dir.glob("*.jsonl")):
            cand_files += 1
            records, skipped, _ = read_jsonl(cand_path, tail_lines=50)
            if not records:
                continue
            last = records[-1]
            cid = last.get("candidate_id") or cand_path.stem
            candidates[cid] = {
                "last": last,
                "records": len(records),
                "skipped": skipped,
                "file": cand_path.name,
            }
    data["files"]["candidates/"] = {"present": cand_dir.is_dir(), "count": cand_files}

    # latest watch_state per candidate_id (append-only log: last line wins).
    # PHX2-E2E-005: the authenticated checkpoint prepends an envelope header
    # line and may carry quarantined-candidate records; neither is a normal
    # candidate row.
    watch = {}
    watch_checkpoint_header = None
    watch_quarantined = {}
    for rec in watch_lines:
        if rec.get("checkpoint_kind"):
            watch_checkpoint_header = rec
            continue
        if rec.get("checkpoint_record_kind") == "PHX2_QUARANTINED_CANDIDATE":
            watch_quarantined[rec.get("token_mint")] = rec
            continue
        cid = rec.get("candidate_id")
        if cid:
            watch[cid] = rec

    data.update({
        "summary": summary,
        "heartbeat": heartbeat,
        "heartbeat_lines": hb_lines,
        "windows": windows,
        "activation_events": activation_events,
        "watch": watch,
        "watch_lines": watch_lines,
        "candidates": candidates,
        "would_pings": would_pings,
        "sent_pings": sent_pings,
        "discord_blocks": discord_blocks,
        "errors": errors,
        "redaction": redaction,
        "ath_state": ath_state,
        "checkpoint_status": checkpoint_status,
        "checkpoint_quarantine": checkpoint_quarantine,
        "watch_checkpoint_header": watch_checkpoint_header,
        "watch_quarantined": watch_quarantined,
        "skipped_lines": {
            "heartbeat.jsonl": hb_skipped,
            "discovery_windows.jsonl": win_skipped,
            "activation_events.jsonl": activation_skipped,
            "watch_state.jsonl": watch_skipped,
            "would_ping_records.jsonl": wp_skipped,
            "sent_ping_records.jsonl": sp_skipped,
            "discord_blocks.jsonl": db_skipped,
            "errors.jsonl": err_skipped,
        },
    })
    return data


def load_paper(paper_dir, now):
    root = Path(paper_dir)
    data = {"dir": str(root), "files": {}, "io_errors": {}}
    for name in PAPER_FILES:
        data["files"][name] = _file_meta(root / name, now)

    def _json(name):
        obj, err = read_json(root / name)
        if err and err != "MISSING":
            data["io_errors"][name] = err
        return obj

    data["heartbeat"] = _json("heartbeat.json")
    data["monitor"] = _json("live_monitor.json")
    data["summary"] = _json("paper_summary.json")
    data["comparison"] = _json("strategy_comparison.json")
    data["open_positions"] = _json("paper_open_positions.json")
    data["checkpoints"] = _json("input_checkpoints.json")

    closed, closed_skipped, _ = read_jsonl(root / "paper_closed_positions.jsonl", tail_lines=200)
    positions, pos_skipped, _ = read_jsonl(root / "paper_positions.jsonl", tail_lines=200)
    equity, eq_skipped, _ = read_jsonl(root / "paper_equity_curve.jsonl", tail_lines=400)
    events, ev_skipped, _ = read_jsonl(root / "paper_recent_events.jsonl", tail_lines=60)
    errors, per_skipped, _ = read_jsonl(root / "paper_errors.jsonl", tail_lines=100)

    data.update({
        "closed": closed,
        "positions": positions,
        "equity": equity,
        "events": events,
        "errors": errors,
        "skipped_lines": {
            "paper_closed_positions.jsonl": closed_skipped,
            "paper_positions.jsonl": pos_skipped,
            "paper_equity_curve.jsonl": eq_skipped,
            "paper_recent_events.jsonl": ev_skipped,
            "paper_errors.jsonl": per_skipped,
        },
    })
    return data


# ─── domain mapping helpers ──────────────────────────────────────────────────

# Producer risk labels -> display tone + short form ("RISK_HIGH" -> "HIGH").
_RISK_TONES = {"RISK_HIGH": "bad", "RISK_MEDIUM": "warn",
               "RISK_LOW": "ok", "RISK_UNKNOWN": "muted"}


def _risk_short(label):
    if isinstance(label, str) and label.startswith("RISK_"):
        return label[len("RISK_"):]
    return "?"


def _risk_fields(label, reasons):
    """Uniform risk sub-shape for candidate / ping / position rows."""
    clean = [str(r) for r in (reasons or []) if isinstance(r, str)][:6]
    return {
        "risk": _risk_short(label) if label else "?",
        "riskLabel": label,
        "riskReasons": clean,
        "riskTone": _RISK_TONES.get(label, "muted"),
    }


_BLOCKER_TEXT = {
    "PENDING_MIGRATION_BASELINE": ("Migration baseline pending", "Needs the first valid fresh Birdeye market-cap snapshot", "Pending baseline"),
    "PENDING_ACTIVATION_THRESHOLD": ("Activation threshold pending", "Current market cap must reach the immutable migration baseline x 1.20", "Pending 1.20x"),
    "ACTIVATED_WAITING_FOR_FRESH_MARKET": ("Activation proven - awaiting market", "A genuinely later fresh current price, market cap and liquidity observation is required for tier evaluation", "Activated - market pending"),
    "ACTIVATION_LATER_MARKET_TICK_REQUIRED": ("Activation proven - later tick required", "Provider timestamp must be later than both the activation event and PHX2 acceptance time", "Activated - later tick pending"),
    "LEGACY_ACTIVATION_UNPROVEN": ("Legacy activation unproven", "Legacy state remains ineligible and will expire", "Legacy blocked"),
    "DROPPED_NON_PUMP": ("Non-pump program — dropped", "Terminal: only pump.fun migrations are eligible", "Non-pump dropped"),
    "NO_SEND_MARKET_UNAVAILABLE": ("Market data unavailable", "Needs MC + price + LP all present on a recheck", "Market data unavailable"),
    "MARKET_UNAVAILABLE": ("Market data unavailable", "Needs MC + price + LP all present on a recheck", "Market data unavailable"),
    "MARKET_INDEXING": ("Market provider indexing", "Refresh remains scheduled with per-token backoff", "Market indexing"),
    "MARKET_INCOMPLETE": ("Market data incomplete", "Awaiting all required fresh fields", "Market incomplete"),
    "MARKET_STALE": ("Market data stale", "Awaiting a fresh provider-timestamped sample", "Market stale"),
    "MARKET_INVALID": ("Market data invalid", "Malformed or unsafe provider data remains blocked", "Market invalid"),
    "MARKET_RECOVERY_BACKOFF": ("Market recovery backoff", "Aggressive polling paused after grace exhaustion; a bounded recovery probe is scheduled and the candidate stays active and recoverable", "Market recovering"),
    "NO_SEND_MARKET_RECOVERY_BACKOFF": ("Market recovery backoff", "Aggressive polling paused after grace exhaustion; a bounded recovery probe is scheduled and the candidate stays active and recoverable", "Market recovering"),
    "MARKET_RECOVERY_BACKOFF_NOT_DUE": ("Market recovery backoff", "Recovery probe not yet due; no provider call until the scheduled time; candidate stays active", "Market recovering"),
    "LEGACY_MARKET_TERMINAL_MIGRATED_TO_RECOVERY": ("Market recovery backoff", "A legacy terminal market state was restored as recoverable backoff; a bounded recovery probe is scheduled", "Market recovering"),
    "NO_SEND_DIP_GATE": ("Dip gate not passed", "Needs tier-dip eligibility PASS_TO_DISPATCH", "Dip gate blocked"),
    "EXPIRED": ("Watch window expired", "Terminal: candidate aged out of the watchlist", "Expired"),
    "DEDUPE_SUPPRESSED": ("Suppressed by dedupe ledger", "Terminal: mint already pinged in a prior run", "Dedupe suppressed"),
}


def _blocker_for(reason):
    if not reason:
        return ("Watching — awaiting next recheck", "Needs eligible market context on recheck", "Watching")
    key = str(reason)
    if key in _BLOCKER_TEXT:
        return _BLOCKER_TEXT[key]
    pretty = key.replace("NO_SEND_", "").replace("_", " ").strip().capitalize()
    return (pretty, "See producer artifacts for detail", pretty)


def _watch_stage(status, last_reason):
    if status in ("PENDING_BASELINE", "PENDING_1_20X"):
        return status
    if status == "ACTIVATED_WAITING_FOR_FRESH_MARKET":
        return status
    if status in ("ACTIVATED", "ACTIVE_DIP_WATCH"):
        return "ACTIVE_DIP_WATCH"
    if status == "WATCHING":
        if last_reason and any(token in str(last_reason) for token in (
                "MARKET_UNAVAILABLE", "MARKET_INDEXING", "MARKET_INCOMPLETE",
                "MARKET_STALE", "MARKET_INVALID", "MARKET_RECOVERY_BACKOFF")):
            return "WAITING_FOR_PRICE"
        return "WATCHING"
    if status == "DROPPED_NON_PUMP":
        return "DEAD"
    if status == "EXPIRED":
        return "DECAYING"
    if status in ("PINGED", "SENT", "SENT_OK"):
        return "WATCHING"
    return status or "WATCHING"


def _lifecycle_for(stage, updated_age_s):
    if stage == "DEAD":
        return "Dead"
    if stage == "DECAYING":
        return "Stale"
    if stage in ("WAITING_FOR_PRICE", "ACTIVATED_WAITING_FOR_FRESH_MARKET"):
        return "Pending"
    if stage in ("PENDING_BASELINE", "PENDING_1_20X"):
        return "Pending"
    if updated_age_s is not None and updated_age_s > 1800:
        return "Stale"
    return "Active"


def build_candidate_rows(producer, now):
    """Merge watch_state + candidates/*.jsonl into CandidateData.queue rows."""
    rows = []
    watch = producer.get("watch", {})
    candidates = producer.get("candidates", {})
    central_mints = ((producer.get("ath_state") or {}).get("mints") or {})
    for cid, wrec in watch.items():
        crec = (candidates.get(cid) or {}).get("last") or {}
        market = crec.get("market_attempt_summary") or {}
        lp_verify = crec.get("lp_verify") or {}
        fee_gate = crec.get("fee_gate") or {}
        lp_integrity = crec.get("lp_integrity") or {}
        scam_policy = crec.get("scam_policy") or {}
        status = wrec.get("status")
        activation = wrec
        reason = wrec.get("last_reason") or crec.get("rejection_reason_raw")
        market_state = (wrec.get("market_state") or market.get("market_state")
                        or crec.get("rejection_reason"))
        stage = _watch_stage(status, reason)
        blocker_key = market_state if isinstance(market_state, str) and market_state.startswith(
            "MARKET_") else (reason if status != "WATCHING" or reason else None)
        blocker, next_cond, group = _blocker_for(blocker_key)
        mint = wrec.get("token_mint") or crec.get("token_mint")
        central_ath = central_mints.get(mint) if isinstance(mint, str) else None
        if not isinstance(central_ath, dict):
            central_ath = crec.get("central_ath") or market.get("central_ath") or {}
        updated_ts = wrec.get("last_observed_at_utc") or crec.get("observed_at_utc") or wrec.get("seeded_at_utc")
        updated_age = age_seconds(updated_ts, now)
        seeded_age = age_seconds(wrec.get("seeded_at_utc"), now)
        migration_age = age_seconds(wrec.get("migration_time_utc") or crec.get("migration_time_utc"), now)
        fetched_age = age_seconds(market.get("market_context_fetched_at_utc"), now)

        attempts = market.get("attempts") or []
        last_attempt = attempts[-1] if attempts else {}
        reserve = market.get("pumpswap_reserve") or last_attempt.get("pumpswap_reserve") or {}
        reserve_artifact = (reserve.get("reserve_artifact")
                            if isinstance(reserve, dict) else {}) or {}
        mcap = market.get("current_market_cap_usd")
        if mcap is None:
            mcap = last_attempt.get("mc_value")
        liq = market.get("liquidity_usd")
        if liq is None:
            liq = last_attempt.get("lp_value")

        filters_code = str(reason or status or "WATCHING").replace("NO_SEND_", "")
        filters_tone = "ok" if status == "WATCHING" and not reason else (
            "bad" if stage in ("DEAD", "DECAYING") else "warn")

        risk_label = crec.get("risk_label")
        risk_reasons = crec.get("risk_reasons") or []
        fee_lifecycle = crec.get("fee_gate_lifecycle") or {}

        rows.append({
            **_risk_fields(risk_label, risk_reasons),
            "id": cid,
            "token": wrec.get("symbol_or_name") or short_mint(mint),
            "tokenSub": short_mint(mint),
            "mint": mint,
            "pair": f"{short_mint(mint)} / SOL",
            "stage": stage,
            "activationState": status,
            "activationEligible": bool(wrec.get("activation_proven")
                                       and status == "ACTIVE_DIP_WATCH"),
            "migrationMarketCapUsd": activation.get("migration_market_cap_usd"),
            "migrationMarketCapSource": activation.get("migration_market_cap_source"),
            "migrationMarketCapObservedAtUtc": activation.get(
                "migration_market_cap_observed_at_utc"),
            "migrationMarketCapPrice": activation.get("migration_market_cap_price"),
            "migrationSupplyAtObservation": activation.get(
                "migration_supply_at_observation"),
            "migrationBaselineStatus": activation.get("migration_baseline_status"),
            "activationMultiplier": activation.get("activation_multiplier"),
            "activationTargetMarketCapUsd": activation.get(
                "activation_target_market_cap_usd"),
            "activatedAtUtc": activation.get("activated_at_utc"),
            "activationObservationSource": activation.get(
                "activation_observation_source"),
            "activationCurrentMarketCapUsd": activation.get(
                "activation_current_market_cap_usd"),
            "activationEvidenceSource": activation.get("activation_evidence_source"),
            "activationEvidenceMarketCapUsd": activation.get(
                "activation_evidence_market_cap_usd"),
            "activationEvidenceEventAtUtc": activation.get(
                "activation_evidence_event_at_utc"),
            "activationEvidenceIngestedAtUtc": activation.get(
                "activation_evidence_ingested_at_utc"),
            "activationEvidenceDigest": activation.get("activation_evidence_digest"),
            "activationEvidenceVersion": activation.get("activation_evidence_version"),
            "activationProofDigest": activation.get("activation_proof_digest"),
            "activationProofVersion": activation.get("activation_proof_version"),
            "activationEvidenceKind": activation.get("activation_evidence_kind"),
            "activationCrossingTickDigest": activation.get(
                "activation_crossing_tick_digest"),
            "activationCrossingTickBlocked": bool(activation.get(
                "activation_crossing_tick_blocked")),
            "activationLatched": bool(activation.get("activation_latched")),
            "activationProven": bool(activation.get("activation_proven")),
            "activationWaitingForFreshMarket": bool(
                activation.get("activation_waiting_for_fresh_market")
                or status == "ACTIVATED_WAITING_FOR_FRESH_MARKET"),
            "activationCurrentMarketRequiredForTier": bool(activation.get(
                "activation_current_market_required_for_tier", True)),
            "activationSourceEvidenceDigest": activation.get(
                "activation_source_evidence_digest"),
            "activationObservationSealDigest": activation.get(
                "activation_observation_seal_digest"),
            "activationObservationSealVersion": activation.get(
                "activation_observation_seal_version"),
            "latestMarketReadinessState": (activation.get(
                "latest_market_readiness_state") or market_state),
            "latestMarketReadinessReason": (activation.get(
                "latest_market_readiness_reason")
                or wrec.get("market_reason_code") or reason),
            "marketState": market_state,
            "marketReasonCode": (wrec.get("market_reason_code")
                                 or market.get("market_reason_code")),
            "nextMarketRefreshAt": (wrec.get("next_market_refresh_at_utc")
                                    or market.get("next_market_refresh_at_utc")),
            "marketAttemptCount": (wrec.get("market_attempt_count")
                                   or market.get("market_attempt_count")),
            "lifecycle": _lifecycle_for(stage, updated_age),
            "mcap": fmt_usd(mcap),
            "liq": fmt_usd(liq),
            "ath": fmt_usd(central_ath.get("ath_market_cap")),
            "athState": central_ath.get("ath_status") or "UNKNOWN",
            "athPriceUsd": central_ath.get("ath_price"),
            "athMarketCapUsd": central_ath.get("ath_market_cap"),
            "athTimestamp": central_ath.get("ath_timestamp"),
            "athProvider": central_ath.get("ath_provider"),
            "athObservationType": central_ath.get("ath_observation_type"),
            "athTransactionSignature": central_ath.get(
                "ath_transaction_signature"),
            "athEvidenceDigest": central_ath.get("ath_evidence_digest"),
            "athEvidenceVersion": central_ath.get("ath_evidence_version"),
            "athObservationSealDigest": central_ath.get(
                "ath_observation_seal_digest"),
            "athObservationSealVersion": central_ath.get(
                "ath_observation_seal_version"),
            "athIngestedAtUtc": central_ath.get("ath_ingested_at_utc"),
            "drawdown": None,
            "distance": None,
            "distanceLabel": "—",
            "targetTier": "T?",
            "blocker": blocker,
            "nextCondition": next_cond,
            "blockerGroup": group if stage != "WATCHING" else None,
            "filters": filters_code,
            "filtersTone": filters_tone,
            "trend": None,
            "updated": fmt_age(updated_age),
            "timeInQueue": fmt_age(seeded_age),
            "migrationAge": fmt_age(migration_age),
            "priceFresh": fmt_age(fetched_age) if fetched_age is not None else "—",
            "reserveComparisonStatus": reserve.get("comparison_status"),
            "reserveValidationStatus": reserve.get("reserve_validation_status"),
            "reservePriceUsd": reserve.get("effective_reserve_price_usd"),
            "reserveMarketCapUsd": reserve.get("effective_reserve_market_cap_usd"),
            "reserveLiquidityUsd": reserve.get("effective_reserve_liquidity_usd"),
            "reserveAthPriceUsd": reserve.get("effective_reserve_ath_price_usd"),
            "reserveDrawdownPct": reserve.get("effective_reserve_drawdown_pct"),
            "reservePriceDiscrepancyPct": reserve.get("price_discrepancy_pct"),
            "reserveTrustedForRouting": reserve.get("reserve_trusted_for_routing", False),
            "rawQuoteReserves": reserve_artifact.get("raw_quote_reserves"),
            "virtualQuoteReserves": reserve_artifact.get("virtual_quote_reserves"),
            "effectiveQuoteReserves": reserve_artifact.get("effective_quote_reserves"),
            "baseReserves": reserve_artifact.get("base_reserves"),
            "reserveSource": reserve_artifact.get("reserve_source"),
            "reserveObservedAt": reserve_artifact.get("observation_timestamp"),
            "reserveDecoderLayout": reserve_artifact.get("decoder_layout_version"),
            "feeGateLabel": fee_gate.get("fee_gate_label") or "UNKNOWN",
            "feeGateReasons": fee_gate.get("fee_gate_reasons") or [],
            "feeGateEligible": bool(fee_gate.get("fee_gate_eligible")),
            "feeGateBribeSharePct": fee_gate.get("bribe_share_pct"),
            "feeGateCreatorShare": fee_gate.get("creator_share"),
            "feeGateLpShare": fee_gate.get("lp_share"),
            "feeGateProtocolShare": fee_gate.get("protocol_share"),
            "feeGateBalancedFees": fee_gate.get("balanced_fees"),
            "feeLifecycleState": fee_lifecycle.get("lifecycle_state") or "UNKNOWN",
            "feeLifecycleMaturity": fee_lifecycle.get("maturity"),
            "feeLifecycleLastFreshVerdict": fee_lifecycle.get("last_fresh_verdict"),
            "feeLifecycleProvisionalScamCount": fee_lifecycle.get("provisional_scam_count"),
            "feeLifecycleDurableLock": bool(fee_lifecycle.get("durable_scam_locked")),
            "feeLifecycleEvidenceDigest": fee_lifecycle.get("evidence_proof_digest"),
            "lpIntegrity": lp_integrity.get("lp_integrity") or "UNKNOWN",
            "lpIntegrityReasons": lp_integrity.get("lp_integrity_reasons") or [],
            "canonicalPool": lp_integrity.get("canonical_pool"),
            "canonicalPoolProven": bool(lp_integrity.get("canonical_pool_proven")),
            "compositeVerdict": scam_policy.get("verdict") or "UNKNOWN",
            "compositeBlockReasons": scam_policy.get("final_block_reasons") or [],
            "recheckCount": wrec.get("recheck_count"),
            "sourceRef": wrec.get("source_ref"),
            "explanation": _candidate_explanation(status, reason, market, lp_verify,
                                                  risk_label, risk_reasons),
            "_seeded_age_s": seeded_age,
        })
    rows.sort(key=lambda r: (r["_seeded_age_s"] is None, r["_seeded_age_s"] or 0))
    for row in rows:
        row.pop("_seeded_age_s", None)
    return rows


def _candidate_explanation(status, reason, market, lp_verify,
                           risk_label=None, risk_reasons=None):
    bits = []
    if status == "WATCHING":
        bits.append("Candidate is on the live watchlist.")
    elif status:
        bits.append(f"Watch status is {status}.")
    if reason:
        bits.append(f"Last recheck outcome: {reason}.")
    if risk_label:
        detail = ", ".join(str(r) for r in (risk_reasons or [])[:4])
        bits.append(f"Risk assessment: {_risk_short(risk_label)}"
                    + (f" ({detail})." if detail else " (no cheap red flag observed)."
                       if risk_label == "RISK_LOW" else "."))
    if market:
        present = []
        missing = []
        for label, key in (("MC", "mc_present"), ("price", "price_present"), ("LP", "lp_present")):
            (present if market.get(key) else missing).append(label)
        if missing:
            bits.append(f"Market context incomplete — missing {', '.join(missing)}.")
        elif present:
            bits.append("Market context complete at last recheck.")
    if lp_verify.get("lp_verify_status"):
        bits.append(f"LP verify: {lp_verify.get('lp_verify_status')} ({lp_verify.get('lp_verify_reason') or 'n/a'}).")
    bits.append("No ping is sent unless the dip gate and market-context gates all pass; this dashboard is read-only.")
    return " ".join(bits)


def build_decisions(producer, now):
    """Decision ledger from candidate rechecks, watch drops, would/sent pings."""
    decisions = []
    seq = 0

    def _mk(ts_utc, token_mint, decision, reason, extra):
        nonlocal seq
        seq += 1
        age = age_seconds(ts_utc, now)
        base = {
            "id": f"PHX-{seq:04d}",
            "t": fmt_age(age),
            "tAbs": fmt_clock(ts_utc),
            "token": short_mint(token_mint),
            "tokenSub": short_mint(token_mint),
            "mint": token_mint,
            "pair": f"{short_mint(token_mint)} / SOL",
            "pairQuote": "SOL",
            "decision": decision,
            "reason": reason,
            "tier": "--",
            "athState": "UNKNOWN",
            "priceState": "UNKNOWN",
            "drawdown": None,
            "filters": reason,
            "filtersTone": "warn",
            "dataQuality": "PARTIAL",
            "candidateStateBefore": "—",
            "knew": [],
            "whatWouldChange": "",
            "_age_s": age if age is not None else float("inf"),
        }
        base.update(extra)
        return base

    for cid, bundle in (producer.get("candidates") or {}).items():
        rec = bundle.get("last") or {}
        market = rec.get("market_attempt_summary") or {}
        lp_verify = rec.get("lp_verify") or {}
        reason = rec.get("rejection_reason") or rec.get("rejection_reason_raw") or "RECHECK"
        knew = [
            f"Migration at {rec.get('migration_time_utc') or '—'}",
            f"Recheck #{rec.get('recheck_index', '—')} observed at {rec.get('observed_at_utc') or '—'}",
            f"Market basis: {market.get('basis') or '—'}",
            f"MC present: {bool(market.get('mc_present'))} · price present: {bool(market.get('price_present'))} · LP present: {bool(market.get('lp_present'))}",
        ]
        if lp_verify:
            knew.append(
                f"LP verify {lp_verify.get('lp_verify_status') or '—'} ({lp_verify.get('lp_verify_reason') or 'n/a'}), observe-only")
        knew.append(f"Transport attempted: {bool(rec.get('transport_attempted'))} · ledger touched: {bool(rec.get('ledger_touched'))}")
        quality = "COMPLETE" if market.get("basis") == "REAL_MARKET_COMPLETE" else (
            "MISSING_LP" if market.get("mc_present") and not market.get("lp_present") else "PARTIAL")
        decisions.append(_mk(
            rec.get("observed_at_utc"), rec.get("token_mint"), "SKIP", str(reason),
            {
                "priceState": "PRESENT" if market.get("price_present") else "MISSING",
                "dataQuality": quality,
                "candidateStateBefore": "WATCHING",
                "knew": knew,
                "whatWouldChange": "Would compose a private ping only if MC, price and LP were all present and the dip gate returned PASS_TO_DISPATCH. This run: no send.",
            }))

    for cid, wrec in (producer.get("watch") or {}).items():
        if wrec.get("status") == "DROPPED_NON_PUMP":
            decisions.append(_mk(
                wrec.get("seeded_at_utc"), wrec.get("token_mint"), "SKIP", "NON_PUMP",
                {
                    "filters": "NON_PUMP",
                    "filtersTone": "bad",
                    "dataQuality": "COMPLETE",
                    "candidateStateBefore": "SEEDED",
                    "knew": [
                        f"Seeded at {wrec.get('seeded_at_utc') or '—'}",
                        f"Migration at {wrec.get('migration_time_utc') or '—'}",
                        "Mint is not a pump.fun migration — outside scope",
                    ],
                    "whatWouldChange": "Nothing — non-pump mints are dropped by design (fail-closed seeding boundary).",
                }))
        elif wrec.get("status") == "WATCHING":
            decisions.append(_mk(
                wrec.get("seeded_at_utc"), wrec.get("token_mint"), "CANDIDATE", "SEEDED_PUMP_MIGRATION",
                {
                    "filters": "SEEDED",
                    "filtersTone": "info",
                    "dataQuality": "COMPLETE",
                    "candidateStateBefore": "—",
                    "knew": [
                        f"Pump migration detected at {wrec.get('migration_time_utc') or '—'}",
                        f"Seeded onto watchlist at {wrec.get('seeded_at_utc') or '—'}",
                        f"Provenance: {wrec.get('source_ref') or '—'}",
                    ],
                    "whatWouldChange": "Candidate advances only when a recheck finds complete market context and the dip gate passes.",
                }))

    for rec in producer.get("would_pings") or []:
        decisions.append(_mk(
            rec.get("observed_at_utc") or rec.get("ts_utc"), rec.get("token_mint") or rec.get("mint"),
            "WOULD_ALERT", str(rec.get("reason") or "WOULD_PING"),
            {
                "filtersTone": "ok",
                "dataQuality": "COMPLETE",
                "candidateStateBefore": "WATCHING",
                "knew": [f"{k}: {v}" for k, v in list(rec.items())[:6]],
                "whatWouldChange": "This was a would-ping (no real send).",
            }))

    for rec in producer.get("sent_pings") or []:
        decisions.append(_mk(
            rec.get("sent_at_utc") or rec.get("ts_utc"), rec.get("token_mint") or rec.get("mint"),
            "SENT", str(rec.get("reason") or "PRIVATE_PING_SENT"),
            {
                "filtersTone": "ok",
                "dataQuality": "COMPLETE",
                "candidateStateBefore": "WATCHING",
                "knew": [f"{k}: {v}" for k, v in list(rec.items())[:6]],
                "whatWouldChange": "Real private ping was dispatched (cap + dedupe guarded).",
            }))

    decisions.sort(key=lambda d: d["_age_s"])
    for dec in decisions:
        dec.pop("_age_s", None)
    return decisions


def build_outcomes(paper, now):
    """OutcomeData rows from paper closed positions (realized outcomes)."""
    outcomes = []
    closed = list(paper.get("closed") or [])
    # also surface CLOSED_* records from the position log if the dedicated
    # closed file is empty (same schema)
    if not closed:
        closed = [r for r in (paper.get("positions") or [])
                  if str(r.get("status", "")).startswith("CLOSED")]
    for i, rec in enumerate(closed):
        pnl = rec.get("realized_pnl_pct")
        pnl_usd = rec.get("realized_pnl_usd")
        try:
            pnl_num = float(pnl) if pnl is not None else (float(pnl_usd) if pnl_usd is not None else None)
        except (TypeError, ValueError):
            pnl_num = None
        status = "PENDING" if pnl_num is None else ("HIT" if pnl_num > 0 else ("MISS" if pnl_num < 0 else "PARTIAL"))
        mint = rec.get("mint")
        closed_age = age_seconds(rec.get("closed_at_utc"), now)
        outcomes.append({
            "id": f"OUT-{i + 1:04d}",
            "token": rec.get("token_symbol") or short_mint(mint),
            "tokenSub": short_mint(mint),
            "mint": mint,
            "pair": f"{short_mint(mint)} / SOL",
            "pairQuote": "SOL",
            "decision": "PAPER_TRADE",
            "reason": str(rec.get("reason_closed") or "CLOSED"),
            "tier": str(rec.get("tier") or "--"),
            "decisionT": fmt_age(closed_age),
            "tAbs": fmt_clock(rec.get("closed_at_utc")),
            "window": fmt_age(rec.get("hold_seconds")) if rec.get("hold_seconds") else "—",
            "status": status,
            "maxBounce": rec.get("max_up_pct"),
            "maxDrawdown": (-abs(rec["max_drawdown_pct"]) if isinstance(rec.get("max_drawdown_pct"), (int, float)) else None),
            "athReclaim": None,
            "timeToResult": fmt_age(rec.get("hold_seconds")) if rec.get("hold_seconds") else "—",
            "filters": str(rec.get("strategy_name") or "—"),
            "filtersTone": "info",
            "dataQuality": "COMPLETE" if pnl_num is not None else "PARTIAL",
            "note": f"strategy {rec.get('strategy_name') or '—'} · realized {fmt_usd(pnl_usd)} ({fmt_pct(pnl)})",
        })
    return outcomes


# ─── page bundles ────────────────────────────────────────────────────────────

# Raw WS notifications are an internal firehose counter, NOT the Helius credit meter — every
# surface that shows the counter carries this note.
RAW_WS_NOTE = "raw WS messages — not Helius credits"


def _raw_ws_cap(caps):
    """Canonical raw-WS cap with legacy-artifact fallback (old runs wrote the old key)."""
    if not isinstance(caps, dict):
        return None
    cap = caps.get("max_raw_ws_notifications_total")
    return cap if cap is not None else caps.get("max_ws_notifications_total")


def _producer_core(producer, now):
    """Extract the numbers everything else reuses."""
    summary = producer.get("summary") or {}
    heartbeat = producer.get("heartbeat") or {}
    budget = (heartbeat.get("credit_budget") or summary.get("credit_budget") or {})
    caps = budget.get("caps") or {}
    transport = (heartbeat.get("market_transport_stats")
                 or summary.get("market_transport_stats") or {})
    hb_ts = heartbeat.get("ts_utc") or summary.get("updated_at_utc")
    hb_age = age_seconds(hb_ts, now)
    stop_reason = heartbeat.get("stop_reason") or summary.get("stop_reason")
    status, tone = compute_status(hb_age, stop_reason, PRODUCER_STALE_SECONDS)
    windows = producer.get("windows") or []
    # PHX2-E2E-005: a quarantined or unreadable authoritative checkpoint is
    # NEVER rendered as an empty healthy watchlist.
    checkpoint_doc = (producer.get("checkpoint_status")
                      or summary.get("checkpoint") or {})
    quarantine_doc = producer.get("checkpoint_quarantine") or {}
    watch_cp = checkpoint_doc.get("watch") or {}
    ath_cp = checkpoint_doc.get("ath") or {}
    watch_file_present = bool(
        ((producer.get("files") or {}).get("watch_state.jsonl") or {})
        .get("present"))
    watch_skipped = int(
        (producer.get("skipped_lines") or {}).get("watch_state.jsonl") or 0)
    watch_header = producer.get("watch_checkpoint_header")
    checkpoint_quarantined = bool(
        quarantine_doc
        or watch_cp.get("checkpoint_quarantined")
        or ath_cp.get("checkpoint_quarantined"))
    checkpoint_unreadable = bool(
        watch_file_present and watch_header is None
        and not (producer.get("watch") or {}) and watch_skipped)
    if checkpoint_quarantined:
        checkpoint_display = "QUARANTINED"
        status, tone = "CHECKPOINT_QUARANTINED", "bad"
    elif checkpoint_unreadable:
        checkpoint_display = "UNREADABLE_SUSPECT"
        status, tone = "CHECKPOINT_UNREADABLE", "bad"
    elif watch_cp.get("checkpoint_status"):
        checkpoint_display = str(watch_cp.get("checkpoint_status"))
    elif watch_header is not None:
        checkpoint_display = "OK"
    else:
        checkpoint_display = "UNKNOWN"
    return {
        "summary": summary, "heartbeat": heartbeat, "budget": budget, "caps": caps,
        "transport": transport, "hb_ts": hb_ts, "hb_age": hb_age,
        "stop_reason": stop_reason, "status": status, "tone": tone,
        "windows": windows,
        "checkpoint": {
            "display": checkpoint_display,
            "quarantined": checkpoint_quarantined,
            "unreadable_suspect": checkpoint_unreadable,
            "quarantine_reason": (
                watch_cp.get("checkpoint_quarantine_reason")
                or ath_cp.get("checkpoint_quarantine_reason")
                or ((quarantine_doc.get("watch") or {})
                    .get("checkpoint_quarantine_reason"))
                or ((quarantine_doc.get("ath") or {})
                    .get("checkpoint_quarantine_reason"))),
            "watch_status": watch_cp.get("checkpoint_status"),
            "ath_status": ath_cp.get("checkpoint_status"),
            "watch_generation": watch_cp.get("checkpoint_generation"),
            "quarantined_candidates": (
                watch_cp.get("checkpoint_quarantined_candidates")
                or len(producer.get("watch_quarantined") or {})),
            "recovered_from_backup": bool(
                watch_cp.get("checkpoint_recovered_from_backup")
                or ath_cp.get("checkpoint_recovered_from_backup")),
            "legacy_activation_migrated": watch_cp.get(
                "checkpoint_legacy_activation_migrated"),
        },
        "discovery_mode": str(heartbeat.get("discovery_mode")
                              or summary.get("discovery_mode") or "WS").upper(),
        "market_freshness": (heartbeat.get("market_freshness")
                             or summary.get("market_freshness") or {}),
        "market_scheduler": (heartbeat.get("market_scheduler")
                             or summary.get("market_scheduler") or {}),
        "polling": (budget.get("polling") or {}),
        "watch_by_status": (heartbeat.get("watchlist_by_status")
                            or (summary.get("watchlist_summary") or {}).get("by_status") or {}),
        "watch_total": heartbeat.get("watchlist_total")
                       or (summary.get("watchlist_summary") or {}).get("total"),
        # Active watches vs archived terminal history are distinct counts
        # (PHX2-E2E-002): terminal candidates are never shown as tracked.
        "watch_active": (heartbeat.get("watchlist_count")
                         if heartbeat.get("watchlist_count") is not None
                         else heartbeat.get("watchlist_tracked")
                         if heartbeat.get("watchlist_tracked") is not None
                         else (summary.get("watchlist_summary") or {}).get("tracked")),
        "watch_capacity": (heartbeat.get("watchlist_active_capacity")
                           or (summary.get("watchlist_summary") or {}).get("active_capacity")),
        "watch_terminal_history": (heartbeat.get("watchlist_terminal_history_total")
                                   if heartbeat.get("watchlist_terminal_history_total") is not None
                                   else (summary.get("watchlist_summary") or {}).get("terminal_history")),
        "watch_capacity_rejections": (heartbeat.get("watchlist_capacity_rejections")
                                      if heartbeat.get("watchlist_capacity_rejections") is not None
                                      else (summary.get("watchlist_summary") or {}).get("capacity_rejections")),
        "no_send_reasons": _sum_no_send_reasons(producer.get("heartbeat_lines") or []),
        "risk_summary": (heartbeat.get("risk_summary")
                         or summary.get("risk_summary") or {}),
        "risk_discord_block": (heartbeat.get("risk_discord_block")
                               or summary.get("risk_discord_block") or {}),
        "provider_telemetry": (heartbeat.get("provider_telemetry")
                               or summary.get("provider_telemetry") or {}),
        "discord_blocks": producer.get("discord_blocks") or [],
    }


def _sum_no_send_reasons(hb_lines):
    totals = {}
    for rec in hb_lines:
        for key, val in (rec.get("no_send_reasons") or {}).items():
            try:
                totals[key] = totals.get(key, 0) + int(val)
            except (TypeError, ValueError):
                continue
    return totals


def _paper_core(paper, now):
    heartbeat = paper.get("heartbeat") or {}
    monitor = paper.get("monitor") or {}
    summary = paper.get("summary") or {}
    hb_ts = heartbeat.get("heartbeat_utc") or monitor.get("as_of_utc")
    hb_age = age_seconds(hb_ts, now)
    status, tone = compute_status(hb_age, None, PAPER_STALE_SECONDS)
    strategies = summary.get("strategies") or {}
    open_total = heartbeat.get("open_positions_total")
    if open_total is None:
        open_total = sum(int(s.get("open_trades") or 0) for s in strategies.values()) if strategies else None
    closed_total = sum(int(s.get("closed_trades") or 0) for s in strategies.values()) if strategies else None
    realized = sum(float(s.get("realized_pnl_usd") or 0) for s in strategies.values()) if strategies else None
    unrealized = sum(float(s.get("unrealized_pnl_usd") or 0) for s in strategies.values()) if strategies else None
    skips = {}
    for strat in strategies.values():
        for reason, count in (strat.get("skip_reasons") or {}).items():
            try:
                skips[reason] = skips.get(reason, 0) + int(count)
            except (TypeError, ValueError):
                continue

    # overall win rate: weighted across strategies with closed trades
    weighted, weight = 0.0, 0
    for strat in strategies.values():
        closed = int(strat.get("closed_trades") or 0)
        rate = strat.get("win_rate_pct")
        if closed and isinstance(rate, (int, float)):
            weighted += float(rate) * closed
            weight += closed
    win_rate = (weighted / weight) if weight else None

    def _trade_pnl(trade):
        if isinstance(trade, dict):
            val = trade.get("realized_pnl_usd", trade.get("pnl_usd"))
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        return None

    best_trade, worst_trade = None, None
    for strat in strategies.values():
        for cand in (strat.get("best_trade"), strat.get("worst_trade")):
            pnl = _trade_pnl(cand)
            if pnl is None:
                continue
            if best_trade is None or pnl > _trade_pnl(best_trade):
                best_trade = cand
            if worst_trade is None or pnl < _trade_pnl(worst_trade):
                worst_trade = cand

    total = None
    if realized is not None or unrealized is not None:
        total = (realized or 0.0) + (unrealized or 0.0)

    return {
        "heartbeat": heartbeat, "monitor": monitor, "summary": summary,
        "hb_ts": hb_ts, "hb_age": hb_age, "status": status, "tone": tone,
        "strategies": strategies,
        "ranking": summary.get("strategy_ranking") or (paper.get("comparison") or {}).get("ranking") or [],
        "open_total": open_total, "closed_total": closed_total,
        "realized": realized, "unrealized": unrealized, "total_pnl": total,
        "win_rate": win_rate, "best_trade": best_trade, "worst_trade": worst_trade,
        "skips": skips,
    }


def _discord_block(core, producer, ledger_lines, now):
    budget = core["budget"]
    summary = core["summary"]
    enabled = summary.get("private_discord_enabled")
    if enabled is None:
        enabled = (core["heartbeat"] or {}).get("private_discord_enabled")
    sent_ok = budget.get("sent_ok_count") or 0
    budget_stop = budget.get("budget_stop_reason")
    outcome = summary.get("outcome")
    if sent_ok:
        last_result, last_tone = "SENT_OK", "ok"
    elif budget_stop:
        last_result, last_tone = f"BUDGET_STOP · {budget_stop}", "warn"
    elif outcome == "ZERO_SEND":
        last_result, last_tone = "NO_ELIGIBLE_CANDIDATE", "info"
    elif outcome:
        last_result, last_tone = str(outcome), "info"
    else:
        last_result, last_tone = "UNKNOWN", "muted"

    def _ping_label(records, ts_keys):
        if not records:
            return "—"
        rec = records[-1]
        mint = short_mint(rec.get("token_mint") or rec.get("mint"))
        ts = next((rec.get(k) for k in ts_keys if rec.get(k)), None)
        age = age_seconds(ts, now)
        return f"{mint} · {fmt_age(age)} ago" if age is not None else mint

    no_send = core["no_send_reasons"] or {}
    if sent_ok:
        last_no_ping = "—"
    elif no_send:
        top = max(no_send.items(), key=lambda kv: kv[1])
        last_no_ping = f"{top[0]} ×{top[1]}"
    elif outcome == "ZERO_SEND":
        last_no_ping = "NO_ELIGIBLE_CANDIDATE"
    else:
        last_no_ping = "—"

    return {
        "last_would_ping": _ping_label(producer.get("would_pings"), ("observed_at_utc", "ts_utc")),
        "last_sent_ping": _ping_label(producer.get("sent_pings"), ("sent_at_utc", "ts_utc")),
        "last_no_ping_reason": last_no_ping,
        "enabled": "YES" if enabled is True else ("NO" if enabled is False else "UNKNOWN"),
        "enabled_tone": "ok" if enabled is True else "muted",
        "last_ping_result": last_result,
        "last_ping_tone": last_tone,
        "outcome": outcome or "—",
        "private_ping_count": budget.get("private_ping_count"),
        "would_ping_count": budget.get("would_ping_count"),
        "send_attempts": budget.get("send_attempts"),
        "sent_ok_count": sent_ok,
        "max_sends_per_run": (core["caps"] or {}).get("max_sends_per_run"),
        "dedupe_suppressed_total": (core["heartbeat"] or {}).get("dedupe_suppressed_total"),
        "ledger_lines": ledger_lines,
        "ledger_delta_total": summary.get("ledger_delta_total"),
        "seconds_since_last_send": (core["heartbeat"] or {}).get("seconds_since_last_send"),
        "routing_note": "private operator webhook only — no public/subscriber routing",
        "public_or_subscriber_routing": bool(summary.get("public_or_subscriber_routing", False)),
        # risk gate: pings the producer BLOCKED before reserve/webhook (never sent)
        "high_risk_discord_block_count":
            (core.get("risk_discord_block") or {}).get("high_risk_discord_block_count") or 0,
        "medium_risk_structure_block_count":
            (core.get("risk_discord_block") or {}).get("medium_risk_structure_block_count") or 0,
    }


def _remaining(cap, used):
    try:
        return max(0, int(cap) - int(used or 0))
    except (TypeError, ValueError):
        return None


def _market_freshness_block(core):
    """Market-freshness surface (producer heartbeat -> dashboard)."""
    fresh = core.get("market_freshness") or {}
    per_mint = []
    for row in (fresh.get("per_mint") or [])[:32]:
        if not isinstance(row, dict):
            continue
        per_mint.append({
            "token": short_mint(row.get("token_mint")),
            "mint": row.get("token_mint"),
            "origin": row.get("origin"),
            "status": row.get("status"),
            "last_success_age": fmt_age(row.get("last_success_age_s")),
            "records": row.get("records"),
            "misses": row.get("misses"),
            "market_provider": row.get("market_provider"),
            "ath_price_usd": row.get("ath_price_usd"),
            "ath_observed_at_utc": row.get("ath_observed_at_utc"),
            "ath_observation_type": row.get("ath_observation_type"),
        })
    return {
        "market_data_fresh_count": fresh.get("market_data_fresh_count"),
        "market_data_stale_count": fresh.get("market_data_stale_count"),
        "market_unavailable_count": fresh.get("market_unavailable_count"),
        "last_successful_market_refresh_at": fresh.get("last_successful_market_refresh_at"),
        "last_market_error": fresh.get("last_market_error"),
        "refresh_success_total": fresh.get("refresh_success_total"),
        "refresh_miss_total": fresh.get("refresh_miss_total"),
        "per_mint": per_mint,
    }


def _discovery_block(core):
    budget, caps, transport = core["budget"], core["caps"], core["transport"]
    hb = core["heartbeat"] or {}
    windows = core["windows"]
    last_window = hb.get("last_discovery_window") or (windows[-1] if windows else {})
    dup_skipped = sum(int(w.get("dup_signatures_skipped") or 0) for w in windows)
    null_fetches = sum(int(w.get("null_fetches") or 0) for w in windows)
    polling = core.get("polling") or {}
    return {
        "discovery_mode": core.get("discovery_mode") or "WS",
        "raw_ws_note": RAW_WS_NOTE,
        "polling": {
            "poll_count": polling.get("poll_count"),
            "pools_listed": polling.get("pools_listed"),
            "pools_new": polling.get("pools_new"),
            "signatures_seen": polling.get("signatures_seen"),
            "signatures_new": polling.get("signatures_new"),
            "transactions_fetched": polling.get("transactions_fetched"),
            "create_pool_candidates": polling.get("create_pool_candidates"),
            "pump_suffix_accepted": polling.get("pump_suffix_accepted"),
            "non_pump_guard_dropped": polling.get("non_pump_guard_dropped"),
            "pools_skipped_too_hot": polling.get("pools_skipped_too_hot"),
            "polling_errors": polling.get("polling_errors"),
            "polling_429": polling.get("polling_429"),
        },
        "market_freshness": _market_freshness_block(core),
        "market_scheduler": dict(core.get("market_scheduler") or {}),
        "provider_telemetry": dict(core.get("provider_telemetry") or {}),
        "remaining": {
            "ws_notifications": _remaining(_raw_ws_cap(caps), budget.get("ws_notifications_seen")),
            "market_requests": _remaining(caps.get("max_market_requests_total"), budget.get("market_requests")),
            "sends": _remaining(caps.get("max_sends_per_run"), budget.get("sent_ok_count")),
            "candidates": _remaining(caps.get("max_candidates_total"), budget.get("candidate_count")),
            "gettransaction": _remaining(caps.get("max_gettransaction_total"), budget.get("gettransaction_fetches")),
        },
        "max_sends_per_run": caps.get("max_sends_per_run"),
        "ws_notifications_seen": budget.get("ws_notifications_seen"),
        "raw_ws_notifications_seen": (budget.get("raw_ws_notifications_seen")
                                      if budget.get("raw_ws_notifications_seen") is not None
                                      else budget.get("ws_notifications_seen")),
        "ws_notifications_cap": _raw_ws_cap(caps),
        "seed_windows": budget.get("seed_windows"),
        "seed_windows_cap": caps.get("max_seed_windows"),
        "candidate_count": budget.get("candidate_count"),
        "candidate_cap": caps.get("max_candidates_total"),
        "watch_total": core["watch_total"],
        "watch_by_status": core["watch_by_status"],
        "watching_now": (core["watch_by_status"] or {}).get("WATCHING"),
        "dropped_non_pump": hb.get("dropped_non_pump_total")
                            or (core["watch_by_status"] or {}).get("DROPPED_NON_PUMP"),
        "non_pump_guard_dropped": (hb.get("non_pump_guard_dropped_total")
                                   if hb.get("non_pump_guard_dropped_total") is not None
                                   else core["summary"].get("non_pump_guard_dropped_total")),
        "expired_total": hb.get("expired_total"),
        "market_requests": budget.get("market_requests"),
        "market_requests_cap": caps.get("max_market_requests_total"),
        "market_http_calls": transport.get("http_calls_total"),
        "market_pairs_calls": transport.get("pairs_calls"),
        "market_ohlcv_calls": transport.get("ohlcv_calls"),
        "market_cache_hits": transport.get("cache_hits"),
        "market_http_429": transport.get("http_429"),
        "market_http_errors": transport.get("http_errors"),
        "market_malformed": transport.get("malformed_bodies"),
        "gettransaction_fetches": budget.get("gettransaction_fetches"),
        "gettransaction_cap": caps.get("max_gettransaction_total"),
        "rpc_429_count": budget.get("429_count"),
        "rpc_429_cap": caps.get("max_429_total"),
        "rpc_errors_total": budget.get("rpc_errors_total"),
        "budget_stop_reason": budget.get("budget_stop_reason"),
        "budget_stop_requested": budget.get("budget_stop_requested"),
        "windows_blocked_by_budget": budget.get("windows_blocked_by_budget"),
        "reseeds": hb.get("reseeds_total") or core["summary"].get("reseeds"),
        "ticks": hb.get("tick") or core["summary"].get("ticks"),
        "axiom_pass_total": hb.get("axiom_pass_total"),
        "axiom_fail_total": hb.get("axiom_fail_total"),
        "dup_signatures_skipped": dup_skipped,
        "null_fetches": null_fetches,
        "windows_recorded": len(windows),
        "last_window_ended": last_window.get("window_ended_at_utc"),
        "last_window_notifications": last_window.get("notifications_seen"),
        "no_send_reasons": core["no_send_reasons"],
        "pricing_tail_tracked": (hb.get("pricing_tail") or {}).get("tracked"),
    }


def _num(value):
    """Coerce an operator-entered credit value to int/float, or None. Never raises."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _credit_panel(core, helius_credits):
    """Helius credit panel — operator-facing, MANUAL entry only.

    Helius dashboard credits are entered by the operator in ``config.json`` (``helius_credits``);
    this dashboard NEVER reads the Helius dashboard, an API key, or any account, and never asks for
    one. Raw WS messages are NOT Helius credits (they are an internal firehose counter). Burn/hour,
    burn/day and credits/ping are DERIVED only when the operator supplies before/after (+ a window);
    until then only observed producer counters are shown, with a hint on how to enable the estimate.
    """
    budget = core["budget"]
    polling = core.get("polling") or {}
    transport = core["transport"]
    sent_pings = budget.get("sent_ok_count") or 0
    raw_ws = (budget.get("raw_ws_notifications_seen")
              if budget.get("raw_ws_notifications_seen") is not None
              else budget.get("ws_notifications_seen"))

    manual = helius_credits if isinstance(helius_credits, dict) else {}
    before = _num(manual.get("before"))
    after = _num(manual.get("after"))
    window_s = _num(manual.get("window_seconds"))
    free_tier_total = _num(manual.get("free_tier_total")) or 1_000_000

    used = per_hour = per_day = per_ping = days_left = None
    provided = before is not None and after is not None
    if provided:
        used = max(0, int(round(after - before)))          # only forward deltas
        if window_s and window_s > 0:
            per_hour = round(used / (window_s / 3600.0), 1)
            per_day = round(per_hour * 24.0, 1)
            if per_day > 0:
                days_left = round(max(0.0, free_tier_total - after) / per_day, 2)
        if sent_pings:
            per_ping = round(used / sent_pings, 1)

    return {
        "manual_entry": True,
        "auto_read": False,
        "entry_provided": provided,
        "source_note": ("Helius dashboard credits are operator-entered in config.json "
                        "(helius_credits: before / after / window_seconds). This dashboard never "
                        "reads the Helius dashboard, an API key, or any account."),
        "raw_ws_note": RAW_WS_NOTE,
        "discovery_mode": core.get("discovery_mode") or "WS",
        # ── observed producer counters (NOT Helius credits; shown for correlation) ──
        "raw_ws_msg_count": raw_ws,
        "polling_tx_count": polling.get("transactions_fetched"),
        "polling_getsig_pages": polling.get("pools_new"),
        "market_http_calls": transport.get("http_calls_total"),
        "gettransaction_fetches": budget.get("gettransaction_fetches"),
        "sent_pings": sent_pings,
        # ── operator-entered credit values (None until entered) ──
        "credits_before": before,
        "credits_after": after,
        "window_seconds": window_s,
        "as_of_utc": manual.get("as_of_utc"),
        "free_tier_total": free_tier_total,
        # ── derived (None until before/after provided) ──
        "credits_used": used,
        "credits_per_hour": per_hour,
        "credits_per_day": per_day,
        "credits_per_ping": per_ping,
        "days_to_exhaust": days_left,
        "entry_hint": (None if provided else
                       "Set config.json helius_credits {before, after, window_seconds} from the "
                       "Helius dashboard to compute burn/hour, burn/day and credits/ping."),
    }


def _fmt_trade(trade):
    if not trade:
        return "—"
    if isinstance(trade, dict):
        sym = trade.get("token_symbol") or short_mint(trade.get("mint"))
        pnl = trade.get("realized_pnl_usd", trade.get("pnl_usd"))
        pct = trade.get("realized_pnl_pct", trade.get("pnl_pct"))
        return f"{sym} · {fmt_usd(pnl)} ({fmt_pct(pct)})"
    return str(trade)


def build_bundle(producer_dir, paper_dir, ledger_path=None, now=None, helius_credits=None):
    """The full dashboard payload. Every string passes the redaction filter.

    ``helius_credits`` is an OPTIONAL operator-entered dict (from config.json) used only to derive
    the manual Helius credit panel; it is never a secret, an API key, or auto-read.
    """
    now = _now(now)
    errors = []

    producer = load_producer(producer_dir, now)
    paper = load_paper(paper_dir, now)
    for name, err in producer["io_errors"].items():
        errors.append(f"producer/{name}: {err}")
    for name, err in paper["io_errors"].items():
        errors.append(f"paper/{name}: {err}")

    core = _producer_core(producer, now)
    pcore = _paper_core(paper, now)

    ledger_lines = None
    if ledger_path:
        ledger_lines = count_lines(Path(ledger_path))

    candidate_rows = build_candidate_rows(producer, now)
    decisions = build_decisions(producer, now)
    outcomes = build_outcomes(paper, now)

    run_id = Path(str(producer_dir)).name
    paper_run_id = (pcore["heartbeat"].get("run_id")
                    or (pcore["summary"] or {}).get("run_id")
                    or Path(str(paper_dir)).name)

    bundle = {
        "meta": {
            "schema": SCHEMA_VERSION,
            "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "producer_dir": str(producer_dir),
            "paper_dir": str(paper_dir),
            "read_only": True,
            "errors": errors,
            "producer_files": producer["files"],
            "paper_files": paper["files"],
            "skipped_lines": {
                "producer": producer["skipped_lines"],
                "paper": paper["skipped_lines"],
            },
        },
        "paper": _paper_page(core, pcore, producer, paper, candidate_rows,
                             ledger_lines, run_id, paper_run_id, now),
        "live": _live_page(core, pcore, producer, candidate_rows, decisions,
                           ledger_lines, run_id, now),
        "candidates": _candidates_page(core, candidate_rows),
        "decisions": {"decisions": decisions},
        "outcomes": {"outcomes": outcomes},
        "runs": _runs_page(core, pcore, producer, paper, run_id, paper_run_id, now),
        "research": {"studies": []},
    }
    # Manual Helius credit panel (operator-entered; never auto-read). Exposed top-level and on the
    # paper page (next to discovery counters) so the operator can see burn/hour + credits/ping.
    credit_panel = _credit_panel(core, helius_credits)
    bundle["credit_panel"] = credit_panel
    bundle["paper"]["credit_panel"] = credit_panel
    return redact_value(bundle)


def _discovery_metric(mode, ws_seen, polling):
    """Feed-status metric for the discovery source: WS / POLLING / HYBRID."""
    def _m(label, value, tone="info"):
        return {"label": label, "value": value, "tone": tone}
    polls = polling.get("poll_count")
    accepted = polling.get("pump_suffix_accepted")
    if mode == "POLLING":
        return _m("Discovery · POLLING",
                  f"{fmt_int(polls)} polls · {fmt_int(accepted)} accepted",
                  "ok" if polls else "muted")
    if mode == "HYBRID":
        return _m("Discovery · HYBRID",
                  f"{fmt_int(ws_seen)} raw WS · {fmt_int(polls)} polls",
                  "ok" if (ws_seen or polls) else "muted")
    return _m("Discovery · WS",
              f"{fmt_int(ws_seen)} raw msgs (not credits)",
              "ok" if ws_seen else "muted")


def _live_page(core, pcore, producer, candidate_rows, decisions, ledger_lines, run_id, now):
    budget, transport = core["budget"], core["transport"]
    hb = core["heartbeat"] or {}

    def _m(label, value, tone="info"):
        return {"label": label, "value": value, "tone": tone}

    ws_seen = budget.get("ws_notifications_seen")
    mode = core.get("discovery_mode") or "WS"
    polling = core.get("polling") or {}
    freshness = core.get("market_freshness") or {}
    provider = core.get("provider_telemetry") or {}
    provider_mode = str(provider.get("provider_mode") or "FREE_TIER")
    paid_provider = provider_mode != "FREE_TIER"
    ticks = hb.get("tick") or core["summary"].get("ticks")
    run_minutes = None
    first_hb = (producer.get("heartbeat_lines") or [{}])[0]
    first_ts = parse_iso(first_hb.get("ts_utc"))
    last_ts = parse_iso(core["hb_ts"])
    if first_ts and last_ts and last_ts > first_ts:
        run_minutes = max(1.0, (last_ts - first_ts).total_seconds() / 60.0)

    sends = hb.get("sends_total") or budget.get("sent_ok_count") or 0
    overall = "STOPPED" if core["status"] == "STOPPED" else core["status"]
    overall_tone = core["tone"]
    if paid_provider:
        provider_metric = _m(
            f"Provider · {provider_mode}",
            f"{provider.get('status') or 'UNKNOWN'} · streams "
            f"{fmt_int(provider.get('active_streams'))}/{fmt_int(provider.get('stream_capacity'))} "
            f"(max {fmt_int(provider.get('max_active_streams'))})",
            "ok" if provider.get("status") == "CONNECTED" else "warn")
        provider_health = _m(
            "gRPC Stream Age · Reconnects",
            f"{fmt_age(provider.get('last_message_age_s'))} · "
            f"{fmt_int(provider.get('reconnects'))}",
            "ok" if provider.get("status") == "CONNECTED" else "warn")
        events_metric = _m("gRPC Events", fmt_int(provider.get("events_received")), "info")
        dedupe_metric = _m(
            "Provider Duplicates",
            f"sig {fmt_int((provider.get('dedupe') or {}).get('duplicate_events_dropped'))} · "
            f"mint {fmt_int((provider.get('dedupe') or {}).get('duplicate_mints_dropped'))}",
            "info")
    else:
        provider_metric = _discovery_metric(mode, ws_seen, polling)
        provider_health = _m("WS Error Windows", fmt_int(budget.get("ws_error_windows")),
                             "ok" if not budget.get("ws_error_windows") else "warn")
        events_metric = _m(
            "WS Notif / min",
            fmt_int(ws_seen / run_minutes) if (ws_seen and run_minutes) else "—", "info")
        dedupe_metric = _m(
            "Dup Signatures Skipped",
            fmt_int(sum(int(w.get("dup_signatures_skipped") or 0) for w in core["windows"])),
            "info")

    live_feed = []
    for row in candidate_rows:
        live_feed.append({
            "token": row["token"], "tokenSub": row["tokenSub"], "mint": row.get("mint"),
            "pair": row["pair"],
            "lifecycle": row["lifecycle"], "mcap": row["mcap"], "liq": row["liq"],
            "ath": row["ath"], "drawdown": "—", "drawdownTone": "muted",
            "tier": "T?", "filters": row["filters"], "filtersTone": row["filtersTone"],
            "decision": row["filters"], "decisionTone": "skipped" if row["stage"] in ("DEAD", "DECAYING") else "watching",
            "updated": row["updated"],
        })

    strip = []
    tone_map = {"SKIP": "skipped", "CANDIDATE": "ember", "WOULD_ALERT": "called", "SENT": "called", "WATCH": "watching"}
    for dec in decisions[:10]:
        strip.append({
            "t": dec["t"], "type": dec["decision"] if dec["decision"] != "SKIP" else dec["reason"],
            "token": dec["pair"], "mint": dec.get("mint"),
            "reason": (dec["knew"][0] if dec["knew"] else dec["reason"]),
            "tone": tone_map.get(dec["decision"], "watching"),
        })

    return {
        "header": {
            "env": "private-live",
            "node": run_id,
            "uptime": fmt_age(run_minutes * 60 if run_minutes else None),
            "pulseLabel": "artifact feed" if core["status"] == "RUNNING" else core["status"].lower(),
            "overall": overall, "overallTone": overall_tone,
        },
        "feedStatus": {
            "bot": _m("Producer", f"{core['status']}" + (f" · {core['stop_reason']}" if core["stop_reason"] else ""), core["tone"]),
            "db": _m("Paper Engine", f"{pcore['status']} · {fmt_int(pcore['heartbeat'].get('snapshots_processed'))} snaps", pcore["tone"]),
            "provider": provider_metric,
            "priceApi": _m("Market Data API", f"{fmt_int(transport.get('http_calls_total'))} calls · {fmt_int(transport.get('http_429'))}×429",
                           "ok" if not transport.get("http_429") else "warn"),
            "discord": _m("Private Discord", ("ENABLED" if core["summary"].get("private_discord_enabled") else "DISABLED")
                          + f" · {sends} sent", "ok" if core["summary"].get("private_discord_enabled") else "muted"),
            "lastEvent": _m("Last Heartbeat", fmt_age(core["hb_age"]) + " ago", "info"),
            "lastWrite": _m("Last Artifact Write", _newest_write(producer, now), "info"),
            "queue": _m("Watchlist Active", fmt_int(hb.get("watchlist_active")), "info"),
            "dedupe": _m("Dedupe Ledger", f"{fmt_int(ledger_lines)} lines · Δ{fmt_int(core['summary'].get('ledger_delta_total'))} this run", "ok"),
            "rawCap": _m("Budget Stop", str(budget.get("budget_stop_reason") or "none"), "ok" if not budget.get("budget_stop_reason") else "warn"),
        },
        "systemHealth": {
            "providerHealth": provider_health,
            "rpcLatency": _m("RPC Errors", fmt_int(budget.get("rpc_errors_total")), "ok" if not budget.get("rpc_errors_total") else "warn"),
            "eventsMin": events_metric,
            "malformed": _m("Malformed Bodies", fmt_int(transport.get("malformed_bodies")), "ok" if not transport.get("malformed_bodies") else "warn"),
            "dedupeHits": dedupe_metric,
            "rawCaps": _m("Seed Windows", f"{fmt_int(budget.get('seed_windows'))} / {fmt_int((core['caps'] or {}).get('max_seed_windows'))}", "info"),
            "failedNorm": _m("Null TX Fetches", fmt_int(sum(int(w.get("null_fetches") or 0) for w in core["windows"])), "ok"),
            "priceFresh": _m(
                "Market Fresh · Stale · Unavail",
                f"{fmt_int(freshness.get('market_data_fresh_count'))} · "
                f"{fmt_int(freshness.get('market_data_stale_count'))} · "
                f"{fmt_int(freshness.get('market_unavailable_count'))} "
                f"({fmt_int((hb.get('pricing_tail') or {}).get('tracked'))} tailed)",
                ("warn" if (freshness.get("market_data_stale_count")
                            or freshness.get("market_unavailable_count"))
                 else ("ok" if freshness.get("market_data_fresh_count") else "info"))),
            "rateLimit": _m("429s (RPC · market)", f"{fmt_int(budget.get('429_count'))} · {fmt_int(transport.get('http_429'))}",
                            "ok" if not (budget.get("429_count") or transport.get("http_429")) else "warn"),
            "dispatch": _m("Sends (would · real)", f"{fmt_int(budget.get('would_ping_count'))} · {fmt_int(sends)}",
                           "ok" if sends else "info"),
        },
        "deltaTitle": f"Run Counters · Budget · {mode}",
        "deltaEyebrow": "05 · Budget",
        "deltaWindow": f"{ticks or '—'} ticks",
        "delta": [
            {"label": "Discovery Mode", "value": mode, "tone": "info"},
            {"label": "Raw WS Msgs (not credits)", "value": fmt_int(ws_seen)},
            {"label": "Seed Windows", "value": f"{fmt_int(budget.get('seed_windows'))} / {fmt_int((core['caps'] or {}).get('max_seed_windows'))}"},
            {"label": "Polls · New Pools", "value": f"{fmt_int(polling.get('poll_count'))} · {fmt_int(polling.get('pools_new'))}"},
            {"label": "Poll TX Fetched", "value": fmt_int(polling.get("transactions_fetched"))},
            {"label": "Candidates (budget)", "value": fmt_int(budget.get("candidate_count")), "tone": "ember"},
            {"label": "Watchlist Total", "value": fmt_int(core["watch_total"]), "tone": "watching"},
            {"label": "Active Watches",
             "value": f"{fmt_int(core.get('watch_active'))} / {fmt_int(core.get('watch_capacity'))}",
             "tone": "watching"},
            {"label": "Terminal History", "value": fmt_int(core.get("watch_terminal_history")), "tone": "muted"},
            {"label": "Capacity Rejections", "value": fmt_int(core.get("watch_capacity_rejections")),
             "tone": "warn" if core.get("watch_capacity_rejections") else "muted"},
            {"label": "Watching Now", "value": fmt_int((core["watch_by_status"] or {}).get("WATCHING")), "tone": "watching"},
            {"label": "Dropped Non-pump", "value": fmt_int((core["watch_by_status"] or {}).get("DROPPED_NON_PUMP")), "tone": "muted"},
            {"label": "Market Fresh · Stale", "value": f"{fmt_int(freshness.get('market_data_fresh_count'))} · {fmt_int(freshness.get('market_data_stale_count'))}"},
            {"label": "Risk H · M · L · ?",
             "value": " · ".join(str(v) for v in _risk_counts(core)[:4]),
             "tone": "ember" if _risk_counts(core)[0] else "info"},
            {"label": "Would-ping", "value": fmt_int(budget.get("would_ping_count")), "tone": "called"},
            {"label": "Private Pings Sent", "value": fmt_int(sends), "tone": "ember"},
        ] + ([
            {"label": "gRPC Stream Status", "value": str(provider.get("status") or "UNKNOWN"),
             "tone": "ok" if provider.get("status") == "CONNECTED" else "warn"},
            {"label": "gRPC Active · Max", "value":
             f"{fmt_int(provider.get('active_streams'))} · {fmt_int(provider.get('max_active_streams'))}"},
            {"label": "gRPC Capacity", "value": fmt_int(provider.get("stream_capacity"))},
            {"label": "Provider Fallback", "value":
             "ACTIVE" if provider.get("fallback_active") else "STANDBY",
             "tone": "warn" if provider.get("fallback_active") else "ok"},
            {"label": "Birdeye Retries · 429", "value":
             f"{fmt_int(transport.get('retries'))} · {fmt_int(transport.get('http_429'))}"},
        ] if paid_provider else []),
        "providerTelemetry": dict(provider),
        "liveFeed": live_feed,
        "dexTrending": [],
        "dexTrendingNote": "No DEX-trending comparison source in the free-tier bundle (keyless mode).",
        "decisions": strip,
        "footLeft": "artifact-backed · read-only · no dispatch from dashboard",
        "footRight": "producer " + core["status"].lower(),
    }


def _newest_write(producer, now):
    best = None
    for meta in (producer.get("files") or {}).values():
        age = meta.get("age_s")
        if age is not None and (best is None or age < best):
            best = age
    return fmt_age(best) + " ago" if best is not None else "—"


def _risk_counts(core):
    """(high, medium, low, unknown, assessed) from the producer risk summary."""
    by_label = (core.get("risk_summary") or {}).get("by_label") or {}

    def _n(key):
        try:
            return int(by_label.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    high, med = _n("RISK_HIGH"), _n("RISK_MEDIUM")
    low, unk = _n("RISK_LOW"), _n("RISK_UNKNOWN")
    return high, med, low, unk, high + med + low + unk


def _candidates_page(core, candidate_rows):
    by_status = core["watch_by_status"] or {}
    budget = core["budget"]
    freshness = core.get("market_freshness") or {}
    waiting = sum(1 for r in candidate_rows if r["stage"] == "WAITING_FOR_PRICE")
    r_high, r_med, r_low, r_unk, r_total = _risk_counts(core)
    summary = [
        {"label": "Discovery Mode", "value": core.get("discovery_mode") or "WS",
         "tone": "info"},
        {"label": "Risk H · M · L · ?",
         "value": f"{r_high} · {r_med} · {r_low} · {r_unk}",
         "tone": "bad" if r_high else ("warn" if r_med else "info")},
        {"label": "Market Fresh · Stale · Unavail",
         "value": f"{fmt_int(freshness.get('market_data_fresh_count'))} · "
                  f"{fmt_int(freshness.get('market_data_stale_count'))} · "
                  f"{fmt_int(freshness.get('market_unavailable_count'))}",
         "tone": ("warn" if (freshness.get("market_data_stale_count")
                             or freshness.get("market_unavailable_count")) else "ok")},
        {"label": "Watchlist Total", "value": core["watch_total"] if core["watch_total"] is not None else len(candidate_rows), "tone": "info"},
        {"label": "Active Watches",
         "value": f"{fmt_int(core.get('watch_active'))} / {fmt_int(core.get('watch_capacity'))}",
         "tone": "watching"},
        {"label": "Terminal History", "value": fmt_int(core.get("watch_terminal_history")), "tone": "muted"},
        {"label": "Capacity Rejections", "value": fmt_int(core.get("watch_capacity_rejections")),
         "tone": "warn" if core.get("watch_capacity_rejections") else "muted"},
        {"label": "Watching Now", "value": by_status.get("WATCHING", 0), "tone": "watching"},
        {"label": "Waiting for Market Data", "value": waiting, "tone": "warn"},
        {"label": "Dropped Non-pump", "value": by_status.get("DROPPED_NON_PUMP", 0), "tone": "muted"},
        {"label": "Expired", "value": by_status.get("EXPIRED", 0), "tone": "muted"},
        {"label": "Candidates (budget)", "value": budget.get("candidate_count", 0), "tone": "ember"},
        {"label": "Would-ping", "value": budget.get("would_ping_count", 0), "tone": "called"},
        {"label": "Private Pings", "value": budget.get("private_ping_count", 0), "tone": "called"},
    ]
    return {
        "summary": summary,
        "queue": candidate_rows,
        "headerMeta": {"window": "run", "sort": "seeded", "refresh": "10s"},
    }


def _runs_page(core, pcore, producer, paper, run_id, paper_run_id, now):
    stages = [
        {"id": "PROD", "label": "Producer", "title": "Free-tier private producer",
         "status": "review" if core["status"] == "RUNNING" else "closed",
         "statusLabel": core["status"].capitalize()},
        {"id": "PAPER", "label": "Paper", "title": "Live paper trading engine",
         "status": "review" if pcore["status"] == "RUNNING" else "closed",
         "statusLabel": pcore["status"].capitalize()},
    ]

    def _artifact_rows(files, stage, run_ref, now):
        rows = []
        for name, meta in files.items():
            if not meta.get("present") or name.endswith("/"):
                continue
            rows.append({
                "id": f"{run_ref}::{name}", "name": name,
                "type": "JSONL log" if name.endswith(".jsonl") else "JSON snapshot",
                "stage": stage, "runId": run_ref,
                "rows": f"{meta.get('bytes', 0):,} B",
                "created": fmt_age(meta.get("age_s")) + " ago",
                "hash": "—", "status": "OK", "notes": "—",
            })
        return rows

    budget = core["budget"]
    first_hb = (producer.get("heartbeat_lines") or [{}])[0]
    started_ts = first_hb.get("ts_utc")
    started_age = age_seconds(started_ts, now)
    dur = None
    first_dt, last_dt = parse_iso(started_ts), parse_iso(core["hb_ts"])
    if first_dt and last_dt:
        dur = (last_dt - first_dt).total_seconds()
    producer_warns = int(budget.get("429_count") or 0) + int(budget.get("windows_blocked_by_budget") or 0)
    producer_errors = int((core["summary"] or {}).get("error_count") or 0)
    producer_status = "FAIL" if budget.get("budget_stop_reason") else (
        "WARN" if (producer_warns or producer_errors) else "PASS")

    paper_hb = pcore["heartbeat"] or {}
    uptime = paper_hb.get("uptime_seconds")
    paper_errs = len(paper.get("errors") or [])

    runs = [
        {
            "id": run_id, "stage": "Producer",
            "runType": (core["heartbeat"] or {}).get("producer_mode") or (core["summary"] or {}).get("mode") or "PRODUCER",
            "started": fmt_age(started_age), "startedAbs": fmt_clock(started_ts),
            "duration": fmt_age(dur), "status": producer_status,
            "inputs": {
                "WS": "Helius WS logsSubscribe · pump migrations",
                "POLLING": "HTTP polling · new pools → create_pool tx · pump migrations",
                "HYBRID": "Hybrid WS windows + HTTP polling · pump migrations",
            }.get(core.get("discovery_mode") or "WS", "pump migrations"),
            "outputs": f"artifacts → {Path(str(producer.get('dir'))).name}",
            "artifactsCount": sum(1 for m in producer["files"].values() if m.get("present")),
            "rows": f"{fmt_int((core['heartbeat'] or {}).get('tick'))} ticks · "
                    f"{fmt_int(budget.get('ws_notifications_seen'))} raw-ws · "
                    f"{fmt_int((core.get('polling') or {}).get('poll_count'))} polls",
            "warnings": producer_warns, "errors": producer_errors, "tests": "—",
            "manifestHash": "—",
            "note": f"outcome {(core['summary'] or {}).get('outcome') or '—'} · stop {core['stop_reason'] or '—'} · "
                    f"sends {budget.get('sent_ok_count') or 0} · would {budget.get('would_ping_count') or 0}",
            "artifactsList": _artifact_rows(producer["files"], "Producer", run_id, now),
        },
        {
            "id": paper_run_id, "stage": "Paper",
            "runType": paper_hb.get("mode") or "LIVE_PAPER",
            "started": fmt_age((pcore["hb_age"] or 0) + uptime if (uptime and pcore["hb_age"] is not None) else None),
            "startedAbs": "—",
            "duration": fmt_age(uptime), "status": "WARN" if paper_errs else "PASS",
            "inputs": " · ".join(str(Path(p).name) for p in (paper_hb.get("watch_inputs") or [])) or "producer out dir",
            "outputs": f"artifacts → {Path(str(paper.get('dir'))).name}",
            "artifactsCount": sum(1 for m in paper["files"].values() if m.get("present")),
            "rows": f"{fmt_int(paper_hb.get('snapshots_processed'))} snapshots",
            "warnings": paper_errs, "errors": 0, "tests": "—",
            "manifestHash": "—",
            "note": (pcore["monitor"] or {}).get("last_skip") or (pcore["monitor"] or {}).get("last_error") or "clean",
            "warningTypes": [str((e.get("kind") or "ERROR")) for e in (paper.get("errors") or [])[:6]],
            "artifactsList": _artifact_rows(paper["files"], "Paper", paper_run_id, now),
        },
    ]
    return {"stages": stages, "runs": runs}


def _paper_page(core, pcore, producer, paper, candidate_rows, ledger_lines,
                run_id, paper_run_id, now):
    budget = core["budget"]
    monitor = pcore["monitor"] or {}
    strategies = pcore["strategies"]
    redaction = producer.get("redaction") or {}
    central_mints = ((producer.get("ath_state") or {}).get("mints") or {})

    # Every strategy account is displayed against a $1,000 starting equity
    # baseline: the artifact's starting_bankroll_usd wins when present, the
    # default fills in when missing. Display-side only — engine untouched.
    ranking = list(pcore["ranking"])
    if not ranking and strategies:
        ranking = [{"rank": i + 1, "strategy_name": name}
                   for i, name in enumerate(sorted(strategies))]
    strategy_rows = []
    for rank in ranking:
        name = rank.get("strategy_name")
        strat = strategies.get(name, {})

        def _num(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        starting = _num(strat.get("starting_bankroll_usd"))
        if starting is None:
            starting = DEFAULT_STARTING_EQUITY_USD
        realized = _num(strat.get("realized_pnl_usd"))
        unrealized = _num(strat.get("unrealized_pnl_usd"))
        total = _num(rank.get("total_pnl_usd"))
        if total is None and (realized is not None or unrealized is not None):
            total = (realized or 0.0) + (unrealized or 0.0)
        equity = _num(strat.get("ending_equity_usd"))
        if equity is None:
            equity = starting + (total or 0.0)
        return_pct = rank.get("total_pnl_pct")
        if return_pct is None and starting:
            return_pct = (equity - starting) / starting * 100.0

        strategy_rows.append({
            "rank": rank.get("rank"), "name": name,
            "starting": fmt_money(starting),
            "equity": fmt_money(equity),
            "realized": fmt_money(realized if realized is not None else 0.0),
            "unrealized": fmt_money(unrealized if unrealized is not None else 0.0),
            "total": fmt_money(total if total is not None else 0.0),
            "return_pct": fmt_pct(return_pct),
            "pnl_usd": fmt_money(total if total is not None else 0.0),
            "pnl_pct": fmt_pct(return_pct),
            "win_rate": fmt_pct(rank.get("win_rate_pct"), signed=False),
            "open": rank.get("open_trades"), "closed": rank.get("closed_trades"),
            "skipped": rank.get("skipped_trades"), "rugged": rank.get("rugged_trades"),
            "data_lost": rank.get("data_lost_trades"),
            "high_risk_skips": (rank.get("high_risk_skips")
                                if rank.get("high_risk_skips") is not None
                                else strat.get("high_risk_skips")),
            "max_dd": fmt_pct(rank.get("max_drawdown_pct"), signed=False),
            "best": _fmt_trade(strat.get("best_trade")),
            "worst": _fmt_trade(strat.get("worst_trade")),
        })

    machine_counts = {}
    bala_machine = {}
    for name, block in (monitor.get("strategies") or {}).items():
        counts = ((block or {}).get("machine") or {}).get("machine_counts") or {}
        if name == "bala_plan":
            bala_machine = dict(counts)
        for state, num in counts.items():
            try:
                machine_counts[state] = machine_counts.get(state, 0) + int(num)
            except (TypeError, ValueError):
                continue

    # equity curve summary: latest point + point count per strategy
    equity_points = {}
    for rec in paper.get("equity") or []:
        name = rec.get("strategy_name")
        if not name:
            continue
        entry = equity_points.setdefault(name, {"points": 0, "latest": None, "latest_ts": None})
        entry["points"] += 1
        entry["latest"] = rec.get("equity_usd")
        entry["latest_ts"] = rec.get("ts_utc")
    equity_summary = [
        {"strategy": name, "points": v["points"], "equity": fmt_usd(v["latest"]),
         "as_of": fmt_age(age_seconds(v["latest_ts"], now)) + " ago" if v["latest_ts"] else "—"}
        for name, v in sorted(equity_points.items())
    ]

    def _position_state(rec):
        """SCOUT / DCA_n leg state when available, else the open reason."""
        legs = rec.get("legs") or []
        if legs:
            last = legs[-1] if isinstance(legs[-1], dict) else {}
            label = last.get("kind") or last.get("label") or last.get("reason")
            if label:
                return f"{label} · {len(legs)} leg{'s' if len(legs) != 1 else ''}"
            return f"{len(legs)} leg{'s' if len(legs) != 1 else ''}"
        state = rec.get("strategy_state") or {}
        if isinstance(state, dict) and state.get("stage"):
            return str(state["stage"])
        return str(rec.get("reason_opened") or "—")

    def _tokens_of(rec):
        for key in ("tokens_open", "estimated_tokens_received", "target_token_amount"):
            val = rec.get(key)
            if isinstance(val, (int, float)) and val:
                return f"{val:,.0f}"
        return "—"

    open_rows = []
    for rec in (paper.get("open_positions") or {}).get("open_positions") or []:
        cost = rec.get("virtual_usd_size")
        unreal = rec.get("unrealized_pnl_usd")
        value = None
        if isinstance(cost, (int, float)) and isinstance(unreal, (int, float)):
            value = cost + unreal
        central_ath = central_mints.get(rec.get("mint")) or {}
        open_rows.append({
            "trade_id": rec.get("paper_trade_id"), "strategy": rec.get("strategy_name"),
            "token": rec.get("token_symbol") or short_mint(rec.get("mint")),
            "tokenSub": short_mint(rec.get("mint")),
            "mint": rec.get("mint"),
            "opened": fmt_age(age_seconds(rec.get("opened_at_utc"), now)),
            "opened_abs": fmt_clock(rec.get("opened_at_utc")),
            "entry": fmt_usd(rec.get("entry_price")),
            "entry_mcap": fmt_usd(rec.get("entry_market_cap")),
            "latest": fmt_usd(rec.get("latest_price")),
            "tokens": _tokens_of(rec),
            "cost": fmt_money(cost),
            "value": fmt_money(value),
            "size": fmt_money(cost),
            "unrealized": fmt_money(unreal),
            "unrealized_pct": fmt_pct(rec.get("unrealized_pnl_pct")),
            "state": _position_state(rec),
            "ath": fmt_usd(central_ath.get("ath_market_cap")
                           or rec.get("ath_market_cap_usd")),
            "athMarketCapUsd": (central_ath.get("ath_market_cap")
                                or rec.get("ath_market_cap_usd")),
            "athPriceUsd": central_ath.get("ath_price") or rec.get("ath_price_usd"),
            "athProvider": central_ath.get("ath_provider") or rec.get("ath_provider"),
            "athTimestamp": (central_ath.get("ath_timestamp")
                             or rec.get("ath_observed_at_utc")),
            **_risk_fields(rec.get("risk_label_at_entry"),
                           rec.get("risk_reasons_at_entry")),
        })

    closed_rows = []
    closed_src = list(paper.get("closed") or [])
    if not closed_src:
        closed_src = [r for r in (paper.get("positions") or [])
                      if str(r.get("status", "")).startswith("CLOSED")]
    for rec in closed_src[-30:]:
        closed_rows.append({
            "trade_id": rec.get("paper_trade_id"), "strategy": rec.get("strategy_name"),
            "token": rec.get("token_symbol") or short_mint(rec.get("mint")),
            "tokenSub": short_mint(rec.get("mint")),
            "mint": rec.get("mint"),
            "entered": fmt_age(age_seconds(rec.get("opened_at_utc"), now)),
            "entered_abs": fmt_clock(rec.get("opened_at_utc")),
            "closed": fmt_age(age_seconds(rec.get("closed_at_utc"), now)),
            "closed_abs": fmt_clock(rec.get("closed_at_utc")),
            "hold": fmt_age(rec.get("hold_seconds")),
            "entry_price": fmt_usd(rec.get("entry_price")),
            "exit_price": fmt_usd(rec.get("exit_price")),
            "tokens": _tokens_of(rec),
            "pnl_usd": fmt_money(rec.get("realized_pnl_usd")),
            "pnl_pct": fmt_pct(rec.get("realized_pnl_pct")),
            "reason": str(rec.get("reason_closed") or "—"),
            **_risk_fields(rec.get("risk_label_at_entry"),
                           rec.get("risk_reasons_at_entry")),
        })

    skip_rows = [r for r in (paper.get("positions") or [])
                 if str(r.get("status", "")).startswith("SKIPPED")][-20:]
    skip_table = [{
        "trade_id": rec.get("paper_trade_id"), "strategy": rec.get("strategy_name"),
        "token": rec.get("token_symbol") or short_mint(rec.get("mint")),
        "mint": rec.get("mint"),
        "reason": str(rec.get("reason_closed") or rec.get("status") or "—"),
        "at": fmt_age(age_seconds(rec.get("closed_at_utc"), now)),
        **_risk_fields(rec.get("risk_label_at_entry"),
                       rec.get("risk_reasons_at_entry")),
        "high_risk_skip": rec.get("status") == "SKIPPED_HIGH_RISK",
    } for rec in skip_rows]

    def _event_detail(rec):
        detail = rec.get("detail") or rec.get("last_skip")
        if detail:
            return str(detail)
        if rec.get("snapshots_processed") is not None:
            return f"snapshots {rec.get('snapshots_processed')}"
        return "—"

    event_rows = []
    for rec in (paper.get("events") or [])[-15:][::-1]:
        mint = rec.get("mint") or rec.get("token_mint")
        event_rows.append({
            "event": str(rec.get("event") or rec.get("kind") or "EVENT"),
            "detail": _event_detail(rec),
            "token": (rec.get("token_symbol") or short_mint(mint)) if mint else None,
            "mint": mint,
            "reason": str(rec.get("reason") or rec.get("reason_closed") or "") or None,
            "strategy": rec.get("strategy_name"),
            "t": fmt_age(age_seconds(rec.get("ts_utc"), now)),
        })

    error_rows = []
    for rec in (producer.get("errors") or [])[-10:]:
        error_rows.append({"source": "producer", "kind": str(rec.get("kind") or "ERROR"),
                           "detail": str(rec.get("error") or rec.get("detail") or "—"),
                           "file": str(Path(str(rec.get("file") or "")).name or "—")})
    for rec in (paper.get("errors") or [])[-10:]:
        error_rows.append({"source": "paper", "kind": str(rec.get("kind") or "ERROR"),
                           "detail": str(rec.get("error") or "—"),
                           "file": str(Path(str(rec.get("file") or "")).name or "—")})

    would_rows = [{
        "token": short_mint(rec.get("token_mint") or rec.get("mint")),
        "mint": rec.get("token_mint") or rec.get("mint"),
        "at": fmt_age(age_seconds(rec.get("observed_at_utc") or rec.get("ts_utc"), now)),
        "reason": str(rec.get("reason") or "WOULD_PING"),
        **_risk_fields(rec.get("risk_label"), rec.get("risk_reasons")),
    } for rec in (producer.get("would_pings") or [])[-20:]]
    sent_rows = [{
        "token": short_mint(rec.get("token_mint") or rec.get("mint")),
        "mint": rec.get("token_mint") or rec.get("mint"),
        "at": fmt_age(age_seconds(rec.get("sent_at_utc") or rec.get("ts_utc"), now)),
        "result": str(rec.get("result") or rec.get("status") or "SENT"),
        **_risk_fields(rec.get("risk_label"), rec.get("risk_reasons")),
    } for rec in (producer.get("sent_pings") or [])[-20:]]

    # ── risk protection surface ──────────────────────────────────────────
    # Producer classifier counts + paper high-risk skips + the observer bucket. The
    # per-strategy PnL rows already EXCLUDE high-risk skips by construction (a skip
    # carries no fills); the observer bucket is the only surface trading RISK_HIGH.
    strat_summaries = pcore["strategies"] or {}
    hr_by_strategy = {}
    hr_reasons = {}
    hr_total = 0
    for sname, sblock in strat_summaries.items():
        try:
            count = int(sblock.get("high_risk_skips") or 0)
        except (TypeError, ValueError):
            count = 0
        if count:
            hr_by_strategy[sname] = count
            hr_total += count
        for hr_reason, hr_count in (sblock.get("high_risk_skip_reasons") or {}).items():
            try:
                hr_reasons[hr_reason] = hr_reasons.get(hr_reason, 0) + int(hr_count)
            except (TypeError, ValueError):
                continue
    observer = None
    monitor_strategies = monitor.get("strategies") or {}
    for sname, sblock in strat_summaries.items():
        machine = ((monitor_strategies.get(sname) or {}).get("machine") or {})
        if sname == "high_risk_observer" or "high_risk_entries" in machine:
            observer = {
                "name": sname,
                "high_risk_entries": machine.get("high_risk_entries"),
                "open": sblock.get("open_trades"),
                "closed": sblock.get("closed_trades"),
                "realized_pnl_usd": sblock.get("realized_pnl_usd"),
                "total_pnl_usd": sblock.get("total_pnl_usd"),
                "total_pnl": fmt_money(sblock.get("total_pnl_usd")),
            }
            break
    bala_machine_block = ((monitor_strategies.get("bala_plan") or {}).get("machine")
                          or {})
    producer_risk = core.get("risk_summary") or {}
    r_high, r_med, r_low, r_unk, r_assessed = _risk_counts(core)
    # Discord dispatch blocks (producer risk gate) — DISTINCT from the paper skips below.
    discord_block = core.get("risk_discord_block") or {}
    discord_blocked_rows = []
    for rec in (core.get("discord_blocks") or [])[-24:]:
        if not isinstance(rec, dict):
            continue
        mc = rec.get("market_context") or {}
        discord_blocked_rows.append({
            "token": short_mint(rec.get("token_mint")),
            "mint": rec.get("token_mint"),
            "terminal_decision": rec.get("terminal_decision"),
            "mapped_reason": rec.get("mapped_reason"),
            "risk_label": rec.get("risk_label"),
            "risk_reasons": rec.get("risk_reasons") or [],
            "liquidity_usd": mc.get("liquidity_usd"),
            "market_cap_usd": mc.get("current_market_cap_usd"),
            "blocked_at_utc": rec.get("blocked_at_utc"),
        })
    risk_protection = {
        "producer_by_label": {"HIGH": r_high, "MEDIUM": r_med,
                              "LOW": r_low, "UNKNOWN": r_unk},
        "producer_assessed": r_assessed,
        "producer_high_risk_mints": len(producer_risk.get("high_risk_mints") or []),
        "producer_reason_counts": producer_risk.get("reason_counts") or {},
        "holder_scan_enabled": bool(producer_risk.get("holder_scan_enabled", False)),
        "risk_note": producer_risk.get("note"),
        "high_risk_skips_total": hr_total,
        "high_risk_skips_by_strategy": hr_by_strategy,
        "high_risk_skip_reasons": hr_reasons,
        "observer": observer,
        "bala_risk_medium_skips": bala_machine_block.get("risk_medium_skips"),
        "bala_last_risk_skip": bala_machine_block.get("last_risk_skip"),
        # ── Discord dispatch blocks (producer risk gate) — the ping never leaves ──
        "discord_high_risk_block_count": discord_block.get("high_risk_discord_block_count") or 0,
        "discord_medium_structure_block_count":
            discord_block.get("medium_risk_structure_block_count") or 0,
        "discord_high_risk_block_reasons": discord_block.get("high_risk_block_reason_counts") or {},
        "discord_medium_block_reasons": discord_block.get("medium_risk_block_reason_counts") or {},
        "discord_blocked_mints": discord_block.get("high_risk_blocked_mints") or [],
        "discord_blocked_candidates": discord_blocked_rows,
        "discord_vs_paper_note": ("'Discord blocked' = the producer risk gate stopped the private "
                                  "ping before reserve/webhook/cap; 'Paper skipped' = the paper "
                                  "strategies declined to trade it (the observer still tracks it "
                                  "separately). Two different surfaces, both from the risk label."),
        "clean_pnl_note": ("strategy PnL rows exclude high-risk skips by construction "
                           "(a skip has no fills); the observer bucket is the only "
                           "strategy that trades RISK_HIGH"),
    }

    return {
        "system": {
            "producer": {
                "status": core["status"], "tone": core["tone"],
                "heartbeat_age": fmt_age(core["hb_age"]),
                "last_update_utc": core["hb_ts"] or "—",
                "run_id": run_id, "out_dir": producer.get("dir"),
                "stop_reason": core["stop_reason"] or "—",
                "mode": (core["heartbeat"] or {}).get("producer_mode") or (core["summary"] or {}).get("mode") or "—",
                "discovery_mode": core.get("discovery_mode") or "WS",
                "raw_ws_note": RAW_WS_NOTE,
                "tick": (core["heartbeat"] or {}).get("tick"),
                "interrupted": bool((core["heartbeat"] or {}).get("interrupted")),
            },
            "paper": {
                "status": pcore["status"], "tone": pcore["tone"],
                "heartbeat_age": fmt_age(pcore["hb_age"]),
                "last_update_utc": pcore["hb_ts"] or "—",
                "run_id": paper_run_id, "out_dir": paper.get("dir"),
                "uptime": fmt_age((pcore["heartbeat"] or {}).get("uptime_seconds")),
                "snapshots_processed": (pcore["heartbeat"] or {}).get("snapshots_processed"),
                "last_error": str(monitor.get("last_error") or "—"),
                "last_skip": str(monitor.get("last_skip") or "—"),
                "watch_inputs": [str(p) for p in ((pcore["heartbeat"] or {}).get("watch_inputs") or [])],
            },
        },
        "discord": _discord_block(core, producer, ledger_lines, now),
        "discovery": _discovery_block(core),
        "trading": {
            "open_positions": pcore["open_total"],
            "closed_positions": pcore["closed_total"],
            "realized_pnl": fmt_money(pcore["realized"]),
            "unrealized_pnl": fmt_money(pcore["unrealized"]),
            "total_pnl": fmt_money(pcore["total_pnl"]),
            "win_rate": fmt_pct(pcore["win_rate"], signed=False),
            "best_trade": _fmt_trade(pcore["best_trade"]),
            "worst_trade": _fmt_trade(pcore["worst_trade"]),
            "realized_raw": pcore["realized"], "unrealized_raw": pcore["unrealized"],
            "skip_reasons": pcore["skips"],
            "machine_counts": machine_counts,
            "bala_machine": bala_machine,
            "equity_summary": equity_summary,
            "last_skip": str(monitor.get("last_skip") or "—"),
            "risk_protection": risk_protection,
            "strategies": strategy_rows,
            "sol_price_usd": (pcore["summary"] or {}).get("sol_price_usd"),
            "config_digest": (pcore["summary"] or {}).get("config_digest"),
        },
        "tables": {
            "candidates": candidate_rows,
            "would_pings": would_rows,
            "sent_pings": sent_rows,
            "open_positions": open_rows,
            "closed_positions": closed_rows,
            "skips": skip_table,
            "events": event_rows,
            "errors": error_rows,
        },
        "safety": {
            "redaction_status": redaction.get("redaction_status") or "—",
            "redaction_unsafe_hits": redaction.get("total_unsafe_hits"),
            "redaction_positive_control_ok": redaction.get("positive_control_ok"),
            "redaction_files_scanned": len(redaction.get("per_file_hits") or {}),
            "ledger_delta_total": (core["summary"] or {}).get("ledger_delta_total"),
            "ledger_lines": ledger_lines,
            "baseline_before": short_mint((core["summary"] or {}).get("baseline_before")),
            "baseline_after": short_mint((core["summary"] or {}).get("baseline_after")),
            "wallet_signing_or_trading": bool((core["summary"] or {}).get("wallet_signing_or_trading", False)),
            "public_or_subscriber_routing": bool((core["summary"] or {}).get("public_or_subscriber_routing", False)),
            "read_only": True,
            "dashboard_discord_sends": "NOT SUPPORTED",
            "wallet_surface": "NONE",
            "old_ceremony_ledger": "NOT TOUCHED (never opened by this dashboard)",
            "notes": [
                "Dashboard is read-only: GET-only server, no dispatch, no wallet, no signing.",
                "Secrets are never read: only allowlisted artifact files are opened; every string is redaction-filtered.",
                "Old one-send ceremony ledger is never opened for write by this dashboard.",
            ],
        },
    }
