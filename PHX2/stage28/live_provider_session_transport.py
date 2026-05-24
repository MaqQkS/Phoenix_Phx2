"""Stage 28.9 private live provider session transport wrapper.

Stage 28.9 ships a thin redaction-safe transport wrapper that lets
the Stage 28.6 bounded private session runner call the Stage 28.4
audited private Discord HTTP transport over a caller-supplied
private webhook URL WITHOUT ever placing the URL on a Stage 28.6
candidate event or on any persisted record.

The Stage 28.6 runner protocol
(``Stage28_6PrivateTransport``) accepts only
``webhook_identity`` + ``payload`` keyword arguments. The Stage
28.4 audited transport accepts
``webhook_url`` + ``webhook_identity`` + ``payload``. The Stage
28.9 wrapper binds the URL inside its instance and forwards
exactly one Stage 28.4 call per ``send_one_audited_post(...)``
invocation; the URL is never echoed on ``repr()`` / ``str()`` /
any returned result. The wrapper does NOT instantiate a real
Stage 28.4 audited transport itself; the caller supplies one
(either the real ``Stage28_4AuditedHttpTransport`` after
operator-authorized readiness, or a fake transport in tests).

Stage 28.9 transport wrapping discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No direct network library import. The wrapper accepts the
    Stage 28.4 transport via the
    ``Stage28_9AuditedTransport`` Protocol; the actual
    ``urllib`` / SSL access lives inside the Stage 28.4
    transport implementation in
    ``audited_http_transport.py``.
  * No sleep. No backoff execution. No scheduling. No queue. No
    threads. No async. No subprocess.
  * The webhook URL is bound at construction time, stored as a
    private attribute, and NEVER copied onto any returned
    record, exception message, ``repr()``, or ``str()``.
  * Exactly one call to the injected audited transport per
    ``send_one_audited_post(...)`` invocation; no retries / no
    batching.
  * The returned ``Stage28_4TransportResult`` is forwarded
    verbatim so the Stage 28.6 runner sees the same closed-set
    shape it sees from the Stage 28.6 fake transport.

Stage 28.9 ships NO Stage 29 enforcement, NO approval /
activation semantics, NO public routing, NO subscriber routing,
NO paid tier routing, NO Telegram, NO X / social, NO automated
trading, NO wallet / private-key / signer logic, NO position
sizing, NO trade execution, NO dashboard / HTTP control server,
NO daemon / systemd / watchdog / autorestart service.

This module imports only stdlib (``typing``) plus the Stage 28.4
transport models module (for the result-record type re-use and
the safe-identity label). It does NOT import Stage 21-27
production code, does NOT import any network / RPC / messaging /
DB / scheduler / secrets-management library at the top level,
and contains no top-level I/O.
"""

from __future__ import annotations

from typing import (
    Any,
    Mapping,
    Protocol,
    runtime_checkable,
)

from PHX2.stage28.audited_http_transport_models import (
    Stage28_4TransportResult,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    is_safe_webhook_identity_label,
)
from PHX2.stage28.live_provider_session_models import (
    STAGE28_9_REDACTION_TOKEN,
    Stage28_9LiveProviderSessionError,
)


# ---------------------------------------------------------------------------
# Stage 28.9 transport wrapper exception
# ---------------------------------------------------------------------------


