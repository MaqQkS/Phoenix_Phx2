"""Stage 29.4 soak artifact writer.

Writes the four Stage 29.4 acceptance artifacts to a caller-
supplied output directory:

  * ``stage29_4_soak_summary.json``     -- the immutable Stage
                                            29.4 soak summary
                                            record carrying the
                                            closed-set soak
                                            outcome, rolled-up
                                            counters, locked
                                            ``filter_enforcement_
                                            status=NOT_ACTIVE_
                                            STAGE_29_PENDING``,
                                            elapsed wall-clock
                                            seconds, soak
                                            start / end UTC
                                            ISO-8601 timestamps,
                                            and the operator-
                                            supplied bounds
                                            echoed back.
  * ``stage29_4_heartbeat.jsonl``       -- append-only JSONL of
                                            one heartbeat record
                                            per soak pass (plus
                                            one final-tick
                                            heartbeat at soak
                                            stop). Each record
                                            carries a redaction-
                                            safe counter
                                            projection of soak
                                            state at the pass
                                            tick + a UTC ISO-8601
                                            timestamp + the
                                            per-pass closed-set
                                            Stage 29.3 outcome
                                            token.
  * ``stage29_4_health_snapshot.json``  -- the rolling Stage 29.4
                                            health snapshot.
                                            Atomically overwritten
                                            on every pass; the
                                            final write carries
                                            the last pass's
                                            snapshot.
  * ``stage29_4_redaction_scan.json``   -- Stage 28.7-style scan
                                            over the three Stage
                                            29.4 artifacts above
                                            plus every per-pass
                                            Stage 29.3 / Stage
                                            28.9 artifact bundle
                                            written during the
                                            soak. Closed-set
                                            verdict ``SAFE`` /
                                            ``REDACTED``.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network. No HTTP. No gRPC. No Discord.
  * Stdlib only (``json`` / ``pathlib`` / ``typing``). No
    third-party HTTP / serialization library.
  * Atomic write pattern for JSON artifacts: every file is
    written to ``<basename>.tmp`` then renamed onto its final
    basename so a half-written file is never observable.
  * Append-only write pattern for the heartbeat JSONL artifact:
    the file is opened in binary append mode; the writer never
    truncates or rewrites prior heartbeat lines.
  * The writer NEVER persists a webhook URL, Chainstack endpoint,
    x-token, Birdeye API key, Birdeye base URL, raw provider
    payload blob, wallet / signer field, raw exception string, or
    any subscriber / paid-tier identifier. Every projector emits
    only closed-set tokens + safe-shape strings + safe counters.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from PHX2.stage29.stage29_4_soak_models import (
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION,
    STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION,
    STAGE29_4_REDACTION_TOKEN,
    Stage29_4PassRecord,
    Stage29_4SoakError,
    Stage29_4SoakSummary,
    pass_record_to_dict,
    soak_summary_to_dict,
)


# ---------------------------------------------------------------------------
# Locked Stage 29.4 artifact basenames
# ---------------------------------------------------------------------------


STAGE29_4_SOAK_SUMMARY_BASENAME: str = (
    "stage29_4_soak_summary.json"
)
STAGE29_4_HEARTBEAT_BASENAME: str = (
    "stage29_4_heartbeat.jsonl"
)
STAGE29_4_HEALTH_SNAPSHOT_BASENAME: str = (
    "stage29_4_health_snapshot.json"
)
STAGE29_4_REDACTION_SCAN_BASENAME: str = (
    "stage29_4_redaction_scan.json"
)


STAGE29_4_ARTIFACT_BASENAMES: tuple[str, ...] = (
    STAGE29_4_SOAK_SUMMARY_BASENAME,
    STAGE29_4_HEARTBEAT_BASENAME,
    STAGE29_4_HEALTH_SNAPSHOT_BASENAME,
    STAGE29_4_REDACTION_SCAN_BASENAME,
)


# Stage 29.3 + Stage 28.9 companion artifact basenames that the
# Stage 29.4 redaction scan also covers when they exist in the
# soak output directory. The Stage 29.4 writer never produces
# these; the per-pass Stage 29.3 + Stage 28.9 layers do.
STAGE29_3_COMPANION_ARTIFACT_BASENAMES: tuple[str, ...] = (
    "stage29_3_tradeable_smoke_result.json",
    "stage29_3_extracted_hints.json",
    "stage29_3_birdeye_evidence.json",
    "stage29_3_redaction_scan.json",
)


STAGE28_9_COMPANION_ARTIFACT_BASENAMES: tuple[str, ...] = (
    "stage28_9_dispatch_ledger.jsonl",
    "stage28_9_heartbeat.jsonl",
    "stage28_9_health_snapshot.json",
    "stage28_9_final_run_summary.json",
)


# ---------------------------------------------------------------------------
# Forbidden substrings for the Stage 29.4 redaction scan
# ---------------------------------------------------------------------------


# The scan vocabulary is the union of Stage 28.7 + Stage 29.3
# vocabularies plus Stage 29.4-specific items. Each forbidden
# needle is concatenated literally so this module's own source
# does not trip the scan when read by a downstream string-leak
# boundary test.
FORBIDDEN_SCAN_SUBSTRINGS: tuple[str, ...] = (
    # URL host literals.
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "/webhooks/",
    "birdeye" + ".so",
    "chainstack" + ".com",
    "helius" + ".xyz",
    "helius" + ".rpc.com",
    # URL scheme literals.
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    # Auth header literals.
    "B" + "earer ",
    "A" + "uthorization:",
    "X-API-K" + "EY:",
    "X-AP" + "I-KEY:",
    # Env-name = value patterns the operator scratch runner uses.
    "BIRDEYE_API_KEY=",
    "PHX2_STAGE29_2_BIRDEYE_API_KEY=",
    "PHX2_STAGE29_2_BIRDEYE_BASE_URL=",
    "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN=",
    "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT=",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
    # API-key-shape prefixes.
    "s" + "k-live-",
    "s" + "k-test-",
    "p" + "k-live-",
    "p" + "k-test-",
    # Wallet / signer prefixes.
    "p" + "rivate_key",
    "p" + "rivatekey",
    "s" + "ecret_key",
    "s" + "ecretkey",
    "s" + "eed_phrase",
    "m" + "nemonic",
    "wallet_" + "seed",
    "wallet_" + "address",
    "signer_" + "address",
    # PHX1 paths.
    "Phoenix" + "_Bot",
    # Pump.fun bonding-curve program id literal (Stage 29 is
    # PumpSwap-only; the Pump.fun bonding-curve decoder is
    # deferred).
    "6EF8rrec" + "thR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    # Raw response body leak fragments.
    "raw_" + "response",
    "response_" + "body",
    "raw_" + "payload",
    "payload_" + "blob",
)


# ---------------------------------------------------------------------------
# Output-directory shape gate
# ---------------------------------------------------------------------------


_OUTPUT_DIR_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    "hooks" + ".slack.com",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
)


def _validate_output_dir(output_dir: object) -> None:
    if not isinstance(output_dir, Path):
        raise Stage29_4SoakError(
            "OUTPUT_DIR_NOT_A_PATH",
        )
    path_str = str(output_dir).lower()
    for needle in _OUTPUT_DIR_FORBIDDEN_SUBSTRINGS:
        if needle in path_str:
            raise Stage29_4SoakError(
                "OUTPUT_DIR_SECRET_LIKE",
            )
    if not output_dir.exists() or not output_dir.is_dir():
        raise Stage29_4SoakError(
            "OUTPUT_DIR_MISSING_OR_NOT_DIR",
        )


# ---------------------------------------------------------------------------
# Atomic JSON write helper
# ---------------------------------------------------------------------------


def _atomic_write_json(
    *,
    output_dir: Path,
    basename: str,
    payload: Mapping[str, Any],
) -> Path:
    """Atomically write a JSON file under ``output_dir``.

    The payload is serialized with sorted keys + 2-space indent so
    the file content is deterministic and reviewable. The function
    writes to ``<basename>.tmp`` then renames onto the final
    basename so a half-written file is never observable.
    """
    target = output_dir / basename
    tmp = output_dir / (basename + ".tmp")
    text = json.dumps(
        dict(payload),
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
        ensure_ascii=False,
        allow_nan=False,
    )
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    return target


# ---------------------------------------------------------------------------
# Append-only JSONL line helper
# ---------------------------------------------------------------------------


def _append_jsonl_line(
    *,
    output_dir: Path,
    basename: str,
    payload: Mapping[str, Any],
) -> Path:
    """Append one JSON object as a single newline-terminated line
    to ``output_dir / basename``.

    The line is serialized with sorted keys + compact separators
    so the line content is deterministic across runs. The file is
    opened in binary append mode; the writer NEVER truncates or
    rewrites prior lines.
    """
    target = output_dir / basename
    line = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    with open(target, "ab") as fh:
        fh.write(line.encode("utf-8"))
        fh.write(b"\n")
    return target


# ---------------------------------------------------------------------------
# Public writers
# ---------------------------------------------------------------------------


def write_soak_summary_artifact(
    *,
    output_dir: Path,
    summary: Stage29_4SoakSummary,
) -> Path:
    """Write the immutable Stage 29.4 soak summary JSON.

    Raises ``Stage29_4SoakError`` when ``summary`` is not a
    ``Stage29_4SoakSummary`` or ``output_dir`` is unsafe.
    """
    _validate_output_dir(output_dir)
    if not isinstance(summary, Stage29_4SoakSummary):
        raise Stage29_4SoakError(
            "SOAK_SUMMARY_TYPE_INVALID",
        )
    payload = soak_summary_to_dict(summary)
    return _atomic_write_json(
        output_dir=output_dir,
        basename=STAGE29_4_SOAK_SUMMARY_BASENAME,
        payload=payload,
    )


def append_heartbeat_artifact(
    *,
    output_dir: Path,
    record: Stage29_4PassRecord,
) -> Path:
    """Append one Stage 29.4 heartbeat record to the heartbeat
    JSONL artifact.

    Raises ``Stage29_4SoakError`` when ``record`` is not a
    ``Stage29_4PassRecord`` or ``output_dir`` is unsafe.
    """
    _validate_output_dir(output_dir)
    if not isinstance(record, Stage29_4PassRecord):
        raise Stage29_4SoakError(
            "HEARTBEAT_RECORD_TYPE_INVALID",
        )
    payload = pass_record_to_dict(record)
    return _append_jsonl_line(
        output_dir=output_dir,
        basename=STAGE29_4_HEARTBEAT_BASENAME,
        payload=payload,
    )


def _build_health_snapshot_payload(
    *,
    record: Stage29_4PassRecord,
    bounds_within_recommended_ranges: bool,
) -> dict:
    """Project a per-pass ``Stage29_4PassRecord`` onto the rolling
    health-snapshot payload.

    The snapshot carries the same counter axes as the heartbeat
    record but uses the Stage 29.4 health-snapshot schema version
    and adds the recommended-ranges-flag axis. Stable across passes.
    """
    base = pass_record_to_dict(record)
    base["schema_version"] = (
        STAGE29_4_HEALTH_SNAPSHOT_SCHEMA_VERSION
    )
    base["bounds_within_recommended_ranges"] = bool(
        bounds_within_recommended_ranges
    )
    return base


def write_health_snapshot_artifact(
    *,
    output_dir: Path,
    record: Stage29_4PassRecord,
    bounds_within_recommended_ranges: bool,
) -> Path:
    """Atomically (re)write the rolling Stage 29.4 health
    snapshot.

    Each call overwrites the prior snapshot; the final write
    carries the last pass's snapshot.
    """
    _validate_output_dir(output_dir)
    if not isinstance(record, Stage29_4PassRecord):
        raise Stage29_4SoakError(
            "HEALTH_SNAPSHOT_RECORD_TYPE_INVALID",
        )
    payload = _build_health_snapshot_payload(
        record=record,
        bounds_within_recommended_ranges=(
            bounds_within_recommended_ranges
        ),
    )
    return _atomic_write_json(
        output_dir=output_dir,
        basename=STAGE29_4_HEALTH_SNAPSHOT_BASENAME,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Redaction scan
# ---------------------------------------------------------------------------


def _scan_file_for_forbidden_substrings(
    path: Path,
) -> tuple[str, ...]:
    """Return the closed-set list of forbidden substring tokens
    found in ``path``. Returns an empty tuple when the file does
    not exist OR when no forbidden substring appears.

    The scan is case-insensitive (every needle is lowercased
    before the check); the haystack is lowercased once per file.
    Pure / deterministic.
    """
    if not path.is_file():
        return ()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ()
    lowered = text.lower()
    hits: list[str] = []
    for needle in FORBIDDEN_SCAN_SUBSTRINGS:
        if needle.lower() in lowered:
            hits.append(needle)
    return tuple(hits)


def _basenames_to_scan() -> tuple[str, ...]:
    """Return the closed-set tuple of artifact basenames the
    Stage 29.4 redaction scan covers when each is present in the
    soak output directory.

    Stage 29.4's own artifacts are scanned first (skipping the
    redaction scan file itself); Stage 29.3 + Stage 28.9
    companions are scanned next when they exist (the soak writes
    them via the per-pass Stage 29.3 + Stage 28.9 layers).
    """
    return (
        STAGE29_4_SOAK_SUMMARY_BASENAME,
        STAGE29_4_HEARTBEAT_BASENAME,
        STAGE29_4_HEALTH_SNAPSHOT_BASENAME,
    ) + STAGE29_3_COMPANION_ARTIFACT_BASENAMES + (
        STAGE28_9_COMPANION_ARTIFACT_BASENAMES
    )


def run_soak_redaction_scan(
    *,
    output_dir: Path,
) -> dict:
    """Run the Stage 29.4 redaction scan over every artifact in
    ``output_dir`` (the three Stage 29.4 artifacts above plus the
    Stage 29.3 + Stage 28.9 companions when they exist).

    Returns a dict with:

      * ``schema_version`` -- locked
        ``STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION``,
      * ``scanned_files`` -- list of basenames that were actually
        scanned (only files that exist),
      * ``hits_by_file`` -- mapping of basename to the closed-set
        list of forbidden substring tokens found in that file,
      * ``redaction_status`` -- locked ``REDACTION_STATUS_SAFE``
        when every file is clean, ``REDACTION_STATUS_REDACTED``
        when at least one file has a hit,
      * ``redaction_token`` -- locked
        ``STAGE29_4_REDACTION_TOKEN`` (the token a downstream
        reader should substitute when masking a hit during
        operator review).
    """
    _validate_output_dir(output_dir)
    basenames = _basenames_to_scan()
    scanned: list[str] = []
    hits: dict[str, list[str]] = {}
    for name in basenames:
        path = output_dir / name
        if not path.is_file():
            continue
        scanned.append(name)
        found = _scan_file_for_forbidden_substrings(path)
        if found:
            hits[name] = list(found)
    status = (
        REDACTION_STATUS_SAFE
        if not hits
        else REDACTION_STATUS_REDACTED
    )
    return {
        "schema_version": (
            STAGE29_4_REDACTION_SCAN_SCHEMA_VERSION
        ),
        "scanned_files": scanned,
        "hits_by_file": hits,
        "redaction_status": status,
        "redaction_token": STAGE29_4_REDACTION_TOKEN,
    }


def write_soak_redaction_scan_artifact(
    *,
    output_dir: Path,
) -> tuple[Path, dict]:
    """Run the redaction scan and write its result to
    ``stage29_4_redaction_scan.json``.

    Returns ``(written_path, scan_dict)`` so the orchestrator can
    surface the closed-set ``redaction_status`` token onto the
    soak summary without re-reading the file.
    """
    scan = run_soak_redaction_scan(output_dir=output_dir)
    written = _atomic_write_json(
        output_dir=output_dir,
        basename=STAGE29_4_REDACTION_SCAN_BASENAME,
        payload=scan,
    )
    return written, scan


# ---------------------------------------------------------------------------
# Bundle writer (summary + redaction scan)
# ---------------------------------------------------------------------------


def write_soak_summary_bundle(
    *,
    output_dir: Path,
    summary: Stage29_4SoakSummary,
) -> dict:
    """Write the Stage 29.4 soak summary then run the redaction
    scan and write its result.

    Returns the dict scan summary so the orchestrator can surface
    the closed-set ``redaction_status`` token. The heartbeat and
    health snapshot are written incrementally during the soak
    loop by the orchestrator; this bundle writer covers the two
    end-of-soak artifacts only.

    Raises ``Stage29_4SoakError`` when ``output_dir`` is unsafe.
    """
    _validate_output_dir(output_dir)
    write_soak_summary_artifact(
        output_dir=output_dir, summary=summary,
    )
    _, scan = write_soak_redaction_scan_artifact(
        output_dir=output_dir,
    )
    return scan


# ---------------------------------------------------------------------------
# Read-back helpers (used by tests)
# ---------------------------------------------------------------------------


def read_heartbeat_artifact_lines(
    *,
    output_dir: Path,
) -> tuple[dict, ...]:
    """Read every Stage 29.4 heartbeat JSONL line from the
    heartbeat artifact under ``output_dir``.

    Returns an empty tuple when the file does not exist. Used by
    tests to verify the heartbeat record sequence. Pure / read-
    only; never mutates the file.
    """
    path = output_dir / STAGE29_4_HEARTBEAT_BASENAME
    if not path.is_file():
        return ()
    lines: list[dict] = []
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        lines.append(json.loads(stripped))
    return tuple(lines)


__all__ = (
    # Locked basenames.
    "STAGE29_4_SOAK_SUMMARY_BASENAME",
    "STAGE29_4_HEARTBEAT_BASENAME",
    "STAGE29_4_HEALTH_SNAPSHOT_BASENAME",
    "STAGE29_4_REDACTION_SCAN_BASENAME",
    "STAGE29_4_ARTIFACT_BASENAMES",
    "STAGE29_3_COMPANION_ARTIFACT_BASENAMES",
    "STAGE28_9_COMPANION_ARTIFACT_BASENAMES",
    # Forbidden substring set.
    "FORBIDDEN_SCAN_SUBSTRINGS",
    # Atomic writers.
    "write_soak_summary_artifact",
    "append_heartbeat_artifact",
    "write_health_snapshot_artifact",
    "run_soak_redaction_scan",
    "write_soak_redaction_scan_artifact",
    "write_soak_summary_bundle",
    # Read-back helpers.
    "read_heartbeat_artifact_lines",
)
