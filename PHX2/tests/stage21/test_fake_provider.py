"""Stage 21.2 fake provider tests."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from PHX2.stage21.fake_provider import (
    STAGE21_FAKE_ONLY_MARKER,
    Stage21FakeEvent,
    Stage21FakeEventSeed,
    Stage21FakeProvider,
)
from PHX2.stage21.errors import Stage21TelemetryError
from PHX2.stage21.ping_payloads import (
    STAGE21_FAKE_CHAIN_NAME,
    STAGE21_FAKE_PROVIDER_NAME,
    STAGE21_FAKE_SOURCE_KIND,
)


def _seed(
    *,
    mint: str = "FAKE_MINT_AAAA",
    event_type: str = "fake_swap",
    observed_at_utc: str = "2026-05-17T12:00:00Z",
    slot: int = 100,
    raw_payload: dict[str, object] | None = None,
) -> Stage21FakeEventSeed:
    return Stage21FakeEventSeed(
        mint=mint,
        event_type=event_type,
        observed_at_utc=observed_at_utc,
        slot=slot,
        raw_payload=raw_payload or {"fake_amount": 1000, "fake_decimals": 6},
    )


def test_fake_provider_class_exposes_fake_only_marker():
    assert Stage21FakeProvider.IS_FAKE_ONLY is True
    assert STAGE21_FAKE_ONLY_MARKER is True


def test_fake_provider_emits_zero_events_for_empty_seeds():
    provider = Stage21FakeProvider([])
    assert provider.fetch_events() == ()


def test_fake_provider_emits_one_event_per_seed_in_order():
    seeds = [
        _seed(mint="FAKE_MINT_A", slot=1),
        _seed(mint="FAKE_MINT_B", slot=2),
        _seed(mint="FAKE_MINT_C", slot=3),
    ]
    events = Stage21FakeProvider(seeds).fetch_events()
    assert len(events) == 3
    assert [e.mint for e in events] == ["FAKE_MINT_A", "FAKE_MINT_B", "FAKE_MINT_C"]


def test_fake_provider_assigns_stable_provider_name_and_chain():
    seeds = [_seed()]
    events = Stage21FakeProvider(seeds).fetch_events()
    e = events[0]
    assert e.provider_name == STAGE21_FAKE_PROVIDER_NAME
    assert e.chain == STAGE21_FAKE_CHAIN_NAME
    assert e.source_kind == STAGE21_FAKE_SOURCE_KIND


def test_fake_provider_is_deterministic_for_identical_seeds():
    seeds = [_seed(mint="FAKE_MINT_X", slot=5)]
    a = Stage21FakeProvider(seeds).fetch_events()
    b = Stage21FakeProvider(seeds).fetch_events()
    assert a == b
    assert a[0].provider_event_id == b[0].provider_event_id
    assert a[0].signature == b[0].signature


def test_fake_provider_distinct_seeds_produce_distinct_event_ids():
    seeds = [
        _seed(mint="FAKE_MINT_A", slot=1),
        _seed(mint="FAKE_MINT_B", slot=2),
    ]
    events = Stage21FakeProvider(seeds).fetch_events()
    assert events[0].provider_event_id != events[1].provider_event_id
    assert events[0].signature != events[1].signature


def test_fake_provider_max_events_truncates_prefix():
    seeds = [
        _seed(mint=f"FAKE_MINT_{i}", slot=i) for i in range(5)
    ]
    events = Stage21FakeProvider(seeds).fetch_events(max_events=3)
    assert len(events) == 3
    assert [e.mint for e in events] == [
        "FAKE_MINT_0",
        "FAKE_MINT_1",
        "FAKE_MINT_2",
    ]


def test_fake_provider_rejects_non_seed_input():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        Stage21FakeProvider([{"mint": "FAKE_MINT_A"}])  # type: ignore[list-item]
    assert excinfo.value.code == "E2113"


def test_fake_provider_rejects_seed_with_empty_mint():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        Stage21FakeProvider([_seed(mint="")])
    assert excinfo.value.code == "E2113"


def test_fake_provider_rejects_seed_with_unknown_event_type():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        Stage21FakeProvider([_seed(event_type="real_swap")])
    assert excinfo.value.code == "E2113"


def test_fake_provider_rejects_seed_with_negative_slot():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        Stage21FakeProvider([_seed(slot=-1)])
    assert excinfo.value.code == "E2113"


def test_fake_provider_rejects_non_sequence_seeds():
    with pytest.raises(Stage21TelemetryError) as excinfo:
        Stage21FakeProvider({"not": "a sequence"})  # type: ignore[arg-type]
    assert excinfo.value.code == "E2113"


def test_fake_provider_event_is_namedtuple_of_expected_shape():
    seeds = [_seed()]
    e = Stage21FakeProvider(seeds).fetch_events()[0]
    assert isinstance(e, Stage21FakeEvent)
    assert e.provider_event_id.startswith("fake_pev_")
    assert e.signature.startswith("fake_sig_")


def test_fake_provider_does_not_require_credentials_or_webhook():
    # Construction needs only seeds. Nothing here should raise.
    seeds = [_seed()]
    provider = Stage21FakeProvider(seeds)
    # No env, no cred, no webhook attributes -- the provider is
    # purely seed-driven.
    assert provider.seed_count == 1


def test_fake_provider_payload_can_be_mappingproxy():
    payload = MappingProxyType({"fake_amount": 123})
    seeds = [_seed(raw_payload=dict(payload))]
    events = Stage21FakeProvider(seeds).fetch_events()
    assert events[0].raw_payload["fake_amount"] == 123
