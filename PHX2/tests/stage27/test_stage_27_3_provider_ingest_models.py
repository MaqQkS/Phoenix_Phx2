"""Stage 27.3 provider-ingest record-shape and closed-set tests.

Pins:

  * ``EVENT_KIND_VALUES`` is the locked closed-set tuple
    (``SWAP`` / ``MIGRATION`` / ``MINT`` / ``UNKNOWN_EVENT_KIND``).
  * ``SUPPORTED_EVENT_KINDS`` is the subset the composer treats as
    classifiable.
  * ``COMPOSITION_STATUS_VALUES`` includes every status named in
    the Stage 27.3 brief (``COMPOSED`` /
    ``SKIPPED_UNSUPPORTED_EVENT`` / ``SKIPPED_MISSING_TOKEN`` /
    ``CLASSIFIED_UNKNOWN`` / ``CLASSIFIED_DISAGREE`` / ``ERROR``).
  * ``COMPOSITION_REASON_VALUES`` includes the Stage 27.3 reason
    codes used by the composer.
  * ``ProviderIngestInputRecord`` and ``ProviderIngestOutputRecord``
    are ``NamedTuple`` instances and are immutable.
  * The input record carries no raw-payload-blob field.
  * The output record carries no raw-payload-blob field.
  * The Stage 27.3 typed errors are module-local and never carry a
    raw payload blob in ``str()`` / ``repr()``.
  * ``is_forbidden_input_field_name`` rejects raw-payload-class /
    secret-class / webhook-class field names.
  * ``ingest_input_provenance_view`` returns only the safe
    provenance subset.
  * The Stage 27.3 schema-version handle is stable.
"""

from __future__ import annotations

import pytest

from PHX2.stage27 import provider_ingest_contracts as errors
from PHX2.stage27 import provider_ingest_models as m


# ---------------------------------------------------------------------------
# Closed-set vocabulary pins
# ---------------------------------------------------------------------------


def test_event_kind_values_locked_closed_set():
    assert m.EVENT_KIND_VALUES == (
        "SWAP",
        "MIGRATION",
        "MINT",
        "UNKNOWN_EVENT_KIND",
    )


def test_supported_event_kinds_is_subset_of_event_kind_values():
    for kind in m.SUPPORTED_EVENT_KINDS:
        assert kind in m.EVENT_KIND_VALUES
    assert "UNKNOWN_EVENT_KIND" not in m.SUPPORTED_EVENT_KINDS


def test_event_kind_constants_match_tuple():
    assert m.EVENT_KIND_SWAP == "SWAP"
    assert m.EVENT_KIND_MIGRATION == "MIGRATION"
    assert m.EVENT_KIND_MINT == "MINT"
    assert m.EVENT_KIND_UNKNOWN == "UNKNOWN_EVENT_KIND"


@pytest.mark.parametrize(
    "expected",
    (
        "COMPOSED",
        "SKIPPED_UNSUPPORTED_EVENT",
        "SKIPPED_MISSING_TOKEN",
        "CLASSIFIED_UNKNOWN",
        "CLASSIFIED_DISAGREE",
        "ERROR",
    ),
)
def test_composition_status_values_include_locked_brief_set(
    expected,
):
    assert expected in m.COMPOSITION_STATUS_VALUES


def test_composition_status_constants_match_tuple():
    assert m.COMPOSITION_STATUS_COMPOSED == "COMPOSED"
    assert (
        m.COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT
        == "SKIPPED_UNSUPPORTED_EVENT"
    )
    assert (
        m.COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN
        == "SKIPPED_MISSING_TOKEN"
    )
    assert (
        m.COMPOSITION_STATUS_CLASSIFIED_UNKNOWN
        == "CLASSIFIED_UNKNOWN"
    )
    assert (
        m.COMPOSITION_STATUS_CLASSIFIED_DISAGREE
        == "CLASSIFIED_DISAGREE"
    )
    assert m.COMPOSITION_STATUS_ERROR == "ERROR"


