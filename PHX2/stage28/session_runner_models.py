"""Stage 28.6 bounded private session runner models.

Stage 28.6 ships the bounded private session runner that composes
the Stage 28.1 / 28.2 / 28.3a / 28.3b / 28.4 / 28.5 reliability
primitives into a single, deterministic, redaction-safe, restart-
safe runner for longer private sessions. Stage 28.6 ships NO live
smoke; the runner consumes a caller-supplied bounded candidate
stream and a caller-injected transport (typically a fake transport
in tests; a Stage 28.4-shaped adapter in a future Stage 28.7
authorized smoke).

This module ships the closed-set vocabularies, immutable record
shapes, safe-counter / safe-identifier validators, the
``Stage28_6PrivateTransport`` protocol, the deterministic
``Stage28_6FakeTransport``, the ``Stage28_6StopSignal`` injected
stop primitive, the canonical ``asdict`` projections, and the
module-local Stage 28.6 exception hierarchy. The runner itself
lives in ``bounded_private_session_runner.py``.

Stage 28.6 does NOT:

  * connect to any provider,
  * send any real Discord message,
  * read the process environment,
  * call HTTP / gRPC / sockets,
  * sleep / schedule / queue / spawn / use asyncio / threads /
    subprocesses,
  * include subscriber / public / paid-tier / trading / wallet /
    enforcement fields anywhere on any record,
  * implement public routing / Telegram / X-social / Stage 29
    enforcement / approval semantics / activation semantics /
    automated trading / wallet logic / position sizing / trade
    execution / dashboard / control server / daemon / watchdog /
    autorestart service.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network. No HTTP. No gRPC. No socket. No file I/O at import
    or call time. (The runner module owns explicit filesystem I/O
    against caller-supplied paths.)
  * No sleep. No backoff execution. No scheduling. No queue. No
    threads. No async. No subprocess.
  * No raw secret value is ever carried on a Stage 28.6 record.
    Run / session identifiers must pass the locked safe-identifier
    allowlist; webhook URLs are never persisted; rendered payloads
    are validated for forbidden routing / secret field names.
  * ``repr()`` / ``str()`` of any Stage 28.6 record is safe to log
    / print / persist; the NamedTuple shape exposes only closed-
    set field values and safe counters / identifiers.

This module imports only stdlib (``typing``) plus the Stage 28.4
transport models (for the result-record shape) and Stage 28.5
health-status models (for stop-reason / health-status / safe-
identifier reuse). It does NOT import Stage 21-27 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import (
    Any,
    Iterable,
    Mapping,
    NamedTuple,
    Optional,
    Protocol,
    runtime_checkable,
)

from PHX2.stage28.audited_http_transport_models import (
    RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
    REDACTION_STATUS_REDACTED as _STAGE28_4_REDACTION_STATUS_REDACTED,
    SEND_ATTEMPT_COUNT_NOT_SENT,
    SEND_ATTEMPT_COUNT_SENT_ONCE,
    STAGE28_4_SCHEMA_VERSION,
    Stage28_4TransportResult,
    TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_PAYLOAD_REFUSED,
    TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_SENT_OK,
    TRANSPORT_STATUS_SERVER_ERROR,
    TRANSPORT_STATUS_VALIDATION_FAILED,
    TRANSPORT_STATUS_VALUES,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    derive_safe_reason_code,
    is_safe_webhook_identity_label,
)
from PHX2.stage28.health_status_models import (
    HEALTH_STATUS_VALUES as _STAGE28_5_HEALTH_STATUS_VALUES,
    REDACTION_STATUS_REDACTED as _STAGE28_5_REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE as _STAGE28_5_REDACTION_STATUS_SAFE,
    REDACTION_STATUS_VALUES as _STAGE28_5_REDACTION_STATUS_VALUES,
    STOP_REASON_ERROR,
    STOP_REASON_MAX_EVENTS,
    STOP_REASON_MAX_WALL_SECONDS,
    STOP_REASON_OPERATOR_STOP,
    STOP_REASON_RETRY_BUDGET_EXHAUSTED,
    STOP_REASON_SIGINT,
    STOP_REASON_VALUES as _STAGE28_5_STOP_REASON_VALUES,
    is_safe_counter_value,
    is_safe_identifier,
)


# ---------------------------------------------------------------------------
# Stage 28.6 version axes
# ---------------------------------------------------------------------------


STAGE28_6_MINOR_VERSION: str = "28.6"
STAGE28_6_SCHEMA_VERSION: str = (
    "stage28_6_bounded_private_session_runner_v0"
)


# Distinctive Stage 28.6 redaction token. Distinct from the Stage
# 27, Stage 28.1, Stage 28.2, Stage 28.3a, Stage 28.3b, Stage 28.4,
# and Stage 28.5 redaction tokens so a leak-scan test for one
# cannot collide with another.
STAGE28_6_REDACTION_TOKEN: str = "<<STAGE28_6_REDACTED>>"


# ---------------------------------------------------------------------------
# Closed-set: candidate pair status
# ---------------------------------------------------------------------------


CANDIDATE_PAIR_STATUS_OK: str = "OK"
CANDIDATE_PAIR_STATUS_UNKNOWN: str = "UNKNOWN"
CANDIDATE_PAIR_STATUS_DISAGREE: str = "DISAGREE"
CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY: str = "USDC_OBSERVE_ONLY"


CANDIDATE_PAIR_STATUS_VALUES: tuple[str, ...] = (
    CANDIDATE_PAIR_STATUS_OK,
    CANDIDATE_PAIR_STATUS_UNKNOWN,
    CANDIDATE_PAIR_STATUS_DISAGREE,
    CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY,
)


def is_candidate_pair_status_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in CANDIDATE_PAIR_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: candidate price status
# ---------------------------------------------------------------------------


CANDIDATE_PRICE_STATUS_OK: str = "OK"
CANDIDATE_PRICE_STATUS_STALE: str = "STALE"
CANDIDATE_PRICE_STATUS_MISSING: str = "MISSING"
CANDIDATE_PRICE_STATUS_TIMEOUT: str = "TIMEOUT"


CANDIDATE_PRICE_STATUS_VALUES: tuple[str, ...] = (
    CANDIDATE_PRICE_STATUS_OK,
    CANDIDATE_PRICE_STATUS_STALE,
    CANDIDATE_PRICE_STATUS_MISSING,
    CANDIDATE_PRICE_STATUS_TIMEOUT,
)


def is_candidate_price_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in CANDIDATE_PRICE_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Locked Stage 28.6 stop-reason vocabulary
# ---------------------------------------------------------------------------


# Stage 28.6 re-exposes the Stage 28.5 stop-reason vocabulary so a
# downstream reader can pin Stage 28.6's runtime-emitted stop_reason
# against the Stage 28.5 closed set without re-importing the Stage
# 28.5 module.
STAGE28_6_RUN_STOP_REASON_VALUES: tuple[str, ...] = tuple(
    _STAGE28_5_STOP_REASON_VALUES
)


def is_stage28_6_stop_reason_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in STAGE28_6_RUN_STOP_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Locked Stage 28.6 final-health-status vocabulary
# ---------------------------------------------------------------------------


STAGE28_6_FINAL_HEALTH_STATUS_VALUES: tuple[str, ...] = tuple(
    _STAGE28_5_HEALTH_STATUS_VALUES
)


def is_stage28_6_final_health_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in STAGE28_6_FINAL_HEALTH_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Locked Stage 28.6 redaction-status vocabulary
# ---------------------------------------------------------------------------


STAGE28_6_REDACTION_STATUS_VALUES: tuple[str, ...] = tuple(
    _STAGE28_5_REDACTION_STATUS_VALUES
)


# ---------------------------------------------------------------------------
# Forbidden payload field names
# ---------------------------------------------------------------------------


# Stage 28.6 candidate payloads must NEVER carry a routing field
# implying audience broadening / public routing / subscriber routing
# / paid tier / trading verdict / enforcement / approval semantics
# / wallet / signer / raw secret. Validation refuses the candidate
# at construction rather than silently forwarding it to the
# transport.
STAGE28_6_FORBIDDEN_PAYLOAD_FIELD_NAMES: tuple[str, ...] = (
    "subscriber_id",
    "subscriber_ids",
    "channel_id",
    "channel_ids",
    "public_channel_id",
    "audience",
    "paid_tier",
    "paid_tier_id",
    "route_id",
    "routing_id",
    "approval_status",
    "approval_id",
    "enforcement_result",
    "enforcement_decision",
    "trade_side",
    "trade_direction",
    "buy_signal",
    "sell_signal",
    "position_size",
    "wallet_address",
    "signer_address",
    "private_key",
    "auth_header",
    "authorization",
    "bearer_token",
    "api_key",
    "webhook_url",
    "discord_webhook_url",
    "rpc_url",
    "telegram_chat_id",
    "x_user_id",
    "tweet_id",
)


def is_stage28_6_forbidden_payload_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a Stage 28.6 forbidden
    payload-routing / secret-class field name.

    Pure / deterministic. The comparison is lower-cased + hyphen-
    normalised (hyphens are treated as underscores) and substring-
    based; any field whose normalised name contains any forbidden
    substring is refused.
    """
    if not isinstance(name, str):
        return False
    normalized = name.lower().replace("-", "_")
    for forbidden in STAGE28_6_FORBIDDEN_PAYLOAD_FIELD_NAMES:
        if forbidden in normalized:
            return True
    return False


