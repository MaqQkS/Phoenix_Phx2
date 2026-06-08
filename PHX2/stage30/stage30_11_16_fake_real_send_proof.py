"""Stage 30.11.16 fake real-send guard proof + recording fake transport.

Offline only. A thin, deterministic driver for the committed Stage 30.11.16 real
private transport guard, plus the Stage 30.11.16 recording FAKE private transport
the proof + tests inject in place of a real audited transport. It proves that a
valid authorization + a genuine deduped ``NO_SEND_DISPATCHED`` compose result
forward EXACTLY ONE recorded would-send through the FAKE transport -- with NO
real opener, NO network, NO env read, and NO Stage 28 import.

The recording FAKE is the Stage 28.9 wrapper SHAPE
(``send_one_audited_post(*, webhook_identity, payload)``) but records the call
and returns an in-memory scripted verdict exposing ``ok`` / ``transport_status``
/ ``send_attempt_count``; it opens NO socket, reads NO env, imports NO Stage 28
module, and carries NO url. A real audited transport is injected ONLY at the
separate, explicitly operator-authorized one-send ceremony this proof does NOT
run.

The deduped compose result is INJECTED (the test builds it from the committed
Stage 30.11.13 / 30.11.15 result types), so this committed proof imports neither
the composer nor a provider fake and stays inside the closed Stage 30 dependency
boundary.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports ONLY the Stage 30.11.16 models + guard siblings. No Stage 21-29
    import; in particular NO Stage 28 transport import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket; no url.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No PHX1 import. No ``time`` / ``datetime`` import; timestamps are
    caller-injected.
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

from PHX2.stage30.stage30_11_16_real_send_models import (
    STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN,
    Stage30_11_16RealSendAuthorization,
    Stage30_11_16RealSendResult,
)
from PHX2.stage30.stage30_11_16_real_private_transport_guard import (
    Stage30_11_16RealPrivateTransportGuard,
    make_stage30_11_16_real_private_transport_guard,
)


# Safe default provenance tokens for the proof's authorization sentinel (safe
# operator tokens; provenance only -- never a secret).
PROOF_OPERATOR_LABEL: str = "OPERATOR_CONTROLLED_CEREMONY"
PROOF_AUTHORIZATION_REASON: str = "STAGE_30_11_16_CONTROLLED_ONE_SEND"
PROOF_CREATED_AT: str = "2026-06-07T07:06:40Z"

# The fake transport's default scripted verdict tokens (safe display tokens that
# mirror the audited transport's success vocabulary BY VALUE; never a real send).
PROOF_FAKE_SENT_STATUS: str = "SENT_OK"


# ---------------------------------------------------------------------------
# Recording fake private transport (the Stage 28.9 wrapper SHAPE; no network)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_16FakeTransportVerdict:
    """The in-memory verdict the recording fake returns.

    Mirrors the audited transport result's safe fields the guard reads
    duck-typed (``ok`` / ``transport_status``) plus a ``send_attempt_count``;
    carries NO url, NO body, NO secret. NEVER a real send.
    """

    ok: bool
    transport_status: str
    send_attempt_count: int


class Stage30_11_16RecordingFakePrivateTransport:
    """Deterministic Stage 30.11.16 recording fake private transport.

    The Stage 28.9 wrapper SHAPE (``send_one_audited_post(*, webhook_identity,
    payload)``). It records each call (the identity + a copy of the payload) so a
    test can assert EXACTLY ONE would-send was forwarded with EXACTLY the
    ``{"content": body}`` payload, and returns a scripted
    ``Stage30_11_16FakeTransportVerdict``. With ``raise_on_send=True`` it records
    the call THEN raises (to exercise the guard's fail-closed
    ``TRANSPORT_EXCEPTION`` path). It opens NO network connection, reads NO env,
    imports NO Stage 28 module, and carries NO url.
    """

    def __init__(
        self,
        *,
        scripted_ok: bool = True,
        scripted_transport_status: str = PROOF_FAKE_SENT_STATUS,
        raise_on_send: bool = False,
    ) -> None:
        self._scripted_ok: bool = scripted_ok
        self._scripted_transport_status: str = scripted_transport_status
        self._raise_on_send: bool = raise_on_send
        self._calls: list[dict] = []

    @property
    def calls(self) -> Tuple[dict, ...]:
        """The recorded ``send_one_audited_post`` calls in invocation order.

        Each entry carries the wrapper-supplied ``webhook_identity`` + a copy of
        the payload (the guard always forwards exactly ``{"content": body}``).
        """
        return tuple(self._calls)

    @property
    def call_count(self) -> int:
        """The number of recorded ``send_one_audited_post`` calls."""
        return len(self._calls)

    def send_one_audited_post(
        self, *, webhook_identity: str, payload: Mapping[str, Any]
    ) -> Stage30_11_16FakeTransportVerdict:
        recorded_payload = dict(payload) if isinstance(payload, dict) else {}
        self._calls.append(
            {
                "webhook_identity": webhook_identity,
                "payload": recorded_payload,
            }
        )
        if self._raise_on_send:
            raise RuntimeError("stage 30.11.16 fake transport scripted failure")
        return Stage30_11_16FakeTransportVerdict(
            ok=self._scripted_ok,
            transport_status=self._scripted_transport_status,
            send_attempt_count=1,
        )


# ---------------------------------------------------------------------------
# Default authorization sentinel
# ---------------------------------------------------------------------------


def default_real_send_authorization(
    *,
    created_at_utc: str = PROOF_CREATED_AT,
    operator_label: str = PROOF_OPERATOR_LABEL,
    authorization_reason: str = PROOF_AUTHORIZATION_REASON,
) -> Stage30_11_16RealSendAuthorization:
    """Build a VALID operator authorization sentinel (the locked confirm token +
    safe operator provenance tokens + a caller-injected timestamp). Pure.
    """
    return Stage30_11_16RealSendAuthorization(
        authorized=True,
        confirm_token=STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN,
        operator_label=operator_label,
        authorization_reason=authorization_reason,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Fake proof driver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_16FakeRealSendProofResult:
    """The guard result + the recording fake transport + the guard instance, so a
    test can assert exactly one would-send was recorded with NO real send.
    """

    result: Stage30_11_16RealSendResult
    transport: Stage30_11_16RecordingFakePrivateTransport
    guard: Stage30_11_16RealPrivateTransportGuard


def run_stage30_11_16_fake_real_send_proof(
    *,
    deduped_result: Any,
    authorization: Optional[Stage30_11_16RealSendAuthorization] = None,
    transport: Optional[Stage30_11_16RecordingFakePrivateTransport] = None,
    created_at_utc: str = PROOF_CREATED_AT,
) -> Stage30_11_16FakeRealSendProofResult:
    """Drive the committed Stage 30.11.16 guard over an INJECTED deduped compose
    result with a VALID authorization sentinel + a recording FAKE transport;
    return ``(result, transport, guard)``.

    The default authorization is the valid proof sentinel and the default
    transport is a recording FAKE -- so a genuine ``NO_SEND_DISPATCHED`` deduped
    result forwards EXACTLY ONE recorded would-send (a RECORDED would-send, NEVER
    a real send). Reads no env, opens no network, builds no real opener.
    """
    effective_authorization = (
        default_real_send_authorization(created_at_utc=created_at_utc)
        if authorization is None
        else authorization
    )
    effective_transport = (
        Stage30_11_16RecordingFakePrivateTransport()
        if transport is None
        else transport
    )
    guard = make_stage30_11_16_real_private_transport_guard(
        transport=effective_transport
    )
    result = guard.authorize_and_dispatch(
        deduped_result,
        authorization=effective_authorization,
        created_at_utc=created_at_utc,
    )
    return Stage30_11_16FakeRealSendProofResult(
        result=result,
        transport=effective_transport,
        guard=guard,
    )


__all__ = (
    "PROOF_OPERATOR_LABEL",
    "PROOF_AUTHORIZATION_REASON",
    "PROOF_CREATED_AT",
    "PROOF_FAKE_SENT_STATUS",
    "Stage30_11_16FakeTransportVerdict",
    "Stage30_11_16RecordingFakePrivateTransport",
    "default_real_send_authorization",
    "Stage30_11_16FakeRealSendProofResult",
    "run_stage30_11_16_fake_real_send_proof",
)
