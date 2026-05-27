"""Stage 29.5.5 render-models tests.

Pins:

  * Closed-set display-token vocabularies (status / source-trust
    / ATH-verified) have the exact expected values.
  * The ``Stage29_5_5RenderedMigrationContextBlock`` frozen
    dataclass validates every closed-set / locked-token field
    at ``__post_init__`` and rejects any malformed input with
    ``ValueError``.
  * The ``Stage29_5_5RecordedRenderEntry`` frozen dataclass
    validates token_mint shape, dataclass identity of
    projection / rendered_block / snapshot, and the
    ``recorded_at_utc`` UTC-shape.
  * Schema-version constants are pinned to the canonical
    Stage 29.5.5 values.
"""

from __future__ import annotations

import pytest

from PHX2.stage27.price_ath_context_reader import (
    MigrationSourceSnapshot,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    MEASUREMENT_STATUS_COMPLETE,
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_SOURCE_HELIUS_WS,
    REDACTION_STATUS_REDACTED,
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
    STAGE29_5_5_DISPLAY_SENTINEL_VALUES,
    STAGE29_5_5_MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_VALUES,
    STAGE29_5_5_MIGRATION_EVIDENCE_STATUS_DISPLAY_VALUES,
    STAGE29_5_5_POST_MIGRATION_ATH_VERIFIED_DISPLAY_VALUES,
    STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION,
    STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION,
    Stage29_5_5RecordedRenderEntry,
    Stage29_5_5RenderedMigrationContextBlock,
    is_stage29_5_5_migration_evidence_source_trust_display_value,
    is_stage29_5_5_migration_evidence_status_display_value,
    is_stage29_5_5_post_migration_ath_verified_display_value,
)


_SAFE_MINT: str = (
    "TestBaseMintAAAA1111111111111111111111111A"
)
_OBSERVED_AT: str = "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Closed-set vocabularies have the expected token values
# ---------------------------------------------------------------------------


def test_migration_evidence_status_display_values_pin() -> None:
    assert STAGE29_5_5_MIGRATION_EVIDENCE_STATUS_DISPLAY_VALUES == (
        "MIGRATION_EVIDENCE_COMPLETE",
        "MIGRATION_EVIDENCE_PARTIAL",
        "MIGRATION_EVIDENCE_MISSING",
        "MIGRATION_EVIDENCE_INVALID",
        "MIGRATION_EVIDENCE_CONFLICTING",
    )


def test_migration_evidence_source_trust_display_values_pin() -> None:
    assert (
        STAGE29_5_5_MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_VALUES
        == (
            "SOURCE_TRUSTED_ON_CHAIN",
            "SOURCE_UNTRUSTED_SYNTHETIC",
            "SOURCE_UNTRUSTED_UNKNOWN",
            "SOURCE_PARTIAL_ON_CHAIN",
            "SOURCE_PARTIAL_SYNTHETIC",
            "SOURCE_NO_SOURCE",
        )
    )


def test_post_migration_ath_verified_display_values_pin() -> None:
    assert (
        STAGE29_5_5_POST_MIGRATION_ATH_VERIFIED_DISPLAY_VALUES
        == (
            "ATH_VERIFIED_POST_MIGRATION",
            "ATH_NOT_VERIFIED_POST_MIGRATION",
            "ATH_VERIFICATION_UNKNOWN",
        )
    )


def test_display_sentinel_values_pin() -> None:
    assert STAGE29_5_5_DISPLAY_SENTINEL_VALUES == (
        "MISSING",
        "NONE",
    )
    assert DISPLAY_TOKEN_MISSING == "MISSING"
    assert DISPLAY_TOKEN_NONE == "NONE"


def test_individual_status_tokens_pin() -> None:
    assert (
        MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE
        == "MIGRATION_EVIDENCE_COMPLETE"
    )
    assert (
        MIGRATION_EVIDENCE_STATUS_DISPLAY_PARTIAL
        == "MIGRATION_EVIDENCE_PARTIAL"
    )
    assert (
        MIGRATION_EVIDENCE_STATUS_DISPLAY_MISSING
        == "MIGRATION_EVIDENCE_MISSING"
    )
    assert (
        MIGRATION_EVIDENCE_STATUS_DISPLAY_INVALID
        == "MIGRATION_EVIDENCE_INVALID"
    )
    assert (
        MIGRATION_EVIDENCE_STATUS_DISPLAY_CONFLICTING
        == "MIGRATION_EVIDENCE_CONFLICTING"
    )


