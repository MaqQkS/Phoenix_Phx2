"""Stage 21 transport contract types.

Stage 21 will eventually dispatch private-preview pings to one or
more operator-controlled targets (Discord webhook / Telegram bot
/ ...). Stage 21.1 ships the contract types only. The concrete
transport adapter is Stage 21.4 scope.

Key invariants:
  * The contract is fakeable. Tests implement ``Stage21Transport``
    against a simple in-memory class to verify the Stage 21
    dispatcher honors the contract -- no network library required.
  * Importing this module triggers no network side effects. The
    Stage 21 import-boundary test asserts no requests / httpx /
    aiohttp / discord / telegram / webhook imports at the top
    level.
  * The contract enforces dispatch safety at the boundary.
    Implementations MUST reject any send when the caller's
    ``safe_for_public_dispatch`` is true. The check is encoded as
    a contract assertion (``assert_transport_dispatch_safety``);
    Stage 21.1 surfaces the helper but does not wire a real
    sender.
"""

from __future__ import annotations

from typing import NamedTuple, Protocol, Tuple

from PHX2.stage21.constants import (
    SAFE_FOR_PUBLIC_DISPATCH,
    Stage21ErrorCode,
)
from PHX2.stage21.errors import Stage21TransportContractError


class TransportPayload(NamedTuple):
    """Typed payload handed to a Stage 21 transport.

    Fields:
      * ``recipient`` -- operator-controlled recipient identifier
        (e.g. webhook URL fingerprint, chat id). Stage 21.1 does
        not enforce a specific shape; the dispatcher MUST validate
        the recipient is present in the configured allowlist
        before constructing a payload.
      * ``body_text`` -- the rendered private-preview message. The
        payload MUST already carry the locked private-preview
        marker tokens (banner / operator-only / do-not-forward) by
        the time the dispatcher hands it to a transport. The
        Stage 21.2 renderer owns marker injection.
      * ``private_preview_marker_present`` -- caller's assertion
        that the marker is present. The transport contract uses
        this field as a defense-in-depth check; the renderer is
        the authoritative source.
      * ``safe_for_public_dispatch`` -- caller's locked dispatch
        flag. Transports MUST refuse to send when this is true.
    """

    recipient: str
    body_text: str
    private_preview_marker_present: bool
    safe_for_public_dispatch: bool


class TransportResult(NamedTuple):
    """Typed return value of a Stage 21 transport send.

    Fields:
      * ``dispatched`` -- True iff the transport actually sent the
        payload. Fake transports flip this True when they record
        the send into their in-memory log; the live transport
        would flip this True only after the upstream API returns
        success. Stage 21.1 ships no live transport.
      * ``rejection_reason`` -- short non-secret string describing
        why ``dispatched`` is False. Empty when ``dispatched`` is
        True.
      * ``recipient`` -- echo of the input recipient so the
        dispatcher can correlate the result back to the payload.
    """

    dispatched: bool
    rejection_reason: str
    recipient: str


class Stage21Transport(Protocol):
    """Stage 21 transport contract.

    Implementations supply a single ``send`` method. Tests
    construct fakes that implement this Protocol directly. The
    fake-transport pattern is the same as the fake-provider
    pattern: a simple class with the right method shape, no
    inheritance required, no network library required.

    Contract semantics:
      * Implementations MUST refuse to send when the payload's
        ``safe_for_public_dispatch`` is true. The contract helper
        ``assert_transport_dispatch_safety`` validates this at
        the boundary and is what tests run against.
      * Implementations MUST refuse to send when the payload's
        ``private_preview_marker_present`` is False. The check is
        belt-and-suspenders: the renderer is the authoritative
        owner of marker presence, but a contract-level guard is
        cheap.
      * Implementations MUST NOT raise on a normal "refused"
        decision; they return a ``TransportResult`` with
        ``dispatched=False``. Hard contract violations -- a
        recipient outside the allowlist, an internal bug -- MAY
        raise ``Stage21TransportContractError``.
    """

    def send(
        self,
        payload: TransportPayload,
    ) -> TransportResult: ...


def assert_transport_dispatch_safety(
    payload: TransportPayload,
) -> Tuple[bool, str]:
    """Validate dispatch safety for a transport payload.

    Returns the tuple ``(allowed, reason)`` where ``allowed`` is
    True only if the payload satisfies every Stage 21 dispatch
    invariant: the dispatch flag must be False (the locked
    Stage 21 invariant in source), and the marker must be present.

    Returns ``(False, "<reason>")`` otherwise; the reason string
    is a short non-secret token suitable for emission into the
    transport result.

    The helper does NOT raise on a "refused" decision. A hard
    contract violation -- such as a malformed payload -- should
    raise ``Stage21TransportContractError`` (E2130) from the
    caller; the helper is the soft-check the contract surface
    runs.
    """
    if not isinstance(payload, TransportPayload):
        raise Stage21TransportContractError(
            Stage21ErrorCode.E2130,
            detail=(
                "assert_transport_dispatch_safety expected "
                "TransportPayload; got "
                f"{type(payload).__name__}"
            ),
        )
    if payload.safe_for_public_dispatch:
        return (False, "safe_for_public_dispatch_true")
    if not payload.private_preview_marker_present:
        return (False, "private_preview_marker_missing")
    # Defensive check against the module-level locked invariant.
    # A drift between the payload flag and the locked constant
    # would indicate the caller flipped the per-payload flag
    # locally; we reject either way.
    if SAFE_FOR_PUBLIC_DISPATCH:
        return (False, "safe_for_public_dispatch_constant_true")
    return (True, "")


__all__ = [
    "Stage21Transport",
    "TransportPayload",
    "TransportResult",
    "assert_transport_dispatch_safety",
]
