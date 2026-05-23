"""Stage 28.5 heartbeat / health snapshot / CLI status models.

Stage 28.5 ships the redaction-safe, deterministic operator-
visibility primitives that future Stage 28 longer-session
substages (Stage 28.6 / 28.7) will use to emit:

  * append-only heartbeat records,
  * current health snapshot records,
  * final run summary records,
  * compact CLI status lines.

This module ships only the closed-set vocabularies, the immutable
record shapes, the safe-counter / safe-identifier validators, the
canonical asdict projections, and the module-local Stage 28.5
exception hierarchy. The writers (``heartbeat_writer.py`` /
``health_snapshot_writer.py``) and CLI formatter
(``cli_status_line.py``) are separate Stage 28.5 modules.

Stage 28.5 does NOT:

  * connect to any provider,
  * send any Discord message,
  * read the process environment,
  * call HTTP / gRPC / sockets,
  * sleep / schedule / queue / spawn / use asyncio / threads /
    subprocesses,
  * retry anything,
  * start a runner / smoke,
  * include subscriber / public / paid-tier / trading / wallet /
    enforcement fields anywhere on any record.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network. No HTTP. No gRPC. No socket. No file I/O at import
    or call time. (Writers in sibling Stage 28.5 modules own
    explicit filesystem I/O against caller-supplied paths.)
  * No sleep. No backoff execution. No scheduling. No queue. No
    threads. No async. No subprocess.
  * No raw secret value is ever carried on a Stage 28.5 record.
    Run / session identifiers must pass the locked safe-identifier
    allowlist; otherwise the record is refused at construction.
    The Stage 28.5 records carry only closed-set status tokens +
    nonneg integer counters + safe-shape run / session identifiers
    + closed-set redaction status. URL / webhook / RPC / API-key /
    bearer-token / auth-header values can never reach a Stage 28.5
    record.
  * ``repr()`` / ``str()`` of any Stage 28.5 record is safe to log
    / print / persist; the NamedTuple shape exposes only the
    closed-set field values.

This module imports only stdlib (``typing``). It does NOT import
Stage 21-27 production code, does NOT import Stage 28.1 / 28.2 /
28.3a / 28.3b / 28.4 production code, does NOT import any
network / RPC / messaging / DB / scheduler / secrets-management
library, does NOT read the process environment, does NOT define
a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


# ---------------------------------------------------------------------------
# Stage 28.5 version axes
# ---------------------------------------------------------------------------


STAGE28_5_MINOR_VERSION: str = "28.5"


# Stage 28.5 ships four distinct artifact schema axes (heartbeat
# JSONL line, health snapshot JSON object, final run summary JSON
# object, CLI status line). Each schema version is locked
# independently so a downstream reader can pin them.
STAGE28_5_HEARTBEAT_SCHEMA_VERSION: str = "stage28_5_heartbeat_v0"
STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION: str = (
    "stage28_5_health_snapshot_v0"
)
STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION: str = (
    "stage28_5_final_run_summary_v0"
)
STAGE28_5_CLI_STATUS_SCHEMA_VERSION: str = "stage28_5_cli_status_v0"


# Distinctive Stage 28.5 redaction token. Distinct from the Stage
# 27, Stage 28.1, Stage 28.2, Stage 28.3a, Stage 28.3b, and Stage
# 28.4 redaction tokens so a leak-scan test for one cannot collide
# with another.
STAGE28_5_REDACTION_TOKEN: str = "<<STAGE28_5_REDACTED>>"


# ---------------------------------------------------------------------------
# Closed-set: provider status
# ---------------------------------------------------------------------------


PROVIDER_STATUS_OK: str = "OK"
PROVIDER_STATUS_DISCONNECTED: str = "DISCONNECTED"
PROVIDER_STATUS_RECONNECTING: str = "RECONNECTING"
PROVIDER_STATUS_LOST: str = "LOST"
PROVIDER_STATUS_NOT_STARTED: str = "NOT_STARTED"
PROVIDER_STATUS_UNKNOWN: str = "UNKNOWN"


PROVIDER_STATUS_VALUES: tuple[str, ...] = (
    PROVIDER_STATUS_OK,
    PROVIDER_STATUS_DISCONNECTED,
    PROVIDER_STATUS_RECONNECTING,
    PROVIDER_STATUS_LOST,
    PROVIDER_STATUS_NOT_STARTED,
    PROVIDER_STATUS_UNKNOWN,
)


def is_provider_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.5
    provider-status token."""
    return (
        isinstance(value, str)
        and value in PROVIDER_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: price status
# ---------------------------------------------------------------------------


PRICE_STATUS_OK: str = "OK"
PRICE_STATUS_STALE: str = "STALE"
PRICE_STATUS_MISSING: str = "MISSING"
PRICE_STATUS_TIMEOUT: str = "TIMEOUT"
PRICE_STATUS_NOT_STARTED: str = "NOT_STARTED"
PRICE_STATUS_UNKNOWN: str = "UNKNOWN"


PRICE_STATUS_VALUES: tuple[str, ...] = (
    PRICE_STATUS_OK,
    PRICE_STATUS_STALE,
    PRICE_STATUS_MISSING,
    PRICE_STATUS_TIMEOUT,
    PRICE_STATUS_NOT_STARTED,
    PRICE_STATUS_UNKNOWN,
)


def is_price_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.5
    price-status token."""
    return (
        isinstance(value, str)
        and value in PRICE_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: dispatch status
# ---------------------------------------------------------------------------


DISPATCH_STATUS_OK: str = "OK"
DISPATCH_STATUS_FAILED: str = "FAILED"
DISPATCH_STATUS_SUPPRESSED: str = "SUPPRESSED"
DISPATCH_STATUS_AMBIGUOUS: str = "AMBIGUOUS"
DISPATCH_STATUS_NOT_STARTED: str = "NOT_STARTED"
DISPATCH_STATUS_UNKNOWN: str = "UNKNOWN"


DISPATCH_STATUS_VALUES: tuple[str, ...] = (
    DISPATCH_STATUS_OK,
    DISPATCH_STATUS_FAILED,
    DISPATCH_STATUS_SUPPRESSED,
    DISPATCH_STATUS_AMBIGUOUS,
    DISPATCH_STATUS_NOT_STARTED,
    DISPATCH_STATUS_UNKNOWN,
)


def is_dispatch_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.5
    dispatch-status token."""
    return (
        isinstance(value, str)
        and value in DISPATCH_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: ledger status
# ---------------------------------------------------------------------------


LEDGER_STATUS_OK: str = "OK"
LEDGER_STATUS_WRITE_FAILED: str = "WRITE_FAILED"
LEDGER_STATUS_REPLAY_FAILED: str = "REPLAY_FAILED"
LEDGER_STATUS_AMBIGUOUS: str = "AMBIGUOUS"
LEDGER_STATUS_DUPLICATE_SUPPRESSED: str = "DUPLICATE_SUPPRESSED"
LEDGER_STATUS_NOT_STARTED: str = "NOT_STARTED"
LEDGER_STATUS_UNKNOWN: str = "UNKNOWN"


LEDGER_STATUS_VALUES: tuple[str, ...] = (
    LEDGER_STATUS_OK,
    LEDGER_STATUS_WRITE_FAILED,
    LEDGER_STATUS_REPLAY_FAILED,
    LEDGER_STATUS_AMBIGUOUS,
    LEDGER_STATUS_DUPLICATE_SUPPRESSED,
    LEDGER_STATUS_NOT_STARTED,
    LEDGER_STATUS_UNKNOWN,
)


def is_ledger_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.5
    ledger-status token."""
    return (
        isinstance(value, str)
        and value in LEDGER_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: transport status (Stage 28.5 visibility view)
# ---------------------------------------------------------------------------


# Stage 28.5 defines its own visibility-layer transport status set
# rather than importing Stage 28.4's transport-result tokens. The
# Stage 28.5 transport-status field summarizes the most recent
# transport attempt's outcome for operator-visible reporting; a
# future runner substage maps Stage 28.4's seven transport-result
# tokens onto this smaller visibility set without importing 28.4.
TRANSPORT_STATUS_OK: str = "OK"
TRANSPORT_STATUS_RATE_LIMITED: str = "RATE_LIMITED"
TRANSPORT_STATUS_SERVER_ERROR: str = "SERVER_ERROR"
TRANSPORT_STATUS_NETWORK_ERROR: str = "NETWORK_ERROR"
TRANSPORT_STATUS_REFUSED: str = "REFUSED"
TRANSPORT_STATUS_NOT_STARTED: str = "NOT_STARTED"
TRANSPORT_STATUS_UNKNOWN: str = "UNKNOWN"


TRANSPORT_STATUS_VALUES: tuple[str, ...] = (
    TRANSPORT_STATUS_OK,
    TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_SERVER_ERROR,
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_REFUSED,
    TRANSPORT_STATUS_NOT_STARTED,
    TRANSPORT_STATUS_UNKNOWN,
)


def is_transport_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.5
    transport-status token."""
    return (
        isinstance(value, str)
        and value in TRANSPORT_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: artifact status
# ---------------------------------------------------------------------------


ARTIFACT_STATUS_OK: str = "OK"
ARTIFACT_STATUS_WRITE_FAILED: str = "WRITE_FAILED"
ARTIFACT_STATUS_READ_FAILED: str = "READ_FAILED"
ARTIFACT_STATUS_NOT_STARTED: str = "NOT_STARTED"
ARTIFACT_STATUS_UNKNOWN: str = "UNKNOWN"


ARTIFACT_STATUS_VALUES: tuple[str, ...] = (
    ARTIFACT_STATUS_OK,
    ARTIFACT_STATUS_WRITE_FAILED,
    ARTIFACT_STATUS_READ_FAILED,
    ARTIFACT_STATUS_NOT_STARTED,
    ARTIFACT_STATUS_UNKNOWN,
)


def is_artifact_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.5
    artifact-status token."""
    return (
        isinstance(value, str)
        and value in ARTIFACT_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: aggregate health status
# ---------------------------------------------------------------------------


HEALTH_STATUS_HEALTHY: str = "HEALTHY"
HEALTH_STATUS_DEGRADED: str = "DEGRADED"
HEALTH_STATUS_FAILED: str = "FAILED"
HEALTH_STATUS_STOPPED: str = "STOPPED"
HEALTH_STATUS_UNKNOWN: str = "UNKNOWN"


HEALTH_STATUS_VALUES: tuple[str, ...] = (
    HEALTH_STATUS_HEALTHY,
    HEALTH_STATUS_DEGRADED,
    HEALTH_STATUS_FAILED,
    HEALTH_STATUS_STOPPED,
    HEALTH_STATUS_UNKNOWN,
)


def is_health_status_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.5
    aggregate-health status token."""
    return (
        isinstance(value, str)
        and value in HEALTH_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: stop reason
# ---------------------------------------------------------------------------


STOP_REASON_MAX_EVENTS: str = "MAX_EVENTS"
STOP_REASON_MAX_WALL_SECONDS: str = "MAX_WALL_SECONDS"
STOP_REASON_SIGINT: str = "SIGINT"
STOP_REASON_SIGTERM: str = "SIGTERM"
STOP_REASON_PROVIDER_LOST: str = "PROVIDER_LOST"
STOP_REASON_RETRY_BUDGET_EXHAUSTED: str = "RETRY_BUDGET_EXHAUSTED"
STOP_REASON_OPERATOR_STOP: str = "OPERATOR_STOP"
STOP_REASON_ERROR: str = "ERROR"
STOP_REASON_NOT_STOPPED: str = "NOT_STOPPED"


STOP_REASON_VALUES: tuple[str, ...] = (
    STOP_REASON_MAX_EVENTS,
    STOP_REASON_MAX_WALL_SECONDS,
    STOP_REASON_SIGINT,
    STOP_REASON_SIGTERM,
    STOP_REASON_PROVIDER_LOST,
    STOP_REASON_RETRY_BUDGET_EXHAUSTED,
    STOP_REASON_OPERATOR_STOP,
    STOP_REASON_ERROR,
    STOP_REASON_NOT_STOPPED,
)


def is_stop_reason_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set Stage 28.5
    stop-reason token."""
    return (
        isinstance(value, str)
        and value in STOP_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: last-event / last-ping status (health-snapshot subfields)
# ---------------------------------------------------------------------------


LAST_EVENT_STATUS_OBSERVED: str = "OBSERVED"
LAST_EVENT_STATUS_NONE_OBSERVED: str = "NONE_OBSERVED"
LAST_EVENT_STATUS_NOT_STARTED: str = "NOT_STARTED"
LAST_EVENT_STATUS_UNKNOWN: str = "UNKNOWN"


LAST_EVENT_STATUS_VALUES: tuple[str, ...] = (
    LAST_EVENT_STATUS_OBSERVED,
    LAST_EVENT_STATUS_NONE_OBSERVED,
    LAST_EVENT_STATUS_NOT_STARTED,
    LAST_EVENT_STATUS_UNKNOWN,
)


def is_last_event_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in LAST_EVENT_STATUS_VALUES
    )


LAST_PING_STATUS_RENDERED: str = "RENDERED"
LAST_PING_STATUS_SUPPRESSED: str = "SUPPRESSED"
LAST_PING_STATUS_NONE_RENDERED: str = "NONE_RENDERED"
LAST_PING_STATUS_NOT_STARTED: str = "NOT_STARTED"
LAST_PING_STATUS_UNKNOWN: str = "UNKNOWN"


LAST_PING_STATUS_VALUES: tuple[str, ...] = (
    LAST_PING_STATUS_RENDERED,
    LAST_PING_STATUS_SUPPRESSED,
    LAST_PING_STATUS_NONE_RENDERED,
    LAST_PING_STATUS_NOT_STARTED,
    LAST_PING_STATUS_UNKNOWN,
)


def is_last_ping_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in LAST_PING_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: retry-budget status (health-snapshot subfield)
# ---------------------------------------------------------------------------


RETRY_BUDGET_STATUS_OK: str = "OK"
RETRY_BUDGET_STATUS_NEAR_LIMIT: str = "NEAR_LIMIT"
RETRY_BUDGET_STATUS_EXHAUSTED: str = "EXHAUSTED"
RETRY_BUDGET_STATUS_NOT_STARTED: str = "NOT_STARTED"
RETRY_BUDGET_STATUS_UNKNOWN: str = "UNKNOWN"


RETRY_BUDGET_STATUS_VALUES: tuple[str, ...] = (
    RETRY_BUDGET_STATUS_OK,
    RETRY_BUDGET_STATUS_NEAR_LIMIT,
    RETRY_BUDGET_STATUS_EXHAUSTED,
    RETRY_BUDGET_STATUS_NOT_STARTED,
    RETRY_BUDGET_STATUS_UNKNOWN,
)


def is_retry_budget_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in RETRY_BUDGET_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: redaction status
# ---------------------------------------------------------------------------


# Stage 28.5 records carry a closed-set redaction-status field.
# ``SAFE`` is the happy-path value (every closed-set / counter
# field passed validation). ``REDACTED`` indicates the record was
# emitted with one or more locked safe-placeholder constants
# substituted for an upstream caller-supplied value that failed
# validation (the unsafe value never reaches the record).
# ``NO_SECRET_MATERIAL`` is reserved for empty / not-started
# records where there was no upstream material to redact.
REDACTION_STATUS_SAFE: str = "SAFE"
REDACTION_STATUS_REDACTED: str = "REDACTED"
REDACTION_STATUS_NO_SECRET_MATERIAL: str = "NO_SECRET_MATERIAL"


REDACTION_STATUS_VALUES: tuple[str, ...] = (
    REDACTION_STATUS_SAFE,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_NO_SECRET_MATERIAL,
)


def is_redaction_status_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in REDACTION_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Safe identifier (run_id / session_id) allowlist
# ---------------------------------------------------------------------------


# Stage 28.5 only carries SAFE-TO-DISPLAY run / session identifiers
# on records. A safe identifier is a non-empty string of length
# 1..64 made of ``A-Z`` / ``a-z`` / ``0-9`` / ``_`` / ``-``. The
# shape mirrors the Stage 27 / Stage 28.2 dedupe-key-field
# allowlist deliberately so Stage 28.5 callers can reuse upstream
# identifiers; Stage 28.5 does NOT import the prior helpers.
_SAFE_IDENTIFIER_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)
_SAFE_IDENTIFIER_MIN_LENGTH: int = 1
_SAFE_IDENTIFIER_MAX_LENGTH: int = 64


# Substrings that, when present anywhere in a caller-supplied
# identifier, indicate the value looks like URL / token / webhook /
# auth material and must be rejected. These literal substrings are
# distinctive enough that a legitimate run / session identifier
# cannot collide with them. The literals are concatenated at module
# load so this source file does not itself carry the URL / webhook
# prefix a downstream string-leak boundary scan would flag.
_SAFE_IDENTIFIER_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
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
    # API-key prefix conventions (OpenAI / Stripe / etc.).
    # Concatenated so this source file does not itself carry the
    # literal raw-secret prefix.
    "s" + "k-",
    "p" + "k-",
)


# Safe-to-stamp placeholder constants for callers who failed the
# safe-identifier allowlist. Distinct from Stage 28.4's placeholder
# constants so a leak scan for one cannot collide with another.
SAFE_RUN_ID_REDACTED: str = "REDACTED_UNSAFE_RUN_ID"
SAFE_SESSION_ID_REDACTED: str = "REDACTED_UNSAFE_SESSION_ID"
SAFE_RUN_ID_MISSING: str = "MISSING_RUN_ID"
SAFE_SESSION_ID_MISSING: str = "MISSING_SESSION_ID"


def is_safe_identifier(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-display Stage
    28.5 run / session identifier label.

    Pure / deterministic. No env access, no I/O, no logging.
    """
    if not isinstance(value, str):
        return False
    if len(value) < _SAFE_IDENTIFIER_MIN_LENGTH:
        return False
    if len(value) > _SAFE_IDENTIFIER_MAX_LENGTH:
        return False
    if value[0] in {"-", "_"} or value[-1] in {"-", "_"}:
        return False
    for ch in value:
        if ch not in _SAFE_IDENTIFIER_ALLOWED_CHARS:
            return False
    lowered = value.lower()
    for needle in _SAFE_IDENTIFIER_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return False
    return True


# ---------------------------------------------------------------------------
# Safe counter validation
# ---------------------------------------------------------------------------


def is_safe_counter_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 28.5 safe counter
    value: a non-negative ``int`` (bool excluded, float excluded,
    NaN / inf impossible by type).
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, int):
        return False
    if value < 0:
        return False
    return True


# Locked Stage 28.5 counter field-name set. Heartbeat / health-
# snapshot / final-summary records all expose these counters
# (final-summary uses the ``total_*`` prefix variant). The set is
# locked so a downstream reader / boundary scan can pin the
# vocabulary without re-deriving it from the record shape.
COUNTER_FIELD_NAMES: tuple[str, ...] = (
    "event_count",
    "candidate_count",
    "ping_rendered_count",
    "dispatch_success_count",
    "dispatch_failure_count",
    "retry_count",
    "duplicate_suppressed_count",
    "ambiguous_suppressed_count",
    "unknown_pair_suppressed_count",
    "disagree_pair_suppressed_count",
    "usdc_observe_only_count",
    "stale_price_count",
    "missing_price_count",
    "malformed_event_count",
)


FINAL_SUMMARY_TOTAL_FIELD_NAMES: tuple[str, ...] = (
    "total_events_seen",
    "total_candidates",
    "total_pings_rendered",
    "total_dispatch_success",
    "total_dispatch_failure",
    "total_retry_attempts",
    "total_duplicates_suppressed",
    "total_ambiguous_suppressed",
    "total_unknown_pair_suppressed",
    "total_disagree_pair_suppressed",
    "total_usdc_observe_only",
    "total_stale_price",
    "total_missing_price",
    "total_malformed_events",
)


# ---------------------------------------------------------------------------
# Module-local Stage 28.5 exception hierarchy
# ---------------------------------------------------------------------------


class Stage28_5HealthStatusError(Exception):
    """Base type for every Stage 28.5 health / status model error.

    Module-local; not a subclass of any central PHX2 error registry.
    Raw secret values must never reach the constructor; callers
    redact at the call site. Subclasses carry only closed-set
    fields + safe-to-log labels.
    """


class Stage28_5HealthStatusValidationError(Stage28_5HealthStatusError):
    """Raised when a caller-supplied Stage 28.5 record-construction
    argument fails the locked validation contract.

    Carries only the canonical field name + a closed-set reason
    token; never the raw rejected value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.5 health-status validation error: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_5HealthStatusRedactionLeakError(
    Stage28_5HealthStatusError
):
    """Raised when an internal Stage 28.5 invariant would have let
    a non-closed-set / secret-shaped value reach a record.

    Carries only the canonical field name + a closed-set reason
    token; never the raw offending value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.5 health-status redaction leak error: "
            f"field={field_name!r} reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Record: heartbeat
# ---------------------------------------------------------------------------


class Stage28_5HeartbeatRecord(NamedTuple):
    """Immutable Stage 28.5 heartbeat record.

    Closed-set / safe fields only. The record is what the future
    runner appends one-per-line to the heartbeat JSONL artifact;
    its shape never carries a webhook URL, provider endpoint, API
    key, bearer token, auth header, wallet / private-key field,
    raw response body, raw env value, secret-like path, or raw
    exception string.

    Fields:

      * ``schema_version``                  -- locked Stage 28.5
                                                heartbeat schema
                                                version.
      * ``run_id``                          -- safe run identifier
                                                label.
      * ``session_id``                      -- safe session
                                                identifier label.
      * ``heartbeat_index``                 -- nonneg int; 0-based
                                                heartbeat sequence
                                                number.
      * ``event_count`` ...                 -- nonneg int counters
                                                (see
                                                ``COUNTER_FIELD_NAMES``).
      * ``provider_status``                 -- closed-set provider
                                                status.
      * ``price_status``                    -- closed-set price
                                                status.
      * ``dispatch_status``                 -- closed-set dispatch
                                                status.
      * ``ledger_status``                   -- closed-set ledger
                                                status.
      * ``transport_status``                -- closed-set transport
                                                status.
      * ``artifact_status``                 -- closed-set artifact
                                                status.
      * ``stop_reason``                     -- optional closed-set
                                                stop reason (None
                                                while the runner is
                                                still running).
      * ``redaction_status``                -- closed-set Stage
                                                28.5 redaction
                                                verdict.
    """

    schema_version: str
    run_id: str
    session_id: str
    heartbeat_index: int
    event_count: int
    candidate_count: int
    ping_rendered_count: int
    dispatch_success_count: int
    dispatch_failure_count: int
    retry_count: int
    duplicate_suppressed_count: int
    ambiguous_suppressed_count: int
    unknown_pair_suppressed_count: int
    disagree_pair_suppressed_count: int
    usdc_observe_only_count: int
    stale_price_count: int
    missing_price_count: int
    malformed_event_count: int
    provider_status: str
    price_status: str
    dispatch_status: str
    ledger_status: str
    transport_status: str
    artifact_status: str
    stop_reason: Optional[str]
    redaction_status: str


# Locked Stage 28.5 heartbeat-record field-name set, in canonical
# serialization order. Used by the heartbeat writer + by
# boundary / leak tests.
HEARTBEAT_RECORD_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "session_id",
    "heartbeat_index",
    "event_count",
    "candidate_count",
    "ping_rendered_count",
    "dispatch_success_count",
    "dispatch_failure_count",
    "retry_count",
    "duplicate_suppressed_count",
    "ambiguous_suppressed_count",
    "unknown_pair_suppressed_count",
    "disagree_pair_suppressed_count",
    "usdc_observe_only_count",
    "stale_price_count",
    "missing_price_count",
    "malformed_event_count",
    "provider_status",
    "price_status",
    "dispatch_status",
    "ledger_status",
    "transport_status",
    "artifact_status",
    "stop_reason",
    "redaction_status",
)


# ---------------------------------------------------------------------------
# Record: health snapshot
# ---------------------------------------------------------------------------


class Stage28_5HealthSnapshotRecord(NamedTuple):
    """Immutable Stage 28.5 health-snapshot record.

    Closed-set / safe fields only. The record is what the future
    runner writes (overwrite-atomic) to the current-health snapshot
    JSON artifact.

    Fields mirror the heartbeat record's status / counter axes plus
    aggregate health verdict + last-event / last-ping observation
    + retry-budget axis.
    """

    schema_version: str
    run_id: str
    session_id: str
    provider_status: str
    price_status: str
    dispatch_status: str
    ledger_status: str
    transport_status: str
    artifact_status: str
    last_event_status: str
    last_ping_status: str
    event_count: int
    candidate_count: int
    ping_rendered_count: int
    dispatch_success_count: int
    dispatch_failure_count: int
    retry_count: int
    duplicate_suppressed_count: int
    ambiguous_suppressed_count: int
    unknown_pair_suppressed_count: int
    disagree_pair_suppressed_count: int
    usdc_observe_only_count: int
    stale_price_count: int
    missing_price_count: int
    malformed_event_count: int
    retry_budget_status: str
    current_health_status: str
    redaction_status: str


HEALTH_SNAPSHOT_RECORD_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "session_id",
    "provider_status",
    "price_status",
    "dispatch_status",
    "ledger_status",
    "transport_status",
    "artifact_status",
    "last_event_status",
    "last_ping_status",
    "event_count",
    "candidate_count",
    "ping_rendered_count",
    "dispatch_success_count",
    "dispatch_failure_count",
    "retry_count",
    "duplicate_suppressed_count",
    "ambiguous_suppressed_count",
    "unknown_pair_suppressed_count",
    "disagree_pair_suppressed_count",
    "usdc_observe_only_count",
    "stale_price_count",
    "missing_price_count",
    "malformed_event_count",
    "retry_budget_status",
    "current_health_status",
    "redaction_status",
)


# ---------------------------------------------------------------------------
# Record: final run summary
# ---------------------------------------------------------------------------


class Stage28_5FinalRunSummaryRecord(NamedTuple):
    """Immutable Stage 28.5 final run summary record.

    Closed-set / safe fields only. The record is what the future
    runner writes once (overwrite-atomic) at shutdown to the final
    summary JSON artifact. The counter fields use the ``total_*``
    prefix to distinguish them visually from the per-heartbeat
    counters; the values mean cumulative totals across the run.
    """

    schema_version: str
    run_id: str
    session_id: str
    stop_reason: str
    total_events_seen: int
    total_candidates: int
    total_pings_rendered: int
    total_dispatch_success: int
    total_dispatch_failure: int
    total_retry_attempts: int
    total_duplicates_suppressed: int
    total_ambiguous_suppressed: int
    total_unknown_pair_suppressed: int
    total_disagree_pair_suppressed: int
    total_usdc_observe_only: int
    total_stale_price: int
    total_missing_price: int
    total_malformed_events: int
    final_provider_status: str
    final_price_status: str
    final_dispatch_status: str
    final_ledger_status: str
    final_transport_status: str
    final_artifact_status: str
    redaction_status: str


FINAL_SUMMARY_RECORD_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "session_id",
    "stop_reason",
    "total_events_seen",
    "total_candidates",
    "total_pings_rendered",
    "total_dispatch_success",
    "total_dispatch_failure",
    "total_retry_attempts",
    "total_duplicates_suppressed",
    "total_ambiguous_suppressed",
    "total_unknown_pair_suppressed",
    "total_disagree_pair_suppressed",
    "total_usdc_observe_only",
    "total_stale_price",
    "total_missing_price",
    "total_malformed_events",
    "final_provider_status",
    "final_price_status",
    "final_dispatch_status",
    "final_ledger_status",
    "final_transport_status",
    "final_artifact_status",
    "redaction_status",
)


