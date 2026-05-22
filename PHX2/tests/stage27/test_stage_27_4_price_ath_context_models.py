"""Stage 27.4 price / ATH / migration context model tests.

Pins:

  * ``PRICE_STATUS_VALUES`` / ``ATH_STATUS_VALUES`` /
    ``MIGRATION_STATUS_VALUES`` carry the locked closed-set
    membership.
  * ``PRICE_UNIT_VALUES`` / ``ATH_UNIT_VALUES`` carry SOL / USDC /
    USD / UNKNOWN.
  * ``ATH_SINCE_MIGRATION_STATUS_VALUES`` carries the four-token
    locked set.
  * ``PriceContextRecord`` / ``AthContextRecord`` /
    ``MigrationContextRecord`` are immutable NamedTuples that
    carry no raw-payload-class field.
  * The Stage 27.4 schema versions are stable.
  * The Stage 27.4 exception types are module-local and carry no
    raw payload in ``str()`` / ``repr()``.
  * The closed-set assertion helpers raise
    ``Stage27UnknownMeasurementContextVocabularyError`` for unknown
    tokens.
  * The forbidden snapshot-field-name helper rejects raw-payload-
    class / secret-class / webhook-class names.
"""

from __future__ import annotations

import pytest

from PHX2.stage27 import migration_context_models as mig
from PHX2.stage27 import price_ath_context_contracts as errors
from PHX2.stage27 import price_ath_context_models as m


# ---------------------------------------------------------------------------
# Price closed-set pins
# ---------------------------------------------------------------------------


def test_price_status_values_locked_closed_set():
    assert m.PRICE_STATUS_VALUES == (
        "PRESENT",
        "STALE",
        "UNAVAILABLE",
        "UNSUPPORTED_PAIR",
        "SOURCE_ERROR",
    )


def test_price_status_constants_match_tuple():
    assert m.PRICE_STATUS_PRESENT == "PRESENT"
    assert m.PRICE_STATUS_STALE == "STALE"
    assert m.PRICE_STATUS_UNAVAILABLE == "UNAVAILABLE"
    assert m.PRICE_STATUS_UNSUPPORTED_PAIR == "UNSUPPORTED_PAIR"
    assert m.PRICE_STATUS_SOURCE_ERROR == "SOURCE_ERROR"


def test_price_unit_values_locked_closed_set():
    assert m.PRICE_UNIT_VALUES == ("SOL", "USDC", "USD", "UNKNOWN")


def test_price_unit_constants_match_tuple():
    assert m.PRICE_UNIT_SOL == "SOL"
    assert m.PRICE_UNIT_USDC == "USDC"
    assert m.PRICE_UNIT_USD == "USD"
    assert m.PRICE_UNIT_UNKNOWN == "UNKNOWN"


@pytest.mark.parametrize(
    "expected",
    (
        "OK",
        "STALE_THRESHOLD_EXCEEDED",
        "SOURCE_RETURNED_NONE",
        "SOURCE_FAILED",
        "UNSUPPORTED_QUOTE_ASSET",
        "UNKNOWN_PAIR_OBSERVE_ONLY",
        "DISAGREE_PAIR_OBSERVE_ONLY",
        "USDC_OBSERVE_ONLY",
        "INVALID_SOURCE_SNAPSHOT",
    ),
)
def test_price_reason_values_include_locked_brief_set(expected):
    assert expected in m.PRICE_REASON_VALUES


# ---------------------------------------------------------------------------
# ATH closed-set pins
# ---------------------------------------------------------------------------


def test_ath_status_values_locked_closed_set():
    assert m.ATH_STATUS_VALUES == (
        "PRESENT",
        "STALE",
        "UNAVAILABLE",
        "NOT_APPLICABLE",
        "UNSUPPORTED_PAIR",
        "SOURCE_ERROR",
    )


def test_ath_unit_values_locked_closed_set():
    assert m.ATH_UNIT_VALUES == ("SOL", "USDC", "USD", "UNKNOWN")


def test_ath_since_migration_status_values_locked_closed_set():
    assert m.ATH_SINCE_MIGRATION_STATUS_VALUES == (
        "POST_MIGRATION_ONLY",
        "MAY_INCLUDE_PRE_MIGRATION",
        "UNKNOWN",
        "NOT_APPLICABLE",
    )


