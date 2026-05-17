"""Stage 21 provider_contracts tests (covers AUDIT-006 freeze_payload)."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from PHX2.stage21.errors import Stage21ProviderContractError
from PHX2.stage21.provider_contracts import (
    ProviderRawEvent,
    Stage21Provider,
    assert_events_immutable,
    assert_payload_is_frozen,
    empty_frozen_payload,
    freeze_payload,
    make_event,
)


class _FakeProvider:
    """Fake provider implementation; satisfies ``Stage21Provider`` protocol.

    The fake exists only as a test scaffold for the contract. It
    does not import any network library and produces no side
    effect on construction. Tests construct events via
    ``make_event`` so payloads are always frozen.
    """

    def __init__(self, events: tuple[ProviderRawEvent, ...]) -> None:
        self._events = events

    def fetch_events(
        self,
        *,
        cursor: object = None,
        max_events: int = 0,
    ) -> tuple[ProviderRawEvent, ...]:
        if max_events and max_events > 0:
            return tuple(self._events[:max_events])
        return self._events


def _sample_event(event_id: str) -> ProviderRawEvent:
    return make_event(
        provider_event_id=event_id,
        provider_kind="swap",
        provider_timestamp_iso="2026-05-17T12:00:00Z",
        payload={"key": "value"},
    )


def test_fake_provider_satisfies_protocol_without_network():
    fake = _FakeProvider((_sample_event("a"), _sample_event("b")))
    typed: Stage21Provider = fake
    events = typed.fetch_events()
    assert events == (_sample_event("a"), _sample_event("b"))


def test_fetch_events_returns_tuple_not_list():
    fake = _FakeProvider((_sample_event("a"),))
    events = fake.fetch_events()
    assert isinstance(events, tuple)


def test_fake_provider_returns_empty_when_no_events_available():
    fake = _FakeProvider(())
    assert fake.fetch_events() == ()


def test_fake_provider_respects_max_events():
    fake = _FakeProvider(tuple(_sample_event(str(i)) for i in range(5)))
    events = fake.fetch_events(max_events=3)
    assert len(events) == 3
    assert events[0].provider_event_id == "0"
    assert events[2].provider_event_id == "2"


def test_assert_events_immutable_returns_tuple():
    events = [_sample_event("a"), _sample_event("b")]
    frozen = assert_events_immutable(events)
    assert isinstance(frozen, tuple)
    assert len(frozen) == 2


def test_assert_events_immutable_rejects_non_provider_event():
    with pytest.raises(Stage21ProviderContractError) as excinfo:
        assert_events_immutable(["bad"])  # type: ignore[list-item]
    assert excinfo.value.code == "E2120"


def test_assert_events_immutable_rejects_mutable_payload():
    # Construct an event directly (bypassing make_event) with a
    # mutable dict payload. The contract must catch this.
    mutable = ProviderRawEvent(
        provider_event_id="x",
        provider_kind="swap",
        provider_timestamp_iso="2026-05-17T12:00:00Z",
        payload={"key": "value"},  # raw dict, not frozen
    )
    with pytest.raises(Stage21ProviderContractError) as excinfo:
        assert_events_immutable([mutable])
    assert excinfo.value.code == "E2121"


def test_provider_raw_event_is_namedtuple_with_locked_fields():
    fields = ProviderRawEvent._fields
    assert fields == (
        "provider_event_id",
        "provider_kind",
        "provider_timestamp_iso",
        "payload",
    )


def test_importing_module_has_no_network_side_effect():
    import importlib

    mod = importlib.reload(
        importlib.import_module("PHX2.stage21.provider_contracts")
    )
    for name in dir(mod):
        attr = getattr(mod, name)
        type_name = type(attr).__name__.lower()
        assert "session" not in type_name, name
        assert "client" not in type_name, name


# ---------------------------------------------------------------------------
# AUDIT-006: freeze_payload + assert_payload_is_frozen
# ---------------------------------------------------------------------------


def test_freeze_payload_returns_mapping_proxy():
    frozen = freeze_payload({"a": 1, "b": "x"})
    assert isinstance(frozen, MappingProxyType)
    assert frozen["a"] == 1
    assert frozen["b"] == "x"


def test_freeze_payload_is_immutable_at_top_level():
    frozen = freeze_payload({"a": 1})
    with pytest.raises(TypeError):
        frozen["a"] = 2  # type: ignore[index]


def test_freeze_payload_freezes_nested_mappings():
    frozen = freeze_payload({"outer": {"inner": 1}})
    assert isinstance(frozen["outer"], MappingProxyType)


def test_freeze_payload_coerces_lists_to_tuples():
    frozen = freeze_payload({"items": [1, 2, 3]})
    assert isinstance(frozen["items"], tuple)
    assert frozen["items"] == (1, 2, 3)


def test_freeze_payload_rejects_non_mapping():
    with pytest.raises(Stage21ProviderContractError) as excinfo:
        freeze_payload([("a", 1)])  # type: ignore[arg-type]
    assert excinfo.value.code == "E2121"


# ---------------------------------------------------------------------------
# AUDIT-006 re-audit: deep / recursive freezing
# ---------------------------------------------------------------------------


def test_freeze_payload_deep_freezes_dict_under_dict():
    frozen = freeze_payload({"outer": {"inner": {"leaf": 1}}})
    assert isinstance(frozen["outer"], MappingProxyType)
    assert isinstance(frozen["outer"]["inner"], MappingProxyType)
    # Mutation must fail at every depth.
    with pytest.raises(TypeError):
        frozen["outer"]["inner"]["leaf"] = 2  # type: ignore[index]
    with pytest.raises(TypeError):
        frozen["outer"]["inner"] = {"replaced": 0}  # type: ignore[index]


def test_freeze_payload_freezes_dict_inside_list():
    frozen = freeze_payload({"items": [{"mutable": 1}, {"mutable": 2}]})
    assert isinstance(frozen["items"], tuple)
    for item in frozen["items"]:
        assert isinstance(item, MappingProxyType)
    with pytest.raises(TypeError):
        frozen["items"][0]["mutable"] = 99  # type: ignore[index]


def test_freeze_payload_freezes_dict_inside_tuple():
    frozen = freeze_payload({"items": ({"mutable": 1}, {"mutable": 2})})
    assert isinstance(frozen["items"], tuple)
    for item in frozen["items"]:
        assert isinstance(item, MappingProxyType)
    with pytest.raises(TypeError):
        frozen["items"][1]["mutable"] = 99  # type: ignore[index]


def test_freeze_payload_freezes_nested_list_inside_dict():
    frozen = freeze_payload({"layers": [[{"k": "v"}]]})
    assert isinstance(frozen["layers"], tuple)
    assert isinstance(frozen["layers"][0], tuple)
    assert isinstance(frozen["layers"][0][0], MappingProxyType)
    with pytest.raises(TypeError):
        frozen["layers"][0][0]["k"] = "x"  # type: ignore[index]


def test_freeze_payload_freezes_deeply_mixed_structure():
    payload = {
        "swap": {
            "legs": [
                {"side": "buy", "size": 1.5},
                {"side": "sell", "meta": {"flag": True, "tags": ["a", "b"]}},
            ],
            "summary": ({"k": 1}, {"k": 2}),
        },
    }
    frozen = freeze_payload(payload)
    assert isinstance(frozen, MappingProxyType)
    assert isinstance(frozen["swap"], MappingProxyType)
    assert isinstance(frozen["swap"]["legs"], tuple)
    assert isinstance(frozen["swap"]["legs"][0], MappingProxyType)
    assert isinstance(frozen["swap"]["legs"][1]["meta"], MappingProxyType)
    assert isinstance(frozen["swap"]["legs"][1]["meta"]["tags"], tuple)
    assert isinstance(frozen["swap"]["summary"], tuple)
    assert isinstance(frozen["swap"]["summary"][0], MappingProxyType)
    # Mutation attempts at every level must fail.
    with pytest.raises(TypeError):
        frozen["swap"]["legs"][0]["side"] = "x"  # type: ignore[index]
    with pytest.raises(TypeError):
        frozen["swap"]["legs"][1]["meta"]["flag"] = False  # type: ignore[index]
    with pytest.raises(TypeError):
        frozen["swap"]["summary"][0]["k"] = 99  # type: ignore[index]


def test_freeze_payload_preserves_primitive_leaf_values():
    frozen = freeze_payload({
        "s": "string",
        "i": 7,
        "f": 1.5,
        "b": True,
        "n": None,
        "raw": b"bytes",
    })
    assert frozen["s"] == "string"
    assert frozen["i"] == 7
    assert frozen["f"] == 1.5
    assert frozen["b"] is True
    assert frozen["n"] is None
    assert frozen["raw"] == b"bytes"


def test_freeze_payload_rejects_unsupported_leaf_type():
    # ``set`` is not a JSON-shaped leaf; the deep freezer must
    # reject it with E2121 rather than passing it through.
    with pytest.raises(Stage21ProviderContractError) as excinfo:
        freeze_payload({"weird": {1, 2, 3}})
    assert excinfo.value.code == "E2121"


def test_freeze_payload_rejects_unsupported_type_nested_inside_list():
    with pytest.raises(Stage21ProviderContractError) as excinfo:
        freeze_payload({"items": [{"k": {1, 2}}]})
    assert excinfo.value.code == "E2121"


def test_freeze_payload_rejects_unsupported_type_nested_inside_dict():
    with pytest.raises(Stage21ProviderContractError) as excinfo:
        freeze_payload({"outer": {"weird": object()}})
    assert excinfo.value.code == "E2121"


def test_assert_payload_is_frozen_still_rejects_top_level_raw_dict():
    # Construct a ProviderRawEvent directly with a raw dict payload
    # (bypassing make_event). The top-level immutability check must
    # still flag this as E2121.
    raw_event = ProviderRawEvent(
        provider_event_id="x",
        provider_kind="swap",
        provider_timestamp_iso="2026-05-17T12:00:00Z",
        payload={"k": "v"},
    )
    with pytest.raises(Stage21ProviderContractError) as excinfo:
        assert_payload_is_frozen(raw_event)
    assert excinfo.value.code == "E2121"


def test_make_event_with_deeply_nested_payload_produces_frozen_event():
    event = make_event(
        provider_event_id="x",
        provider_kind="swap",
        provider_timestamp_iso="2026-05-17T12:00:00Z",
        payload={"a": {"b": [{"c": 1}]}},
    )
    assert isinstance(event.payload, MappingProxyType)
    assert isinstance(event.payload["a"], MappingProxyType)
    assert isinstance(event.payload["a"]["b"], tuple)
    assert isinstance(event.payload["a"]["b"][0], MappingProxyType)
    with pytest.raises(TypeError):
        event.payload["a"]["b"][0]["c"] = 2  # type: ignore[index]


def test_empty_frozen_payload_is_mapping_proxy():
    empty = empty_frozen_payload()
    assert isinstance(empty, MappingProxyType)
    assert dict(empty) == {}


def test_empty_frozen_payload_is_singleton():
    # The module pre-builds the empty mapping; identity matters
    # to keep allocation pressure low.
    assert empty_frozen_payload() is empty_frozen_payload()


def test_assert_payload_is_frozen_accepts_frozen_payload():
    event = make_event(
        provider_event_id="a",
        provider_kind="swap",
        provider_timestamp_iso="2026-05-17T12:00:00Z",
        payload={"key": "value"},
    )
    assert_payload_is_frozen(event)  # no raise


def test_assert_payload_is_frozen_rejects_dict_payload():
    event = ProviderRawEvent(
        provider_event_id="a",
        provider_kind="swap",
        provider_timestamp_iso="2026-05-17T12:00:00Z",
        payload={"key": "value"},  # raw dict
    )
    with pytest.raises(Stage21ProviderContractError) as excinfo:
        assert_payload_is_frozen(event)
    assert excinfo.value.code == "E2121"


def test_make_event_with_default_payload_is_empty_frozen():
    event = make_event(
        provider_event_id="x",
        provider_kind="swap",
        provider_timestamp_iso="2026-05-17T12:00:00Z",
    )
    # The default-payload event must be a frozen MappingProxyType
    # with no entries. Identity-equality is intentionally not
    # asserted -- ``importlib.reload`` in an earlier test can
    # cycle the module-level singleton and we tolerate that drift
    # so long as the immutability + emptiness invariants hold.
    assert isinstance(event.payload, MappingProxyType)
    assert dict(event.payload) == {}


def test_make_event_freezes_supplied_payload():
    event = make_event(
        provider_event_id="x",
        provider_kind="swap",
        provider_timestamp_iso="2026-05-17T12:00:00Z",
        payload={"k": "v"},
    )
    assert isinstance(event.payload, MappingProxyType)
    with pytest.raises(TypeError):
        event.payload["k"] = "y"  # type: ignore[index]
