"""Stage 21 provider_contracts tests."""

from __future__ import annotations

import pytest

from PHX2.stage21.errors import Stage21ProviderContractError
from PHX2.stage21.provider_contracts import (
    ProviderRawEvent,
    Stage21Provider,
    assert_events_immutable,
)


class _FakeProvider:
    """Fake provider implementation; satisfies ``Stage21Provider`` protocol.

    The fake exists only as a test scaffold for the contract. It
    does not import any network library and produces no side
    effect on construction.
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
    return ProviderRawEvent(
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


def test_provider_raw_event_is_namedtuple_with_locked_fields():
    fields = ProviderRawEvent._fields
    assert fields == (
        "provider_event_id",
        "provider_kind",
        "provider_timestamp_iso",
        "payload",
    )


def test_importing_module_has_no_network_side_effect():
    # If the module triggered a network call on import, the
    # import-boundary test would already have detected it.
    # Here we additionally exercise the module by importing it
    # fresh and asserting no top-level attribute is a network
    # client class.
    import importlib

    mod = importlib.reload(
        importlib.import_module("PHX2.stage21.provider_contracts")
    )
    for name in dir(mod):
        attr = getattr(mod, name)
        type_name = type(attr).__name__.lower()
        assert "session" not in type_name, name
        assert "client" not in type_name, name
