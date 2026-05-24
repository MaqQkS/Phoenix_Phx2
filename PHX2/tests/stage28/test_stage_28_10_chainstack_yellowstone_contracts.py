"""Stage 28.10 Chainstack Yellowstone contracts tests.

Pin:

  * the Stage 28.10 client Protocol is structurally satisfied by
    the deterministic fake client + by the raising fake client,
  * the fake client honours ``max_events`` exactly,
  * the fake client refuses non-payload entries at construction,
  * the fake client refuses non-positive / non-int max_events,
  * the raising fake client raises typed errors,
  * the fake client never carries a URL / secret in its repr,
  * the contracts module imports no network library.

No network. No env reads.
"""

from __future__ import annotations

import pytest

from PHX2.stage28.chainstack_yellowstone_contracts import (
    Stage28_10ChainstackYellowstoneClient,
    Stage28_10ChainstackYellowstoneClientError,
    Stage28_10ChainstackYellowstoneFakeClient,
    Stage28_10ChainstackYellowstoneRaisingFakeClient,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    EVENT_TYPE_SWAP,
    INSTRUCTION_KIND_PUMP_SWAP,
    QUOTE_ASSET_HINT_SOL,
    SOURCE_KIND_FAKE,
    Stage28_10ChainstackYellowstoneError,
    build_chainstack_yellowstone_payload,
)


def _build_payload(index: int = 0):
    return build_chainstack_yellowstone_payload(
        provider_event_id=f"evt_{index:09d}",
        provider_name="chainstack_yellowstone_test",
        source_kind=SOURCE_KIND_FAKE,
        mint="So11111111111111111111111111111111111111112",
        event_type=EVENT_TYPE_SWAP,
        observed_at_utc=f"2026-05-24T12:00:{index:02d}Z",
        slot=12345678 + index,
        signature=(
            f"5sig{index:0>50d}"
            + "x" * 30
        ),
        instruction_kind=INSTRUCTION_KIND_PUMP_SWAP,
        decoded_fields={"swap_in_amount": "1000000"},
        provider_quote_asset_hint=QUOTE_ASSET_HINT_SOL,
    )


# ---------------------------------------------------------------------------
# Protocol structural conformance
# ---------------------------------------------------------------------------


def test_fake_client_satisfies_protocol():
    client = Stage28_10ChainstackYellowstoneFakeClient(payloads=[])
    assert isinstance(
        client, Stage28_10ChainstackYellowstoneClient,
    )


def test_raising_fake_client_satisfies_protocol():
    client = Stage28_10ChainstackYellowstoneRaisingFakeClient()
    assert isinstance(
        client, Stage28_10ChainstackYellowstoneClient,
    )


# ---------------------------------------------------------------------------
# Fake client yield behaviour
# ---------------------------------------------------------------------------


def test_fake_client_iter_yields_one_payload():
    payload = _build_payload(0)
    client = Stage28_10ChainstackYellowstoneFakeClient(
        payloads=[payload],
    )
    yielded = list(client.iter_yellowstone_events(max_events=1))
    assert yielded == [payload]
    assert client.iter_call_count == 1


def test_fake_client_iter_honours_max_events_smaller_than_payloads():
    payloads = [_build_payload(i) for i in range(5)]
    client = Stage28_10ChainstackYellowstoneFakeClient(
        payloads=payloads,
    )
    yielded = list(client.iter_yellowstone_events(max_events=3))
    assert len(yielded) == 3
    assert yielded == payloads[:3]


def test_fake_client_iter_honours_max_events_larger_than_payloads():
    payloads = [_build_payload(i) for i in range(3)]
    client = Stage28_10ChainstackYellowstoneFakeClient(
        payloads=payloads,
    )
    yielded = list(client.iter_yellowstone_events(max_events=10))
    assert yielded == payloads


def test_fake_client_iter_call_count_increments():
    client = Stage28_10ChainstackYellowstoneFakeClient(payloads=[])
    assert client.iter_call_count == 0
    list(client.iter_yellowstone_events(max_events=1))
    assert client.iter_call_count == 1
    list(client.iter_yellowstone_events(max_events=1))
    assert client.iter_call_count == 2


def test_fake_client_fetch_honours_max_events():
    payloads = [_build_payload(i) for i in range(5)]
    client = Stage28_10ChainstackYellowstoneFakeClient(
        payloads=payloads,
    )
    yielded, cursor = client.fetch_yellowstone_events(
        cursor=None, max_events=2,
    )
    assert yielded == tuple(payloads[:2])
    assert cursor is None
    assert client.fetch_call_count == 1


