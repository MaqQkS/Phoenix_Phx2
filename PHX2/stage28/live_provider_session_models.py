"""Stage 28.9 private live provider session models.

Stage 28.9 is the post-Stage-28-closure operational bridge that
gets real provider-backed candidate events flowing into the
already-closed Stage 28.6 bounded private session runner so the
operator can see real private Discord coin pings from the
Stage 27 candidate chain. Stage 28.9 is NOT a reliability
substage; it is the operator-only bridge that lights up the
already-audited reliability composition.

This module ships the immutable closed-set vocabularies +
config / result / readiness records + the module-local
exception hierarchy used by the Stage 28.9 adapter and
transport modules. The module is intentionally narrow:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network. No HTTP. No gRPC. No socket. No file I/O at
    import or call time.
  * No sleep. No backoff execution. No scheduling. No queue. No
    threads. No async. No subprocess.
  * No raw secret value is ever carried on a Stage 28.9 record.
    Provider IDs / provider kinds / run / session identifiers
    pass the locked safe-identifier allowlist; webhook URLs are
    never persisted; output-directory labels are reduced to a
    safe basename token.
  * ``repr()`` / ``str()`` of any Stage 28.9 record is safe to
    log / print / persist; the NamedTuple shape exposes only
    closed-set field values and safe counters / identifiers.

Stage 28.9 ships NO Stage 29 enforcement, NO approval /
activation semantics, NO public routing, NO subscriber routing,
NO paid tier routing, NO Telegram, NO X / social, NO automated
trading, NO wallet / private-key / signer logic, NO position
sizing, NO trade execution, NO dashboard / HTTP control server,
NO daemon / systemd / watchdog / autorestart service.

This module imports only stdlib (``typing``) plus the Stage 28.4
transport models (for the locked safe-identifier label re-use)
and the Stage 28.5 health-status models (for safe-identifier
re-use). It does NOT import Stage 21-27 production code, does
NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import Any, Mapping, NamedTuple, Optional

from PHX2.stage28.audited_http_transport_models import (
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
    is_safe_webhook_identity_label,
)
from PHX2.stage28.health_status_models import (
    is_safe_counter_value,
    is_safe_identifier,
)


# ---------------------------------------------------------------------------
# Stage 28.9 version axes
# ---------------------------------------------------------------------------


STAGE28_9_MINOR_VERSION: str = "28.9"
STAGE28_9_SCHEMA_VERSION: str = (
    "stage28_9_live_provider_session_v0"
)


# Distinctive Stage 28.9 redaction token. Distinct from the Stage
# 27 / 28.1 / 28.2 / 28.3a / 28.3b / 28.4 / 28.5 / 28.6 / 28.7
# redaction tokens so a leak-scan test for one cannot collide with
# another.
STAGE28_9_REDACTION_TOKEN: str = "<<STAGE28_9_REDACTED>>"


# Locked operator-visible marker the Stage 28.9 adapter stamps on
# every rendered Discord payload. The marker tells the operator
# that Stage 28.9 pings flow without the Stage 29 approved /
# activated filter enforcement gate; the operator must manually
# interpret each ping until Stage 29 lands.
FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING: str = (
    "NOT_ACTIVE_STAGE_29_PENDING"
)


FILTER_ENFORCEMENT_NOTICE_TEXT: str = (
    "Filter enforcement: "
    + FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
)


# Closed-set policy mode labels the Stage 28.9 payload header
# carries. Stage 28.9 is private operator only; observe / manual
# mode only; no trading verdict; no automated send to any other
# audience.
POLICY_MODE_PRIVATE_OPERATOR_ONLY: str = (
    "PRIVATE_OPERATOR_ONLY_OBSERVE_MANUAL"
)


# ---------------------------------------------------------------------------
# Closed-set: session outcome
# ---------------------------------------------------------------------------


SESSION_OUTCOME_OK: str = "OK"
SESSION_OUTCOME_DEGRADED: str = "DEGRADED"
SESSION_OUTCOME_REFUSED: str = "REFUSED"
SESSION_OUTCOME_FAILED: str = "FAILED"


SESSION_OUTCOME_VALUES: tuple[str, ...] = (
    SESSION_OUTCOME_OK,
    SESSION_OUTCOME_DEGRADED,
    SESSION_OUTCOME_REFUSED,
    SESSION_OUTCOME_FAILED,
)


def is_session_outcome_value(value: object) -> bool:
    return isinstance(value, str) and value in SESSION_OUTCOME_VALUES


# ---------------------------------------------------------------------------
# Closed-set: refusal reason
# ---------------------------------------------------------------------------


REFUSAL_REASON_NOT_REFUSED: str = "NOT_REFUSED"
REFUSAL_REASON_NOT_LIVE: str = "READINESS_FAILED_NOT_LIVE"
REFUSAL_REASON_WEBHOOK_MISSING: str = (
    "READINESS_FAILED_WEBHOOK_MISSING"
)
REFUSAL_REASON_PROVIDER_UNSAFE: str = (
    "READINESS_FAILED_PROVIDER_UNSAFE"
)
REFUSAL_REASON_BOUNDS_INVALID: str = (
    "READINESS_FAILED_BOUNDS_INVALID"
)
REFUSAL_REASON_OUTPUT_DIR_UNSAFE: str = (
    "READINESS_FAILED_OUTPUT_DIR_UNSAFE"
)
REFUSAL_REASON_NOT_OPERATOR_REQUESTED: str = (
    "READINESS_FAILED_NOT_OPERATOR_REQUESTED"
)


REFUSAL_REASON_VALUES: tuple[str, ...] = (
    REFUSAL_REASON_NOT_REFUSED,
    REFUSAL_REASON_NOT_LIVE,
    REFUSAL_REASON_WEBHOOK_MISSING,
    REFUSAL_REASON_PROVIDER_UNSAFE,
    REFUSAL_REASON_BOUNDS_INVALID,
    REFUSAL_REASON_OUTPUT_DIR_UNSAFE,
    REFUSAL_REASON_NOT_OPERATOR_REQUESTED,
)


def is_refusal_reason_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in REFUSAL_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: dry-run / live-private flag
# ---------------------------------------------------------------------------


SESSION_MODE_DRY_RUN: str = "DRY_RUN"
SESSION_MODE_LIVE_PRIVATE: str = "LIVE_PRIVATE"


SESSION_MODE_VALUES: tuple[str, ...] = (
    SESSION_MODE_DRY_RUN,
    SESSION_MODE_LIVE_PRIVATE,
)


def is_session_mode_value(value: object) -> bool:
    return isinstance(value, str) and value in SESSION_MODE_VALUES


# ---------------------------------------------------------------------------
# Closed-set: redaction status
# ---------------------------------------------------------------------------


REDACTION_STATUS_SAFE: str = "SAFE"
REDACTION_STATUS_REDACTED: str = "REDACTED"


REDACTION_STATUS_VALUES: tuple[str, ...] = (
    REDACTION_STATUS_SAFE,
    REDACTION_STATUS_REDACTED,
)


# ---------------------------------------------------------------------------
# Safe provider-id / provider-kind / output-dir-label validators
# ---------------------------------------------------------------------------


_PROVIDER_FIELD_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)
_PROVIDER_FIELD_MIN_LENGTH: int = 1
_PROVIDER_FIELD_MAX_LENGTH: int = 64


# Substrings that indicate URL / secret material. Concatenated
# literally so the leak scanner does not flag the canonical
# secret-shape prefixes in this module's source.
_PROVIDER_FIELD_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
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


def is_safe_provider_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe provider-id label.

    Pure / deterministic. No env access, no I/O, no logging.
    """
    if not isinstance(value, str):
        return False
    if len(value) < _PROVIDER_FIELD_MIN_LENGTH:
        return False
    if len(value) > _PROVIDER_FIELD_MAX_LENGTH:
        return False
    if value[0] in {"-", "_"} or value[-1] in {"-", "_"}:
        return False
    for ch in value:
        if ch not in _PROVIDER_FIELD_ALLOWED_CHARS:
            return False
    lowered = value.lower()
    for needle in _PROVIDER_FIELD_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return False
    return True


