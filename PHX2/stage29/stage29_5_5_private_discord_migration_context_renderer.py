"""Stage 29.5.5 private discord migration context renderer.

Pure / deterministic projector that turns a Stage 29.5
``Stage29_5PrivatePingMigrationContext`` into a Stage 29.5.5
``Stage29_5_5RenderedMigrationContextBlock``.

The renderer NEVER opens a network connection, NEVER reads the
process environment, NEVER deduplicates calls, NEVER enforces
Stage 26 policy candidates, NEVER decides a trading verdict,
NEVER widens the closed-set output vocabulary, NEVER mutates
its input, and NEVER produces BUY / SELL / APPROVED / GATE /
BLOCK / SAFE / ENFORCEMENT / EXECUTE / POSITION-SIZE /
AUTO-TRADE language.

Mapping discipline (closed-set; see Stage 29.5.5 runbook
Section 5):

  * Section 5.1 — ``measurement_status`` -> closed-set
    ``migration_evidence_status_display`` (5 cases).
  * Section 5.2 — ``(measurement_status, migration_source)``
    pair -> closed-set
    ``migration_evidence_source_trust_display`` (precedence-
    resolved; ``COMPLETE`` with ``SYNTHETIC_TEST_ONLY`` or
    ``UNKNOWN`` NEVER promotes to ``SOURCE_TRUSTED_ON_CHAIN``).
  * Section 5.3 — ``post_migration_ath_verified`` (``True`` /
    ``False`` / ``None``) -> closed-set
    ``post_migration_ath_verified_display`` (3 cases).
  * Section 5.4 — echo fields for timestamp / slot / source /
    join-status / warnings / observation timestamp.
  * Section 5.5 — pinned ``informational_only = True`` and
    ``not_a_trading_verdict = True`` flags.

The renderer validates its input shape and rejects:

  * a non-``Stage29_5PrivatePingMigrationContext`` projection
    with ``ValueError``,
  * a projection carrying a non-``SAFE`` ``redaction_status``
    with ``ValueError`` (defensive; the Stage 29.5 projection
    validator already locks this),
  * a projection carrying a non-``NOT_ACTIVE_STAGE_29_PENDING``
    ``filter_enforcement_status`` with ``ValueError``
    (defensive; same Stage 29.5 projection lock).

This module imports stdlib (``typing``) plus the Stage 29.5
projection models module and the Stage 29.5.5 render models
module. It does NOT import any Stage 21-26 / Stage 28 / Stage
29.1 / Stage 29.2 / Stage 29.3 / Stage 29.4 production module,
any network / RPC / messaging / DB / scheduler / secrets-
management library, any legacy / pre-PHX2 module, the process
environment, or the filesystem. It defines no CLI surface. It
contains no top-level Call (the only admitted module-body Call
shape is ``@dataclass(...)`` and this module ships zero
``@dataclass`` classes).
"""

from __future__ import annotations

from typing import Optional, Tuple

from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    MEASUREMENT_STATUS_INVALID_MIGRATION,
    MEASUREMENT_STATUS_MISSING_MIGRATION,
    MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    REDACTION_STATUS_SAFE,
    Stage29_5PrivatePingMigrationContext,
)
from PHX2.stage29.stage29_5_5_render_models import (
    DISPLAY_TOKEN_MISSING,
    DISPLAY_TOKEN_NONE,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_SYNTHETIC,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_SYNTHETIC,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_UNKNOWN,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_CONFLICTING,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_INVALID,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_MISSING,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_PARTIAL,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_NOT_VERIFIED,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_UNKNOWN,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED,
    STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION,
    Stage29_5_5RenderedMigrationContextBlock,
)


# ---------------------------------------------------------------------------
# Renderer schema version pin
# ---------------------------------------------------------------------------


STAGE29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERER_SCHEMA_VERSION: str = (
    "stage29_5_5_v0_private_discord_migration_context_renderer"
)