@pytest.mark.parametrize(
    "expected",
    (
        "OK",
        "UNSUPPORTED_EVENT_KIND",
        "MISSING_TOKEN_MINT",
        "PAIR_UNRESOLVED",
        "PAIR_DISAGREE",
        "ADAPTER_REJECTED_RAW_PAYLOAD",
        "INVALID_INPUT_SHAPE",
    ),
)
def test_composition_reason_values_include_locked_brief_set(
    expected,
):
    assert expected in m.COMPOSITION_REASON_VALUES


# ---------------------------------------------------------------------------
# Schema version handle
# ---------------------------------------------------------------------------


def test_stage27_3_schema_version_is_stable_string():
    assert isinstance(m.STAGE27_3_SCHEMA_VERSION, str)
    assert m.STAGE27_3_SCHEMA_VERSION != ""


def test_stage27_3_minor_version_is_27_3():
    assert m.STAGE27_3_MINOR_VERSION == "27.3"


# ---------------------------------------------------------------------------
# Record-shape immutability
# ---------------------------------------------------------------------------


def test_input_record_is_namedtuple_immutable():
    record = m.ProviderIngestInputRecord()
    assert isinstance(record, tuple)
    assert hasattr(record, "_fields")
    with pytest.raises(AttributeError):
        record.provider_id = "spoof"  # type: ignore[misc]


def test_output_record_is_namedtuple_immutable():
    record = m.ProviderIngestOutputRecord(
        provider_id=None,
        provider_event_id=None,
        normalized_event_id=None,
        event_kind="UNKNOWN_EVENT_KIND",
        observed_at_utc=None,
        token_mint=None,
        quote_mint=None,
        pair_quote_asset="UNKNOWN",
        pair_pair_type="UNKNOWN",
        pair_bonding_curve_version="UNKNOWN",
        pair_detection_status="UNRESOLVED",
        pair_detection_confidence="NONE",
        pair_detection_reason="NO_EVIDENCE",
        pair_live_policy="LIVE_SUPPRESS_UNKNOWN",
        pair_calibration_lane="UNKNOWN_PAIR_OBSERVE_ONLY",
        raw_capture_ref=None,
        source_summary=None,
        composition_status="SKIPPED_UNSUPPORTED_EVENT",
        composition_reason="UNSUPPORTED_EVENT_KIND",
        schema_version=m.STAGE27_3_SCHEMA_VERSION,
    )
    assert isinstance(record, tuple)
    with pytest.raises(AttributeError):
        record.provider_id = "spoof"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Input record carries no raw-payload-blob field
# ---------------------------------------------------------------------------


_INPUT_FIELD_NAMES: tuple[str, ...] = (
    m.ProviderIngestInputRecord._fields
)
_OUTPUT_FIELD_NAMES: tuple[str, ...] = (
    m.ProviderIngestOutputRecord._fields
)


@pytest.mark.parametrize("field", _INPUT_FIELD_NAMES)
def test_input_field_name_is_not_raw_payload_class(field):
    assert not m.is_forbidden_input_field_name(field), (
        f"input record field {field!r} is raw-payload-class"
    )


@pytest.mark.parametrize("field", _OUTPUT_FIELD_NAMES)
def test_output_field_name_is_not_raw_payload_class(field):
    assert not m.is_forbidden_input_field_name(field), (
        f"output record field {field!r} is raw-payload-class"
    )


def test_input_record_default_is_all_none_except_event_kind():
    record = m.ProviderIngestInputRecord()
    assert record.provider_id is None
    assert record.provider_event_id is None
    assert record.normalized_event_id is None
    assert record.event_kind == m.EVENT_KIND_UNKNOWN
    assert record.observed_at_utc is None
    assert record.token_mint is None
    assert record.pool_account is None
    assert record.pool_program_id is None
    assert record.base_mint is None
    assert record.quote_mint is None
    assert record.bonding_curve_program_id is None
    assert record.bonding_curve_version_hint is None
    assert record.migration_event_quote_asset_hint is None
    assert record.provider_quote_asset_hint is None
    assert record.provider_pair_type_hint is None
    assert record.provider_bonding_curve_version_hint is None
    assert record.raw_capture_ref is None
    assert record.source_summary is None


