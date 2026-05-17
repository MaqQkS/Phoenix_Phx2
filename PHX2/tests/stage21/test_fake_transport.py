"""Stage 21.2 fake_transport tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from PHX2.stage21.clock import FrozenClock
from PHX2.stage21.errors import Stage21Error, Stage21TelemetryError
from PHX2.stage21.fake_transport import (
    FakePrivateTransport,
    FakeTransportCaptureRecord,
    FakeTransportResult,
    STAGE21_FAKE_TRANSPORT_ACTUALLY_SENT_ON_NETWORK,
    STAGE21_FAKE_TRANSPORT_FAKE_ONLY_MARKER,
    STAGE21_FAKE_TRANSPORT_FORBIDDEN_METHOD_NAMES,
)
from PHX2.stage21.normalized_events import normalize_fake_event
from PHX2.stage21.ping_builder import (
    build_candidate_from_normalized_event,
    build_private_preview_payload,
)
from PHX2.stage21.ping_payloads import (
    STAGE21_FAKE_CHAIN_NAME,
    STAGE21_FAKE_PROVIDER_NAME,
)


def _payload(mint: str = "FAKE_MINT_AAAA"):
    norm = normalize_fake_event(
        provider_event_id="fake_pev_aaaa1111",
        provider_name=STAGE21_FAKE_PROVIDER_NAME,
        source_kind="stage21_fake_source",
        chain=STAGE21_FAKE_CHAIN_NAME,
        mint=mint,
        event_type="fake_swap",
        observed_at_utc="2026-05-17T12:00:00Z",
        slot=100,
        signature="fake_sig_aaaa1111",
        raw_payload={"fake_amount": 1000},
    )
    return build_private_preview_payload(
        build_candidate_from_normalized_event(norm)
    )


def _frozen_clock(iso: str = "2026-05-17T12:00:00+00:00") -> FrozenClock:
    return FrozenClock(datetime.fromisoformat(iso))


# ---------------------------------------------------------------------------
# Fake-only marker
# ---------------------------------------------------------------------------


def test_fake_transport_class_exposes_fake_only_marker():
    assert FakePrivateTransport.IS_FAKE_ONLY is True
    assert STAGE21_FAKE_TRANSPORT_FAKE_ONLY_MARKER is True


# ---------------------------------------------------------------------------
# Capture happy path
# ---------------------------------------------------------------------------


def test_capture_returns_captured_result_for_valid_payload():
    transport = FakePrivateTransport(clock=_frozen_clock())
    result = transport.capture(_payload())
    assert isinstance(result, FakeTransportResult)
    assert result.captured is True
    assert result.rejection_reason == ""
    assert result.capture_record is not None


def test_capture_appends_to_captures_list_in_order():
    transport = FakePrivateTransport(clock=_frozen_clock())
    transport.capture(_payload(mint="FAKE_MINT_A"))
    transport.capture(_payload(mint="FAKE_MINT_B"))
    captures = transport.captures()
    assert len(captures) == 2
    assert captures[0].mint == "FAKE_MINT_A"
    assert captures[1].mint == "FAKE_MINT_B"


def test_capture_record_records_payload_hash():
    transport = FakePrivateTransport(clock=_frozen_clock())
    payload = _payload()
    result = transport.capture(payload)
    assert result.capture_record is not None
    assert result.capture_record.payload_hash == payload.payload_hash


def test_capture_record_uses_injected_clock_for_captured_at_utc():
    clock = _frozen_clock("2026-05-17T12:34:56+00:00")
    transport = FakePrivateTransport(clock=clock)
    result = transport.capture(_payload())
    assert result.capture_record is not None
    assert result.capture_record.captured_at_utc == "2026-05-17T12:34:56Z"


def test_capture_is_deterministic_with_frozen_clock():
    a = FakePrivateTransport(clock=_frozen_clock())
    b = FakePrivateTransport(clock=_frozen_clock())
    ra = a.capture(_payload())
    rb = b.capture(_payload())
    assert ra.capture_record == rb.capture_record


def test_capture_records_are_captureid_prefixed():
    transport = FakePrivateTransport(clock=_frozen_clock())
    result = transport.capture(_payload())
    assert result.capture_record is not None
    assert result.capture_record.capture_id.startswith("cap_")


# ---------------------------------------------------------------------------
# Rejection paths
# ---------------------------------------------------------------------------


def test_capture_rejects_non_payload_input():
    transport = FakePrivateTransport(clock=_frozen_clock())
    with pytest.raises(Stage21TelemetryError) as excinfo:
        transport.capture("not a payload")  # type: ignore[arg-type]
    assert excinfo.value.code == "E2110"


def test_capture_rejects_payload_with_wrong_stage():
    transport = FakePrivateTransport(clock=_frozen_clock())
    bad = _payload()._replace(stage="21.3")
    with pytest.raises(Stage21TelemetryError) as excinfo:
        transport.capture(bad)
    assert excinfo.value.code == "E2111"
    assert transport.capture_count == 0


def test_capture_rejects_payload_with_wrong_visibility():
    transport = FakePrivateTransport(clock=_frozen_clock())
    bad = _payload()._replace(visibility="public_view")
    with pytest.raises(Stage21TelemetryError) as excinfo:
        transport.capture(bad)
    assert excinfo.value.code == "E2111"


def test_capture_rejects_payload_with_false_operator_only():
    transport = FakePrivateTransport(clock=_frozen_clock())
    bad = _payload()._replace(operator_only=False)
    with pytest.raises(Stage21TelemetryError) as excinfo:
        transport.capture(bad)
    assert excinfo.value.code == "E2111"


def test_capture_rejects_payload_with_true_live_mode():
    transport = FakePrivateTransport(clock=_frozen_clock())
    bad = _payload()._replace(live_mode=True)
    with pytest.raises(Stage21TelemetryError) as excinfo:
        transport.capture(bad)
    assert excinfo.value.code == "E2111"


def test_capture_rejects_payload_with_wrong_dispatch_target():
    transport = FakePrivateTransport(clock=_frozen_clock())
    bad = _payload()._replace(dispatch_target="real_private_transport")
    with pytest.raises(Stage21TelemetryError) as excinfo:
        transport.capture(bad)
    assert excinfo.value.code == "E2111"


def test_capture_rejects_truthy_non_bool_operator_only():
    transport = FakePrivateTransport(clock=_frozen_clock())
    bad = _payload()._replace(operator_only=1)  # type: ignore[arg-type]
    with pytest.raises(Stage21TelemetryError) as excinfo:
        transport.capture(bad)
    assert excinfo.value.code == "E2111"


def test_capture_record_carries_locked_marker_fields_unchanged():
    transport = FakePrivateTransport(clock=_frozen_clock())
    result = transport.capture(_payload())
    record = result.capture_record
    assert record is not None
    assert isinstance(record, FakeTransportCaptureRecord)
    assert record.stage == "21.2"
    assert record.visibility == "private_preview"
    assert record.operator_only is True
    assert record.live_mode is False
    assert record.dispatch_target == "fake_private_transport"


# ---------------------------------------------------------------------------
# Capture sequence
# ---------------------------------------------------------------------------


def test_capture_sequence_counter_increments_starting_at_zero():
    transport = FakePrivateTransport(clock=_frozen_clock())
    r1 = transport.capture(_payload(mint="FAKE_MINT_A"))
    r2 = transport.capture(_payload(mint="FAKE_MINT_B"))
    assert r1.capture_record is not None
    assert r2.capture_record is not None
    assert r1.capture_record.capture_sequence == 0
    assert r2.capture_record.capture_sequence == 1


# ---------------------------------------------------------------------------
# No network / credential requirements
# ---------------------------------------------------------------------------


def test_fake_transport_constructs_without_webhook_url_or_credentials():
    # Construction is keyword-only with an optional clock; there
    # are no credential / target / webhook fields.
    transport = FakePrivateTransport()
    assert transport.capture_count == 0


def test_fake_transport_default_clock_is_used_when_clock_not_supplied():
    # Default clock returns SystemClock-derived now(); the capture
    # still produces a valid ISO-8601 UTC string and never raises.
    transport = FakePrivateTransport()
    result = transport.capture(_payload())
    assert result.capture_record is not None
    captured = result.capture_record.captured_at_utc
    # Stage 21 convention: trailing Z.
    assert captured.endswith("Z")


# ---------------------------------------------------------------------------
# Stage 21.2 remediation R3: structured_payload + recomputed_payload_hash
# ---------------------------------------------------------------------------


from types import MappingProxyType  # noqa: E402

from PHX2.stage21.ping_payloads import (  # noqa: E402
    PING_PAYLOAD_REQUIRED_MARKER_KEYS,
)


def test_capture_record_includes_structured_payload_field():
    """R3: FakeTransportCaptureRecord gains a structured_payload field."""
    transport = FakePrivateTransport(clock=_frozen_clock())
    payload = _payload()
    result = transport.capture(payload)
    assert result.capture_record is not None
    assert hasattr(result.capture_record, "structured_payload")


def test_capture_record_structured_payload_matches_source_canonically():
    """R3: captured structured_payload is canonical-equal to the source.

    The fake transport rebuilds the structured payload via the
    canonical helper (sorted keys recursively, deep-frozen);
    every key/value pair from the source payload must appear in
    the captured record's structured_payload mapping with the
    same value.
    """
    transport = FakePrivateTransport(clock=_frozen_clock())
    payload = _payload()
    result = transport.capture(payload)
    assert result.capture_record is not None
    captured = result.capture_record.structured_payload
    source = payload.structured_payload
    assert set(captured.keys()) == set(source.keys())
    for k, v in source.items():
        assert captured[k] == v, (k, captured[k], v)


def test_capture_record_includes_recomputed_payload_hash_field():
    """R3: FakeTransportCaptureRecord gains a recomputed_payload_hash field."""
    transport = FakePrivateTransport(clock=_frozen_clock())
    result = transport.capture(_payload())
    assert result.capture_record is not None
    assert hasattr(result.capture_record, "recomputed_payload_hash")


def test_recomputed_payload_hash_matches_payload_hash_on_valid_capture():
    """R3: the recomputed hash equals the caller's payload_hash."""
    transport = FakePrivateTransport(clock=_frozen_clock())
    payload = _payload()
    result = transport.capture(payload)
    assert result.capture_record is not None
    assert (
        result.capture_record.recomputed_payload_hash
        == payload.payload_hash
    )
    assert (
        result.capture_record.recomputed_payload_hash
        == result.capture_record.payload_hash
    )


