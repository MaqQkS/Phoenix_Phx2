"""Stage 27.3 provider-event adapter tests.

Every test uses obvious synthetic / fake records. No live network
call is ever made and no real provider payload blob is ever passed
into the adapter.

Pins (full coverage of the Stage 27.3 adapter hard requirements):

  * ``classify_event_kind`` maps locked event_type strings into the
    Stage 27.3 closed set; everything else resolves to
    ``UNKNOWN_EVENT_KIND``.
  * The adapter rejects ``None`` / dict / scalar inputs as
    structurally invalid.
  * The adapter rejects an ``extra_fields`` mapping carrying a
    raw-payload-class key.
  * The adapter never copies an upstream raw-payload blob through;
    it uses only ``raw_event_hash`` as a stable ``raw_capture_ref``.
  * The adapter preserves provider provenance (``provider_id`` /
    ``provider_event_id`` / ``normalized_event_id``).
  * The adapter preserves the upstream ``raw_event_hash`` as the
    ``raw_capture_ref`` of the ingest record.
  * ``adapt_ingest_input_to_pair_input`` projects only the safe
    pair-detection-relevant subset.
  * Missing quote-mint does NOT default to SOL.
  * Provider hints flow through but never override an explicit
    pool-quote-mint.
"""

from __future__ import annotations

from typing import Optional

import pytest

from PHX2.stage27 import pair_detection_constants as pc
from PHX2.stage27 import pair_detection_models as pm
from PHX2.stage27 import provider_event_adapter as adapter
from PHX2.stage27 import provider_ingest_contracts as errors
from PHX2.stage27 import provider_ingest_models as m


# ---------------------------------------------------------------------------
# Fake normalized event fixture (Stage 27.3 owns its own; we do NOT
# import Stage 21).
# ---------------------------------------------------------------------------


class FakeNormalizedEvent:
    """Plain-Python stand-in for the Stage 21.2 NormalizedLiveEvent.

    Mirrors only the structural Protocol Stage 27.3 expects:
    ``event_id``, ``provider_event_id``, ``provider_name``,
    ``mint``, ``event_type``, ``observed_at_utc``,
    ``raw_event_hash``. Stage 27.3 tests use this stand-in so the
    Stage 27 boundary scans (which forbid Stage 21 imports from
    Stage 27 production modules) remain trivially intact.
    """

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


# ---------------------------------------------------------------------------
# classify_event_kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    (
        ("swap", "SWAP"),
        ("fake_swap", "SWAP"),
        ("trade", "SWAP"),
        ("migration", "MIGRATION"),
        ("fake_migration", "MIGRATION"),
        ("pool_migration", "MIGRATION"),
        ("mint", "MINT"),
        ("fake_mint", "MINT"),
        ("token_mint_created", "MINT"),
    ),
)
def test_classify_event_kind_locked_mapping(raw, expected):
    assert adapter.classify_event_kind(raw) == expected


@pytest.mark.parametrize(
    "raw",
    (
        None,
        "",
        "fake_transfer",
        "unknown_event",
        "BOGUS",
        123,
        ["fake_swap"],
    ),
)
def test_classify_event_kind_unknown_falls_back(raw):
    assert (
        adapter.classify_event_kind(raw)
        == m.EVENT_KIND_UNKNOWN
    )


def test_classify_event_kind_normalizes_whitespace_and_case():
    assert adapter.classify_event_kind("  Fake_Swap  ") == "SWAP"
    assert (
        adapter.classify_event_kind("MIGRATION")
        == "MIGRATION"
    )


# ---------------------------------------------------------------------------
# Structural shape validation
# ---------------------------------------------------------------------------


def test_adapter_rejects_none_event():
    with pytest.raises(
        errors.Stage27ProviderIngestInvalidEventError
    ):
        adapter.adapt_normalized_event_to_ingest_input(None)  # type: ignore[arg-type]


def test_adapter_rejects_dict_event():
    with pytest.raises(
        errors.Stage27ProviderIngestInvalidEventError
    ):
        adapter.adapt_normalized_event_to_ingest_input({  # type: ignore[arg-type]
            "event_id": "evt_x",
            "provider_event_id": "p",
            "provider_name": "n",
            "mint": "m",
            "event_type": "fake_swap",
            "observed_at_utc": "2026-05-22T00:00:00Z",
            "raw_event_hash": "h",
        })


@pytest.mark.parametrize(
    "candidate", (42, "fake_swap", [1, 2], (1, 2), True, 3.14)
)
def test_adapter_rejects_scalar_or_sequence(candidate):
    with pytest.raises(
        errors.Stage27ProviderIngestInvalidEventError
    ):
        adapter.adapt_normalized_event_to_ingest_input(candidate)  # type: ignore[arg-type]