# ---------------------------------------------------------------------------
# Trusted-source set (Stage 29.5.5 mirrors the Stage 29.5.4 adapter
# definition: HELIUS_WS / STAGE29_MIGRATION_ARTIFACT are the only
# trusted on-chain sources; SYNTHETIC_TEST_ONLY and UNKNOWN are
# never trusted).
# ---------------------------------------------------------------------------


_TRUSTED_ON_CHAIN_SOURCES: Tuple[str, ...] = (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
)


# ---------------------------------------------------------------------------
# Section 5.1 mapping: measurement_status -> evidence_status_display
# ---------------------------------------------------------------------------


_MEASUREMENT_STATUS_DISPLAY_MAP: dict[str, str] = {
    MEASUREMENT_STATUS_COMPLETE: (
        MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE
    ),
    MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT: (
        MIGRATION_EVIDENCE_STATUS_DISPLAY_PARTIAL
    ),
    MEASUREMENT_STATUS_MISSING_MIGRATION: (
        MIGRATION_EVIDENCE_STATUS_DISPLAY_MISSING
    ),
    MEASUREMENT_STATUS_INVALID_MIGRATION: (
        MIGRATION_EVIDENCE_STATUS_DISPLAY_INVALID
    ),
    MEASUREMENT_STATUS_CONFLICTING_MIGRATION: (
        MIGRATION_EVIDENCE_STATUS_DISPLAY_CONFLICTING
    ),
}


def _resolve_evidence_status_display(
    measurement_status: str,
) -> str:
    display = _MEASUREMENT_STATUS_DISPLAY_MAP.get(
        measurement_status,
    )
    if display is None:
        # The Stage 29.5 projection validator pins
        # measurement_status to the 5 closed-set tokens; an
        # unrecognized value can only reach here via a hand-
        # crafted projection that bypassed the validator. The
        # renderer refuses such inputs.
        raise ValueError(
            "Stage 29.5.5 renderer: unrecognized "
            f"measurement_status {measurement_status!r}"
        )
    return display


# ---------------------------------------------------------------------------
# Section 5.2 mapping: (measurement_status, migration_source)
# -> source_trust_display
# ---------------------------------------------------------------------------


def _resolve_source_trust_display(
    measurement_status: str,
    migration_source: str,
) -> str:
    is_complete = (
        measurement_status == MEASUREMENT_STATUS_COMPLETE
    )
    is_missing = (
        measurement_status == MEASUREMENT_STATUS_MISSING_MIGRATION
    )
    is_trusted_source = (
        migration_source in _TRUSTED_ON_CHAIN_SOURCES
    )
    is_synthetic_source = (
        migration_source == MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY
    )
    is_unknown_source = (
        migration_source == MIGRATION_SOURCE_UNKNOWN_STAGE29_5
    )
    if is_missing:
        # MISSING_MIGRATION ALWAYS degrades to NO_SOURCE
        # regardless of the migration_source token (the
        # projection should also have UNKNOWN source on the
        # MISSING branch, but we render conservatively).
        return MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE
    if is_complete:
        if is_trusted_source:
            return (
                MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN
            )
        if is_synthetic_source:
            return (
                MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_SYNTHETIC
            )
        # COMPLETE + UNKNOWN (or any other non-trusted, non-
        # synthetic value) -> UNTRUSTED_UNKNOWN. The Stage 29.5
        # projection validator pins migration_source to the 4
        # closed-set tokens so this branch only fires for
        # COMPLETE + UNKNOWN.
        if is_unknown_source:
            return (
                MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_UNKNOWN
            )
        # Defensive: unrecognized migration_source value reaching
        # here would be a contract violation; collapse to
        # UNTRUSTED_UNKNOWN so the renderer never promotes to
        # TRUSTED_ON_CHAIN.
        return (
            MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_UNKNOWN
        )
    # Non-COMPLETE, non-MISSING branches (PARTIAL / INVALID /
    # CONFLICTING). Source-trust collapses to PARTIAL_* or
    # NO_SOURCE based on the migration_source token.
    if is_trusted_source:
        return (
            MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN
        )
    if is_synthetic_source:
        return (
            MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_SYNTHETIC
        )
    return MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE


