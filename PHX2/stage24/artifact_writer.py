"""Stage 24.6 deterministic artifact writer.

Writes a Stage 24 run's deterministic, redaction-scanned
artifacts to a caller-supplied output directory:

  * ``stage24_manifest.json``                    -- artifact manifest with
                                                    file basenames,
                                                    SHA-256 hashes,
                                                    row counts, Stage
                                                    24.5 lock markers.
  * ``stage24_summary.json``                     -- per-(primitive_family,
                                                    decoder_status)
                                                    counter summary.
  * ``stage24_execution_primitives.jsonl``       -- unified per-primitive
                                                    rows.
  * ``stage24_compute_budget_results.jsonl``     -- per-tx compute-budget
                                                    decoder rows.
  * ``stage24_priority_fee_results.jsonl``       -- per-tx priority-fee
                                                    decoder rows.
  * ``stage24_jito_tip_results.jsonl``           -- per-tx Jito-tip
                                                    decoder rows.
  * ``stage24_router_fee_results.jsonl``         -- per-tx router-fee
                                                    rows with
                                                    ``decoder_status =
                                                    DECODED``. Empty at
                                                    Stage 24.6 because
                                                    Stage 24.5 took Path
                                                    B.
  * ``stage24_router_fee_candidates.jsonl``      -- per-tx router-fee
                                                    candidate rows
                                                    (24.4 / 24.5
                                                    candidate-only).
  * ``stage24_execution_quality_results.jsonl``  -- per-tx
                                                    execution-quality
                                                    rows.
  * ``stage24_decoder_coverage.csv``             -- per-(primitive_family,
                                                    decoder_status,
                                                    data_status)
                                                    coverage matrix.
  * ``stage24_rejections.jsonl``                 -- one row per
                                                    rejection (typed
                                                    Stage24Error during
                                                    a decoder call).

Honesty rules:

  * Stage 24.5 took Path B; no confirmed router/global-fee
    decoder exists. Router-fee rows with
    ``decoder_status == "DECODED"`` are never emitted. The
    writer partitions ``runner_result.router_fee_results`` into
    candidates (everything except DECODED) and confirmed
    (DECODED). With Path B, the confirmed bucket is empty.
  * The manifest carries
    ``STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER`` /
    ``STAGE_24_5_REAL_FIXTURE_COUNT`` /
    ``STAGE_24_5_CONFIRMED_LAYOUT_COUNT`` so downstream readers
    can see the no-confirmed-decoder state explicitly.
  * Writes are atomic: each artifact is staged into a temp
    sibling file in the same directory then renamed into place.
    A failure mid-write does not leave a partial artifact under
    the locked filename.
  * Every artifact body is shape-redaction-scanned before write:
    forbidden field substrings, URL / webhook-host substrings,
    and long-hex-run shapes cause the writer to refuse the run
    rather than persist the leak.
  * Every row's JSON encoding is canonical (sorted keys, no
    whitespace, ASCII-safe).

This module imports only stdlib (``hashlib`` / ``pathlib`` /
``types`` / ``typing``) plus the Stage 24 constants, models,
errors, and runner. It does NOT import Stage 21 / Stage 22 /
Stage 23 modules; it does NOT import any network / RPC /
messaging / DB / scheduler / secrets-management library; it
does NOT read the process environment; it does NOT define a
CLI surface; and it contains no top-level I/O.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Mapping, NamedTuple, Optional

from PHX2.stage24.constants import (
    ALL_STAGE24_ARTIFACT_FILENAMES,
    ARTIFACT_FILENAME_COMPUTE_BUDGET_RESULTS,
    ARTIFACT_FILENAME_DECODER_COVERAGE,
    ARTIFACT_FILENAME_EXECUTION_PRIMITIVES,
    ARTIFACT_FILENAME_EXECUTION_QUALITY_RESULTS,
    ARTIFACT_FILENAME_JITO_TIP_RESULTS,
    ARTIFACT_FILENAME_MANIFEST,
    ARTIFACT_FILENAME_PRIORITY_FEE_RESULTS,
    ARTIFACT_FILENAME_REJECTIONS,
    ARTIFACT_FILENAME_ROUTER_FEE_CANDIDATES,
    ARTIFACT_FILENAME_ROUTER_FEE_RESULTS,
    ARTIFACT_FILENAME_SUMMARY,
    DECODER_STATUS_DECODED,
    DEFAULT_SCHEMA_VERSION,
    DEFAULT_THRESHOLD_VERSION,
    OBSERVE_ONLY_MODE,
    STAGE24_ARTIFACT_COVERAGE_SCHEMA_VERSION,
    STAGE24_ARTIFACT_SUMMARY_SCHEMA_VERSION,
    STAGE24_ARTIFACT_WRITER_NAME,
    STAGE24_ARTIFACT_WRITER_VERSION,
    STAGE24_FORBIDDEN_INPUT_FIELD_SUBSTRINGS,
    STAGE24_FORBIDDEN_INPUT_VALUE_SUBSTRINGS,
    STAGE24_LONG_HEX_RUN_MIN_LEN,
    STAGE24_MANIFEST_SCHEMA_VERSION,
    STAGE24_RUNNER_NAME,
    STAGE24_RUNNER_VERSION,
    STAGE_24_5_CONFIRMED_LAYOUT_COUNT,
    STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER,
    STAGE_24_5_REAL_FIXTURE_COUNT,
    STAGE_NAME,
    STAGE_VERSION,
)
from PHX2.stage24.errors import Stage24Error
from PHX2.stage24.models import (
    Stage24ComputeBudgetResult,
    Stage24ExecutionPrimitive,
    Stage24ExecutionQualityResult,
    Stage24JitoTipResult,
    Stage24PriorityFeeResult,
    Stage24RouterFeeResult,
    Stage24RunnerResult,
    canonical_json,
)
from PHX2.stage24.runner import Stage24RejectionRecord
from PHX2.stage24.stage24_manifest import REDACTION_CONFIRMED_TOKEN


# ---------------------------------------------------------------------------
# Writer identity
# ---------------------------------------------------------------------------


WRITER_NAME: str = STAGE24_ARTIFACT_WRITER_NAME
WRITER_VERSION: str = STAGE24_ARTIFACT_WRITER_VERSION


# ---------------------------------------------------------------------------
# Stage24WriterError -- module-local typed error
# ---------------------------------------------------------------------------


class Stage24WriterError(Stage24Error):
    """Raised when the Stage 24.6 artifact writer sees a contract violation."""


# ---------------------------------------------------------------------------
# Public NamedTuple return shape
# ---------------------------------------------------------------------------


class Stage24ArtifactFileRecord(NamedTuple):
    """Per-artifact write record returned to the caller."""

    file_basename: str
    sha256: str
    row_count: int
    bytes_written: int


class Stage24ArtifactSet(NamedTuple):
    """Aggregate Stage 24.6 artifact writer return value.

    Carries the artifact directory plus a deterministic tuple of
    per-file records (sorted by ``file_basename``). The caller can
    reconcile the on-disk artifacts against this record without
    re-hashing.
    """

    artifact_records: tuple[Stage24ArtifactFileRecord, ...]
    summary_counters: Mapping[str, object]
    created_at_utc: str
    output_dir_name: str


# ---------------------------------------------------------------------------
# Path-safety helpers
# ---------------------------------------------------------------------------


def _require_safe_output_directory(output_dir: Path) -> None:
    """Reject unsafe output directory paths.

    The writer accepts only an existing directory; it does not
    create parents (callers control their working tree). Symlink
    paths are rejected to avoid accidental traversal.
    """
    if not isinstance(output_dir, Path):
        raise Stage24WriterError(
            "output_dir must be a pathlib.Path"
        )
    if not output_dir.exists():
        raise Stage24WriterError(
            "output_dir does not exist"
        )
    if not output_dir.is_dir():
        raise Stage24WriterError(
            "output_dir is not a directory"
        )
    if output_dir.is_symlink():
        raise Stage24WriterError(
            "output_dir must not be a symlink"
        )


def _require_safe_basename(basename: str) -> None:
    if not isinstance(basename, str) or basename == "":
        raise Stage24WriterError(
            "artifact basename must be a non-empty string"
        )
    if "/" in basename or "\\" in basename:
        raise Stage24WriterError(
            "artifact basename must not contain a path separator"
        )
    lower = basename.lower()
    for needle in STAGE24_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
        if needle in lower:
            raise Stage24WriterError(
                "artifact basename carries a forbidden field substring"
            )
    for needle in STAGE24_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
        if needle in lower:
            raise Stage24WriterError(
                "artifact basename carries a forbidden URL-shape substring"
            )


# ---------------------------------------------------------------------------
# Redaction sweep over outbound bodies
# ---------------------------------------------------------------------------


_HEX_CHARS: frozenset[str] = frozenset("0123456789abcdefABCDEF")


# Field names whose values are writer-computed deterministic
# hashes. The long-hex-run leak shape detector is skipped for
# these because Stage 24's own canonical SHA-256 hex digests are
# 64 chars of hex by design. Mirrors the input_reader's
# documented contract that "writer-computed SHA-256 hashes are
# never sent through" the value-shape detector.
_WRITER_COMPUTED_HASH_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "input_hash",
        "payload_hash",
        "primitive_hash",
        "result_hash",
        "sha256",
        "compute_budget_result_hash",
    }
)


def _value_carries_long_hex_run(value: str) -> bool:
    run = 0
    for ch in value:
        if ch in _HEX_CHARS:
            run += 1
            if run >= STAGE24_LONG_HEX_RUN_MIN_LEN:
                return True
        else:
            run = 0
    return False


def _scan_value_for_redaction(
    value: object,
    *,
    parent_field_name: Optional[str] = None,
) -> None:
    """Recursively assert ``value`` has no forbidden substring.

    Raises ``Stage24WriterError`` rather than redacting. The
    runner / decoders should already have stripped sensitive
    fields; this is a last line of defense.

    The long-hex-run leak shape check is skipped when
    ``parent_field_name`` is a writer-computed hash field name
    (``input_hash`` / ``primitive_hash`` / ``result_hash`` /
    ``payload_hash`` / ``sha256``). URL-shape and forbidden-
    field-name checks still apply to those fields.
    """
    if isinstance(value, bool) or isinstance(value, int):
        return
    if value is None:
        return
    if isinstance(value, float):
        return
    if isinstance(value, str):
        lower = value.lower()
        for needle in STAGE24_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
            if needle in lower:
                raise Stage24WriterError(
                    "artifact value carries a forbidden URL-shape "
                    "substring"
                )
        if parent_field_name not in _WRITER_COMPUTED_HASH_FIELD_NAMES:
            if _value_carries_long_hex_run(value):
                raise Stage24WriterError(
                    "artifact value carries a long-hex-run credential "
                    "shape"
                )
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _scan_value_for_redaction(
                item, parent_field_name=parent_field_name
            )
        return
    if isinstance(value, Mapping):
        for key, sub in value.items():
            if isinstance(key, str):
                key_lower = key.lower()
                for needle in STAGE24_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
                    if needle in key_lower:
                        raise Stage24WriterError(
                            "artifact key carries a forbidden field "
                            "substring"
                        )
                _scan_value_for_redaction(sub, parent_field_name=key)
            else:
                _scan_value_for_redaction(
                    sub, parent_field_name=None
                )
        return
    # Fall through: anything else is an unsupported shape; the
    # canonical-JSON serializer will reject it shortly.


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------


def _atomic_write_text(*, path: Path, body: str) -> int:
    """Write ``body`` to ``path`` atomically.

    Stages the bytes into a sibling temp file then renames into
    place. Returns the number of bytes written. ``path`` must
    not already exist as a symlink (defense-in-depth against
    overwriting linked targets).
    """
    encoded = body.encode("utf-8")
    if path.exists() and path.is_symlink():
        raise Stage24WriterError(
            "artifact path must not be a symlink"
        )
    temp_path = path.with_name(path.name + ".tmp")
    if temp_path.exists():
        # Clean up any leftover temp from a prior aborted run.
        # We never read from a temp file; safe to remove.
        temp_path.unlink()
    handle = temp_path.open("wb")
    try:
        handle.write(encoded)
        handle.flush()
    finally:
        handle.close()
    temp_path.replace(path)
    return len(encoded)


# ---------------------------------------------------------------------------
# Row-body builders
# ---------------------------------------------------------------------------


def _compute_budget_result_to_dict(
    result: Stage24ComputeBudgetResult,
) -> dict[str, object]:
    return {
        "primitive_family": result.primitive_family,
        "decoder_name": result.decoder_name,
        "decoder_version": result.decoder_version,
        "threshold_version": result.threshold_version,
        "decoder_status": result.decoder_status,
        "data_status": result.data_status,
        "confidence_level": result.confidence_level,
        "fee_source": result.fee_source,
        "route_family": result.route_family,
        "instruction_location": result.instruction_location,
        "program_id": result.program_id,
        "unit_limit": result.unit_limit,
        "unit_price_microlamports": result.unit_price_microlamports,
        "reason_codes": list(result.reason_codes),
        "numeric_features": dict(result.numeric_features),
        "evidence": dict(result.evidence),
        "input_missing_fields": list(result.input_missing_fields),
        "result_hash": result.result_hash,
    }


def _priority_fee_result_to_dict(
    result: Stage24PriorityFeeResult,
) -> dict[str, object]:
    return {
        "primitive_family": result.primitive_family,
        "decoder_name": result.decoder_name,
        "decoder_version": result.decoder_version,
        "threshold_version": result.threshold_version,
        "decoder_status": result.decoder_status,
        "data_status": result.data_status,
        "confidence_level": result.confidence_level,
        "fee_source": result.fee_source,
        "route_family": result.route_family,
        "instruction_location": result.instruction_location,
        "program_id": result.program_id,
        "amount_lamports": result.amount_lamports,
        "unit_limit": result.unit_limit,
        "unit_price_microlamports": result.unit_price_microlamports,
        "reason_codes": list(result.reason_codes),
        "numeric_features": dict(result.numeric_features),
        "evidence": dict(result.evidence),
        "input_missing_fields": list(result.input_missing_fields),
        "result_hash": result.result_hash,
    }


def _jito_tip_result_to_dict(
    result: Stage24JitoTipResult,
) -> dict[str, object]:
    return {
        "primitive_family": result.primitive_family,
        "decoder_name": result.decoder_name,
        "decoder_version": result.decoder_version,
        "threshold_version": result.threshold_version,
        "decoder_status": result.decoder_status,
        "data_status": result.data_status,
        "confidence_level": result.confidence_level,
        "fee_source": result.fee_source,
        "route_family": result.route_family,
        "instruction_location": result.instruction_location,
        "program_id": result.program_id,
        "tip_account": result.tip_account,
        "amount_lamports": result.amount_lamports,
        "reason_codes": list(result.reason_codes),
        "numeric_features": dict(result.numeric_features),
        "evidence": dict(result.evidence),
        "input_missing_fields": list(result.input_missing_fields),
        "result_hash": result.result_hash,
    }


def _router_fee_result_to_dict(
    result: Stage24RouterFeeResult,
) -> dict[str, object]:
    return {
        "primitive_family": result.primitive_family,
        "decoder_name": result.decoder_name,
        "decoder_version": result.decoder_version,
        "threshold_version": result.threshold_version,
        "decoder_status": result.decoder_status,
        "data_status": result.data_status,
        "confidence_level": result.confidence_level,
        "fee_source": result.fee_source,
        "route_family": result.route_family,
        "instruction_location": result.instruction_location,
        "program_id": result.program_id,
        "amount_lamports": result.amount_lamports,
        "amount_token": result.amount_token,
        "mint": result.mint,
        "reason_codes": list(result.reason_codes),
        "numeric_features": dict(result.numeric_features),
        "evidence": dict(result.evidence),
        "input_missing_fields": list(result.input_missing_fields),
        "result_hash": result.result_hash,
    }


def _execution_quality_result_to_dict(
    result: Stage24ExecutionQualityResult,
) -> dict[str, object]:
    return {
        "primitive_family": result.primitive_family,
        "decoder_name": result.decoder_name,
        "decoder_version": result.decoder_version,
        "threshold_version": result.threshold_version,
        "decoder_status": result.decoder_status,
        "data_status": result.data_status,
        "confidence_level": result.confidence_level,
        "fee_source": result.fee_source,
        "route_family": result.route_family,
        "landed": result.landed,
        "landed_slot": result.landed_slot,
        "submitted_slot": result.submitted_slot,
        "slot_delta": result.slot_delta,
        "realized_priority_fee_lamports": (
            result.realized_priority_fee_lamports
        ),
        "realized_jito_tip_lamports": (
            result.realized_jito_tip_lamports
        ),
        "realized_router_fee_lamports": (
            result.realized_router_fee_lamports
        ),
        "error_code": result.error_code,
        "reason_codes": list(result.reason_codes),
        "numeric_features": dict(result.numeric_features),
        "evidence": dict(result.evidence),
        "input_missing_fields": list(result.input_missing_fields),
        "result_hash": result.result_hash,
    }


def _execution_primitive_to_dict(
    primitive: Stage24ExecutionPrimitive,
) -> dict[str, object]:
    return {
        "tx_signature": primitive.tx_signature,
        "slot": primitive.slot,
        "provider_id": primitive.provider_id,
        "observed_at_utc": primitive.observed_at_utc,
        "primitive_family": primitive.primitive_family,
        "fee_source": primitive.fee_source,
        "decoder_status": primitive.decoder_status,
        "data_status": primitive.data_status,
        "confidence_level": primitive.confidence_level,
        "route_family": primitive.route_family,
        "instruction_location": primitive.instruction_location,
        "program_id": primitive.program_id,
        "amount_lamports": primitive.amount_lamports,
        "amount_token": primitive.amount_token,
        "mint": primitive.mint,
        "unit_price_microlamports": primitive.unit_price_microlamports,
        "unit_limit": primitive.unit_limit,
        "reason_codes": list(primitive.reason_codes),
        "numeric_features": dict(primitive.numeric_features),
        "evidence": dict(primitive.evidence),
        "missing_features": list(primitive.missing_features),
        "input_hash": primitive.input_hash,
        "primitive_hash": primitive.primitive_hash,
        "created_at_utc": primitive.created_at_utc,
    }


def _rejection_to_dict(
    rejection: Stage24RejectionRecord,
) -> dict[str, object]:
    return {
        "input_id": rejection.input_id,
        "payload_hash": rejection.payload_hash,
        "decoder_name": rejection.decoder_name,
        "primitive_family": rejection.primitive_family,
        "reason": rejection.reason,
        "error_class": rejection.error_class,
    }


# ---------------------------------------------------------------------------
# Deterministic sort keys
# ---------------------------------------------------------------------------


def _sort_compute_budget(
    rows: tuple[Stage24ComputeBudgetResult, ...],
) -> tuple[Stage24ComputeBudgetResult, ...]:
    return tuple(sorted(rows, key=lambda r: r.result_hash))


def _sort_priority_fee(
    rows: tuple[Stage24PriorityFeeResult, ...],
) -> tuple[Stage24PriorityFeeResult, ...]:
    return tuple(sorted(rows, key=lambda r: r.result_hash))


def _sort_jito_tip(
    rows: tuple[Stage24JitoTipResult, ...],
) -> tuple[Stage24JitoTipResult, ...]:
    return tuple(sorted(rows, key=lambda r: r.result_hash))


def _sort_router_fee(
    rows: tuple[Stage24RouterFeeResult, ...],
) -> tuple[Stage24RouterFeeResult, ...]:
    return tuple(sorted(rows, key=lambda r: r.result_hash))


def _sort_execution_quality(
    rows: tuple[Stage24ExecutionQualityResult, ...],
) -> tuple[Stage24ExecutionQualityResult, ...]:
    return tuple(sorted(rows, key=lambda r: r.result_hash))


def _sort_execution_primitives(
    rows: tuple[Stage24ExecutionPrimitive, ...],
) -> tuple[Stage24ExecutionPrimitive, ...]:
    return tuple(
        sorted(
            rows,
            key=lambda p: (
                p.tx_signature,
                p.primitive_family,
                p.fee_source,
                p.primitive_hash,
            ),
        )
    )


def _sort_rejections(
    rows: tuple[Stage24RejectionRecord, ...],
) -> tuple[Stage24RejectionRecord, ...]:
    return tuple(
        sorted(
            rows,
            key=lambda r: (
                r.input_id,
                r.decoder_name,
                r.primitive_family,
                r.reason,
            ),
        )
    )


# ---------------------------------------------------------------------------
# JSONL body builder
# ---------------------------------------------------------------------------


def _build_jsonl_body(
    rows: Iterable[Mapping[str, object]],
) -> tuple[str, int]:
    """Return ``(canonical_jsonl_body, row_count)``.

    Empty input produces the empty string (zero data rows, no
    trailing newline) which mirrors the Stage 23 empty-artifact
    discipline.
    """
    lines: list[str] = []
    count = 0
    for row in rows:
        _scan_value_for_redaction(row)
        lines.append(canonical_json(row))
        count += 1
    if count == 0:
        return "", 0
    return "\n".join(lines) + "\n", count


# ---------------------------------------------------------------------------
# Coverage CSV body builder
# ---------------------------------------------------------------------------


def _build_coverage_csv_body(
    coverage: Mapping[tuple[str, str, str], int],
) -> tuple[str, int]:
    """Return ``(coverage_csv_body, data_row_count)``.

    Rows are sorted by ``(primitive_family, decoder_status,
    data_status)`` for determinism. The header row is always
    written.
    """
    header = "primitive_family,decoder_status,data_status,row_count\n"
    keys = sorted(coverage.keys())
    body_lines: list[str] = [header]
    for key in keys:
        primitive_family, decoder_status, data_status = key
        body_lines.append(
            f"{primitive_family},{decoder_status},{data_status},"
            f"{coverage[key]}\n"
        )
    return "".join(body_lines), len(keys)


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------


def _build_summary_body(
    *,
    runner_result: Stage24RunnerResult,
    rejection_count: int,
    coverage: Mapping[tuple[str, str, str], int],
    created_at_utc: str,
) -> tuple[str, dict[str, object]]:
    by_decoder_status: dict[str, int] = {}
    by_primitive_family: dict[str, int] = {}
    for key, count in coverage.items():
        primitive_family, decoder_status, _ = key
        by_decoder_status[decoder_status] = (
            by_decoder_status.get(decoder_status, 0) + count
        )
        by_primitive_family[primitive_family] = (
            by_primitive_family.get(primitive_family, 0) + count
        )
    router_candidate_count = sum(
        1
        for r in runner_result.router_fee_results
        if r.decoder_status != DECODER_STATUS_DECODED
    )
    router_confirmed_count = sum(
        1
        for r in runner_result.router_fee_results
        if r.decoder_status == DECODER_STATUS_DECODED
    )
    body: dict[str, object] = {
        "stage_name": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "schema_version": STAGE24_ARTIFACT_SUMMARY_SCHEMA_VERSION,
        "default_schema_version": DEFAULT_SCHEMA_VERSION,
        "observe_only_mode": OBSERVE_ONLY_MODE,
        "created_at_utc": created_at_utc,
        "input_count": runner_result.input_count,
        "compute_budget_result_count": len(
            runner_result.compute_budget_results
        ),
        "priority_fee_result_count": len(
            runner_result.priority_fee_results
        ),
        "jito_tip_result_count": len(runner_result.jito_tip_results),
        "router_fee_result_count": len(
            runner_result.router_fee_results
        ),
        "router_fee_candidate_count": router_candidate_count,
        "router_fee_confirmed_count": router_confirmed_count,
        "execution_quality_result_count": len(
            runner_result.execution_quality_results
        ),
        "execution_primitive_count": len(
            runner_result.execution_primitives
        ),
        "rejection_count": rejection_count,
        "by_decoder_status_count": dict(
            sorted(by_decoder_status.items())
        ),
        "by_primitive_family_count": dict(
            sorted(by_primitive_family.items())
        ),
        "stage_24_5_has_confirmed_router_fee_decoder": (
            STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER
        ),
        "stage_24_5_real_fixture_count": (
            STAGE_24_5_REAL_FIXTURE_COUNT
        ),
        "stage_24_5_confirmed_layout_count": (
            STAGE_24_5_CONFIRMED_LAYOUT_COUNT
        ),
    }
    _scan_value_for_redaction(body)
    return canonical_json(body) + "\n", body


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_manifest_body(
    *,
    artifact_records: tuple[Stage24ArtifactFileRecord, ...],
    created_at_utc: str,
    runner_result: Stage24RunnerResult,
    rejection_count: int,
) -> tuple[str, dict[str, object]]:
    files_list: list[dict[str, object]] = []
    for record in artifact_records:
        files_list.append(
            {
                "file_basename": record.file_basename,
                "sha256": record.sha256,
                "row_count": record.row_count,
                "bytes_written": record.bytes_written,
            }
        )
    body: dict[str, object] = {
        "stage_name": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "schema_version": STAGE24_MANIFEST_SCHEMA_VERSION,
        "default_schema_version": DEFAULT_SCHEMA_VERSION,
        "observe_only_mode": OBSERVE_ONLY_MODE,
        "redaction_confirmed": REDACTION_CONFIRMED_TOKEN,
        "writer_name": STAGE24_ARTIFACT_WRITER_NAME,
        "writer_version": STAGE24_ARTIFACT_WRITER_VERSION,
        "runner_name": STAGE24_RUNNER_NAME,
        "runner_version": STAGE24_RUNNER_VERSION,
        "default_threshold_version": DEFAULT_THRESHOLD_VERSION,
        "created_at_utc": created_at_utc,
        "input_count": runner_result.input_count,
        "rejection_count": rejection_count,
        "files": files_list,
        "stage_24_5_has_confirmed_router_fee_decoder": (
            STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER
        ),
        "stage_24_5_real_fixture_count": (
            STAGE_24_5_REAL_FIXTURE_COUNT
        ),
        "stage_24_5_confirmed_layout_count": (
            STAGE_24_5_CONFIRMED_LAYOUT_COUNT
        ),
        "artifact_filenames": list(ALL_STAGE24_ARTIFACT_FILENAMES),
    }
    _scan_value_for_redaction(body)
    return canonical_json(body) + "\n", body


# ---------------------------------------------------------------------------
# Coverage matrix builder
# ---------------------------------------------------------------------------


def _build_coverage_matrix(
    runner_result: Stage24RunnerResult,
) -> dict[tuple[str, str, str], int]:
    """Count execution primitives by (family, decoder_status, data_status)."""
    matrix: dict[tuple[str, str, str], int] = {}
    for primitive in runner_result.execution_primitives:
        key = (
            primitive.primitive_family,
            primitive.decoder_status,
            primitive.data_status,
        )
        matrix[key] = matrix.get(key, 0) + 1
    return matrix


# ---------------------------------------------------------------------------
# Public writer
# ---------------------------------------------------------------------------


def write_stage24_artifacts(
    *,
    output_dir: Path,
    runner_result: Stage24RunnerResult,
    rejections: tuple[Stage24RejectionRecord, ...] = (),
    created_at_utc: Optional[str] = None,
) -> Stage24ArtifactSet:
    """Write every Stage 24 artifact to ``output_dir`` deterministically.

    Pure function: depends only on arguments. Returns a
    ``Stage24ArtifactSet`` carrying per-file write records and
    the summary counters. Raises ``Stage24WriterError`` on
    contract violations (unsafe path, leak shape, etc.).
    """
    _require_safe_output_directory(output_dir)
    if not isinstance(runner_result, Stage24RunnerResult):
        raise Stage24WriterError(
            "runner_result must be a Stage24RunnerResult"
        )
    if not isinstance(rejections, tuple):
        raise Stage24WriterError("rejections must be a tuple")
    for r in rejections:
        if not isinstance(r, Stage24RejectionRecord):
            raise Stage24WriterError(
                "each rejection must be a Stage24RejectionRecord"
            )
    effective_created_at_utc = (
        created_at_utc
        if created_at_utc is not None
        else runner_result.created_at_utc
    )
    if (
        not isinstance(effective_created_at_utc, str)
        or effective_created_at_utc == ""
    ):
        raise Stage24WriterError(
            "created_at_utc must be a non-empty string"
        )

    for filename in ALL_STAGE24_ARTIFACT_FILENAMES:
        _require_safe_basename(filename)

    # Build sorted, redacted body content for each artifact.
    sorted_compute_budget = _sort_compute_budget(
        runner_result.compute_budget_results
    )
    sorted_priority_fee = _sort_priority_fee(
        runner_result.priority_fee_results
    )
    sorted_jito_tip = _sort_jito_tip(runner_result.jito_tip_results)
    sorted_router_fee_all = _sort_router_fee(
        runner_result.router_fee_results
    )
    router_fee_confirmed = tuple(
        r
        for r in sorted_router_fee_all
        if r.decoder_status == DECODER_STATUS_DECODED
    )
    router_fee_candidates = tuple(
        r
        for r in sorted_router_fee_all
        if r.decoder_status != DECODER_STATUS_DECODED
    )
    sorted_execution_quality = _sort_execution_quality(
        runner_result.execution_quality_results
    )
    sorted_execution_primitives = _sort_execution_primitives(
        runner_result.execution_primitives
    )
    sorted_rejections = _sort_rejections(rejections)

    compute_budget_body, compute_budget_count = _build_jsonl_body(
        _compute_budget_result_to_dict(r) for r in sorted_compute_budget
    )
    priority_fee_body, priority_fee_count = _build_jsonl_body(
        _priority_fee_result_to_dict(r) for r in sorted_priority_fee
    )
    jito_tip_body, jito_tip_count = _build_jsonl_body(
        _jito_tip_result_to_dict(r) for r in sorted_jito_tip
    )
    router_fee_results_body, router_fee_results_count = (
        _build_jsonl_body(
            _router_fee_result_to_dict(r) for r in router_fee_confirmed
        )
    )
    router_fee_candidates_body, router_fee_candidates_count = (
        _build_jsonl_body(
            _router_fee_result_to_dict(r) for r in router_fee_candidates
        )
    )
    execution_quality_body, execution_quality_count = (
        _build_jsonl_body(
            _execution_quality_result_to_dict(r)
            for r in sorted_execution_quality
        )
    )
    execution_primitives_body, execution_primitives_count = (
        _build_jsonl_body(
            _execution_primitive_to_dict(p)
            for p in sorted_execution_primitives
        )
    )
    rejections_body, rejections_count = _build_jsonl_body(
        _rejection_to_dict(r) for r in sorted_rejections
    )

    coverage_matrix = _build_coverage_matrix(runner_result)
    coverage_body, coverage_data_row_count = _build_coverage_csv_body(
        coverage_matrix
    )

    summary_body, _summary_body_dict = _build_summary_body(
        runner_result=runner_result,
        rejection_count=rejections_count,
        coverage=coverage_matrix,
        created_at_utc=effective_created_at_utc,
    )

    # Write every artifact except the manifest (which depends on
    # the per-artifact hashes).
    bodies_for_first_pass: tuple[tuple[str, str, int], ...] = (
        (
            ARTIFACT_FILENAME_SUMMARY,
            summary_body,
            1 if summary_body else 0,
        ),
        (
            ARTIFACT_FILENAME_EXECUTION_PRIMITIVES,
            execution_primitives_body,
            execution_primitives_count,
        ),
        (
            ARTIFACT_FILENAME_COMPUTE_BUDGET_RESULTS,
            compute_budget_body,
            compute_budget_count,
        ),
        (
            ARTIFACT_FILENAME_PRIORITY_FEE_RESULTS,
            priority_fee_body,
            priority_fee_count,
        ),
        (
            ARTIFACT_FILENAME_JITO_TIP_RESULTS,
            jito_tip_body,
            jito_tip_count,
        ),
        (
            ARTIFACT_FILENAME_ROUTER_FEE_RESULTS,
            router_fee_results_body,
            router_fee_results_count,
        ),
        (
            ARTIFACT_FILENAME_ROUTER_FEE_CANDIDATES,
            router_fee_candidates_body,
            router_fee_candidates_count,
        ),
        (
            ARTIFACT_FILENAME_EXECUTION_QUALITY_RESULTS,
            execution_quality_body,
            execution_quality_count,
        ),
        (
            ARTIFACT_FILENAME_DECODER_COVERAGE,
            coverage_body,
            coverage_data_row_count,
        ),
        (
            ARTIFACT_FILENAME_REJECTIONS,
            rejections_body,
            rejections_count,
        ),
    )

    pre_manifest_records: list[Stage24ArtifactFileRecord] = []
    for filename, body, row_count in bodies_for_first_pass:
        path = output_dir / filename
        bytes_written = _atomic_write_text(path=path, body=body)
        encoded = body.encode("utf-8")
        pre_manifest_records.append(
            Stage24ArtifactFileRecord(
                file_basename=filename,
                sha256=_sha256_of_bytes(encoded),
                row_count=row_count,
                bytes_written=bytes_written,
            )
        )

    # Manifest covers the other artifacts; manifest carries its
    # own row_count of 1 (one JSON document).
    manifest_body, _manifest_dict = _build_manifest_body(
        artifact_records=tuple(pre_manifest_records),
        created_at_utc=effective_created_at_utc,
        runner_result=runner_result,
        rejection_count=rejections_count,
    )
    manifest_path = output_dir / ARTIFACT_FILENAME_MANIFEST
    manifest_bytes_written = _atomic_write_text(
        path=manifest_path, body=manifest_body
    )
    manifest_record = Stage24ArtifactFileRecord(
        file_basename=ARTIFACT_FILENAME_MANIFEST,
        sha256=_sha256_of_bytes(manifest_body.encode("utf-8")),
        row_count=1,
        bytes_written=manifest_bytes_written,
    )

    all_records = tuple(
        sorted(
            (manifest_record,) + tuple(pre_manifest_records),
            key=lambda r: r.file_basename,
        )
    )

    summary_counters: dict[str, object] = {
        "input_count": runner_result.input_count,
        "compute_budget_result_count": compute_budget_count,
        "priority_fee_result_count": priority_fee_count,
        "jito_tip_result_count": jito_tip_count,
        "router_fee_result_count": router_fee_results_count,
        "router_fee_candidate_count": router_fee_candidates_count,
        "execution_quality_result_count": execution_quality_count,
        "execution_primitive_count": execution_primitives_count,
        "rejection_count": rejections_count,
        "decoder_coverage_row_count": coverage_data_row_count,
        "schema_version": STAGE24_ARTIFACT_COVERAGE_SCHEMA_VERSION,
    }

    return Stage24ArtifactSet(
        artifact_records=all_records,
        summary_counters=summary_counters,
        created_at_utc=effective_created_at_utc,
        output_dir_name=output_dir.name,
    )


__all__ = [
    "Stage24ArtifactFileRecord",
    "Stage24ArtifactSet",
    "Stage24WriterError",
    "WRITER_NAME",
    "WRITER_VERSION",
    "write_stage24_artifacts",
]