def test_recomputed_payload_hash_is_64_lowercase_hex():
    """R3: recomputed_payload_hash is sha256 hex format."""
    transport = FakePrivateTransport(clock=_frozen_clock())
    result = transport.capture(_payload())
    assert result.capture_record is not None
    rec_hash = result.capture_record.recomputed_payload_hash
    assert len(rec_hash) == 64
    assert all(c in "0123456789abcdef" for c in rec_hash)


def test_capture_raises_e2170_on_payload_hash_mismatch():
    """R3: hash mismatch raises Stage21Error E2170 at capture time."""
    transport = FakePrivateTransport(clock=_frozen_clock())
    payload = _payload()
    poisoned = payload._replace(payload_hash="0" * 64)
    with pytest.raises(Stage21Error) as exc:
        transport.capture(poisoned)
    assert exc.value.code == "E2170"
    # No record was appended on the failed capture.
    assert transport.capture_count == 0


def test_capture_raises_e2170_when_payload_hash_is_wrong_hex():
    """R3: any non-matching valid-hex hash also raises E2170."""
    transport = FakePrivateTransport(clock=_frozen_clock())
    payload = _payload()
    # Flip the first hex char so the hash differs but is still
    # valid hex (so the payload-hash-format check inside the
    # ping builder doesn't trip first).
    bad_first = "f" if payload.payload_hash[0] != "f" else "e"
    poisoned = payload._replace(
        payload_hash=bad_first + payload.payload_hash[1:]
    )
    with pytest.raises(Stage21Error) as exc:
        transport.capture(poisoned)
    assert exc.value.code == "E2170"