def test_individual_source_trust_tokens_pin() -> None:
    assert (
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN
        == "SOURCE_TRUSTED_ON_CHAIN"
    )
    assert (
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_SYNTHETIC
        == "SOURCE_UNTRUSTED_SYNTHETIC"
    )
    assert (
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_UNKNOWN
        == "SOURCE_UNTRUSTED_UNKNOWN"
    )
    assert (
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN
        == "SOURCE_PARTIAL_ON_CHAIN"
    )
    assert (
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_SYNTHETIC
        == "SOURCE_PARTIAL_SYNTHETIC"
    )
    assert (
        MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE
        == "SOURCE_NO_SOURCE"
    )


def test_individual_ath_verified_tokens_pin() -> None:
    assert (
        POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED
        == "ATH_VERIFIED_POST_MIGRATION"
    )
    assert (
        POST_MIGRATION_ATH_VERIFIED_DISPLAY_NOT_VERIFIED
        == "ATH_NOT_VERIFIED_POST_MIGRATION"
    )
    assert (
        POST_MIGRATION_ATH_VERIFIED_DISPLAY_UNKNOWN
        == "ATH_VERIFICATION_UNKNOWN"
    )


# ---------------------------------------------------------------------------
# is_*_display_value predicate behavior
# ---------------------------------------------------------------------------


def test_is_status_display_value_admits_closed_set() -> None:
    for token in (
        STAGE29_5_5_MIGRATION_EVIDENCE_STATUS_DISPLAY_VALUES
    ):
        assert is_stage29_5_5_migration_evidence_status_display_value(
            token,
        )


def test_is_status_display_value_rejects_outsiders() -> None:
    for bad in (
        None,
        "",
        "OTHER",
        "complete",
        123,
        object(),
    ):
        assert not (
            is_stage29_5_5_migration_evidence_status_display_value(
                bad,
            )
        )


def test_is_source_trust_display_value_admits_closed_set() -> None:
    for token in (
        STAGE29_5_5_MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_VALUES
    ):
        assert is_stage29_5_5_migration_evidence_source_trust_display_value(
            token,
        )


def test_is_source_trust_display_value_rejects_outsiders() -> None:
    for bad in (None, "", "TRUSTED", "trusted_on_chain", 0):
        assert not (
            is_stage29_5_5_migration_evidence_source_trust_display_value(
                bad,
            )
        )


def test_is_ath_verified_display_value_admits_closed_set() -> None:
    for token in (
        STAGE29_5_5_POST_MIGRATION_ATH_VERIFIED_DISPLAY_VALUES
    ):
        assert is_stage29_5_5_post_migration_ath_verified_display_value(
            token,
        )


def test_is_ath_verified_display_value_rejects_outsiders() -> None:
    for bad in (None, "", "VERIFIED", "true", True):
        assert not (
            is_stage29_5_5_post_migration_ath_verified_display_value(
                bad,
            )
        )


# ---------------------------------------------------------------------------
# Schema version constants
# ---------------------------------------------------------------------------


def test_rendered_block_schema_version_pin() -> None:
    assert (
        STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION
        == "stage29_5_5_v0_rendered_migration_context_block"
    )


def test_recorded_entry_schema_version_pin() -> None:
    assert (
        STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION
        == "stage29_5_5_v0_recorded_render_entry"
    )


# ---------------------------------------------------------------------------
# Stage29_5_5RenderedMigrationContextBlock validators
# ---------------------------------------------------------------------------


def _build_block(**overrides) -> (
    Stage29_5_5RenderedMigrationContextBlock
):
    defaults = dict(
        migration_evidence_status_display=(
            MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE
        ),
        migration_evidence_source_trust_display=(
            MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN
        ),
        post_migration_ath_verified_display=(
            POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED
        ),
        migration_timestamp_utc_display=_OBSERVED_AT,
        migration_slot_display="12345",
        migration_source_token=MIGRATION_SOURCE_HELIUS_WS,
        join_status_echoed_token=MIGRATION_JOIN_STATUS_JOINED,
        warnings_display=DISPLAY_TOKEN_NONE,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_OBSERVED_AT,
        informational_only=True,
        not_a_trading_verdict=True,
        body_text="non-empty body text",
    )
    defaults.update(overrides)
    return Stage29_5_5RenderedMigrationContextBlock(**defaults)


def test_block_constructs_with_valid_inputs() -> None:
    block = _build_block()
    assert (
        block.migration_evidence_status_display
        == MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE
    )


def test_block_rejects_invalid_status_display() -> None:
    with pytest.raises(ValueError):
        _build_block(
            migration_evidence_status_display="OTHER",
        )


def test_block_rejects_invalid_source_trust_display() -> None:
    with pytest.raises(ValueError):
        _build_block(
            migration_evidence_source_trust_display="OTHER",
        )


def test_block_rejects_invalid_ath_verified_display() -> None:
    with pytest.raises(ValueError):
        _build_block(
            post_migration_ath_verified_display="OTHER",
        )


