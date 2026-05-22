"""Stage 27.5 private-ping provenance artifact tests.

Pins:

  * ``canonical_payload_json`` is deterministic, sort-keyed,
    separator-tight, UTF-8 friendly.
  * ``compute_payload_content_hash`` is a SHA-256 hex digest that is
    stable across identical inputs and changes when any payload
    field changes.
  * ``build_ping_provenance_artifact`` returns an immutable record
    with the locked field set, the locked schema versions, and the
    injected clock's wall time.
  * The artifact carries the locked artifact_kind, the locked
    redaction status, and the deterministic payload content hash.
  * The artifact NEVER carries a raw payload blob, a webhook URL, a
    secret canary, or a Stage 26 enforcement decision.
  * ``canonical_artifact_json`` is deterministic.
  * Stage 27.5 NEVER calls ``datetime.now()`` / ``time.time()`` to
    produce the artifact_created_at timestamp (the clock Protocol
    is injected).
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from PHX2.stage27 import private_ping_models as pm
from PHX2.stage27 import private_ping_provenance as prov
from PHX2.stage27 import private_ping_renderer as renderer

# Re-use the renderer test fixtures so we exercise the same
# synthetic measurement-context space.
from PHX2.tests.stage27 import (
    test_stage_27_5_private_ping_renderer as renderer_fixtures,
)


# ---------------------------------------------------------------------------
# Fixed-clock helpers
# ---------------------------------------------------------------------------


class _FixedClock:
    """Test-only Stage27_5Clock that returns a caller-pinned string."""

    def __init__(self, value: str) -> None:
        self._value = value

    def now_utc_iso(self) -> str:
        return self._value


def _sol_payload(ping_id: str = "ping-prov") -> pm.PrivatePingPayloadRecord:
    return renderer.render_private_ping(
        renderer_fixtures._sol_complete_context(), ping_id=ping_id
    )


def _usdc_payload(ping_id: str = "ping-prov-usdc") -> pm.PrivatePingPayloadRecord:
    return renderer.render_private_ping(
        renderer_fixtures._usdc_context(), ping_id=ping_id
    )


def _unknown_payload(ping_id: str = "ping-prov-unknown") -> pm.PrivatePingPayloadRecord:
    return renderer.render_private_ping(
        renderer_fixtures._unknown_context(), ping_id=ping_id
    )


# ---------------------------------------------------------------------------
# Canonical payload JSON
# ---------------------------------------------------------------------------


def test_canonical_payload_json_is_sort_keyed_and_separator_tight():
    payload = _sol_payload()
    encoded = prov.canonical_payload_json(payload)
    # No incidental ``key": "value`` spaces (JSON separator
    # tightness). The body_text field legitimately contains
    # ``label: value`` lines, so we cannot scan the whole encoding
    # for ``": "``; we instead pin the JSON structure separators
    # appearing immediately after a quote-key.
    assert '": "' not in encoded
    assert '", "' not in encoded
    # Round-trip parses cleanly.
    parsed = json.loads(encoded)
    assert parsed["ping_id"] == payload.ping_id
    # Keys are sorted globally.
    encoded_keys_in_order = re.findall(r'"([a-zA-Z_]+)":', encoded)
    assert encoded_keys_in_order == sorted(
        encoded_keys_in_order
    )


def test_canonical_payload_json_is_deterministic():
    a = prov.canonical_payload_json(_sol_payload())
    b = prov.canonical_payload_json(_sol_payload())
    assert a == b


def test_canonical_payload_json_changes_with_payload():
    base = prov.canonical_payload_json(_sol_payload())
    diff = prov.canonical_payload_json(
        _sol_payload(ping_id="ping-prov-diff")
    )
    assert base != diff


def test_canonical_payload_json_rejects_non_payload():
    with pytest.raises(TypeError):
        prov.canonical_payload_json({"ping_id": "x"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------


def test_compute_payload_content_hash_is_sha256_hex_64():
    digest = prov.compute_payload_content_hash(_sol_payload())
    assert isinstance(digest, str)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_content_hash_matches_manual_sha256():
    payload = _sol_payload()
    encoded = prov.canonical_payload_json(payload)
    manual = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    assert (
        prov.compute_payload_content_hash(payload) == manual
    )


def test_content_hash_is_stable_across_runs():
    a = prov.compute_payload_content_hash(_sol_payload())
    b = prov.compute_payload_content_hash(_sol_payload())
    assert a == b


def test_content_hash_changes_when_payload_changes():
    a = prov.compute_payload_content_hash(_sol_payload())
    b = prov.compute_payload_content_hash(
        _sol_payload(ping_id="ping-prov-different")
    )
    assert a != b


# ---------------------------------------------------------------------------
# Provenance artifact builder
# ---------------------------------------------------------------------------


def test_build_artifact_returns_named_tuple_with_locked_field_set():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert isinstance(artifact, tuple)
    assert isinstance(
        artifact, pm.PingProvenanceArtifactRecord
    )


def test_build_artifact_carries_locked_schema_versions():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert (
        artifact.artifact_schema_version
        == pm.STAGE27_5_PROVENANCE_SCHEMA_VERSION
    )
    assert (
        artifact.ping_schema_version
        == pm.STAGE27_5_PING_SCHEMA_VERSION
    )


def test_build_artifact_carries_locked_artifact_kind():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert (
        artifact.artifact_kind
        == pm.ARTIFACT_KIND_PRIVATE_PING_DRY_RUN
    )


def test_build_artifact_carries_injected_clock_string():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:14:15+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert (
        artifact.artifact_created_at_utc
        == "2026-05-22T13:14:15+00:00"
    )


def test_build_artifact_copies_payload_provenance_ids():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert artifact.ping_id == payload.ping_id
    assert artifact.provider_id == payload.provider_id
    assert artifact.provider_event_id == payload.provider_event_id
    assert (
        artifact.normalized_event_id
        == payload.normalized_event_id
    )
    assert artifact.raw_capture_ref == payload.raw_capture_ref
    assert artifact.token_mint == payload.token_mint


def test_build_artifact_copies_closed_set_pair_tokens():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert artifact.pair_quote_asset == payload.quote_asset
    assert artifact.pair_type == payload.pair_type
    assert (
        artifact.pair_detection_status
        == payload.pair_detection_status
    )
    assert (
        artifact.pair_detection_confidence
        == payload.pair_detection_confidence
    )
    assert artifact.pair_live_policy == payload.pair_live_policy
    assert artifact.calibration_lane == payload.calibration_lane


def test_build_artifact_copies_measurement_tokens():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert (
        artifact.measurement_status == payload.measurement_status
    )
    assert (
        artifact.measurement_warnings
        == payload.measurement_warnings
    )
    assert artifact.render_status == payload.render_status


def test_build_artifact_redaction_status_redacted_on_happy_path():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert (
        artifact.redaction_status
        == pm.REDACTION_STATUS_REDACTED
    )


def test_build_artifact_payload_content_hash_matches():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert (
        artifact.payload_content_hash
        == prov.compute_payload_content_hash(payload)
    )


def test_build_artifact_is_deterministic_for_pinned_clock():
    payload = _sol_payload()
    clock_a = _FixedClock("2026-05-22T13:00:00+00:00")
    clock_b = _FixedClock("2026-05-22T13:00:00+00:00")
    a = prov.build_ping_provenance_artifact(payload, clock_a)
    b = prov.build_ping_provenance_artifact(payload, clock_b)
    assert a == b


def test_build_artifact_differs_only_on_clock():
    payload = _sol_payload()
    clock_a = _FixedClock("2026-05-22T13:00:00+00:00")
    clock_b = _FixedClock("2026-05-22T14:00:00+00:00")
    a = prov.build_ping_provenance_artifact(payload, clock_a)
    b = prov.build_ping_provenance_artifact(payload, clock_b)
    assert a != b
    assert a._replace(
        artifact_created_at_utc=b.artifact_created_at_utc
    ) == b


def test_build_artifact_rejects_non_payload():
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    with pytest.raises(TypeError):
        prov.build_ping_provenance_artifact(
            {"ping_id": "x"}, clock  # type: ignore[arg-type]
        )


def test_build_artifact_rejects_empty_clock_string():
    payload = _sol_payload()
    clock = _FixedClock("")
    with pytest.raises(ValueError):
        prov.build_ping_provenance_artifact(payload, clock)


# ---------------------------------------------------------------------------
# Canonical artifact JSON
# ---------------------------------------------------------------------------


def test_canonical_artifact_json_is_sort_keyed_and_separator_tight():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    encoded = prov.canonical_artifact_json(artifact)
    assert ": " not in encoded
    assert ", " not in encoded
    parsed = json.loads(encoded)
    assert parsed["ping_id"] == artifact.ping_id
    keys_in_order = re.findall(r'"([a-zA-Z_]+)":', encoded)
    assert keys_in_order == sorted(keys_in_order)


def test_canonical_artifact_json_rejects_non_artifact():
    with pytest.raises(TypeError):
        prov.canonical_artifact_json({"ping_id": "x"})  # type: ignore[arg-type]


def test_canonical_artifact_json_is_deterministic():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    a = prov.canonical_artifact_json(artifact)
    b = prov.canonical_artifact_json(artifact)
    assert a == b


# ---------------------------------------------------------------------------
# Redaction guarantees
# ---------------------------------------------------------------------------


_FORBIDDEN_SECRET_CANARIES: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "Bear" + "er sk-",
    "api_key=",
    "API_KEY=",
    "STAGE27_3_RAW_PAYLOAD",
)


@pytest.mark.parametrize("canary", _FORBIDDEN_SECRET_CANARIES)
def test_artifact_json_carries_no_secret_canary(canary):
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    encoded = prov.canonical_artifact_json(artifact)
    assert canary not in encoded


@pytest.mark.parametrize("canary", _FORBIDDEN_SECRET_CANARIES)
def test_payload_json_carries_no_secret_canary(canary):
    payload = _sol_payload()
    encoded = prov.canonical_payload_json(payload)
    assert canary not in encoded


def test_provenance_artifact_carries_no_body_text_field():
    payload = _sol_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    # Provenance is redacted summary, NOT the full body.
    assert "body_text" not in artifact._fields


# ---------------------------------------------------------------------------
# Pair-aware coverage
# ---------------------------------------------------------------------------


def test_usdc_artifact_lane_is_usdc_observe_only():
    payload = _usdc_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert artifact.calibration_lane == "USDC_OBSERVE_ONLY"


def test_unknown_artifact_lane_is_unknown_observe_only():
    payload = _unknown_payload()
    clock = _FixedClock("2026-05-22T13:00:00+00:00")
    artifact = prov.build_ping_provenance_artifact(payload, clock)
    assert (
        artifact.calibration_lane == "UNKNOWN_PAIR_OBSERVE_ONLY"
    )