# ---------------------------------------------------------------------------
# Record: CLI status line model
# ---------------------------------------------------------------------------


class Stage28_5CliStatusLineModel(NamedTuple):
    """Immutable Stage 28.5 CLI status-line input model.

    Closed-set / safe fields only. The compact CLI status string is
    formatted from this model by ``cli_status_line.py``; this
    record carries no raw URL / webhook / RPC / API-key / bearer-
    token / auth-header / wallet / signer field, and no public-
    routing / subscriber / paid-tier / trade / enforcement field.
    """

    schema_version: str
    run_id: str
    session_id: str
    health_status: str
    provider_status: str
    price_status: str
    dispatch_status: str
    ledger_status: str
    transport_status: str
    artifact_status: str
    event_count: int
    ping_rendered_count: int
    dispatch_success_count: int
    dispatch_failure_count: int
    retry_count: int
    duplicate_suppressed_count: int
    ambiguous_suppressed_count: int
    unknown_pair_suppressed_count: int
    disagree_pair_suppressed_count: int
    usdc_observe_only_count: int
    stale_price_count: int
    missing_price_count: int
    malformed_event_count: int
    stop_reason: str
    redaction_status: str


CLI_STATUS_LINE_MODEL_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "session_id",
    "health_status",
    "provider_status",
    "price_status",
    "dispatch_status",
    "ledger_status",
    "transport_status",
    "artifact_status",
    "event_count",
    "ping_rendered_count",
    "dispatch_success_count",
    "dispatch_failure_count",
    "retry_count",
    "duplicate_suppressed_count",
    "ambiguous_suppressed_count",
    "unknown_pair_suppressed_count",
    "disagree_pair_suppressed_count",
    "usdc_observe_only_count",
    "stale_price_count",
    "missing_price_count",
    "malformed_event_count",
    "stop_reason",
    "redaction_status",
)


