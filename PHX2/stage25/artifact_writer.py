"""Stage 25.6 deterministic artifact writer.

Atomic deterministic writer that emits Stage 25 artifact files into
a caller-supplied output directory and returns a
``Stage25ArtifactManifest`` recording the per-file basename, SHA-256,
row count, and byte count.

Public entry points:

  * ``write_stage25_artifacts``        -- top-level batch writer that
                                          serialises every Stage 25.1-
                                          25.5 tuple, writes the
                                          summary + manifest files,
                                          and returns the artifact
                                          manifest.
  * ``serialize_jsonl_rows``           -- serialise a tuple of
                                          NamedTuple rows into the
                                          canonical Stage 25 JSONL
                                          text.
  * ``write_atomic_text``              -- atomic temp-file write
                                          using ``os.replace``.
  * ``validate_output_dir``            -- safety check that the
                                          caller-supplied output
                                          directory exists and is a
                                          directory.

Determinism / safety rules (Stage 25.6 invariants):

  * Output directory MUST exist before the writer runs; the writer
    never creates arbitrary parent directories.
  * Every file is written via a temp file in the same directory and
    promoted via ``os.replace`` so a partial / interrupted write
    never leaves a half-written artifact behind.
  * Temp filenames are deterministic (``<final-name>.tmp``) so the
    writer's filesystem footprint is reproducible.
  * Every JSONL row is canonical JSON (sorted keys, no whitespace,
    ASCII-safe). Identical input tuples + identical injected
    ``created_at_utc`` produce byte-identical artifacts.
  * Non-empty JSONL files end with a single trailing ``"\\n"``; an
    empty JSONL file is zero bytes (no trailing newline).
  * Summary + manifest JSON files are canonical JSON without a
    trailing newline.
  * Before writing any artifact the writer runs a redaction sweep
    over every row's canonical text. The sweep refuses forbidden
    secret-bearing field names, URL / webhook host substrings, and
    long hex credential shapes; any failure raises
    ``Stage25ManifestError`` and leaves the output directory
    untouched.
  * Manifest entries record ONLY basenames (no absolute paths) and
    are sorted lexicographically by ``file_basename``.

This module imports only stdlib (``json`` / ``hashlib`` /
``pathlib`` / ``os`` / ``types``) plus the Stage 25 constants /
errors / models / manifest / summary surfaces. It does NOT import
Stage 21 / Stage 22 / Stage 23 / Stage 24 production modules, does
NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Mapping, NamedTuple, Optional

from PHX2.stage25.constants import (
    OBSERVE_ONLY_MODE,
    REDACTION_CONFIRMED_TOKEN,
    STAGE25_ARTIFACT_FILENAMES,
    STAGE25_ATH_CANDIDATES_FILENAME,
    STAGE25_ATH_MEASUREMENTS_FILENAME,
    STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS,
    STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS,
    STAGE25_LONG_HEX_RUN_MIN_LEN,
    STAGE25_MANIFEST_FILENAME,
    STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
    STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
    STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
    STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
    STAGE25_RUNNER_NAME,
    STAGE25_RUNNER_VERSION,
    STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
    STAGE25_SUMMARY_FILENAME,
    STAGE25_WRITER_NAME,
    STAGE25_WRITER_VERSION,
    STAGE_NAME,
    STAGE_VERSION,
)
from PHX2.stage25.errors import Stage25ContractError, Stage25ManifestError
from PHX2.stage25.models import (
    Stage25ATHCandidate,
    Stage25ATHMeasurement,
    Stage25MeasurementRejection,
    Stage25MigrationMeasurement,
    Stage25MigrationObservation,
    Stage25PriceWindowObservation,
    Stage25SourceReconciliation,
    canonical_json,
)
from PHX2.stage25.stage25_manifest import (
    SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
    SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
    SELF_REFERENTIAL_MANIFEST_SHA256,
    Stage25ArtifactManifest,
    Stage25ManifestFileEntry,
    artifact_manifest_to_canonical_body,
    build_artifact_manifest,
    build_manifest_file_entry,
    serialize_artifact_manifest,
)
from PHX2.stage25.summary import serialize_stage25_summary


# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------


_HEX_CHARS: str = "0123456789abcdefABCDEF"
_NEWLINE: str = "\n"
_TEMP_SUFFIX: str = ".tmp"


# ---------------------------------------------------------------------------
# Row -> dict serialisation
# ---------------------------------------------------------------------------


def _evidence_to_dict(value: Mapping[str, object]) -> dict[str, object]:
    """Return a plain dict copy of ``value`` for canonical-JSON encoding.

    The canonicalisation in ``canonical_json`` accepts any
    ``Mapping``; this helper converts a ``MappingProxyType`` to a
    plain ``dict`` so the resulting JSON encoding cannot accidentally
    capture a stale ``MappingProxyType`` repr. The inputs are
    never mutated.
    """
    return dict(value)


def _migration_observation_to_dict(
    row: Stage25MigrationObservation,
) -> dict[str, object]:
    return {
        "token_mint": row.token_mint,
        "source_family": row.source_family,
        "source_status": row.source_status,
        "observed_at_utc": row.observed_at_utc,
        "slot": row.slot,
        "block_time": row.block_time,
        "migration_signature": row.migration_signature,
        "migration_pool": row.migration_pool,
        "provider_id": row.provider_id,
        "reason_codes": list(row.reason_codes),
        "evidence": _evidence_to_dict(row.evidence),
        "input_missing_fields": list(row.input_missing_fields),
        "observation_hash": row.observation_hash,
    }


def _migration_measurement_to_dict(
    row: Stage25MigrationMeasurement,
) -> dict[str, object]:
    return {
        "measurement_family": row.measurement_family,
        "measurement_status": row.measurement_status,
        "confidence_level": row.confidence_level,
        "reconciliation_status": row.reconciliation_status,
        "token_mint": row.token_mint,
        "schema_version": row.schema_version,
        "threshold_version": row.threshold_version,
        "measurer_name": row.measurer_name,
        "measurer_version": row.measurer_version,
        "consolidated_slot": row.consolidated_slot,
        "consolidated_block_time": row.consolidated_block_time,
        "reconciled_signature": row.reconciled_signature,
        "selected_source_family": row.selected_source_family,
        "contributing_source_count": row.contributing_source_count,
        "reason_codes": list(row.reason_codes),
        "numeric_features": _evidence_to_dict(row.numeric_features),
        "evidence": _evidence_to_dict(row.evidence),
        "input_missing_fields": list(row.input_missing_fields),
        "measurement_hash": row.measurement_hash,
    }


def _price_window_observation_to_dict(
    row: Stage25PriceWindowObservation,
) -> dict[str, object]:
    return {
        "token_mint": row.token_mint,
        "source_family": row.source_family,
        "source_status": row.source_status,
        "window_kind": row.window_kind,
        "observed_at_utc": row.observed_at_utc,
        "slot": row.slot,
        "block_time": row.block_time,
        "price": row.price,
        "quote_denomination": row.quote_denomination,
        "reason_codes": list(row.reason_codes),
        "evidence": _evidence_to_dict(row.evidence),
        "observation_hash": row.observation_hash,
    }


def _ath_candidate_to_dict(row: Stage25ATHCandidate) -> dict[str, object]:
    return {
        "token_mint": row.token_mint,
        "source_family": row.source_family,
        "source_status": row.source_status,
        "candidate_kind": row.candidate_kind,
        "confidence_level": row.confidence_level,
        "peak_observed_at_utc": row.peak_observed_at_utc,
        "peak_slot": row.peak_slot,
        "peak_block_time": row.peak_block_time,
        "peak_price": row.peak_price,
        "quote_denomination": row.quote_denomination,
        "reason_codes": list(row.reason_codes),
        "evidence": _evidence_to_dict(row.evidence),
        "input_missing_fields": list(row.input_missing_fields),
        "candidate_hash": row.candidate_hash,
    }


def _source_reconciliation_to_dict(
    row: Stage25SourceReconciliation,
) -> dict[str, object]:
    if row.disagreement_metric is None:
        metric: Optional[dict[str, object]] = None
    else:
        metric = _evidence_to_dict(row.disagreement_metric)
    return {
        "measurement_family": row.measurement_family,
        "reconciliation_status": row.reconciliation_status,
        "confidence_level": row.confidence_level,
        "token_mint": row.token_mint,
        "source_families": list(row.source_families),
        "contributing_source_count": row.contributing_source_count,
        "disagreeing_source_count": row.disagreeing_source_count,
        "disagreement_metric": metric,
        "reason_codes": list(row.reason_codes),
        "evidence": _evidence_to_dict(row.evidence),
        "reconciliation_hash": row.reconciliation_hash,
    }


def _ath_measurement_to_dict(
    row: Stage25ATHMeasurement,
) -> dict[str, object]:
    return {
        "measurement_family": row.measurement_family,
        "measurement_status": row.measurement_status,
        "confidence_level": row.confidence_level,
        "reconciliation_status": row.reconciliation_status,
        "token_mint": row.token_mint,
        "schema_version": row.schema_version,
        "threshold_version": row.threshold_version,
        "measurer_name": row.measurer_name,
        "measurer_version": row.measurer_version,
        "consolidated_peak_slot": row.consolidated_peak_slot,
        "consolidated_peak_block_time": row.consolidated_peak_block_time,
        "consolidated_peak_price": row.consolidated_peak_price,
        "quote_denomination": row.quote_denomination,
        "peak_source_family": row.peak_source_family,
        "reconciled_peak_observed_at_utc": (
            row.reconciled_peak_observed_at_utc
        ),
        "time_to_peak_seconds": row.time_to_peak_seconds,
        "contributing_source_count": row.contributing_source_count,
        "reason_codes": list(row.reason_codes),
        "numeric_features": _evidence_to_dict(row.numeric_features),
        "evidence": _evidence_to_dict(row.evidence),
        "input_missing_fields": list(row.input_missing_fields),
        "measurement_hash": row.measurement_hash,
    }


def _measurement_rejection_to_dict(
    row: Stage25MeasurementRejection,
) -> dict[str, object]:
    return {
        "rejection_reason": row.rejection_reason,
        "token_mint": row.token_mint,
        "source_family": row.source_family,
        "detail": row.detail,
        "reason_codes": list(row.reason_codes),
    }


def _row_to_dict(row: object) -> dict[str, object]:
    if isinstance(row, Stage25MigrationObservation):
        return _migration_observation_to_dict(row)
    if isinstance(row, Stage25MigrationMeasurement):
        return _migration_measurement_to_dict(row)
    if isinstance(row, Stage25PriceWindowObservation):
        return _price_window_observation_to_dict(row)
    if isinstance(row, Stage25ATHCandidate):
        return _ath_candidate_to_dict(row)
    if isinstance(row, Stage25SourceReconciliation):
        return _source_reconciliation_to_dict(row)
    if isinstance(row, Stage25ATHMeasurement):
        return _ath_measurement_to_dict(row)
    if isinstance(row, Stage25MeasurementRejection):
        return _measurement_rejection_to_dict(row)
    raise Stage25ContractError(
        "serialize_jsonl_rows: unsupported row type "
        f"{type(row).__name__}"
    )


def serialize_jsonl_rows(rows: tuple[object, ...]) -> str:
    """Return the canonical JSONL text for ``rows``.

    Each row is canonical JSON; rows are joined by ``"\\n"`` and the
    result ends with a single trailing ``"\\n"`` when ``rows`` is
    non-empty. An empty input produces the empty string so the writer
    can record a zero-byte JSONL artifact deterministically.
    """
    if not isinstance(rows, tuple):
        raise Stage25ContractError(
            "serialize_jsonl_rows: rows must be a tuple"
        )
    if not rows:
        return ""
    lines = [canonical_json(_row_to_dict(row)) for row in rows]
    return _NEWLINE.join(lines) + _NEWLINE


# ---------------------------------------------------------------------------
# Redaction sweep
# ---------------------------------------------------------------------------


def _has_long_hex_run(s: str) -> bool:
    run = 0
    for ch in s:
        if ch in _HEX_CHARS:
            run += 1
            if run >= STAGE25_LONG_HEX_RUN_MIN_LEN:
                return True
        else:
            run = 0
    return False


def _string_carries_forbidden_value_substring(value: str) -> bool:
    """Return True iff ``value`` carries a forbidden URL / webhook /
    secret-bearing-as-value substring.

    The check looks for:

      * any ``STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS`` substring
        (URL schemes, webhook host literals); AND
      * any ``STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS`` substring
        embedded inside the value itself (e.g. an evidence string
        ``"contains api_key_payload"`` is a leak even when no field
        name carries the forbidden substring).
    """
    lower = value.lower()
    for forbidden in STAGE25_FORBIDDEN_INPUT_VALUE_SUBSTRINGS:
        if forbidden in lower:
            return True
    for forbidden in STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
        if forbidden in lower:
            return True
    return False


def _field_name_is_secret_bearing(name: str) -> bool:
    lower = name.lower()
    for forbidden in STAGE25_FORBIDDEN_INPUT_FIELD_SUBSTRINGS:
        if forbidden in lower:
            return True
    return False


# Field-name suffixes that hold a deterministic Stage 25 hash digest.
# Hash values are 64-character hex strings by construction; the
# long-hex-run scan must therefore skip these fields so a legitimate
# digest does not look like a leaked credential. The hash-field
# allowlist intentionally does NOT include the broad bare ``"hash"``
# suffix because that would let an attacker bypass the long-hex
# check by naming a leak field e.g. ``token_secret_for_hash`` --
# only the explicit ``_hash`` / ``_sha256`` underscore-bounded
# suffixes are honoured.
_HASH_FIELD_SUFFIXES: tuple[str, ...] = (
    "_hash",
    "_sha256",
)


# Field names known to hold sha256 hex digests in nested evidence
# bodies. Scanned fields that exactly match one of these names skip
# the long-hex-run check (but NOT the URL / webhook / secret-bearing
# value check).
_HASH_FIELD_EXACT_NAMES: frozenset[str] = frozenset(
    {
        "candidate_hash",
        "candidate_hashes",
        "contributor_candidate_hashes",
        "measurement_hash",
        "migration_measurement_hash",
        "observation_hash",
        "reconciliation_hash",
        "selected_observation_hash",
        "sha256",
        "source_observation_hash",
        "window_observation_hashes",
    }
)


def _is_hash_field(field_path: str) -> bool:
    """Return True iff ``field_path``'s leaf name is a known hash field.

    The leaf name is the final ``"."``-separated segment with any
    trailing ``"[i]"`` index stripped.

    A "hash field" only earns relaxation of the long-hex-run check.
    The leaf name still must not contain a forbidden secret-bearing
    substring (caught at the parent-mapping iteration); hash-named
    leak fields like ``secret_hash`` / ``api_key_hash`` / ``webhook_hash``
    are therefore rejected by the field-name scan before they reach
    this predicate.
    """
    leaf = field_path.rsplit(".", 1)[-1]
    leaf = leaf.split("[", 1)[0]
    if leaf in _HASH_FIELD_EXACT_NAMES:
        return True
    for suffix in _HASH_FIELD_SUFFIXES:
        if leaf.endswith(suffix):
            return True
    return False


def _scan_value_for_leaks(value: object, field_path: str) -> None:
    """Recursively scan ``value`` for leak shapes.

    Stage 25.6 redaction discipline:

      * Mapping KEYS always get the forbidden-field-name scan, at
        every nesting level. This catches both top-level
        ``{"api_key": "..."}`` and nested
        ``{"evidence": {"api_key": "..."}}`` leaks.
      * Mapping KEYS named ``secret_hash`` / ``api_key_hash`` /
        ``webhook_hash`` / ... are rejected by the field-name scan
        before the hash-field allowlist ever applies.
      * String VALUES always get the URL / webhook / secret-bearing
        value substring scan, regardless of whether the field is in
        the hash allowlist. URL / webhook leaks inside a
        ``foo_hash`` field are rejected.
      * Hash-field allowlist relaxes ONLY the long-hex-run check,
        because legitimate sha256 digests look like long-hex
        credentials.

    Raises ``Stage25ManifestError`` on any detected leak.
    """
    if isinstance(value, str):
        # Always run the URL / webhook / secret-bearing-value scan.
        if _string_carries_forbidden_value_substring(value):
            raise Stage25ManifestError(
                f"redaction sweep: field {field_path!r} value carries a "
                "leak-shape substring"
            )
        # Hash-field allowlist relaxes only the long-hex check.
        if not _is_hash_field(field_path):
            if _has_long_hex_run(value):
                raise Stage25ManifestError(
                    f"redaction sweep: field {field_path!r} value "
                    "carries a long-hex credential shape"
                )
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise Stage25ManifestError(
                    f"redaction sweep: field {field_path!r} has a "
                    "non-string nested key"
                )
            if _field_name_is_secret_bearing(key):
                raise Stage25ManifestError(
                    f"redaction sweep: nested field {key!r} under "
                    f"{field_path!r} carries a forbidden "
                    "secret-bearing substring"
                )
            _scan_value_for_leaks(nested, f"{field_path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_value_for_leaks(item, f"{field_path}[{index}]")
        return
    # Primitive scalars (int / bool / float / None) need no scan.


def _redaction_sweep_row(row: object) -> None:
    body = _row_to_dict(row)
    _scan_value_for_leaks(body, type(row).__name__)


def _redaction_sweep_mapping(
    *,
    mapping: Mapping[str, object],
    label: str,
) -> None:
    if not isinstance(mapping, Mapping):
        raise Stage25ManifestError(
            f"redaction sweep: {label} must be a mapping"
        )
    _scan_value_for_leaks(mapping, label)


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


def validate_output_dir(output_dir: Path) -> None:
    """Raise ``Stage25ManifestError`` unless ``output_dir`` exists and is a directory.

    The writer never creates parent directories itself; the caller
    must arrange the output directory before invoking the writer.
    """
    if not isinstance(output_dir, Path):
        raise Stage25ManifestError(
            "output_dir must be a pathlib.Path"
        )
    if not output_dir.exists():
        raise Stage25ManifestError(
            f"output_dir does not exist: {output_dir.name!r}"
        )
    if not output_dir.is_dir():
        raise Stage25ManifestError(
            f"output_dir is not a directory: {output_dir.name!r}"
        )


def write_atomic_text(path: Path, text: str) -> int:
    """Write ``text`` to ``path`` atomically via a sibling temp file.

    Returns the byte count of the encoded UTF-8 text. The writer
    encodes ``text`` once, writes it to ``<path>.tmp`` in the same
    parent directory, and then promotes the temp file via
    ``os.replace`` so a partial / interrupted write never leaves a
    half-written artifact in place. If the encoded text differs from
    the on-disk bytes after replacement the writer raises
    ``Stage25ManifestError``.
    """
    if not isinstance(path, Path):
        raise Stage25ManifestError(
            "write_atomic_text: path must be a pathlib.Path"
        )
    if not isinstance(text, str):
        raise Stage25ManifestError(
            "write_atomic_text: text must be a string"
        )
    encoded = text.encode("utf-8")
    temp_path = path.with_name(path.name + _TEMP_SUFFIX)
    try:
        with path.parent.joinpath(temp_path.name).open("wb") as handle:
            handle.write(encoded)
    except OSError as exc:
        # Clean up a half-written temp file then re-raise as typed
        # error so the writer never leaves a stray temp file behind.
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        raise Stage25ManifestError(
            f"write_atomic_text: failed to write {path.name!r}"
        ) from exc
    os.replace(temp_path, path)
    return len(encoded)


# ---------------------------------------------------------------------------
# Manifest assembly
# ---------------------------------------------------------------------------


class _ArtifactRecord(NamedTuple):
    """Internal record describing one Stage 25 artifact file.

    Tracks the basename, the encoded text written to disk, the row
    count, and the SHA-256 / byte-count derived after the bytes are
    promoted via ``os.replace``.
    """

    basename: str
    text: str
    row_count: int


def _stage24_pin_from_strings(
    stage24_manifest_basename: str,
    stage24_manifest_sha256: str,
) -> tuple[Optional[str], Optional[str]]:
    """Return ``(basename, sha256)`` tuples honoring the empty-string sentinel.

    The Stage 25 input manifest pin accepts ``None`` for "no pin" and
    rejects partial pins. The writer accepts empty strings on the
    public surface and converts them to ``None`` before delegating
    to ``build_artifact_manifest``.
    """
    basename = (
        stage24_manifest_basename
        if stage24_manifest_basename != ""
        else None
    )
    sha256 = (
        stage24_manifest_sha256 if stage24_manifest_sha256 != "" else None
    )
    return basename, sha256


def _build_artifact_entry(
    *,
    basename: str,
    sha256: str,
    row_count: int,
    byte_count: int,
) -> Stage25ManifestFileEntry:
    return build_manifest_file_entry(
        file_basename=basename,
        sha256=sha256,
        row_count=row_count,
        byte_count=byte_count,
    )


def _validate_summary_row_counts(
    *,
    summary: Mapping[str, object],
    expected_counts: Mapping[str, int],
) -> None:
    """Raise ``Stage25ManifestError`` if ``summary["row_counts"]`` does
    not match the actual artifact tuple lengths.

    The writer refuses to emit a summary that misreports the row
    counts of its sibling artifacts. ``expected_counts`` is the
    {artifact_label: actual_len} mapping derived from the runtime
    tuple inputs.
    """
    raw = summary.get("row_counts")
    if not isinstance(raw, Mapping):
        raise Stage25ManifestError(
            "summary['row_counts'] must be a mapping"
        )
    for label, expected in expected_counts.items():
        actual = raw.get(label)
        if actual != expected:
            raise Stage25ManifestError(
                f"summary['row_counts'][{label!r}] = {actual!r} does "
                f"not match the actual artifact length {expected!r}"
            )


def _validate_stage24_pin_strings(
    *,
    stage24_manifest_basename: str,
    stage24_manifest_sha256: str,
) -> None:
    """Validate the Stage 24 pin strings BEFORE any artifact is written.

    Empty strings on both arguments mean "no pin". Supplying exactly
    one raises; supplying both runs full basename / sha256 safety
    checks (via ``build_stage24_manifest_pin``) so a malformed pin
    fails before any file is touched.
    """
    if not isinstance(stage24_manifest_basename, str):
        raise Stage25ManifestError(
            "stage24_manifest_basename must be a string"
        )
    if not isinstance(stage24_manifest_sha256, str):
        raise Stage25ManifestError(
            "stage24_manifest_sha256 must be a string"
        )
    if (stage24_manifest_basename == "") != (
        stage24_manifest_sha256 == ""
    ):
        raise Stage25ManifestError(
            "Stage 24 manifest pin requires both basename and sha256 "
            "or neither"
        )
    if stage24_manifest_basename == "":
        return
    # Delegate to the safe-basename / safe-sha256 checks inside the
    # manifest module. The pin builder raises a typed
    # Stage25ManifestError on any malformed input.
    from PHX2.stage25.stage25_manifest import build_stage24_manifest_pin

    build_stage24_manifest_pin(
        upstream_manifest_basename=stage24_manifest_basename,
        upstream_manifest_sha256=stage24_manifest_sha256,
    )


# ---------------------------------------------------------------------------
# Top-level writer
# ---------------------------------------------------------------------------


def write_stage25_artifacts(
    output_dir: Path,
    *,
    migration_observations: tuple[Stage25MigrationObservation, ...],
    migration_measurements: tuple[Stage25MigrationMeasurement, ...],
    price_window_observations: tuple[Stage25PriceWindowObservation, ...],
    ath_candidates: tuple[Stage25ATHCandidate, ...],
    source_reconciliations: tuple[Stage25SourceReconciliation, ...],
    ath_measurements: tuple[Stage25ATHMeasurement, ...],
    rejections: tuple[Stage25MeasurementRejection, ...],
    summary: Mapping[str, object],
    created_at_utc: str,
    stage24_manifest_basename: str = "",
    stage24_manifest_sha256: str = "",
) -> Stage25ArtifactManifest:
    """Write Stage 25 artifact files atomically and return the manifest.

    Stage 25.6 ordering invariant: every validation runs BEFORE any
    bytes hit disk. If any validation fails the output directory is
    left untouched, never partially written. The validation pipeline:

      1. ``output_dir`` exists and is a directory.
      2. ``created_at_utc`` is a non-empty string.
      3. Every input tuple is a tuple of the expected record type.
      4. ``summary`` is a mapping and its ``row_counts`` field
         matches the actual artifact tuple lengths.
      5. Stage 24 pin strings (both empty or both present-and-safe).
      6. Redaction sweep over every row + the summary mapping.
      7. Redaction sweep over the assembled artifact manifest body
         (so caller-supplied ``created_at_utc`` / Stage 24 pin
         strings cannot smuggle a leak into the manifest).

    Only after every check passes does the writer perform the
    atomic per-file writes (JSONL artifacts, then summary, then
    manifest). The manifest's own self-entry uses the
    ``SELF_REFERENTIAL_MANIFEST_SHA256`` sentinel and ``-1``
    byte_count by Stage 25.6 convention: the manifest cannot
    record the true hash of its own bytes without breaking the
    self-referential hash chain.
    """
    # 1. output_dir
    validate_output_dir(output_dir)
    # 2. created_at_utc
    if not isinstance(created_at_utc, str) or created_at_utc == "":
        raise Stage25ManifestError(
            "created_at_utc must be a non-empty string"
        )
    # 3. tuple types
    _require_tuple_of(
        "migration_observations",
        migration_observations,
        Stage25MigrationObservation,
    )
    _require_tuple_of(
        "migration_measurements",
        migration_measurements,
        Stage25MigrationMeasurement,
    )
    _require_tuple_of(
        "price_window_observations",
        price_window_observations,
        Stage25PriceWindowObservation,
    )
    _require_tuple_of(
        "ath_candidates",
        ath_candidates,
        Stage25ATHCandidate,
    )
    _require_tuple_of(
        "source_reconciliations",
        source_reconciliations,
        Stage25SourceReconciliation,
    )
    _require_tuple_of(
        "ath_measurements",
        ath_measurements,
        Stage25ATHMeasurement,
    )
    _require_tuple_of(
        "rejections",
        rejections,
        Stage25MeasurementRejection,
    )
    if not isinstance(summary, Mapping):
        raise Stage25ManifestError(
            "summary must be a mapping"
        )

    # 4. Summary row_counts must match actual tuple lengths.
    expected_counts: Mapping[str, int] = {
        "migration_observations": len(migration_observations),
        "migration_measurements": len(migration_measurements),
        "price_window_observations": len(price_window_observations),
        "ath_candidates": len(ath_candidates),
        "source_reconciliations": len(source_reconciliations),
        "ath_measurements": len(ath_measurements),
        "rejections": len(rejections),
    }
    _validate_summary_row_counts(
        summary=summary, expected_counts=expected_counts
    )

    # 5. Stage 24 pin (validated before any artifact bytes hit disk).
    _validate_stage24_pin_strings(
        stage24_manifest_basename=stage24_manifest_basename,
        stage24_manifest_sha256=stage24_manifest_sha256,
    )

    # 6. Redaction sweep over rows + summary.
    for row in migration_observations:
        _redaction_sweep_row(row)
    for row in migration_measurements:
        _redaction_sweep_row(row)
    for row in price_window_observations:
        _redaction_sweep_row(row)
    for row in ath_candidates:
        _redaction_sweep_row(row)
    for row in source_reconciliations:
        _redaction_sweep_row(row)
    for row in ath_measurements:
        _redaction_sweep_row(row)
    for row in rejections:
        _redaction_sweep_row(row)
    _redaction_sweep_mapping(mapping=summary, label="summary")

    # All validations passed. Pre-compute every artifact's text and
    # digest so the atomic-write phase only touches files after we
    # know the writes will succeed.
    jsonl_artifacts: tuple[_ArtifactRecord, ...] = (
        _ArtifactRecord(
            basename=STAGE25_MIGRATION_OBSERVATIONS_FILENAME,
            text=serialize_jsonl_rows(migration_observations),
            row_count=len(migration_observations),
        ),
        _ArtifactRecord(
            basename=STAGE25_MIGRATION_MEASUREMENTS_FILENAME,
            text=serialize_jsonl_rows(migration_measurements),
            row_count=len(migration_measurements),
        ),
        _ArtifactRecord(
            basename=STAGE25_PRICE_WINDOW_OBSERVATIONS_FILENAME,
            text=serialize_jsonl_rows(price_window_observations),
            row_count=len(price_window_observations),
        ),
        _ArtifactRecord(
            basename=STAGE25_ATH_CANDIDATES_FILENAME,
            text=serialize_jsonl_rows(ath_candidates),
            row_count=len(ath_candidates),
        ),
        _ArtifactRecord(
            basename=STAGE25_SOURCE_RECONCILIATIONS_FILENAME,
            text=serialize_jsonl_rows(source_reconciliations),
            row_count=len(source_reconciliations),
        ),
        _ArtifactRecord(
            basename=STAGE25_ATH_MEASUREMENTS_FILENAME,
            text=serialize_jsonl_rows(ath_measurements),
            row_count=len(ath_measurements),
        ),
        _ArtifactRecord(
            basename=STAGE25_MEASUREMENT_REJECTIONS_FILENAME,
            text=serialize_jsonl_rows(rejections),
            row_count=len(rejections),
        ),
    )

    summary_text = serialize_stage25_summary(summary)

    # Build the manifest entries for non-manifest files using the
    # pre-computed texts.
    entries: list[Stage25ManifestFileEntry] = []
    for artifact in jsonl_artifacts:
        encoded = artifact.text.encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        entries.append(
            _build_artifact_entry(
                basename=artifact.basename,
                sha256=digest,
                row_count=artifact.row_count,
                byte_count=len(encoded),
            )
        )
    summary_encoded = summary_text.encode("utf-8")
    summary_digest = hashlib.sha256(summary_encoded).hexdigest()
    entries.append(
        _build_artifact_entry(
            basename=STAGE25_SUMMARY_FILENAME,
            sha256=summary_digest,
            row_count=-1,
            byte_count=len(summary_encoded),
        )
    )

    # Self-referential manifest entry: locked sentinel SHA-256 +
    # ``-1`` byte_count by Stage 25.6 convention.
    entries.append(
        _build_artifact_entry(
            basename=STAGE25_MANIFEST_FILENAME,
            sha256=SELF_REFERENTIAL_MANIFEST_SHA256,
            row_count=SELF_REFERENTIAL_MANIFEST_ROW_COUNT,
            byte_count=SELF_REFERENTIAL_MANIFEST_BYTE_COUNT,
        )
    )

    pin_basename, pin_sha256 = _stage24_pin_from_strings(
        stage24_manifest_basename, stage24_manifest_sha256
    )
    manifest = build_artifact_manifest(
        files=tuple(entries),
        created_at_utc=created_at_utc,
        redaction_confirmed=REDACTION_CONFIRMED_TOKEN,
        upstream_manifest_basename=pin_basename,
        upstream_manifest_sha256=pin_sha256,
        runner_name=STAGE25_RUNNER_NAME,
        runner_version=STAGE25_RUNNER_VERSION,
        writer_name=STAGE25_WRITER_NAME,
        writer_version=STAGE25_WRITER_VERSION,
    )
    # 7. Redaction sweep over the manifest body BEFORE serialisation
    # /writing. This catches a leak in caller-supplied
    # ``created_at_utc`` / Stage 24 pin strings even though the
    # earlier sweeps did not touch the assembled manifest body.
    _redaction_sweep_mapping(
        mapping=artifact_manifest_to_canonical_body(manifest),
        label="artifact_manifest",
    )
    manifest_text = serialize_artifact_manifest(manifest)

    # All validations have passed. Perform the atomic writes.
    for artifact in jsonl_artifacts:
        artifact_path = output_dir / artifact.basename
        written = write_atomic_text(artifact_path, artifact.text)
        if written != len(artifact.text.encode("utf-8")):
            raise Stage25ManifestError(
                f"byte_count mismatch for {artifact.basename!r}"
            )
    summary_path = output_dir / STAGE25_SUMMARY_FILENAME
    summary_written = write_atomic_text(summary_path, summary_text)
    if summary_written != len(summary_text.encode("utf-8")):
        raise Stage25ManifestError(
            f"byte_count mismatch for {STAGE25_SUMMARY_FILENAME!r}"
        )
    manifest_path = output_dir / STAGE25_MANIFEST_FILENAME
    write_atomic_text(manifest_path, manifest_text)
    return manifest


def _require_tuple_of(
    field_name: str,
    value: object,
    expected_type: type,
) -> None:
    if not isinstance(value, tuple):
        raise Stage25ManifestError(f"{field_name} must be a tuple")
    for entry in value:
        if not isinstance(entry, expected_type):
            raise Stage25ManifestError(
                f"{field_name} must contain only {expected_type.__name__} "
                "records"
            )


def writer_identity() -> Mapping[str, str]:
    """Return the writer identity tokens (name / version / stage)."""
    return {
        "writer_name": STAGE25_WRITER_NAME,
        "writer_version": STAGE25_WRITER_VERSION,
        "stage_name": STAGE_NAME,
        "stage_version": STAGE_VERSION,
        "observe_only_mode": OBSERVE_ONLY_MODE,
    }


__all__ = [
    "STAGE25_ARTIFACT_FILENAMES",
    "serialize_jsonl_rows",
    "validate_output_dir",
    "write_atomic_text",
    "write_stage25_artifacts",
    "writer_identity",
]
