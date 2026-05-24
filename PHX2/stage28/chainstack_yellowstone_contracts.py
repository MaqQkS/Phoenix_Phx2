"""Stage 28.10 Chainstack Yellowstone provider client contracts.

Stage 28.10 ships the Protocol contract a future real Chainstack
Yellowstone gRPC client must satisfy, plus a deterministic fake
client for unit tests. No grpc / grpcio / protobuf / generated
``*_pb2.py`` / ``*_pb2_grpc.py`` import lives in this module; the
real provider client (when it lands) will live OUTSIDE Stage
28.10 and only be expected to satisfy the Protocol below.

The Stage 28.10 contracts module imports only stdlib (``typing``)
plus the Stage 28.10 models module. It does NOT import Stage
21-27 production code, does NOT import any network / RPC /
messaging / DB / scheduler / secrets-management library, does
NOT read the process environment, does NOT define a CLI surface,
and contains no top-level I/O.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network. No HTTP. No gRPC. No socket. No file I/O at
    import or call time.
  * No sleep. No backoff execution. No scheduling. No queue. No
    threads. No async. No subprocess.
  * The Stage 28.10 fake client carries a caller-supplied tuple
    of pre-built ``Stage28_10ChainstackYellowstonePayload``
    records; it never opens a connection, never reads a secret,
    never echoes a raw endpoint / token / username / password.
"""

from __future__ import annotations