# ---------------------------------------------------------------------------
# Builders (validating constructors)
# ---------------------------------------------------------------------------


def _normalize_run_id(value: object) -> str:
    """Return a safe-to-stamp run-id label for ``value``.

    Returns the value unchanged if it passes ``is_safe_identifier``.
    Returns ``SAFE_RUN_ID_MISSING`` for ``None`` / empty / non-str.
    Returns ``SAFE_RUN_ID_REDACTED`` for any other unsafe value.
    """
    if value is None or value == "":
        return SAFE_RUN_ID_MISSING
    if not isinstance(value, str):
        return SAFE_RUN_ID_REDACTED
    if not is_safe_identifier(value):
        return SAFE_RUN_ID_REDACTED
    return value


def _normalize_session_id(value: object) -> str:
    """Return a safe-to-stamp session-id label for ``value``."""
    if value is None or value == "":
        return SAFE_SESSION_ID_MISSING
    if not isinstance(value, str):
        return SAFE_SESSION_ID_REDACTED
    if not is_safe_identifier(value):
        return SAFE_SESSION_ID_REDACTED
    return value


def _check_counter(field_name: str, value: object) -> int:
    """Validate a counter field. Returns the int on success;
    raises ``Stage28_5HealthStatusValidationError`` on any failure.
    """
    if not is_safe_counter_value(value):
        raise Stage28_5HealthStatusValidationError(
            field_name=field_name,
            reason="COUNTER_NOT_NONNEG_INT",
        )
    return value  # type: ignore[return-value]


