"""Stage 29.3 artifact writer.

Writes the four Stage 29.3 acceptance JSON artifacts to a
caller-supplied output directory:

  * ``stage29_3_tradeable_smoke_result.json``  -- the immutable
                                                  Stage 29.3
                                                  smoke result
                                                  record.
  * ``stage29_3_extracted_hints.json``         -- the safe-shape
                                                  projection of
                                                  the Stage 29.1
                                                  hint extraction
                                                  result for the
                                                  event that drove
                                                  the dispatch
                                                  (or ``null`` slot
                                                  when no event
                                                  was received).
  * ``stage29_3_birdeye_evidence.json``        -- the
                                                  Stage 29.2
                                                  Birdeye price /
                                                  ATH evidence
                                                  record for the
                                                  dispatched mint
                                                  (or ``null``
                                                  slots when no
                                                  event was
                                                  received).
  * ``stage29_3_redaction_scan.json``          -- Stage 28.7-style
                                                  scan over the
                                                  prior three
                                                  files for the
                                                  forbidden-
                                                  substring set,
                                                  with closed-set
                                                  ``SAFE`` /
                                                  ``REDACTED``
                                                  verdict.

The Stage 28.9 wrapper writes its own four artifacts
(dispatch ledger / heartbeat / health snapshot / final summary)
into the same directory. The Stage 29.3 artifact writer does
NOT touch those; the redaction scan reads them when present so
the operator gets one combined scan over the full bundle.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched.
  * No network. No HTTP. No gRPC.
  * Stdlib only (``json`` / ``pathlib``). No third-party HTTP /
    serialization library.
  * Atomic write pattern: every file is written to a
    ``<basename>.tmp`` then renamed onto its final basename so a
    half-written file is never observable.
  * The writer NEVER persists a webhook URL, x-token, Birdeye API
    key, Birdeye base URL, raw provider payload blob, or wallet /
    signer field. Every projector emits only closed-set tokens +
    safe-shape strings + safe counters.
  * No raw secret value, no PHX1 / ``Phoenix_Bot`` import.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional

from PHX2.stage29.stage29_2_birdeye_models import (
    Stage29_2BirdeyeAthSnapshot,
    Stage29_2BirdeyeEvidenceRecord,
    Stage29_2BirdeyePriceSnapshot,
)
from PHX2.stage29.pumpswap_hint_models import (
    Stage29_1PumpSwapHintExtractionResult,
)
from PHX2.stage29.stage29_3_smoke_models import (
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    STAGE29_3_REDACTION_TOKEN,
    Stage29_3TradeableSmokeError,
    Stage29_3TradeableSmokeResult,
    smoke_result_to_dict,
)


# ---------------------------------------------------------------------------
# Locked Stage 29.3 artifact basenames
# ---------------------------------------------------------------------------


STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME: str = (
    "stage29_3_tradeable_smoke_result.json"
)
STAGE29_3_EXTRACTED_HINTS_BASENAME: str = (
    "stage29_3_extracted_hints.json"
)
STAGE29_3_BIRDEYE_EVIDENCE_BASENAME: str = (
    "stage29_3_birdeye_evidence.json"
)
STAGE29_3_REDACTION_SCAN_BASENAME: str = (
    "stage29_3_redaction_scan.json"
)


STAGE29_3_ARTIFACT_BASENAMES: tuple[str, ...] = (
    STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME,
    STAGE29_3_EXTRACTED_HINTS_BASENAME,
    STAGE29_3_BIRDEYE_EVIDENCE_BASENAME,
    STAGE29_3_REDACTION_SCAN_BASENAME,
)


# Stage 28.9 artifacts the wrapper writes into the same directory.
# Listed here so the Stage 29.3 redaction scan can pick them up when
# they exist; the writer never produces them itself.
STAGE28_9_COMPANION_ARTIFACT_BASENAMES: tuple[str, ...] = (
    "stage28_9_dispatch_ledger.jsonl",
    "stage28_9_heartbeat.jsonl",
    "stage28_9_health_snapshot.json",
    "stage28_9_final_run_summary.json",
)


# ---------------------------------------------------------------------------
# Forbidden-substring set for the redaction scan
# ---------------------------------------------------------------------------


# Substrings that indicate URL / secret material. Each forbidden
# needle is concatenated literally so this module's source itself
# does not trip the scan when read by tests.
FORBIDDEN_SCAN_SUBSTRINGS: tuple[str, ...] = (
    # URL host literals.
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "/webhooks/",
    "birdeye" + ".so",
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
    # PHX1 paths.
    "Phoenix" + "_Bot",
    # Pump.fun bonding-curve program id literal (must not appear
    # in Stage 29.3 artifacts; Stage 29.3 is PumpSwap-only).
    "6EF8rrec" + "thR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
)


# ---------------------------------------------------------------------------
# Projection helpers
# ---------------------------------------------------------------------------


def project_extraction_result_to_safe_dict(
    extraction: Optional[Stage29_1PumpSwapHintExtractionResult],
) -> dict[str, Any]:
    """Project a Stage 29.1 hint extraction result onto a safe
    serialization dict.

    Returns a dict with every field present and ``None`` slots
    explicit. When ``extraction`` is ``None`` (the ceremony
    reached no event), every hint slot is ``None`` and ``outcome``
    is the explicit string ``"NO_EXTRACTION"``.
    """
    if extraction is None:
        return {
            "outcome": "NO_EXTRACTION",
            "base_mint": None,
            "pool_account": None,
            "quote_mint": None,
            "pool_program_id": None,
            "provider_pair_type_hint": None,
            "provider_quote_asset_hint": None,
            "bonding_curve_version_hint": None,
            "no_evidence_reason": "NO_EXTRACTION",
            "pool_account_evidence_source": "NONE",
            "quote_mint_evidence_source": "NONE",
            "spl_token_balance_count": 0,
            "pool_owner_candidate_count": 0,
        }
    if not isinstance(
        extraction, Stage29_1PumpSwapHintExtractionResult,
    ):
        raise Stage29_3TradeableSmokeError(
            "EXTRACTION_RESULT_TYPE_INVALID",
        )
    return {
        "outcome": extraction.outcome,
        "base_mint": extraction.base_mint,
        "pool_account": extraction.pool_account,
        "quote_mint": extraction.quote_mint,
        "pool_program_id": extraction.pool_program_id,
        "provider_pair_type_hint": (
            extraction.provider_pair_type_hint
        ),
        "provider_quote_asset_hint": (
            extraction.provider_quote_asset_hint
        ),
        "bonding_curve_version_hint": (
            extraction.bonding_curve_version_hint
        ),
        "no_evidence_reason": extraction.no_evidence_reason,
        "pool_account_evidence_source": (
            extraction.pool_account_evidence_source
        ),
        "quote_mint_evidence_source": (
            extraction.quote_mint_evidence_source
        ),
        "spl_token_balance_count": (
            extraction.spl_token_balance_count
        ),
        "pool_owner_candidate_count": (
            extraction.pool_owner_candidate_count
        ),
    }


def project_birdeye_evidence_to_safe_dict(
    *,
    base_mint: Optional[str],
    price_snapshot: Optional[Stage29_2BirdeyePriceSnapshot],
    ath_snapshot: Optional[Stage29_2BirdeyeAthSnapshot],
    evidence: Optional[Stage29_2BirdeyeEvidenceRecord] = None,
) -> dict[str, Any]:
    """Project Stage 29.2 Birdeye evidence (price + ATH +
    optional combined evidence record) onto a safe serialization
    dict.

    Every field is present; ``None`` slots are explicit. The
    safe-shape ``base_mint`` is echoed when supplied so the
    artifact preserves provenance without needing to be cross-
    referenced against the smoke-result file.
    """
    price_block: dict[str, Any]
    if price_snapshot is None:
        price_block = {
            "price_value": None,
            "price_unit": None,
            "source_label": None,
            "fetched_at_utc": None,
            "upstream_update_unix_time": None,
            "birdeye_price_status": "MISSING",
            "birdeye_freshness_status": "UNKNOWN",
        }
    elif not isinstance(
        price_snapshot, Stage29_2BirdeyePriceSnapshot,
    ):
        raise Stage29_3TradeableSmokeError(
            "PRICE_SNAPSHOT_TYPE_INVALID",
        )
    else:
        price_block = {
            "price_value": price_snapshot.price_value,
            "price_unit": price_snapshot.price_unit,
            "source_label": price_snapshot.source_label,
            "fetched_at_utc": price_snapshot.fetched_at_utc,
            "upstream_update_unix_time": (
                price_snapshot.upstream_update_unix_time
            ),
            "birdeye_price_status": (
                price_snapshot.birdeye_price_status
            ),
            "birdeye_freshness_status": (
                price_snapshot.birdeye_freshness_status
            ),
        }

    ath_block: dict[str, Any]
    if ath_snapshot is None:
        ath_block = {
            "ath_value": None,
            "ath_unit": None,
            "source_label": None,
            "ath_observed_at_utc": None,
            "window_starts_post_migration": None,
            "lookback_hours": 0,
            "items_count": 0,
            "birdeye_ath_status": "MISSING",
            "birdeye_freshness_status": "UNKNOWN",
        }
    elif not isinstance(
        ath_snapshot, Stage29_2BirdeyeAthSnapshot,
    ):
        raise Stage29_3TradeableSmokeError(
            "ATH_SNAPSHOT_TYPE_INVALID",
        )
    else:
        ath_block = {
            "ath_value": ath_snapshot.ath_value,
            "ath_unit": ath_snapshot.ath_unit,
            "source_label": ath_snapshot.source_label,
            "ath_observed_at_utc": (
                ath_snapshot.ath_observed_at_utc
            ),
            "window_starts_post_migration": (
                ath_snapshot.window_starts_post_migration
            ),
            "lookback_hours": ath_snapshot.lookback_hours,
            "items_count": ath_snapshot.items_count,
            "birdeye_ath_status": (
                ath_snapshot.birdeye_ath_status
            ),
            "birdeye_freshness_status": (
                ath_snapshot.birdeye_freshness_status
            ),
        }

    drawdown_ratio: Optional[str] = None
    if evidence is not None and isinstance(
        evidence, Stage29_2BirdeyeEvidenceRecord,
    ):
        drawdown_ratio = evidence.drawdown_ratio

    return {
        "base_mint": base_mint,
        "price": price_block,
        "ath": ath_block,
        "drawdown_ratio": drawdown_ratio,
    }


# ---------------------------------------------------------------------------
# Atomic write helpers
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
    writes to ``<basename>.tmp`` and renames onto the final
    basename so a half-written file is never observable.
    """
    target = output_dir / basename
    tmp = output_dir / (basename + ".tmp")
    text = json.dumps(
        dict(payload),
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    )
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    return target