# ---------------------------------------------------------------------------
# Forbidden-field-name guard
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    (
        "raw_payload",
        "raw_payload_blob",
        "payload_summary",
        "payload",
        "secret",
        "api_key",
        "apikey",
        "webhook",
        "webhook_url",
        "discord_webhook",
        "private_key",
        "credentials",
    ),
)
def test_forbidden_input_field_name_rejected(name):
    assert m.is_forbidden_input_field_name(name)


@pytest.mark.parametrize(
    "name",
    (
        "provider_id",
        "provider_event_id",
        "normalized_event_id",
        "token_mint",
        "pool_account",
        "quote_mint",
        "raw_capture_ref",
        "source_summary",
    ),
)
def test_safe_input_field_name_allowed(name):
    assert not m.is_forbidden_input_field_name(name)


def test_forbidden_input_field_name_handles_non_string():
    assert not m.is_forbidden_input_field_name(None)
    assert not m.is_forbidden_input_field_name(123)
    assert not m.is_forbidden_input_field_name(["payload"])


# ---------------------------------------------------------------------------
# Provenance projector
# ---------------------------------------------------------------------------


def test_ingest_input_provenance_view_returns_only_safe_fields():
    record = m.ProviderIngestInputRecord(
        provider_id="stage21_fake_provider",
        provider_event_id="prov-1",
        normalized_event_id="evt_aaa",
        token_mint="mint-AAA",
        quote_mint="quote-XYZ",
        raw_capture_ref="raw_hash_aaa",
        source_summary="fake-fixture",
    )
    view = m.ingest_input_provenance_view(record)
    assert view == {
        "provider_id": "stage21_fake_provider",
        "provider_event_id": "prov-1",
        "normalized_event_id": "evt_aaa",
        "raw_capture_ref": "raw_hash_aaa",
        "source_summary": "fake-fixture",
    }
    # The pair / mint / pool fields are NOT exposed by the
    # provenance projector.
    assert "token_mint" not in view
    assert "quote_mint" not in view


# ---------------------------------------------------------------------------
# Module-local typed errors
# ---------------------------------------------------------------------------


def test_invalid_event_error_is_stage_27_3_local():
    exc = errors.Stage27ProviderIngestInvalidEventError(
        "shape", offending_type_name="dict"
    )
    assert isinstance(exc, errors.Stage27ProviderIngestError)
    assert isinstance(exc, Exception)
    # The error must NOT carry a payload blob via str()/repr().
    text = str(exc) + repr(exc)
    assert "payload" not in text.lower()


def test_raw_payload_rejected_error_carries_only_field_name():
    exc = errors.Stage27ProviderIngestRawPayloadRejectedError(
        "webhook_url"
    )
    assert isinstance(exc, errors.Stage27ProviderIngestError)
    text = str(exc)
    assert "webhook_url" in text
    # Errors must never carry an actual URL value (no scheme prefix).
    assert "://" not in text


def test_unknown_vocabulary_error_carries_only_kind_and_value():
    exc = errors.Stage27UnknownProviderIngestVocabularyError(
        "event_kind", "NOT_A_KIND"
    )
    text = str(exc)
    assert "event_kind" in text
    assert "NOT_A_KIND" in text


# ---------------------------------------------------------------------------
# Closed-set assertion helpers
# ---------------------------------------------------------------------------


def test_assert_event_kind_accepts_known_value():
    for value in m.EVENT_KIND_VALUES:
        assert errors.assert_event_kind(value) == value


def test_assert_event_kind_rejects_unknown_value():
    with pytest.raises(
        errors.Stage27UnknownProviderIngestVocabularyError
    ):
        errors.assert_event_kind("BOGUS")


def test_assert_composition_status_accepts_known_value():
    for value in m.COMPOSITION_STATUS_VALUES:
        assert errors.assert_composition_status(value) == value


def test_assert_composition_status_rejects_unknown_value():
    with pytest.raises(
        errors.Stage27UnknownProviderIngestVocabularyError
    ):
        errors.assert_composition_status("BOGUS")


def test_assert_composition_reason_accepts_known_value():
    for value in m.COMPOSITION_REASON_VALUES:
        assert errors.assert_composition_reason(value) == value


def test_assert_composition_reason_rejects_unknown_value():
    with pytest.raises(
        errors.Stage27UnknownProviderIngestVocabularyError
    ):
        errors.assert_composition_reason("BOGUS")