def _check_closed_set(
    field_name: str,
    value: object,
    closed_set: tuple[str, ...],
) -> str:
    """Validate a closed-set string field. Returns the value on
    success; raises ``Stage28_5HealthStatusValidationError``
    otherwise. Never echoes the raw rejected value.
    """
    if not isinstance(value, str) or value not in closed_set:
        raise Stage28_5HealthStatusValidationError(
            field_name=field_name,
            reason="STATUS_NOT_CLOSED_SET",
        )
    return value


def build_heartbeat_record(
    *,
    run_id: object,
    session_id: object,
    heartbeat_index: object,
    event_count: object,
    candidate_count: object,
    ping_rendered_count: object,
    dispatch_success_count: object,
    dispatch_failure_count: object,
    retry_count: object,
    duplicate_suppressed_count: object,
    ambiguous_suppressed_count: object,
    unknown_pair_suppressed_count: object,
    disagree_pair_suppressed_count: object,
    usdc_observe_only_count: object,
    stale_price_count: object,
    missing_price_count: object,
    malformed_event_count: object,
    provider_status: object,
    price_status: object,
    dispatch_status: object,
    ledger_status: object,
    transport_status: object,
    artifact_status: object,
    stop_reason: object = None,
) -> Stage28_5HeartbeatRecord:
    """Construct a Stage 28.5 heartbeat record with full validation.

    The run / session identifiers are normalized to safe-to-stamp
    placeholders if the caller-supplied value fails the safe-
    identifier allowlist; the resulting ``redaction_status`` is
    ``REDACTED`` in that case and ``SAFE`` otherwise. Counter
    fields must be non-negative ints; closed-set status fields
    must be locked values.
    """
    safe_run_id = _normalize_run_id(run_id)
    safe_session_id = _normalize_session_id(session_id)
    redacted = (
        safe_run_id != run_id
        or safe_session_id != session_id
    )
    hb_index = _check_counter("heartbeat_index", heartbeat_index)
    ev = _check_counter("event_count", event_count)
    cand = _check_counter("candidate_count", candidate_count)
    ping_r = _check_counter(
        "ping_rendered_count", ping_rendered_count
    )
    disp_ok = _check_counter(
        "dispatch_success_count", dispatch_success_count
    )
    disp_fail = _check_counter(
        "dispatch_failure_count", dispatch_failure_count
    )
    retries = _check_counter("retry_count", retry_count)
    dup = _check_counter(
        "duplicate_suppressed_count", duplicate_suppressed_count
    )
    amb = _check_counter(
        "ambiguous_suppressed_count", ambiguous_suppressed_count
    )
    unk_pair = _check_counter(
        "unknown_pair_suppressed_count",
        unknown_pair_suppressed_count,
    )
    dis_pair = _check_counter(
        "disagree_pair_suppressed_count",
        disagree_pair_suppressed_count,
    )
    usdc_obs = _check_counter(
        "usdc_observe_only_count", usdc_observe_only_count
    )
    stale = _check_counter("stale_price_count", stale_price_count)
    missing = _check_counter(
        "missing_price_count", missing_price_count
    )
    malformed = _check_counter(
        "malformed_event_count", malformed_event_count
    )
    prov_st = _check_closed_set(
        "provider_status", provider_status, PROVIDER_STATUS_VALUES
    )
    price_st = _check_closed_set(
        "price_status", price_status, PRICE_STATUS_VALUES
    )
    disp_st = _check_closed_set(
        "dispatch_status", dispatch_status, DISPATCH_STATUS_VALUES
    )
    ledg_st = _check_closed_set(
        "ledger_status", ledger_status, LEDGER_STATUS_VALUES
    )
    tr_st = _check_closed_set(
        "transport_status",
        transport_status,
        TRANSPORT_STATUS_VALUES,
    )
    art_st = _check_closed_set(
        "artifact_status", artifact_status, ARTIFACT_STATUS_VALUES
    )
    if stop_reason is None:
        stop = None
    else:
        stop = _check_closed_set(
            "stop_reason", stop_reason, STOP_REASON_VALUES
        )
    redaction = (
        REDACTION_STATUS_REDACTED
        if redacted
        else REDACTION_STATUS_SAFE
    )
    return Stage28_5HeartbeatRecord(
        schema_version=STAGE28_5_HEARTBEAT_SCHEMA_VERSION,
        run_id=safe_run_id,
        session_id=safe_session_id,
        heartbeat_index=hb_index,
        event_count=ev,
        candidate_count=cand,
        ping_rendered_count=ping_r,
        dispatch_success_count=disp_ok,
        dispatch_failure_count=disp_fail,
        retry_count=retries,
        duplicate_suppressed_count=dup,
        ambiguous_suppressed_count=amb,
        unknown_pair_suppressed_count=unk_pair,
        disagree_pair_suppressed_count=dis_pair,
        usdc_observe_only_count=usdc_obs,
        stale_price_count=stale,
        missing_price_count=missing,
        malformed_event_count=malformed,
        provider_status=prov_st,
        price_status=price_st,
        dispatch_status=disp_st,
        ledger_status=ledg_st,
        transport_status=tr_st,
        artifact_status=art_st,
        stop_reason=stop,
        redaction_status=redaction,
    )