from typing import (
    Iterable,
    Iterator,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from PHX2.stage28.chainstack_yellowstone_models import (
    Stage28_10ChainstackYellowstoneError,
    Stage28_10ChainstackYellowstonePayload,
)


# ---------------------------------------------------------------------------
# Stage 28.10 client Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage28_10ChainstackYellowstoneClient(Protocol):
    """Stage 28.10 Chainstack Yellowstone client Protocol.

    The future real provider client will satisfy this Protocol so
    Stage 28.10 can drain a bounded number of safe-shape payloads
    without depending on grpc / grpcio / protobuf / generated
    stubs at import time.

    Methods:

      * ``fetch_yellowstone_events(cursor, max_events)`` -- return a
        ``(tuple_of_payloads, next_cursor_or_none)`` pair. The
        implementation MUST honour ``max_events`` exactly. The
        cursor is an optional safe-shape token suitable for
        resumable iteration.
      * ``iter_yellowstone_events(max_events)`` -- yield up to
        ``max_events`` payloads as an iterator. The Stage 28.10
        event source uses this iteration shape internally.

    Both methods MUST raise
    ``Stage28_10ChainstackYellowstoneClientError`` on a recoverable
    upstream failure; non-recoverable / unexpected errors are
    propagated by raising any
    ``Stage28_10ChainstackYellowstoneError`` subclass. The
    Protocol must NEVER raise raw library errors at the Stage
    28.10 boundary.
    """

    def fetch_yellowstone_events(
        self,
        cursor: Optional[str],
        max_events: int,
    ) -> Tuple[
        Tuple[Stage28_10ChainstackYellowstonePayload, ...],
        Optional[str],
    ]:
        ...

    def iter_yellowstone_events(
        self,
        *,
        max_events: int,
    ) -> Iterator[Stage28_10ChainstackYellowstonePayload]:
        ...


# ---------------------------------------------------------------------------
# Stage 28.10 client-specific error
# ---------------------------------------------------------------------------


class Stage28_10ChainstackYellowstoneClientError(
    Stage28_10ChainstackYellowstoneError,
):
    """Raised by a Stage 28.10 Chainstack Yellowstone client for a
    recoverable upstream failure (transport hiccup, decode failure
    on a single payload, etc.). The Stage 28.10 event source
    catches this exception to refuse the offending payload safely
    without crashing the bounded session.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 28.10 Chainstack Yellowstone client error: "
            f"reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Stage 28.10 deterministic fake client
# ---------------------------------------------------------------------------


def _validate_max_events(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Stage28_10ChainstackYellowstoneClientError(
            "MAX_EVENTS_NOT_INT"
        )
    if value <= 0:
        raise Stage28_10ChainstackYellowstoneClientError(
            "MAX_EVENTS_NOT_POSITIVE"
        )
    return value


class Stage28_10ChainstackYellowstoneFakeClient:
    """Deterministic Stage 28.10 fake Chainstack Yellowstone client
    for unit tests.

    The fake yields a caller-supplied tuple of pre-built
    ``Stage28_10ChainstackYellowstonePayload`` records. The fake
    never opens a network connection, never reads the process
    environment, never sleeps, never imports a non-stdlib library,
    and never echoes any endpoint / token / username / password.

    The fake honours ``max_events`` exactly: at most ``max_events``
    payloads are emitted per invocation of ``fetch_yellowstone_events``
    / ``iter_yellowstone_events``. The internal call counter is
    exposed for tests that want to pin that the Stage 28.10 event
    source called the fake exactly the expected number of times.
    """

    def __init__(
        self,
        *,
        payloads: Iterable[Stage28_10ChainstackYellowstonePayload],
    ) -> None:
        validated: list[
            Stage28_10ChainstackYellowstonePayload
        ] = []
        for entry in payloads:
            if not isinstance(
                entry, Stage28_10ChainstackYellowstonePayload,
            ):
                raise Stage28_10ChainstackYellowstoneClientError(
                    "FAKE_PAYLOADS_INCLUDE_NON_PAYLOAD"
                )
            validated.append(entry)
        self._payloads: tuple[
            Stage28_10ChainstackYellowstonePayload, ...
        ] = tuple(validated)
        self._fetch_call_count: int = 0
        self._iter_call_count: int = 0

    @property
    def fetch_call_count(self) -> int:
        """Return the number of times ``fetch_yellowstone_events``
        has been invoked. Pure / deterministic.
        """
        return self._fetch_call_count

    @property
    def iter_call_count(self) -> int:
        """Return the number of times ``iter_yellowstone_events``
        has been invoked. Pure / deterministic.
        """
        return self._iter_call_count

    @property
    def payload_count(self) -> int:
        return len(self._payloads)

    def fetch_yellowstone_events(
        self,
        cursor: Optional[str],
        max_events: int,
    ) -> Tuple[
        Tuple[Stage28_10ChainstackYellowstonePayload, ...],
        Optional[str],
    ]:
        bound = _validate_max_events(max_events)
        if cursor is not None and not isinstance(cursor, str):
            raise Stage28_10ChainstackYellowstoneClientError(
                "CURSOR_NOT_STRING_OR_NONE"
            )
        self._fetch_call_count += 1
        slice_payloads = self._payloads[:bound]
        # The fake does not implement real cursor pagination; the
        # next-cursor sentinel is always ``None`` so the caller
        # treats the bounded pull as terminal.
        return slice_payloads, None

    def iter_yellowstone_events(
        self,
        *,
        max_events: int,
    ) -> Iterator[Stage28_10ChainstackYellowstonePayload]:
        bound = _validate_max_events(max_events)
        self._iter_call_count += 1
        for index, payload in enumerate(self._payloads):
            if index >= bound:
                return
            yield payload


# ---------------------------------------------------------------------------
# Stage 28.10 deterministic raising fake client (test helper)
# ---------------------------------------------------------------------------


class Stage28_10ChainstackYellowstoneRaisingFakeClient:
    """Deterministic Stage 28.10 fake client that raises a typed
    ``Stage28_10ChainstackYellowstoneClientError`` on every call.

    Used by Stage 28.10 event-source tests to pin the typed-error
    propagation path.
    """

    def __init__(self, *, reason: str = "FAKE_REASON") -> None:
        if not isinstance(reason, str) or reason == "":
            raise Stage28_10ChainstackYellowstoneClientError(
                "RAISING_FAKE_REASON_EMPTY"
            )
        self._reason: str = reason

    @property
    def reason(self) -> str:
        return self._reason

    def fetch_yellowstone_events(
        self,
        cursor: Optional[str],
        max_events: int,
    ) -> Tuple[
        Tuple[Stage28_10ChainstackYellowstonePayload, ...],
        Optional[str],
    ]:
        raise Stage28_10ChainstackYellowstoneClientError(
            self._reason
        )

    def iter_yellowstone_events(
        self,
        *,
        max_events: int,
    ) -> Iterator[Stage28_10ChainstackYellowstonePayload]:
        raise Stage28_10ChainstackYellowstoneClientError(
            self._reason
        )


__all__ = (
    "Stage28_10ChainstackYellowstoneClient",
    "Stage28_10ChainstackYellowstoneClientError",
    "Stage28_10ChainstackYellowstoneFakeClient",
    "Stage28_10ChainstackYellowstoneRaisingFakeClient",
)
