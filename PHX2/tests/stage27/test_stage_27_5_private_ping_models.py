"""Stage 27.5 private ping model tests.

Pins:

  * Schema-version handles are the locked Stage 27.5 strings.
  * ``RENDER_STATUS_VALUES`` is the locked closed set.
  * ``ARTIFACT_KIND_VALUES`` is the locked closed set.
  * ``REDACTION_STATUS_VALUES`` is the locked closed set.
  * ``DISPLAY_SENTINEL_VALUES`` carries the locked sentinel
    vocabulary; ``"0"`` / ``"0.0"`` are NEVER in the sentinel set.
  * ``PrivatePingPayloadRecord`` is an immutable NamedTuple with the
    locked field set.
  * ``PingProvenanceArtifactRecord`` is an immutable NamedTuple
    with the locked field set.
  * Forbidden field-name helper rejects raw-payload / secret /
    webhook / api-key / rpc-url substrings.
"""

from __future__ import annotations

import pytest

from PHX2.stage27 import private_ping_models as m


# ---------------------------------------------------------------------------
# Version-axis pins
# ---------------------------------------------------------------------------


def test_stage_27_5_minor_version_handle():
    assert m.STAGE27_5_MINOR_VERSION == "27.5"


def test_stage_27_5_ping_schema_version_handle():
    assert (
        m.STAGE27_5_PING_SCHEMA_VERSION
        == "stage27_v0_private_ping"
    )


def test_stage_27_5_provenance_schema_version_handle():
    assert (
        m.STAGE27_5_PROVENANCE_SCHEMA_VERSION
        == "stage27_v0_ping_provenance"
    )


# ---------------------------------------------------------------------------
# Closed-set pins
# ---------------------------------------------------------------------------


def test_render_status_values_locked_closed_set():
    assert m.RENDER_STATUS_VALUES == (
        "RENDERED",
        "RENDERED_WITH_WARNINGS",
        "RENDERED_SUPPRESSED",
        "RENDERED_OBSERVE_ONLY",
        "RENDERED_UNSUPPORTED",
    )


def test_artifact_kind_values_locked_closed_set():
    assert m.ARTIFACT_KIND_VALUES == ("PRIVATE_PING_DRY_RUN",)


def test_redaction_status_values_locked_closed_set():
    assert m.REDACTION_STATUS_VALUES == (
        "REDACTED",
        "REDACTION_FAILED",
    )


def test_display_sentinel_values_locked_closed_set():
    assert m.DISPLAY_SENTINEL_VALUES == (
        "UNAVAILABLE",
        "STALE",
        "MISSING",
        "UNTRUSTED",
        "SOURCE_ERROR",
        "NOT_APPLICABLE",
        "UNSUPPORTED_PAIR",
        "NONE",
    )


@pytest.mark.parametrize("zero_token", ("0", "0.0"))
def test_zero_is_never_a_display_sentinel(zero_token):
    assert zero_token not in m.DISPLAY_SENTINEL_VALUES


# ---------------------------------------------------------------------------
# PrivatePingPayloadRecord field set
# ---------------------------------------------------------------------------


_EXPECTED_PAYLOAD_FIELDS: frozenset[str] = frozenset(
    {
        "ping_id",
        "run_id",
        "session_id",
        "ping_schema_version",
        "provider_id",
        "provider_event_id",
        "normalized_event_id",
        "raw_capture_ref",
        "token_mint",
        "quote_mint",
        "pair_type",
        "quote_asset",
        "bonding_curve_version",
        "pair_detection_status",
        "pair_detection_confidence",
        "pair_detection_reason",
        "pair_live_policy",
        "calibration_lane",
        "measurement_status",
        "measurement_warnings",
        "price_status",
        "price_value_display",
        "price_unit_display",
        "price_source_display",
        "price_staleness_seconds_display",
        "ath_status",
        "ath_value_display",
        "ath_unit_display",
        "ath_since_migration_status_display",
        "drawdown_display",
        "drawdown_basis_display",
        "migration_status",
        "migration_timestamp_display",
        "migration_age_seconds_display",
        "migration_source_display",
        "render_status",
        "render_note",
        "body_text",
    }
)


def test_private_ping_payload_record_field_set_locked():
    assert set(m.PrivatePingPayloadRecord._fields) == (
        _EXPECTED_PAYLOAD_FIELDS
    )