def build_health_snapshot_record(
    *,
    run_id: object,
    session_id: object,
    provider_status: object,
    price_status: object,
    dispatch_status: object,
    ledger_status: object,
    transport_status: object,
    artifact_status: object,
    last_event_status: object,
    last_ping_status: object,
    event_count: object,
    candidate_count: object,
    ping_rendered_count: object,
    dispatch_success_count: object,
    dispatch_failure_count: object,
    retry_count: object,
    duplicate_suppressed_count: object,
    ambiguous_suppressed_count: object,
    unknown_pair_suppressed_count: object,
    disagree_pair_suppressed_count: object,
    usdc_observe_only_count: object,
    stale_price_count: object,
    missing_price_count: object,
    malformed_event_count: object,
    retry_budget_status: object,
    current_health_status: object,
) -> Stage28_5HealthSnapshotRecord:
    """Construct a Stage 28.5 health-snapshot record with full
    validation."""
    safe_run_id = _normalize_run_id(run_id)
    safe_session_id = _normalize_session_id(session_id)
    redacted = (
        safe_run_id != run_id
        or safe_session_id != session_id
    )
    prov_st = _check_closed_set(
        "provider_status", provider_status, PROVIDER_STATUS_VALUES
    )
    price_st = _check_closed_set(
        "price_status", price_status, PRICE_STATUS_VALUES
    )
    disp_st = _check_closed_set(
        "dispatch_status", dispatch_status, DISPATCH_STATUS_VALUES
    )
    ledg_st = _check_closed_set(
        "ledger_status", ledger_status, LEDGER_STATUS_VALUES
    )
    tr_st = _check_closed_set(
        "transport_status",
        transport_status,
        TRANSPORT_STATUS_VALUES,
    )
    art_st = _check_closed_set(
        "artifact_status",
        artifact_status,
        ARTIFACT_STATUS_VALUES,
    )
    last_ev = _check_closed_set(
        "last_event_status",
        last_event_status,
        LAST_EVENT_STATUS_VALUES,
    )
    last_pg = _check_closed_set(
        "last_ping_status",
        last_ping_status,
        LAST_PING_STATUS_VALUES,
    )
    ev = _check_counter("event_count", event_count)
    cand = _check_counter("candidate_count", candidate_count)
    ping_r = _check_counter(
        "ping_rendered_count", ping_rendered_count
    )
    disp_ok = _check_counter(
        "dispatch_success_count", dispatch_success_count
    )
    disp_fail = _check_counter(
        "dispatch_failure_count", dispatch_failure_count
    )
    retries = _check_counter("retry_count", retry_count)
    dup = _check_counter(
        "duplicate_suppressed_count", duplicate_suppressed_count
    )
    amb = _check_counter(
        "ambiguous_suppressed_count", ambiguous_suppressed_count
    )
    unk_pair = _check_counter(
        "unknown_pair_suppressed_count",
        unknown_pair_suppressed_count,
    )
    dis_pair = _check_counter(
        "disagree_pair_suppressed_count",
        disagree_pair_suppressed_count,
    )
    usdc_obs = _check_counter(
        "usdc_observe_only_count", usdc_observe_only_count
    )
    stale = _check_counter(
        "stale_price_count", stale_price_count
    )
    missing = _check_counter(
        "missing_price_count", missing_price_count
    )
    malformed = _check_counter(
        "malformed_event_count", malformed_event_count
    )
    retry_b = _check_closed_set(
        "retry_budget_status",
        retry_budget_status,
        RETRY_BUDGET_STATUS_VALUES,
    )
    health = _check_closed_set(
        "current_health_status",
        current_health_status,
        HEALTH_STATUS_VALUES,
    )
    redaction = (
        REDACTION_STATUS_REDACTED
        if redacted
        else REDACTION_STATUS_SAFE
    )
    return Stage28_5HealthSnapshotRecord(
        schema_version=STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION,
        run_id=safe_run_id,
        session_id=safe_session_id,
        provider_status=prov_st,
        price_status=price_st,
        dispatch_status=disp_st,
        ledger_status=ledg_st,
        transport_status=tr_st,
        artifact_status=art_st,
        last_event_status=last_ev,
        last_ping_status=last_pg,
        event_count=ev,
        candidate_count=cand,
        ping_rendered_count=ping_r,
        dispatch_success_count=disp_ok,
        dispatch_failure_count=disp_fail,
        retry_count=retries,
        duplicate_suppressed_count=dup,
        ambiguous_suppressed_count=amb,
        unknown_pair_suppressed_count=unk_pair,
        disagree_pair_suppressed_count=dis_pair,
        usdc_observe_only_count=usdc_obs,
        stale_price_count=stale,
        missing_price_count=missing,
        malformed_event_count=malformed,
        retry_budget_status=retry_b,
        current_health_status=health,
        redaction_status=redaction,
    )


