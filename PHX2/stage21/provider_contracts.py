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

from typing import Mapping, NamedTuple, Protocol, Sequence, Tuple

from PHX2.stage21.constants import Stage21ErrorCode
from PHX2.stage21.errors import Stage21ProviderContractError


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


def assert_events_immutable(
    events: Sequence[ProviderRawEvent],
) -> Tuple[ProviderRawEvent, ...]:
    """Validate and freeze a provider's ``fetch_events`` return value.

    Stage 21.1 calls this helper from the fake provider used in
    the contract test. The helper:
      * coerces the input to a ``tuple`` of ``ProviderRawEvent``;
      * raises ``Stage21ProviderContractError`` (E2120) if any
        element is not a ``ProviderRawEvent``.

    The helper is the single point where the Stage 21 provider
    contract's element-type invariant is enforced.
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
        out.append(event)
    return tuple(out)


__all__ = [
    "ProviderRawEvent",
    "Stage21Provider",
    "assert_events_immutable",
]
