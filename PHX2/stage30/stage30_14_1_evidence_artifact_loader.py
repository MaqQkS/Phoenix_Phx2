"""Stage 30.14.1 Build 26.1 evidence-artifact loader.

Build #26, substage 30.14.1. The ONLY filesystem-touching Stage 30.14.1 production surface:
a bounded, read-only, fail-closed loader that reads a persisted
``build26_capture_evidence.jsonl`` artifact (SYNTHETIC fixtures only in this slice; a real
Build 26.1B capture is deferred and never copied into the repo), validates the locked
15-field Build 26.1 capture-evidence schema line by line, and reconstructs a
``Stage29_5MigrationEvidenceRecord`` for each ACCEPTED line WITHOUT fabricating any axis the
artifact did not supply. The reconstructed records (the accepted set) are exactly what the
committed Stage 30.14.0 replay seam (driven by the Stage 30.14.1 verifier sibling) consumes.

The loader FABRICATES nothing: every reconstructed record field is sourced from an explicit,
present, validated JSONL field; a missing required axis fails the line closed (it is never
defaulted into existence). It carries the migration anchor + observed timestamp VERBATIM
(never reformats a value into a passing one). The committed
``Stage29_5MigrationEvidenceRecord.__post_init__`` validator is the backstop: an incomplete
PRESENT record can never be constructed.

Two failure tiers:

  * a STRUCTURAL fault (unreadable path / oversized file / too-many lines / too-many
    accepted records / malformed JSONL line / wrong artifact schema_version / out-of-bounds
    caller cap) makes the whole artifact untrustworthy and RAISES
    ``Stage30_14_1EvidenceLoadError`` carrying a closed-set reason -- never a raw payload or
    secret;
  * a per-line CONTENT fault (missing field / non-PRESENT / invalid source / unsafe axis
    shape / non-pump mint / malformed timestamp / bad source_ref / incomplete measurement /
    unsafe redaction / non-empty warnings / duplicate mint or signature) is recorded as a
    REJECTED load outcome and excluded from the accepted set (default), so the artifact's
    VALID lines still load. Constructed with ``strict=True``, a per-line content fault RAISES
    instead (carrying the same closed-set reason).

The byte cap is enforced against the file size BEFORE the file is read into memory. The
loader opens NO network connection, reads NO process environment, reads NO wall clock
(``created_at_utc`` is caller-injected), reserves NO dispatch, sends NO message, touches NO
durable ledger, WRITES no file (read-only filesystem access only -- ``Path`` / ``.exists`` /
``.is_file`` / ``.stat`` / ``.read_text``), runs NO daemon / ``while`` loop, and edits NO
committed Stage 29 / Stage 30 production file.

Discipline:

  * Stdlib only (``json`` / ``pathlib`` / ``typing``) -- the relaxed Stage 30.14.1 LOADER
    tier (read-only filesystem). No ``os`` (no env read), no ``datetime`` / ``time`` (no
    clock), no network / socket / db / compression.
  * Imports ONLY the Stage 30.14.1 models sibling + the committed Stage 29.5
    migration-models module (the SCOPED discovery-currency deviation -- the record type +
    closed-set tokens + safe-shape validators + closed-set capture error). No other Stage
    21-29 import (no Birdeye, no Stage 27 / 28); no transport / dispatch / runner /
    durable-ledger / real-send-guard import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No filesystem WRITE surface (no ``.write_text`` / ``.write_bytes`` / ``.mkdir`` and no
    bare builtin file-open call); no live provider, transport-destination, url, or host
    reference; no wallet / signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional, Tuple

from PHX2.stage29.stage29_5_migration_models import (
    MEASUREMENT_STATUS_COMPLETE,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_PRESENT,
    REDACTION_STATUS_SAFE,
    Stage29_5MigrationEvidenceRecord,
    is_safe_iso8601_utc_string,
    is_safe_mint_or_pool_string,
    is_stage29_5_migration_source_value,
)
from PHX2.stage30.stage30_14_1_evidence_artifact_models import (
    BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION,
    BUILD26_1_REQUIRED_FIELDS,
    LOAD_DECISION_ACCEPTED,
    LOAD_DECISION_REJECTED,
    LOAD_ERROR_FILE_TOO_LARGE,
    LOAD_ERROR_INVALID_CAP,
    LOAD_ERROR_MALFORMED_JSONL_LINE,
    LOAD_ERROR_TOO_MANY_LINES,
    LOAD_ERROR_TOO_MANY_RECORDS,
    LOAD_ERROR_UNREADABLE_ARTIFACT,
    LOAD_ERROR_WRONG_SCHEMA_VERSION,
    LOAD_REASON_ACCEPTED_FRESH_EVIDENCE,
    LOAD_REASON_BAD_SOURCE_REF,
    LOAD_REASON_DUPLICATE_MINT,
    LOAD_REASON_DUPLICATE_SIGNATURE,
    LOAD_REASON_INCOMPLETE_MEASUREMENT,
    LOAD_REASON_INVALID_SOURCE,
    LOAD_REASON_MALFORMED_TIMESTAMP,
    LOAD_REASON_MISSING_REQUIRED_FIELD,
    LOAD_REASON_NONEMPTY_WARNINGS,
    LOAD_REASON_NON_PRESENT_STATUS,
    LOAD_REASON_NOT_PUMP_SUFFIX,
    LOAD_REASON_UNSAFE_AXIS_SHAPE,
    LOAD_REASON_UNSAFE_REDACTION,
    STAGE30_14_1_DEFAULT_MAX_ACCEPTED,
    STAGE30_14_1_DEFAULT_MAX_BYTES,
    STAGE30_14_1_DEFAULT_MAX_LINES,
    STAGE30_14_1_REDACTION_STATUS_REDACTED,
    STAGE30_14_1_REDACTION_STATUS_VIOLATION,
    Stage30_14_1EvidenceLoadOutcome,
    Stage30_14_1EvidenceLoadResult,
    Stage30_14_1EvidenceLoadSummary,
    Stage30_14_1PersistedAttestation,
    are_strings_redaction_safe,
    build_expected_source_ref,
    is_load_error_reason,
    is_load_reason,
    is_nonblank_str,
    is_pump_suffix_mint,
    is_within_accepted_cap,
    is_within_byte_cap,
    is_within_line_cap,
    safe_echo,
)


# ---------------------------------------------------------------------------
# Closed-set load error
# ---------------------------------------------------------------------------


class Stage30_14_1EvidenceLoadError(Exception):
    """Closed-set Stage 30.14.1 evidence-load error.

    Raised for a STRUCTURAL fault (unreadable / oversized / too-many lines / too-many
    accepted records / malformed JSONL line / wrong artifact schema_version / out-of-bounds
    caller cap), and -- when the loader is constructed with ``strict=True`` -- for a per-line
    CONTENT fault as well. Carries ONLY a closed-set reason token (a structural load-error
    reason or a per-line load reject reason) + a short safe-to-display detail; never a raw
    payload, a raw URL, a raw mint, or any secret value.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        if not (is_load_error_reason(reason) or is_load_reason(reason)):
            raise ValueError(
                "Stage30_14_1EvidenceLoadError reason must be a closed-set "
                f"token; got {reason!r}"
            )
        if not isinstance(detail, str):
            raise ValueError(
                "Stage30_14_1EvidenceLoadError detail must be a string"
            )
        self.reason: str = reason
        self.detail: str = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