class Stage28_9TransportWrapperError(
    Stage28_9LiveProviderSessionError,
):
    """Raised when the Stage 28.9 transport wrapper rejects a
    construction-time argument (missing / non-string URL,
    audited transport without the required method).

    Carries only the canonical field name + a closed-set reason
    token; never the raw rejected value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.9 transport wrapper rejected argument: "
            f"field={field_name!r} reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Stage28_9AuditedTransport Protocol (Stage 28.4-shaped duck type)
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage28_9AuditedTransport(Protocol):
    """Stage 28.9 audited-transport protocol.

    The wrapper expects exactly one method:
    ``send_one_audited_post`` with the Stage 28.4-shaped keyword
    arguments. The real ``Stage28_4AuditedHttpTransport`` (in
    ``audited_http_transport.py``) satisfies this protocol; a
    fake test transport may also satisfy it without inheriting.

    Implementations MUST:

      * accept ``webhook_url`` / ``webhook_identity`` /
        ``payload`` keyword arguments,
      * return a ``Stage28_4TransportResult``,
      * NEVER sleep, schedule, retry, or batch,
      * NEVER expose the raw webhook URL on records / exceptions /
        repr / str / public dicts.
    """

    def send_one_audited_post(
        self,
        *,
        webhook_url: str,
        webhook_identity: str,
        payload: Mapping[str, Any],
    ) -> Stage28_4TransportResult:
        ...


# ---------------------------------------------------------------------------
# Stage 28.9 non-empty webhook URL gate
# ---------------------------------------------------------------------------


def is_nonempty_private_webhook_url(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty string of
    bounded length.

    Stage 28.9 deliberately delegates deep URL validation (the
    locked Discord https + host allowlist + regex) to the Stage
    28.4 audited transport. The Stage 28.9 wrapper only enforces
    the cheap up-front non-empty / bounded-length / no-control-
    characters gate so an obviously bogus URL is rejected before
    the wrapper is built. Pure / deterministic.
    """
    if not isinstance(value, str):
        return False
    if value == "":
        return False
    if len(value) > 512:
        return False
    for ch in value:
        cp = ord(ch)
        if cp < 0x21 or cp == 0x7F:
            return False
    return True


# ---------------------------------------------------------------------------
# Stage 28.9 private webhook transport wrapper
# ---------------------------------------------------------------------------


class Stage28_9PrivateWebhookTransport:
    """Stage 28.9 redaction-safe private webhook transport
    wrapper.

    Construction-time arguments:

      * ``audited_transport`` -- a Stage 28.4-shaped audited
                                  transport (the real
                                  ``Stage28_4AuditedHttpTransport``
                                  for live private operator-only
                                  sends; a fake recording
                                  transport in tests).
      * ``webhook_url``       -- the private operator-only
                                  Discord webhook URL. Bound at
                                  construction time, stored as a
                                  private attribute, NEVER
                                  echoed on any returned record /
                                  exception message / ``repr()`` /
                                  ``str()``.
      * ``webhook_identity``  -- safe-to-display webhook identity
                                  label (defaults to
                                  ``WEBHOOK_IDENTITY_PRIVATE_OPERATOR``).
                                  The label is echoed on the
                                  Stage 28.4 transport result; the
                                  raw URL is not.

    Runtime guarantees:

      * exactly one call to the injected audited transport per
        ``send_one_audited_post(...)`` invocation;
      * the webhook URL is bound once and never re-validated by
        the wrapper between calls (the audited transport
        re-validates on every call);
      * the returned ``Stage28_4TransportResult`` is forwarded
        verbatim;
      * ``repr()`` / ``str()`` of the wrapper carry only the
        redaction token + the safe webhook identity label.
    """

    def __init__(
        self,
        *,
        audited_transport: Stage28_9AuditedTransport,
        webhook_url: str,
        webhook_identity: str = WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    ) -> None:
        if not hasattr(audited_transport, "send_one_audited_post"):
            raise Stage28_9TransportWrapperError(
                field_name="audited_transport",
                reason="MISSING_SEND_ONE_AUDITED_POST_METHOD",
            )
        if not is_nonempty_private_webhook_url(webhook_url):
            raise Stage28_9TransportWrapperError(
                field_name="webhook_url",
                reason="WEBHOOK_URL_EMPTY_OR_UNSAFE_SHAPE",
            )
        if not is_safe_webhook_identity_label(webhook_identity):
            raise Stage28_9TransportWrapperError(
                field_name="webhook_identity",
                reason="WEBHOOK_IDENTITY_UNSAFE_SHAPE",
            )
        self._audited_transport: Stage28_9AuditedTransport = (
            audited_transport
        )
        # Stored as a private attribute. NEVER copied onto a
        # returned record, exception message, repr, str, or any
        # public dict.
        self._webhook_url: str = webhook_url
        self._webhook_identity: str = webhook_identity
        self._calls_forwarded: int = 0

    @property
    def calls_forwarded(self) -> int:
        """Return the count of Stage 28.4 audited-transport calls
        forwarded by this wrapper. Pure / deterministic.
        """
        return self._calls_forwarded

    @property
    def bound_webhook_identity(self) -> str:
        """Return the safe-to-display webhook identity label bound
        at construction time. Pure / deterministic; safe to log.
        """
        return self._webhook_identity

    def send_one_audited_post(
        self,
        *,
        webhook_identity: str,
        payload: Mapping[str, Any],
    ) -> Stage28_4TransportResult:
        """Forward exactly one Stage 28.4 audited HTTP POST
        through the bound audited transport.

        The Stage 28.9 wrapper signature matches the Stage 28.6
        ``Stage28_6PrivateTransport`` protocol (no ``webhook_url``
        keyword); the URL is supplied from the wrapper's private
        attribute.

        Pure forwarding: no retries, no batching, no sleep, no
        scheduling. The wrapper increments its forwarded-call
        counter once per invocation.
        """
        self._calls_forwarded += 1
        return self._audited_transport.send_one_audited_post(
            webhook_url=self._webhook_url,
            webhook_identity=webhook_identity,
            payload=payload,
        )

    def __repr__(self) -> str:
        return (
            f"Stage28_9PrivateWebhookTransport("
            f"webhook_url={STAGE28_9_REDACTION_TOKEN!r}, "
            f"webhook_identity={self._webhook_identity!r}, "
            f"calls_forwarded={self._calls_forwarded!r})"
        )

    __str__ = __repr__