# ---------------------------------------------------------------------------
# Section 5.3 mapping: post_migration_ath_verified
# -> post_migration_ath_verified_display
# ---------------------------------------------------------------------------


def _resolve_post_migration_ath_verified_display(
    post_migration_ath_verified: Optional[bool],
) -> str:
    if post_migration_ath_verified is True:
        return (
            POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED
        )
    if post_migration_ath_verified is False:
        return (
            POST_MIGRATION_ATH_VERIFIED_DISPLAY_NOT_VERIFIED
        )
    # Includes the None branch and any defensive non-bool value
    # (the Stage 29.5 projection validator pins this field to
    # bool or None).
    return POST_MIGRATION_ATH_VERIFIED_DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# Section 5.4 echo helpers
# ---------------------------------------------------------------------------


def _project_migration_timestamp_display(
    migration_timestamp_utc: Optional[str],
) -> str:
    if migration_timestamp_utc is None:
        return DISPLAY_TOKEN_MISSING
    return migration_timestamp_utc


def _project_migration_slot_display(
    migration_slot: Optional[int],
) -> str:
    if migration_slot is None:
        return DISPLAY_TOKEN_MISSING
    return str(migration_slot)


def _project_warnings_display(
    warnings: Tuple[str, ...],
) -> str:
    if not warnings:
        return DISPLAY_TOKEN_NONE
    return ", ".join(warnings)


# ---------------------------------------------------------------------------
# body_text rendering
# ---------------------------------------------------------------------------


