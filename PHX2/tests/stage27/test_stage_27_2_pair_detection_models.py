"""Stage 27.2 pair-detection record-shape tests.

Pins:

  * Every record (``PairDetectionInputRecord`` /
    ``PairDetectionEvidenceRecord`` /
    ``PairDetectionOutputRecord``) is a ``NamedTuple`` and is
    immutable (``setattr`` raises ``AttributeError``).
  * The input record carries no raw-payload-blob field; the only
    payload-related field is the safe ``source_payload_reference``
    handle.
  * The output record carries no raw-payload-blob field.
  * Default-constructible input record has every field set to
    ``None`` (caller may pass partial evidence).
  * The Stage 27.2 typed errors are module-local and never carry a
    raw payload blob in ``str()`` / ``repr()``.
"""

from __future__ import annotations

import pytest

from PHX2.stage27 import pair_detection_models as m
from PHX2.stage27 import pair_detection_contracts as errors


# ---------------------------------------------------------------------------
# Record-shape immutability
# ---------------------------------------------------------------------------


def test_input_record_is_namedtuple_immutable():
    record = m.PairDetectionInputRecord()
    assert isinstance(record, tuple)
    # NamedTuple instances expose the ``_fields`` attribute, which
    # is the canonical duck-type marker for a NamedTuple subclass.
    assert hasattr(record, "_fields")
    with pytest.raises(AttributeError):
        record.event_id = "spoof"  # type: ignore[misc]


def test_evidence_record_is_namedtuple_immutable():
    record = m.PairDetectionEvidenceRecord(
        source="POOL_QUOTE_MINT",
        quote_asset_verdict="SOL",
        pair_type_verdict="PUMP_SOL",
        bonding_curve_version_verdict="SOL_LEGACY",
        confidence="HIGH",
        reason=None,
    )
    assert isinstance(record, tuple)
    with pytest.raises(AttributeError):
        record.source = "PROVIDER_PAYLOAD"  # type: ignore[misc]


def test_output_record_is_namedtuple_immutable():
    record = m.PairDetectionOutputRecord(
        quote_asset="SOL",
        quote_mint=None,
        pair_type="PUMP_SOL",
        bonding_curve_version="SOL_LEGACY",
        pair_detection_status="CONFIRMED",
        pair_detection_confidence="HIGH",
        pair_detection_reason="CONFIRMED_AGREEMENT",
        evidence_count=1,
        disagreement_count=0,
        live_policy="LIVE_ALLOWED",
        calibration_lane="EXISTING_SOL_LANE",
    )
    assert isinstance(record, tuple)
    with pytest.raises(AttributeError):
        record.quote_asset = "USDC"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Input-record default constructibility
# ---------------------------------------------------------------------------


def test_input_record_is_default_constructible_with_all_none():
    record = m.PairDetectionInputRecord()
    for field_name in record._fields:
        assert getattr(record, field_name) is None, (
            f"default input record field {field_name!r} should "
            f"default to None"
        )


def test_input_record_field_set_is_exactly_the_locked_set():
    expected = {
        "event_id",
        "token_mint",
        "pool_account",
        "pool_program_id",
        "base_mint",
        "quote_mint",
        "bonding_curve_program_id",
        "bonding_curve_version_hint",
        "migration_event_quote_asset_hint",
        "provider_quote_asset_hint",
        "provider_pair_type_hint",
        "provider_bonding_curve_version_hint",
        "observed_at_utc",
        "fetched_at_utc",
        "source_payload_reference",
    }
    assert set(m.PairDetectionInputRecord._fields) == expected


def test_evidence_record_field_set_is_exactly_the_locked_set():
    expected = {
        "source",
        "quote_asset_verdict",
        "pair_type_verdict",
        "bonding_curve_version_verdict",
        "confidence",
        "reason",
    }
    assert set(m.PairDetectionEvidenceRecord._fields) == expected


def test_output_record_field_set_is_exactly_the_locked_set():
    expected = {
        "quote_asset",
        "quote_mint",
        "pair_type",
        "bonding_curve_version",
        "pair_detection_status",
        "pair_detection_confidence",
        "pair_detection_reason",
        "evidence_count",
        "disagreement_count",
        "live_policy",
        "calibration_lane",
    }
    assert set(m.PairDetectionOutputRecord._fields) == expected


# ---------------------------------------------------------------------------
# Raw-payload-blob safety
# ---------------------------------------------------------------------------


_RAW_PAYLOAD_FIELD_SUBSTRINGS: tuple[str, ...] = (
    "raw",
    "payload_bytes",
    "payload_blob",
    "payload_body",
    "payload_text",
    "payload_json",
    "raw_message",
)


def test_input_record_has_no_raw_payload_field():
    """The only payload-related field on the input record is the
    safe ``source_payload_reference`` handle.
    """
    for field_name in m.PairDetectionInputRecord._fields:
        if field_name == "source_payload_reference":
            continue
        lower = field_name.lower()
        for needle in _RAW_PAYLOAD_FIELD_SUBSTRINGS:
            assert needle not in lower, (
                f"input record field {field_name!r} smells like a "
                f"raw provider payload blob (substring {needle!r})"
            )


def test_output_record_has_no_raw_payload_field():
    for field_name in m.PairDetectionOutputRecord._fields:
        lower = field_name.lower()
        for needle in _RAW_PAYLOAD_FIELD_SUBSTRINGS:
            assert needle not in lower, (
                f"output record field {field_name!r} smells like a "
                f"raw provider payload blob (substring {needle!r})"
            )


def test_evidence_record_has_no_raw_payload_field():
    for field_name in m.PairDetectionEvidenceRecord._fields:
        lower = field_name.lower()
        for needle in _RAW_PAYLOAD_FIELD_SUBSTRINGS:
            assert needle not in lower, (
                f"evidence record field {field_name!r} smells like "
                f"a raw provider payload blob (substring {needle!r})"
            )