def test_private_ping_payload_record_is_immutable_namedtuple():
    record = m.PrivatePingPayloadRecord(
        ping_id="ping-1",
        run_id=None,
        session_id=None,
        ping_schema_version=m.STAGE27_5_PING_SCHEMA_VERSION,
        provider_id=None,
        provider_event_id=None,
        normalized_event_id=None,
        raw_capture_ref=None,
        token_mint=None,
        quote_mint=None,
        pair_type="UNKNOWN",
        quote_asset="UNKNOWN",
        bonding_curve_version="UNKNOWN",
        pair_detection_status="UNRESOLVED",
        pair_detection_confidence="NONE",
        pair_detection_reason="NO_EVIDENCE",
        pair_live_policy="LIVE_SUPPRESS_UNKNOWN",
        calibration_lane="UNKNOWN_PAIR_OBSERVE_ONLY",
        measurement_status="UNSUPPORTED_PAIR",
        measurement_warnings=(),
        price_status="UNSUPPORTED_PAIR",
        price_value_display=m.DISPLAY_UNSUPPORTED_PAIR,
        price_unit_display=m.DISPLAY_UNSUPPORTED_PAIR,
        price_source_display=m.DISPLAY_UNSUPPORTED_PAIR,
        price_staleness_seconds_display=(
            m.DISPLAY_UNSUPPORTED_PAIR
        ),
        ath_status="UNSUPPORTED_PAIR",
        ath_value_display=m.DISPLAY_UNSUPPORTED_PAIR,
        ath_unit_display="UNKNOWN",
        ath_since_migration_status_display=(
            m.DISPLAY_NOT_APPLICABLE
        ),
        drawdown_display=m.DISPLAY_NOT_APPLICABLE,
        drawdown_basis_display=m.DISPLAY_NOT_APPLICABLE,
        migration_status="UNSUPPORTED_PAIR",
        migration_timestamp_display=(
            m.DISPLAY_UNSUPPORTED_PAIR
        ),
        migration_age_seconds_display=(
            m.DISPLAY_UNSUPPORTED_PAIR
        ),
        migration_source_display="UNKNOWN",
        render_status=m.RENDER_STATUS_RENDERED_UNSUPPORTED,
        render_note="UNSUPPORTED_PAIR",
        body_text="placeholder",
    )
    assert isinstance(record, tuple)
    with pytest.raises(AttributeError):
        record.ping_id = "other"


# ---------------------------------------------------------------------------
# PingProvenanceArtifactRecord field set
# ---------------------------------------------------------------------------


_EXPECTED_ARTIFACT_FIELDS: frozenset[str] = frozenset(
    {
        "artifact_kind",
        "artifact_schema_version",
        "artifact_created_at_utc",
        "ping_id",
        "ping_schema_version",
        "run_id",
        "session_id",
        "provider_id",
        "provider_event_id",
        "normalized_event_id",
        "raw_capture_ref",
        "token_mint",
        "pair_quote_asset",
        "pair_type",
        "pair_detection_status",
        "pair_detection_confidence",
        "pair_live_policy",
        "calibration_lane",
        "measurement_status",
        "measurement_warnings",
        "render_status",
        "redaction_status",
        "payload_content_hash",
    }
)


def test_ping_provenance_artifact_record_field_set_locked():
    assert set(m.PingProvenanceArtifactRecord._fields) == (
        _EXPECTED_ARTIFACT_FIELDS
    )


# ---------------------------------------------------------------------------
# Forbidden field-name helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    (
        "raw_payload",
        "Raw_Payload",
        "raw_payload_blob",
        "payload_blob",
        "secret",
        "api_key",
        "apikey",
        "API_KEY",
        "webhook",
        "webhook_url",
        "discord_webhook",
        "rpc_url",
        "private_key",
        "credentials",
        "bearer_token",
    ),
)
def test_forbidden_payload_field_name_helper_rejects(name):
    assert m.is_forbidden_payload_field_name(name) is True


@pytest.mark.parametrize(
    "name",
    (
        "ping_id",
        "token_mint",
        "render_status",
        "measurement_warnings",
        "body_text",
    ),
)
def test_forbidden_payload_field_name_helper_admits(name):
    assert m.is_forbidden_payload_field_name(name) is False


def test_forbidden_payload_field_name_helper_admits_non_string():
    assert m.is_forbidden_payload_field_name(None) is False
    assert m.is_forbidden_payload_field_name(42) is False


# ---------------------------------------------------------------------------
# Payload field set excludes every forbidden substring
# ---------------------------------------------------------------------------


def test_payload_record_field_set_carries_no_forbidden_substring():
    for field_name in m.PrivatePingPayloadRecord._fields:
        assert not m.is_forbidden_payload_field_name(field_name), (
            f"payload field {field_name!r} contains a forbidden "
            "substring"
        )


def test_artifact_record_field_set_carries_no_forbidden_substring():
    for field_name in m.PingProvenanceArtifactRecord._fields:
        assert not m.is_forbidden_payload_field_name(field_name), (
            f"artifact field {field_name!r} contains a forbidden "
            "substring"
        )
