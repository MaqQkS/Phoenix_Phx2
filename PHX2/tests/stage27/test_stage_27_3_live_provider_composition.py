"""Stage 27.3 provider-ingest composition pipeline tests.

Every test uses obvious synthetic / fake records. No live network
call is ever made and no real provider payload blob is ever
passed into the composer.

Pins (full coverage of the Stage 27.3 composition hard requirements):

  * Known SOL quote mint -> Stage 27.2 verdict ``SOL`` /
    ``CONFIRMED`` / ``LIVE_ALLOWED`` / ``EXISTING_SOL_LANE`` ->
    Stage 27.3 ``COMPOSED`` / ``OK``.
  * Known USDC quote mint -> Stage 27.2 verdict ``USDC`` /
    ``CONFIRMED`` / ``DRY_RUN_ONLY`` / ``USDC_OBSERVE_ONLY`` ->
    Stage 27.3 ``COMPOSED`` / ``OK`` (NOT the SOL lane).
  * Missing quote mint + no other evidence -> Stage 27.2
    ``UNRESOLVED`` -> Stage 27.3 ``CLASSIFIED_UNKNOWN`` /
    ``PAIR_UNRESOLVED`` with ``LIVE_SUPPRESS_UNKNOWN``.
  * Quote-mint SOL + provider says USDC -> Stage 27.2 ``DISAGREE``
    -> Stage 27.3 ``CLASSIFIED_DISAGREE`` / ``PAIR_DISAGREE``
    with ``LIVE_SUPPRESS_DISAGREE``.
  * Unsupported event kind -> ``SKIPPED_UNSUPPORTED_EVENT`` /
    ``UNSUPPORTED_EVENT_KIND``; no classifier run.
  * Missing token mint -> ``SKIPPED_MISSING_TOKEN`` /
    ``MISSING_TOKEN_MINT``; no classifier run.
  * UNKNOWN / DISAGREE / USDC verdicts NEVER map into the SOL
    lane on the Stage 27.3 output.
  * Provider provenance is preserved on the output record.
  * ``raw_capture_ref`` is preserved on the output record.
  * The composer reuses Stage 27.2 ``classify_pair`` (verified via
    monkeypatch -- if the composer duplicated logic, the test
    would never observe the monkeypatched stub).
  * Output records are immutable.
  * Output records carry the locked ``schema_version``.
  * Structurally invalid input raises a typed error.
  * The convenience composer (``compose_provider_ingest_from_normalized_event``)
    round-trips a fake normalized event through the full pipeline.
"""

from __future__ import annotations

import pytest

from PHX2.stage27 import live_provider_composition as comp
from PHX2.stage27 import pair_detection_constants as pc
from PHX2.stage27 import pair_detection_models as pm
from PHX2.stage27 import provider_ingest_contracts as errors
from PHX2.stage27 import provider_ingest_models as m


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeNormalizedEvent:
    """Stage 27.3 test stand-in for the Stage 21.2 normalized event."""

    def __init__(
        self,
        *,
        event_id: str = "evt_fake_aaa",
        provider_event_id: str = "prov_fake_aaa",
        provider_name: str = "stage21_fake_provider",
        mint: str = "mint-AAA",
        event_type: str = "fake_swap",
        observed_at_utc: str = "2026-05-22T00:00:00Z",
        raw_event_hash: str = "raw_hash_aaa",
    ) -> None:
        self.event_id = event_id
        self.provider_event_id = provider_event_id
        self.provider_name = provider_name
        self.mint = mint
        self.event_type = event_type
        self.observed_at_utc = observed_at_utc
        self.raw_event_hash = raw_event_hash


