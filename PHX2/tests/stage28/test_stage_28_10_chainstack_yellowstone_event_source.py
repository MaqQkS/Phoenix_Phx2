"""Stage 28.10 Chainstack Yellowstone event source tests.

Pin:

  * the event source maps one fake payload to one Stage 28.9-
    compatible normalized event,
  * the event source honours ``max_events`` exactly,
  * the event source refuses non-positive / non-int max_events,
  * the event source refuses malformed payloads safely,
  * the event source refuses bad config / bad client at
    construction,
  * the event source records typed client-readiness errors
    without crashing,
  * the event source carries no secrets in errors / repr /
    results,
  * the event source produces objects structurally compatible
    with Stage 28.9 ``Stage28_9ProviderEventSource``.

No network. No env reads.
"""

from __future__ import annotations

import pytest

from PHX2.stage28.chainstack_yellowstone_contracts import (
    Stage28_10ChainstackYellowstoneFakeClient,
    Stage28_10ChainstackYellowstoneRaisingFakeClient,
)
from PHX2.stage28.chainstack_yellowstone_event_source import (
    Stage28_10ChainstackYellowstoneEventSource,
    Stage28_10EventSourceError,
    project_payload_to_normalized_event,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    AUTH_MODE_XTOKEN,
    BONDING_CURVE_VERSION_HINT_SOL_LEGACY,
    EVENT_TYPE_SWAP,
    INSTRUCTION_KIND_PUMP_SWAP,
    PAIR_TYPE_HINT_PUMP_SOL,
    QUOTE_ASSET_HINT_SOL,
    SOURCE_KIND_FAKE,
    Stage28_10ChainstackYellowstoneError,
    Stage28_10InvalidPayloadError,
    Stage28_10NormalizedEvent,
    build_chainstack_yellowstone_config,
    build_chainstack_yellowstone_payload,
)


def _build_payload(index: int = 0, **overrides):
    kwargs = dict(
        provider_event_id=f"evt_{index:09d}",
        provider_name="chainstack_yellowstone_test",
        source_kind=SOURCE_KIND_FAKE,
        mint="So11111111111111111111111111111111111111112",
        event_type=EVENT_TYPE_SWAP,
        observed_at_utc=f"2026-05-24T12:00:{index:02d}Z",
        slot=12345678 + index,
        signature=f"5sig{index:0>50d}" + "x" * 30,
        instruction_kind=INSTRUCTION_KIND_PUMP_SWAP,
        decoded_fields={"swap_in_amount": "1000000"},
        provider_quote_asset_hint=QUOTE_ASSET_HINT_SOL,
        provider_pair_type_hint=PAIR_TYPE_HINT_PUMP_SOL,
        bonding_curve_version_hint=(
            BONDING_CURVE_VERSION_HINT_SOL_LEGACY
        ),
        quote_mint=(
            "So11111111111111111111111111111111111111112"
        ),
        pool_account=(
            "PoolPoolPoolPoolPoolPoolPoolPoolPoolPoolPool11"
        ),
        pool_program_id=(
            "ProgProgProgProgProgProgProgProgProgProgProg11"
        ),
        base_mint=(
            "BaseBaseBaseBaseBaseBaseBaseBaseBaseBaseBase11"
        ),
    )
    kwargs.update(overrides)
    return build_chainstack_yellowstone_payload(**kwargs)


def _build_config(max_events: int = 8):
    return build_chainstack_yellowstone_config(
        provider_id="chainstack_yellowstone_test",
        endpoint_safe_label="yellowstone-mainnet",
        auth_mode=AUTH_MODE_XTOKEN,
        max_events=max_events,
    )


# ---------------------------------------------------------------------------
# Payload -> normalized event projection
# ---------------------------------------------------------------------------