# ---------------------------------------------------------------------------
# Public writers
# ---------------------------------------------------------------------------


def write_smoke_result_artifact(
    *,
    output_dir: Path,
    smoke_result: Stage29_3TradeableSmokeResult,
) -> Path:
    """Write the immutable Stage 29.3 smoke result JSON.

    Raises ``Stage29_3TradeableSmokeError`` when ``smoke_result``
    is not a ``Stage29_3TradeableSmokeResult``.
    """
    if not isinstance(
        smoke_result, Stage29_3TradeableSmokeResult,
    ):
        raise Stage29_3TradeableSmokeError(
            "SMOKE_RESULT_TYPE_INVALID",
        )
    payload = smoke_result_to_dict(smoke_result)
    return _atomic_write_json(
        output_dir=output_dir,
        basename=STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME,
        payload=payload,
    )


def write_extracted_hints_artifact(
    *,
    output_dir: Path,
    extraction: Optional[Stage29_1PumpSwapHintExtractionResult],
) -> Path:
    """Write the safe-shape projection of the Stage 29.1
    extraction result.

    When ``extraction`` is ``None`` (no event reached the
    ceremony), the file carries the explicit ``"NO_EXTRACTION"``
    outcome.
    """
    payload = project_extraction_result_to_safe_dict(extraction)
    return _atomic_write_json(
        output_dir=output_dir,
        basename=STAGE29_3_EXTRACTED_HINTS_BASENAME,
        payload=payload,
    )


