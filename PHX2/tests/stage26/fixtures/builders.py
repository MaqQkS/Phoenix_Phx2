"""Stage 26.1 test fixture builders.

Synthetic Stage 25-shape JSON / JSONL byte builders used by the
Stage 26.1 test suite. Every fixture is handcrafted: no live Stage
25 artifact is checked into the repository, no Stage 25 record
class is imported, and no Stage 25 production runner / writer is
invoked.

The builders import Stage 25 closed-set vocabulary tokens from
``PHX2.stage25.constants`` -- test code is permitted to consume
the Stage 25 constants directly, but Stage 26 PRODUCTION code goes
through ``PHX2.stage26.stage25_schema_whitelist`` (see Stage 26.0
spec-lock §8). Importing Stage 25 record / runner / writer modules
from production code is forbidden.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Optional

from PHX2.stage25.constants import (
    ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
    ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_NONE,
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_THRESHOLD_VERSION,
    MEASUREMENT_FAMILY_ATH,
    MEASUREMENT_FAMILY_MIGRATION,
    MEASUREMENT_STATUS_AMBIGUOUS,
    MEASUREMENT_STATUS_MEASURED,
    MEASUREMENT_STATUS_MISSING,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_SOURCE_CONFLICT,
    OBSERVE_ONLY_MODE,
    PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
    PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
    QUOTE_DENOMINATION_USD_MICRO,
    RECONCILIATION_STATUS_AGREED,
    RECONCILIATION_STATUS_AMBIGUOUS,
    RECONCILIATION_STATUS_NO_SOURCES,
    REDACTION_CONFIRMED_TOKEN,
    REJECTION_REASON_INPUT_MALFORMED,
    SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
    SELF_REFERENTIAL_MANIFEST_SHA256,
    SOURCE_FAMILY_BIRDEYE,
    SOURCE_FAMILY_DEXSCREENER,
    SOURCE_STATUS_PRESENT,
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_ATH_MEASUREMENTS_FILENAME,
    STAGE25_MANIFEST_FILENAME,
    STAGE25_MANIFEST_SCHEMA_VERSION,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    STAGE25_RUNNER_NAME,
    STAGE25_RUNNER_VERSION,
    STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    STAGE25_SUMMARY_FILENAME,
    STAGE25_SUMMARY_VERSION,
    STAGE25_WRITER_NAME,
    STAGE25_WRITER_VERSION,
    STAGE_NAME,
    STAGE_VERSION,
)


# ---------------------------------------------------------------------------
# Sample token / signature / pool literals (non-secret synthetic strings)
# ---------------------------------------------------------------------------


SAMPLE_TOKEN_MINT_A: str = "MintAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
SAMPLE_TOKEN_MINT_B: str = "MintBbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
SAMPLE_TOKEN_MINT_C: str = "MintCcccccccccccccccccccccccccccccccccccccc"
SAMPLE_MIGRATION_POOL: str = "PoolXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
SAMPLE_MIGRATION_SIGNATURE: str = "sig_migration_synthetic_001"
SAMPLE_MIGRATION_SIGNATURE_ALT: str = "sig_migration_synthetic_002"
FIXED_CLOCK_UTC: str = "2026-01-01T00:00:00Z"
FIXED_PEAK_AT_UTC: str = "2026-01-01T01:00:00Z"
FAKE_HASH_64: str = "a" * 64
FAKE_HASH_64_ALT: str = "b" * 64


# ---------------------------------------------------------------------------
# Canonical JSON serializers (mirror Stage 25's writer)
# ---------------------------------------------------------------------------


def canonical_json_bytes(obj: object) -> bytes:
    """Serialize ``obj`` with the Stage 25 canonical-JSON convention.

    sort_keys=True, ASCII-safe, minimal separators, no trailing
    newline. Returns the bytes a Stage 25 JSON artifact would carry
    on disk.
    """
    text = json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return text.encode("utf-8")


def canonical_jsonl_bytes(rows: tuple[Mapping[str, object], ...]) -> bytes:
    """Serialize ``rows`` as a JSONL byte stream.

    Each row is canonical JSON; rows are joined with ``"\\n"`` and a
    trailing ``"\\n"`` is appended iff ``rows`` is non-empty. An empty
    ``rows`` tuple produces ``b""``.
    """
    if rows == ():
        return b""
    pieces: list[str] = []
    for row in rows:
        pieces.append(
            json.dumps(
                row,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
        )
    return ("\n".join(pieces) + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Per-row dict builders (return dicts with the exact key set the reader expects)
# ---------------------------------------------------------------------------


def make_migration_observation_dict(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    source_family: str = SOURCE_FAMILY_BIRDEYE,
    source_status: str = SOURCE_STATUS_PRESENT,
    observed_at_utc: str = FIXED_CLOCK_UTC,
    slot: int = 251_000_000,
    block_time: int = 1_750_000_000,
    migration_signature: str = SAMPLE_MIGRATION_SIGNATURE,
    migration_pool: str = SAMPLE_MIGRATION_POOL,
    provider_id: str = "fixture_provider",
    reason_codes: tuple[str, ...] = (),
    evidence: Optional[Mapping[str, object]] = None,
    input_missing_fields: tuple[str, ...] = (),
    observation_hash: str = FAKE_HASH_64,
) -> dict[str, object]:
    return {
        "token_mint": token_mint,
        "source_family": source_family,
        "source_status": source_status,
        "observed_at_utc": observed_at_utc,
        "slot": slot,
        "block_time": block_time,
        "migration_signature": migration_signature,
        "migration_pool": migration_pool,
        "provider_id": provider_id,
        "reason_codes": list(reason_codes),
        "evidence": dict(evidence) if evidence is not None else {},
        "input_missing_fields": list(input_missing_fields),
        "observation_hash": observation_hash,
    }


def make_migration_measurement_measured_dict(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    consolidated_slot: int = 251_000_000,
    consolidated_block_time: int = 1_750_000_000,
    reconciled_signature: str = SAMPLE_MIGRATION_SIGNATURE,
    selected_source_family: str = SOURCE_FAMILY_BIRDEYE,
    measurement_hash: str = FAKE_HASH_64,
    reason_codes: tuple[str, ...] = ("MIGRATION_SOURCES_AGREED",),
) -> dict[str, object]:
    return {
        "measurement_family": MEASUREMENT_FAMILY_MIGRATION,
        "measurement_status": MEASUREMENT_STATUS_MEASURED,
        "confidence_level": CONFIDENCE_LEVEL_HIGH,
        "reconciliation_status": RECONCILIATION_STATUS_AGREED,
        "token_mint": token_mint,
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "threshold_version": DEFAULT_THRESHOLD_VERSION,
        "measurer_name": "stage25_migration_measurer",
        "measurer_version": "stage25_migration_measurer_v0",
        "consolidated_slot": consolidated_slot,
        "consolidated_block_time": consolidated_block_time,
        "reconciled_signature": reconciled_signature,
        "selected_source_family": selected_source_family,
        "contributing_source_count": 2,
        "reason_codes": list(reason_codes),
        "numeric_features": {
            "contributor_count": 2,
            "block_time_spread_seconds": 0,
            "tolerance_seconds": 60,
        },
        "evidence": {
            "contributing_source_families": [
                SOURCE_FAMILY_BIRDEYE,
                SOURCE_FAMILY_DEXSCREENER,
            ],
            "observed_source_families": [
                SOURCE_FAMILY_BIRDEYE,
                SOURCE_FAMILY_DEXSCREENER,
            ],
            "observation_count": 2,
            "duplicate_collapsed_count": 0,
        },
        "input_missing_fields": [],
        "measurement_hash": measurement_hash,
    }


def make_migration_measurement_missing_dict(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_B,
    measurement_hash: str = FAKE_HASH_64_ALT,
    reason_codes: tuple[str, ...] = ("MIGRATION_NO_OBSERVATIONS",),
    measurement_status: str = MEASUREMENT_STATUS_MISSING,
    reconciliation_status: str = RECONCILIATION_STATUS_NO_SOURCES,
    confidence_level: str = CONFIDENCE_LEVEL_NONE,
) -> dict[str, object]:
    return {
        "measurement_family": MEASUREMENT_FAMILY_MIGRATION,
        "measurement_status": measurement_status,
        "confidence_level": confidence_level,
        "reconciliation_status": reconciliation_status,
        "token_mint": token_mint,
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "threshold_version": DEFAULT_THRESHOLD_VERSION,
        "measurer_name": "stage25_migration_measurer",
        "measurer_version": "stage25_migration_measurer_v0",
        "consolidated_slot": -1,
        "consolidated_block_time": -1,
        "reconciled_signature": "",
        "selected_source_family": "",
        "contributing_source_count": 0,
        "reason_codes": list(reason_codes),
        "numeric_features": {
            "contributor_count": 0,
            "block_time_spread_seconds": 0,
            "tolerance_seconds": 60,
        },
        "evidence": {
            "contributing_source_families": [],
            "observed_source_families": [],
            "observation_count": 0,
            "duplicate_collapsed_count": 0,
        },
        "input_missing_fields": [],
        "measurement_hash": measurement_hash,
    }


def make_price_window_observation_dict(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    window_kind: str = PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY,
    price: Optional[int] = 1_500_000,
    observation_hash: str = FAKE_HASH_64,
    source_family: str = SOURCE_FAMILY_BIRDEYE,
    source_status: str = SOURCE_STATUS_PRESENT,
    reason_codes: tuple[str, ...] = (
        "PRICE_WINDOW_POST_MIGRATION_PRIMARY",
    ),
) -> dict[str, object]:
    return {
        "token_mint": token_mint,
        "source_family": source_family,
        "source_status": source_status,
        "window_kind": window_kind,
        "observed_at_utc": FIXED_PEAK_AT_UTC,
        "slot": 251_000_500,
        "block_time": 1_750_001_000,
        "price": price,
        "quote_denomination": QUOTE_DENOMINATION_USD_MICRO,
        "reason_codes": list(reason_codes),
        "evidence": {
            "source_observation_hash": FAKE_HASH_64,
            "migration_measurement_hash": FAKE_HASH_64,
            "migration_measurement_status": MEASUREMENT_STATUS_MEASURED,
            "migration_consolidated_block_time": 1_750_000_000,
            "window_version": "stage25_price_window_v0",
            "threshold_version": DEFAULT_THRESHOLD_VERSION,
            "input_missing_fields": [],
        },
        "observation_hash": observation_hash,
    }


def make_ath_candidate_dict(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    source_family: str = SOURCE_FAMILY_BIRDEYE,
    candidate_kind: str = ATH_CANDIDATE_KIND_SOURCE_REPORTED_PEAK,
    confidence_level: str = CONFIDENCE_LEVEL_MEDIUM,
    peak_price: Optional[int] = 1_500_000,
    candidate_hash: str = FAKE_HASH_64,
) -> dict[str, object]:
    is_insufficient = candidate_kind == ATH_CANDIDATE_KIND_INSUFFICIENT_DATA
    peak_observed_at = "" if is_insufficient else FIXED_PEAK_AT_UTC
    peak_slot = -1 if is_insufficient else 251_000_500
    peak_block_time = -1 if is_insufficient else 1_750_001_000
    selected_window_kind = (
        ""
        if is_insufficient
        else PRICE_WINDOW_KIND_POST_MIGRATION_PRIMARY
    )
    selected_observation_hash = "" if is_insufficient else FAKE_HASH_64
    return {
        "token_mint": token_mint,
        "source_family": source_family,
        "source_status": SOURCE_STATUS_PRESENT,
        "candidate_kind": candidate_kind,
        "confidence_level": CONFIDENCE_LEVEL_NONE if is_insufficient else confidence_level,
        "peak_observed_at_utc": peak_observed_at,
        "peak_slot": peak_slot,
        "peak_block_time": peak_block_time,
        "peak_price": None if is_insufficient else peak_price,
        "quote_denomination": QUOTE_DENOMINATION_USD_MICRO,
        "reason_codes": (
            ["ATH_CANDIDATE_INSUFFICIENT_DATA"]
            if is_insufficient
            else ["ATH_CANDIDATE_SELECTED_SOURCE_PEAK"]
        ),
        "evidence": {
            "candidate_version": "stage25_ath_candidate_v0",
            "threshold_version": DEFAULT_THRESHOLD_VERSION,
            "selected_window_kind": selected_window_kind,
            "selected_observation_hash": selected_observation_hash,
            "observation_count": 1,
            "eligible_observation_count": 0 if is_insufficient else 1,
            "window_observation_hashes": (
                [] if is_insufficient else [FAKE_HASH_64]
            ),
        },
        "input_missing_fields": [],
        "candidate_hash": candidate_hash,
    }


def make_source_reconciliation_dict(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    reconciliation_status: str = RECONCILIATION_STATUS_AGREED,
    confidence_level: str = CONFIDENCE_LEVEL_HIGH,
    reconciliation_hash: str = FAKE_HASH_64,
    disagreement_metric: Optional[Mapping[str, object]] = None,
) -> dict[str, object]:
    return {
        "measurement_family": MEASUREMENT_FAMILY_ATH,
        "reconciliation_status": reconciliation_status,
        "confidence_level": confidence_level,
        "token_mint": token_mint,
        "source_families": [SOURCE_FAMILY_BIRDEYE, SOURCE_FAMILY_DEXSCREENER],
        "contributing_source_count": 2,
        "disagreeing_source_count": 0,
        "disagreement_metric": (
            None
            if disagreement_metric is None
            else dict(disagreement_metric)
        ),
        "reason_codes": ["SOURCE_RECONCILIATION_SOURCES_AGREED"],
        "evidence": {
            "reconciliation_version": "stage25_source_reconciliation_v0",
            "threshold_version": DEFAULT_THRESHOLD_VERSION,
            "candidate_count": 2,
            "contributor_count": 2,
            "candidate_hashes": [FAKE_HASH_64, FAKE_HASH_64_ALT],
            "contributor_candidate_hashes": [FAKE_HASH_64, FAKE_HASH_64_ALT],
            "quote_denomination": QUOTE_DENOMINATION_USD_MICRO,
            "price_disagreement_tolerance_ppm": 50_000,
            "peak_time_tolerance_seconds": 120,
            "price_disagreement_major_tolerance_ppm": 250_000,
            "peak_time_major_tolerance_seconds": 600,
        },
        "reconciliation_hash": reconciliation_hash,
    }


def make_ath_measurement_measured_dict(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_A,
    consolidated_peak_slot: int = 251_000_500,
    consolidated_peak_block_time: int = 1_750_001_000,
    consolidated_peak_price: Optional[int] = 1_500_000,
    peak_source_family: str = SOURCE_FAMILY_BIRDEYE,
    reconciled_peak_observed_at_utc: str = FIXED_PEAK_AT_UTC,
    measurement_hash: str = FAKE_HASH_64,
) -> dict[str, object]:
    return {
        "measurement_family": MEASUREMENT_FAMILY_ATH,
        "measurement_status": MEASUREMENT_STATUS_MEASURED,
        "confidence_level": CONFIDENCE_LEVEL_HIGH,
        "reconciliation_status": RECONCILIATION_STATUS_AGREED,
        "token_mint": token_mint,
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "threshold_version": DEFAULT_THRESHOLD_VERSION,
        "measurer_name": "stage25_ath_measurer",
        "measurer_version": "stage25_ath_measurement_v0",
        "consolidated_peak_slot": consolidated_peak_slot,
        "consolidated_peak_block_time": consolidated_peak_block_time,
        "consolidated_peak_price": consolidated_peak_price,
        "quote_denomination": QUOTE_DENOMINATION_USD_MICRO,
        "peak_source_family": peak_source_family,
        "reconciled_peak_observed_at_utc": reconciled_peak_observed_at_utc,
        "time_to_peak_seconds": None,
        "contributing_source_count": 2,
        "reason_codes": ["ATH_MEASUREMENT_MEASURED_FROM_AGREED_SOURCES"],
        "numeric_features": {
            "candidate_count": 2,
            "contributor_count": 2,
            "contributing_source_count": 2,
            "disagreeing_source_count": 0,
        },
        "evidence": {
            "measurement_version": "stage25_ath_measurement_v0",
            "threshold_version": DEFAULT_THRESHOLD_VERSION,
            "reconciliation_hash": FAKE_HASH_64,
            "candidate_hashes": [FAKE_HASH_64, FAKE_HASH_64_ALT],
            "contributor_candidate_hashes": [
                FAKE_HASH_64,
                FAKE_HASH_64_ALT,
            ],
            "quote_denomination": QUOTE_DENOMINATION_USD_MICRO,
        },
        "input_missing_fields": [],
        "measurement_hash": measurement_hash,
    }


def make_ath_measurement_missing_dict(
    *,
    token_mint: str = SAMPLE_TOKEN_MINT_B,
    measurement_hash: str = FAKE_HASH_64_ALT,
    measurement_status: str = MEASUREMENT_STATUS_MISSING,
    reconciliation_status: str = RECONCILIATION_STATUS_NO_SOURCES,
    confidence_level: str = CONFIDENCE_LEVEL_NONE,
) -> dict[str, object]:
    return {
        "measurement_family": MEASUREMENT_FAMILY_ATH,
        "measurement_status": measurement_status,
        "confidence_level": confidence_level,
        "reconciliation_status": reconciliation_status,
        "token_mint": token_mint,
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "threshold_version": DEFAULT_THRESHOLD_VERSION,
        "measurer_name": "stage25_ath_measurer",
        "measurer_version": "stage25_ath_measurement_v0",
        "consolidated_peak_slot": -1,
        "consolidated_peak_block_time": -1,
        "consolidated_peak_price": None,
        "quote_denomination": QUOTE_DENOMINATION_USD_MICRO,
        "peak_source_family": "",
        "reconciled_peak_observed_at_utc": "",
        "time_to_peak_seconds": None,
        "contributing_source_count": 0,
        "reason_codes": ["ATH_MEASUREMENT_MISSING_NO_SOURCES"],
        "numeric_features": {
            "candidate_count": 0,
            "contributor_count": 0,
            "contributing_source_count": 0,
            "disagreeing_source_count": 0,
        },
        "evidence": {
            "measurement_version": "stage25_ath_measurement_v0",
            "threshold_version": DEFAULT_THRESHOLD_VERSION,
            "reconciliation_hash": FAKE_HASH_64_ALT,
            "candidate_hashes": [],
            "contributor_candidate_hashes": [],
            "quote_denomination": QUOTE_DENOMINATION_USD_MICRO,
        },
        "input_missing_fields": [],
        "measurement_hash": measurement_hash,
    }


def make_measurement_rejection_dict(
    *,
    rejection_reason: str = REJECTION_REASON_INPUT_MALFORMED,
    token_mint: str = SAMPLE_TOKEN_MINT_C,
    source_family: str = SOURCE_FAMILY_BIRDEYE,
    detail: str = "synthetic rejection detail",
    reason_codes: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "rejection_reason": rejection_reason,
        "token_mint": token_mint,
        "source_family": source_family,
        "detail": detail,
        "reason_codes": list(reason_codes),
    }


# ---------------------------------------------------------------------------
# Summary dict builder
# ---------------------------------------------------------------------------


def _zero_count_map(tokens: tuple[str, ...]) -> dict[str, int]:
    return {token: 0 for token in tokens}


def make_summary_dict(
    *,
    row_counts: Mapping[str, int],
    created_at_utc: str = FIXED_CLOCK_UTC,
    observed_token_count: int = 0,
) -> dict[str, object]:
    from PHX2.stage25.constants import (
        ATH_CANDIDATE_KINDS,
        CONFIDENCE_LEVELS,
        MEASUREMENT_STATUSES,
        PRICE_WINDOW_KINDS,
        RECONCILIATION_STATUSES,
        REJECTION_REASONS,
        SOURCE_FAMILIES,
        SOURCE_STATUSES,
    )

    return {
        "stage_name": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "schema_version": DEFAULT_SCHEMA_VERSION,
        "summary_version": STAGE25_SUMMARY_VERSION,
        "observe_only_mode": OBSERVE_ONLY_MODE,
        "created_at_utc": created_at_utc,
        "observed_token_count": observed_token_count,
        "row_counts": dict(row_counts),
        "migration_observation_source_family_counts": _zero_count_map(
            SOURCE_FAMILIES
        ),
        "migration_observation_source_status_counts": _zero_count_map(
            SOURCE_STATUSES
        ),
        "migration_measurement_status_counts": _zero_count_map(
            MEASUREMENT_STATUSES
        ),
        "migration_measurement_confidence_counts": _zero_count_map(
            CONFIDENCE_LEVELS
        ),
        "migration_measurement_reconciliation_counts": _zero_count_map(
            RECONCILIATION_STATUSES
        ),
        "price_window_kind_counts": _zero_count_map(PRICE_WINDOW_KINDS),
        "price_window_source_status_counts": _zero_count_map(
            SOURCE_STATUSES
        ),
        "ath_candidate_kind_counts": _zero_count_map(ATH_CANDIDATE_KINDS),
        "ath_candidate_confidence_counts": _zero_count_map(
            CONFIDENCE_LEVELS
        ),
        "ath_candidate_source_family_counts": _zero_count_map(
            SOURCE_FAMILIES
        ),
        "ath_candidate_source_status_counts": _zero_count_map(
            SOURCE_STATUSES
        ),
        "source_reconciliation_status_counts": _zero_count_map(
            RECONCILIATION_STATUSES
        ),
        "source_reconciliation_confidence_counts": _zero_count_map(
            CONFIDENCE_LEVELS
        ),
        "ath_measurement_status_counts": _zero_count_map(
            MEASUREMENT_STATUSES
        ),
        "ath_measurement_confidence_counts": _zero_count_map(
            CONFIDENCE_LEVELS
        ),
        "ath_measurement_reconciliation_counts": _zero_count_map(
            RECONCILIATION_STATUSES
        ),
        "rejection_reason_counts": _zero_count_map(REJECTION_REASONS),
    }


# ---------------------------------------------------------------------------
# Manifest dict + file-write helpers
# ---------------------------------------------------------------------------


_REQUIRED_JSONL_BASENAMES: tuple[str, ...] = (
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    STAGE25_ATH_MEASUREMENTS_FILENAME,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
)


def make_manifest_dict(
    *,
    file_entries: tuple[Mapping[str, object], ...],
    created_at_utc: str = FIXED_CLOCK_UTC,
    redaction_confirmed: str = REDACTION_CONFIRMED_TOKEN,
    upstream_stage24_pin: Optional[Mapping[str, object]] = None,
    manifest_kind: str = "artifact",
) -> dict[str, object]:
    # The manifest writer sorts entries lex by file_basename; mirror that.
    sorted_entries = sorted(
        (dict(entry) for entry in file_entries),
        key=lambda entry: entry["file_basename"],  # type: ignore[index]
    )
    return {
        "stage_name": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "schema_version": STAGE25_MANIFEST_SCHEMA_VERSION,
        "observe_only_mode": OBSERVE_ONLY_MODE,
        "redaction_confirmed": redaction_confirmed,
        "manifest_kind": manifest_kind,
        "files": sorted_entries,
        "upstream_stage24_pin": (
            dict(upstream_stage24_pin)
            if upstream_stage24_pin is not None
            else None
        ),
        "created_at_utc": created_at_utc,
        "runner_name": STAGE25_RUNNER_NAME,
        "runner_version": STAGE25_RUNNER_VERSION,
        "writer_name": STAGE25_WRITER_NAME,
        "writer_version": STAGE25_WRITER_VERSION,
    }


def _file_entry(
    *,
    basename: str,
    sha256: str,
    row_count: int,
    byte_count: int,
) -> dict[str, object]:
    return {
        "file_basename": basename,
        "sha256": sha256,
        "row_count": row_count,
        "byte_count": byte_count,
    }


def _count_non_blank_lines(data: bytes) -> int:
    if data == b"":
        return 0
    return sum(
        1 for line in data.decode("utf-8").split("\n") if line.strip() != ""
    )


def write_stage25_dir(
    *,
    base_dir: Path,
    artifact_bytes_by_basename: Mapping[str, bytes],
    manifest_overrides: Optional[Mapping[str, object]] = None,
    extra_manifest_entries: tuple[Mapping[str, object], ...] = (),
    omit_manifest_entry_basenames: tuple[str, ...] = (),
    self_entry_override: Optional[Mapping[str, object]] = None,
) -> Path:
    """Write a complete Stage 25 directory under ``base_dir``.

    ``artifact_bytes_by_basename`` MUST carry every non-manifest
    artifact basename (the 7 JSONL artifacts + the summary). The
    helper computes each entry's sha256 / byte_count / row_count
    and assembles a manifest with the locked self-entry sentinel.

    Optional knobs:
      * ``manifest_overrides``         -- merged into the manifest
        body before serialization (e.g. to flip
        ``observe_only_mode`` to an invalid value).
      * ``extra_manifest_entries``     -- extra file entries to add
        to ``files`` (e.g. to declare a basename the directory does
        not contain).
      * ``omit_manifest_entry_basenames`` -- basenames to drop from
        the manifest (e.g. to declare the manifest does not list a
        required artifact).
      * ``self_entry_override``        -- replace the manifest's own
        self-entry record (e.g. to violate the sentinel rule).
    """
    stage25_dir = base_dir / "stage25"
    stage25_dir.mkdir(parents=True, exist_ok=False)

    file_entries: list[dict[str, object]] = []
    for basename, payload in artifact_bytes_by_basename.items():
        file_path = stage25_dir / basename
        file_path.write_bytes(payload)
        if basename.endswith(".jsonl"):
            row_count = _count_non_blank_lines(payload)
        else:
            row_count = -1
        file_entries.append(
            _file_entry(
                basename=basename,
                sha256=sha256_hex(payload),
                row_count=row_count,
                byte_count=len(payload),
            )
        )

    if self_entry_override is None:
        file_entries.append(
            _file_entry(
                basename=STAGE25_MANIFEST_FILENAME,
                sha256=SELF_REFERENTIAL_MANIFEST_SHA256,
                row_count=SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
                byte_count=SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
            )
        )
    else:
        file_entries.append(dict(self_entry_override))

    # Apply omit BEFORE extending with extras so a caller can drop the
    # auto-generated entry for a basename and then provide a hand-
    # crafted (e.g. intentionally-tampered) replacement.
    filtered_entries_list = [
        entry
        for entry in file_entries
        if entry["file_basename"] not in omit_manifest_entry_basenames
    ]
    filtered_entries_list.extend(
        dict(entry) for entry in extra_manifest_entries
    )
    filtered_entries = tuple(filtered_entries_list)

    manifest_body = make_manifest_dict(file_entries=filtered_entries)
    if manifest_overrides is not None:
        manifest_body.update(manifest_overrides)
    manifest_bytes = canonical_json_bytes(manifest_body)
    (stage25_dir / STAGE25_MANIFEST_FILENAME).write_bytes(manifest_bytes)
    return stage25_dir


# ---------------------------------------------------------------------------
# High-level convenience: write a complete valid Stage 25 directory
# ---------------------------------------------------------------------------


def _default_artifact_payloads() -> dict[str, bytes]:
    migration_observations = (
        make_migration_observation_dict(
            token_mint=SAMPLE_TOKEN_MINT_A,
            observation_hash=FAKE_HASH_64,
        ),
        make_migration_observation_dict(
            token_mint=SAMPLE_TOKEN_MINT_B,
            source_family=SOURCE_FAMILY_DEXSCREENER,
            observation_hash=FAKE_HASH_64_ALT,
        ),
    )
    migration_measurements = (
        make_migration_measurement_measured_dict(
            token_mint=SAMPLE_TOKEN_MINT_A,
            measurement_hash=FAKE_HASH_64,
        ),
        make_migration_measurement_missing_dict(
            token_mint=SAMPLE_TOKEN_MINT_B,
            measurement_hash=FAKE_HASH_64_ALT,
        ),
    )
    price_window_observations = (
        make_price_window_observation_dict(
            token_mint=SAMPLE_TOKEN_MINT_A,
            observation_hash=FAKE_HASH_64,
        ),
        make_price_window_observation_dict(
            token_mint=SAMPLE_TOKEN_MINT_A,
            window_kind=PRICE_WINDOW_KIND_PRE_MIGRATION_EXCLUDED,
            reason_codes=("PRICE_WINDOW_PRE_MIGRATION_EXCLUDED",),
            observation_hash=FAKE_HASH_64_ALT,
        ),
    )
    ath_candidates = (
        make_ath_candidate_dict(
            token_mint=SAMPLE_TOKEN_MINT_A,
            candidate_hash=FAKE_HASH_64,
        ),
        make_ath_candidate_dict(
            token_mint=SAMPLE_TOKEN_MINT_B,
            candidate_kind=ATH_CANDIDATE_KIND_INSUFFICIENT_DATA,
            candidate_hash=FAKE_HASH_64_ALT,
        ),
    )
    source_reconciliations = (
        make_source_reconciliation_dict(
            token_mint=SAMPLE_TOKEN_MINT_A,
            reconciliation_hash=FAKE_HASH_64,
        ),
        make_source_reconciliation_dict(
            token_mint=SAMPLE_TOKEN_MINT_B,
            reconciliation_status=RECONCILIATION_STATUS_NO_SOURCES,
            confidence_level=CONFIDENCE_LEVEL_NONE,
            reconciliation_hash=FAKE_HASH_64_ALT,
        ),
    )
    ath_measurements = (
        make_ath_measurement_measured_dict(
            token_mint=SAMPLE_TOKEN_MINT_A,
            measurement_hash=FAKE_HASH_64,
        ),
        make_ath_measurement_missing_dict(
            token_mint=SAMPLE_TOKEN_MINT_B,
            measurement_hash=FAKE_HASH_64_ALT,
        ),
    )
    measurement_rejections = (
        make_measurement_rejection_dict(),
    )
    payloads = {
        STAGE25_MIGRATION_OBSERVATIONS_FILENAME: canonical_jsonl_bytes(
            migration_observations
        ),
        STAGE25_MIGRATION_MEASUREMENTS_FILENAME: canonical_jsonl_bytes(
            migration_measurements
        ),
        STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME: canonical_jsonl_bytes(
            price_window_observations
        ),
        STAGE25_ATH_CANDIDATES_FILENAME: canonical_jsonl_bytes(
            ath_candidates
        ),
        STAGE25_SOURCE_RECONCILIATIONS_FILENAME: canonical_jsonl_bytes(
            source_reconciliations
        ),
        STAGE25_ATH_MEASUREMENTS_FILENAME: canonical_jsonl_bytes(
            ath_measurements
        ),
        STAGE25_MEASUREMENT_REJECTIONS_FILENAME: canonical_jsonl_bytes(
            measurement_rejections
        ),
    }
    summary = make_summary_dict(
        row_counts={
            "migration_observations": len(migration_observations),
            "migration_measurements": len(migration_measurements),
            "price_window_observations": len(price_window_observations),
            "ath_candidates": len(ath_candidates),
            "source_reconciliations": len(source_reconciliations),
            "ath_measurements": len(ath_measurements),
            "rejections": len(measurement_rejections),
        },
        observed_token_count=2,
    )
    payloads[STAGE25_SUMMARY_FILENAME] = canonical_json_bytes(summary)
    return payloads


def write_default_valid_stage25_dir(base_dir: Path) -> Path:
    """Write a complete valid Stage 25 directory and return its path."""
    return write_stage25_dir(
        base_dir=base_dir,
        artifact_bytes_by_basename=_default_artifact_payloads(),
    )


def write_empty_stage25_dir(base_dir: Path) -> Path:
    """Write a Stage 25 directory where every JSONL artifact is empty.

    The manifest carries row_count=0 / byte_count=0 for each JSONL
    artifact. Useful for the "empty-but-present JSONL is valid"
    test.
    """
    payloads: dict[str, bytes] = {
        basename: b"" for basename in _REQUIRED_JSONL_BASENAMES
    }
    summary = make_summary_dict(
        row_counts={
            "migration_observations": 0,
            "migration_measurements": 0,
            "price_window_observations": 0,
            "ath_candidates": 0,
            "source_reconciliations": 0,
            "ath_measurements": 0,
            "rejections": 0,
        },
        observed_token_count=0,
    )
    payloads[STAGE25_SUMMARY_FILENAME] = canonical_json_bytes(summary)
    return write_stage25_dir(
        base_dir=base_dir,
        artifact_bytes_by_basename=payloads,
    )


__all__ = [
    "FAKE_HASH_64",
    "FAKE_HASH_64_ALT",
    "FIXED_CLOCK_UTC",
    "FIXED_PEAK_AT_UTC",
    "SAMPLE_MIGRATION_POOL",
    "SAMPLE_MIGRATION_SIGNATURE",
    "SAMPLE_MIGRATION_SIGNATURE_ALT",
    "SAMPLE_TOKEN_MINT_A",
    "SAMPLE_TOKEN_MINT_B",
    "SAMPLE_TOKEN_MINT_C",
    "canonical_json_bytes",
    "canonical_jsonl_bytes",
    "make_ath_candidate_dict",
    "make_ath_measurement_measured_dict",
    "make_ath_measurement_missing_dict",
    "make_manifest_dict",
    "make_measurement_rejection_dict",
    "make_migration_measurement_measured_dict",
    "make_migration_measurement_missing_dict",
    "make_migration_observation_dict",
    "make_price_window_observation_dict",
    "make_source_reconciliation_dict",
    "make_summary_dict",
    "sha256_hex",
    "write_default_valid_stage25_dir",
    "write_empty_stage25_dir",
    "write_stage25_dir",
]
