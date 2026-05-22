"""Stage 27.5 private ping renderer.

Pure / deterministic projector that turns a Stage 27.4 combined
``LiveMeasurementContextRecord`` into a Stage 27.5
``PrivatePingPayloadRecord``. The renderer never opens a network
connection, never reads the process environment, never deduplicates
events, never enforces Stage 26 policy candidates, never decides a
trading verdict, and never produces BUY / SELL / APPROVED / GATE /
BLOCK / SAFE / ENFORCEMENT / EXECUTE / POSITION-SIZE / AUTO-TRADE
language.

Pair-aware rendering policy:

  * SOL pair on the existing-SOL lane and every measurement axis
    PRESENT and trusted -> ``RENDERED`` (clean).
  * SOL pair on the existing-SOL lane with any degraded axis (STALE
    price, MAY_INCLUDE_PRE_MIGRATION ATH, UNTRUSTED migration,
    MISSING_PRICE / MISSING_ATH / MISSING_MIGRATION, SOURCE_ERROR)
    -> ``RENDERED_WITH_WARNINGS``.
  * USDC pair -> ``RENDERED_OBSERVE_ONLY`` (Stage 27 USDC observe-
    only discipline; SOL calibration does not apply).
  * UNKNOWN pair (composition CLASSIFIED_UNKNOWN, or quote_asset
    UNKNOWN, or detection_status UNRESOLVED) -> ``RENDERED_SUPPRESSED``
    (Stage 27 live policy ``LIVE_SUPPRESS_UNKNOWN``).
  * DISAGREE pair -> ``RENDERED_SUPPRESSED`` (Stage 27 live policy
    ``LIVE_SUPPRESS_DISAGREE``).
  * Composition skipped (unsupported event kind / missing token /
    composition error) -> ``RENDERED_UNSUPPORTED``.
  * Any sub-context reporting ``UNSUPPORTED_PAIR`` ->
    ``RENDERED_UNSUPPORTED``.

This module imports only stdlib (``typing``) plus Stage 27.2 / 27.3 /
27.4 / 27.5 production modules. It does NOT import Stage 21-26
production code, does NOT import Stage 27.1 production code, does
NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process environment,
does NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage27.live_measurement_context import (
    LiveMeasurementContextRecord,
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_PARTIAL,
    MEASUREMENT_STATUS_UNSUPPORTED_PAIR,
)
from PHX2.stage27.migration_context_models import (
    MIGRATION_STATUS_MISSING,
    MIGRATION_STATUS_PRESENT,
    MIGRATION_STATUS_SOURCE_ERROR,
    MIGRATION_STATUS_UNSUPPORTED_PAIR,
    MIGRATION_STATUS_UNTRUSTED,
    MigrationContextRecord,
)
from PHX2.stage27.pair_detection_constants import (
    CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_EXISTING_SOL_LANE,
    CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_USDC_OBSERVE_ONLY,
    PAIR_DETECTION_STATUS_DISAGREE,
    PAIR_DETECTION_STATUS_UNRESOLVED,
    QUOTE_ASSET_SOL,
    QUOTE_ASSET_UNKNOWN,
    QUOTE_ASSET_USDC,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_STATUS_NOT_APPLICABLE,
    ATH_STATUS_PRESENT,
    ATH_STATUS_SOURCE_ERROR,
    ATH_STATUS_STALE,
    ATH_STATUS_UNAVAILABLE,
    ATH_STATUS_UNSUPPORTED_PAIR,
    AthContextRecord,
    PRICE_STATUS_PRESENT,
    PRICE_STATUS_SOURCE_ERROR,
    PRICE_STATUS_STALE,
    PRICE_STATUS_UNAVAILABLE,
    PRICE_STATUS_UNSUPPORTED_PAIR,
    PriceContextRecord,
)
from PHX2.stage27.private_ping_models import (
    DISPLAY_MISSING,
    DISPLAY_NONE,
    DISPLAY_NOT_APPLICABLE,
    DISPLAY_SOURCE_ERROR,
    DISPLAY_STALE,
    DISPLAY_UNAVAILABLE,
    DISPLAY_UNSUPPORTED_PAIR,
    DISPLAY_UNTRUSTED,
    PrivatePingPayloadRecord,
    RENDER_STATUS_RENDERED,
    RENDER_STATUS_RENDERED_OBSERVE_ONLY,
    RENDER_STATUS_RENDERED_SUPPRESSED,
    RENDER_STATUS_RENDERED_UNSUPPORTED,
    RENDER_STATUS_RENDERED_WITH_WARNINGS,
    STAGE27_5_PING_SCHEMA_VERSION,
)
from PHX2.stage27.provider_ingest_models import (
    COMPOSITION_STATUS_CLASSIFIED_DISAGREE,
    COMPOSITION_STATUS_CLASSIFIED_UNKNOWN,
    COMPOSITION_STATUS_COMPOSED,
    COMPOSITION_STATUS_ERROR,
    COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN,
    COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT,
)


# ---------------------------------------------------------------------------
# Render-note tokens
# ---------------------------------------------------------------------------
#
# Short safe-to-display markers a downstream operator review can pin
# on. Every value is a neutral context / status token; no trading
# verdict / enforcement / execution / position-size language.


RENDER_NOTE_LIVE_OK: str = "LIVE_OK"
RENDER_NOTE_LIVE_WARNINGS: str = "LIVE_WARNINGS"
RENDER_NOTE_LIVE_SUPPRESSED: str = "LIVE_SUPPRESSED"
RENDER_NOTE_OBSERVE_ONLY: str = "OBSERVE_ONLY"
RENDER_NOTE_UNSUPPORTED_PAIR: str = "UNSUPPORTED_PAIR"


RENDER_NOTE_VALUES: tuple[str, ...] = (
    RENDER_NOTE_LIVE_OK,
    RENDER_NOTE_LIVE_WARNINGS,
    RENDER_NOTE_LIVE_SUPPRESSED,
    RENDER_NOTE_OBSERVE_ONLY,
    RENDER_NOTE_UNSUPPORTED_PAIR,
)


# ---------------------------------------------------------------------------
# Render-status / render-note resolver
# ---------------------------------------------------------------------------


_COMPOSITION_STATUSES_SKIPPED_UPSTREAM: tuple[str, ...] = (
    COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN,
    COMPOSITION_STATUS_ERROR,
)


def _resolve_render(
    measurement_context: LiveMeasurementContextRecord,
) -> tuple[str, str]:
    """Return the ``(render_status, render_note)`` pair for ``measurement_context``.

    Precedence (highest first):

      1. Composition was skipped upstream (unsupported event kind /
         missing token / composition error) -> ``RENDERED_UNSUPPORTED``.
      2. Pair classification is ``DISAGREE`` -> ``RENDERED_SUPPRESSED``.
      3. Pair classification is ``UNRESOLVED`` (or quote_asset is
         ``UNKNOWN``) -> ``RENDERED_SUPPRESSED``.
      4. Any sub-context reports ``UNSUPPORTED_PAIR`` on an otherwise
         SOL/USDC pair -> ``RENDERED_UNSUPPORTED``.
      5. Pair is USDC -> ``RENDERED_OBSERVE_ONLY`` (Stage 27 USDC
         observe-only discipline).
      6. SOL + COMPLETE + EXISTING_SOL_LANE -> ``RENDERED``.
      7. Otherwise -> ``RENDERED_WITH_WARNINGS``.

    Pure / deterministic. Stage 27.5 NEVER routes USDC / UNKNOWN /
    DISAGREE pairs into the existing-SOL calibration lane and NEVER
    relabels a SUPPRESSED pair as RENDERED.
    """
    if (
        measurement_context.composition_status
        in _COMPOSITION_STATUSES_SKIPPED_UPSTREAM
    ):
        return (
            RENDER_STATUS_RENDERED_UNSUPPORTED,
            RENDER_NOTE_UNSUPPORTED_PAIR,
        )

    if (
        measurement_context.pair_detection_status
        == PAIR_DETECTION_STATUS_DISAGREE
    ):
        return (
            RENDER_STATUS_RENDERED_SUPPRESSED,
            RENDER_NOTE_LIVE_SUPPRESSED,
        )

    if (
        measurement_context.pair_detection_status
        == PAIR_DETECTION_STATUS_UNRESOLVED
        or measurement_context.pair_quote_asset == QUOTE_ASSET_UNKNOWN
    ):
        return (
            RENDER_STATUS_RENDERED_SUPPRESSED,
            RENDER_NOTE_LIVE_SUPPRESSED,
        )

    if (
        measurement_context.measurement_status
        == MEASUREMENT_STATUS_UNSUPPORTED_PAIR
    ):
        return (
            RENDER_STATUS_RENDERED_UNSUPPORTED,
            RENDER_NOTE_UNSUPPORTED_PAIR,
        )

    if measurement_context.pair_quote_asset == QUOTE_ASSET_USDC:
        return (
            RENDER_STATUS_RENDERED_OBSERVE_ONLY,
            RENDER_NOTE_OBSERVE_ONLY,
        )

    if (
        measurement_context.measurement_status
        == MEASUREMENT_STATUS_COMPLETE
        and measurement_context.pair_quote_asset == QUOTE_ASSET_SOL
        and measurement_context.pair_calibration_lane
        == CALIBRATION_LANE_EXISTING_SOL_LANE
    ):
        return (RENDER_STATUS_RENDERED, RENDER_NOTE_LIVE_OK)

    return (
        RENDER_STATUS_RENDERED_WITH_WARNINGS,
        RENDER_NOTE_LIVE_WARNINGS,
    )


# ---------------------------------------------------------------------------
# Display-projection helpers (canonical text for every field)
# ---------------------------------------------------------------------------


def _project_optional(value: Optional[str]) -> str:
    """Return a safe-to-display string for an optional safe field.

    Returns ``DISPLAY_NONE`` for ``None`` / empty inputs. NEVER returns
    ``"0"`` or ``"0.0"`` as a missing sentinel.
    """
    if value is None or value == "":
        return DISPLAY_NONE
    return value


def _project_price_value(price: PriceContextRecord) -> str:
    if price.price_status == PRICE_STATUS_PRESENT:
        return _project_optional(price.price_value)
    if price.price_status == PRICE_STATUS_STALE:
        if price.price_value is not None and price.price_value != "":
            return price.price_value
        return DISPLAY_STALE
    if price.price_status == PRICE_STATUS_UNAVAILABLE:
        return DISPLAY_UNAVAILABLE
    if price.price_status == PRICE_STATUS_SOURCE_ERROR:
        return DISPLAY_SOURCE_ERROR
    if price.price_status == PRICE_STATUS_UNSUPPORTED_PAIR:
        return DISPLAY_UNSUPPORTED_PAIR
    return DISPLAY_NONE


def _project_price_unit(price: PriceContextRecord) -> str:
    if price.price_status in (
        PRICE_STATUS_UNAVAILABLE,
        PRICE_STATUS_SOURCE_ERROR,
        PRICE_STATUS_UNSUPPORTED_PAIR,
    ):
        if price.price_unit:
            return price.price_unit
        return DISPLAY_UNAVAILABLE
    return price.price_unit if price.price_unit else DISPLAY_NONE


def _project_price_source(price: PriceContextRecord) -> str:
    if price.price_status == PRICE_STATUS_UNAVAILABLE:
        return _project_optional(price.price_source) if price.price_source else DISPLAY_UNAVAILABLE
    if price.price_status == PRICE_STATUS_SOURCE_ERROR:
        return _project_optional(price.price_source) if price.price_source else DISPLAY_SOURCE_ERROR
    if price.price_status == PRICE_STATUS_UNSUPPORTED_PAIR:
        return _project_optional(price.price_source) if price.price_source else DISPLAY_UNSUPPORTED_PAIR
    return _project_optional(price.price_source)


def _project_price_staleness(price: PriceContextRecord) -> str:
    if price.staleness_seconds is None:
        if price.price_status == PRICE_STATUS_UNAVAILABLE:
            return DISPLAY_UNAVAILABLE
        if price.price_status == PRICE_STATUS_SOURCE_ERROR:
            return DISPLAY_SOURCE_ERROR
        if price.price_status == PRICE_STATUS_UNSUPPORTED_PAIR:
            return DISPLAY_UNSUPPORTED_PAIR
        return DISPLAY_NONE
    return str(price.staleness_seconds)


def _project_ath_value(ath: AthContextRecord) -> str:
    if ath.ath_status == ATH_STATUS_PRESENT:
        return _project_optional(ath.ath_value)
    if ath.ath_status == ATH_STATUS_STALE:
        if ath.ath_value is not None and ath.ath_value != "":
            return ath.ath_value
        return DISPLAY_STALE
    if ath.ath_status == ATH_STATUS_UNAVAILABLE:
        return DISPLAY_UNAVAILABLE
    if ath.ath_status == ATH_STATUS_NOT_APPLICABLE:
        return DISPLAY_NOT_APPLICABLE
    if ath.ath_status == ATH_STATUS_SOURCE_ERROR:
        return DISPLAY_SOURCE_ERROR
    if ath.ath_status == ATH_STATUS_UNSUPPORTED_PAIR:
        return DISPLAY_UNSUPPORTED_PAIR
    return DISPLAY_NONE


def _project_ath_unit(ath: AthContextRecord) -> str:
    return ath.ath_unit if ath.ath_unit else DISPLAY_NONE


def _project_ath_since_migration(ath: AthContextRecord) -> str:
    if not ath.ath_since_migration_status:
        return DISPLAY_NONE
    return ath.ath_since_migration_status


def _project_drawdown(ath: AthContextRecord) -> str:
    if ath.drawdown_from_ath is None or ath.drawdown_from_ath == "":
        if ath.ath_status == ATH_STATUS_UNAVAILABLE:
            return DISPLAY_UNAVAILABLE
        if ath.ath_status == ATH_STATUS_SOURCE_ERROR:
            return DISPLAY_SOURCE_ERROR
        if ath.ath_status == ATH_STATUS_UNSUPPORTED_PAIR:
            return DISPLAY_UNSUPPORTED_PAIR
        if ath.ath_status == ATH_STATUS_NOT_APPLICABLE:
            return DISPLAY_NOT_APPLICABLE
        return DISPLAY_NOT_APPLICABLE
    return ath.drawdown_from_ath


def _project_drawdown_basis(ath: AthContextRecord) -> str:
    if not ath.drawdown_basis:
        return DISPLAY_NONE
    return ath.drawdown_basis


def _project_migration_timestamp(
    migration: MigrationContextRecord,
) -> str:
    if (
        migration.migration_status == MIGRATION_STATUS_PRESENT
        or migration.migration_status == MIGRATION_STATUS_UNTRUSTED
    ):
        return _project_optional(migration.migration_timestamp_utc)
    if migration.migration_status == MIGRATION_STATUS_MISSING:
        return DISPLAY_MISSING
    if migration.migration_status == MIGRATION_STATUS_SOURCE_ERROR:
        return DISPLAY_SOURCE_ERROR
    if (
        migration.migration_status
        == MIGRATION_STATUS_UNSUPPORTED_PAIR
    ):
        return DISPLAY_UNSUPPORTED_PAIR
    return DISPLAY_NONE


def _project_migration_age(migration: MigrationContextRecord) -> str:
    if migration.age_since_migration_seconds is None:
        if migration.migration_status == MIGRATION_STATUS_MISSING:
            return DISPLAY_MISSING
        if (
            migration.migration_status == MIGRATION_STATUS_UNTRUSTED
        ):
            return DISPLAY_UNTRUSTED
        if (
            migration.migration_status
            == MIGRATION_STATUS_SOURCE_ERROR
        ):
            return DISPLAY_SOURCE_ERROR
        if (
            migration.migration_status
            == MIGRATION_STATUS_UNSUPPORTED_PAIR
        ):
            return DISPLAY_UNSUPPORTED_PAIR
        return DISPLAY_NONE
    return str(migration.age_since_migration_seconds)


def _project_migration_source(
    migration: MigrationContextRecord,
) -> str:
    return migration.migration_source if migration.migration_source else DISPLAY_NONE


# ---------------------------------------------------------------------------
# Plain-text body rendering
# ---------------------------------------------------------------------------


def _render_body_text(
    payload_fields: dict,
    measurement_context: LiveMeasurementContextRecord,
) -> str:
    """Return the deterministic plain-text body for the ping payload.

    Field ordering is fixed. Whitespace ordering is fixed. Every line
    is ``<label>: <value>``. No BUY / SELL / APPROVED / GATE / BLOCK /
    SAFE / ENFORCEMENT / EXECUTE / POSITION-SIZE / AUTO-TRADE
    language is admitted.
    """
    warnings = measurement_context.measurement_warnings
    warnings_display = (
        ", ".join(warnings) if warnings else DISPLAY_NONE
    )

    lines: list[str] = []
    lines.append("PHX2 STAGE 27.5 PRIVATE DRY-RUN PING")
    lines.append(f"ping_id: {payload_fields['ping_id']}")
    lines.append(
        f"run_id: {_project_optional(payload_fields['run_id'])}"
    )
    lines.append(
        f"session_id: "
        f"{_project_optional(payload_fields['session_id'])}"
    )
    lines.append(
        f"ping_schema_version: "
        f"{payload_fields['ping_schema_version']}"
    )

    lines.append("")
    lines.append("PROVENANCE")
    lines.append(
        f"provider_id: "
        f"{_project_optional(payload_fields['provider_id'])}"
    )
    lines.append(
        f"provider_event_id: "
        f"{_project_optional(payload_fields['provider_event_id'])}"
    )
    lines.append(
        f"normalized_event_id: "
        f"{_project_optional(payload_fields['normalized_event_id'])}"
    )
    lines.append(
        f"raw_capture_ref: "
        f"{_project_optional(payload_fields['raw_capture_ref'])}"
    )

    lines.append("")
    lines.append("TOKEN")
    lines.append(
        f"token_mint: "
        f"{_project_optional(payload_fields['token_mint'])}"
    )
    lines.append(
        f"quote_mint: "
        f"{_project_optional(payload_fields['quote_mint'])}"
    )

    lines.append("")
    lines.append("PAIR")
    lines.append(f"pair_type: {payload_fields['pair_type']}")
    lines.append(f"quote_asset: {payload_fields['quote_asset']}")
    lines.append(
        f"bonding_curve_version: "
        f"{payload_fields['bonding_curve_version']}"
    )
    lines.append(
        f"pair_detection_status: "
        f"{payload_fields['pair_detection_status']}"
    )
    lines.append(
        f"pair_detection_confidence: "
        f"{payload_fields['pair_detection_confidence']}"
    )
    lines.append(
        f"pair_detection_reason: "
        f"{payload_fields['pair_detection_reason']}"
    )
    lines.append(
        f"pair_live_policy: "
        f"{payload_fields['pair_live_policy']}"
    )
    lines.append(
        f"calibration_lane: "
        f"{payload_fields['calibration_lane']}"
    )

    lines.append("")
    lines.append("PRICE")
    lines.append(
        f"price_status: {payload_fields['price_status']}"
    )
    lines.append(
        f"price_value: {payload_fields['price_value_display']}"
    )
    lines.append(
        f"price_unit: {payload_fields['price_unit_display']}"
    )
    lines.append(
        f"price_source: "
        f"{payload_fields['price_source_display']}"
    )
    lines.append(
        f"price_staleness_seconds: "
        f"{payload_fields['price_staleness_seconds_display']}"
    )

    lines.append("")
    lines.append("ATH")
    lines.append(f"ath_status: {payload_fields['ath_status']}")
    lines.append(
        f"ath_value: {payload_fields['ath_value_display']}"
    )
    lines.append(
        f"ath_unit: {payload_fields['ath_unit_display']}"
    )
    lines.append(
        f"ath_since_migration: "
        f"{payload_fields['ath_since_migration_status_display']}"
    )
    lines.append(
        f"drawdown: {payload_fields['drawdown_display']}"
    )
    lines.append(
        f"drawdown_basis: "
        f"{payload_fields['drawdown_basis_display']}"
    )

    lines.append("")
    lines.append("MIGRATION")
    lines.append(
        f"migration_status: "
        f"{payload_fields['migration_status']}"
    )
    lines.append(
        f"migration_timestamp_utc: "
        f"{payload_fields['migration_timestamp_display']}"
    )
    lines.append(
        f"migration_age_seconds: "
        f"{payload_fields['migration_age_seconds_display']}"
    )
    lines.append(
        f"migration_source: "
        f"{payload_fields['migration_source_display']}"
    )

    lines.append("")
    lines.append("MEASUREMENT")
    lines.append(
        f"measurement_status: "
        f"{payload_fields['measurement_status']}"
    )
    lines.append(f"measurement_warnings: {warnings_display}")

    lines.append("")
    lines.append("RENDER")
    lines.append(
        f"render_status: {payload_fields['render_status']}"
    )
    lines.append(
        f"render_note: {payload_fields['render_note']}"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public renderer
# ---------------------------------------------------------------------------


def render_private_ping(
    measurement_context: LiveMeasurementContextRecord,
    ping_id: str,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> PrivatePingPayloadRecord:
    """Render a Stage 27.5 private dry-run ping payload.

    Pure / deterministic. NEVER opens a network connection, NEVER
    reads the process environment, NEVER deduplicates events, NEVER
    enforces Stage 26 policy candidates, NEVER decides a trading
    verdict, NEVER widens the closed-set vocabulary.

    Arguments:

      * ``measurement_context`` -- Stage 27.4 combined live
        measurement context record.
      * ``ping_id``             -- caller-supplied stable ping
        identifier (must be a non-empty string).
      * ``run_id``              -- caller-supplied run identifier.
        ``None`` when not attached yet.
      * ``session_id``          -- caller-supplied session identifier.
        ``None`` when not attached yet.
    """
    if not isinstance(
        measurement_context, LiveMeasurementContextRecord
    ):
        raise TypeError(
            "render_private_ping requires a "
            "LiveMeasurementContextRecord"
        )
    if not isinstance(ping_id, str) or ping_id == "":
        raise ValueError(
            "render_private_ping requires a non-empty ping_id"
        )

    render_status, render_note = _resolve_render(measurement_context)

    price = measurement_context.price_context
    ath = measurement_context.ath_context
    migration = measurement_context.migration_context

    payload_fields = {
        "ping_id": ping_id,
        "run_id": run_id,
        "session_id": session_id,
        "ping_schema_version": STAGE27_5_PING_SCHEMA_VERSION,
        "provider_id": measurement_context.provider_id,
        "provider_event_id": (
            measurement_context.provider_event_id
        ),
        "normalized_event_id": (
            measurement_context.normalized_event_id
        ),
        "raw_capture_ref": (
            measurement_context.raw_capture_ref
        ),
        "token_mint": measurement_context.token_mint,
        "quote_mint": measurement_context.quote_mint,
        "pair_type": measurement_context.pair_pair_type,
        "quote_asset": measurement_context.pair_quote_asset,
        "bonding_curve_version": (
            measurement_context.pair_bonding_curve_version
        ),
        "pair_detection_status": (
            measurement_context.pair_detection_status
        ),
        "pair_detection_confidence": (
            measurement_context.pair_detection_confidence
        ),
        "pair_detection_reason": (
            measurement_context.pair_detection_reason
        ),
        "pair_live_policy": (
            measurement_context.pair_live_policy
        ),
        "calibration_lane": (
            measurement_context.pair_calibration_lane
        ),
        "measurement_status": (
            measurement_context.measurement_status
        ),
        "measurement_warnings": (
            measurement_context.measurement_warnings
        ),
        "price_status": price.price_status,
        "price_value_display": _project_price_value(price),
        "price_unit_display": _project_price_unit(price),
        "price_source_display": _project_price_source(price),
        "price_staleness_seconds_display": (
            _project_price_staleness(price)
        ),
        "ath_status": ath.ath_status,
        "ath_value_display": _project_ath_value(ath),
        "ath_unit_display": _project_ath_unit(ath),
        "ath_since_migration_status_display": (
            _project_ath_since_migration(ath)
        ),
        "drawdown_display": _project_drawdown(ath),
        "drawdown_basis_display": _project_drawdown_basis(ath),
        "migration_status": migration.migration_status,
        "migration_timestamp_display": (
            _project_migration_timestamp(migration)
        ),
        "migration_age_seconds_display": (
            _project_migration_age(migration)
        ),
        "migration_source_display": (
            _project_migration_source(migration)
        ),
        "render_status": render_status,
        "render_note": render_note,
    }

    # Stage 27 locked invariant: USDC / UNKNOWN / DISAGREE pairs MUST
    # NOT render the existing-SOL calibration lane. The Stage 27.4
    # composer enforces this upstream; the assertion below is a
    # defensive pin so a future refactor cannot silently widen.
    assert not (
        payload_fields["quote_asset"]
        in (QUOTE_ASSET_USDC, QUOTE_ASSET_UNKNOWN)
        and payload_fields["calibration_lane"]
        == CALIBRATION_LANE_EXISTING_SOL_LANE
    )
    assert not (
        payload_fields["pair_detection_status"]
        == PAIR_DETECTION_STATUS_DISAGREE
        and payload_fields["calibration_lane"]
        == CALIBRATION_LANE_EXISTING_SOL_LANE
    )

    body_text = _render_body_text(
        payload_fields, measurement_context
    )

    return PrivatePingPayloadRecord(
        ping_id=ping_id,
        run_id=run_id,
        session_id=session_id,
        ping_schema_version=STAGE27_5_PING_SCHEMA_VERSION,
        provider_id=measurement_context.provider_id,
        provider_event_id=(
            measurement_context.provider_event_id
        ),
        normalized_event_id=(
            measurement_context.normalized_event_id
        ),
        raw_capture_ref=measurement_context.raw_capture_ref,
        token_mint=measurement_context.token_mint,
        quote_mint=measurement_context.quote_mint,
        pair_type=measurement_context.pair_pair_type,
        quote_asset=measurement_context.pair_quote_asset,
        bonding_curve_version=(
            measurement_context.pair_bonding_curve_version
        ),
        pair_detection_status=(
            measurement_context.pair_detection_status
        ),
        pair_detection_confidence=(
            measurement_context.pair_detection_confidence
        ),
        pair_detection_reason=(
            measurement_context.pair_detection_reason
        ),
        pair_live_policy=(
            measurement_context.pair_live_policy
        ),
        calibration_lane=(
            measurement_context.pair_calibration_lane
        ),
        measurement_status=(
            measurement_context.measurement_status
        ),
        measurement_warnings=tuple(
            measurement_context.measurement_warnings
        ),
        price_status=price.price_status,
        price_value_display=payload_fields["price_value_display"],
        price_unit_display=payload_fields["price_unit_display"],
        price_source_display=(
            payload_fields["price_source_display"]
        ),
        price_staleness_seconds_display=(
            payload_fields["price_staleness_seconds_display"]
        ),
        ath_status=ath.ath_status,
        ath_value_display=payload_fields["ath_value_display"],
        ath_unit_display=payload_fields["ath_unit_display"],
        ath_since_migration_status_display=(
            payload_fields["ath_since_migration_status_display"]
        ),
        drawdown_display=payload_fields["drawdown_display"],
        drawdown_basis_display=(
            payload_fields["drawdown_basis_display"]
        ),
        migration_status=migration.migration_status,
        migration_timestamp_display=(
            payload_fields["migration_timestamp_display"]
        ),
        migration_age_seconds_display=(
            payload_fields["migration_age_seconds_display"]
        ),
        migration_source_display=(
            payload_fields["migration_source_display"]
        ),
        render_status=render_status,
        render_note=render_note,
        body_text=body_text,
    )


# Calibration-lane lookup the renderer mirrors verbatim from the
# Stage 27.4 measurement context. Stage 27.5 never derives a lane
# itself; the constants below exist only so a downstream consumer
# can pin the Stage 27.5 lane vocabulary against the Stage 27.2 set.
RENDERED_CALIBRATION_LANES_NON_SOL: tuple[str, ...] = (
    CALIBRATION_LANE_USDC_OBSERVE_ONLY,
    CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
    CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
)