def test_capture_rejects_unsafe_structured_payload_before_capture():
    """R3: an unsafe structured_payload is rejected before record creation.

    We can't smuggle an unsafe value through the public ping
    builder (it runs the same safe_content validation), but we
    can directly construct a poisoned ``PrivatePreviewPingPayload``
    via ``_replace`` for the test. The transport must reject it
    via safe_content BEFORE the canonical-JSON / hash steps,
    and BEFORE any record is appended.
    """
    transport = FakePrivateTransport(clock=_frozen_clock())
    payload = _payload()
    # Inject an unsafe value (URL fragment) into a non-marker key
    # of the structured payload. The marker keys remain locked
    # so the marker assertion still passes; safe_content should
    # then reject the unsafe value.
    structured = dict(payload.structured_payload)
    structured["reason"] = "https" + "://attacker.example/leak"
    poisoned = payload._replace(structured_payload=MappingProxyType(structured))
    with pytest.raises(Stage21Error) as exc:
        transport.capture(poisoned)
    # The safe_content layer raises E2153 (forbidden_substring).
    # Any code in the safe_content E2150..E2158 range or E2170
    # (if hash mismatch is detected first) is acceptable evidence
    # of fail-closed behavior, but E2153 is the locked
    # forbidden-substring code we expect.
    assert exc.value.code == "E2153"
    # No record appended on the failed capture.
    assert transport.capture_count == 0