def test_adapter_rejects_object_missing_required_field():
    class _Incomplete:
        event_id = "x"
        provider_event_id = "y"
        provider_name = "z"
        mint = "m"
        event_type = "fake_swap"
        # ``observed_at_utc`` and ``raw_event_hash`` are missing.

    with pytest.raises(
        errors.Stage27ProviderIngestInvalidEventError
    ):
        adapter.adapt_normalized_event_to_ingest_input(_Incomplete())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Raw-payload-class field rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
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
def test_adapter_rejects_extra_fields_with_forbidden_key(key):
    event = FakeNormalizedEvent()
    with pytest.raises(
        errors.Stage27ProviderIngestRawPayloadRejectedError
    ):
        adapter.adapt_normalized_event_to_ingest_input(
            event, extra_fields={key: "irrelevant"}
        )


def test_adapter_accepts_extra_fields_with_safe_keys():
    event = FakeNormalizedEvent()
    record = adapter.adapt_normalized_event_to_ingest_input(
        event,
        extra_fields={"trace_id": "t-1", "ingest_lane": "fake"},
    )
    assert isinstance(record, m.ProviderIngestInputRecord)


def test_adapter_rejects_non_mapping_extra_fields():
    event = FakeNormalizedEvent()
    with pytest.raises(
        errors.Stage27ProviderIngestInvalidEventError
    ):
        adapter.adapt_normalized_event_to_ingest_input(
            event, extra_fields=["not", "a", "mapping"]  # type: ignore[arg-type]
        )


def test_reject_raw_payload_fields_accepts_none_extra_fields():
    # Sanity: the public helper short-circuits on ``None``.
    adapter.reject_raw_payload_fields(None)


# ---------------------------------------------------------------------------
# Provenance / raw_capture_ref preservation
# ---------------------------------------------------------------------------


def test_adapter_preserves_provider_event_normalized_ids_and_capture_ref():
    event = FakeNormalizedEvent(
        event_id="evt_fake_xyz",
        provider_event_id="prov_fake_xyz",
        provider_name="stage21_fake_provider",
        raw_event_hash="raw_hash_xyz",
    )
    record = adapter.adapt_normalized_event_to_ingest_input(
        event, provider_id="stage21_fake_provider"
    )
    assert record.provider_id == "stage21_fake_provider"
    assert record.provider_event_id == "prov_fake_xyz"
    assert record.normalized_event_id == "evt_fake_xyz"
    assert record.raw_capture_ref == "raw_hash_xyz"
    # No raw payload field on the input record (defensive check).
    assert "raw_payload" not in record._fields


def test_adapter_falls_back_to_provider_name_when_provider_id_absent():
    event = FakeNormalizedEvent(
        provider_name="stage21_fake_provider"
    )
    record = adapter.adapt_normalized_event_to_ingest_input(event)
    assert record.provider_id == "stage21_fake_provider"


def test_adapter_prefers_explicit_provider_id_over_provider_name():
    event = FakeNormalizedEvent(
        provider_name="stage21_fake_provider"
    )
    record = adapter.adapt_normalized_event_to_ingest_input(
        event, provider_id="phx2_test_provider_override"
    )
    assert record.provider_id == "phx2_test_provider_override"


# ---------------------------------------------------------------------------
# Event-kind projection
# ---------------------------------------------------------------------------


def test_adapter_projects_known_event_type():
    event = FakeNormalizedEvent(event_type="fake_swap")
    record = adapter.adapt_normalized_event_to_ingest_input(event)
    assert record.event_kind == m.EVENT_KIND_SWAP


def test_adapter_projects_unknown_event_type_as_unknown_kind():
    event = FakeNormalizedEvent(event_type="fake_transfer")
    record = adapter.adapt_normalized_event_to_ingest_input(event)
    assert record.event_kind == m.EVENT_KIND_UNKNOWN


def test_adapter_token_mint_is_copied_from_event_mint():
    event = FakeNormalizedEvent(mint="mint-AAA")
    record = adapter.adapt_normalized_event_to_ingest_input(event)
    assert record.token_mint == "mint-AAA"


# ---------------------------------------------------------------------------
# Quote-mint discipline: never defaults to SOL
# ---------------------------------------------------------------------------


def test_adapter_does_not_default_missing_quote_mint_to_sol():
    event = FakeNormalizedEvent()
    record = adapter.adapt_normalized_event_to_ingest_input(event)
    assert record.quote_mint is None


