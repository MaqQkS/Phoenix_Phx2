"""Stage 29.5 migration evidence artifact reader.

Stage 29.5 admits a pre-recorded migration evidence artifact
bundle on disk as a migration evidence source, alongside (and
independent of) the Stage 29.5 Helius WS adapter. The artifact
reader is the only Stage 29.5 production surface that touches
the local filesystem; it never opens a network connection.

The artifact format is one of:

  * a single JSON object encoding one record, OR
  * a JSON array of objects encoding many records, OR
  * a ``.jsonl`` file with one JSON object per line.

Required object keys (mirroring the Helius WS adapter):

  * ``kind``                         -- must equal
                                        ``STAGE29_5_MIGRATION_ARTIFACT_KIND``
  * ``base_mint``                    -- optional safe-shape str
  * ``pool_account``                 -- optional safe-shape str
  * ``pool_program_id``              -- optional safe-shape str
  * ``quote_mint``                   -- optional safe-shape str
  * ``migration_timestamp_utc``      -- optional UTC ISO-8601
  * ``migration_slot``               -- optional non-negative int
  * ``migration_signature``          -- optional str
  * ``source_event_ref``             -- optional str
  * ``observed_at_utc``              -- required UTC ISO-8601
    (the time at which the artifact was originally captured)

The reader:

  * NEVER emits ``migration_source=HELIUS_WS`` (that source is
    the Stage 29.5 Helius WS adapter's surface);
  * NEVER emits ``migration_source=SYNTHETIC_TEST_ONLY``
    (production refuses synthetic-source artifacts to keep the
    test vocabulary strictly out of production data flow);
  * NEVER fabricates an axis value the artifact did not supply;
  * emits ``migration_source=STAGE29_MIGRATION_ARTIFACT`` on every
    successful record;
  * raises :class:`Stage29_5MigrationEvidenceError` when the
    artifact path cannot be read or when a record carries
    ``migration_source=SYNTHETIC_TEST_ONLY``.

Discipline:

  * No env reads.
  * No network. No HTTP. No gRPC. No WebSocket. No socket
    import.
  * No third-party runtime dependency. Imports only stdlib
    (``json`` / ``pathlib`` / ``typing``) plus the Stage 29.5
    models module.
  * No top-level Call (no implicit I/O at import time).
  * No PHX1 import path. No legacy phoenix-1 import path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Tuple

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_STATUS_INVALID,
    MIGRATION_STATUS_PRESENT,
    REFUSAL_REASON_BUDGET_EXCEEDED,
    REFUSAL_REASON_MALFORMED_PAYLOAD,
    REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED,
    REFUSAL_REASON_UNREADABLE_ARTIFACT,
    REFUSAL_REASON_UNSUPPORTED_KIND,
    Stage29_5MigrationEvidenceError,
    Stage29_5MigrationEvidenceRecord,
    is_safe_iso8601_utc_string,
    is_safe_mint_or_pool_string,
)


# ---------------------------------------------------------------------------
# Reader bounds
# ---------------------------------------------------------------------------


STAGE29_5_ARTIFACT_DEFAULT_MAX_RECORDS_PER_CALL: int = 128
STAGE29_5_ARTIFACT_HARD_MAX_RECORDS_PER_CALL: int = 4096


# Expected ``kind`` value carried by every Stage 29.5 migration
# evidence artifact record.
STAGE29_5_MIGRATION_ARTIFACT_KIND: str = "STAGE29_5_MIGRATION"


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


def _resolve_artifact_path(path: object) -> Path:
    if isinstance(path, Path):
        candidate = path
    elif isinstance(path, str):
        candidate = Path(path)
    else:
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_UNREADABLE_ARTIFACT,
            "path must be a str or pathlib.Path",
        )
    if not candidate.exists():
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_UNREADABLE_ARTIFACT,
            "artifact path does not exist",
        )
    if not candidate.is_file():
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_UNREADABLE_ARTIFACT,
            "artifact path is not a regular file",
        )
    return candidate


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------


def _coerce_optional_string(value: object) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return None


def _coerce_optional_nonneg_int(value: object) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _parse_one_record_object(
    obj: Any,
) -> Stage29_5MigrationEvidenceRecord:
    if not isinstance(obj, dict):
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_MALFORMED_PAYLOAD,
            "artifact record is not a JSON object",
        )
    kind_value = obj.get("kind")
    if (
        not isinstance(kind_value, str)
        or kind_value
        != STAGE29_5_MIGRATION_ARTIFACT_KIND
    ):
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_UNSUPPORTED_KIND,
            f"expected kind={STAGE29_5_MIGRATION_ARTIFACT_KIND}; "
            f"got kind={kind_value!r}",
        )
    declared_source = _coerce_optional_string(
        obj.get("migration_source")
    )
    if (
        declared_source
        == MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY
    ):
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED,
            "artifact record declares "
            "migration_source=SYNTHETIC_TEST_ONLY which is not "
            "admitted in production data flow",
        )
    observed_at_utc = _coerce_optional_string(
        obj.get("observed_at_utc")
    )
    if observed_at_utc is None or not (
        is_safe_iso8601_utc_string(observed_at_utc)
    ):
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_MALFORMED_PAYLOAD,
            "artifact record observed_at_utc must be a "
            "UTC-shaped ISO-8601 string",
        )
    base_mint_raw = _coerce_optional_string(
        obj.get("base_mint")
    )
    pool_account_raw = _coerce_optional_string(
        obj.get("pool_account")
    )
    pool_program_id_raw = _coerce_optional_string(
        obj.get("pool_program_id")
    )
    quote_mint_raw = _coerce_optional_string(
        obj.get("quote_mint")
    )
    migration_timestamp_raw = _coerce_optional_string(
        obj.get("migration_timestamp_utc")
    )
    migration_slot_raw = _coerce_optional_nonneg_int(
        obj.get("migration_slot")
    )
    migration_signature_raw = _coerce_optional_string(
        obj.get("migration_signature")
    )
    source_event_ref_raw = _coerce_optional_string(
        obj.get("source_event_ref")
    )
    safe_axes = (
        base_mint_raw
        if (
            base_mint_raw is not None
            and is_safe_mint_or_pool_string(base_mint_raw)
        )
        else None,
        pool_account_raw
        if (
            pool_account_raw is not None
            and is_safe_mint_or_pool_string(pool_account_raw)
        )
        else None,
        pool_program_id_raw
        if (
            pool_program_id_raw is not None
            and is_safe_mint_or_pool_string(
                pool_program_id_raw
            )
        )
        else None,
        quote_mint_raw
        if (
            quote_mint_raw is not None
            and is_safe_mint_or_pool_string(quote_mint_raw)
        )
        else None,
    )
    safe_timestamp = (
        migration_timestamp_raw
        if (
            migration_timestamp_raw is not None
            and is_safe_iso8601_utc_string(
                migration_timestamp_raw
            )
        )
        else None
    )
    quartet_complete = all(
        axis is not None for axis in safe_axes
    )
    if quartet_complete and safe_timestamp is not None:
        return Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_PRESENT,
            migration_source=(
                MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT
            ),
            base_mint=safe_axes[0],
            pool_account=safe_axes[1],
            pool_program_id=safe_axes[2],
            quote_mint=safe_axes[3],
            migration_timestamp_utc=safe_timestamp,
            migration_slot=migration_slot_raw,
            migration_signature=migration_signature_raw,
            observed_at_utc=observed_at_utc,
            source_event_ref=source_event_ref_raw,
        )
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_INVALID,
        migration_source=(
            MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT
        ),
        base_mint=safe_axes[0],
        pool_account=safe_axes[1],
        pool_program_id=safe_axes[2],
        quote_mint=safe_axes[3],
        migration_timestamp_utc=safe_timestamp,
        migration_slot=migration_slot_raw,
        migration_signature=migration_signature_raw,
        observed_at_utc=observed_at_utc,
        source_event_ref=source_event_ref_raw,
    )


# ---------------------------------------------------------------------------
# File parsers (one object / array / jsonl)
# ---------------------------------------------------------------------------


def _read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_UNREADABLE_ARTIFACT,
            "could not read artifact file as utf-8",
        ) from exc


def _is_jsonl_path(path: Path) -> bool:
    return path.suffix.lower() == ".jsonl"


def _iter_jsonl_records(
    text: str,
) -> Tuple[Any, ...]:
    out: list = []
    for line_index, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_MALFORMED_PAYLOAD,
                f"jsonl line {line_index} is not valid JSON",
            ) from exc
        out.append(parsed)
    return tuple(out)


def _iter_json_records(text: str) -> Tuple[Any, ...]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Stage29_5MigrationEvidenceError(
            REFUSAL_REASON_MALFORMED_PAYLOAD,
            "artifact file is not valid JSON",
        ) from exc
    if isinstance(parsed, dict):
        return (parsed,)
    if isinstance(parsed, list):
        return tuple(parsed)
    raise Stage29_5MigrationEvidenceError(
        REFUSAL_REASON_MALFORMED_PAYLOAD,
        "artifact file must contain a JSON object or array of "
        "objects",
    )


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------


class Stage29_5MigrationArtifactReader:
    """Stage 29.5 migration evidence artifact reader.

    Construction takes:

      * an optional ``max_records_per_call`` budget (default 128,
        capped at 4096).

    The reader is stateless across calls; each
    :meth:`read_evidence_from_path` invocation independently
    opens, reads, parses, and closes the artifact file. No
    handle is retained between calls.
    """

    def __init__(
        self,
        max_records_per_call: int = (
            STAGE29_5_ARTIFACT_DEFAULT_MAX_RECORDS_PER_CALL
        ),
    ) -> None:
        if not isinstance(
            max_records_per_call, int
        ) or isinstance(max_records_per_call, bool):
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_BUDGET_EXCEEDED,
                "max_records_per_call must be an int",
            )
        if max_records_per_call < 1:
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_BUDGET_EXCEEDED,
                "max_records_per_call must be >= 1",
            )
        if (
            max_records_per_call
            > STAGE29_5_ARTIFACT_HARD_MAX_RECORDS_PER_CALL
        ):
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_BUDGET_EXCEEDED,
                "max_records_per_call must be <= "
                f"{STAGE29_5_ARTIFACT_HARD_MAX_RECORDS_PER_CALL}",
            )
        self._max_records_per_call: int = max_records_per_call

    def read_evidence_from_path(
        self,
        path: object,
    ) -> Tuple[Stage29_5MigrationEvidenceRecord, ...]:
        """Read up to ``max_records_per_call`` records from the
        supplied artifact path.

        Behavior:

          * ``.jsonl`` extension parses one JSON object per
            non-empty line.
          * Any other extension parses the whole file as a single
            JSON document — a JSON object becomes one record, a
            JSON array becomes many.
          * A malformed file or unreadable path raises
            ``Stage29_5MigrationEvidenceError``.
          * An ``UNSUPPORTED_KIND`` record is silently skipped (a
            mixed bundle that carries non-Stage-29.5-migration
            records is still readable; only matching records are
            emitted).
          * A record declaring
            ``migration_source=SYNTHETIC_TEST_ONLY`` raises
            ``Stage29_5MigrationEvidenceError(REFUSAL_REASON_SYNTHETIC_SOURCE_REJECTED)``.
          * Returns a frozen tuple of evidence records (possibly
            empty).
        """
        artifact_path = _resolve_artifact_path(path)
        text = _read_file_text(artifact_path)
        if _is_jsonl_path(artifact_path):
            objects = _iter_jsonl_records(text)
        else:
            objects = _iter_json_records(text)
        if len(objects) > self._max_records_per_call:
            raise Stage29_5MigrationEvidenceError(
                REFUSAL_REASON_BUDGET_EXCEEDED,
                "artifact carries more records than "
                "max_records_per_call",
            )
        out: list = []
        for obj in objects:
            try:
                record = _parse_one_record_object(obj)
            except Stage29_5MigrationEvidenceError as exc:
                if (
                    exc.refusal_reason
                    == REFUSAL_REASON_UNSUPPORTED_KIND
                ):
                    continue
                raise
            out.append(record)
        return tuple(out)


__all__ = (
    "STAGE29_5_ARTIFACT_DEFAULT_MAX_RECORDS_PER_CALL",
    "STAGE29_5_ARTIFACT_HARD_MAX_RECORDS_PER_CALL",
    "STAGE29_5_MIGRATION_ARTIFACT_KIND",
    "Stage29_5MigrationArtifactReader",
)