@pytest.mark.parametrize(
    "expected",
    (
        "OK",
        "NO_OBSERVATIONS",
        "PRE_MIGRATION_DATA_REJECTED",
        "SOURCE_FAILED",
        "UNSUPPORTED_QUOTE_ASSET",
        "UNKNOWN_PAIR_OBSERVE_ONLY",
        "DISAGREE_PAIR_OBSERVE_ONLY",
        "USDC_OBSERVE_ONLY",
        "NOT_APPLICABLE",
        "INVALID_SOURCE_SNAPSHOT",
    ),
)
def test_ath_reason_values_include_locked_brief_set(expected):
    assert expected in m.ATH_REASON_VALUES


def test_drawdown_basis_values_locked_closed_set():
    assert m.DRAWDOWN_BASIS_VALUES == (
        "FROM_POST_MIGRATION_ATH",
        "NOT_APPLICABLE",
        "UNKNOWN",
    )


# ---------------------------------------------------------------------------
# Migration closed-set pins
# ---------------------------------------------------------------------------


def test_migration_status_values_locked_closed_set():
    assert mig.MIGRATION_STATUS_VALUES == (
        "PRESENT",
        "MISSING",
        "UNTRUSTED",
        "UNSUPPORTED_PAIR",
        "SOURCE_ERROR",
    )


@pytest.mark.parametrize(
    "expected",
    (
        "OK",
        "NO_MIGRATION_EVENT",
        "MISSING_TIMESTAMP",
        "MALFORMED_TIMESTAMP",
        "SOURCE_FAILED",
        "SOURCE_NOT_TRUSTED",
        "UNKNOWN_PAIR_OBSERVE_ONLY",
        "DISAGREE_PAIR_OBSERVE_ONLY",
        "INVALID_SOURCE_SNAPSHOT",
    ),
)
def test_migration_reason_values_include_locked_brief_set(expected):
    assert expected in mig.MIGRATION_REASON_VALUES


def test_migration_source_values_locked_closed_set():
    assert mig.MIGRATION_SOURCE_VALUES == (
        "ON_CHAIN_MIGRATION_EVENT",
        "PROVIDER_ENRICHED",
        "OPERATOR_OVERRIDE",
        "UNKNOWN",
    )


def test_migration_sources_trusted_locked():
    assert mig.MIGRATION_SOURCES_TRUSTED == (
        "ON_CHAIN_MIGRATION_EVENT",
        "OPERATOR_OVERRIDE",
    )
    # Untrusted upstream labels MUST not appear in the trusted tuple.
    assert "PROVIDER_ENRICHED" not in mig.MIGRATION_SOURCES_TRUSTED
    assert "UNKNOWN" not in mig.MIGRATION_SOURCES_TRUSTED


# ---------------------------------------------------------------------------
# Schema version pins
# ---------------------------------------------------------------------------


def test_stage27_4_minor_version_handle():
    assert m.STAGE27_4_MINOR_VERSION == "27.4"


def test_stage27_4_price_ath_schema_version_handle():
    assert (
        m.STAGE27_4_PRICE_ATH_SCHEMA_VERSION
        == "stage27_v0_price_ath_context"
    )


def test_stage27_4_migration_schema_version_handle():
    assert (
        mig.STAGE27_4_MIGRATION_SCHEMA_VERSION
        == "stage27_v0_migration_context"
    )


# ---------------------------------------------------------------------------
# Record shape pins (immutable NamedTuple)
# ---------------------------------------------------------------------------