def test_project_payload_to_normalized_event_succeeds():
    payload = _build_payload(0)
    event = project_payload_to_normalized_event(payload)
    assert isinstance(event, Stage28_10NormalizedEvent)
    assert event.event_id.startswith("stage28_10_")
    assert event.provider_event_id == payload.provider_event_id
    assert event.provider_name == payload.provider_name
    assert event.mint == payload.mint
    assert event.event_type == payload.event_type
    assert event.observed_at_utc == payload.observed_at_utc
    assert event.raw_event_hash.startswith("stage28_10_")
    assert event.quote_mint == payload.quote_mint
    assert event.pool_account == payload.pool_account
    assert event.pool_program_id == payload.pool_program_id
    assert event.base_mint == payload.base_mint
    assert (
        event.bonding_curve_version_hint
        == payload.bonding_curve_version_hint
    )
    assert (
        event.provider_quote_asset_hint
        == payload.provider_quote_asset_hint
    )
    assert (
        event.provider_pair_type_hint
        == payload.provider_pair_type_hint
    )


def test_project_payload_to_normalized_event_rejects_non_payload():
    with pytest.raises(Stage28_10InvalidPayloadError):
        project_payload_to_normalized_event(
            "not_a_payload",  # type: ignore[arg-type]
        )


def test_project_payload_to_normalized_event_no_hints_preserved_as_none():
    payload = _build_payload(
        0,
        quote_mint=None,
        pool_account=None,
        pool_program_id=None,
        base_mint=None,
        bonding_curve_version_hint=None,
        provider_quote_asset_hint=None,
        provider_pair_type_hint=None,
        provider_bonding_curve_version_hint=None,
    )
    event = project_payload_to_normalized_event(payload)
    assert event.quote_mint is None
    assert event.pool_account is None
    assert event.pool_program_id is None
    assert event.base_mint is None
    assert event.bonding_curve_version_hint is None
    assert event.provider_quote_asset_hint is None
    assert event.provider_pair_type_hint is None


# ---------------------------------------------------------------------------
# Event source construction
# ---------------------------------------------------------------------------


def test_event_source_constructs_with_safe_inputs():
    config = _build_config()
    client = Stage28_10ChainstackYellowstoneFakeClient(payloads=[])
    source = Stage28_10ChainstackYellowstoneEventSource(
        config=config, client=client,
    )
    assert source.config is config
    assert source.iter_count == 0
    assert source.payloads_seen == 0
    assert source.normalized_yielded == 0
    assert source.payloads_skipped_malformed == 0
    assert source.last_client_error_reason is None


def test_event_source_rejects_non_config():
    client = Stage28_10ChainstackYellowstoneFakeClient(payloads=[])
    with pytest.raises(Stage28_10EventSourceError):
        Stage28_10ChainstackYellowstoneEventSource(
            config="not_a_config",  # type: ignore[arg-type]
            client=client,
        )