def _render_body_text(
    *,
    schema_version: str,
    filter_enforcement_status: str,
    redaction_status: str,
    evidence_status_display: str,
    source_trust_display: str,
    migration_source_token: str,
    join_status_echoed_token: str,
    migration_timestamp_display: str,
    migration_slot_display: str,
    ath_verified_display: str,
    warnings_display: str,
    observed_at_utc: str,
) -> str:
    """Return the deterministic plain-text body for the Stage
    29.5.5 rendered block.

    Field ordering is fixed. Whitespace ordering is fixed. Every
    line is ``<label>: <value>``. Sections are separated by a
    single blank line. The body text never contains BUY / SELL /
    APPROVED / GATE / BLOCK / SAFE / ENFORCEMENT / EXECUTE /
    POSITION-SIZE / AUTO-TRADE verdict language.
    """
    lines: list[str] = []
    lines.append(
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
    )
    lines.append(f"schema_version: {schema_version}")
    lines.append("informational_only: true")
    lines.append("not_a_trading_verdict: true")
    lines.append(
        f"filter_enforcement_status: "
        f"{filter_enforcement_status}"
    )
    lines.append(f"redaction_status: {redaction_status}")
    lines.append("")
    lines.append("MIGRATION")
    lines.append(
        f"migration_evidence_status: "
        f"{evidence_status_display}"
    )
    lines.append(
        f"migration_evidence_source_trust: "
        f"{source_trust_display}"
    )
    lines.append(
        f"migration_source: {migration_source_token}"
    )
    lines.append(f"join_status: {join_status_echoed_token}")
    lines.append(
        f"migration_timestamp_utc: "
        f"{migration_timestamp_display}"
    )
    lines.append(f"migration_slot: {migration_slot_display}")
    lines.append("")
    lines.append("ATH")
    lines.append(
        f"post_migration_ath_verified: "
        f"{ath_verified_display}"
    )
    lines.append("")
    lines.append("WARNINGS")
    lines.append(f"warnings: {warnings_display}")
    lines.append("")
    lines.append("OBSERVATION")
    lines.append(f"observed_at_utc: {observed_at_utc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------


def render_private_discord_migration_context_block(
    projection: Stage29_5PrivatePingMigrationContext,
) -> Stage29_5_5RenderedMigrationContextBlock:
    """Render a Stage 29.5.5 private migration context block from
    a Stage 29.5 projection.

    Pure / deterministic. NEVER opens a network connection,
    NEVER reads the process environment, NEVER touches a wallet
    / private-key / signer surface, NEVER produces a trading
    verdict, NEVER widens the closed-set output vocabulary.

    Raises ``ValueError`` when ``projection`` is not a
    ``Stage29_5PrivatePingMigrationContext`` instance, or when
    ``projection.redaction_status`` is not ``SAFE``, or when
    ``projection.filter_enforcement_status`` is not
    ``NOT_ACTIVE_STAGE_29_PENDING``. (The Stage 29.5 projection
    validator already locks these two fields; the renderer
    re-checks defensively so a hand-crafted projection that
    bypassed the validator cannot smuggle a non-SAFE / non-
    locked block past the renderer's contract.)
    """
    if not isinstance(
        projection, Stage29_5PrivatePingMigrationContext,
    ):
        raise ValueError(
            "Stage 29.5.5 renderer: projection must be a "
            "Stage29_5PrivatePingMigrationContext instance; "
            f"got {type(projection).__name__}"
        )
    if projection.redaction_status != REDACTION_STATUS_SAFE:
        raise ValueError(
            "Stage 29.5.5 renderer: projection.redaction_status "
            "must be SAFE; got "
            f"{projection.redaction_status!r}"
        )
    if (
        projection.filter_enforcement_status
        != FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    ):
        raise ValueError(
            "Stage 29.5.5 renderer: "
            "projection.filter_enforcement_status must be "
            "NOT_ACTIVE_STAGE_29_PENDING; got "
            f"{projection.filter_enforcement_status!r}"
        )
    evidence_status_display = _resolve_evidence_status_display(
        projection.measurement_status,
    )
    source_trust_display = _resolve_source_trust_display(
        projection.measurement_status,
        projection.migration_source,
    )
    ath_verified_display = (
        _resolve_post_migration_ath_verified_display(
            projection.post_migration_ath_verified,
        )
    )
    migration_timestamp_display = (
        _project_migration_timestamp_display(
            projection.migration_timestamp_utc,
        )
    )
    migration_slot_display = _project_migration_slot_display(
        projection.migration_slot,
    )
    warnings_display = _project_warnings_display(
        projection.warnings,
    )
    body_text = _render_body_text(
        schema_version=(
            STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION
        ),
        filter_enforcement_status=(
            projection.filter_enforcement_status
        ),
        redaction_status=projection.redaction_status,
        evidence_status_display=evidence_status_display,
        source_trust_display=source_trust_display,
        migration_source_token=projection.migration_source,
        join_status_echoed_token=(
            projection.join_status_echoed
        ),
        migration_timestamp_display=(
            migration_timestamp_display
        ),
        migration_slot_display=migration_slot_display,
        ath_verified_display=ath_verified_display,
        warnings_display=warnings_display,
        observed_at_utc=projection.observed_at_utc,
    )
    return Stage29_5_5RenderedMigrationContextBlock(
        migration_evidence_status_display=(
            evidence_status_display
        ),
        migration_evidence_source_trust_display=(
            source_trust_display
        ),
        post_migration_ath_verified_display=(
            ath_verified_display
        ),
        migration_timestamp_utc_display=(
            migration_timestamp_display
        ),
        migration_slot_display=migration_slot_display,
        migration_source_token=projection.migration_source,
        join_status_echoed_token=(
            projection.join_status_echoed
        ),
        warnings_display=warnings_display,
        redaction_status=projection.redaction_status,
        filter_enforcement_status=(
            projection.filter_enforcement_status
        ),
        observed_at_utc=projection.observed_at_utc,
        informational_only=True,
        not_a_trading_verdict=True,
        body_text=body_text,
    )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = (
    "STAGE29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERER_SCHEMA_VERSION",
    "render_private_discord_migration_context_block",
)