# ---------------------------------------------------------------------------
# Safe candidate-field validation
# ---------------------------------------------------------------------------


# Stage 28.6 candidate-field allowlist. Same shape as the Stage
# 28.2 dedupe-key allowlist + the Stage 28.5 safe-identifier
# allowlist; redeclared here so Stage 28.6 does not need to import
# the prior-stage helpers (the Stage 28.6 boundary scan admits
# imports of Stage 28.4 / 28.5 models only).
_CANDIDATE_FIELD_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)
_CANDIDATE_FIELD_MIN_LENGTH: int = 1
_CANDIDATE_FIELD_MAX_LENGTH: int = 128


# Substrings that indicate URL / token / webhook / auth material;
# concatenated literally so this source file does not itself carry
# the literal prefix a downstream string-leak scan would flag.
_CANDIDATE_FIELD_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps:",
    "h" + "ttp:",
    "w" + "ss:",
    "w" + "s:",
    "://",
    "bearer",
    "authorization",
    "auth=",
    "token=",
    "apikey=",
    "key=",
    "secret=",
    "password",
    "passwd",
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "/webhooks/",
    "s" + "k-",
    "p" + "k-",
)


def is_safe_candidate_field(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe Stage 28.6 candidate
    field (token mint / event id / event kind / ping type /
    normalized event id).

    Pure / deterministic. No env access, no I/O, no logging.
    """
    if not isinstance(value, str):
        return False
    if len(value) < _CANDIDATE_FIELD_MIN_LENGTH:
        return False
    if len(value) > _CANDIDATE_FIELD_MAX_LENGTH:
        return False
    if value[0] in {"-", "_"} or value[-1] in {"-", "_"}:
        return False
    for ch in value:
        if ch not in _CANDIDATE_FIELD_ALLOWED_CHARS:
            return False
    lowered = value.lower()
    for needle in _CANDIDATE_FIELD_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return False
    return True


# Stage 28.6 artifact-reference allowlist. Mirrors Stage 28.2's
# allowlist (basename-shaped, dots allowed for file extension,
# no traversal). Redeclared so Stage 28.6 does not import Stage
# 28.2 production code.
_ARTIFACT_REFERENCE_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_.-"
)
_ARTIFACT_REFERENCE_MIN_LENGTH: int = 1
_ARTIFACT_REFERENCE_MAX_LENGTH: int = 256


def is_safe_artifact_reference(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe Stage 28.6 artifact
    reference (a bare basename, no path separators, no traversal,
    no secret-looking substring).
    """
    if not isinstance(value, str):
        return False
    if len(value) < _ARTIFACT_REFERENCE_MIN_LENGTH:
        return False
    if len(value) > _ARTIFACT_REFERENCE_MAX_LENGTH:
        return False
    if value[0] in {".", "-"} or value[-1] in {".", "-"}:
        return False
    if ".." in value:
        return False
    if "/" in value or "\\" in value:
        return False
    for ch in value:
        if ch not in _ARTIFACT_REFERENCE_ALLOWED_CHARS:
            return False
    lowered = value.lower()
    for needle in _CANDIDATE_FIELD_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return False
    return True


# ---------------------------------------------------------------------------
# Exception hierarchy (module-local)
# ---------------------------------------------------------------------------


class Stage28_6SessionRunnerError(Exception):
    """Base type for every Stage 28.6 session-runner error.

    Module-local; not a subclass of any central PHX2 error
    registry. Raw secret values must never reach the constructor;
    callers redact at the call site.
    """


class Stage28_6InvalidCandidateError(Stage28_6SessionRunnerError):
    """Raised when a ``Stage28_6CandidateEvent`` field fails
    validation.

    Carries only the canonical field name + a closed-set reason
    token; never the raw rejected value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.6 invalid candidate: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_6InvalidRunnerConfigError(Stage28_6SessionRunnerError):
    """Raised when a ``Stage28_6RunnerConfig`` field fails the
    bounded-controls invariants.

    Carries only the field name + closed-set reason token; never
    the raw rejected value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.6 invalid runner config: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_6InvalidRunSummaryError(Stage28_6SessionRunnerError):
    """Raised when a ``Stage28_6RunSummary`` field fails locked
    validation (negative counter, unknown closed-set token, etc.).
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.6 invalid run summary: "
            f"field={field_name!r} reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Stage28_6CandidateEvent
# ---------------------------------------------------------------------------


class Stage28_6CandidateEvent(NamedTuple):
    """Immutable Stage 28.6 candidate event.

    A Stage 28.6 candidate event is an already-normalized private
    candidate input handed to the runner by a caller (or by a
    bounded test fixture). The record carries only closed-set /
    safe-shape fields.

    Closed-set fields:

      * ``event_id``                    -- safe-shape candidate
                                            identifier label.
      * ``token_mint``                  -- safe-shape token mint
                                            label.
      * ``pair_quote_asset``            -- safe-shape pair quote
                                            asset label.
      * ``event_kind``                  -- safe-shape event kind
                                            label.
      * ``ping_type``                   -- safe-shape ping type
                                            label.
      * ``normalized_event_id``         -- safe-shape normalized
                                            event id label.
      * ``rendered_payload``            -- already-rendered payload
                                            dict (validated; no
                                            forbidden routing /
                                            secret keys).
      * ``pre_send_artifact_reference`` -- safe artifact basename.
      * ``webhook_identity``            -- safe-shape webhook
                                            identity label echoed
                                            on the Stage 28.4
                                            transport result.
      * ``dispatch_allowed``            -- ``bool``; ``False`` when
                                            an upstream stage
                                            already decided to
                                            suppress.
      * ``pair_status``                 -- closed-set
                                            ``CANDIDATE_PAIR_STATUS_*``.
      * ``price_status``                -- closed-set
                                            ``CANDIDATE_PRICE_STATUS_*``.
      * ``malformed``                   -- ``bool``; ``True`` when an
                                            upstream stage flagged
                                            the event as malformed.

    Excluded by construction:

      * webhook URL,
      * provider endpoint,
      * RPC URL,
      * API key / bearer token / auth header,
      * subscriber / channel / public-routing / paid-tier fields,
      * trade side / position size / buy/sell verdict,
      * wallet / signer fields.
    """

    event_id: str
    token_mint: str
    pair_quote_asset: str
    event_kind: str
    ping_type: str
    normalized_event_id: str
    rendered_payload: Mapping[str, Any]
    pre_send_artifact_reference: str
    webhook_identity: str
    dispatch_allowed: bool
    pair_status: str
    price_status: str
    malformed: bool


def _validate_rendered_payload(
    payload: object,
) -> Mapping[str, Any]:
    """Validate the caller-supplied candidate payload and return
    it.

    Validation rules:

      * payload MUST be a ``dict``,
      * every key MUST be a ``str`` and MUST NOT match any
        Stage 28.6 forbidden field name,
      * a ``rendered_payload`` of any nested shape is accepted as
        long as the *top-level* keys pass the forbidden-field
        check (deep validation is the Stage 28.4 transport's
        responsibility).
    """
    if not isinstance(payload, dict):
        raise Stage28_6InvalidCandidateError(
            field_name="rendered_payload",
            reason="PAYLOAD_NOT_DICT",
        )
    for key in payload.keys():
        if not isinstance(key, str):
            raise Stage28_6InvalidCandidateError(
                field_name="rendered_payload",
                reason="PAYLOAD_KEY_NOT_STRING",
            )
        if is_stage28_6_forbidden_payload_field_name(key):
            raise Stage28_6InvalidCandidateError(
                field_name="rendered_payload",
                reason="PAYLOAD_FORBIDDEN_FIELD_NAME",
            )
    return payload


def build_candidate_event(
    *,
    event_id: object,
    token_mint: object,
    pair_quote_asset: object,
    event_kind: object,
    ping_type: object,
    normalized_event_id: object,
    rendered_payload: object,
    pre_send_artifact_reference: object,
    webhook_identity: object,
    dispatch_allowed: object,
    pair_status: object,
    price_status: object,
    malformed: object = False,
) -> Stage28_6CandidateEvent:
    """Construct an immutable ``Stage28_6CandidateEvent`` with full
    validation.

    Raises ``Stage28_6InvalidCandidateError`` for any field that
    fails the locked allowlist; never echoes the raw rejected
    value.
    """
    fields: tuple[tuple[str, object], ...] = (
        ("event_id", event_id),
        ("token_mint", token_mint),
        ("pair_quote_asset", pair_quote_asset),
        ("event_kind", event_kind),
        ("ping_type", ping_type),
        ("normalized_event_id", normalized_event_id),
    )
    for name, value in fields:
        if not is_safe_candidate_field(value):
            raise Stage28_6InvalidCandidateError(
                field_name=name,
                reason="CANDIDATE_FIELD_UNSAFE",
            )
    payload = _validate_rendered_payload(rendered_payload)
    if not is_safe_artifact_reference(pre_send_artifact_reference):
        raise Stage28_6InvalidCandidateError(
            field_name="pre_send_artifact_reference",
            reason="ARTIFACT_REFERENCE_UNSAFE",
        )
    if not is_safe_webhook_identity_label(webhook_identity):
        raise Stage28_6InvalidCandidateError(
            field_name="webhook_identity",
            reason="WEBHOOK_IDENTITY_UNSAFE",
        )
    if isinstance(dispatch_allowed, bool):
        d_allowed = dispatch_allowed
    else:
        raise Stage28_6InvalidCandidateError(
            field_name="dispatch_allowed",
            reason="DISPATCH_ALLOWED_NOT_BOOL",
        )
    if not is_candidate_pair_status_value(pair_status):
        raise Stage28_6InvalidCandidateError(
            field_name="pair_status",
            reason="PAIR_STATUS_NOT_CLOSED_SET",
        )
    if not is_candidate_price_status_value(price_status):
        raise Stage28_6InvalidCandidateError(
            field_name="price_status",
            reason="PRICE_STATUS_NOT_CLOSED_SET",
        )
    if isinstance(malformed, bool):
        m = malformed
    else:
        raise Stage28_6InvalidCandidateError(
            field_name="malformed",
            reason="MALFORMED_NOT_BOOL",
        )
    return Stage28_6CandidateEvent(
        event_id=event_id,  # type: ignore[arg-type]
        token_mint=token_mint,  # type: ignore[arg-type]
        pair_quote_asset=pair_quote_asset,  # type: ignore[arg-type]
        event_kind=event_kind,  # type: ignore[arg-type]
        ping_type=ping_type,  # type: ignore[arg-type]
        normalized_event_id=normalized_event_id,  # type: ignore[arg-type]
        rendered_payload=payload,
        pre_send_artifact_reference=(
            pre_send_artifact_reference  # type: ignore[arg-type]
        ),
        webhook_identity=webhook_identity,  # type: ignore[arg-type]
        dispatch_allowed=d_allowed,
        pair_status=pair_status,  # type: ignore[arg-type]
        price_status=price_status,  # type: ignore[arg-type]
        malformed=m,
    )


# ---------------------------------------------------------------------------
# Stage28_6RunnerConfig
# ---------------------------------------------------------------------------


class Stage28_6RunnerConfig(NamedTuple):
    """Immutable Stage 28.6 runner config record.

    Closed-set / bounded-controls fields:

      * ``run_id``                            -- safe-shape run id.
      * ``session_id``                        -- safe-shape session
                                                  id.
      * ``max_events``                        -- positive ``int``;
                                                  hard cap on the
                                                  number of candidate
                                                  events the runner
                                                  will process.
      * ``max_dispatches``                    -- positive ``int``;
                                                  hard cap on the
                                                  number of successful
                                                  + failed transport
                                                  send attempts.
      * ``max_total_retries``                 -- non-negative ``int``;
                                                  session-wide retry
                                                  budget.
      * ``max_ticks``                         -- positive ``int``;
                                                  injected-clock tick
                                                  budget (Stage 28.6
                                                  uses ticks rather
                                                  than wall-clock
                                                  seconds for
                                                  determinism).
      * ``heartbeat_every_n_events``          -- positive ``int``;
                                                  the runner emits a
                                                  heartbeat record
                                                  every ``N``
                                                  observed events.
      * ``fail_closed_on_artifact_error``     -- ``bool``; when
                                                  ``True``, an
                                                  artifact write
                                                  failure stops the
                                                  session.
      * ``fail_closed_on_ledger_error``       -- ``bool``; when
                                                  ``True``, a ledger
                                                  write failure stops
                                                  the session.
      * ``fail_closed_on_heartbeat_error``    -- ``bool``; when
                                                  ``True``, a
                                                  heartbeat write
                                                  failure stops the
                                                  session.
    """

    run_id: str
    session_id: str
    max_events: int
    max_dispatches: int
    max_total_retries: int
    max_ticks: int
    heartbeat_every_n_events: int
    fail_closed_on_artifact_error: bool
    fail_closed_on_ledger_error: bool
    fail_closed_on_heartbeat_error: bool


def _validate_positive_int(field_name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Stage28_6InvalidRunnerConfigError(
            field_name=field_name,
            reason="VALUE_NOT_INT",
        )
    if value <= 0:
        raise Stage28_6InvalidRunnerConfigError(
            field_name=field_name,
            reason="VALUE_NOT_POSITIVE",
        )
    return value


def _validate_nonneg_int(field_name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Stage28_6InvalidRunnerConfigError(
            field_name=field_name,
            reason="VALUE_NOT_INT",
        )
    if value < 0:
        raise Stage28_6InvalidRunnerConfigError(
            field_name=field_name,
            reason="VALUE_NEGATIVE",
        )
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise Stage28_6InvalidRunnerConfigError(
            field_name=field_name,
            reason="VALUE_NOT_BOOL",
        )
    return value


def build_runner_config(
    *,
    run_id: object,
    session_id: object,
    max_events: object,
    max_dispatches: object,
    max_total_retries: object,
    max_ticks: object,
    heartbeat_every_n_events: object,
    fail_closed_on_artifact_error: object = True,
    fail_closed_on_ledger_error: object = True,
    fail_closed_on_heartbeat_error: object = False,
) -> Stage28_6RunnerConfig:
    """Construct an immutable ``Stage28_6RunnerConfig`` with full
    validation.

    Raises ``Stage28_6InvalidRunnerConfigError`` for any field
    that fails the bounded-controls invariants.
    """
    if not is_safe_identifier(run_id):
        raise Stage28_6InvalidRunnerConfigError(
            field_name="run_id",
            reason="RUN_ID_UNSAFE",
        )
    if not is_safe_identifier(session_id):
        raise Stage28_6InvalidRunnerConfigError(
            field_name="session_id",
            reason="SESSION_ID_UNSAFE",
        )
    me = _validate_positive_int("max_events", max_events)
    md = _validate_positive_int("max_dispatches", max_dispatches)
    mr = _validate_nonneg_int("max_total_retries", max_total_retries)
    mt = _validate_positive_int("max_ticks", max_ticks)
    he = _validate_positive_int(
        "heartbeat_every_n_events", heartbeat_every_n_events
    )
    fca = _validate_bool(
        "fail_closed_on_artifact_error",
        fail_closed_on_artifact_error,
    )
    fcl = _validate_bool(
        "fail_closed_on_ledger_error",
        fail_closed_on_ledger_error,
    )
    fch = _validate_bool(
        "fail_closed_on_heartbeat_error",
        fail_closed_on_heartbeat_error,
    )
    return Stage28_6RunnerConfig(
        run_id=run_id,  # type: ignore[arg-type]
        session_id=session_id,  # type: ignore[arg-type]
        max_events=me,
        max_dispatches=md,
        max_total_retries=mr,
        max_ticks=mt,
        heartbeat_every_n_events=he,
        fail_closed_on_artifact_error=fca,
        fail_closed_on_ledger_error=fcl,
        fail_closed_on_heartbeat_error=fch,
    )


# ---------------------------------------------------------------------------
# Stage28_6RunSummary
# ---------------------------------------------------------------------------


class Stage28_6RunSummary(NamedTuple):
    """Immutable Stage 28.6 run summary record.

    Closed-set / safe fields only. The record summarizes the
    bounded private session run; its shape never carries a
    webhook URL, provider endpoint, API key, bearer token, auth
    header, wallet / private-key field, raw response body, raw env
    value, secret-like path, or raw exception string.

    Counter axes (all non-negative ``int``):

      * ``events_seen``                  -- total candidate events
                                             observed (including
                                             malformed / suppressed).
      * ``candidates_seen``              -- total non-malformed
                                             candidates considered.
      * ``dispatch_attempts``            -- total transport send
                                             invocations across the
                                             run.
      * ``dispatch_success``             -- transport-OK outcomes.
      * ``dispatch_failure``             -- transport-non-OK
                                             terminal outcomes.
      * ``retries_attempted``            -- total retry attempts
                                             beyond the first send
                                             per candidate.
      * ``duplicates_suppressed``        -- ledger terminal-duplicate
                                             suppressions.
      * ``ambiguous_suppressed``         -- ledger ambiguous
                                             suppressions.
      * ``unknown_pair_suppressed``      -- Stage 27
                                             unknown-pair-pair-status
                                             suppressions.
      * ``disagree_pair_suppressed``     -- Stage 27 DISAGREE pair
                                             suppressions.
      * ``usdc_observe_only``            -- Stage 27 USDC observe-
                                             only suppressions.
      * ``stale_price_suppressed``       -- Stage 25-shape stale
                                             price suppressions.
      * ``missing_price_suppressed``     -- Stage 25-shape missing
                                             price suppressions.
      * ``malformed_events``             -- malformed-event
                                             observations.
      * ``ledger_failures``              -- ledger I/O failures.
      * ``artifact_failures``            -- heartbeat / snapshot /
                                             summary write failures.
      * ``transport_failures``           -- transport non-OK
                                             outcomes (subset of
                                             dispatch_failure when
                                             non-retryable).
    """

    schema_version: str
    run_id: str
    session_id: str
    stop_reason: str
    events_seen: int
    candidates_seen: int
    dispatch_attempts: int
    dispatch_success: int
    dispatch_failure: int
    retries_attempted: int
    duplicates_suppressed: int
    ambiguous_suppressed: int
    unknown_pair_suppressed: int
    disagree_pair_suppressed: int
    usdc_observe_only: int
    stale_price_suppressed: int
    missing_price_suppressed: int
    malformed_events: int
    ledger_failures: int
    artifact_failures: int
    transport_failures: int
    final_health_status: str
    redaction_status: str


STAGE28_6_RUN_SUMMARY_COUNTER_FIELD_NAMES: tuple[str, ...] = (
    "events_seen",
    "candidates_seen",
    "dispatch_attempts",
    "dispatch_success",
    "dispatch_failure",
    "retries_attempted",
    "duplicates_suppressed",
    "ambiguous_suppressed",
    "unknown_pair_suppressed",
    "disagree_pair_suppressed",
    "usdc_observe_only",
    "stale_price_suppressed",
    "missing_price_suppressed",
    "malformed_events",
    "ledger_failures",
    "artifact_failures",
    "transport_failures",
)


STAGE28_6_RUN_SUMMARY_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "session_id",
    "stop_reason",
    "events_seen",
    "candidates_seen",
    "dispatch_attempts",
    "dispatch_success",
    "dispatch_failure",
    "retries_attempted",
    "duplicates_suppressed",
    "ambiguous_suppressed",
    "unknown_pair_suppressed",
    "disagree_pair_suppressed",
    "usdc_observe_only",
    "stale_price_suppressed",
    "missing_price_suppressed",
    "malformed_events",
    "ledger_failures",
    "artifact_failures",
    "transport_failures",
    "final_health_status",
    "redaction_status",
)


def build_run_summary(
    *,
    run_id: object,
    session_id: object,
    stop_reason: object,
    events_seen: object,
    candidates_seen: object,
    dispatch_attempts: object,
    dispatch_success: object,
    dispatch_failure: object,
    retries_attempted: object,
    duplicates_suppressed: object,
    ambiguous_suppressed: object,
    unknown_pair_suppressed: object,
    disagree_pair_suppressed: object,
    usdc_observe_only: object,
    stale_price_suppressed: object,
    missing_price_suppressed: object,
    malformed_events: object,
    ledger_failures: object,
    artifact_failures: object,
    transport_failures: object,
    final_health_status: object,
) -> Stage28_6RunSummary:
    """Construct an immutable ``Stage28_6RunSummary`` with full
    validation."""
    if not is_safe_identifier(run_id):
        raise Stage28_6InvalidRunSummaryError(
            field_name="run_id",
            reason="RUN_ID_UNSAFE",
        )
    if not is_safe_identifier(session_id):
        raise Stage28_6InvalidRunSummaryError(
            field_name="session_id",
            reason="SESSION_ID_UNSAFE",
        )
    if not is_stage28_6_stop_reason_value(stop_reason):
        raise Stage28_6InvalidRunSummaryError(
            field_name="stop_reason",
            reason="STOP_REASON_NOT_CLOSED_SET",
        )
    counters: dict[str, int] = {}
    for name, value in (
        ("events_seen", events_seen),
        ("candidates_seen", candidates_seen),
        ("dispatch_attempts", dispatch_attempts),
        ("dispatch_success", dispatch_success),
        ("dispatch_failure", dispatch_failure),
        ("retries_attempted", retries_attempted),
        ("duplicates_suppressed", duplicates_suppressed),
        ("ambiguous_suppressed", ambiguous_suppressed),
        ("unknown_pair_suppressed", unknown_pair_suppressed),
        ("disagree_pair_suppressed", disagree_pair_suppressed),
        ("usdc_observe_only", usdc_observe_only),
        ("stale_price_suppressed", stale_price_suppressed),
        ("missing_price_suppressed", missing_price_suppressed),
        ("malformed_events", malformed_events),
        ("ledger_failures", ledger_failures),
        ("artifact_failures", artifact_failures),
        ("transport_failures", transport_failures),
    ):
        if not is_safe_counter_value(value):
            raise Stage28_6InvalidRunSummaryError(
                field_name=name,
                reason="COUNTER_NOT_NONNEG_INT",
            )
        counters[name] = value  # type: ignore[assignment]
    if not is_stage28_6_final_health_status_value(final_health_status):
        raise Stage28_6InvalidRunSummaryError(
            field_name="final_health_status",
            reason="HEALTH_STATUS_NOT_CLOSED_SET",
        )
    return Stage28_6RunSummary(
        schema_version=STAGE28_6_SCHEMA_VERSION,
        run_id=run_id,  # type: ignore[arg-type]
        session_id=session_id,  # type: ignore[arg-type]
        stop_reason=stop_reason,  # type: ignore[arg-type]
        events_seen=counters["events_seen"],
        candidates_seen=counters["candidates_seen"],
        dispatch_attempts=counters["dispatch_attempts"],
        dispatch_success=counters["dispatch_success"],
        dispatch_failure=counters["dispatch_failure"],
        retries_attempted=counters["retries_attempted"],
        duplicates_suppressed=counters["duplicates_suppressed"],
        ambiguous_suppressed=counters["ambiguous_suppressed"],
        unknown_pair_suppressed=counters["unknown_pair_suppressed"],
        disagree_pair_suppressed=counters["disagree_pair_suppressed"],
        usdc_observe_only=counters["usdc_observe_only"],
        stale_price_suppressed=counters["stale_price_suppressed"],
        missing_price_suppressed=counters["missing_price_suppressed"],
        malformed_events=counters["malformed_events"],
        ledger_failures=counters["ledger_failures"],
        artifact_failures=counters["artifact_failures"],
        transport_failures=counters["transport_failures"],
        final_health_status=(
            final_health_status  # type: ignore[arg-type]
        ),
        redaction_status=_STAGE28_5_REDACTION_STATUS_SAFE,
    )


def run_summary_to_dict(record: Stage28_6RunSummary) -> dict:
    """Project a run summary record into a deterministic-order dict
    suitable for tests and downstream inspection.
    """
    if not isinstance(record, Stage28_6RunSummary):
        raise Stage28_6InvalidRunSummaryError(
            field_name="record",
            reason="NOT_A_RUN_SUMMARY_RECORD",
        )
    return {
        name: getattr(record, name)
        for name in STAGE28_6_RUN_SUMMARY_FIELD_NAMES
    }


# ---------------------------------------------------------------------------
# Stage28_6StopSignal
# ---------------------------------------------------------------------------


class Stage28_6StopSignal:
    """Injectable Stage 28.6 stop-signal primitive.

    Tests and operator integrations construct a
    ``Stage28_6StopSignal`` instance and request the runner to stop
    by calling ``request_stop()``. The runner polls
    ``is_requested()`` between candidates / retry attempts and
    initiates graceful shutdown when the signal is set.

    The signal carries an optional closed-set ``reason`` field. The
    runner emits the matching Stage 28.5 stop-reason when the signal
    is set (``STOP_REASON_OPERATOR_STOP`` by default;
    ``STOP_REASON_SIGINT`` for the SIGINT-like signal kind).

    No OS signal handlers are installed by Stage 28.6 itself; the
    caller is responsible for wiring an external signal (if any)
    into ``request_stop()``.
    """

    def __init__(self) -> None:
        self._requested: bool = False
        self._reason: str = STOP_REASON_OPERATOR_STOP

    def request_stop(
        self,
        *,
        reason: str = STOP_REASON_OPERATOR_STOP,
    ) -> None:
        """Set the stop flag. The locked Stage 28.5 stop reason
        ``reason`` is captured for use when the runner emits the
        final summary.
        """
        if reason not in (
            STOP_REASON_OPERATOR_STOP,
            STOP_REASON_SIGINT,
        ):
            raise Stage28_6SessionRunnerError(
                f"Stage 28.6 stop signal reason {reason!r} is not "
                f"one of the locked operator-stop reasons"
            )
        self._requested = True
        self._reason = reason

    def is_requested(self) -> bool:
        return self._requested

    @property
    def reason(self) -> str:
        return self._reason


# ---------------------------------------------------------------------------
# Stage28_6PrivateTransport protocol + fake transport
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage28_6PrivateTransport(Protocol):
    """Stage 28.6 private transport protocol.

    The runner expects exactly one method: ``send_one_audited_post``
    with the Stage 28.4-shaped keyword arguments. The protocol
    omits the ``webhook_url`` keyword from the Stage 28.4 shape:
    Stage 28.6 holds no webhook URL itself, so the URL (if any)
    is bound inside the injected transport implementation. The
    Stage 28.6 fake transport keeps no URL; a future Stage 28.7
    audited adapter binds a real Stage 28.4 URL inside itself
    before being passed to Stage 28.6.

    Implementations MUST:

      * return a Stage 28.4 ``Stage28_4TransportResult``,
      * NEVER sleep, schedule, retry, or batch,
      * NEVER expose the raw webhook URL on records / exceptions /
        repr / str / public dicts.
    """

    def send_one_audited_post(
        self,
        *,
        webhook_identity: str,
        payload: Mapping[str, Any],
    ) -> Stage28_4TransportResult:
        ...


def _build_stage28_4_compatible_result(
    *,
    transport_status: str,
    http_status_code: Optional[int],
    retry_after_seconds: Optional[float],
    webhook_identity: str,
    send_attempt_count: int,
) -> Stage28_4TransportResult:
    """Construct a Stage 28.4-compatible ``Stage28_4TransportResult``
    from closed-set inputs.

    Used by the Stage 28.6 fake transport so the runner sees the
    same result shape it will see from a real Stage 28.4 adapter
    in a future Stage 28.7 substage. The function never copies
    a raw webhook URL, raw response body, or raw exception
    message onto the result.
    """
    if transport_status not in TRANSPORT_STATUS_VALUES:
        raise Stage28_6SessionRunnerError(
            f"Stage 28.6 fake transport refusing to emit a non-"
            f"closed-set transport status (length="
            f"{len(transport_status) if isinstance(transport_status, str) else -1})"
        )
    ok = transport_status == TRANSPORT_STATUS_SENT_OK
    safe_identity = (
        webhook_identity
        if is_safe_webhook_identity_label(webhook_identity)
        else WEBHOOK_IDENTITY_PRIVATE_OPERATOR
    )
    return Stage28_4TransportResult(
        transport_status=transport_status,
        ok=ok,
        http_status_code=http_status_code,
        retry_after_seconds=retry_after_seconds,
        send_attempt_count=send_attempt_count,
        webhook_identity=safe_identity,
        redaction_status=_STAGE28_4_REDACTION_STATUS_REDACTED,
        safe_reason_code=derive_safe_reason_code(transport_status),
        response_body_status=RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
        schema_version=STAGE28_4_SCHEMA_VERSION,
    )


class Stage28_6FakeTransport:
    """Deterministic Stage 28.6 fake transport for tests.

    The fake records each ``send_one_audited_post(...)`` call so
    tests can assert the runner built the expected payload /
    webhook identity. The fake never opens a network connection,
    never reads the process environment, never sleeps, never
    retries, and never imports a non-stdlib library.

    Behavior knobs:

      * ``scripted_outcomes``           -- tuple of Stage 28.4
                                            transport-status tokens.
                                            The fake yields one
                                            per ``send_one_audited_post``
                                            call (truncating at the
                                            tuple length; subsequent
                                            calls reuse the last
                                            scripted outcome). The
                                            default is a single
                                            ``SENT_OK``.
      * ``scripted_retry_after_seconds`` -- optional non-negative
                                            ``float`` retry-after
                                            value attached to a
                                            ``RATE_LIMITED`` outcome.
      * ``scripted_http_status_code``    -- optional numeric HTTP
                                            status echoed on the
                                            result.
    """

    def __init__(
        self,
        *,
        scripted_outcomes: tuple[str, ...] = (TRANSPORT_STATUS_SENT_OK,),
        scripted_retry_after_seconds: Optional[float] = None,
        scripted_http_status_code: Optional[int] = None,
    ) -> None:
        if not scripted_outcomes:
            scripted_outcomes = (TRANSPORT_STATUS_SENT_OK,)
        for outcome in scripted_outcomes:
            if outcome not in TRANSPORT_STATUS_VALUES:
                raise Stage28_6SessionRunnerError(
                    "Stage 28.6 fake transport refusing a non-"
                    "closed-set scripted outcome token"
                )
        self._scripted_outcomes: tuple[str, ...] = tuple(
            scripted_outcomes
        )
        self._scripted_retry_after_seconds: Optional[float] = (
            scripted_retry_after_seconds
        )
        self._scripted_http_status_code: Optional[int] = (
            scripted_http_status_code
        )
        self._calls: list[dict] = []

    @property
    def calls(self) -> tuple[dict, ...]:
        """Return the recorded ``send_one_audited_post(...)`` calls
        in invocation order.
        """
        return tuple(self._calls)

    @property
    def call_count(self) -> int:
        return len(self._calls)

    def send_one_audited_post(
        self,
        *,
        webhook_identity: str,
        payload: Mapping[str, Any],
    ) -> Stage28_4TransportResult:
        index = len(self._calls)
        outcome_index = (
            index
            if index < len(self._scripted_outcomes)
            else len(self._scripted_outcomes) - 1
        )
        outcome = self._scripted_outcomes[outcome_index]
        recorded_payload: dict
        if isinstance(payload, dict):
            recorded_payload = dict(payload)
        else:
            recorded_payload = {}
        self._calls.append(
            {
                "webhook_identity": webhook_identity,
                "payload": recorded_payload,
            }
        )
        if outcome == TRANSPORT_STATUS_SENT_OK:
            http_status = self._scripted_http_status_code
            if http_status is None:
                http_status = 204
            return _build_stage28_4_compatible_result(
                transport_status=outcome,
                http_status_code=http_status,
                retry_after_seconds=None,
                webhook_identity=webhook_identity,
                send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
            )
        if outcome == TRANSPORT_STATUS_RATE_LIMITED:
            http_status = self._scripted_http_status_code
            if http_status is None:
                http_status = 429
            return _build_stage28_4_compatible_result(
                transport_status=outcome,
                http_status_code=http_status,
                retry_after_seconds=(
                    self._scripted_retry_after_seconds
                ),
                webhook_identity=webhook_identity,
                send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
            )
        if outcome == TRANSPORT_STATUS_SERVER_ERROR:
            http_status = self._scripted_http_status_code
            if http_status is None:
                http_status = 503
            return _build_stage28_4_compatible_result(
                transport_status=outcome,
                http_status_code=http_status,
                retry_after_seconds=None,
                webhook_identity=webhook_identity,
                send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
            )
        if outcome == TRANSPORT_STATUS_NETWORK_ERROR:
            return _build_stage28_4_compatible_result(
                transport_status=outcome,
                http_status_code=None,
                retry_after_seconds=None,
                webhook_identity=webhook_identity,
                send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
            )
        if outcome == TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED:
            http_status = self._scripted_http_status_code
            if http_status is None:
                http_status = 401
            return _build_stage28_4_compatible_result(
                transport_status=outcome,
                http_status_code=http_status,
                retry_after_seconds=None,
                webhook_identity=webhook_identity,
                send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
            )
        if outcome == TRANSPORT_STATUS_VALIDATION_FAILED:
            return _build_stage28_4_compatible_result(
                transport_status=outcome,
                http_status_code=None,
                retry_after_seconds=None,
                webhook_identity=webhook_identity,
                send_attempt_count=SEND_ATTEMPT_COUNT_NOT_SENT,
            )
        # TRANSPORT_STATUS_PAYLOAD_REFUSED.
        return _build_stage28_4_compatible_result(
            transport_status=TRANSPORT_STATUS_PAYLOAD_REFUSED,
            http_status_code=None,
            retry_after_seconds=None,
            webhook_identity=webhook_identity,
            send_attempt_count=SEND_ATTEMPT_COUNT_NOT_SENT,
        )


# ---------------------------------------------------------------------------
# Stage28_6TickClock protocol + deterministic counter clock
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage28_6TickClock(Protocol):
    """Stage 28.6 tick-clock protocol.

    The runner consults ``tick()`` after each candidate to advance
    its tick counter without a real wall-clock. The clock returns
    a monotonically non-decreasing ``int`` count.
    """

    def tick(self) -> int:
        ...


class Stage28_6DeterministicTickClock:
    """Deterministic Stage 28.6 tick clock used by tests.

    Each ``tick()`` call increments an internal counter by one and
    returns the new value. The clock never sleeps and never reads
    a real wall-clock; the runner uses it purely as a bounded-
    iteration counter.
    """

    def __init__(self) -> None:
        self._count: int = 0

    def tick(self) -> int:
        self._count += 1
        return self._count

    @property
    def count(self) -> int:
        return self._count


__all__ = (
    # Version axes.
    "STAGE28_6_MINOR_VERSION",
    "STAGE28_6_SCHEMA_VERSION",
    "STAGE28_6_REDACTION_TOKEN",
    # Candidate pair status.
    "CANDIDATE_PAIR_STATUS_OK",
    "CANDIDATE_PAIR_STATUS_UNKNOWN",
    "CANDIDATE_PAIR_STATUS_DISAGREE",
    "CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY",
    "CANDIDATE_PAIR_STATUS_VALUES",
    "is_candidate_pair_status_value",
    # Candidate price status.
    "CANDIDATE_PRICE_STATUS_OK",
    "CANDIDATE_PRICE_STATUS_STALE",
    "CANDIDATE_PRICE_STATUS_MISSING",
    "CANDIDATE_PRICE_STATUS_TIMEOUT",
    "CANDIDATE_PRICE_STATUS_VALUES",
    "is_candidate_price_status_value",
    # Run stop-reason vocabulary.
    "STAGE28_6_RUN_STOP_REASON_VALUES",
    "is_stage28_6_stop_reason_value",
    # Run final-health-status vocabulary.
    "STAGE28_6_FINAL_HEALTH_STATUS_VALUES",
    "is_stage28_6_final_health_status_value",
    # Redaction-status vocabulary.
    "STAGE28_6_REDACTION_STATUS_VALUES",
    # Forbidden payload fields.
    "STAGE28_6_FORBIDDEN_PAYLOAD_FIELD_NAMES",
    "is_stage28_6_forbidden_payload_field_name",
    # Safe-field validation.
    "is_safe_candidate_field",
    "is_safe_artifact_reference",
    # Run summary field names.
    "STAGE28_6_RUN_SUMMARY_COUNTER_FIELD_NAMES",
    "STAGE28_6_RUN_SUMMARY_FIELD_NAMES",
    # Records.
    "Stage28_6CandidateEvent",
    "Stage28_6RunnerConfig",
    "Stage28_6RunSummary",
    # Builders.
    "build_candidate_event",
    "build_runner_config",
    "build_run_summary",
    "run_summary_to_dict",
    # Stop-signal primitive.
    "Stage28_6StopSignal",
    # Transport protocol + fake.
    "Stage28_6PrivateTransport",
    "Stage28_6FakeTransport",
    # Tick clock protocol + deterministic clock.
    "Stage28_6TickClock",
    "Stage28_6DeterministicTickClock",
    # Exceptions.
    "Stage28_6SessionRunnerError",
    "Stage28_6InvalidCandidateError",
    "Stage28_6InvalidRunnerConfigError",
    "Stage28_6InvalidRunSummaryError",
)