def write_birdeye_evidence_artifact(
    *,
    output_dir: Path,
    base_mint: Optional[str],
    price_snapshot: Optional[Stage29_2BirdeyePriceSnapshot],
    ath_snapshot: Optional[Stage29_2BirdeyeAthSnapshot],
    evidence: Optional[Stage29_2BirdeyeEvidenceRecord] = None,
) -> Path:
    """Write the Stage 29.2 Birdeye evidence artifact.

    The artifact carries the price snapshot, the ATH snapshot,
    and (when supplied) the combined evidence record's drawdown
    ratio. All slots are explicit ``None`` when the corresponding
    Birdeye call was not made.
    """
    payload = project_birdeye_evidence_to_safe_dict(
        base_mint=base_mint,
        price_snapshot=price_snapshot,
        ath_snapshot=ath_snapshot,
        evidence=evidence,
    )
    return _atomic_write_json(
        output_dir=output_dir,
        basename=STAGE29_3_BIRDEYE_EVIDENCE_BASENAME,
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


def run_redaction_scan(
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Run the Stage 29.3 redaction scan over every artifact in
    ``output_dir`` (the three Stage 29.3 artifacts written above
    + the four Stage 28.9 companion artifacts when they exist).

    Returns a dict with:

      * ``scanned_files``  -- list of basenames that were
                              actually scanned (only files that
                              exist),
      * ``hits_by_file``   -- mapping of basename to the closed-
                              set list of forbidden substring
                              tokens found in that file,
      * ``redaction_status`` -- locked
                                ``REDACTION_STATUS_SAFE`` when
                                every file is clean,
                                ``REDACTION_STATUS_REDACTED``
                                when at least one file has a
                                hit,
      * ``redaction_token`` -- locked
                                ``STAGE29_3_REDACTION_TOKEN``
                                (the token a downstream reader
                                should substitute when masking
                                a hit during operator review).
    """
    basenames_to_scan = (
        STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME,
        STAGE29_3_EXTRACTED_HINTS_BASENAME,
        STAGE29_3_BIRDEYE_EVIDENCE_BASENAME,
    ) + STAGE28_9_COMPANION_ARTIFACT_BASENAMES
    scanned: list[str] = []
    hits: dict[str, list[str]] = {}
    for name in basenames_to_scan:
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
        "scanned_files": scanned,
        "hits_by_file": hits,
        "redaction_status": status,
        "redaction_token": STAGE29_3_REDACTION_TOKEN,
    }


def write_redaction_scan_artifact(
    *,
    output_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    """Run the redaction scan and write the result to
    ``stage29_3_redaction_scan.json``.

    Returns ``(written_path, scan_dict)`` so the orchestrator can
    surface the closed-set ``redaction_status`` token onto the
    smoke-result record without re-reading the file.
    """
    scan = run_redaction_scan(output_dir=output_dir)
    written = _atomic_write_json(
        output_dir=output_dir,
        basename=STAGE29_3_REDACTION_SCAN_BASENAME,
        payload=scan,
    )
    return written, scan


# ---------------------------------------------------------------------------
# Bundle writer
# ---------------------------------------------------------------------------


def write_stage29_3_artifact_bundle(
    *,
    output_dir: Path,
    smoke_result: Stage29_3TradeableSmokeResult,
    extraction: Optional[Stage29_1PumpSwapHintExtractionResult],
    base_mint: Optional[str],
    price_snapshot: Optional[Stage29_2BirdeyePriceSnapshot],
    ath_snapshot: Optional[Stage29_2BirdeyeAthSnapshot],
    evidence: Optional[Stage29_2BirdeyeEvidenceRecord] = None,
) -> dict[str, Any]:
    """Write the three Stage 29.3 acceptance artifacts in order,
    then run the redaction scan and write its result.

    Returns the dict scan summary so the orchestrator can surface
    the closed-set ``redaction_status`` token.

    Raises ``Stage29_3TradeableSmokeError`` when ``output_dir``
    does not exist OR is not a directory. The Stage 29.3 caller
    is responsible for creating the directory upstream (typically
    operator scratch space outside the PHX2 working tree).
    """
    if not isinstance(output_dir, Path):
        raise Stage29_3TradeableSmokeError(
            "OUTPUT_DIR_NOT_A_PATH",
        )
    if not output_dir.is_dir():
        raise Stage29_3TradeableSmokeError(
            "OUTPUT_DIR_MISSING_OR_NOT_DIR",
        )
    write_smoke_result_artifact(
        output_dir=output_dir, smoke_result=smoke_result,
    )
    write_extracted_hints_artifact(
        output_dir=output_dir, extraction=extraction,
    )
    write_birdeye_evidence_artifact(
        output_dir=output_dir,
        base_mint=base_mint,
        price_snapshot=price_snapshot,
        ath_snapshot=ath_snapshot,
        evidence=evidence,
    )
    _, scan = write_redaction_scan_artifact(
        output_dir=output_dir,
    )
    return scan


__all__ = (
    # Locked basenames.
    "STAGE29_3_TRADEABLE_SMOKE_RESULT_BASENAME",
    "STAGE29_3_EXTRACTED_HINTS_BASENAME",
    "STAGE29_3_BIRDEYE_EVIDENCE_BASENAME",
    "STAGE29_3_REDACTION_SCAN_BASENAME",
    "STAGE29_3_ARTIFACT_BASENAMES",
    "STAGE28_9_COMPANION_ARTIFACT_BASENAMES",
    # Forbidden substring set.
    "FORBIDDEN_SCAN_SUBSTRINGS",
    # Projectors.
    "project_extraction_result_to_safe_dict",
    "project_birdeye_evidence_to_safe_dict",
    # Atomic writers.
    "write_smoke_result_artifact",
    "write_extracted_hints_artifact",
    "write_birdeye_evidence_artifact",
    "run_redaction_scan",
    "write_redaction_scan_artifact",
    "write_stage29_3_artifact_bundle",
)
