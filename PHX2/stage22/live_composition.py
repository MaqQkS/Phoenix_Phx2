"""Stage 22.5 live composition module.

The single Stage 22 production seam permitted to import Stage 21
modules. Provides the adapters that wire Stage 21 helius /
decoder / Discord / readiness pieces into Stage 22 runner
dependencies:

  * ``build_live_readiness_check_fn`` -- returns a zero-arg
    callable that evaluates the Stage 21.3A readiness gate
    against a caller-supplied env mapping snapshot.
  * ``build_live_fetch_outcome_fn`` -- returns a one-arg callable
    (``attempt_index -> ProviderFetchOutcome``) that wraps the
    Stage 21.3B Helius provider adapter and maps adapter
    exceptions onto sanitized Stage 22 ``status_class`` /
    ``upstream_error_type`` tokens.
  * ``classify_stage21_decode_exception`` -- maps the Stage 21.3A
    decoder ``ProviderPayloadError`` subclass family onto the
    Stage 22.1 ``MALFORMED_EVENT_REASONS`` closed set.
  * ``build_private_ping_body`` -- pure helper that renders a
    bounded, secret-free Stage 22 private ping body text from an
    ``IngestEventEnvelope``. Rejects any candidate body that
    exceeds the locked length cap or that contains a forbidden
    URL / secret-bearing substring.
  * ``Stage22DiscordPrivateTransportAdapter`` -- adapts a Stage
    21.3C ``DiscordPrivateTransport`` plus a fixed recipient
    into the Stage 22.5 ``Stage22PrivateTransport`` Protocol.

This module does NOT define a CLI surface, does NOT read
``os.environ`` / ``os.getenv`` (the caller supplies the env
mapping), does NOT open files / sockets / network connections,
does NOT import any Phoenix1 or PHX2 runtime-layer module,
does NOT route into any non-private sink (the Stage 22
forbidden-routing token tuple is locked in ``constants.py``),
and does NOT execute any retry / backoff / sleep / dedupe /
capture logic of its own. Those concerns live in the Stage
22.5 bounded runner and in the Stage 22.2 / 22.3 / 22.4
helpers already shipped.

Stage 21 imports allowed here ONLY (locked):

  * PHX2.stage21.live_secrets_boundary
  * PHX2.stage21.provider_adapter_helius
  * PHX2.stage21.provider_event_decoder
  * PHX2.stage21.discord_private_transport
  * PHX2.stage21.transport_contracts
  * PHX2.stage21.allowlist
  * PHX2.stage21.secret_redaction

The bounded private ingest runner (``bounded_live_runner.py``)
imports NOTHING from Stage 21. The Stage 21 dependency surface
fans through this module only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Callable

from PHX2.stage21.discord_private_transport import (
    DiscordPrivateTransport,
)
from PHX2.stage21.live_secrets_boundary import (
    Stage21LiveReadinessConfig,
    evaluate_live_readiness,
    load_live_readiness_config_from_env,
)
from PHX2.stage21.provider_adapter_helius import (
    HeliusClientFetchError,
    HeliusClientResponseFieldTypeError,
    HeliusClientResponseFieldValueError,
    HeliusClientResponseShapeError,
    HeliusProviderAdapter,
)
from PHX2.stage21.provider_event_decoder import (
    ProviderPayloadFieldTypeError,
    ProviderPayloadFieldValueError,
    ProviderPayloadShapeError,
    ProviderPayloadSuspiciousContentError,
    ProviderPayloadUnsupportedInstructionError,
    decode_provider_event,
)
from PHX2.stage21.transport_contracts import TransportPayload

from PHX2.stage22.constants import (
    CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS,
    CAPTURE_FORBIDDEN_URL_SUBSTRINGS,
    MALFORMED_REASON_FIELD_TYPE_ERROR,
    MALFORMED_REASON_FIELD_VALUE_ERROR,
    MALFORMED_REASON_SHAPE_ERROR,
    MALFORMED_REASON_SUSPICIOUS_CONTENT,
    MALFORMED_REASON_UNEXPECTED_ERROR,
    MALFORMED_REASON_UNSUPPORTED_INSTRUCTION,
    STAGE22_PRIVATE_PING_BODY_MAX_LEN,
    STATUS_CLASS_MALFORMED,
    STATUS_CLASS_SUCCESS,
    STATUS_CLASS_UNKNOWN,
    UPSTREAM_ERROR_TYPE_MALFORMED_RESPONSE,
    UPSTREAM_ERROR_TYPE_NONE,
    UPSTREAM_ERROR_TYPE_UNKNOWN,
)
from PHX2.stage22.errors import Stage22RunnerError
from PHX2.stage22.ingest_contracts import (
    IngestEventEnvelope,
    ProviderFetchOutcome,
    Stage22DispatchOutcome,
)


# ---------------------------------------------------------------------------
# Locked Stage 22.5 banner
# ---------------------------------------------------------------------------
#
# Fixed prefix the live composition renderer prepends to every
# private ping body. The string is intentionally short and uses
# only safe ASCII characters. The literal contains no URL, no
# webhook host, no API / RPC / token / credential substring;
# the boundary scanner's source-text and identifier passes both
# accept it.


_STAGE22_5_PING_BANNER: str = "[Stage 22.5 private-preview ingest]"


# ---------------------------------------------------------------------------
# Readiness check builder
# ---------------------------------------------------------------------------


def build_live_readiness_check_fn(
    *,
    env: Mapping[str, str],
) -> Callable[[], bool]:
    """Build a zero-arg readiness-check callable.

    The caller supplies an environment mapping snapshot
    (typically a copy of ``os.environ`` taken in a scratch
    script). Stage 22 production code -- including this module
    and the bounded runner -- does NOT call ``os.environ`` /
    ``os.getenv`` directly: the Stage 21 env-read boundary
    remains ``PHX2/stage21/config.py``.

    The returned callable re-evaluates the Stage 21.3A readiness
    gate on every invocation against the *same* snapshot mapping.
    The bounded runner calls it exactly once per ``run`` pass.
    """
    if env is None:
        raise Stage22RunnerError(
            "build_live_readiness_check_fn requires a non-None env "
            "mapping"
        )
    if not isinstance(env, Mapping):
        raise Stage22RunnerError(
            "build_live_readiness_check_fn env must be a Mapping"
        )
    readiness_config: Stage21LiveReadinessConfig = (
        load_live_readiness_config_from_env(env)
    )

    def _check() -> bool:
        return evaluate_live_readiness(readiness_config).ready

    return _check


# ---------------------------------------------------------------------------
# Provider fetch wrapper
# ---------------------------------------------------------------------------


def _map_helius_exception(
    exc: BaseException,
) -> tuple[str, str]:
    """Map a Stage 21.3B Helius adapter exception onto sanitized
    ``(status_class, upstream_error_type)`` tokens.

    The mapping is intentionally conservative:

      * ``HeliusClientFetchError`` (the adapter's wrapper around
        an underlying client failure) -> ``("unknown",
        "unknown_error")``. The adapter has already sanitised
        the message to expose only the client exception's type
        name; the runner-level mapping stays in the
        ``unknown`` bucket because the actual transport-level
        failure category (timeout / rate_limit / 5xx / ...)
        cannot be recovered without inspecting the underlying
        exception, which the adapter deliberately discards.
      * ``HeliusClientResponseShapeError`` /
        ``HeliusClientResponseFieldTypeError`` /
        ``HeliusClientResponseFieldValueError`` ->
        ``("malformed", "malformed_response")``. These are the
        adapter's response-shape rejection paths; the upstream
        client returned a value the adapter could not project
        onto the 11-key payload contract.

    The raw exception ``str`` / ``repr`` / ``args`` are NEVER
    surfaced.
    """
    if isinstance(exc, HeliusClientFetchError):
        return (STATUS_CLASS_UNKNOWN, UPSTREAM_ERROR_TYPE_UNKNOWN)
    if isinstance(
        exc,
        (
            HeliusClientResponseShapeError,
            HeliusClientResponseFieldTypeError,
            HeliusClientResponseFieldValueError,
        ),
    ):
        return (STATUS_CLASS_MALFORMED, UPSTREAM_ERROR_TYPE_MALFORMED_RESPONSE)
    return (STATUS_CLASS_UNKNOWN, UPSTREAM_ERROR_TYPE_UNKNOWN)


def build_live_fetch_outcome_fn(
    *,
    adapter: HeliusProviderAdapter,
    max_results: int,
) -> Callable[[int], ProviderFetchOutcome]:
    """Build a one-arg fetch-outcome callable.

    The returned callable wraps the Stage 21.3B Helius adapter's
    ``fetch_raw_payloads`` and produces a Stage 22
    ``ProviderFetchOutcome``. The adapter is responsible for the
    actual upstream interaction; this wrapper only catches
    adapter-level exceptions and projects them onto the Stage 22
    sanitized ``status_class`` / ``upstream_error_type`` vocabulary.

    The wrapper does NOT execute retries; the bounded runner is
    one-shot in Stage 22.5 and always invokes ``fetch_outcome_fn``
    with ``attempt_index == 0``. The wrapper still echoes the
    incoming ``attempt_index`` onto the outcome's
    ``provider_attempt_index`` field so a future Stage 22.6 retry
    layer can attribute the outcome to the correct attempt.
    """
    if adapter is None:
        raise Stage22RunnerError(
            "build_live_fetch_outcome_fn requires a non-None adapter"
        )
    if not isinstance(max_results, int) or isinstance(max_results, bool):
        raise Stage22RunnerError(
            "build_live_fetch_outcome_fn max_results must be a strict int"
        )
    if max_results <= 0:
        raise Stage22RunnerError(
            "build_live_fetch_outcome_fn max_results must be >= 1"
        )

    def _fetch(attempt_index: int) -> ProviderFetchOutcome:
        if not isinstance(attempt_index, int) or isinstance(
            attempt_index, bool
        ):
            raise Stage22RunnerError(
                "fetch_outcome_fn attempt_index must be a strict int"
            )
        if attempt_index < 0:
            raise Stage22RunnerError(
                "fetch_outcome_fn attempt_index must be >= 0"
            )
        try:
            raw_payloads = adapter.fetch_raw_payloads(
                cursor=None,
                max_results=max_results,
            )
        except (
            HeliusClientFetchError,
            HeliusClientResponseShapeError,
            HeliusClientResponseFieldTypeError,
            HeliusClientResponseFieldValueError,
        ) as adapter_exc:
            status_class, upstream_error_type = _map_helius_exception(
                adapter_exc
            )
            return ProviderFetchOutcome(
                ok=False,
                responses=(),
                status_class=status_class,
                upstream_error_type=upstream_error_type,
                provider_attempt_index=attempt_index,
            )
        return ProviderFetchOutcome(
            ok=True,
            responses=tuple(raw_payloads),
            status_class=STATUS_CLASS_SUCCESS,
            upstream_error_type=UPSTREAM_ERROR_TYPE_NONE,
            provider_attempt_index=attempt_index,
        )

    return _fetch


# ---------------------------------------------------------------------------
# Decode error classifier
# ---------------------------------------------------------------------------


def classify_stage21_decode_exception(exc: BaseException) -> str:
    """Map a Stage 21.3A decoder exception onto a Stage 22.1
    ``MALFORMED_EVENT_REASONS`` token.

    The Stage 21.3A ``ProviderPayloadError`` subclass family maps
    1:1 onto the Stage 22.1 closed reason set; any other exception
    type falls back to ``decode_unexpected_error``. The raw
    exception ``str`` / ``repr`` / ``args`` are NEVER inspected
    here -- the classifier matches on type only so a hostile
    exception message cannot influence the routing decision.
    """
    if isinstance(exc, ProviderPayloadShapeError):
        return MALFORMED_REASON_SHAPE_ERROR
    if isinstance(exc, ProviderPayloadFieldTypeError):
        return MALFORMED_REASON_FIELD_TYPE_ERROR
    if isinstance(exc, ProviderPayloadFieldValueError):
        return MALFORMED_REASON_FIELD_VALUE_ERROR
    if isinstance(exc, ProviderPayloadUnsupportedInstructionError):
        return MALFORMED_REASON_UNSUPPORTED_INSTRUCTION
    if isinstance(exc, ProviderPayloadSuspiciousContentError):
        return MALFORMED_REASON_SUSPICIOUS_CONTENT
    return MALFORMED_REASON_UNEXPECTED_ERROR


# ---------------------------------------------------------------------------
# Private ping body builder
# ---------------------------------------------------------------------------


def _ensure_safe_substring(*, label: str, body: str) -> None:
    lowered = body.lower()
    for needle in CAPTURE_FORBIDDEN_URL_SUBSTRINGS:
        if needle in lowered:
            raise Stage22RunnerError(
                f"{label}: candidate body contains a forbidden "
                "URL-shape substring"
            )
    for needle in CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS:
        if needle in lowered:
            raise Stage22RunnerError(
                f"{label}: candidate body contains a forbidden "
                "secret-bearing substring"
            )


def build_private_ping_body(
    *,
    envelope: IngestEventEnvelope,
) -> str:
    """Render the Stage 22.5 private ping body for one envelope.

    The body projects only the locked safe field names
    (``provider_id``, ``chain``, ``event_type``, ``mint``,
    ``slot``, ``event_id``) onto a short fixed-shape line. It
    does NOT include the raw payload summary, the raw event
    hash, the provider event id, the signature, the
    ``observed_at_utc`` timestamp, the ATH / price / filter
    labels, the fees / Jito / Axiom / X / social context, or
    any URL / webhook / API key / RPC URL.

    The renderer applies a two-stage defence after constructing
    the body:

      1. length cap (``STAGE22_PRIVATE_PING_BODY_MAX_LEN``);
      2. forbidden URL / secret-bearing substring scan.

    Either violation raises ``Stage22RunnerError``. The renderer
    NEVER silently truncates an unsafe body -- the failure
    surfaces to the runner caller.
    """
    if envelope is None:
        raise Stage22RunnerError(
            "build_private_ping_body requires a non-None envelope"
        )
    if not isinstance(envelope, IngestEventEnvelope):
        raise Stage22RunnerError(
            "build_private_ping_body envelope must be an "
            "IngestEventEnvelope"
        )
    key = envelope.ingest_key
    event = envelope.event

    # Pre-flight: every projected field must be a non-empty
    # string (or strict int for slot) so the rendered body cannot
    # accidentally contain a Python ``None`` repr or a bool
    # coercion. The Stage 21 decoder already enforces these
    # invariants; this is the second line of defence.
    for label, field_value in (
        ("provider_id", key.provider_id),
        ("chain", key.chain),
        ("event_type", event.event_type),
        ("mint", event.mint),
        ("event_id", key.event_id),
    ):
        if not isinstance(field_value, str):
            raise Stage22RunnerError(
                f"build_private_ping_body field {label!r} must be a string"
            )
        if field_value == "":
            raise Stage22RunnerError(
                f"build_private_ping_body field {label!r} must be non-empty"
            )
    if isinstance(event.slot, bool) or not isinstance(event.slot, int):
        raise Stage22RunnerError(
            "build_private_ping_body field 'slot' must be a strict int"
        )
    if event.slot < 0:
        raise Stage22RunnerError(
            "build_private_ping_body field 'slot' must be >= 0"
        )

    body = (
        f"{_STAGE22_5_PING_BANNER} "
        f"provider={key.provider_id} chain={key.chain} "
        f"event_type={event.event_type} mint={event.mint} "
        f"slot={event.slot} event_id={key.event_id}"
    )

    if len(body) > STAGE22_PRIVATE_PING_BODY_MAX_LEN:
        raise Stage22RunnerError(
            "build_private_ping_body: rendered body exceeds the "
            "locked length cap"
        )
    _ensure_safe_substring(
        label="build_private_ping_body", body=body
    )
    return body


# ---------------------------------------------------------------------------
# Stage 22 Discord private transport adapter
# ---------------------------------------------------------------------------


class Stage22DiscordPrivateTransportAdapter:
    """Adapt a Stage 21.3C ``DiscordPrivateTransport`` plus a fixed
    recipient onto the Stage 22.5 ``Stage22PrivateTransport``
    Protocol.

    The adapter:

      * builds the private ping body via
        ``build_private_ping_body`` on every ``dispatch`` call;
      * constructs a Stage 21 ``TransportPayload`` with
        ``private_preview_marker_present=True`` and
        ``safe_for_public_dispatch=False`` (private-only, no
        routing flag flip);
      * calls ``transport.send(payload)`` exactly once;
      * maps the resulting Stage 21 ``TransportResult`` onto a
        Stage 22 ``Stage22DispatchOutcome``.

    The Stage 21 ``rejection_reason`` is passed through verbatim
    when present and short; it is replaced with the empty string
    on the dispatched=True path. The Stage 21.3C transport's
    rejection vocabulary is a small closed set of non-secret
    tokens (``readiness_not_ready`` / ``recipient_not_in_allowlist``
    / ``dispatch_safety_rejected`` / ``webhook_not_present`` /
    ``client_post_failed`` / ``upstream_non_2xx``); the adapter
    does NOT need to re-sanitise it.
    """

    def __init__(
        self,
        *,
        transport: DiscordPrivateTransport,
        recipient: str,
    ) -> None:
        if transport is None:
            raise Stage22RunnerError(
                "Stage22DiscordPrivateTransportAdapter requires a "
                "non-None transport"
            )
        if not isinstance(transport, DiscordPrivateTransport):
            raise Stage22RunnerError(
                "Stage22DiscordPrivateTransportAdapter transport must "
                "be a DiscordPrivateTransport"
            )
        if not isinstance(recipient, str):
            raise Stage22RunnerError(
                "Stage22DiscordPrivateTransportAdapter recipient must "
                "be a string"
            )
        if recipient == "":
            raise Stage22RunnerError(
                "Stage22DiscordPrivateTransportAdapter recipient must "
                "be non-empty"
            )
        self._transport: DiscordPrivateTransport = transport
        self._recipient: str = recipient

    def __repr__(self) -> str:
        return (
            "Stage22DiscordPrivateTransportAdapter(transport_type="
            f"{type(self._transport).__name__!r})"
        )

    def dispatch(
        self,
        *,
        envelope: IngestEventEnvelope,
    ) -> Stage22DispatchOutcome:
        body_text = build_private_ping_body(envelope=envelope)
        payload = TransportPayload(
            recipient=self._recipient,
            body_text=body_text,
            private_preview_marker_present=True,
            safe_for_public_dispatch=False,
        )
        result = self._transport.send(payload)
        if result.dispatched:
            return Stage22DispatchOutcome(
                dispatched=True,
                rejection_reason="",
            )
        return Stage22DispatchOutcome(
            dispatched=False,
            rejection_reason=result.rejection_reason,
        )


# ---------------------------------------------------------------------------
# Decode wrapper helper
# ---------------------------------------------------------------------------


def get_stage21_decode_fn() -> Callable[
    [Mapping[str, object]], object
]:
    """Return the Stage 21.3A ``decode_provider_event`` callable.

    Stage 22.5 callers may pass this directly to the bounded
    runner's ``decode_event_fn`` argument. The function is a pure
    decoder; it raises a ``ProviderPayloadError`` subclass on any
    contract violation and otherwise returns a
    ``NormalizedLiveEvent``. The Stage 22.4 ``handle_provider_batch``
    helper isolates each call inside a try/except so one bad event
    does not abort the surrounding batch.
    """
    return decode_provider_event


# Re-export the conservative mapping helpers so the live
# composition test surface can pin them without re-importing the
# Stage 21 exception classes.
_HELIUS_EXCEPTION_MAPPING_HELPER: Callable[
    [BaseException], tuple[str, str]
] = _map_helius_exception


__all__ = [
    "Stage22DiscordPrivateTransportAdapter",
    "build_live_fetch_outcome_fn",
    "build_live_readiness_check_fn",
    "build_private_ping_body",
    "classify_stage21_decode_exception",
    "get_stage21_decode_fn",
]
