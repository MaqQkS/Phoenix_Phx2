"""Stage 21.2 fake-only event provider.

``Stage21FakeProvider`` emits deterministic Stage-21-owned fake
events for use by the local fake private live-path simulator.

Hard scope:

  * Fake-only. Never reads the environment. Never opens a
    network connection. Never requires credentials or a webhook
    target. Never depends on any Phoenix1 / Stage 17..20 runtime
    module.
  * Stage-21-owned. The provider name embedded in every emitted
    fake event is ``STAGE21_FAKE_PROVIDER_NAME``; the chain is
    ``STAGE21_FAKE_CHAIN_NAME``. Real provider adapters land in
    a later Stage 21 sub-stage with their own design lock.
  * Deterministic. Given the same seed input the provider
    re-emits the same fake events in the same order with the
    same per-event ids and the same per-event hashes. This is
    the property the simulator depends on for byte-identical
    artifact reruns.
  * Must not become the base live provider. The fake provider is
    explicitly fake-only; the boundary tests assert no live
    adapter (Stage 21.3+) imports from this module.

The fake provider exposes a ``fetch_events`` method that
satisfies the Stage 21.1 ``Stage21Provider`` Protocol shape but
returns Stage-21-owned fake records. The simulator builds its
input by calling ``fetch_events`` directly; it does not consume
any external feed.
"""

from __future__ import annotations

import hashlib
from typing import NamedTuple, Mapping, Sequence, Tuple

from PHX2.stage21 import safe_content as _sc
from PHX2.stage21.constants import Stage21ErrorCode
from PHX2.stage21.errors import Stage21TelemetryError
from PHX2.stage21.normalized_events import STAGE21_2_NORMALIZED_EVENT_TYPES
from PHX2.stage21.ping_payloads import (
    STAGE21_FAKE_CHAIN_NAME,
    STAGE21_FAKE_PROVIDER_NAME,
    STAGE21_FAKE_SOURCE_KIND,
)


# ---------------------------------------------------------------------------
# Fake-only marker
# ---------------------------------------------------------------------------
#
# A Stage-21-owned marker constant. The class also exposes the
# same marker as an attribute so static checks (boundary tests)
# can assert any class with ``IS_FAKE_ONLY = True`` is
# Stage-21-owned fake material and not a live runtime.


STAGE21_FAKE_ONLY_MARKER: bool = True


# ---------------------------------------------------------------------------
# Fake event record
# ---------------------------------------------------------------------------


class Stage21FakeEvent(NamedTuple):
    """Stage-21-owned fake event emitted by ``Stage21FakeProvider``.

    Carries only Stage-21-owned non-secret fields. The raw_payload
    mapping is intentionally small and free of any URL / secret
    material so the downstream normalizer's secret-leak guards
    never fire on a clean run.
    """

    provider_event_id: str
    provider_name: str
    source_kind: str
    chain: str
    mint: str
    event_type: str
    observed_at_utc: str
    slot: int
    signature: str
    raw_payload: Mapping[str, object]


# ---------------------------------------------------------------------------
# Deterministic seed input
# ---------------------------------------------------------------------------


class Stage21FakeEventSeed(NamedTuple):
    """Deterministic seed material for one Stage 21.2 fake event.

    The seed is what callers (the simulator and the tests) hand
    to the fake provider. The provider derives all per-event
    fields (id, signature, slot offset) from the seed material so
    two calls with identical seeds produce identical events.
    """

    mint: str
    event_type: str
    observed_at_utc: str
    slot: int
    raw_payload: Mapping[str, object]


def _validate_seed(seed: object, *, index: int) -> Stage21FakeEventSeed:
    """Validate a seed entry; raise ``Stage21TelemetryError`` on miss."""
    if not isinstance(seed, Stage21FakeEventSeed):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                f"Stage21FakeProvider seed at index {index} must be a "
                "Stage21FakeEventSeed"
            ),
        )
    if not isinstance(seed.mint, str) or seed.mint == "":
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                f"Stage21FakeProvider seed at index {index} has empty mint"
            ),
        )
    if seed.event_type not in STAGE21_2_NORMALIZED_EVENT_TYPES:
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                f"Stage21FakeProvider seed at index {index} has "
                "event_type outside the locked Stage 21.2 vocabulary"
            ),
        )
    if not isinstance(seed.observed_at_utc, str) or seed.observed_at_utc == "":
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                f"Stage21FakeProvider seed at index {index} has empty "
                "observed_at_utc"
            ),
        )
    if (
        isinstance(seed.slot, bool)
        or not isinstance(seed.slot, int)
        or seed.slot < 0
    ):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                f"Stage21FakeProvider seed at index {index} has invalid slot"
            ),
        )
    if not isinstance(seed.raw_payload, Mapping):
        raise Stage21TelemetryError(
            Stage21ErrorCode.E2113,
            detail=(
                f"Stage21FakeProvider seed at index {index} raw_payload must "
                "be a Mapping"
            ),
        )
    # Stage 21.2 remediation (R11a): apply the shared safe_content
    # predicate to every seed string field plus the raw_payload
    # dict. The existing E2113 checks above stay in place; the
    # safe_content layer adds the locked R4 forbidden-substring /
    # char-set / control-char / length predicates on top, raising
    # Stage21Error E2150..E2158 on violation. This is the boundary
    # the Codex PoC for a URL-laced mint enters before any fake
    # event is emitted.
    _sc.validate_safe_string(
        seed.mint,
        kind=_sc.SafeStringKind.SHORT_LABEL,
        field_name=f"seed[{index}].mint",
    )
    _sc.validate_safe_string(
        seed.event_type,
        kind=_sc.SafeStringKind.SHORT_LABEL,
        field_name=f"seed[{index}].event_type",
    )
    _sc.validate_timestamp_value(
        seed.observed_at_utc,
        field_name=f"seed[{index}].observed_at_utc",
    )
    _sc.validate_safe_payload_dict(
        seed.raw_payload,
        field_name=f"seed[{index}].raw_payload",
    )
    return seed