# ---------------------------------------------------------------------------
# Stage 28.9 recording fake audited transport (test helper)
# ---------------------------------------------------------------------------


class Stage28_9RecordingFakeAuditedTransport:
    """Deterministic Stage 28.9 fake audited transport used to
    test the ``Stage28_9PrivateWebhookTransport`` wrapper.

    The fake records each ``send_one_audited_post(...)`` call
    (including the wrapper-supplied URL) so the wrapper-level
    tests can assert exactly one Stage 28.4 call was forwarded
    with the bound URL. The fake itself is module-local; it is
    NOT exposed as a Stage 28.6 candidate transport (the Stage
    28.6 fake transport in ``session_runner_models.py`` is the
    canonical Stage 28.6-shape fake).

    The fake never opens a network connection, never reads the
    process environment, never sleeps, never retries, and never
    imports a non-stdlib library.
    """

    def __init__(
        self,
        *,
        scripted_result: Stage28_4TransportResult,
    ) -> None:
        if not isinstance(scripted_result, Stage28_4TransportResult):
            raise Stage28_9TransportWrapperError(
                field_name="scripted_result",
                reason="SCRIPTED_RESULT_NOT_STAGE28_4_RESULT",
            )
        self._scripted_result: Stage28_4TransportResult = (
            scripted_result
        )
        self._calls: list[dict] = []

    @property
    def calls(self) -> tuple[dict, ...]:
        """Return the recorded ``send_one_audited_post(...)``
        calls in invocation order. Each entry contains the
        wrapper-supplied URL + identity + payload copy.
        """
        return tuple(self._calls)

    @property
    def call_count(self) -> int:
        return len(self._calls)

    def send_one_audited_post(
        self,
        *,
        webhook_url: str,
        webhook_identity: str,
        payload: Mapping[str, Any],
    ) -> Stage28_4TransportResult:
        if isinstance(payload, dict):
            recorded_payload: dict = dict(payload)
        else:
            recorded_payload = {}
        self._calls.append(
            {
                "webhook_url": webhook_url,
                "webhook_identity": webhook_identity,
                "payload": recorded_payload,
            }
        )
        return self._scripted_result


__all__ = (
    "Stage28_9TransportWrapperError",
    "Stage28_9AuditedTransport",
    "is_nonempty_private_webhook_url",
    "Stage28_9PrivateWebhookTransport",
    "Stage28_9RecordingFakeAuditedTransport",
)