def test_block_rejects_non_string_timestamp_display() -> None:
    with pytest.raises(ValueError):
        _build_block(migration_timestamp_utc_display=12345)


def test_block_rejects_non_string_slot_display() -> None:
    with pytest.raises(ValueError):
        _block_with_int_slot()


def _block_with_int_slot():
    return _build_block(migration_slot_display=12345)


def test_block_rejects_outside_set_source_token() -> None:
    with pytest.raises(ValueError):
        _build_block(migration_source_token="OUTSIDE_TOKEN")


def test_block_rejects_outside_set_join_status_token() -> None:
    with pytest.raises(ValueError):
        _build_block(
            join_status_echoed_token="OUTSIDE_JOIN_STATUS",
        )


def test_block_rejects_non_string_warnings_display() -> None:
    with pytest.raises(ValueError):
        _build_block(warnings_display=42)


def test_block_rejects_redaction_status_other_than_safe() -> None:
    with pytest.raises(ValueError):
        _build_block(
            redaction_status=REDACTION_STATUS_REDACTED,
        )


def test_block_rejects_filter_enforcement_other_than_locked() -> None:
    with pytest.raises(ValueError):
        _build_block(filter_enforcement_status="ACTIVE")


def test_block_rejects_non_utc_observed_at() -> None:
    with pytest.raises(ValueError):
        _build_block(observed_at_utc="not-a-datetime")


def test_block_rejects_informational_only_not_true() -> None:
    with pytest.raises(ValueError):
        _build_block(informational_only=False)


def test_block_rejects_not_a_trading_verdict_not_true() -> None:
    with pytest.raises(ValueError):
        _build_block(not_a_trading_verdict=False)


def test_block_rejects_empty_body_text() -> None:
    with pytest.raises(ValueError):
        _build_block(body_text="")


def test_block_rejects_non_string_body_text() -> None:
    with pytest.raises(ValueError):
        _build_block(body_text=None)


def test_block_rejects_overridden_schema_version() -> None:
    with pytest.raises(ValueError):
        _build_block(schema_version="other_schema")


def test_block_is_frozen() -> None:
    block = _build_block()
    with pytest.raises(Exception):
        block.migration_evidence_status_display = "OTHER"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Stage29_5_5RecordedRenderEntry validators
# ---------------------------------------------------------------------------


def _build_projection() -> Stage29_5PrivatePingMigrationContext:
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=MEASUREMENT_STATUS_COMPLETE,
        warnings=(),
        migration_timestamp_utc=_OBSERVED_AT,
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


def _build_snapshot() -> MigrationSourceSnapshot:
    return MigrationSourceSnapshot(
        migration_event_id=None,
        migration_timestamp_utc=None,
        migration_source="UNKNOWN",
        source_event_ref=None,
        raw_capture_ref=None,
    )


def _build_entry(**overrides) -> (
    Stage29_5_5RecordedRenderEntry
):
    projection = _build_projection()
    block = _build_block()
    snapshot = _build_snapshot()
    defaults = dict(
        token_mint=_SAFE_MINT,
        projection=projection,
        rendered_block=block,
        snapshot=snapshot,
        recorded_at_utc=_OBSERVED_AT,
    )
    defaults.update(overrides)
    return Stage29_5_5RecordedRenderEntry(**defaults)


def test_entry_constructs_with_valid_inputs() -> None:
    entry = _build_entry()
    assert entry.token_mint == _SAFE_MINT


def test_entry_rejects_unsafe_token_mint() -> None:
    with pytest.raises(ValueError):
        _build_entry(token_mint="short")


def test_entry_rejects_non_string_token_mint() -> None:
    with pytest.raises(ValueError):
        _build_entry(token_mint=None)


def test_entry_rejects_wrong_projection_type() -> None:
    with pytest.raises(ValueError):
        _build_entry(projection="not a projection")


def test_entry_rejects_wrong_rendered_block_type() -> None:
    with pytest.raises(ValueError):
        _build_entry(rendered_block={"not": "a block"})


def test_entry_rejects_wrong_snapshot_type() -> None:
    with pytest.raises(ValueError):
        _build_entry(snapshot={"not": "a snapshot"})


def test_entry_rejects_non_utc_recorded_at() -> None:
    with pytest.raises(ValueError):
        _build_entry(recorded_at_utc="bad-timestamp")


def test_entry_rejects_overridden_schema_version() -> None:
    with pytest.raises(ValueError):
        _build_entry(schema_version="other")


def test_entry_is_frozen() -> None:
    entry = _build_entry()
    with pytest.raises(Exception):
        entry.token_mint = "OTHER"  # type: ignore[misc]