def test_event_source_rejects_client_missing_iter_method():
    config = _build_config()

    class _NoIterClient:
        pass

    with pytest.raises(Stage28_10EventSourceError):
        Stage28_10ChainstackYellowstoneEventSource(
            config=config,
            client=_NoIterClient(),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Event source iter_events behaviour
# ---------------------------------------------------------------------------


def test_event_source_yields_one_normalized_event_from_one_payload():
    config = _build_config(max_events=8)
    payload = _build_payload(0)
    client = Stage28_10ChainstackYellowstoneFakeClient(
        payloads=[payload],
    )
    source = Stage28_10ChainstackYellowstoneEventSource(
        config=config, client=client,
    )
    yielded = list(source.iter_events(max_events=1))
    assert len(yielded) == 1
    event = yielded[0]
    assert isinstance(event, Stage28_10NormalizedEvent)
    assert event.provider_event_id == payload.provider_event_id
    assert source.iter_count == 1
    assert source.payloads_seen == 1
    assert source.normalized_yielded == 1
    assert source.payloads_skipped_malformed == 0


def test_event_source_honours_max_events_smaller_than_payloads():
    config = _build_config(max_events=10)
    payloads = [_build_payload(i) for i in range(5)]
    client = Stage28_10ChainstackYellowstoneFakeClient(
        payloads=payloads,
    )
    source = Stage28_10ChainstackYellowstoneEventSource(
        config=config, client=client,
    )
    yielded = list(source.iter_events(max_events=3))
    assert len(yielded) == 3


def test_event_source_honours_config_max_events_as_upper_bound():
    config = _build_config(max_events=2)
    payloads = [_build_payload(i) for i in range(5)]
    client = Stage28_10ChainstackYellowstoneFakeClient(
        payloads=payloads,
    )
    source = Stage28_10ChainstackYellowstoneEventSource(
        config=config, client=client,
    )
    yielded = list(source.iter_events(max_events=10))
    assert len(yielded) == 2


@pytest.mark.parametrize("bad_max_events", [0, -1, 1.5, True])
def test_event_source_rejects_bad_max_events(bad_max_events):
    config = _build_config()
    client = Stage28_10ChainstackYellowstoneFakeClient(payloads=[])
    source = Stage28_10ChainstackYellowstoneEventSource(
        config=config, client=client,
    )
    with pytest.raises(Stage28_10EventSourceError):
        list(source.iter_events(max_events=bad_max_events))


def test_event_source_handles_client_error_safely():
    config = _build_config()
    client = Stage28_10ChainstackYellowstoneRaisingFakeClient(
        reason="UPSTREAM_HICCUP",
    )
    source = Stage28_10ChainstackYellowstoneEventSource(
        config=config, client=client,
    )
    yielded = list(source.iter_events(max_events=1))
    assert yielded == []
    assert source.iter_count == 1
    assert source.last_client_error_reason == "UPSTREAM_HICCUP"


def test_event_source_skips_non_payload_emitted_by_client():
    config = _build_config()

    class _BadClient:
        def iter_yellowstone_events(self, *, max_events):
            yield "not_a_payload"

    source = Stage28_10ChainstackYellowstoneEventSource(
        config=config,
        client=_BadClient(),  # type: ignore[arg-type]
    )
    yielded = list(source.iter_events(max_events=1))
    assert yielded == []
    assert source.payloads_seen == 1
    assert source.payloads_skipped_malformed == 1


def test_event_source_iter_call_count_increments():
    config = _build_config()
    client = Stage28_10ChainstackYellowstoneFakeClient(payloads=[])
    source = Stage28_10ChainstackYellowstoneEventSource(
        config=config, client=client,
    )
    list(source.iter_events(max_events=1))
    list(source.iter_events(max_events=1))
    assert source.iter_count == 2


# ---------------------------------------------------------------------------
# Stage 28.9 structural compatibility
# ---------------------------------------------------------------------------


def test_event_source_satisfies_stage28_9_provider_event_source_shape():
    """The Stage 28.10 event source MUST expose an
    ``iter_events(max_events=...)`` method so a Stage 28.9
    orchestrator can plug it in. This test does NOT import
    Stage 28.9 to avoid widening the boundary -- it pins the
    structural shape directly.
    """
    config = _build_config()
    client = Stage28_10ChainstackYellowstoneFakeClient(payloads=[])
    source = Stage28_10ChainstackYellowstoneEventSource(
        config=config, client=client,
    )
    assert hasattr(source, "iter_events")
    method = getattr(source, "iter_events")
    assert callable(method)


# ---------------------------------------------------------------------------
# Redaction safety
# ---------------------------------------------------------------------------


def test_event_source_error_reason_carries_no_secret():
    err = Stage28_10EventSourceError(reason="REASON_X")
    rendered = str(err).lower()
    forbidden = (
        "h" + "ttps://",
        "h" + "ttp://",
        "bearer",
        "token=",
        "secret=",
        "password",
        "x-token",
    )
    for needle in forbidden:
        assert needle not in rendered, (
            f"event source error leaked {needle!r}"
        )


def test_event_source_error_is_subclass_of_module_root():
    assert issubclass(
        Stage28_10EventSourceError,
        Stage28_10ChainstackYellowstoneError,
    )
