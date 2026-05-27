"""Stage 29.5.5 renderer correctness tests.

Pins:

  * ``render_private_discord_migration_context_block`` is a
    pure function — same input -> same output.
  * The renderer rejects non-projection inputs with
    ``ValueError``.
  * The renderer rejects projections carrying a non-``SAFE``
    redaction_status with ``ValueError``.
  * The renderer rejects projections carrying a non-
    ``NOT_ACTIVE_STAGE_29_PENDING`` filter_enforcement_status
    with ``ValueError``.
  * Every rendered block carries ``informational_only = True``,
    ``not_a_trading_verdict = True``, ``redaction_status =
    SAFE``, ``filter_enforcement_status =
    NOT_ACTIVE_STAGE_29_PENDING``.
  * The ``body_text`` plain-text rendering has a deterministic
    line ordering and label vocabulary.
  * Missing timestamp / slot render as the ``MISSING`` literal.
  * Empty warnings tuple renders as the ``NONE`` literal.
  * Non-empty warnings render comma-joined in input order.
  * The renderer schema version constant pins the canonical
    Stage 29.5.5 value.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_MISSING_MIGRATION,
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_JOIN_STATUS_NO_MATCH,
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    Stage29_5PrivatePingMigrationContext,
    WARNING_MIGRATION_MISSING,
    WARNING_POST_MIGRATION_ATH_UNVERIFIED,
)
from PHX2.stage29.stage29_5_5_private_discord_migration_context_renderer import (
    STAGE29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERER_SCHEMA_VERSION,
    render_private_discord_migration_context_block,
)
from PHX2.stage29.stage29_5_5_render_models import (
    DISPLAY_TOKEN_MISSING,
    DISPLAY_TOKEN_NONE,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_MISSING,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_UNKNOWN,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED,
    STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION,
    Stage29_5_5RenderedMigrationContextBlock,
)


_OBSERVED_AT: str = "2026-01-01T00:00:00+00:00"
_MIGRATION_TS: str = "2026-01-01T00:00:05+00:00"


def _build_complete_trusted_verified_projection() -> (
    Stage29_5PrivatePingMigrationContext
):
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=MEASUREMENT_STATUS_COMPLETE,
        warnings=(),
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=12345,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        post_migration_ath_verified=True,
        join_status_echoed=MIGRATION_JOIN_STATUS_JOINED,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_OBSERVED_AT,
    )


def _build_missing_projection() -> (
    Stage29_5PrivatePingMigrationContext
):
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=MEASUREMENT_STATUS_MISSING_MIGRATION,
        warnings=(
            WARNING_MIGRATION_MISSING,
            WARNING_POST_MIGRATION_ATH_UNVERIFIED,
        ),
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_source=MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        post_migration_ath_verified=None,
        join_status_echoed=MIGRATION_JOIN_STATUS_NO_MATCH,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_OBSERVED_AT,
    )


# ---------------------------------------------------------------------------
# Schema version pin
# ---------------------------------------------------------------------------


def test_renderer_schema_version_pin() -> None:
    assert (
        STAGE29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERER_SCHEMA_VERSION
        == "stage29_5_5_v0_private_discord_migration_context_renderer"
    )


# ---------------------------------------------------------------------------
# Input-shape validation
# ---------------------------------------------------------------------------


def test_renderer_rejects_non_projection_input() -> None:
    with pytest.raises(ValueError):
        render_private_discord_migration_context_block("not-a-projection")  # type: ignore[arg-type]


def test_renderer_rejects_none_input() -> None:
    with pytest.raises(ValueError):
        render_private_discord_migration_context_block(None)  # type: ignore[arg-type]


def test_renderer_rejects_dict_input() -> None:
    with pytest.raises(ValueError):
        render_private_discord_migration_context_block({"x": 1})  # type: ignore[arg-type]


# The Stage 29.5 projection validator already pins redaction +
# filter_enforcement; the renderer's defensive re-check fires
# when someone hand-constructs a malformed projection via, e.g.,
# ``object.__setattr__``. We exercise that path here so the
# defensive guard is covered.


def test_renderer_rejects_non_safe_redaction_status() -> None:
    projection = _build_complete_trusted_verified_projection()
    object.__setattr__(
        projection,
        "redaction_status",
        REDACTION_STATUS_REDACTED,
    )
    with pytest.raises(ValueError):
        render_private_discord_migration_context_block(projection)


def test_renderer_rejects_non_locked_enforcement_status() -> None:
    projection = _build_complete_trusted_verified_projection()
    object.__setattr__(
        projection,
        "filter_enforcement_status",
        "ENFORCEMENT_ACTIVE",
    )
    with pytest.raises(ValueError):
        render_private_discord_migration_context_block(projection)


# ---------------------------------------------------------------------------
# Output shape pins
# ---------------------------------------------------------------------------


def test_renderer_output_is_rendered_block_instance() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert isinstance(
        block, Stage29_5_5RenderedMigrationContextBlock,
    )


def test_renderer_output_pins_informational_only_true() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert block.informational_only is True


def test_renderer_output_pins_not_a_trading_verdict_true() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert block.not_a_trading_verdict is True


def test_renderer_output_pins_redaction_status_safe() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert block.redaction_status == REDACTION_STATUS_SAFE


def test_renderer_output_pins_filter_enforcement_locked() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert (
        block.filter_enforcement_status
        == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )


def test_renderer_output_pins_block_schema_version() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert (
        block.schema_version
        == STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION
    )


# ---------------------------------------------------------------------------
# Echo fields
# ---------------------------------------------------------------------------


def test_renderer_echoes_migration_timestamp_when_present() -> None:
    projection = _build_complete_trusted_verified_projection()
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert (
        block.migration_timestamp_utc_display
        == projection.migration_timestamp_utc
    )


def test_renderer_renders_missing_when_timestamp_is_none() -> None:
    block = render_private_discord_migration_context_block(
        _build_missing_projection(),
    )
    assert (
        block.migration_timestamp_utc_display
        == DISPLAY_TOKEN_MISSING
    )


def test_renderer_echoes_migration_slot_when_present() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert block.migration_slot_display == "12345"


def test_renderer_renders_missing_when_slot_is_none() -> None:
    block = render_private_discord_migration_context_block(
        _build_missing_projection(),
    )
    assert (
        block.migration_slot_display == DISPLAY_TOKEN_MISSING
    )


def test_renderer_echoes_migration_source_token() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert (
        block.migration_source_token
        == MIGRATION_SOURCE_HELIUS_WS
    )


def test_renderer_echoes_join_status_token() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert (
        block.join_status_echoed_token
        == MIGRATION_JOIN_STATUS_JOINED
    )


def test_renderer_echoes_observed_at_utc() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert block.observed_at_utc == _OBSERVED_AT


def test_renderer_renders_none_warnings_as_none_token() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert block.warnings_display == DISPLAY_TOKEN_NONE


def test_renderer_renders_warnings_comma_joined_in_input_order() -> None:
    projection = _build_missing_projection()
    block = render_private_discord_migration_context_block(
        projection,
    )
    expected = (
        f"{WARNING_MIGRATION_MISSING}, "
        f"{WARNING_POST_MIGRATION_ATH_UNVERIFIED}"
    )
    assert block.warnings_display == expected


# ---------------------------------------------------------------------------
# Status-display mapping (covered more thoroughly in
# test_stage_29_5_5_status_matrix.py)
# ---------------------------------------------------------------------------


def test_complete_trusted_renders_complete_and_trusted() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert (
        block.migration_evidence_status_display
        == MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE
    )
    assert (
        block.migration_evidence_source_trust_display
        == MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN
    )
    assert (
        block.post_migration_ath_verified_display
        == POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED
    )


def test_missing_renders_missing_and_no_source_and_unknown_ath() -> None:
    block = render_private_discord_migration_context_block(
        _build_missing_projection(),
    )
    assert (
        block.migration_evidence_status_display
        == MIGRATION_EVIDENCE_STATUS_DISPLAY_MISSING
    )
    assert (
        block.migration_evidence_source_trust_display
        == MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE
    )
    assert (
        block.post_migration_ath_verified_display
        == POST_MIGRATION_ATH_VERIFIED_DISPLAY_UNKNOWN
    )


# ---------------------------------------------------------------------------
# body_text rendering
# ---------------------------------------------------------------------------


def test_body_text_is_non_empty() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert block.body_text != ""


def test_body_text_starts_with_canonical_header() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert block.body_text.startswith(
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
    )


def test_body_text_contains_informational_only_flag_line() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert "informational_only: true" in block.body_text


def test_body_text_contains_not_a_trading_verdict_flag_line() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert (
        "not_a_trading_verdict: true" in block.body_text
    )


def test_body_text_contains_locked_enforcement_token_line() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert (
        "filter_enforcement_status: "
        "NOT_ACTIVE_STAGE_29_PENDING" in block.body_text
    )


def test_body_text_contains_redaction_safe_line() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert "redaction_status: SAFE" in block.body_text


def test_body_text_section_order_pinned() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    body = block.body_text
    migration_idx = body.find("\nMIGRATION\n")
    ath_idx = body.find("\nATH\n")
    warnings_idx = body.find("\nWARNINGS\n")
    observation_idx = body.find("\nOBSERVATION\n")
    assert migration_idx >= 0
    assert ath_idx >= 0
    assert warnings_idx >= 0
    assert observation_idx >= 0
    assert (
        migration_idx
        < ath_idx
        < warnings_idx
        < observation_idx
    ), f"section order broken: {body!r}"


def test_body_text_does_not_contain_trading_verdict_language() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    body = block.body_text
    for needle in (
        "BUY",
        "SELL",
        "APPROVED",
        "GATE",
        "BLOCK",
        "ENFORCEMENT",
        "EXECUTE",
        "POSITION-SIZE",
        "AUTO-TRADE",
        "AUTOTRADE",
    ):
        assert needle not in body, (
            f"renderer body_text must not contain trading "
            f"verdict token {needle!r}; body: {body!r}"
        )


def test_body_text_contains_schema_version_pin() -> None:
    block = render_private_discord_migration_context_block(
        _build_complete_trusted_verified_projection(),
    )
    assert (
        "schema_version: "
        "stage29_5_5_v0_rendered_migration_context_block"
    ) in block.body_text


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_renderer_is_deterministic_same_inputs_same_output() -> None:
    p1 = _build_complete_trusted_verified_projection()
    p2 = _build_complete_trusted_verified_projection()
    b1 = render_private_discord_migration_context_block(p1)
    b2 = render_private_discord_migration_context_block(p2)
    assert b1 == b2


def test_renderer_does_not_mutate_input_projection() -> None:
    projection = _build_complete_trusted_verified_projection()
    before_status = projection.measurement_status
    before_warnings = projection.warnings
    render_private_discord_migration_context_block(projection)
    assert projection.measurement_status == before_status
    assert projection.warnings == before_warnings
