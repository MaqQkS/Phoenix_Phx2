"""Stage 30.5.1 offline migration-context adapter / projector.

Pure projector that turns a Stage 30.5.1 source-protocol-shaped
object (or ``None``) into a Stage 30.5.1
``Stage30_5MigrationContextProjection`` carrying the single safe
``Mig`` display word the compact body shows. The adapter NEVER
opens a network connection, NEVER reads the process environment,
NEVER calls ``datetime.now`` (the clock is caller-supplied via
``observed_at_utc``), NEVER mutates its inputs, NEVER recomputes
Stage 30.1 tier decisions, NEVER routes data into Stage 30.1 /
30.2 / 30.3 runtime, NEVER triggers a transport send, NEVER
imports the Stage 29.5.5 private side-channel renderer / recorder /
artifact writer, and NEVER fabricates a migration status (missing /
``None`` / source error / invalid evidence => ``Mig: Unknown``).

Status -> ``Mig`` display mapping (Stage 30.5.0 spec lock §3, §5).
Source availability DOMINATES migration_status: only a ``PRESENT``
source_status may project a migration status word.

  * ``PRESENT`` + ``KNOWN``      -> ``"Known"``
  * ``PRESENT`` + ``UNVERIFIED`` -> ``"Unverified"``
  * ``PRESENT`` + ``UNKNOWN``    -> ``"Unknown"``
  * any non-PRESENT source_status (``UNAVAILABLE`` / ``ERROR`` /
    ``STALE``) -> ``"Unknown"`` REGARDLESS of migration_status (there
    is NO ``Mig: Stale`` display token).
  * no source / ``read`` returns ``None`` / ``read`` raises /
    off-closed-set evidence -> ``"Unknown"``.

Source-availability dominance. Only a ``PRESENT`` source_status may
project a migration status word; any non-PRESENT source_status
(``UNAVAILABLE`` / ``ERROR`` / ``STALE``) conservatively degrades to
``Mig: Unknown`` regardless of the record's migration_status. The
SOURCE is additionally responsible for only emitting ``KNOWN`` when
its evidence is promotable (a trusted ``ON_CHAIN_EVENT`` basis). The
adapter does not re-derive migration evidence (Stage 29.5 owns the
evidence side, Stage 30 owns the compact display contract).

The adapter hard-locks ``runtime_consumable=False`` on every
projection it returns. A future Stage 30.5.2 opt-in runtime
substage may flip the flag under the orchestrator boundary, but
Stage 30.5.1 does not. The projection carries NO migration event
time, NO migration age, NO token label, NO ATH field, and NO Net
field: the ``Mig`` token is a single short word, never a verbose
block.

Discipline:

  * Stdlib only (``typing``).
  * Stage 30.5.1 sibling module ``models`` imported read-only.
  * No process-env read, no live secret access.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No Discord, Telegram, X / social, inbound-hook reference.
  * No Stage 29.5.5 private side-channel renderer / recorder /
    artifact writer import.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No network / env / filesystem I/O at import time.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage30.stage30_5_migration_context_models import (
    MIGRATION_BASIS_NONE,
    MIGRATION_STATUS_UNKNOWN,
    SOURCE_REASON_EVIDENCE_INVALID,
    SOURCE_REASON_SOURCE_ERROR,
    SOURCE_REASON_SOURCE_NOT_CONFIGURED,
    SOURCE_REASON_SOURCE_UNAVAILABLE,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNAVAILABLE,
    STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
    Stage30_5MigrationContextProjection,
    display_text_for_status,
    is_migration_basis_value,
    is_migration_status_value,
    is_safe_source_label,
    is_source_reason_value,
    is_source_status_value,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _echo_source_label(value: object) -> Optional[str]:
    """Return ``value`` if it is a safe-shape source label; return
    ``None`` for ``None`` or any unsafe-shape input.
    """
    if value is None:
        return None
    if is_safe_source_label(value):
        assert isinstance(value, str)  # narrows for downstream
        return value
    return None


def _unknown_projection(
    *,
    source_status: str,
    source_reason: str,
    source_label: Optional[str],
) -> Stage30_5MigrationContextProjection:
    """Build a safe ``Mig: Unknown`` projection.

    ``migration_status`` resolves to ``UNKNOWN`` with basis ``NONE``
    and ``migration_display_text`` ``"Unknown"``. ``runtime_consumable``
    is hard-locked ``False``.
    """
    return Stage30_5MigrationContextProjection(
        schema_version=(
            STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION
        ),
        migration_display_text=display_text_for_status(
            MIGRATION_STATUS_UNKNOWN
        ),
        migration_status=MIGRATION_STATUS_UNKNOWN,
        migration_basis=MIGRATION_BASIS_NONE,
        source_status=source_status,
        source_reason=source_reason,
        source_label=source_label,
        runtime_consumable=False,
    )


# ---------------------------------------------------------------------------
# Public: project_migration_context
# ---------------------------------------------------------------------------


def project_migration_context(
    source: object,
    token_mint: object,
    observed_at_utc: Optional[str] = None,
) -> Stage30_5MigrationContextProjection:
    """Project a Stage 30.5.1 compact migration-context projection.

    Behavior:

      * ``source is None``                  => ``Mig: Unknown``,
                                               ``source_status=UNAVAILABLE``,
                                               ``source_reason=SOURCE_NOT_CONFIGURED``,
                                               ``source_label=None``.
      * ``token_mint`` not a ``str``        => ``Mig: Unknown``,
                                               ``source_status=UNAVAILABLE``,
                                               ``source_reason=SOURCE_UNAVAILABLE``.
      * ``source`` has no callable ``read`` => ``Mig: Unknown``,
                                               ``source_status=ERROR``,
                                               ``source_reason=SOURCE_ERROR``.
      * ``source.read`` raises              => ``Mig: Unknown``,
                                               ``source_status=ERROR``,
                                               ``source_reason=SOURCE_ERROR``
                                               (the raw exception text
                                               is NEVER echoed).
      * ``source.read`` returns ``None``    => ``Mig: Unknown``,
                                               ``source_status=UNAVAILABLE``,
                                               ``source_reason=SOURCE_UNAVAILABLE``.
      * ``source.read`` returns an object
        whose closed-set evidence fields do
        not all validate                    => ``Mig: Unknown``,
                                               ``source_status=ERROR``,
                                               ``source_reason=EVIDENCE_INVALID``
                                               (a safe ``source_label``
                                               is still preserved).
      * ``source.read`` returns a valid
        record whose ``source_status`` is
        NOT ``PRESENT`` (``UNAVAILABLE`` /
        ``ERROR`` / ``STALE``)              => ``Mig: Unknown``
                                               REGARDLESS of the
                                               record's
                                               ``migration_status``;
                                               ``migration_status=UNKNOWN``,
                                               ``migration_basis=NONE``;
                                               the original
                                               ``source_status`` /
                                               ``source_reason`` and a
                                               safe ``source_label``
                                               are preserved as
                                               provenance.
      * ``source.read`` returns a valid
        record whose ``source_status`` is
        ``PRESENT``                         => echo its closed-set
                                               ``migration_status`` /
                                               ``migration_basis`` /
                                               ``source_status`` /
                                               ``source_reason`` and a
                                               safe ``source_label``;
                                               ``migration_display_text``
                                               is the status word
                                               (``Known`` /
                                               ``Unverified`` /
                                               ``Unknown``).

    Always returns a projection (never raises for a source failure);
    caller-shape and evidence failures degrade to ``Mig: Unknown``.
    ``runtime_consumable`` is hard-locked ``False`` on every
    projection. NEVER mutates ``source``, NEVER calls anything on
    ``source`` other than ``source.read(token_mint, observed_at_utc)``,
    NEVER fetches network data, NEVER reads the process environment.
    """
    # ----- No source: full Unknown path -----------------------------------
    if source is None:
        return _unknown_projection(
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_NOT_CONFIGURED,
            source_label=None,
        )

    # ----- Unusable token_mint -------------------------------------------
    if not isinstance(token_mint, str):
        return _unknown_projection(
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_UNAVAILABLE,
            source_label=None,
        )

    # ----- Source must expose a callable read ----------------------------
    read_method = getattr(source, "read", None)
    if not callable(read_method):
        return _unknown_projection(
            source_status=SOURCE_STATUS_ERROR,
            source_reason=SOURCE_REASON_SOURCE_ERROR,
            source_label=None,
        )

    # ----- Ask for a record; a raising source degrades to Unknown --------
    try:
        record = read_method(token_mint, observed_at_utc)
    except Exception:  # noqa: BLE001 - any source failure => Unknown
        return _unknown_projection(
            source_status=SOURCE_STATUS_ERROR,
            source_reason=SOURCE_REASON_SOURCE_ERROR,
            source_label=None,
        )

    if record is None:
        return _unknown_projection(
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_UNAVAILABLE,
            source_label=None,
        )

    # ----- Validate the record's closed-set evidence fields --------------
    # Duck-typed read via getattr so a non-dataclass shaped source can
    # still satisfy the protocol; a record carrying any off-closed-set
    # field degrades to Unknown with EVIDENCE_INVALID.
    raw_status = getattr(record, "migration_status", None)
    raw_basis = getattr(record, "migration_basis", None)
    raw_source_status = getattr(record, "source_status", None)
    raw_source_reason = getattr(record, "source_reason", None)
    raw_source_label = getattr(record, "source_label", None)

    if not (
        is_migration_status_value(raw_status)
        and is_migration_basis_value(raw_basis)
        and is_source_status_value(raw_source_status)
        and is_source_reason_value(raw_source_reason)
    ):
        return _unknown_projection(
            source_status=SOURCE_STATUS_ERROR,
            source_reason=SOURCE_REASON_EVIDENCE_INVALID,
            source_label=_echo_source_label(raw_source_label),
        )

    # ----- Source-availability dominance --------------------------------
    # Only a PRESENT source_status may project a migration status word.
    # Any non-PRESENT source_status (UNAVAILABLE / ERROR / STALE)
    # conservatively degrades to Mig: Unknown REGARDLESS of the record's
    # migration_status -- source availability dominates migration_status
    # (Stage 30.5.0 spec lock §3 / §5: missing / ambiguous / degraded
    # evidence renders Mig: Unknown). The original source_status /
    # source_reason / source_label are preserved as provenance; there is
    # no Mig: Stale display token.
    if raw_source_status != SOURCE_STATUS_PRESENT:
        return _unknown_projection(
            source_status=raw_source_status,
            source_reason=raw_source_reason,
            source_label=_echo_source_label(raw_source_label),
        )

    return Stage30_5MigrationContextProjection(
        schema_version=(
            STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION
        ),
        migration_display_text=display_text_for_status(raw_status),
        migration_status=raw_status,
        migration_basis=raw_basis,
        source_status=raw_source_status,
        source_reason=raw_source_reason,
        source_label=_echo_source_label(raw_source_label),
        runtime_consumable=False,
    )


__all__ = (
    "project_migration_context",
)