def _derive_fake_provider_event_id(seed: Stage21FakeEventSeed, index: int) -> str:
    """Return a deterministic provider-side id for one seed entry.

    The id is sha256-derived from the seed material plus the seed
    index. Repeated calls with identical inputs return identical
    ids.
    """
    material = (
        f"{STAGE21_FAKE_PROVIDER_NAME}|"
        f"{index}|"
        f"{seed.mint}|"
        f"{seed.event_type}|"
        f"{seed.slot}|"
        f"{seed.observed_at_utc}|"
        f"{repr(sorted((str(k), repr(v)) for k, v in seed.raw_payload.items()))}"
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return "fake_pev_" + digest[:16]


def _derive_fake_signature(seed: Stage21FakeEventSeed, index: int) -> str:
    """Return a deterministic Stage-21-owned fake signature.

    Stage-21-owned fake signatures are stable strings derived from
    the seed. They are never real chain signatures and never
    indicate any on-chain state.
    """
    material = (
        f"sig|{STAGE21_FAKE_PROVIDER_NAME}|{index}|"
        f"{seed.mint}|{seed.slot}|{seed.observed_at_utc}"
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return "fake_sig_" + digest[:32]


# ---------------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------------


class Stage21FakeProvider:
    """Stage 21.2 fake-only event provider.

    Construct with a sequence of ``Stage21FakeEventSeed`` records.
    ``fetch_events`` returns the deterministically derived fake
    events in seed order.

    Stage-21-owned invariants:
      * The provider name on every event is
        ``STAGE21_FAKE_PROVIDER_NAME``.
      * The chain on every event is ``STAGE21_FAKE_CHAIN_NAME``.
      * The source kind on every event is
        ``STAGE21_FAKE_SOURCE_KIND``.
      * The provider never touches the environment, the network,
        the filesystem, a webhook target, or any credential
        material.

    The class exposes the ``IS_FAKE_ONLY`` boolean attribute so
    the Stage 21 boundary tests can assert any use of this
    provider is fake-only.
    """

    IS_FAKE_ONLY: bool = STAGE21_FAKE_ONLY_MARKER

    def __init__(self, seeds: Sequence[Stage21FakeEventSeed]) -> None:
        if not isinstance(seeds, (list, tuple)):
            raise Stage21TelemetryError(
                Stage21ErrorCode.E2113,
                detail=(
                    "Stage21FakeProvider seeds must be a list or tuple of "
                    "Stage21FakeEventSeed"
                ),
            )
        validated: list[Stage21FakeEventSeed] = []
        for index, seed in enumerate(seeds):
            validated.append(_validate_seed(seed, index=index))
        self._seeds: tuple[Stage21FakeEventSeed, ...] = tuple(validated)

    @property
    def seed_count(self) -> int:
        return len(self._seeds)

    def fetch_events(
        self,
        *,
        cursor: object = None,
        max_events: int = 0,
    ) -> Tuple[Stage21FakeEvent, ...]:
        """Return the deterministic fake events derived from the seeds.

        Stage 21.2 ignores ``cursor`` -- the seed list is the
        cursor. ``max_events == 0`` means "return all seeds". A
        positive ``max_events`` truncates the prefix.

        The method is pure: identical seeds produce identical
        events on every call.
        """
        events: list[Stage21FakeEvent] = []
        for index, seed in enumerate(self._seeds):
            if max_events and index >= max_events:
                break
            provider_event_id = _derive_fake_provider_event_id(seed, index)
            signature = _derive_fake_signature(seed, index)
            # Stage 21.2 remediation (R11a): defense-in-depth
            # validation of the derived fake-event identifier
            # fields before the event leaves the provider. The
            # derivation helpers above are pure sha256-hex shapes
            # but the explicit check pins the contract so a
            # future change to the helpers cannot silently emit
            # an unsafe id without tripping the predicate.
            _sc.validate_safe_string(
                provider_event_id,
                kind=_sc.SafeStringKind.SHORT_IDENTIFIER,
                field_name=f"fake_event[{index}].provider_event_id",
            )
            _sc.validate_safe_string(
                signature,
                kind=_sc.SafeStringKind.SHORT_LABEL,
                field_name=f"fake_event[{index}].signature",
            )
            events.append(
                Stage21FakeEvent(
                    provider_event_id=provider_event_id,
                    provider_name=STAGE21_FAKE_PROVIDER_NAME,
                    source_kind=STAGE21_FAKE_SOURCE_KIND,
                    chain=STAGE21_FAKE_CHAIN_NAME,
                    mint=seed.mint,
                    event_type=seed.event_type,
                    observed_at_utc=seed.observed_at_utc,
                    slot=seed.slot,
                    signature=signature,
                    raw_payload=seed.raw_payload,
                )
            )
        return tuple(events)


__all__ = [
    "STAGE21_FAKE_ONLY_MARKER",
    "Stage21FakeEvent",
    "Stage21FakeEventSeed",
    "Stage21FakeProvider",
]
