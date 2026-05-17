"""Stage 21 provider contract types.

Stage 21 will eventually consume a provider (Helius / gRPC /
Birdeye / ... -- the specific choice is Stage 21.3 scope) via a
narrow async-or-sync contract. Stage 21.1 ships the contract
types only; the concrete adapter is deferred.

Key invariants:
  * The contract is fakeable. Tests construct a fake provider by
    implementing the ``Stage21Provider`` Protocol directly; no
    network library import is required.
  * Importing this module triggers no network side effects. The
    Stage 21 import-boundary test asserts this module has no
    top-level requests / httpx / aiohttp / websockets / grpc /
    Helius / Birdeye / ... imports.
  * The contract surface stays small. ``Stage21Provider`` exposes
    a single method (``fetch_events``) that returns an immutable
    tuple of typed ``ProviderRawEvent`` records. The Stage 22+
    hardening sub-stage will add a separate streaming API; that
    surface is out of scope for 21.1.

The ``ProviderRawEvent`` shape is deliberately minimal -- a
typed pass-through container. Stage 21.2+ will define the
normalized PHX2 event shape (``ProviderNormalizedEvent``) and the
mapper from raw -> normalized. 21.1 does not normalize.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, NamedTuple, Protocol, Sequence, Tuple

from PHX2.stage21.constants import Stage21ErrorCode
from PHX2.stage21.errors import Stage21ProviderContractError


# An immutable empty mapping used as the canonical "no payload"
# fallback when callers omit a payload. Built once at module load.
_EMPTY_FROZEN_PAYLOAD: Mapping[str, object] = MappingProxyType({})


# Allowed leaf types in a Stage 21 provider payload. JSON-shaped
# values plus ``bytes`` (some providers emit binary blobs). Any
# other type at any depth triggers an E2121 freeze error -- the
# Stage 21 contract is strict so unfreezable custom objects never
# slip through.
_PAYLOAD_LEAF_TYPES: tuple[type, ...] = (str, int, float, bool, bytes)


def _freeze_value(value: object, *, path: str) -> object:
    """Recursively freeze ``value`` for a Stage 21 payload.

    Returns:
      * ``None`` as-is.
      * Any ``_PAYLOAD_LEAF_TYPES`` instance (str, int, float,
        bool, bytes) as-is. ``bool`` is handled before ``int``
        only conceptually -- Python's ``isinstance`` against
        either accepts both, and both return value-identical
        primitives.
      * ``Mapping`` -> ``MappingProxyType`` whose values are
        themselves recursively frozen.
      * ``list`` / ``tuple`` -> ``tuple`` whose items are
        themselves recursively frozen (so a dict inside a list /
        tuple is wrapped in ``MappingProxyType``).

    Anything else raises ``Stage21ProviderContractError`` (E2121)
    with the offending type name and the dotted path inside the
    payload. The path is a non-secret breadcrumb (it carries only
    structural keys / indices, never values).
    """
    if value is None:
        return None
    if isinstance(value, _PAYLOAD_LEAF_TYPES):
        return value
    if isinstance(value, Mapping):
        frozen: dict[object, object] = {}
        for key, sub in value.items():
            frozen[key] = _freeze_value(sub, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_value(item, path=f"{path}[{i}]")
            for i, item in enumerate(value)
        )
    raise Stage21ProviderContractError(
        Stage21ErrorCode.E2121,
        detail=(
            "freeze_payload encountered unsupported type "
            f"{type(value).__name__} at payload path {path}"
        ),
    )


def freeze_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    """Return a deeply-immutable ``MappingProxyType`` view of ``payload``.

    AUDIT-006: Stage 21.2+ will construct ``ProviderRawEvent``
    instances with provider-supplied payloads. If those payloads
    are mutable dicts -- or contain nested mutable dicts inside
    lists / tuples -- downstream code could mutate them between
    receipt and use. ``freeze_payload`` is the helper that
    normalizes any inbound mapping into a deeply-frozen view.

    Freezing rules:
      * The root payload itself MUST be a ``Mapping``; anything
        else raises ``Stage21ProviderContractError`` (E2121).
      * Nested ``Mapping`` values are recursively wrapped in
        ``MappingProxyType`` -- ``frozen["outer"]["inner"]`` is
        also immutable.
      * ``list`` and ``tuple`` values are coerced into ``tuple``;
        dict items inside lists / tuples are themselves recursively
        frozen, so ``frozen["items"][0]`` cannot be mutated.
      * Leaf values must be one of: ``None``, ``str``, ``int``,
        ``float``, ``bool``, ``bytes``. Any other type at any
        depth raises ``Stage21ProviderContractError`` (E2121)
        with the offending path inside the payload.

    The function is pure: identical input produces identical
    output (sequence ordering preserved, dict iteration order
    preserved).
    """
    if not isinstance(payload, Mapping):
        raise Stage21ProviderContractError(
            Stage21ErrorCode.E2121,
            detail=(
                "freeze_payload expected a Mapping; got "
                f"{type(payload).__name__}"
            ),
        )
    frozen: dict[object, object] = {}
    for key, value in payload.items():
        frozen[key] = _freeze_value(value, path=str(key))
    return MappingProxyType(frozen)


def empty_frozen_payload() -> Mapping[str, object]:
    """Return the canonical empty frozen payload.

    Tests and Stage 21.2 fake providers that don't need a payload
    body can use this directly rather than calling
    ``freeze_payload({})`` repeatedly.
    """
    return _EMPTY_FROZEN_PAYLOAD


class ProviderRawEvent(NamedTuple):
    """Minimal typed pass-through container for a provider raw event.

    Stage 21.1 does not interpret the payload. The fields capture
    only what every provider supplies as part of any v0 contract:

      * ``provider_event_id`` -- string id assigned by the
        provider. Used as the dedupe key by the Stage 21.5+ local
        ledger; 21.1 does not dedupe.
      * ``provider_kind`` -- short string identifying the event
        family (e.g. ``swap`` / ``mint``). The exact vocabulary
        is provider-specific and Stage 21.3 will lock the set
        we consume.
      * ``provider_timestamp_iso`` -- ISO-8601 UTC string the
        provider claims. Treated as opaque metadata in 21.1.
      * ``payload`` -- a ``Mapping[str, object]`` carrying the
        provider's event body. Wrapped in ``MappingProxyType`` or
        an immutable mapping by the caller; the contract record
        itself does not freeze nested values.

    The record is intentionally opaque. Stage 21.2 will introduce
    a richer normalized event type; 21.1 does not bind to that
    yet.
    """

    provider_event_id: str
    provider_kind: str
    provider_timestamp_iso: str
    payload: Mapping[str, object]


class Stage21Provider(Protocol):
    """Stage 21 provider contract.

    Implementations supply ``fetch_events`` and nothing else for
    21.1. Tests construct fakes by writing a simple class that
    matches the Protocol -- no inheritance required, no network
    library required.

    Contract semantics:
      * The returned tuple MUST be immutable. Implementations that
        cannot guarantee immutability should return a ``tuple``,
        not a ``list``.
      * The ``cursor`` argument is provider-defined; ``None`` means
        "start from the provider's current position". 21.1
        does not specify the cursor format.
      * Implementations MUST NOT raise on missing data; an empty
        tuple is the contract-correct "no events" response.
      * Implementations that need to surface a contract violation
        SHOULD raise ``Stage21ProviderContractError`` so callers
        can match the closed code surface.
    """

    def fetch_events(
        self,
        *,
        cursor: object = None,
        max_events: int = 0,
    ) -> Tuple[ProviderRawEvent, ...]: ...


def assert_payload_is_frozen(event: ProviderRawEvent) -> None:
    """Validate that ``event.payload`` is a frozen mapping.

    AUDIT-006: Stage 21 requires every ``ProviderRawEvent``
    payload to be a ``MappingProxyType`` (the immutable mapping
    type produced by ``freeze_payload``). The helper raises
    ``Stage21ProviderContractError`` (E2121) if the payload is a
    mutable mapping (e.g. raw ``dict``) or any other type.

    Stage 21.2+ fake providers must call ``freeze_payload`` (or
    use ``empty_frozen_payload``) before constructing a
    ``ProviderRawEvent``; the contract enforces this at the
    immutability check.
    """
    if not isinstance(event.payload, MappingProxyType):
        raise Stage21ProviderContractError(
            Stage21ErrorCode.E2121,
            detail=(
                "ProviderRawEvent payload must be a frozen "
                "MappingProxyType (build it via freeze_payload); got "
                f"{type(event.payload).__name__}"
            ),
        )


def make_event(
    *,
    provider_event_id: str,
    provider_kind: str,
    provider_timestamp_iso: str,
    payload: Mapping[str, object] = _EMPTY_FROZEN_PAYLOAD,
) -> ProviderRawEvent:
    """Construct a ``ProviderRawEvent`` with a frozen payload.

    Convenience constructor that runs ``payload`` through
    ``freeze_payload`` so the returned event always satisfies the
    Stage 21 immutability contract. Tests and Stage 21.2 fake
    providers should prefer this over the raw NamedTuple
    constructor.
    """
    if payload is _EMPTY_FROZEN_PAYLOAD:
        frozen_payload = _EMPTY_FROZEN_PAYLOAD
    else:
        frozen_payload = freeze_payload(payload)
    return ProviderRawEvent(
        provider_event_id=provider_event_id,
        provider_kind=provider_kind,
        provider_timestamp_iso=provider_timestamp_iso,
        payload=frozen_payload,
    )


def assert_events_immutable(
    events: Sequence[ProviderRawEvent],
) -> Tuple[ProviderRawEvent, ...]:
    """Validate and freeze a provider's ``fetch_events`` return value.

    Stage 21.1 calls this helper from the fake provider used in
    the contract test. The helper:
      * coerces the input to a ``tuple`` of ``ProviderRawEvent``;
      * raises ``Stage21ProviderContractError`` (E2120) if any
        element is not a ``ProviderRawEvent``;
      * raises ``Stage21ProviderContractError`` (E2121) if any
        element's ``payload`` is not a frozen mapping
        (``MappingProxyType``).

    The helper is the single point where the Stage 21 provider
    contract's element-type and payload-immutability invariants are
    enforced.
    """
    out: list[ProviderRawEvent] = []
    for index, event in enumerate(events):
        if not isinstance(event, ProviderRawEvent):
            raise Stage21ProviderContractError(
                Stage21ErrorCode.E2120,
                detail=(
                    "provider returned a non-ProviderRawEvent element at "
                    f"index {index}: {type(event).__name__}"
                ),
            )
        assert_payload_is_frozen(event)
        out.append(event)
    return tuple(out)


__all__ = [
    "ProviderRawEvent",
    "Stage21Provider",
    "assert_events_immutable",
    "assert_payload_is_frozen",
    "empty_frozen_payload",
    "freeze_payload",
    "make_event",
]