def test_adapter_passes_quote_mint_through_when_provided():
    event = FakeNormalizedEvent()
    record = adapter.adapt_normalized_event_to_ingest_input(
        event, quote_mint=pc.KNOWN_WRAPPED_SOL_MINT
    )
    assert record.quote_mint == pc.KNOWN_WRAPPED_SOL_MINT


def test_adapter_passes_unknown_quote_mint_through_verbatim():
    event = FakeNormalizedEvent()
    record = adapter.adapt_normalized_event_to_ingest_input(
        event, quote_mint="UNKNOWN_MINT_STRING"
    )
    assert record.quote_mint == "UNKNOWN_MINT_STRING"


# ---------------------------------------------------------------------------
# Hint propagation
# ---------------------------------------------------------------------------


def test_adapter_propagates_pair_hints_to_record():
    event = FakeNormalizedEvent()
    record = adapter.adapt_normalized_event_to_ingest_input(
        event,
        pool_account="pool-acct",
        pool_program_id="pool-prog",
        base_mint="base-mint",
        quote_mint=pc.KNOWN_USDC_MINT,
        bonding_curve_program_id="bc-prog",
        bonding_curve_version_hint=(
            pc.BONDING_CURVE_VERSION_USDC_FIXED
        ),
        migration_event_quote_asset_hint=pc.QUOTE_ASSET_USDC,
        provider_quote_asset_hint=pc.QUOTE_ASSET_USDC,
        provider_pair_type_hint=pc.PAIR_TYPE_PUMP_USDC,
        provider_bonding_curve_version_hint=(
            pc.BONDING_CURVE_VERSION_USDC_FIXED
        ),
        source_summary="test-provenance",
    )
    assert record.pool_account == "pool-acct"
    assert record.pool_program_id == "pool-prog"
    assert record.base_mint == "base-mint"
    assert record.quote_mint == pc.KNOWN_USDC_MINT
    assert record.bonding_curve_program_id == "bc-prog"
    assert (
        record.bonding_curve_version_hint
        == pc.BONDING_CURVE_VERSION_USDC_FIXED
    )
    assert (
        record.migration_event_quote_asset_hint
        == pc.QUOTE_ASSET_USDC
    )
    assert (
        record.provider_quote_asset_hint == pc.QUOTE_ASSET_USDC
    )
    assert (
        record.provider_pair_type_hint == pc.PAIR_TYPE_PUMP_USDC
    )
    assert (
        record.provider_bonding_curve_version_hint
        == pc.BONDING_CURVE_VERSION_USDC_FIXED
    )
    assert record.source_summary == "test-provenance"


# ---------------------------------------------------------------------------
# Stage 27.3 -> Stage 27.2 input projection
# ---------------------------------------------------------------------------


def test_adapt_ingest_input_to_pair_input_returns_pair_record():
    record = m.ProviderIngestInputRecord(
        provider_id="stage21_fake_provider",
        provider_event_id="prov-1",
        normalized_event_id="evt_aaa",
        event_kind=m.EVENT_KIND_SWAP,
        observed_at_utc="2026-05-22T00:00:00Z",
        token_mint="mint-AAA",
        quote_mint=pc.KNOWN_WRAPPED_SOL_MINT,
        raw_capture_ref="raw_hash_aaa",
    )
    pair_in = adapter.adapt_ingest_input_to_pair_input(record)
    assert isinstance(pair_in, pm.PairDetectionInputRecord)
    assert pair_in.event_id == "evt_aaa"
    assert pair_in.token_mint == "mint-AAA"
    assert pair_in.quote_mint == pc.KNOWN_WRAPPED_SOL_MINT
    assert pair_in.source_payload_reference == "raw_hash_aaa"
    # The pair-detection input has no Stage 27.3 provenance fields.
    assert "provider_id" not in pair_in._fields
    assert "raw_capture_ref" not in pair_in._fields


def test_adapt_ingest_input_to_pair_input_rejects_wrong_type():
    with pytest.raises(
        errors.Stage27ProviderIngestInvalidEventError
    ):
        adapter.adapt_ingest_input_to_pair_input({"x": 1})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Pure / deterministic
# ---------------------------------------------------------------------------


def test_adapter_is_deterministic():
    event_a = FakeNormalizedEvent()
    event_b = FakeNormalizedEvent()
    record_a = adapter.adapt_normalized_event_to_ingest_input(
        event_a
    )
    record_b = adapter.adapt_normalized_event_to_ingest_input(
        event_b
    )
    assert record_a == record_b