def test_captured_structured_payload_is_immutable_top_level():
    """R3: captured structured_payload is a MappingProxyType."""
    transport = FakePrivateTransport(clock=_frozen_clock())
    result = transport.capture(_payload())
    assert result.capture_record is not None
    sp = result.capture_record.structured_payload
    assert isinstance(sp, MappingProxyType)
    with pytest.raises(TypeError):
        sp["new_key"] = "leak"  # type: ignore[index]
    with pytest.raises(TypeError):
        del sp["stage"]  # type: ignore[arg-type]


def test_captured_structured_payload_is_deep_frozen_for_nested_mappings():
    """R3: nested mappings inside structured_payload are also frozen.

    Stage 21.2 fake fixtures don't currently produce nested
    mappings in the structured_payload, so we exercise the deep
    freeze by directly constructing a payload with a nested
    mapping in a non-marker field and capturing it. The captured
    nested mapping must also reject mutation.
    """
    transport = FakePrivateTransport(clock=_frozen_clock())
    payload = _payload()
    # We must keep the payload_hash consistent with the new
    # structured_payload, so we recompute via the same canonical
    # JSON the transport uses. The transport's hash-mismatch
    # check would otherwise trip first.
    from PHX2.stage21.fake_transport import _canonical_json_string
    import hashlib
    base = dict(payload.structured_payload)
    base["reason"] = "stage21_2_fake_event_promotion"  # safe label
    base["nested_data"] = {"inner_amount": 42, "inner_decimals": 6}
    canonical = _canonical_json_string(base)
    new_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    poisoned = payload._replace(
        structured_payload=MappingProxyType(base),
        payload_hash=new_hash,
    )
    result = transport.capture(poisoned)
    assert result.capture_record is not None
    nested = result.capture_record.structured_payload["nested_data"]
    assert isinstance(nested, MappingProxyType)
    with pytest.raises(TypeError):
        nested["leak"] = 99  # type: ignore[index]


