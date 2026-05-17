"""Stage 21.2 ping_builder tests."""

from __future__ import annotations

import pytest

from PHX2.stage21.errors import Stage21TelemetryError
from PHX2.stage21.normalized_events import normalize_fake_event
from PHX2.stage21.ping_builder import (
    assert_private_preview_markers,
    build_candidate_from_normalized_event,
    build_private_preview_payload,
)
from PHX2.stage21.ping_payloads import (
    FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET,
    LIVE_MODE_MARKER,
    OPERATOR_ONLY_MARKER,
    PING_PAYLOAD_REQUIRED_MARKER_KEYS,
    PRIVATE_PREVIEW_VISIBILITY,
    PrivatePreviewCandidate,
    PrivatePreviewPingPayload,
    STAGE21_2_STAGE_LABEL,
    STAGE21_FAKE_CHAIN_NAME,
    STAGE21_FAKE_PROVIDER_NAME,
)


def _norm_event():
    return normalize_fake_event(
        provider_event_id="fake_pev_aaaa1111",
        provider_name=STAGE21_FAKE_PROVIDER_NAME,
        source_kind="stage21_fake_source",
        chain=STAGE21_FAKE_CHAIN_NAME,
        mint="FAKE_MINT_AAAA",
        event_type="fake_swap",
        observed_at_utc="2026-05-17T12:00:00Z",
        slot=100,
        signature="fake_sig_aaaa1111",
        raw_payload={"fake_amount": 1000, "fake_decimals": 6},
    )


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------


def test_build_candidate_returns_private_preview_candidate():
    cand = build_candidate_from_normalized_event(_norm_event())
    assert isinstance(cand, PrivatePreviewCandidate)
    assert cand.normalized_event_id == _norm_event().event_id
    assert cand.mint == "FAKE_MINT_AAAA"
    assert cand.event_type == "fake_swap"


def test_build_candidate_id_has_cand_prefix():
    cand = build_candidate_from_normalized_event(_norm_event())
    assert cand.candidate_id.startswith("cand_")


def test_build_candidate_is_deterministic():
    a = build_candidate_from_normalized_event(_norm_event())
    b = build_candidate_from_normalized_event(_norm_event())
    assert a == b


def test_build_candidate_rejects_non_event_input():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        build_candidate_from_normalized_event("not an event")  # type: ignore[arg-type]
    assert excinfo.value.code == "E2113"


def test_build_candidate_rejects_empty_reason():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        build_candidate_from_normalized_event(_norm_event(), reason="")
    assert excinfo.value.code == "E2113"


def test_build_candidate_rejects_empty_source():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        build_candidate_from_normalized_event(_norm_event(), source="")
    assert excinfo.value.code == "E2113"


# ---------------------------------------------------------------------------
# Ping payload construction
# ---------------------------------------------------------------------------


def test_build_payload_carries_locked_markers():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    assert isinstance(payload, PrivatePreviewPingPayload)
    assert payload.stage == STAGE21_2_STAGE_LABEL
    assert payload.stage == "21.2"
    assert payload.visibility == PRIVATE_PREVIEW_VISIBILITY
    assert payload.visibility == "private_preview"
    assert payload.operator_only is True
    assert payload.live_mode is False
    assert payload.dispatch_target == FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET
    assert payload.dispatch_target == "fake_private_transport"


def test_build_payload_ping_id_has_ping_prefix():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    assert payload.ping_id.startswith("ping_")


def test_build_payload_payload_hash_is_sha256_hex():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    assert len(payload.payload_hash) == 64
    int(payload.payload_hash, 16)


def test_build_payload_structured_payload_carries_all_markers():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    for key in PING_PAYLOAD_REQUIRED_MARKER_KEYS:
        assert key in payload.structured_payload
    assert payload.structured_payload["stage"] == "21.2"
    assert payload.structured_payload["visibility"] == "private_preview"
    assert payload.structured_payload["operator_only"] is True
    assert payload.structured_payload["live_mode"] is False
    assert (
        payload.structured_payload["dispatch_target"]
        == "fake_private_transport"
    )


def test_build_payload_is_deterministic():
    cand = build_candidate_from_normalized_event(_norm_event())
    a = build_private_preview_payload(cand)
    b = build_private_preview_payload(cand)
    assert a == b
    assert a.payload_hash == b.payload_hash


def test_build_payload_rejects_non_candidate_input():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        build_private_preview_payload("not a candidate")  # type: ignore[arg-type]
    assert excinfo.value.code == "E2113"


def test_build_payload_summary_and_body_are_non_empty_non_secret():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    assert payload.summary_text != ""
    assert payload.body_text != ""
    # No secret-class strings appear.
    for forbidden in ("api_key", "secret=", "password=", "webhook"):
        assert forbidden not in payload.summary_text
        assert forbidden not in payload.body_text


def test_build_payload_excludes_routing_strings_from_structured_payload():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    structured_str = repr(dict(payload.structured_payload))
    for forbidden in (
        "public_dispatch",
        "paid_dispatch",
        "subscriber",
        "public_signal",
        "paid_signal",
        "public_channel",
        "paid_channel",
    ):
        assert forbidden not in structured_str


# ---------------------------------------------------------------------------
# Marker assertion
# ---------------------------------------------------------------------------


def test_marker_assertion_passes_for_valid_payload():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    assert_private_preview_markers(payload)  # no raise


def test_marker_assertion_rejects_wrong_stage_label():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    bad = payload._replace(stage="21.3")
    with pytest.raises(Stage21TelemetryError) as excinfo:
        assert_private_preview_markers(bad)
    assert excinfo.value.code == "E2111"


def test_marker_assertion_rejects_wrong_visibility():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    bad = payload._replace(visibility="public_view")
    with pytest.raises(Stage21TelemetryError) as excinfo:
        assert_private_preview_markers(bad)
    assert excinfo.value.code == "E2111"


def test_marker_assertion_rejects_false_operator_only():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    bad = payload._replace(operator_only=False)
    with pytest.raises(Stage21TelemetryError) as excinfo:
        assert_private_preview_markers(bad)
    assert excinfo.value.code == "E2111"


def test_marker_assertion_rejects_true_live_mode():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    bad = payload._replace(live_mode=True)
    with pytest.raises(Stage21TelemetryError) as excinfo:
        assert_private_preview_markers(bad)
    assert excinfo.value.code == "E2111"


def test_marker_assertion_rejects_truthy_non_bool_operator_only():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    bad = payload._replace(operator_only=1)  # type: ignore[arg-type]
    with pytest.raises(Stage21TelemetryError) as excinfo:
        assert_private_preview_markers(bad)
    assert excinfo.value.code == "E2111"


def test_marker_assertion_rejects_wrong_dispatch_target():
    cand = build_candidate_from_normalized_event(_norm_event())
    payload = build_private_preview_payload(cand)
    bad = payload._replace(dispatch_target="real_private_transport")
    with pytest.raises(Stage21TelemetryError) as excinfo:
        assert_private_preview_markers(bad)
    assert excinfo.value.code == "E2111"


def test_marker_assertion_rejects_non_payload_input():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        assert_private_preview_markers("not a payload")  # type: ignore[arg-type]
    assert excinfo.value.code == "E2110"


def test_marker_constants_are_locked_at_known_values():
    assert OPERATOR_ONLY_MARKER is True
    assert LIVE_MODE_MARKER is False
    assert PRIVATE_PREVIEW_VISIBILITY == "private_preview"
    assert STAGE21_2_STAGE_LABEL == "21.2"
    assert FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET == "fake_private_transport"
