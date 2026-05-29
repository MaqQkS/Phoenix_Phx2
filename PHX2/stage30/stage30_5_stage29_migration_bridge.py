"""Stage 30.5.3 offline Stage 29.5 migration-evidence -> Stage 30.5 bridge.

Stage 30.5.3 ships the Stage-30-owned offline bridge that converts a
sanitized Stage 29.5 migration-evidence summary into the Stage 30.5
migration-context contract (record / projection / resolver) so the
compact ping ``Mig`` token can carry an honest, evidence-backed
migration display word (``Known`` / ``Unverified`` / ``Unknown``) drawn
from the Stage 29.5 evidence instead of the literal ``Unknown`` the
Stage 30.4.2 path emits by default.

Stage 30 owns the compact projection contract; Stage 29.5 owns the
migration-evidence semantics. The bridge reads the Stage 29.5 evidence
SHAPE but Stage 30 maps it onto its own closed sets. Crucially, the
bridge imports NO Stage 29 production module: it consumes a sanitized,
duck-typed artifact-shaped input (a Stage-30-owned
``Stage30_5_3SanitizedStage29MigrationEvidence`` dataclass, or any
object / namespace exposing the same safe summary attributes). The
no-Stage-29-import boundary subsumes the Stage 29.5.5 private
side-channel renderer / recorder / artifact-writer exclusion: none of
those can be reached here because no Stage 29 module is imported at all.

Input shape (sanitized Stage 29.5 migration-evidence summary):

  * ``measurement_status`` -- the Stage 29.5 private-ping measurement
    status token (``COMPLETE`` / ``PARTIAL_MIGRATION_PRESENT`` /
    ``MISSING_MIGRATION`` / ``INVALID_MIGRATION`` /
    ``CONFLICTING_MIGRATION``). This is the most-processed Stage 29.5
    evidence verdict (post join + ATH cross-check) and is the primary
    discriminator.
  * ``warnings`` -- the Stage 29.5 warning-code tuple. Only the
    ``MIGRATION_STALE`` token is consulted (to degrade a partial reading
    to ``Unknown`` with a ``STALE`` source-status).
  * ``redaction_status`` -- the Stage 29.5 redaction token. A present
    non-``SAFE`` value degrades the projection to ``Unknown`` (the bridge
    trusts only a redaction-safe summary).

The bridge reads ONLY those three safe summary fields. It deliberately
does NOT read (and the Stage 30.5 record cannot carry) the Stage 29.5
migration signature, the migration event id, the source event ref, the
raw capture ref, the candidate / pool / quote mint axes, the raw
provider payload, or any secret -- so no raw transaction signature,
provider payload, or raw log can leak into the Stage 30 bridge output.

Mapping (sanitized Stage 29.5 summary -> Stage 30.5 closed sets):

  Stage 29.5 measurement_status     -> (migration_status, migration_basis,
   (+ warnings / redaction)             source_status, source_reason)  -> Mig
  ---------------------------------------------------------------------------
  COMPLETE                          -> KNOWN / ON_CHAIN_EVENT /
                                       PRESENT / SOURCE_PRESENT        -> Known
  PARTIAL_MIGRATION_PRESENT
    (no MIGRATION_STALE warning)    -> UNVERIFIED / EVIDENCE_PARTIAL /
                                       PRESENT / EVIDENCE_PARTIAL      -> Unverified
  PARTIAL_MIGRATION_PRESENT
    (+ MIGRATION_STALE warning)     -> UNKNOWN / NONE /
                                       STALE / SOURCE_STALE            -> Unknown
  MISSING_MIGRATION                 -> UNKNOWN / NONE /
                                       UNAVAILABLE / SOURCE_UNAVAILABLE -> Unknown
  INVALID_MIGRATION                 -> UNKNOWN / NONE /
                                       ERROR / EVIDENCE_INVALID        -> Unknown
  CONFLICTING_MIGRATION             -> UNKNOWN / NONE /
                                       ERROR / EVIDENCE_INVALID        -> Unknown
   (conservative: a conflict is never promoted to Known / Unverified)
  redaction_status present, != SAFE -> UNKNOWN / NONE /
                                       ERROR / EVIDENCE_INVALID        -> Unknown
  evidence is None                  -> UNKNOWN / NONE /
                                       UNAVAILABLE / SOURCE_UNAVAILABLE -> Unknown
  unrecognized / missing
    measurement_status (malformed)  -> UNKNOWN / NONE /
                                       ERROR / SOURCE_ERROR            -> Unknown

Source-availability dominance lives in the Stage 30.5.1 adapter: only a
``PRESENT`` source_status projects a status word, so every non-PRESENT
row above renders ``Mig: Unknown`` regardless of migration_status. The
bridge still sets migration_status=UNKNOWN / basis=NONE on those rows so
the record reads ``Unknown`` even when inspected directly. There is no
``Mig: Stale`` / ``Mig: Fresh`` display word: a stale reading maps to a
``STALE`` source-status that the adapter renders as ``Unknown``.

``runtime_consumable`` is always ``False`` on the emitted record (the
Stage 30.5.1 record REJECTS ``True`` at construction); the bridge is
offline-only and never flips it. No ATH field, no Net field is ever
introduced.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Stage 30.5 sibling modules imported read-only (the Stage 30.5.1
    models + the Stage 30.5.2 runtime display resolver).
  * No Stage 21-29 production-source import (the Stage 29.5 evidence is
    consumed as a sanitized duck-typed shape, never imported).
  * No process-env read, no live secret access.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No provider client, no private side-channel transport reference.
  * No PHX1 import.
  * No network / env / filesystem I/O at import time (or ever).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from PHX2.stage30.stage30_5_compact_migration_runtime_adapter import (
    Stage30_5_2MigrationDisplayResolver,
)
from PHX2.stage30.stage30_5_migration_context_models import (
    MIGRATION_BASIS_EVIDENCE_PARTIAL,
    MIGRATION_BASIS_NONE,
    MIGRATION_BASIS_ON_CHAIN_EVENT,
    MIGRATION_STATUS_KNOWN,
    MIGRATION_STATUS_UNKNOWN,
    MIGRATION_STATUS_UNVERIFIED,
    SOURCE_REASON_EVIDENCE_INVALID,
    SOURCE_REASON_EVIDENCE_PARTIAL,
    SOURCE_REASON_SOURCE_ERROR,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_REASON_SOURCE_STALE,
    SOURCE_REASON_SOURCE_UNAVAILABLE,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_STALE,
    SOURCE_STATUS_UNAVAILABLE,
    STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
    Stage30_5MigrationContextRecord,
    is_safe_iso8601_utc,
    is_safe_source_label,
)


# ---------------------------------------------------------------------------
# Stage 30.5.3 minor version + safe source-family label
# ---------------------------------------------------------------------------


STAGE30_5_3_MINOR_VERSION: str = "30.5.3"


# Stage-30-owned safe source-family label stamped onto every bridge
# record (echoed to the projection as provenance; never rendered into the
# compact body). Safe-shape per ``is_safe_source_label``.
STAGE30_5_3_SOURCE_LABEL: str = "stage29_5_migration_evidence"


# ---------------------------------------------------------------------------
# Stage-30-owned mirror of the Stage 29.5 summary vocabulary (NOT imported)
# ---------------------------------------------------------------------------
#
# These mirror the Stage 29.5 private-ping measurement-status tokens plus
# the one warning token and the redaction-safe token the bridge consults.
# They are duplicated here as plain Stage-30-owned string literals
# precisely to preserve the no-Stage-29-import boundary: the bridge
# recognizes the Stage 29.5 SHAPE without importing any Stage 29 module.
# If a future Stage 29.5 spec lock renames these tokens, the divergence is
# caught by the Stage 30.5.3 mapping tests (which document the expected
# token strings), and an unrecognized token degrades conservatively to
# ``Mig: Unknown`` rather than overclaiming.


STAGE29_5_MEASUREMENT_STATUS_COMPLETE: str = "COMPLETE"
STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT: str = (
    "PARTIAL_MIGRATION_PRESENT"
)
STAGE29_5_MEASUREMENT_STATUS_MISSING_MIGRATION: str = "MISSING_MIGRATION"
STAGE29_5_MEASUREMENT_STATUS_INVALID_MIGRATION: str = "INVALID_MIGRATION"
STAGE29_5_MEASUREMENT_STATUS_CONFLICTING_MIGRATION: str = (
    "CONFLICTING_MIGRATION"
)


STAGE29_5_RECOGNIZED_MEASUREMENT_STATUS_VALUES: Tuple[str, ...] = (
    STAGE29_5_MEASUREMENT_STATUS_COMPLETE,
    STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    STAGE29_5_MEASUREMENT_STATUS_MISSING_MIGRATION,
    STAGE29_5_MEASUREMENT_STATUS_INVALID_MIGRATION,
    STAGE29_5_MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
)


# The single Stage 29.5 warning token the bridge consults (to degrade a
# partial reading to a STALE source-status).
STAGE29_5_WARNING_MIGRATION_STALE: str = "MIGRATION_STALE"


# The Stage 29.5 redaction-safe token. Any present non-SAFE redaction
# token degrades the projection to ``Mig: Unknown``.
STAGE29_5_REDACTION_STATUS_SAFE: str = "SAFE"


# ---------------------------------------------------------------------------
# Sanitized Stage 29.5 migration-evidence summary (Stage-30-owned input)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_5_3SanitizedStage29MigrationEvidence:
    """Stage-30-owned sanitized Stage 29.5 migration-evidence summary.

    The canonical artifact-shaped input the Stage 30.5.3 bridge accepts.
    Carries ONLY the three safe summary fields the bridge consults; it has
    no field for a migration signature, migration event id, source event
    ref, raw capture ref, mint / pool axes, raw provider payload, or any
    secret, so a sanitized artifact can never smuggle a raw identifier into
    the Stage 30 projection.

    The bridge also accepts any duck-typed object / namespace that exposes
    ``measurement_status`` / ``warnings`` / ``redaction_status`` attributes
    (read via ``getattr``) -- so a caller may pass a sanitized copy of a
    Stage 29.5 private-ping migration-context record without the bridge
    importing Stage 29.5.

    Fields:

      * ``measurement_status`` -- Stage 29.5 measurement-status token (or
        any value; an unrecognized / ``None`` value degrades to
        ``Mig: Unknown``).
      * ``warnings`` -- tuple of Stage 29.5 warning-code tokens. Only
        ``MIGRATION_STALE`` is consulted. Defaults to ``()``.
      * ``redaction_status`` -- Stage 29.5 redaction token or ``None``. A
        present non-``SAFE`` value degrades to ``Mig: Unknown``.
    """

    measurement_status: Optional[str]
    warnings: Tuple[str, ...] = ()
    redaction_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stale_in_warnings(warnings: object) -> bool:
    """Return ``True`` iff the Stage 29.5 ``MIGRATION_STALE`` warning token
    is present in a tuple / list / set / frozenset of warning codes.

    A non-collection input (including a bare ``str``, to avoid
    character-iteration) returns ``False``.
    """
    if isinstance(warnings, (tuple, list, set, frozenset)):
        return STAGE29_5_WARNING_MIGRATION_STALE in warnings
    return False


def _safe_source_label(source_label: object) -> Optional[str]:
    """Return ``source_label`` if it is a safe-shape source label; return
    ``None`` for any unsafe-shape / non-string input.
    """
    if isinstance(source_label, str) and is_safe_source_label(source_label):
        return source_label
    return None


# ---------------------------------------------------------------------------
# Public: project a sanitized Stage 29.5 summary -> Stage 30.5.1 record
# ---------------------------------------------------------------------------


def project_stage29_migration_evidence_to_stage30_record(
    evidence: object,
    observed_at_utc: object,
    *,
    source_label: str = STAGE30_5_3_SOURCE_LABEL,
) -> Optional[Stage30_5MigrationContextRecord]:
    """Project a sanitized Stage 29.5 migration-evidence summary onto a
    Stage 30.5.1 ``Stage30_5MigrationContextRecord``.

    See the module docstring for the full mapping table.

    Returns ``None`` ONLY when ``observed_at_utc`` is not a safe-shape
    ISO-8601 UTC string (the record cannot be stamped without a caller-
    supplied clock). Otherwise ALWAYS returns a record, degrading missing /
    malformed / conflicting / stale / non-redaction-safe evidence to an
    ``Unknown``-projecting record (a non-PRESENT source_status, which the
    Stage 30.5.1 adapter renders as ``Mig: Unknown``).

    Never raises for an evidence-shape failure. Never mutates ``evidence``.
    Never reads anything off ``evidence`` other than its safe summary
    attributes (``measurement_status`` / ``warnings`` / ``redaction_status``).
    ``runtime_consumable`` is hard-locked ``False``; ``token_label`` is
    always ``None`` (no full mint string is carried).
    """
    if not is_safe_iso8601_utc(observed_at_utc):
        return None
    assert isinstance(observed_at_utc, str)  # narrowed by is_safe check
    safe_label = _safe_source_label(source_label)

    def _record(
        *,
        migration_status: str,
        migration_basis: str,
        source_status: str,
        source_reason: str,
    ) -> Stage30_5MigrationContextRecord:
        return Stage30_5MigrationContextRecord(
            schema_version=STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
            token_label=None,
            migration_status=migration_status,
            migration_basis=migration_basis,
            migration_event_time_utc=None,
            migration_age_seconds=None,
            source_label=safe_label,
            source_status=source_status,
            source_reason=source_reason,
            runtime_consumable=False,
            observed_at_utc=observed_at_utc,
        )

    # ----- No evidence at all: source unavailable --------------------------
    if evidence is None:
        return _record(
            migration_status=MIGRATION_STATUS_UNKNOWN,
            migration_basis=MIGRATION_BASIS_NONE,
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_UNAVAILABLE,
        )

    measurement_status = getattr(evidence, "measurement_status", None)
    redaction_status = getattr(evidence, "redaction_status", None)
    warnings = getattr(evidence, "warnings", ())

    # ----- Untrusted redaction dominates: degrade to Unknown ---------------
    if (
        isinstance(redaction_status, str)
        and redaction_status != STAGE29_5_REDACTION_STATUS_SAFE
    ):
        return _record(
            migration_status=MIGRATION_STATUS_UNKNOWN,
            migration_basis=MIGRATION_BASIS_NONE,
            source_status=SOURCE_STATUS_ERROR,
            source_reason=SOURCE_REASON_EVIDENCE_INVALID,
        )

    # ----- Confirmed: COMPLETE -> Known ------------------------------------
    if measurement_status == STAGE29_5_MEASUREMENT_STATUS_COMPLETE:
        return _record(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        )

    # ----- Partial: PARTIAL_MIGRATION_PRESENT ------------------------------
    if (
        measurement_status
        == STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
    ):
        if _stale_in_warnings(warnings):
            # A stale partial reading degrades to a STALE source-status,
            # which the adapter renders ``Mig: Unknown`` (no Stale word).
            return _record(
                migration_status=MIGRATION_STATUS_UNKNOWN,
                migration_basis=MIGRATION_BASIS_NONE,
                source_status=SOURCE_STATUS_STALE,
                source_reason=SOURCE_REASON_SOURCE_STALE,
            )
        return _record(
            migration_status=MIGRATION_STATUS_UNVERIFIED,
            migration_basis=MIGRATION_BASIS_EVIDENCE_PARTIAL,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_EVIDENCE_PARTIAL,
        )

    # ----- Missing: MISSING_MIGRATION --------------------------------------
    if (
        measurement_status
        == STAGE29_5_MEASUREMENT_STATUS_MISSING_MIGRATION
    ):
        return _record(
            migration_status=MIGRATION_STATUS_UNKNOWN,
            migration_basis=MIGRATION_BASIS_NONE,
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_UNAVAILABLE,
        )

    # ----- Invalid / conflicting: conservative ERROR -> Unknown ------------
    if measurement_status in (
        STAGE29_5_MEASUREMENT_STATUS_INVALID_MIGRATION,
        STAGE29_5_MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    ):
        return _record(
            migration_status=MIGRATION_STATUS_UNKNOWN,
            migration_basis=MIGRATION_BASIS_NONE,
            source_status=SOURCE_STATUS_ERROR,
            source_reason=SOURCE_REASON_EVIDENCE_INVALID,
        )

    # ----- Unrecognized / missing measurement_status: malformed ------------
    return _record(
        migration_status=MIGRATION_STATUS_UNKNOWN,
        migration_basis=MIGRATION_BASIS_NONE,
        source_status=SOURCE_STATUS_ERROR,
        source_reason=SOURCE_REASON_SOURCE_ERROR,
    )


# ---------------------------------------------------------------------------
# Public: Stage 30.5.1 source-protocol-shaped bridge
# ---------------------------------------------------------------------------


class Stage30_5_3Stage29MigrationEvidenceBridge:
    """Stage 30.5.1-source-protocol-shaped bridge over a sanitized Stage
    29.5 migration-evidence summary.

    Holds one sanitized evidence object (or ``None``) and exposes the Stage
    30.5.1 source-protocol ``read`` method:
    ``read(token_mint, observed_at_utc=None) ->
    Optional[Stage30_5MigrationContextRecord]``. Each ``read`` projects the
    held evidence via
    :func:`project_stage29_migration_evidence_to_stage30_record`.

    The bridge never opens a network connection, never reads the process
    environment, never mutates the evidence, and never calls anything on the
    evidence other than reading its safe summary attributes. The
    ``token_mint`` argument is accepted for protocol compatibility; the
    bridge does NOT echo it into the record (``token_label`` stays
    ``None``), so no full mint string is carried on the output.
    """

    __slots__ = ("_evidence", "_source_label")

    def __init__(
        self,
        *,
        evidence: object,
        source_label: str = STAGE30_5_3_SOURCE_LABEL,
    ) -> None:
        self._evidence: object = evidence
        self._source_label: str = source_label

    @property
    def evidence(self) -> object:
        """Return the wrapped sanitized Stage 29.5 evidence summary."""
        return self._evidence

    def read(
        self,
        token_mint: object,
        observed_at_utc: Optional[str] = None,
    ) -> Optional[Stage30_5MigrationContextRecord]:
        """Project the held sanitized Stage 29.5 evidence onto a Stage
        30.5.1 record. ``token_mint`` is accepted for protocol
        compatibility and is intentionally unused (it is never echoed into
        the record).
        """
        return project_stage29_migration_evidence_to_stage30_record(
            self._evidence,
            observed_at_utc,
            source_label=self._source_label,
        )


# ---------------------------------------------------------------------------
# Public: build the Stage 30.5.2 runtime resolver from a sanitized artifact
# ---------------------------------------------------------------------------


def build_stage30_migration_resolver_from_stage29_artifact(
    *,
    evidence: object,
    source_label: str = STAGE30_5_3_SOURCE_LABEL,
) -> Stage30_5_2MigrationDisplayResolver:
    """Build a Stage 30.5.2 migration display resolver wrapping a Stage
    30.5.3 bridge over the sanitized Stage 29.5 evidence summary.

    The returned resolver is the drop-in object the Stage 30.4.2
    orchestrator's opt-in ``migration_context_resolver`` seam consumes: its
    ``resolve_display_text(token_mint, observed_at_utc)`` returns the single
    closed-set ``Mig`` display word (``Known`` / ``Unverified`` /
    ``Unknown``) for the held evidence.
    """
    bridge = Stage30_5_3Stage29MigrationEvidenceBridge(
        evidence=evidence,
        source_label=source_label,
    )
    return Stage30_5_2MigrationDisplayResolver(source=bridge)


__all__ = (
    "STAGE30_5_3_MINOR_VERSION",
    "STAGE30_5_3_SOURCE_LABEL",
    "STAGE29_5_MEASUREMENT_STATUS_COMPLETE",
    "STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT",
    "STAGE29_5_MEASUREMENT_STATUS_MISSING_MIGRATION",
    "STAGE29_5_MEASUREMENT_STATUS_INVALID_MIGRATION",
    "STAGE29_5_MEASUREMENT_STATUS_CONFLICTING_MIGRATION",
    "STAGE29_5_RECOGNIZED_MEASUREMENT_STATUS_VALUES",
    "STAGE29_5_WARNING_MIGRATION_STALE",
    "STAGE29_5_REDACTION_STATUS_SAFE",
    "Stage30_5_3SanitizedStage29MigrationEvidence",
    "Stage30_5_3Stage29MigrationEvidenceBridge",
    "project_stage29_migration_evidence_to_stage30_record",
    "build_stage30_migration_resolver_from_stage29_artifact",
)