def test_input_record_source_payload_reference_is_just_a_string():
    """The ``source_payload_reference`` field is a short string
    handle, never a raw payload blob. We pin the type at the
    annotation level by constructing with a short string and
    asserting the record carries it verbatim.
    """
    handle = "stage22_capture:0xabc123"
    record = m.PairDetectionInputRecord(source_payload_reference=handle)
    assert record.source_payload_reference == handle
    assert len(handle) < 100, (
        "the source_payload_reference test handle should be short "
        "enough to obviously be a reference and not a payload"
    )


# ---------------------------------------------------------------------------
# Typed error redaction safety
# ---------------------------------------------------------------------------


def test_invalid_pair_input_error_repr_carries_no_payload():
    err = errors.Stage27InvalidPairInputError(
        "input must be a PairDetectionInputRecord",
        offending_type_name="dict",
    )
    rep = repr(err)
    s = str(err)
    # The error carries the reason and the offending type name --
    # never a raw payload value.
    assert "dict" in s
    assert "payload" not in s.lower()
    assert "secret" not in s.lower()
    assert rep == repr(err)  # idempotent


def test_unknown_pair_vocabulary_error_repr_carries_only_kind_and_value():
    err = errors.Stage27UnknownPairVocabularyError(
        kind="quote_asset", value="ETH"
    )
    s = str(err)
    assert "quote_asset" in s
    assert "ETH" in s
    assert "payload" not in s.lower()
    assert "secret" not in s.lower()


def test_pair_detection_errors_are_module_local_exception_subclasses():
    assert issubclass(
        errors.Stage27PairDetectionError, Exception
    )
    assert issubclass(
        errors.Stage27InvalidPairInputError,
        errors.Stage27PairDetectionError,
    )
    assert issubclass(
        errors.Stage27UnknownPairVocabularyError,
        errors.Stage27PairDetectionError,
    )


# ---------------------------------------------------------------------------
# Closed-set assertion helpers
# ---------------------------------------------------------------------------


def test_assert_quote_asset_accepts_known_values():
    assert errors.assert_quote_asset("SOL") == "SOL"
    assert errors.assert_quote_asset("USDC") == "USDC"
    assert errors.assert_quote_asset("UNKNOWN") == "UNKNOWN"


def test_assert_quote_asset_rejects_unknown_tokens():
    with pytest.raises(errors.Stage27UnknownPairVocabularyError):
        errors.assert_quote_asset("ETH")


def test_assert_pair_type_accepts_known_values():
    assert errors.assert_pair_type("PUMP_SOL") == "PUMP_SOL"
    assert errors.assert_pair_type("PUMP_USDC") == "PUMP_USDC"
    assert errors.assert_pair_type("UNKNOWN") == "UNKNOWN"


def test_assert_pair_type_rejects_unknown_tokens():
    with pytest.raises(errors.Stage27UnknownPairVocabularyError):
        errors.assert_pair_type("RAY_SOL")


def test_assert_bonding_curve_version_accepts_known_values():
    assert (
        errors.assert_bonding_curve_version("SOL_LEGACY")
        == "SOL_LEGACY"
    )
    assert (
        errors.assert_bonding_curve_version("USDC_FIXED")
        == "USDC_FIXED"
    )


def test_assert_bonding_curve_version_rejects_unknown_tokens():
    with pytest.raises(errors.Stage27UnknownPairVocabularyError):
        errors.assert_bonding_curve_version("USDC_V2")


def test_assert_pair_detection_status_rejects_unknown_tokens():
    for value in ("CONFIRMED", "PROVIDER_ONLY", "DISAGREE", "UNRESOLVED"):
        assert errors.assert_pair_detection_status(value) == value
    with pytest.raises(errors.Stage27UnknownPairVocabularyError):
        errors.assert_pair_detection_status("APPROVED")


def test_assert_pair_detection_confidence_rejects_unknown_tokens():
    for value in ("HIGH", "MEDIUM", "LOW", "NONE"):
        assert errors.assert_pair_detection_confidence(value) == value
    with pytest.raises(errors.Stage27UnknownPairVocabularyError):
        errors.assert_pair_detection_confidence("VERY_HIGH")


def test_assert_pair_detection_source_rejects_unknown_tokens():
    for value in (
        "POOL_QUOTE_MINT",
        "BONDING_CURVE_METADATA",
        "MIGRATION_EVENT",
        "PROVIDER_PAYLOAD",
        "KNOWN_MINT_FALLBACK",
    ):
        assert errors.assert_pair_detection_source(value) == value
    with pytest.raises(errors.Stage27UnknownPairVocabularyError):
        errors.assert_pair_detection_source("ORACLE_FEED")


def test_assert_live_policy_rejects_unknown_tokens():
    for value in (
        "LIVE_ALLOWED",
        "LIVE_SUPPRESS_UNKNOWN",
        "LIVE_SUPPRESS_DISAGREE",
        "DRY_RUN_ONLY",
    ):
        assert errors.assert_live_policy(value) == value
    with pytest.raises(errors.Stage27UnknownPairVocabularyError):
        errors.assert_live_policy("LIVE_FORCED")


def test_assert_calibration_lane_rejects_unknown_tokens():
    for value in (
        "EXISTING_SOL_LANE",
        "USDC_OBSERVE_ONLY",
        "UNKNOWN_PAIR_OBSERVE_ONLY",
        "DISAGREE_PAIR_OBSERVE_ONLY",
    ):
        assert errors.assert_calibration_lane(value) == value
    with pytest.raises(errors.Stage27UnknownPairVocabularyError):
        errors.assert_calibration_lane("NEW_LANE")