def _build_minimal_price_record() -> m.PriceContextRecord:
    return m.PriceContextRecord(
        token_mint="MintAAA",
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        quote_mint="So11111111111111111111111111111111111111112",
        price_value="0.0001",
        price_unit="SOL",
        price_source="fake_birdeye",
        fetched_at_utc="2026-05-22T12:00:00+00:00",
        observed_at_utc="2026-05-22T12:00:30+00:00",
        staleness_seconds=30,
        price_status="PRESENT",
        price_reason="OK",
        schema_version=m.STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _build_minimal_ath_record() -> m.AthContextRecord:
    return m.AthContextRecord(
        token_mint="MintAAA",
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        ath_value="0.0009",
        ath_unit="SOL",
        ath_source="fake_birdeye",
        ath_observed_at_utc="2026-05-22T11:00:00+00:00",
        ath_since_migration_status="POST_MIGRATION_ONLY",
        drawdown_from_ath="0.0008",
        drawdown_unit="SOL",
        drawdown_basis="FROM_POST_MIGRATION_ATH",
        ath_status="PRESENT",
        ath_reason="OK",
        schema_version=m.STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _build_minimal_migration_record() -> mig.MigrationContextRecord:
    return mig.MigrationContextRecord(
        token_mint="MintAAA",
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        migration_event_id="evt-42",
        migration_timestamp_utc="2026-05-22T10:00:00+00:00",
        migration_source="ON_CHAIN_MIGRATION_EVENT",
        migration_status="PRESENT",
        migration_reason="OK",
        age_since_migration_seconds=7200,
        observed_at_utc="2026-05-22T12:00:30+00:00",
        source_event_ref="ref-mig-42",
        raw_capture_ref="hash-abc",
        schema_version=mig.STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


def test_price_context_record_is_namedtuple_and_immutable():
    record = _build_minimal_price_record()
    assert isinstance(record, tuple)
    with pytest.raises(AttributeError):
        record.price_value = "0.0002"


def test_ath_context_record_is_namedtuple_and_immutable():
    record = _build_minimal_ath_record()
    assert isinstance(record, tuple)
    with pytest.raises(AttributeError):
        record.ath_value = "0.0010"


def test_migration_context_record_is_namedtuple_and_immutable():
    record = _build_minimal_migration_record()
    assert isinstance(record, tuple)
    with pytest.raises(AttributeError):
        record.migration_status = "UNTRUSTED"


def test_price_context_record_field_set_locked():
    record = _build_minimal_price_record()
    assert set(record._fields) == {
        "token_mint",
        "pair_type",
        "quote_asset",
        "quote_mint",
        "price_value",
        "price_unit",
        "price_source",
        "fetched_at_utc",
        "observed_at_utc",
        "staleness_seconds",
        "price_status",
        "price_reason",
        "schema_version",
    }


def test_ath_context_record_field_set_locked():
    record = _build_minimal_ath_record()
    assert set(record._fields) == {
        "token_mint",
        "pair_type",
        "quote_asset",
        "ath_value",
        "ath_unit",
        "ath_source",
        "ath_observed_at_utc",
        "ath_since_migration_status",
        "drawdown_from_ath",
        "drawdown_unit",
        "drawdown_basis",
        "ath_status",
        "ath_reason",
        "schema_version",
    }


def test_migration_context_record_field_set_locked():
    record = _build_minimal_migration_record()
    assert set(record._fields) == {
        "token_mint",
        "pair_type",
        "quote_asset",
        "migration_event_id",
        "migration_timestamp_utc",
        "migration_source",
        "migration_status",
        "migration_reason",
        "age_since_migration_seconds",
        "observed_at_utc",
        "source_event_ref",
        "raw_capture_ref",
        "schema_version",
    }


def test_no_record_carries_raw_payload_field():
    """No Stage 27.4 model record admits a raw-payload-class field."""
    for record_cls in (
        m.PriceContextRecord,
        m.AthContextRecord,
        mig.MigrationContextRecord,
    ):
        for field in record_cls._fields:
            lower = field.lower()
            assert "raw_payload" not in lower
            assert "payload" not in lower or field == "raw_capture_ref"
            assert "secret" not in lower
            assert "api_key" not in lower
            assert "webhook" not in lower


def test_price_value_is_optional_text_not_float():
    """Stage 27.4 NEVER uses ``0.0`` as a missing sentinel.

    Missing-price is represented by ``price_value=None``.
    """
    record = _build_minimal_price_record()._replace(
        price_value=None,
        price_status="UNAVAILABLE",
        price_reason="SOURCE_RETURNED_NONE",
    )
    assert record.price_value is None
    # When PRESENT, the value is a canonical text string, not a
    # float -- so a "0" text price is explicitly NOT the same as
    # missing.
    explicit_zero = _build_minimal_price_record()._replace(
        price_value="0",
        price_status="PRESENT",
    )
    assert explicit_zero.price_value == "0"
    assert explicit_zero.price_status == "PRESENT"


def test_ath_value_is_optional_text_not_float():
    record = _build_minimal_ath_record()._replace(
        ath_value=None,
        ath_status="UNAVAILABLE",
        ath_reason="NO_OBSERVATIONS",
    )
    assert record.ath_value is None


def test_migration_timestamp_can_be_missing_without_crash():
    record = _build_minimal_migration_record()._replace(
        migration_timestamp_utc=None,
        migration_status="MISSING",
        migration_reason="MISSING_TIMESTAMP",
        age_since_migration_seconds=None,
    )
    assert record.migration_timestamp_utc is None
    assert record.age_since_migration_seconds is None


# ---------------------------------------------------------------------------
# Exception hierarchy pins
# ---------------------------------------------------------------------------


def test_exception_hierarchy_is_module_local():
    """Stage 27.4 error types must root at plain ``Exception``."""
    assert issubclass(
        errors.Stage27MeasurementContextError, Exception
    )
    assert issubclass(
        errors.Stage27PriceSourceError,
        errors.Stage27MeasurementContextError,
    )
    assert issubclass(
        errors.Stage27AthSourceError,
        errors.Stage27MeasurementContextError,
    )
    assert issubclass(
        errors.Stage27MigrationSourceError,
        errors.Stage27MeasurementContextError,
    )
    assert issubclass(
        errors.Stage27UnknownMeasurementContextVocabularyError,
        errors.Stage27MeasurementContextError,
    )


def test_price_source_error_str_does_not_carry_raw_payload():
    err = errors.Stage27PriceSourceError(
        "SOURCE_FAILED", source_label="fake_birdeye"
    )
    text = str(err)
    assert "SOURCE_FAILED" in text
    assert "fake_birdeye" in text
    for forbidden in ("api_key", "secret", "webhook", "https"):
        assert forbidden not in text


def test_unknown_measurement_vocabulary_error_carries_only_token():
    err = errors.Stage27UnknownMeasurementContextVocabularyError(
        "price_status", "WAT"
    )
    assert err.kind == "price_status"
    assert err.value == "WAT"
    text = str(err)
    assert "price_status" in text
    assert "WAT" in text


# ---------------------------------------------------------------------------
# Closed-set assertion helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", m.PRICE_STATUS_VALUES)
def test_assert_price_status_accepts_locked_tokens(value):
    assert errors.assert_price_status(value) == value


def test_assert_price_status_rejects_unknown_token():
    with pytest.raises(
        errors.Stage27UnknownMeasurementContextVocabularyError
    ):
        errors.assert_price_status("DEFINITELY_NOT_A_STATUS")


@pytest.mark.parametrize("value", m.PRICE_UNIT_VALUES)
def test_assert_price_unit_accepts_locked_tokens(value):
    assert errors.assert_price_unit(value) == value


def test_assert_price_unit_rejects_unknown_token():
    with pytest.raises(
        errors.Stage27UnknownMeasurementContextVocabularyError
    ):
        errors.assert_price_unit("ETH")


@pytest.mark.parametrize("value", m.ATH_STATUS_VALUES)
def test_assert_ath_status_accepts_locked_tokens(value):
    assert errors.assert_ath_status(value) == value


def test_assert_ath_status_rejects_unknown_token():
    with pytest.raises(
        errors.Stage27UnknownMeasurementContextVocabularyError
    ):
        errors.assert_ath_status("ALL_TIME_HIGH")


@pytest.mark.parametrize(
    "value", m.ATH_SINCE_MIGRATION_STATUS_VALUES
)
def test_assert_ath_since_migration_status_accepts(value):
    assert errors.assert_ath_since_migration_status(value) == value


@pytest.mark.parametrize("value", m.DRAWDOWN_BASIS_VALUES)
def test_assert_drawdown_basis_accepts(value):
    assert errors.assert_drawdown_basis(value) == value


@pytest.mark.parametrize("value", mig.MIGRATION_STATUS_VALUES)
def test_assert_migration_status_accepts(value):
    assert errors.assert_migration_status(value) == value


def test_assert_migration_status_rejects_unknown_token():
    with pytest.raises(
        errors.Stage27UnknownMeasurementContextVocabularyError
    ):
        errors.assert_migration_status("MIGRATING")


@pytest.mark.parametrize("value", mig.MIGRATION_SOURCE_VALUES)
def test_assert_migration_source_accepts(value):
    assert errors.assert_migration_source(value) == value


# ---------------------------------------------------------------------------
# Forbidden snapshot field-name guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    (
        "raw_payload",
        "raw_payload_blob",
        "payload",
        "payload_summary",
        "secret",
        "api_key",
        "apikey",
        "token_secret",
        "webhook",
        "webhook_url",
        "private_key",
        "credentials",
        "bearer_token",
        "PAYLOAD",
        "API_KEY",
        "Webhook_URL",
    ),
)
def test_is_forbidden_snapshot_field_name_rejects(name):
    assert m.is_forbidden_snapshot_field_name(name)


@pytest.mark.parametrize(
    "name",
    (
        "price_value",
        "ath_value",
        "migration_event_id",
        "source_label",
        "raw_capture_ref",
        "fetched_at_utc",
    ),
)
def test_is_forbidden_snapshot_field_name_accepts(name):
    assert not m.is_forbidden_snapshot_field_name(name)


def test_is_forbidden_snapshot_field_name_non_string():
    assert not m.is_forbidden_snapshot_field_name(None)
    assert not m.is_forbidden_snapshot_field_name(42)
    assert not m.is_forbidden_snapshot_field_name(["payload"])