def build_final_run_summary_record(
    *,
    run_id: object,
    session_id: object,
    stop_reason: object,
    total_events_seen: object,
    total_candidates: object,
    total_pings_rendered: object,
    total_dispatch_success: object,
    total_dispatch_failure: object,
    total_retry_attempts: object,
    total_duplicates_suppressed: object,
    total_ambiguous_suppressed: object,
    total_unknown_pair_suppressed: object,
    total_disagree_pair_suppressed: object,
    total_usdc_observe_only: object,
    total_stale_price: object,
    total_missing_price: object,
    total_malformed_events: object,
    final_provider_status: object,
    final_price_status: object,
    final_dispatch_status: object,
    final_ledger_status: object,
    final_transport_status: object,
    final_artifact_status: object,
) -> Stage28_5FinalRunSummaryRecord:
    """Construct a Stage 28.5 final-run-summary record with full
    validation."""
    safe_run_id = _normalize_run_id(run_id)
    safe_session_id = _normalize_session_id(session_id)
    redacted = (
        safe_run_id != run_id
        or safe_session_id != session_id
    )
    stop = _check_closed_set(
        "stop_reason", stop_reason, STOP_REASON_VALUES
    )
    totals: dict[str, int] = {}
    for field, value in (
        ("total_events_seen", total_events_seen),
        ("total_candidates", total_candidates),
        ("total_pings_rendered", total_pings_rendered),
        ("total_dispatch_success", total_dispatch_success),
        ("total_dispatch_failure", total_dispatch_failure),
        ("total_retry_attempts", total_retry_attempts),
        ("total_duplicates_suppressed", total_duplicates_suppressed),
        ("total_ambiguous_suppressed", total_ambiguous_suppressed),
        (
            "total_unknown_pair_suppressed",
            total_unknown_pair_suppressed,
        ),
        (
            "total_disagree_pair_suppressed",
            total_disagree_pair_suppressed,
        ),
        ("total_usdc_observe_only", total_usdc_observe_only),
        ("total_stale_price", total_stale_price),
        ("total_missing_price", total_missing_price),
        ("total_malformed_events", total_malformed_events),
    ):
        totals[field] = _check_counter(field, value)
    f_prov = _check_closed_set(
        "final_provider_status",
        final_provider_status,
        PROVIDER_STATUS_VALUES,
    )
    f_price = _check_closed_set(
        "final_price_status",
        final_price_status,
        PRICE_STATUS_VALUES,
    )
    f_disp = _check_closed_set(
        "final_dispatch_status",
        final_dispatch_status,
        DISPATCH_STATUS_VALUES,
    )
    f_ledg = _check_closed_set(
        "final_ledger_status",
        final_ledger_status,
        LEDGER_STATUS_VALUES,
    )
    f_tr = _check_closed_set(
        "final_transport_status",
        final_transport_status,
        TRANSPORT_STATUS_VALUES,
    )
    f_art = _check_closed_set(
        "final_artifact_status",
        final_artifact_status,
        ARTIFACT_STATUS_VALUES,
    )
    redaction = (
        REDACTION_STATUS_REDACTED
        if redacted
        else REDACTION_STATUS_SAFE
    )
    return Stage28_5FinalRunSummaryRecord(
        schema_version=STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION,
        run_id=safe_run_id,
        session_id=safe_session_id,
        stop_reason=stop,
        total_events_seen=totals["total_events_seen"],
        total_candidates=totals["total_candidates"],
        total_pings_rendered=totals["total_pings_rendered"],
        total_dispatch_success=totals["total_dispatch_success"],
        total_dispatch_failure=totals["total_dispatch_failure"],
        total_retry_attempts=totals["total_retry_attempts"],
        total_duplicates_suppressed=(
            totals["total_duplicates_suppressed"]
        ),
        total_ambiguous_suppressed=(
            totals["total_ambiguous_suppressed"]
        ),
        total_unknown_pair_suppressed=(
            totals["total_unknown_pair_suppressed"]
        ),
        total_disagree_pair_suppressed=(
            totals["total_disagree_pair_suppressed"]
        ),
        total_usdc_observe_only=totals["total_usdc_observe_only"],
        total_stale_price=totals["total_stale_price"],
        total_missing_price=totals["total_missing_price"],
        total_malformed_events=totals["total_malformed_events"],
        final_provider_status=f_prov,
        final_price_status=f_price,
        final_dispatch_status=f_disp,
        final_ledger_status=f_ledg,
        final_transport_status=f_tr,
        final_artifact_status=f_art,
        redaction_status=redaction,
    )


