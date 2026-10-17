"""Build #26 Phase 1A — evidence-preserving capture artifact writer + redaction scanner.

OUT-OF-REPO operator glue. OFFLINE. Stdlib only (json / re / pathlib) + the committed
Stage 29.5.7 projection (read-only, via sys.path). Imports NO socket, NO process
environment, NO network, NO Discord/webhook/send/guard/durable-ledger.

This is the Build #25 sanitized writer EXTENDED to additionally persist the migration
EVIDENCE the Build #25 writer discarded (it kept only ``token_mint``). The capture already
produces the proven evidence in memory (``run.evidence_records`` + ``run.sanitized_summaries``);
this writer serializes, per accepted ``*pump`` record, the redaction-safe full-record +
sanitized-summary fields needed to reconstruct a committed
``Stage29_5MigrationEvidenceRecord`` for the committed Build 26.0 Stage 30.14 replay path.

It FABRICATES nothing: an evidence line is written ONLY when the committed projection
``project_migration_evidence_to_sanitized_summary(record)`` returns a COMPLETE summary (the
same gate the auto-seeder uses); any incomplete / non-PRESENT record is skipped (counted,
never invented). Every persisted artifact is redaction-scanned; an unsafe evidence line is
WITHHELD (never written) and any unsafe content reaching disk VOIDs the run.

Build 26.1A: raw getTransaction quarantine is DISABLED (off by default; requesting it
raises). No committed repo file is edited.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_REPO_ROOT = r"C:\Users\BalaC\Downloads\Phoenix_PHX2"
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from PHX2.stage29.stage29_5_7_live_migration_evidence_producer import (  # committed, read-only  # noqa: E402
    project_migration_evidence_to_sanitized_summary,
)


BUILD26_EVIDENCE_BASENAME = "build26_capture_evidence.jsonl"
BUILD26_EVIDENCE_MANIFEST_BASENAME = "build26_capture_evidence_manifest.json"
BUILD26_EVIDENCE_SCHEMA_VERSION = "build26_evidence_v0"
BUILD26_EVIDENCE_MANIFEST_SCHEMA_VERSION = "build26_evidence_manifest_v0"
_SCAN_REPORT_NAME = "build26_capture_redaction_scan.txt"

# The exact evidence fields persisted per accepted *pump record (the Build 26.1 contract).
BUILD26_REQUIRED_EVIDENCE_FIELDS: Tuple[str, ...] = (
    "schema_version",
    "token_mint",
    "migration_status",
    "migration_source",
    "pool_account",
    "pool_program_id",
    "quote_mint",
    "migration_event_time_utc",
    "migration_slot",
    "migration_signature",
    "source_ref",
    "observed_at_utc",
    "measurement_status",
    "redaction_status",
    "warnings",
)

# ---------------------------------------------------------------------------
# Redaction scanner (mirrors the Build #25 scanner BY VALUE; same allowlist + needles).
# ---------------------------------------------------------------------------

# Allowlisted provenance ref: helius:sig:<base58>:slot:<n> (public chain identifiers only).
_SAFE_SOURCE_REF = re.compile(r"helius:sig:[1-9A-HJ-NP-Za-km-z]+:slot:\d+")

# A URI scheme is only a URI scheme when the authority separator follows it.
# ``ws`` / ``wss`` / ``http`` / ``https`` are spelled ENTIRELY with valid Base58
# characters, so a raw ``<scheme>:`` substring needle cannot tell real endpoint
# material from a public transaction signature that merely ends in those letters
# ahead of the structural ATH event-key delimiter (``f"{transaction_signature}:
# {event_index}"``, ath_state.py) -- e.g. ``<sig ending in wss>:0`` self-flagged
# and stopped two production runs with SECRET_SCAN_FAILURE.  Requiring ``://``
# supplies the context the bare substring lacked: Base58 encodes no ``/`` and no
# ``:``, so a signature can never satisfy it.  The lookbehind keeps the scheme
# anchored at a token boundary; IGNORECASE covers WSS:// / WS:// / HTTPS:// /
# HTTP://.  The generic ``://`` needle below still fires on ANY scheme (known or
# not), so these categories never carry detection alone and the scan stays fail
# closed.  Categories are reported as stable tokens, never as matched text.
_WEBSOCKET_URI = re.compile(r"(?<![A-Za-z0-9])wss?://", re.IGNORECASE)
_HTTP_URI = re.compile(r"(?<![A-Za-z0-9])https?://", re.IGNORECASE)

# ``authorization`` is only dangerous as an actual header/field NAME carrying a
# nonempty credential value (``Authorization: Bearer <v>``, ``authorization=<v>``,
# ``"Authorization": "Basic <v>"``).  The former bare substring needle also
# matched harmless runtime metric identifiers that merely CONTAIN the word —
# ``baseline_observed_pre_authorization`` in the migration-admission telemetry
# aborted the first live acceptance window (2026-07-18) from inside
# producer_heartbeat.json even though no credential was present.  The rule now
# requires a standalone name token (no identifier character on either side:
# ``_pre_authorization`` and ``authorization_state`` cannot match, while
# hyphen-joined real headers such as ``Proxy-Authorization`` still can), the
# ``:``/``=`` header-value syntax with optional JSON quoting, and at least one
# non-whitespace, non-quote value character — so a bare name mention or an
# empty value never fires, but any credential-bearing shape still fails the
# scan closed.  Categories are reported as stable tokens, never matched text,
# so no credential value is ever persisted or logged by the scanner itself.
_AUTHORIZATION_HEADER = re.compile(
    r"(?<![A-Za-z0-9_])authorization[\"']?\s*[:=]\s*[\"']?[^\s\"']",
    re.IGNORECASE,
)

# A Telegram bot token is ``<bot_id>:<35-char secret>`` -- an 6-to-10 digit bot
# id, a colon, then exactly 35 URL-safe-base64 characters -- and is the
# credential the supervisor's Telegram production pipeline carries.  It carries
# no ``://``, no ``discord.com`` and no ``api-key``, so none of the needles above
# fired on a bare token (2026-07-20 residual re-audit, L-4).  The pattern is
# anchored so it cannot masquerade-match structural PHX2 shapes: the trailing
# ``(?![A-Za-z0-9_-])`` forbids a 36th token character, so a ``<64-hex>:<...>``
# sha/baseline token (``<hex>:<size>:<lines>``) and a base58 ``<sig>:<index>``
# event key -- whose post-colon field is never a 35-char URL-safe run -- can
# never satisfy it, while the optional ``bot`` prefix matches the ``api`` path
# form.  The category is reported as a stable token, never the matched value, so
# no credential is ever echoed by the scanner.
_TELEGRAM_BOT_TOKEN = re.compile(
    r"(?:bot)?\d{6,10}:[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])"
)
_DANGER_PATTERNS = (
    ("WEBSOCKET_URL", _WEBSOCKET_URI),
    ("HTTP_URL", _HTTP_URI),
    ("AUTHORIZATION_HEADER", _AUTHORIZATION_HEADER),
    ("TELEGRAM_BOT_TOKEN", _TELEGRAM_BOT_TOKEN),
)

_DANGER_NEEDLES = (
    "://", "helius-rpc", "helius.dev", "atlas-mainnet",
    "api-key", "api_key", "apikey", "x-api-key", "x-token", "bearer",
    "/webhooks/", "discord.com", "discordapp", "chainstack", "birdeye", "dexscreener",
    "api.telegram.org", "raw_body", "response_body",
)


def scan_text(text: str) -> List[str]:
    """Return stable danger categories/needles after masking safe source refs."""
    masked = _SAFE_SOURCE_REF.sub("<SAFE_SOURCE_REF>", text)
    low = masked.lower()
    hits = [category for category, pattern in _DANGER_PATTERNS if pattern.search(masked)]
    hits.extend(n for n in _DANGER_NEEDLES if n.lower() in low)
    return hits


def scan_dir(dir_path) -> Dict[str, List[str]]:
    """Scan every file in ``dir_path`` (except the scan report itself) for danger needles."""
    out: Dict[str, List[str]] = {}
    for p in sorted(Path(dir_path).rglob("*")):
        if p.is_file() and p.name != _SCAN_REPORT_NAME:
            out[str(p.relative_to(dir_path))] = scan_text(
                p.read_text(encoding="utf-8")
            )
    return out


# ---------------------------------------------------------------------------
# Safe-six decision-ledger writer (the Build #25 artifacts, kept for continuity).
# ---------------------------------------------------------------------------


def _write_safe_six(out: Path, *, run, seed, stats, caps) -> None:
    s = seed.summary
    (out / "build26_capture_seed_summary.json").write_text(
        json.dumps(
            {
                "records_seen": s.records_seen, "accepted": s.accepted, "rejected": s.rejected,
                "duplicate": s.duplicate, "error": s.error,
                "redaction_status": seed.redaction_status, "created_at_utc": s.created_at_utc,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    seeded = [getattr(sm, "token_mint", "") for sm in seed.seeded_summaries]
    (out / "build26_capture_seeded_mints.txt").write_text(
        "\n".join(seeded) + ("\n" if seeded else ""), encoding="utf-8"
    )
    with (out / "build26_capture_outcomes.jsonl").open("w", encoding="utf-8") as fh:
        for oc in seed.outcomes:
            fh.write(json.dumps({
                "token_mint": oc.token_mint, "seed_decision": oc.seed_decision,
                "seed_reason": oc.seed_reason, "created_at_utc": oc.created_at_utc,
            }) + "\n")
    per_reason: Dict[str, int] = {}
    for oc in getattr(run, "outcomes", ()):  # producer normalization outcomes
        reason = getattr(oc, "reject_reason", "NONE")
        if reason != "NONE":
            per_reason[reason] = per_reason.get(reason, 0) + 1
    (out / "build26_capture_normalizer_tally.json").write_text(
        json.dumps({
            "envelopes_seen": run.summary.envelopes_seen,
            "migrations_proven": run.summary.migrations_proven,
            "rejected": run.summary.rejected, "per_reject_reason": per_reason,
        }, indent=2),
        encoding="utf-8",
    )
    (out / "build26_capture_meta.json").write_text(
        json.dumps({
            "caps": {
                "max_runtime_seconds": caps.max_runtime_seconds,
                "max_logs_notifications": caps.max_logs_notifications,
                "max_gettransaction_fetches": caps.max_gettransaction_fetches,
                "max_seed": caps.max_seed,
                "max_accepted_evidence": getattr(caps, "max_accepted_evidence", None),
                "max_artifact_bytes": getattr(caps, "max_artifact_bytes", None),
            },
            "stats": dict(stats),
        }, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Evidence line builder (NO fabrication: only a projected-COMPLETE record persists).
# ---------------------------------------------------------------------------


def _evidence_line(record, summary) -> Dict[str, Any]:
    warnings = getattr(summary, "warnings", None)
    return {
        "schema_version": BUILD26_EVIDENCE_SCHEMA_VERSION,
        "token_mint": summary.token_mint,
        "migration_status": "PRESENT",
        "migration_source": getattr(record, "migration_source", ""),
        "pool_account": getattr(record, "pool_account", None),
        "pool_program_id": getattr(record, "pool_program_id", None),
        "quote_mint": getattr(record, "quote_mint", None),
        "migration_event_time_utc": summary.migration_event_time_utc,
        "migration_slot": getattr(record, "migration_slot", None),
        "migration_signature": getattr(record, "migration_signature", None),
        "source_ref": summary.source_ref,
        "observed_at_utc": getattr(record, "observed_at_utc", None),
        "measurement_status": summary.measurement_status,
        "redaction_status": summary.redaction_status,
        "warnings": list(warnings) if warnings is not None else [],
    }


def _build_evidence_lines(run, caps) -> Tuple[List[str], Dict[str, int]]:
    """Project each evidence record, withholding unsafe / incomplete / duplicate / over-cap
    lines. Returns (json_lines, counts). FAIL CLOSED: never persists an unprojectable record
    and never persists a line that trips a danger needle."""
    counts = {"accepted": 0, "incomplete_skipped": 0, "duplicate_skipped": 0,
              "redaction_withheld": 0, "artifact_bytes": 0, "artifact_bytes_capped": 0}
    seen_mints = set()
    lines: List[str] = []
    total_bytes = 0
    for record in getattr(run, "evidence_records", ()):
        if counts["accepted"] >= caps.max_accepted_evidence:
            counts["artifact_bytes_capped"] = 1
            break
        summary = project_migration_evidence_to_sanitized_summary(record)
        if summary is None or not getattr(summary, "token_mint", None):
            counts["incomplete_skipped"] += 1  # not a proven COMPLETE record -> never fabricate
            continue
        mint = summary.token_mint
        if mint in seen_mints:
            counts["duplicate_skipped"] += 1  # first-wins
            continue
        line_json = json.dumps(_evidence_line(record, summary), sort_keys=True)
        if scan_text(line_json):
            counts["redaction_withheld"] += 1  # unsafe -> withhold, never write
            continue
        add_bytes = len((line_json + "\n").encode("utf-8"))
        if total_bytes + add_bytes > caps.max_artifact_bytes:
            counts["artifact_bytes_capped"] = 1
            break
        seen_mints.add(mint)
        lines.append(line_json)
        total_bytes += add_bytes
        counts["accepted"] += 1
    counts["artifact_bytes"] = total_bytes
    return lines, counts


# ---------------------------------------------------------------------------
# Public evidence-preserving writer
# ---------------------------------------------------------------------------


def write_capture_artifacts_v2(
    out_dir,
    *,
    run,
    seed,
    stats,
    caps,
    created_at_utc: str,
    persist_evidence: bool = True,
    persist_raw_quarantine: bool = False,
) -> Dict[str, Any]:
    """Write the safe-six decision ledger + (when ``persist_evidence``) the evidence JSONL +
    manifest, then redaction-scan EVERY artifact. Returns a result dict. Build 26.1A: raw
    quarantine is unsupported -> requesting it raises (off by default)."""
    if persist_raw_quarantine:
        raise NotImplementedError(
            "Build 26.1A: raw getTransaction quarantine is disabled (off by default)."
        )
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    _write_safe_six(out, run=run, seed=seed, stats=stats, caps=caps)

    ev_counts = {"accepted": 0, "incomplete_skipped": 0, "duplicate_skipped": 0,
                 "redaction_withheld": 0, "artifact_bytes": 0, "artifact_bytes_capped": 0}
    if persist_evidence:
        lines, ev_counts = _build_evidence_lines(run, caps)
        (out / BUILD26_EVIDENCE_BASENAME).write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
        (out / BUILD26_EVIDENCE_MANIFEST_BASENAME).write_text(
            json.dumps({
                "schema_version": BUILD26_EVIDENCE_MANIFEST_SCHEMA_VERSION,
                "evidence_basename": BUILD26_EVIDENCE_BASENAME,
                "accepted_evidence_records": ev_counts["accepted"],
                "incomplete_skipped": ev_counts["incomplete_skipped"],
                "duplicate_skipped": ev_counts["duplicate_skipped"],
                "redaction_withheld": ev_counts["redaction_withheld"],
                "artifact_bytes": ev_counts["artifact_bytes"],
                "artifact_bytes_capped": bool(ev_counts["artifact_bytes_capped"]),
                "raw_quarantine_enabled": False,
                "required_fields": list(BUILD26_REQUIRED_EVIDENCE_FIELDS),
                "created_at_utc": created_at_utc,
            }, indent=2),
            encoding="utf-8",
        )

    # Redaction scan over EVERY written artifact + positive control.
    res = scan_dir(out)
    total = sum(len(v) for v in res.values())
    planted = ("wss" + "://atlas-mainnet.helius-rpc.com/?api-key=PLANTED bearer z"
               + " Authoriz" + "ation: PLANTED-credential"
               + " bot" + "1234567:" + "PLANTED" + ("d" * 28))
    pc = scan_text(planted)
    lines_out = ["# Build #26 Phase 1A — Capture Redaction Scan", ""]
    for name, hits in res.items():
        lines_out.append(f"- {name}: {'CLEAN' if not hits else 'HITS=' + ','.join(hits)}")
    lines_out += [
        "",
        f"POSITIVE CONTROL (planted secret) flagged: {','.join(pc)}",
        f"TOTAL UNSAFE HITS: {total}",
        "NOTE: helius:sig:<sig>:slot:<n> provenance refs are allowlisted SAFE per design.",
    ]
    (out / _SCAN_REPORT_NAME).write_text("\n".join(lines_out) + "\n", encoding="utf-8")

    return {
        "total_unsafe_hits": total,
        "positive_control_flagged": pc,
        "redaction_status": "REDACTED" if total == 0 else "REDACTION_VIOLATION",
        "evidence": ev_counts,
        "raw_quarantine_enabled": False,
    }


__all__ = (
    "BUILD26_EVIDENCE_BASENAME",
    "BUILD26_EVIDENCE_MANIFEST_BASENAME",
    "BUILD26_EVIDENCE_SCHEMA_VERSION",
    "BUILD26_REQUIRED_EVIDENCE_FIELDS",
    "scan_text",
    "scan_dir",
    "write_capture_artifacts_v2",
)