def test_capture_marker_rejection_behavior_unchanged_by_r3():
    """R3 preserves the existing marker rejection behavior.

    R3 added a new canonical / validate / hash flow but did NOT
    relax any of the existing marker rejection paths. Verify
    that wrong-marker payloads still raise the same
    Stage21TelemetryError(E2111) the existing test suite asserts.
    """
    transport = FakePrivateTransport(clock=_frozen_clock())
    bad = _payload()._replace(stage="21.3")
    with pytest.raises(Stage21TelemetryError) as exc:
        transport.capture(bad)
    assert exc.value.code == "E2111"


def test_actually_sent_on_network_class_attribute_is_locked_false():
    """R3: FakePrivateTransport.ACTUALLY_SENT_ON_NETWORK == False (locked)."""
    assert FakePrivateTransport.ACTUALLY_SENT_ON_NETWORK is False
    assert STAGE21_FAKE_TRANSPORT_ACTUALLY_SENT_ON_NETWORK is False


def test_actually_sent_on_network_is_in_capture_record_and_false():
    """R3: each captured record explicitly carries actually_sent_on_network=False."""
    transport = FakePrivateTransport(clock=_frozen_clock())
    result = transport.capture(_payload())
    assert result.capture_record is not None
    assert result.capture_record.actually_sent_on_network is False


def test_capture_api_exposes_no_send_dispatch_publish_transmit():
    """R3: the capture API has no real-send-shaped methods.

    Walks every attribute on both the class and an instance and
    asserts none of the locked forbidden method names appears.
    Pinned by ``STAGE21_FAKE_TRANSPORT_FORBIDDEN_METHOD_NAMES``.
    """
    expected_forbidden = ("send", "dispatch", "publish", "transmit")
    assert (
        set(STAGE21_FAKE_TRANSPORT_FORBIDDEN_METHOD_NAMES)
        == set(expected_forbidden)
    )
    transport = FakePrivateTransport(clock=_frozen_clock())
    for forbidden in STAGE21_FAKE_TRANSPORT_FORBIDDEN_METHOD_NAMES:
        assert not hasattr(FakePrivateTransport, forbidden), (
            f"FakePrivateTransport class exposes forbidden method "
            f"{forbidden!r}"
        )
        assert not hasattr(transport, forbidden), (
            f"FakePrivateTransport instance exposes forbidden method "
            f"{forbidden!r}"
        )
        # Also verify the name does not appear in the public
        # capture API (the instance attribute scan above covers
        # this; the dir() scan adds defense against descriptor /
        # __getattr__ shenanigans).
        assert forbidden not in dir(FakePrivateTransport), (
            f"dir(FakePrivateTransport) contains {forbidden!r}"
        )


def test_public_summary_carries_new_r3_fields():
    """R3: public_summary includes structured_payload + recomputed hash."""
    transport = FakePrivateTransport(clock=_frozen_clock())
    result = transport.capture(_payload())
    assert result.capture_record is not None
    summary = result.capture_record.public_summary()
    assert "structured_payload" in summary
    assert "recomputed_payload_hash" in summary
    assert "actually_sent_on_network" in summary
    assert summary["actually_sent_on_network"] is False
    # structured_payload in the public_summary is a plain dict
    # (for JSON serialization) but contains the same keys as the
    # frozen mapping on the record.
    assert isinstance(summary["structured_payload"], dict)
    assert (
        set(summary["structured_payload"].keys())
        == set(result.capture_record.structured_payload.keys())
    )


def test_capture_is_byte_deterministic_with_frozen_clock_for_r3_fields():
    """R3: recomputed hash + structured_payload are deterministic per run."""
    a = FakePrivateTransport(clock=_frozen_clock())
    b = FakePrivateTransport(clock=_frozen_clock())
    payload = _payload()
    ra = a.capture(payload)
    rb = b.capture(payload)
    assert ra.capture_record is not None
    assert rb.capture_record is not None
    assert (
        ra.capture_record.recomputed_payload_hash
        == rb.capture_record.recomputed_payload_hash
    )
    assert (
        dict(ra.capture_record.structured_payload)
        == dict(rb.capture_record.structured_payload)
    )