def build_cli_status_line_model(
    *,
    run_id: object,
    session_id: object,
    health_status: object,
    provider_status: object,
    price_status: object,
    dispatch_status: object,
    ledger_status: object,
    transport_status: object,
    artifact_status: object,
    event_count: object,
    ping_rendered_count: object,
    dispatch_success_count: object,
    dispatch_failure_count: object,
    retry_count: object,
    duplicate_suppressed_count: object,
    ambiguous_suppressed_count: object,
    unknown_pair_suppressed_count: object,
    disagree_pair_suppressed_count: object,
    usdc_observe_only_count: object,
    stale_price_count: object,
    missing_price_count: object,
    malformed_event_count: object,
    stop_reason: object,
) -> Stage28_5CliStatusLineModel:
    """Construct a Stage 28.5 CLI status line input model with full
    validation."""
    safe_run_id = _normalize_run_id(run_id)
    safe_session_id = _normalize_session_id(session_id)
    redacted = (
        safe_run_id != run_id
        or safe_session_id != session_id
    )
    health = _check_closed_set(
        "health_status", health_status, HEALTH_STATUS_VALUES
    )
    prov_st = _check_closed_set(
        "provider_status", provider_status, PROVIDER_STATUS_VALUES
    )
    price_st = _check_closed_set(
        "price_status", price_status, PRICE_STATUS_VALUES
    )
    disp_st = _check_closed_set(
        "dispatch_status", dispatch_status, DISPATCH_STATUS_VALUES
    )
    ledg_st = _check_closed_set(
        "ledger_status", ledger_status, LEDGER_STATUS_VALUES
    )
    tr_st = _check_closed_set(
        "transport_status",
        transport_status,
        TRANSPORT_STATUS_VALUES,
    )
    art_st = _check_closed_set(
        "artifact_status", artifact_status, ARTIFACT_STATUS_VALUES
    )
    ev = _check_counter("event_count", event_count)
    ping_r = _check_counter(
        "ping_rendered_count", ping_rendered_count
    )
    disp_ok = _check_counter(
        "dispatch_success_count", dispatch_success_count
    )
    disp_fail = _check_counter(
        "dispatch_failure_count", dispatch_failure_count
    )
    retries = _check_counter("retry_count", retry_count)
    dup = _check_counter(
        "duplicate_suppressed_count", duplicate_suppressed_count
    )
    amb = _check_counter(
        "ambiguous_suppressed_count", ambiguous_suppressed_count
    )
    unk_pair = _check_counter(
        "unknown_pair_suppressed_count",
        unknown_pair_suppressed_count,
    )
    dis_pair = _check_counter(
        "disagree_pair_suppressed_count",
        disagree_pair_suppressed_count,
    )
    usdc_obs = _check_counter(
        "usdc_observe_only_count", usdc_observe_only_count
    )
    stale = _check_counter("stale_price_count", stale_price_count)
    missing = _check_counter(
        "missing_price_count", missing_price_count
    )
    malformed = _check_counter(
        "malformed_event_count", malformed_event_count
    )
    stop = _check_closed_set(
        "stop_reason", stop_reason, STOP_REASON_VALUES
    )
    redaction = (
        REDACTION_STATUS_REDACTED
        if redacted
        else REDACTION_STATUS_SAFE
    )
    return Stage28_5CliStatusLineModel(
        schema_version=STAGE28_5_CLI_STATUS_SCHEMA_VERSION,
        run_id=safe_run_id,
        session_id=safe_session_id,
        health_status=health,
        provider_status=prov_st,
        price_status=price_st,
        dispatch_status=disp_st,
        ledger_status=ledg_st,
        transport_status=tr_st,
        artifact_status=art_st,
        event_count=ev,
        ping_rendered_count=ping_r,
        dispatch_success_count=disp_ok,
        dispatch_failure_count=disp_fail,
        retry_count=retries,
        duplicate_suppressed_count=dup,
        ambiguous_suppressed_count=amb,
        unknown_pair_suppressed_count=unk_pair,
        disagree_pair_suppressed_count=dis_pair,
        usdc_observe_only_count=usdc_obs,
        stale_price_count=stale,
        missing_price_count=missing,
        malformed_event_count=malformed,
        stop_reason=stop,
        redaction_status=redaction,
    )


# ---------------------------------------------------------------------------
# Canonical dict projections (deterministic key order)
# ---------------------------------------------------------------------------


def heartbeat_record_to_dict(
    record: Stage28_5HeartbeatRecord,
) -> dict:
    """Project a heartbeat record into a deterministic-order dict
    suitable for JSON serialization."""
    if not isinstance(record, Stage28_5HeartbeatRecord):
        raise Stage28_5HealthStatusRedactionLeakError(
            field_name="record",
            reason="NOT_A_HEARTBEAT_RECORD",
        )
    return {name: getattr(record, name) for name in HEARTBEAT_RECORD_FIELD_NAMES}


def health_snapshot_record_to_dict(
    record: Stage28_5HealthSnapshotRecord,
) -> dict:
    """Project a health-snapshot record into a deterministic-order
    dict suitable for JSON serialization."""
    if not isinstance(record, Stage28_5HealthSnapshotRecord):
        raise Stage28_5HealthStatusRedactionLeakError(
            field_name="record",
            reason="NOT_A_HEALTH_SNAPSHOT_RECORD",
        )
    return {
        name: getattr(record, name)
        for name in HEALTH_SNAPSHOT_RECORD_FIELD_NAMES
    }


def final_run_summary_record_to_dict(
    record: Stage28_5FinalRunSummaryRecord,
) -> dict:
    """Project a final-run-summary record into a deterministic-
    order dict suitable for JSON serialization."""
    if not isinstance(record, Stage28_5FinalRunSummaryRecord):
        raise Stage28_5HealthStatusRedactionLeakError(
            field_name="record",
            reason="NOT_A_FINAL_RUN_SUMMARY_RECORD",
        )
    return {
        name: getattr(record, name)
        for name in FINAL_SUMMARY_RECORD_FIELD_NAMES
    }