# ---------------------------------------------------------------------------
# Path validation (read-only)
# ---------------------------------------------------------------------------


def _resolve_artifact_path(path: object) -> Path:
    """Resolve ``path`` to an existing regular file, read-only. Raises
    ``Stage30_14_1EvidenceLoadError(UNREADABLE_ARTIFACT)`` on any failure.
    """
    if isinstance(path, Path):
        candidate = path
    elif isinstance(path, str):
        candidate = Path(path)
    else:
        raise Stage30_14_1EvidenceLoadError(
            LOAD_ERROR_UNREADABLE_ARTIFACT,
            "path must be a str or pathlib.Path",
        )
    if not candidate.exists():
        raise Stage30_14_1EvidenceLoadError(
            LOAD_ERROR_UNREADABLE_ARTIFACT,
            "artifact path does not exist",
        )
    if not candidate.is_file():
        raise Stage30_14_1EvidenceLoadError(
            LOAD_ERROR_UNREADABLE_ARTIFACT,
            "artifact path is not a regular file",
        )
    return candidate


# ---------------------------------------------------------------------------
# Per-line validation helpers (pure)
# ---------------------------------------------------------------------------


def _coerce_nonneg_int(value: object) -> Optional[int]:
    """Return ``value`` if it is a non-negative ``int`` that is not ``bool``; else
    ``None``. Pure / total.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _validate_object_fields(obj: dict) -> Tuple[str, str]:
    """Validate the 14 non-``schema_version`` required fields of one parsed object in a
    fixed order; return ``(decision, reason)``.

    The FIRST failing check wins (mirrors the committed Stage 29.5.7 normalizer reason
    discipline). On full success returns ``(ACCEPTED, ACCEPTED_FRESH_EVIDENCE)``; the caller
    then applies dedupe + reconstruction. Pure / total; never raises.
    """
    # 1. every required key present (schema_version was validated structurally upstream).
    for field_name in BUILD26_1_REQUIRED_FIELDS:
        if field_name == "schema_version":
            continue
        if field_name not in obj:
            return LOAD_DECISION_REJECTED, LOAD_REASON_MISSING_REQUIRED_FIELD

    # 2. migration_status must be PRESENT (only a PRESENT record replays + seeds).
    if obj["migration_status"] != MIGRATION_STATUS_PRESENT:
        return LOAD_DECISION_REJECTED, LOAD_REASON_NON_PRESENT_STATUS

    # 3. migration_source must be a closed-set token other than UNKNOWN (PRESENT cannot pair
    #    with UNKNOWN; the synthetic / real source token is carried verbatim).
    source_value = obj["migration_source"]
    if (
        not is_stage29_5_migration_source_value(source_value)
        or source_value == MIGRATION_SOURCE_UNKNOWN_STAGE29_5
    ):
        return LOAD_DECISION_REJECTED, LOAD_REASON_INVALID_SOURCE

    # 4. token_mint: safe-shape mint, then a base58 pump-suffix mint.
    token_mint = obj["token_mint"]
    if not is_safe_mint_or_pool_string(token_mint):
        return LOAD_DECISION_REJECTED, LOAD_REASON_UNSAFE_AXIS_SHAPE
    if not is_pump_suffix_mint(token_mint):
        return LOAD_DECISION_REJECTED, LOAD_REASON_NOT_PUMP_SUFFIX

    # 5. pool quartet remainder: safe-shape mint/pool strings.
    for axis_name in ("pool_account", "pool_program_id", "quote_mint"):
        if not is_safe_mint_or_pool_string(obj[axis_name]):
            return LOAD_DECISION_REJECTED, LOAD_REASON_UNSAFE_AXIS_SHAPE

    # 6. migration_slot: a non-negative int (not bool).
    if _coerce_nonneg_int(obj["migration_slot"]) is None:
        return LOAD_DECISION_REJECTED, LOAD_REASON_UNSAFE_AXIS_SHAPE

    # 7. migration_signature: a non-blank string.
    if not is_nonblank_str(obj["migration_signature"]):
        return LOAD_DECISION_REJECTED, LOAD_REASON_UNSAFE_AXIS_SHAPE

    # 8. timestamps: UTC-shaped ISO-8601.
    if not is_safe_iso8601_utc_string(obj["migration_event_time_utc"]):
        return LOAD_DECISION_REJECTED, LOAD_REASON_MALFORMED_TIMESTAMP
    if not is_safe_iso8601_utc_string(obj["observed_at_utc"]):
        return LOAD_DECISION_REJECTED, LOAD_REASON_MALFORMED_TIMESTAMP

    # 9. source_ref: EXACTLY helius:sig:<migration_signature>:slot:<migration_slot>.
    #    One equality catches a wrong form AND a sig/slot that disagree with the explicit
    #    fields.
    expected_ref = build_expected_source_ref(
        obj["migration_signature"], obj["migration_slot"]
    )
    if obj["source_ref"] != expected_ref:
        return LOAD_DECISION_REJECTED, LOAD_REASON_BAD_SOURCE_REF

    # 10. measurement_status: COMPLETE.
    if obj["measurement_status"] != MEASUREMENT_STATUS_COMPLETE:
        return LOAD_DECISION_REJECTED, LOAD_REASON_INCOMPLETE_MEASUREMENT

    # 11. redaction_status: SAFE.
    if obj["redaction_status"] != REDACTION_STATUS_SAFE:
        return LOAD_DECISION_REJECTED, LOAD_REASON_UNSAFE_REDACTION

    # 12. warnings: an explicit EMPTY list (a proven complete migration has no anomaly).
    warnings_value = obj["warnings"]
    if not isinstance(warnings_value, list) or len(warnings_value) != 0:
        return LOAD_DECISION_REJECTED, LOAD_REASON_NONEMPTY_WARNINGS

    return LOAD_DECISION_ACCEPTED, LOAD_REASON_ACCEPTED_FRESH_EVIDENCE


def _reconstruct_record(obj: dict) -> Stage29_5MigrationEvidenceRecord:
    """Reconstruct a PRESENT ``Stage29_5MigrationEvidenceRecord`` from a fully validated
    object, reversing the committed projection's field renames (``token_mint`` ->
    ``base_mint`` / ``migration_event_time_utc`` -> ``migration_timestamp_utc`` /
    ``source_ref`` -> ``source_event_ref``). FABRICATES nothing -- every field is sourced
    from an explicit JSONL field. The committed validator re-checks the shape.
    """
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=obj["migration_source"],
        base_mint=obj["token_mint"],
        pool_account=obj["pool_account"],
        pool_program_id=obj["pool_program_id"],
        quote_mint=obj["quote_mint"],
        migration_timestamp_utc=obj["migration_event_time_utc"],
        migration_slot=obj["migration_slot"],
        migration_signature=obj["migration_signature"],
        observed_at_utc=obj["observed_at_utc"],
        source_event_ref=obj["source_ref"],
    )


def _persisted_attestation(obj: dict) -> Stage30_14_1PersistedAttestation:
    """Build the persisted attestation carrier from a fully validated object (warnings is a
    validated empty list -> empty tuple)."""
    return Stage30_14_1PersistedAttestation(
        token_mint=obj["token_mint"],
        measurement_status=obj["measurement_status"],
        migration_event_time_utc=obj["migration_event_time_utc"],
        warnings=tuple(obj["warnings"]),
        redaction_status=obj["redaction_status"],
        source_ref=obj["source_ref"],
    )


# ---------------------------------------------------------------------------
# The loader
# ---------------------------------------------------------------------------


class Stage30_14_1EvidenceArtifactLoader:
    """Bounded, read-only, fail-closed Build 26.1 evidence-artifact loader.

    Construction takes optional caps (each validated against its hard ceiling; an
    out-of-bounds cap raises ``Stage30_14_1EvidenceLoadError(INVALID_CAP)``) and a
    ``strict`` flag (default ``False``):

      * ``max_bytes``    -- file-size ceiling, checked BEFORE the file is read.
      * ``max_lines``    -- non-empty JSONL line ceiling.
      * ``max_accepted`` -- reconstructed-record ceiling.
      * ``strict``       -- when ``True``, a per-line content fault raises instead of being
                            recorded as a REJECTED outcome.

    The loader is stateless across calls; each :meth:`load_evidence_from_path` invocation
    independently opens, reads, parses, validates, and closes the artifact file. No handle is
    retained between calls.
    """

    __slots__ = ("_max_bytes", "_max_lines", "_max_accepted", "_strict")

    def __init__(
        self,
        *,
        max_bytes: int = STAGE30_14_1_DEFAULT_MAX_BYTES,
        max_lines: int = STAGE30_14_1_DEFAULT_MAX_LINES,
        max_accepted: int = STAGE30_14_1_DEFAULT_MAX_ACCEPTED,
        strict: bool = False,
    ) -> None:
        if not is_within_byte_cap(max_bytes):
            raise Stage30_14_1EvidenceLoadError(
                LOAD_ERROR_INVALID_CAP, "max_bytes out of bounds"
            )
        if not is_within_line_cap(max_lines):
            raise Stage30_14_1EvidenceLoadError(
                LOAD_ERROR_INVALID_CAP, "max_lines out of bounds"
            )
        if not is_within_accepted_cap(max_accepted):
            raise Stage30_14_1EvidenceLoadError(
                LOAD_ERROR_INVALID_CAP, "max_accepted out of bounds"
            )
        if not isinstance(strict, bool):
            raise Stage30_14_1EvidenceLoadError(
                LOAD_ERROR_INVALID_CAP, "strict must be a bool"
            )
        self._max_bytes: int = max_bytes
        self._max_lines: int = max_lines
        self._max_accepted: int = max_accepted
        self._strict: bool = strict

    def _read_text(self, artifact_path: Path) -> str:
        """Read the artifact as utf-8 AFTER enforcing the byte cap against the file size.
        Read-only; raises ``Stage30_14_1EvidenceLoadError`` on an oversized or unreadable
        file.
        """
        try:
            size = artifact_path.stat().st_size
        except OSError as exc:
            raise Stage30_14_1EvidenceLoadError(
                LOAD_ERROR_UNREADABLE_ARTIFACT,
                "could not stat artifact file",
            ) from exc
        if size > self._max_bytes:
            raise Stage30_14_1EvidenceLoadError(
                LOAD_ERROR_FILE_TOO_LARGE,
                "artifact file exceeds max_bytes",
            )
        try:
            return artifact_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise Stage30_14_1EvidenceLoadError(
                LOAD_ERROR_UNREADABLE_ARTIFACT,
                "could not read artifact file as utf-8",
            ) from exc

    def _parse_jsonl_objects(self, text: str) -> Tuple[dict, ...]:
        """Parse one JSON object per non-empty line, enforcing the line cap. Raises
        ``TOO_MANY_LINES`` / ``MALFORMED_JSONL_LINE`` / ``WRONG_SCHEMA_VERSION``.
        """
        nonempty: List[str] = [
            line for line in text.splitlines() if line.strip()
        ]
        if len(nonempty) > self._max_lines:
            raise Stage30_14_1EvidenceLoadError(
                LOAD_ERROR_TOO_MANY_LINES,
                "artifact carries more lines than max_lines",
            )
        objects: List[dict] = []
        for line_index, line in enumerate(nonempty):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise Stage30_14_1EvidenceLoadError(
                    LOAD_ERROR_MALFORMED_JSONL_LINE,
                    f"jsonl line {line_index} is not valid JSON",
                ) from exc
            if not isinstance(parsed, dict):
                raise Stage30_14_1EvidenceLoadError(
                    LOAD_ERROR_MALFORMED_JSONL_LINE,
                    f"jsonl line {line_index} is not a JSON object",
                )
            # Structural version gate: a missing / mismatched schema_version makes the whole
            # artifact untrusted.
            if (
                parsed.get("schema_version")
                != BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION
            ):
                raise Stage30_14_1EvidenceLoadError(
                    LOAD_ERROR_WRONG_SCHEMA_VERSION,
                    f"jsonl line {line_index} carries a non-Build-26.1 "
                    "schema_version",
                )
            objects.append(parsed)
        return tuple(objects)

    def load_evidence_from_path(
        self,
        path: object,
        *,
        created_at_utc: str,
    ) -> Stage30_14_1EvidenceLoadResult:
        """Load + validate + reconstruct evidence records from the artifact at ``path``.

        Structural faults raise ``Stage30_14_1EvidenceLoadError``; per-line content faults
        are recorded as ``REJECTED`` outcomes (or raise when ``strict=True``). Returns a
        ``Stage30_14_1EvidenceLoadResult`` carrying the ordered outcomes, the reconstructed
        accepted records, the aligned persisted attestations, the four-count summary, and the
        combined redaction status. ``created_at_utc`` is caller-injected; the loader reads no
        wall clock. ``KeyboardInterrupt`` / ``SystemExit`` are NOT swallowed.
        """
        artifact_path = _resolve_artifact_path(path)
        text = self._read_text(artifact_path)
        objects = self._parse_jsonl_objects(text)

        outcomes: List[Stage30_14_1EvidenceLoadOutcome] = []
        accepted_records: List[Any] = []
        accepted_attestations: List[Stage30_14_1PersistedAttestation] = []
        seen_mints: set = set()
        seen_signatures: set = set()
        lines_seen = 0
        accepted = 0
        rejected = 0
        duplicate = 0

        for obj in objects:
            lines_seen += 1
            mint_echo = safe_echo(obj.get("token_mint"))
            decision, reason = _validate_object_fields(obj)

            # ---- dedupe (first-wins) only AFTER full field validation passes ----
            if decision == LOAD_DECISION_ACCEPTED:
                base_mint = obj["token_mint"]
                signature = obj["migration_signature"]
                if base_mint in seen_mints:
                    decision, reason = (
                        LOAD_DECISION_REJECTED,
                        LOAD_REASON_DUPLICATE_MINT,
                    )
                elif signature in seen_signatures:
                    decision, reason = (
                        LOAD_DECISION_REJECTED,
                        LOAD_REASON_DUPLICATE_SIGNATURE,
                    )

            if decision == LOAD_DECISION_REJECTED:
                if self._strict:
                    raise Stage30_14_1EvidenceLoadError(
                        reason, "strict-mode per-line content fault"
                    )
                outcomes.append(
                    Stage30_14_1EvidenceLoadOutcome(
                        token_mint=mint_echo,
                        load_decision=decision,
                        load_reason=reason,
                        created_at_utc=created_at_utc,
                    )
                )
                if reason in (
                    LOAD_REASON_DUPLICATE_MINT,
                    LOAD_REASON_DUPLICATE_SIGNATURE,
                ):
                    duplicate += 1
                else:
                    rejected += 1
                continue

            # ---- accepted: reconstruct (committed validator backstop) ----
            try:
                record = _reconstruct_record(obj)
            except ValueError:
                # The committed validator refused a shape our explicit checks admitted; fail
                # the line closed rather than fabricate. (Defense in depth; unreachable on a
                # well-formed line.)
                if self._strict:
                    raise Stage30_14_1EvidenceLoadError(
                        LOAD_REASON_UNSAFE_AXIS_SHAPE,
                        "committed record validator refused the line",
                    )
                outcomes.append(
                    Stage30_14_1EvidenceLoadOutcome(
                        token_mint=mint_echo,
                        load_decision=LOAD_DECISION_REJECTED,
                        load_reason=LOAD_REASON_UNSAFE_AXIS_SHAPE,
                        created_at_utc=created_at_utc,
                    )
                )
                rejected += 1
                continue

            seen_mints.add(obj["token_mint"])
            seen_signatures.add(obj["migration_signature"])
            accepted_records.append(record)
            accepted_attestations.append(_persisted_attestation(obj))
            outcomes.append(
                Stage30_14_1EvidenceLoadOutcome(
                    token_mint=mint_echo,
                    load_decision=LOAD_DECISION_ACCEPTED,
                    load_reason=LOAD_REASON_ACCEPTED_FRESH_EVIDENCE,
                    created_at_utc=created_at_utc,
                )
            )
            accepted += 1

        if accepted > self._max_accepted:
            raise Stage30_14_1EvidenceLoadError(
                LOAD_ERROR_TOO_MANY_RECORDS,
                "artifact carries more accepted records than max_accepted",
            )

        summary = Stage30_14_1EvidenceLoadSummary(
            lines_seen=lines_seen,
            accepted=accepted,
            rejected=rejected,
            duplicate=duplicate,
            created_at_utc=created_at_utc,
        )
        scanned: List[str] = [created_at_utc]
        for outcome in outcomes:
            scanned.append(outcome.token_mint)
            scanned.append(outcome.load_decision)
            scanned.append(outcome.load_reason)
        redaction_status = (
            STAGE30_14_1_REDACTION_STATUS_REDACTED
            if are_strings_redaction_safe(tuple(scanned))
            else STAGE30_14_1_REDACTION_STATUS_VIOLATION
        )
        return Stage30_14_1EvidenceLoadResult(
            outcomes=tuple(outcomes),
            accepted_records=tuple(accepted_records),
            accepted_attestations=tuple(accepted_attestations),
            summary=summary,
            redaction_status=redaction_status,
            created_at_utc=created_at_utc,
        )


__all__ = (
    "Stage30_14_1EvidenceLoadError",
    "Stage30_14_1EvidenceArtifactLoader",
)