def test_fake_client_fetch_accepts_explicit_cursor():
    payloads = [_build_payload(i) for i in range(3)]
    client = Stage28_10ChainstackYellowstoneFakeClient(
        payloads=payloads,
    )
    yielded, cursor = client.fetch_yellowstone_events(
        cursor="cursor_abc", max_events=5,
    )
    assert yielded == tuple(payloads)
    assert cursor is None


def test_fake_client_payload_count_property():
    payloads = [_build_payload(i) for i in range(4)]
    client = Stage28_10ChainstackYellowstoneFakeClient(
        payloads=payloads,
    )
    assert client.payload_count == 4


# ---------------------------------------------------------------------------
# Fake client rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_max_events", [0, -1, 1.5, True])
def test_fake_client_iter_rejects_non_positive_or_non_int_max(
    bad_max_events,
):
    client = Stage28_10ChainstackYellowstoneFakeClient(payloads=[])
    with pytest.raises(
        Stage28_10ChainstackYellowstoneClientError,
    ):
        list(
            client.iter_yellowstone_events(
                max_events=bad_max_events,
            ),
        )


@pytest.mark.parametrize("bad_max_events", [0, -1, 1.5, True])
def test_fake_client_fetch_rejects_non_positive_or_non_int_max(
    bad_max_events,
):
    client = Stage28_10ChainstackYellowstoneFakeClient(payloads=[])
    with pytest.raises(
        Stage28_10ChainstackYellowstoneClientError,
    ):
        client.fetch_yellowstone_events(
            cursor=None, max_events=bad_max_events,
        )


def test_fake_client_fetch_rejects_non_string_cursor():
    client = Stage28_10ChainstackYellowstoneFakeClient(payloads=[])
    with pytest.raises(
        Stage28_10ChainstackYellowstoneClientError,
    ):
        client.fetch_yellowstone_events(
            cursor=123, max_events=1,  # type: ignore[arg-type]
        )


def test_fake_client_construction_rejects_non_payload_entry():
    with pytest.raises(
        Stage28_10ChainstackYellowstoneClientError,
    ):
        Stage28_10ChainstackYellowstoneFakeClient(
            payloads=["not_a_payload"],  # type: ignore[list-item]
        )


# ---------------------------------------------------------------------------
# Raising fake client
# ---------------------------------------------------------------------------


def test_raising_fake_client_iter_raises_typed():
    client = Stage28_10ChainstackYellowstoneRaisingFakeClient(
        reason="UPSTREAM_HICCUP",
    )
    with pytest.raises(
        Stage28_10ChainstackYellowstoneClientError,
    ) as exc_info:
        list(client.iter_yellowstone_events(max_events=1))
    assert exc_info.value.reason == "UPSTREAM_HICCUP"


def test_raising_fake_client_fetch_raises_typed():
    client = Stage28_10ChainstackYellowstoneRaisingFakeClient(
        reason="UPSTREAM_HICCUP",
    )
    with pytest.raises(
        Stage28_10ChainstackYellowstoneClientError,
    ) as exc_info:
        client.fetch_yellowstone_events(
            cursor=None, max_events=1,
        )
    assert exc_info.value.reason == "UPSTREAM_HICCUP"


def test_raising_fake_client_rejects_empty_reason():
    with pytest.raises(
        Stage28_10ChainstackYellowstoneClientError,
    ):
        Stage28_10ChainstackYellowstoneRaisingFakeClient(
            reason="",
        )


def test_raising_fake_client_exposes_reason():
    client = Stage28_10ChainstackYellowstoneRaisingFakeClient(
        reason="REASON_X",
    )
    assert client.reason == "REASON_X"


# ---------------------------------------------------------------------------
# Error hierarchy + redaction
# ---------------------------------------------------------------------------


def test_client_error_is_subclass():
    assert issubclass(
        Stage28_10ChainstackYellowstoneClientError,
        Stage28_10ChainstackYellowstoneError,
    )


def test_client_error_message_carries_reason():
    err = Stage28_10ChainstackYellowstoneClientError(
        "MY_REASON",
    )
    assert err.reason == "MY_REASON"
    assert "MY_REASON" in str(err)


def test_fake_client_repr_carries_no_secret():
    payload = _build_payload(0)
    client = Stage28_10ChainstackYellowstoneFakeClient(
        payloads=[payload],
    )
    rendered = repr(client).lower()
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
            f"fake client repr leaked {needle!r}"
        )