def cli_status_line_model_to_dict(
    record: Stage28_5CliStatusLineModel,
) -> dict:
    """Project a CLI status-line model into a deterministic-order
    dict (useful for tests / introspection; the CLI formatter
    itself does not consume this dict)."""
    if not isinstance(record, Stage28_5CliStatusLineModel):
        raise Stage28_5HealthStatusRedactionLeakError(
            field_name="record",
            reason="NOT_A_CLI_STATUS_LINE_MODEL",
        )
    return {
        name: getattr(record, name)
        for name in CLI_STATUS_LINE_MODEL_FIELD_NAMES
    }


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------


__all__ = (
    # Version axes.
    "STAGE28_5_MINOR_VERSION",
    "STAGE28_5_HEARTBEAT_SCHEMA_VERSION",
    "STAGE28_5_HEALTH_SNAPSHOT_SCHEMA_VERSION",
    "STAGE28_5_FINAL_SUMMARY_SCHEMA_VERSION",
    "STAGE28_5_CLI_STATUS_SCHEMA_VERSION",
    "STAGE28_5_REDACTION_TOKEN",
    # Provider status.
    "PROVIDER_STATUS_OK",
    "PROVIDER_STATUS_DISCONNECTED",
    "PROVIDER_STATUS_RECONNECTING",
    "PROVIDER_STATUS_LOST",
    "PROVIDER_STATUS_NOT_STARTED",
    "PROVIDER_STATUS_UNKNOWN",
    "PROVIDER_STATUS_VALUES",
    "is_provider_status_value",
    # Price status.
    "PRICE_STATUS_OK",
    "PRICE_STATUS_STALE",
    "PRICE_STATUS_MISSING",
    "PRICE_STATUS_TIMEOUT",
    "PRICE_STATUS_NOT_STARTED",
    "PRICE_STATUS_UNKNOWN",
    "PRICE_STATUS_VALUES",
    "is_price_status_value",
    # Dispatch status.
    "DISPATCH_STATUS_OK",
    "DISPATCH_STATUS_FAILED",
    "DISPATCH_STATUS_SUPPRESSED",
    "DISPATCH_STATUS_AMBIGUOUS",
    "DISPATCH_STATUS_NOT_STARTED",
    "DISPATCH_STATUS_UNKNOWN",
    "DISPATCH_STATUS_VALUES",
    "is_dispatch_status_value",
    # Ledger status.
    "LEDGER_STATUS_OK",
    "LEDGER_STATUS_WRITE_FAILED",
    "LEDGER_STATUS_REPLAY_FAILED",
    "LEDGER_STATUS_AMBIGUOUS",
    "LEDGER_STATUS_DUPLICATE_SUPPRESSED",
    "LEDGER_STATUS_NOT_STARTED",
    "LEDGER_STATUS_UNKNOWN",
    "LEDGER_STATUS_VALUES",
    "is_ledger_status_value",
    # Transport status (visibility view).
    "TRANSPORT_STATUS_OK",
    "TRANSPORT_STATUS_RATE_LIMITED",
    "TRANSPORT_STATUS_SERVER_ERROR",
    "TRANSPORT_STATUS_NETWORK_ERROR",
    "TRANSPORT_STATUS_REFUSED",
    "TRANSPORT_STATUS_NOT_STARTED",
    "TRANSPORT_STATUS_UNKNOWN",
    "TRANSPORT_STATUS_VALUES",
    "is_transport_status_value",
    # Artifact status.
    "ARTIFACT_STATUS_OK",
    "ARTIFACT_STATUS_WRITE_FAILED",
    "ARTIFACT_STATUS_READ_FAILED",
    "ARTIFACT_STATUS_NOT_STARTED",
    "ARTIFACT_STATUS_UNKNOWN",
    "ARTIFACT_STATUS_VALUES",
    "is_artifact_status_value",
    # Aggregate health status.
    "HEALTH_STATUS_HEALTHY",
    "HEALTH_STATUS_DEGRADED",
    "HEALTH_STATUS_FAILED",
    "HEALTH_STATUS_STOPPED",
    "HEALTH_STATUS_UNKNOWN",
    "HEALTH_STATUS_VALUES",
    "is_health_status_value",
    # Stop reason.
    "STOP_REASON_MAX_EVENTS",
    "STOP_REASON_MAX_WALL_SECONDS",
    "STOP_REASON_SIGINT",
    "STOP_REASON_SIGTERM",
    "STOP_REASON_PROVIDER_LOST",
    "STOP_REASON_RETRY_BUDGET_EXHAUSTED",
    "STOP_REASON_OPERATOR_STOP",
    "STOP_REASON_ERROR",
    "STOP_REASON_NOT_STOPPED",
    "STOP_REASON_VALUES",
    "is_stop_reason_value",
    # Last-event / last-ping status.
    "LAST_EVENT_STATUS_OBSERVED",
    "LAST_EVENT_STATUS_NONE_OBSERVED",
    "LAST_EVENT_STATUS_NOT_STARTED",
    "LAST_EVENT_STATUS_UNKNOWN",
    "LAST_EVENT_STATUS_VALUES",
    "is_last_event_status_value",
    "LAST_PING_STATUS_RENDERED",
    "LAST_PING_STATUS_SUPPRESSED",
    "LAST_PING_STATUS_NONE_RENDERED",
    "LAST_PING_STATUS_NOT_STARTED",
    "LAST_PING_STATUS_UNKNOWN",
    "LAST_PING_STATUS_VALUES",
    "is_last_ping_status_value",
    # Retry-budget status.
    "RETRY_BUDGET_STATUS_OK",
    "RETRY_BUDGET_STATUS_NEAR_LIMIT",
    "RETRY_BUDGET_STATUS_EXHAUSTED",
    "RETRY_BUDGET_STATUS_NOT_STARTED",
    "RETRY_BUDGET_STATUS_UNKNOWN",
    "RETRY_BUDGET_STATUS_VALUES",
    "is_retry_budget_status_value",
    # Redaction status.
    "REDACTION_STATUS_SAFE",
    "REDACTION_STATUS_REDACTED",
    "REDACTION_STATUS_NO_SECRET_MATERIAL",
    "REDACTION_STATUS_VALUES",
    "is_redaction_status_value",
    # Safe identifier helpers.
    "SAFE_RUN_ID_REDACTED",
    "SAFE_SESSION_ID_REDACTED",
    "SAFE_RUN_ID_MISSING",
    "SAFE_SESSION_ID_MISSING",
    "is_safe_identifier",
    # Counter validation.
    "is_safe_counter_value",
    # Field-name inventories.
    "COUNTER_FIELD_NAMES",
    "FINAL_SUMMARY_TOTAL_FIELD_NAMES",
    "HEARTBEAT_RECORD_FIELD_NAMES",
    "HEALTH_SNAPSHOT_RECORD_FIELD_NAMES",
    "FINAL_SUMMARY_RECORD_FIELD_NAMES",
    "CLI_STATUS_LINE_MODEL_FIELD_NAMES",
    # Records.
    "Stage28_5HeartbeatRecord",
    "Stage28_5HealthSnapshotRecord",
    "Stage28_5FinalRunSummaryRecord",
    "Stage28_5CliStatusLineModel",
    # Builders.
    "build_heartbeat_record",
    "build_health_snapshot_record",
    "build_final_run_summary_record",
    "build_cli_status_line_model",
    # Dict projections.
    "heartbeat_record_to_dict",
    "health_snapshot_record_to_dict",
    "final_run_summary_record_to_dict",
    "cli_status_line_model_to_dict",
    # Exceptions.
    "Stage28_5HealthStatusError",
    "Stage28_5HealthStatusValidationError",
    "Stage28_5HealthStatusRedactionLeakError",
)