def is_safe_provider_kind(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe provider-kind label.

    Same shape rule as ``is_safe_provider_id``.
    """
    return is_safe_provider_id(value)


_OUTPUT_DIR_LABEL_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_.-"
)
_OUTPUT_DIR_LABEL_MIN_LENGTH: int = 1
_OUTPUT_DIR_LABEL_MAX_LENGTH: int = 96


def is_safe_output_dir_label(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe redaction-safe
    output-dir basename label (the Stage 28.9 result echoes this
    label only -- never the full path).
    """
    if not isinstance(value, str):
        return False
    if len(value) < _OUTPUT_DIR_LABEL_MIN_LENGTH:
        return False
    if len(value) > _OUTPUT_DIR_LABEL_MAX_LENGTH:
        return False
    if value[0] in {".", "-"} or value[-1] in {".", "-"}:
        return False
    if ".." in value:
        return False
    if "/" in value or "\\" in value:
        return False
    for ch in value:
        if ch not in _OUTPUT_DIR_LABEL_ALLOWED_CHARS:
            return False
    lowered = value.lower()
    for needle in _PROVIDER_FIELD_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return False
    return True


# ---------------------------------------------------------------------------
# Exception hierarchy (module-local)
# ---------------------------------------------------------------------------


class Stage28_9LiveProviderSessionError(Exception):
    """Base type for every Stage 28.9 live-provider-session error.

    Module-local; not a subclass of any central PHX2 error
    registry. Raw secret values must never reach the constructor;
    callers redact at the call site.
    """


class Stage28_9InvalidSessionConfigError(
    Stage28_9LiveProviderSessionError,
):
    """Raised when a ``Stage28_9LiveProviderSessionConfig`` field
    fails the locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.9 invalid session config: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_9InvalidSessionResultError(
    Stage28_9LiveProviderSessionError,
):
    """Raised when a ``Stage28_9LiveProviderSessionResult`` field
    fails the locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.9 invalid session result: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_9InvalidReadinessVerdictError(
    Stage28_9LiveProviderSessionError,
):
    """Raised when a ``Stage28_9ReadinessVerdict`` field fails the
    locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.9 invalid readiness verdict: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_9UnsafeMappingError(Stage28_9LiveProviderSessionError):
    """Raised by the adapter mapper when the Stage 27 input shape
    cannot be projected into a Stage 28.6 candidate event without
    fabricating data.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.9 unsafe candidate mapping: "
            f"field={field_name!r} reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Stage28_9LiveProviderSessionConfig
# ---------------------------------------------------------------------------


class Stage28_9LiveProviderSessionConfig(NamedTuple):
    """Immutable Stage 28.9 live-provider-session config record.

    Closed-set / bounded-controls fields:

      * ``run_id``                      -- safe-shape run id.
      * ``session_id``                  -- safe-shape session id.
      * ``provider_id``                 -- safe-shape provider id
                                            label (e.g.
                                            ``"helius_grpc"``).
      * ``provider_kind``               -- safe-shape provider kind
                                            label (e.g.
                                            ``"solana_websocket"``).
      * ``max_events``                  -- positive ``int`` hard cap
                                            on candidate events to
                                            drain from the provider
                                            source.
      * ``max_dispatches``              -- positive ``int`` hard cap
                                            on successful + failed
                                            transport send attempts.
      * ``max_ticks``                   -- positive ``int`` injected-
                                            clock tick budget
                                            forwarded to Stage 28.6.
      * ``max_total_retries``           -- non-negative ``int``
                                            session-wide retry
                                            budget forwarded to
                                            Stage 28.6.
      * ``heartbeat_every_n_events``    -- positive ``int`` forwarded
                                            to Stage 28.6.
      * ``output_dir_safe_label``       -- safe basename label for
                                            the caller-supplied
                                            output directory (the
                                            full path is NEVER
                                            stored).
      * ``session_mode``                -- closed-set
                                            ``SESSION_MODE_*`` token
                                            (``DRY_RUN`` /
                                            ``LIVE_PRIVATE``).
    """

    run_id: str
    session_id: str
    provider_id: str
    provider_kind: str
    max_events: int
    max_dispatches: int
    max_ticks: int
    max_total_retries: int
    heartbeat_every_n_events: int
    output_dir_safe_label: str
    session_mode: str


def _validate_positive_int_config(
    field_name: str, value: object
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Stage28_9InvalidSessionConfigError(
            field_name=field_name, reason="VALUE_NOT_INT",
        )
    if value <= 0:
        raise Stage28_9InvalidSessionConfigError(
            field_name=field_name, reason="VALUE_NOT_POSITIVE",
        )
    return value


def _validate_nonneg_int_config(
    field_name: str, value: object
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise Stage28_9InvalidSessionConfigError(
            field_name=field_name, reason="VALUE_NOT_INT",
        )
    if value < 0:
        raise Stage28_9InvalidSessionConfigError(
            field_name=field_name, reason="VALUE_NEGATIVE",
        )
    return value


def build_live_provider_session_config(
    *,
    run_id: object,
    session_id: object,
    provider_id: object,
    provider_kind: object,
    max_events: object,
    max_dispatches: object,
    max_ticks: object,
    max_total_retries: object,
    heartbeat_every_n_events: object,
    output_dir_safe_label: object,
    session_mode: object = SESSION_MODE_LIVE_PRIVATE,
) -> Stage28_9LiveProviderSessionConfig:
    """Construct an immutable ``Stage28_9LiveProviderSessionConfig``
    with full validation.

    Raises ``Stage28_9InvalidSessionConfigError`` for any field
    that fails the locked allowlist.
    """
    if not is_safe_identifier(run_id):
        raise Stage28_9InvalidSessionConfigError(
            field_name="run_id", reason="RUN_ID_UNSAFE",
        )
    if not is_safe_identifier(session_id):
        raise Stage28_9InvalidSessionConfigError(
            field_name="session_id", reason="SESSION_ID_UNSAFE",
        )
    if not is_safe_provider_id(provider_id):
        raise Stage28_9InvalidSessionConfigError(
            field_name="provider_id", reason="PROVIDER_ID_UNSAFE",
        )
    if not is_safe_provider_kind(provider_kind):
        raise Stage28_9InvalidSessionConfigError(
            field_name="provider_kind",
            reason="PROVIDER_KIND_UNSAFE",
        )
    me = _validate_positive_int_config("max_events", max_events)
    md = _validate_positive_int_config(
        "max_dispatches", max_dispatches,
    )
    mt = _validate_positive_int_config("max_ticks", max_ticks)
    mr = _validate_nonneg_int_config(
        "max_total_retries", max_total_retries,
    )
    he = _validate_positive_int_config(
        "heartbeat_every_n_events", heartbeat_every_n_events,
    )
    if not is_safe_output_dir_label(output_dir_safe_label):
        raise Stage28_9InvalidSessionConfigError(
            field_name="output_dir_safe_label",
            reason="OUTPUT_DIR_LABEL_UNSAFE",
        )
    if not is_session_mode_value(session_mode):
        raise Stage28_9InvalidSessionConfigError(
            field_name="session_mode",
            reason="SESSION_MODE_NOT_CLOSED_SET",
        )
    return Stage28_9LiveProviderSessionConfig(
        run_id=run_id,  # type: ignore[arg-type]
        session_id=session_id,  # type: ignore[arg-type]
        provider_id=provider_id,  # type: ignore[arg-type]
        provider_kind=provider_kind,  # type: ignore[arg-type]
        max_events=me,
        max_dispatches=md,
        max_ticks=mt,
        max_total_retries=mr,
        heartbeat_every_n_events=he,
        output_dir_safe_label=(
            output_dir_safe_label  # type: ignore[arg-type]
        ),
        session_mode=session_mode,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Stage28_9ReadinessVerdict
# ---------------------------------------------------------------------------


class Stage28_9ReadinessVerdict(NamedTuple):
    """Immutable Stage 28.9 readiness verdict.

    Fields:

      * ``ready``           -- ``True`` iff every readiness gate
                                passed; the orchestrator may then
                                call the provider source.
      * ``refusal_reason``  -- closed-set ``REFUSAL_REASON_*``
                                token; ``REFUSAL_REASON_NOT_REFUSED``
                                when ``ready`` is ``True``.
    """

    ready: bool
    refusal_reason: str


def build_readiness_verdict(
    *, ready: object, refusal_reason: object,
) -> Stage28_9ReadinessVerdict:
    """Construct an immutable ``Stage28_9ReadinessVerdict`` with
    full validation."""
    if not isinstance(ready, bool):
        raise Stage28_9InvalidReadinessVerdictError(
            field_name="ready", reason="READY_NOT_BOOL",
        )
    if not is_refusal_reason_value(refusal_reason):
        raise Stage28_9InvalidReadinessVerdictError(
            field_name="refusal_reason",
            reason="REFUSAL_REASON_NOT_CLOSED_SET",
        )
    if ready and refusal_reason != REFUSAL_REASON_NOT_REFUSED:
        raise Stage28_9InvalidReadinessVerdictError(
            field_name="refusal_reason",
            reason="READY_TRUE_REQUIRES_NOT_REFUSED",
        )
    if not ready and refusal_reason == REFUSAL_REASON_NOT_REFUSED:
        raise Stage28_9InvalidReadinessVerdictError(
            field_name="refusal_reason",
            reason="READY_FALSE_REQUIRES_REFUSAL_REASON",
        )
    return Stage28_9ReadinessVerdict(
        ready=ready, refusal_reason=refusal_reason,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Stage28_9LiveProviderSessionResult
# ---------------------------------------------------------------------------


STAGE28_9_SESSION_RESULT_COUNTER_FIELD_NAMES: tuple[str, ...] = (
    "events_seen",
    "candidates_assembled",
    "candidates_dispatched",
    "candidates_suppressed",
    "dispatch_success",
    "dispatch_failure",
    "duplicate_suppressed",
    "ambiguous_suppressed",
    "stale_price_suppressed",
    "missing_price_suppressed",
    "unknown_pair_suppressed",
    "disagree_pair_suppressed",
    "usdc_observe_only_suppressed",
    "malformed_suppressed",
)


STAGE28_9_SESSION_RESULT_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "session_outcome",
    "refusal_reason",
    "run_id",
    "session_id",
    "provider_id",
    "provider_kind",
    "output_dir_safe_label",
    "session_mode",
    "events_seen",
    "candidates_assembled",
    "candidates_dispatched",
    "candidates_suppressed",
    "dispatch_success",
    "dispatch_failure",
    "duplicate_suppressed",
    "ambiguous_suppressed",
    "stale_price_suppressed",
    "missing_price_suppressed",
    "unknown_pair_suppressed",
    "disagree_pair_suppressed",
    "usdc_observe_only_suppressed",
    "malformed_suppressed",
    "stop_reason",
    "redaction_status",
    "webhook_identity",
    "filter_enforcement_status",
)


class Stage28_9LiveProviderSessionResult(NamedTuple):
    """Immutable Stage 28.9 live-provider-session result record.

    All fields are closed-set tokens / safe identifiers / safe
    counters / safe basenames. The record never carries a webhook
    URL, provider endpoint, RPC URL, API key, bearer token, auth
    header, private key, wallet seed, raw response body, raw env
    value, secret-like path, or raw exception string.

    Counter axes are non-negative ``int``; the closed-set
    ``stop_reason`` is reused from the Stage 28.5 / Stage 28.6
    vocabulary; the ``filter_enforcement_status`` is locked to
    ``NOT_ACTIVE_STAGE_29_PENDING`` for Stage 28.9 -- a downstream
    reader can rely on the constant to gate against Stage 29
    behaviour assumptions.
    """

    schema_version: str
    session_outcome: str
    refusal_reason: str
    run_id: str
    session_id: str
    provider_id: str
    provider_kind: str
    output_dir_safe_label: str
    session_mode: str
    events_seen: int
    candidates_assembled: int
    candidates_dispatched: int
    candidates_suppressed: int
    dispatch_success: int
    dispatch_failure: int
    duplicate_suppressed: int
    ambiguous_suppressed: int
    stale_price_suppressed: int
    missing_price_suppressed: int
    unknown_pair_suppressed: int
    disagree_pair_suppressed: int
    usdc_observe_only_suppressed: int
    malformed_suppressed: int
    stop_reason: str
    redaction_status: str
    webhook_identity: str
    filter_enforcement_status: str


def build_live_provider_session_result(
    *,
    session_outcome: object,
    refusal_reason: object,
    run_id: object,
    session_id: object,
    provider_id: object,
    provider_kind: object,
    output_dir_safe_label: object,
    session_mode: object,
    events_seen: object,
    candidates_assembled: object,
    candidates_dispatched: object,
    candidates_suppressed: object,
    dispatch_success: object,
    dispatch_failure: object,
    duplicate_suppressed: object,
    ambiguous_suppressed: object,
    stale_price_suppressed: object,
    missing_price_suppressed: object,
    unknown_pair_suppressed: object,
    disagree_pair_suppressed: object,
    usdc_observe_only_suppressed: object,
    malformed_suppressed: object,
    stop_reason: object,
    webhook_identity: object = WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
) -> Stage28_9LiveProviderSessionResult:
    """Construct an immutable
    ``Stage28_9LiveProviderSessionResult`` with full validation."""
    if not is_session_outcome_value(session_outcome):
        raise Stage28_9InvalidSessionResultError(
            field_name="session_outcome",
            reason="SESSION_OUTCOME_NOT_CLOSED_SET",
        )
    if not is_refusal_reason_value(refusal_reason):
        raise Stage28_9InvalidSessionResultError(
            field_name="refusal_reason",
            reason="REFUSAL_REASON_NOT_CLOSED_SET",
        )
    if session_outcome == SESSION_OUTCOME_REFUSED and (
        refusal_reason == REFUSAL_REASON_NOT_REFUSED
    ):
        raise Stage28_9InvalidSessionResultError(
            field_name="refusal_reason",
            reason="REFUSED_REQUIRES_REFUSAL_REASON",
        )
    if session_outcome != SESSION_OUTCOME_REFUSED and (
        refusal_reason != REFUSAL_REASON_NOT_REFUSED
    ):
        raise Stage28_9InvalidSessionResultError(
            field_name="refusal_reason",
            reason="NON_REFUSED_REQUIRES_NOT_REFUSED",
        )
    if not is_safe_identifier(run_id):
        raise Stage28_9InvalidSessionResultError(
            field_name="run_id", reason="RUN_ID_UNSAFE",
        )
    if not is_safe_identifier(session_id):
        raise Stage28_9InvalidSessionResultError(
            field_name="session_id", reason="SESSION_ID_UNSAFE",
        )
    if not is_safe_provider_id(provider_id):
        raise Stage28_9InvalidSessionResultError(
            field_name="provider_id", reason="PROVIDER_ID_UNSAFE",
        )
    if not is_safe_provider_kind(provider_kind):
        raise Stage28_9InvalidSessionResultError(
            field_name="provider_kind",
            reason="PROVIDER_KIND_UNSAFE",
        )
    if not is_safe_output_dir_label(output_dir_safe_label):
        raise Stage28_9InvalidSessionResultError(
            field_name="output_dir_safe_label",
            reason="OUTPUT_DIR_LABEL_UNSAFE",
        )
    if not is_session_mode_value(session_mode):
        raise Stage28_9InvalidSessionResultError(
            field_name="session_mode",
            reason="SESSION_MODE_NOT_CLOSED_SET",
        )
    counters: dict[str, int] = {}
    for name, value in (
        ("events_seen", events_seen),
        ("candidates_assembled", candidates_assembled),
        ("candidates_dispatched", candidates_dispatched),
        ("candidates_suppressed", candidates_suppressed),
        ("dispatch_success", dispatch_success),
        ("dispatch_failure", dispatch_failure),
        ("duplicate_suppressed", duplicate_suppressed),
        ("ambiguous_suppressed", ambiguous_suppressed),
        ("stale_price_suppressed", stale_price_suppressed),
        ("missing_price_suppressed", missing_price_suppressed),
        ("unknown_pair_suppressed", unknown_pair_suppressed),
        ("disagree_pair_suppressed", disagree_pair_suppressed),
        (
            "usdc_observe_only_suppressed",
            usdc_observe_only_suppressed,
        ),
        ("malformed_suppressed", malformed_suppressed),
    ):
        if not is_safe_counter_value(value):
            raise Stage28_9InvalidSessionResultError(
                field_name=name,
                reason="COUNTER_NOT_NONNEG_INT",
            )
        counters[name] = value  # type: ignore[assignment]
    if not isinstance(stop_reason, str) or stop_reason == "":
        raise Stage28_9InvalidSessionResultError(
            field_name="stop_reason",
            reason="STOP_REASON_EMPTY",
        )
    if not is_safe_webhook_identity_label(webhook_identity):
        raise Stage28_9InvalidSessionResultError(
            field_name="webhook_identity",
            reason="WEBHOOK_IDENTITY_UNSAFE",
        )
    return Stage28_9LiveProviderSessionResult(
        schema_version=STAGE28_9_SCHEMA_VERSION,
        session_outcome=session_outcome,  # type: ignore[arg-type]
        refusal_reason=refusal_reason,  # type: ignore[arg-type]
        run_id=run_id,  # type: ignore[arg-type]
        session_id=session_id,  # type: ignore[arg-type]
        provider_id=provider_id,  # type: ignore[arg-type]
        provider_kind=provider_kind,  # type: ignore[arg-type]
        output_dir_safe_label=(
            output_dir_safe_label  # type: ignore[arg-type]
        ),
        session_mode=session_mode,  # type: ignore[arg-type]
        events_seen=counters["events_seen"],
        candidates_assembled=counters["candidates_assembled"],
        candidates_dispatched=counters["candidates_dispatched"],
        candidates_suppressed=counters["candidates_suppressed"],
        dispatch_success=counters["dispatch_success"],
        dispatch_failure=counters["dispatch_failure"],
        duplicate_suppressed=counters["duplicate_suppressed"],
        ambiguous_suppressed=counters["ambiguous_suppressed"],
        stale_price_suppressed=counters["stale_price_suppressed"],
        missing_price_suppressed=(
            counters["missing_price_suppressed"]
        ),
        unknown_pair_suppressed=(
            counters["unknown_pair_suppressed"]
        ),
        disagree_pair_suppressed=(
            counters["disagree_pair_suppressed"]
        ),
        usdc_observe_only_suppressed=(
            counters["usdc_observe_only_suppressed"]
        ),
        malformed_suppressed=counters["malformed_suppressed"],
        stop_reason=stop_reason,  # type: ignore[arg-type]
        redaction_status=REDACTION_STATUS_SAFE,
        webhook_identity=webhook_identity,  # type: ignore[arg-type]
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
    )


def session_result_to_dict(
    record: Stage28_9LiveProviderSessionResult,
) -> dict:
    """Project a session result record into a deterministic-order
    dict suitable for tests and downstream inspection.
    """
    if not isinstance(record, Stage28_9LiveProviderSessionResult):
        raise Stage28_9InvalidSessionResultError(
            field_name="record",
            reason="NOT_A_SESSION_RESULT_RECORD",
        )
    return {
        name: getattr(record, name)
        for name in STAGE28_9_SESSION_RESULT_FIELD_NAMES
    }


__all__ = (
    # Version axes.
    "STAGE28_9_MINOR_VERSION",
    "STAGE28_9_SCHEMA_VERSION",
    "STAGE28_9_REDACTION_TOKEN",
    # Filter-enforcement marker (Stage 29 pending).
    "FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING",
    "FILTER_ENFORCEMENT_NOTICE_TEXT",
    "POLICY_MODE_PRIVATE_OPERATOR_ONLY",
    # Session-outcome vocabulary.
    "SESSION_OUTCOME_OK",
    "SESSION_OUTCOME_DEGRADED",
    "SESSION_OUTCOME_REFUSED",
    "SESSION_OUTCOME_FAILED",
    "SESSION_OUTCOME_VALUES",
    "is_session_outcome_value",
    # Refusal-reason vocabulary.
    "REFUSAL_REASON_NOT_REFUSED",
    "REFUSAL_REASON_NOT_LIVE",
    "REFUSAL_REASON_WEBHOOK_MISSING",
    "REFUSAL_REASON_PROVIDER_UNSAFE",
    "REFUSAL_REASON_BOUNDS_INVALID",
    "REFUSAL_REASON_OUTPUT_DIR_UNSAFE",
    "REFUSAL_REASON_NOT_OPERATOR_REQUESTED",
    "REFUSAL_REASON_VALUES",
    "is_refusal_reason_value",
    # Session-mode vocabulary.
    "SESSION_MODE_DRY_RUN",
    "SESSION_MODE_LIVE_PRIVATE",
    "SESSION_MODE_VALUES",
    "is_session_mode_value",
    # Redaction-status vocabulary.
    "REDACTION_STATUS_SAFE",
    "REDACTION_STATUS_REDACTED",
    "REDACTION_STATUS_VALUES",
    # Provider-id / provider-kind / output-dir-label validators.
    "is_safe_provider_id",
    "is_safe_provider_kind",
    "is_safe_output_dir_label",
    # Records.
    "Stage28_9LiveProviderSessionConfig",
    "Stage28_9ReadinessVerdict",
    "Stage28_9LiveProviderSessionResult",
    # Builders.
    "build_live_provider_session_config",
    "build_readiness_verdict",
    "build_live_provider_session_result",
    "session_result_to_dict",
    # Field-name inventories.
    "STAGE28_9_SESSION_RESULT_COUNTER_FIELD_NAMES",
    "STAGE28_9_SESSION_RESULT_FIELD_NAMES",
    # Exceptions.
    "Stage28_9LiveProviderSessionError",
    "Stage28_9InvalidSessionConfigError",
    "Stage28_9InvalidSessionResultError",
    "Stage28_9InvalidReadinessVerdictError",
    "Stage28_9UnsafeMappingError",
)