def _ingest_input(
    *,
    event_kind: str = m.EVENT_KIND_SWAP,
    token_mint: str = "mint-AAA",
    quote_mint: str = None,
    **kwargs,
) -> m.ProviderIngestInputRecord:
    return m.ProviderIngestInputRecord(
        provider_id="stage21_fake_provider",
        provider_event_id="prov-1",
        normalized_event_id="evt_fake_aaa",
        event_kind=event_kind,
        observed_at_utc="2026-05-22T00:00:00Z",
        token_mint=token_mint,
        quote_mint=quote_mint,
        raw_capture_ref="raw_hash_aaa",
        source_summary="fake-fixture",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Known SOL / USDC compose to COMPOSED
# ---------------------------------------------------------------------------


def test_known_sol_quote_mint_composes_as_composed_ok_sol_lane():
    record = _ingest_input(
        quote_mint=pc.KNOWN_WRAPPED_SOL_MINT,
    )
    out = comp.compose_provider_ingest_event(record)
    assert out.composition_status == m.COMPOSITION_STATUS_COMPOSED
    assert out.composition_reason == m.COMPOSITION_REASON_OK
    assert out.pair_quote_asset == pc.QUOTE_ASSET_SOL
    assert out.pair_pair_type == pc.PAIR_TYPE_PUMP_SOL
    assert (
        out.pair_bonding_curve_version
        == pc.BONDING_CURVE_VERSION_SOL_LEGACY
    )
    assert (
        out.pair_detection_status
        == pc.PAIR_DETECTION_STATUS_CONFIRMED
    )
    assert out.pair_live_policy == pc.LIVE_POLICY_LIVE_ALLOWED
    assert (
        out.pair_calibration_lane
        == pc.CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_known_usdc_quote_mint_composes_as_composed_ok_observe_only():
    record = _ingest_input(
        quote_mint=pc.KNOWN_USDC_MINT,
    )
    out = comp.compose_provider_ingest_event(record)
    assert out.composition_status == m.COMPOSITION_STATUS_COMPOSED
    assert out.composition_reason == m.COMPOSITION_REASON_OK
    assert out.pair_quote_asset == pc.QUOTE_ASSET_USDC
    assert out.pair_pair_type == pc.PAIR_TYPE_PUMP_USDC
    assert (
        out.pair_bonding_curve_version
        == pc.BONDING_CURVE_VERSION_USDC_FIXED
    )
    assert (
        out.pair_detection_status
        == pc.PAIR_DETECTION_STATUS_CONFIRMED
    )
    assert out.pair_live_policy == pc.LIVE_POLICY_DRY_RUN_ONLY
    assert (
        out.pair_calibration_lane
        == pc.CALIBRATION_LANE_USDC_OBSERVE_ONLY
    )
    # USDC MUST NOT map into the SOL lane.
    assert (
        out.pair_calibration_lane
        != pc.CALIBRATION_LANE_EXISTING_SOL_LANE
    )


# ---------------------------------------------------------------------------
# UNKNOWN / DISAGREE compose to classifier-aware statuses
# ---------------------------------------------------------------------------


def test_missing_quote_mint_composes_as_classified_unknown_suppress():
    record = _ingest_input(quote_mint=None)
    out = comp.compose_provider_ingest_event(record)
    assert (
        out.composition_status
        == m.COMPOSITION_STATUS_CLASSIFIED_UNKNOWN
    )
    assert (
        out.composition_reason
        == m.COMPOSITION_REASON_PAIR_UNRESOLVED
    )
    assert out.pair_quote_asset == pc.QUOTE_ASSET_UNKNOWN
    assert (
        out.pair_detection_status
        == pc.PAIR_DETECTION_STATUS_UNRESOLVED
    )
    assert (
        out.pair_live_policy
        == pc.LIVE_POLICY_LIVE_SUPPRESS_UNKNOWN
    )
    assert (
        out.pair_calibration_lane
        == pc.CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY
    )
    # UNKNOWN MUST NOT map into the SOL lane.
    assert (
        out.pair_calibration_lane
        != pc.CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_quote_mint_sol_with_provider_usdc_composes_as_disagree_suppress():
    record = _ingest_input(
        quote_mint=pc.KNOWN_WRAPPED_SOL_MINT,
        provider_quote_asset_hint=pc.QUOTE_ASSET_USDC,
        provider_pair_type_hint=pc.PAIR_TYPE_PUMP_USDC,
    )
    out = comp.compose_provider_ingest_event(record)
    assert (
        out.composition_status
        == m.COMPOSITION_STATUS_CLASSIFIED_DISAGREE
    )
    assert (
        out.composition_reason
        == m.COMPOSITION_REASON_PAIR_DISAGREE
    )
    assert (
        out.pair_detection_status
        == pc.PAIR_DETECTION_STATUS_DISAGREE
    )
    assert (
        out.pair_live_policy
        == pc.LIVE_POLICY_LIVE_SUPPRESS_DISAGREE
    )
    assert (
        out.pair_calibration_lane
        == pc.CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY
    )
    # DISAGREE MUST NOT map into the SOL lane.
    assert (
        out.pair_calibration_lane
        != pc.CALIBRATION_LANE_EXISTING_SOL_LANE
    )


def test_quote_mint_usdc_with_provider_sol_composes_as_disagree_suppress():
    record = _ingest_input(
        quote_mint=pc.KNOWN_USDC_MINT,
        provider_quote_asset_hint=pc.QUOTE_ASSET_SOL,
        provider_pair_type_hint=pc.PAIR_TYPE_PUMP_SOL,
    )
    out = comp.compose_provider_ingest_event(record)
    assert (
        out.composition_status
        == m.COMPOSITION_STATUS_CLASSIFIED_DISAGREE
    )
    assert (
        out.pair_calibration_lane
        == pc.CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY
    )


# ---------------------------------------------------------------------------
# Skip statuses (no classifier work)
# ---------------------------------------------------------------------------


def test_unsupported_event_kind_skipped_without_classifier_call(
    monkeypatch,
):
    called = {"count": 0}

    def _sentinel_classify_pair(pair_in):
        called["count"] += 1
        raise AssertionError(
            "classify_pair must NOT run for an unsupported event kind"
        )

    monkeypatch.setattr(
        comp, "classify_pair", _sentinel_classify_pair
    )

    record = _ingest_input(
        event_kind=m.EVENT_KIND_UNKNOWN,
        quote_mint=pc.KNOWN_WRAPPED_SOL_MINT,
    )
    out = comp.compose_provider_ingest_event(record)
    assert (
        out.composition_status
        == m.COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT
    )
    assert (
        out.composition_reason
        == m.COMPOSITION_REASON_UNSUPPORTED_EVENT_KIND
    )
    assert out.pair_quote_asset == pc.QUOTE_ASSET_UNKNOWN
    assert (
        out.pair_calibration_lane
        == pc.CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY
    )
    assert called["count"] == 0


def test_event_kind_outside_closed_set_skipped(monkeypatch):
    def _sentinel_classify_pair(pair_in):
        raise AssertionError("classify_pair must NOT run")

    monkeypatch.setattr(
        comp, "classify_pair", _sentinel_classify_pair
    )

    # Bypass the closed-set guard via the NamedTuple constructor
    # to verify the composer's defensive 'not in SUPPORTED' branch.
    record = m.ProviderIngestInputRecord(
        provider_id="x",
        normalized_event_id="evt",
        event_kind="NOT_A_KIND",
        token_mint="mint-AAA",
        quote_mint=pc.KNOWN_WRAPPED_SOL_MINT,
    )
    out = comp.compose_provider_ingest_event(record)
    assert (
        out.composition_status
        == m.COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT
    )


def test_missing_token_mint_skipped_without_classifier_call(
    monkeypatch,
):
    def _sentinel_classify_pair(pair_in):
        raise AssertionError(
            "classify_pair must NOT run when token_mint is missing"
        )

    monkeypatch.setattr(
        comp, "classify_pair", _sentinel_classify_pair
    )

    record = _ingest_input(token_mint=None)
    out = comp.compose_provider_ingest_event(record)
    assert (
        out.composition_status
        == m.COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN
    )
    assert (
        out.composition_reason
        == m.COMPOSITION_REASON_MISSING_TOKEN_MINT
    )
    assert (
        out.pair_detection_status
        == pc.PAIR_DETECTION_STATUS_UNRESOLVED
    )


def test_empty_token_mint_string_also_skipped():
    record = _ingest_input(token_mint="")
    out = comp.compose_provider_ingest_event(record)
    assert (
        out.composition_status
        == m.COMPOSITION_STATUS_SKIPPED_MISSING_TOKEN
    )


# ---------------------------------------------------------------------------
# Provenance / capture_ref preservation
# ---------------------------------------------------------------------------


def test_output_preserves_provider_provenance():
    record = _ingest_input(quote_mint=pc.KNOWN_WRAPPED_SOL_MINT)
    out = comp.compose_provider_ingest_event(record)
    assert out.provider_id == record.provider_id
    assert out.provider_event_id == record.provider_event_id
    assert (
        out.normalized_event_id == record.normalized_event_id
    )
    assert out.observed_at_utc == record.observed_at_utc
    assert out.token_mint == record.token_mint
    assert out.quote_mint == record.quote_mint


def test_output_preserves_raw_capture_ref_and_source_summary():
    record = _ingest_input(
        quote_mint=pc.KNOWN_WRAPPED_SOL_MINT,
    )
    out = comp.compose_provider_ingest_event(record)
    assert out.raw_capture_ref == "raw_hash_aaa"
    assert out.source_summary == "fake-fixture"


def test_output_preserves_provenance_when_skipped():
    record = _ingest_input(
        event_kind=m.EVENT_KIND_UNKNOWN,
    )
    out = comp.compose_provider_ingest_event(record)
    assert out.provider_id == "stage21_fake_provider"
    assert out.raw_capture_ref == "raw_hash_aaa"
    assert out.source_summary == "fake-fixture"


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------


def test_output_carries_locked_schema_version():
    record = _ingest_input(quote_mint=pc.KNOWN_WRAPPED_SOL_MINT)
    out = comp.compose_provider_ingest_event(record)
    assert out.schema_version == m.STAGE27_3_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Output immutability
# ---------------------------------------------------------------------------


def test_output_record_is_immutable():
    record = _ingest_input(quote_mint=pc.KNOWN_WRAPPED_SOL_MINT)
    out = comp.compose_provider_ingest_event(record)
    with pytest.raises(AttributeError):
        out.composition_status = "spoof"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# UNKNOWN / DISAGREE / USDC never reach the SOL lane (multi-axis pin)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ingest_args,expected_lane",
    (
        (
            {"quote_mint": pc.KNOWN_USDC_MINT},
            pc.CALIBRATION_LANE_USDC_OBSERVE_ONLY,
        ),
        (
            {"quote_mint": None},
            pc.CALIBRATION_LANE_UNKNOWN_PAIR_OBSERVE_ONLY,
        ),
        (
            {
                "quote_mint": pc.KNOWN_WRAPPED_SOL_MINT,
                "provider_quote_asset_hint": pc.QUOTE_ASSET_USDC,
                "provider_pair_type_hint": pc.PAIR_TYPE_PUMP_USDC,
            },
            pc.CALIBRATION_LANE_DISAGREE_PAIR_OBSERVE_ONLY,
        ),
    ),
)
def test_non_sol_classifications_never_route_to_sol_lane(
    ingest_args, expected_lane
):
    record = _ingest_input(**ingest_args)
    out = comp.compose_provider_ingest_event(record)
    assert out.pair_calibration_lane == expected_lane
    assert (
        out.pair_calibration_lane
        != pc.CALIBRATION_LANE_EXISTING_SOL_LANE
    )


# ---------------------------------------------------------------------------
# Classifier reuse: monkeypatch-stubbed verdict propagates intact
# ---------------------------------------------------------------------------


def test_composer_uses_stage_27_2_classify_pair_not_duplicated_logic(
    monkeypatch,
):
    """If the composer duplicated pair classification logic, the
    monkeypatched stub below would never observe the call. The
    test stubs classify_pair to a sentinel verdict and asserts
    the Stage 27.3 output mirrors that verdict.
    """
    called = {"count": 0}
    sentinel_verdict = pm.PairDetectionOutputRecord(
        quote_asset=pc.QUOTE_ASSET_SOL,
        quote_mint=pc.KNOWN_WRAPPED_SOL_MINT,
        pair_type=pc.PAIR_TYPE_PUMP_SOL,
        bonding_curve_version=pc.BONDING_CURVE_VERSION_SOL_LEGACY,
        pair_detection_status=(
            pc.PAIR_DETECTION_STATUS_PROVIDER_ONLY
        ),
        pair_detection_confidence=(
            pc.PAIR_DETECTION_CONFIDENCE_MEDIUM
        ),
        pair_detection_reason=(
            pc.PAIR_DETECTION_REASON_PROVIDER_ONLY_EVIDENCE
        ),
        evidence_count=1,
        disagreement_count=0,
        live_policy=pc.LIVE_POLICY_LIVE_ALLOWED,
        calibration_lane=pc.CALIBRATION_LANE_EXISTING_SOL_LANE,
    )

    def _stub_classify_pair(pair_in):
        called["count"] += 1
        return sentinel_verdict

    monkeypatch.setattr(
        comp, "classify_pair", _stub_classify_pair
    )

    record = _ingest_input(
        quote_mint=pc.KNOWN_WRAPPED_SOL_MINT
    )
    out = comp.compose_provider_ingest_event(record)
    assert called["count"] == 1
    assert out.composition_status == m.COMPOSITION_STATUS_COMPOSED
    assert (
        out.pair_detection_status
        == pc.PAIR_DETECTION_STATUS_PROVIDER_ONLY
    )
    assert (
        out.pair_detection_confidence
        == pc.PAIR_DETECTION_CONFIDENCE_MEDIUM
    )
    assert (
        out.pair_detection_reason
        == pc.PAIR_DETECTION_REASON_PROVIDER_ONLY_EVIDENCE
    )


# ---------------------------------------------------------------------------
# Structural shape rejection
# ---------------------------------------------------------------------------


def test_compose_rejects_non_ingest_input_record():
    with pytest.raises(
        errors.Stage27ProviderIngestInvalidEventError
    ):
        comp.compose_provider_ingest_event({"x": 1})  # type: ignore[arg-type]


def test_compose_rejects_none_input():
    with pytest.raises(
        errors.Stage27ProviderIngestInvalidEventError
    ):
        comp.compose_provider_ingest_event(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Convenience composer: full pipeline from fake normalized event
# ---------------------------------------------------------------------------


def test_compose_from_normalized_event_round_trips_sol():
    event = FakeNormalizedEvent(event_type="fake_swap")
    out = comp.compose_provider_ingest_from_normalized_event(
        event,
        provider_id="stage21_fake_provider",
        quote_mint=pc.KNOWN_WRAPPED_SOL_MINT,
    )
    assert out.composition_status == m.COMPOSITION_STATUS_COMPOSED
    assert out.pair_quote_asset == pc.QUOTE_ASSET_SOL
    assert (
        out.pair_calibration_lane
        == pc.CALIBRATION_LANE_EXISTING_SOL_LANE
    )
    assert out.raw_capture_ref == "raw_hash_aaa"
    assert out.provider_id == "stage21_fake_provider"


def test_compose_from_normalized_event_skips_unsupported_event_type():
    event = FakeNormalizedEvent(event_type="fake_transfer")
    out = comp.compose_provider_ingest_from_normalized_event(
        event, quote_mint=pc.KNOWN_WRAPPED_SOL_MINT
    )
    assert (
        out.composition_status
        == m.COMPOSITION_STATUS_SKIPPED_UNSUPPORTED_EVENT
    )
    assert (
        out.composition_reason
        == m.COMPOSITION_REASON_UNSUPPORTED_EVENT_KIND
    )


def test_compose_from_normalized_event_rejects_raw_payload_extra():
    event = FakeNormalizedEvent()
    with pytest.raises(
        errors.Stage27ProviderIngestRawPayloadRejectedError
    ):
        comp.compose_provider_ingest_from_normalized_event(
            event,
            extra_fields={"raw_payload": "would-be-blob"},
        )


def test_compose_from_normalized_event_rejects_none_event():
    with pytest.raises(
        errors.Stage27ProviderIngestInvalidEventError
    ):
        comp.compose_provider_ingest_from_normalized_event(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Deterministic / pure
# ---------------------------------------------------------------------------


def test_compose_is_deterministic_for_same_input():
    record_a = _ingest_input(quote_mint=pc.KNOWN_WRAPPED_SOL_MINT)
    record_b = _ingest_input(quote_mint=pc.KNOWN_WRAPPED_SOL_MINT)
    assert (
        comp.compose_provider_ingest_event(record_a)
        == comp.compose_provider_ingest_event(record_b)
    )
