"""Stage 22 locked constants (foundation only at 22.1).

All Stage 22 version strings, closed-set token vocabularies, and
boundary-scan inputs (forbidden routing token tuple, forbidden
vocabulary tuple, explicit-allow tuple) live here. Stage 22
mirrors the Stage 21 convention: every closed-set surface is a
``tuple[str, ...]`` declared once in this module and consumed
verbatim by callers.

Stage 22.1 is contracts-only: this module is read by
``PHX2/stage22/ingest_contracts.py``,
``PHX2/stage22/failure_classification.py``, and by the
``PHX2/tests/stage22/`` boundary tests. No production module
outside this stage may declare a Stage 22 token.

The Stage 22 forbidden-routing tuple intentionally mirrors the
Stage 21 set (``subscriber`` / ``public_dispatch`` /
``paid_dispatch`` / ...) but is re-declared locally so the
identifier-aware ``test_no_public_routing.py`` scanner does not
need to reach into Stage 21 to enforce the same invariant.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 22 version strings
# ---------------------------------------------------------------------------


STAGE22_VERSION: str = "stage22_v0_ingest_hardening_foundation"
# Minor version axis. Bump on every sub-stage merge: 22.1 -> 22.2 -> ...
STAGE22_MINOR_VERSION: str = "22.1"

# Stage 22 consumes Stage 21 normalized event records as input.
# The Stage 22 -> Stage 23 contract version is reserved here but
# not yet emitted by any 22.1 surface.
STAGE22_CONSUMER_CONTRACT_VERSION: str = "stage22_v0_ingest"


# ---------------------------------------------------------------------------
# PROVIDER_FAILURE_LABELS -- closed set of provider failure outcomes
# ---------------------------------------------------------------------------
#
# Locked per Stage 22.1 design-lock decisions:
#   * ``provider_returned_empty`` is NOT in this set. An empty
#     fetch is a successful zero-event run, not a failure; it
#     surfaces at the runner level as ``provider_returned_zero``
#     in ``INGEST_RUNNER_OUTCOMES``.
#   * ``provider_returned_malformed`` IS in this set because an
#     unparseable response envelope is a fetch-level failure
#     distinct from per-event decode failures (those map to
#     ``MALFORMED_EVENT_REASONS`` instead).


PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT: str = "provider_fetch_timeout"
PROVIDER_FAILURE_LABEL_FETCH_RATE_LIMITED: str = "provider_fetch_rate_limited"
PROVIDER_FAILURE_LABEL_FETCH_5XX: str = "provider_fetch_5xx"
PROVIDER_FAILURE_LABEL_FETCH_4XX: str = "provider_fetch_4xx"
PROVIDER_FAILURE_LABEL_FETCH_CONNECTION: str = "provider_fetch_connection"
PROVIDER_FAILURE_LABEL_FETCH_AUTH: str = "provider_fetch_auth"
PROVIDER_FAILURE_LABEL_FETCH_OTHER: str = "provider_fetch_other"
PROVIDER_FAILURE_LABEL_RETURNED_MALFORMED: str = "provider_returned_malformed"


PROVIDER_FAILURE_LABELS: tuple[str, ...] = (
    PROVIDER_FAILURE_LABEL_FETCH_TIMEOUT,
    PROVIDER_FAILURE_LABEL_FETCH_RATE_LIMITED,
    PROVIDER_FAILURE_LABEL_FETCH_5XX,
    PROVIDER_FAILURE_LABEL_FETCH_4XX,
    PROVIDER_FAILURE_LABEL_FETCH_CONNECTION,
    PROVIDER_FAILURE_LABEL_FETCH_AUTH,
    PROVIDER_FAILURE_LABEL_FETCH_OTHER,
    PROVIDER_FAILURE_LABEL_RETURNED_MALFORMED,
)


# ---------------------------------------------------------------------------
# STATUS_CLASSES -- classifier input vocabulary
# ---------------------------------------------------------------------------
#
# The provider adapter (a future Stage 22.2+ wrapper around an
# injected client) is responsible for mapping each concrete
# transport-level outcome into one of these tokens before
# constructing a ``ProviderFetchOutcome``. The mapping table
# itself is NOT defined in Stage 22.1 -- only the closed set.


STATUS_CLASS_SUCCESS: str = "success"
STATUS_CLASS_AUTH: str = "auth"
STATUS_CLASS_RATE_LIMIT: str = "rate_limit"
STATUS_CLASS_CLIENT_ERROR: str = "client_error"
STATUS_CLASS_SERVER_ERROR: str = "server_error"
STATUS_CLASS_TIMEOUT: str = "timeout"
STATUS_CLASS_CONNECTION: str = "connection"
STATUS_CLASS_MALFORMED: str = "malformed"
STATUS_CLASS_UNKNOWN: str = "unknown"


STATUS_CLASSES: tuple[str, ...] = (
    STATUS_CLASS_SUCCESS,
    STATUS_CLASS_AUTH,
    STATUS_CLASS_RATE_LIMIT,
    STATUS_CLASS_CLIENT_ERROR,
    STATUS_CLASS_SERVER_ERROR,
    STATUS_CLASS_TIMEOUT,
    STATUS_CLASS_CONNECTION,
    STATUS_CLASS_MALFORMED,
    STATUS_CLASS_UNKNOWN,
)


# ---------------------------------------------------------------------------
# UPSTREAM_ERROR_TYPES -- sanitized exception class categories
# ---------------------------------------------------------------------------
#
# Each token is a category, NOT a raw ``type(exc).__name__``. The
# adapter pre-maps its concrete exceptions into one of these
# categories before constructing a ``ProviderFetchOutcome``. The
# empty-string token is reserved for the ok=True case.


UPSTREAM_ERROR_TYPE_NONE: str = ""
UPSTREAM_ERROR_TYPE_TIMEOUT: str = "timeout"
UPSTREAM_ERROR_TYPE_CONNECTION_REFUSED: str = "connection_refused"
UPSTREAM_ERROR_TYPE_TLS_ERROR: str = "tls_error"
UPSTREAM_ERROR_TYPE_DNS_ERROR: str = "dns_error"
UPSTREAM_ERROR_TYPE_RATE_LIMITED: str = "rate_limited"
UPSTREAM_ERROR_TYPE_AUTH_ERROR: str = "auth_error"
UPSTREAM_ERROR_TYPE_SERVER_ERROR: str = "server_error"
UPSTREAM_ERROR_TYPE_CLIENT_ERROR: str = "client_error"
UPSTREAM_ERROR_TYPE_MALFORMED_RESPONSE: str = "malformed_response"
UPSTREAM_ERROR_TYPE_UNKNOWN: str = "unknown_error"


UPSTREAM_ERROR_TYPES: tuple[str, ...] = (
    UPSTREAM_ERROR_TYPE_NONE,
    UPSTREAM_ERROR_TYPE_TIMEOUT,
    UPSTREAM_ERROR_TYPE_CONNECTION_REFUSED,
    UPSTREAM_ERROR_TYPE_TLS_ERROR,
    UPSTREAM_ERROR_TYPE_DNS_ERROR,
    UPSTREAM_ERROR_TYPE_RATE_LIMITED,
    UPSTREAM_ERROR_TYPE_AUTH_ERROR,
    UPSTREAM_ERROR_TYPE_SERVER_ERROR,
    UPSTREAM_ERROR_TYPE_CLIENT_ERROR,
    UPSTREAM_ERROR_TYPE_MALFORMED_RESPONSE,
    UPSTREAM_ERROR_TYPE_UNKNOWN,
)


# ---------------------------------------------------------------------------
# MALFORMED_EVENT_REASONS -- per-event decode failure vocabulary
# ---------------------------------------------------------------------------
#
# Each reason maps 1:1 to the Stage 21.3A ``ProviderPayloadError``
# subclass family plus a catch-all. The future Stage 22 decode
# step (per-payload try/except wrapping the Stage 21.3A
# ``decode_provider_event`` call) maps each subclass to its token
# before constructing a ``MalformedEventRecord``.


MALFORMED_REASON_SHAPE_ERROR: str = "decode_shape_error"
MALFORMED_REASON_FIELD_TYPE_ERROR: str = "decode_field_type_error"
MALFORMED_REASON_FIELD_VALUE_ERROR: str = "decode_field_value_error"
MALFORMED_REASON_UNSUPPORTED_INSTRUCTION: str = "decode_unsupported_instruction"
MALFORMED_REASON_SUSPICIOUS_CONTENT: str = "decode_suspicious_content"
MALFORMED_REASON_UNEXPECTED_ERROR: str = "decode_unexpected_error"


MALFORMED_EVENT_REASONS: tuple[str, ...] = (
    MALFORMED_REASON_SHAPE_ERROR,
    MALFORMED_REASON_FIELD_TYPE_ERROR,
    MALFORMED_REASON_FIELD_VALUE_ERROR,
    MALFORMED_REASON_UNSUPPORTED_INSTRUCTION,
    MALFORMED_REASON_SUSPICIOUS_CONTENT,
    MALFORMED_REASON_UNEXPECTED_ERROR,
)


# ---------------------------------------------------------------------------
# RETRY_DECISIONS -- retry contract decision vocabulary
# ---------------------------------------------------------------------------
#
# Stage 22.1 defines the decision tokens only. The retry policy
# itself (what triggers ``retry`` vs ``abort``, how long to wait,
# the cap interaction) is a Stage 22.2+ concern.


RETRY_DECISION_RETRY: str = "retry"
RETRY_DECISION_SKIP: str = "skip"
RETRY_DECISION_ABORT: str = "abort"


RETRY_DECISIONS: tuple[str, ...] = (
    RETRY_DECISION_RETRY,
    RETRY_DECISION_SKIP,
    RETRY_DECISION_ABORT,
)


# ---------------------------------------------------------------------------
# DEDUPE_OUTCOMES -- ledger check-and-record outcome vocabulary
# ---------------------------------------------------------------------------
#
# The ``duplicate_not_yet_dispatched`` token preserves the
# two-phase seen-then-dispatched state on the ledger; the future
# ledger implementation MUST distinguish "seen and dispatched"
# from "seen but never dispatched" (e.g. a crash between record
# and send). ``ledger_unavailable`` is the fail-closed token for
# transient ledger storage failure.


DEDUPE_OUTCOME_NEW: str = "new"
DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED: str = (
    "duplicate_already_dispatched"
)
DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED: str = (
    "duplicate_not_yet_dispatched"
)
DEDUPE_OUTCOME_LEDGER_UNAVAILABLE: str = "ledger_unavailable"


DEDUPE_OUTCOMES: tuple[str, ...] = (
    DEDUPE_OUTCOME_NEW,
    DEDUPE_OUTCOME_DUPLICATE_ALREADY_DISPATCHED,
    DEDUPE_OUTCOME_DUPLICATE_NOT_YET_DISPATCHED,
    DEDUPE_OUTCOME_LEDGER_UNAVAILABLE,
)


# ---------------------------------------------------------------------------
# INGEST_RUNNER_OUTCOMES -- top-level Stage 22 runner outcome vocabulary
# ---------------------------------------------------------------------------
#
# Locked per Stage 22.1 design-lock decisions:
#   * ``provider_returned_zero`` covers the successful empty fetch.
#   * ``all_malformed`` covers the case where every returned event
#     failed decode -- distinct from ``provider_failed`` (fetch
#     itself failed) and from ``all_duplicates`` (events known).
#   * ``max_attempts_exhausted`` is distinct from ``provider_failed``
#     in that the latter covers an abort decision on a single
#     attempt, while the former covers exhausting retry attempts.


INGEST_OUTCOME_OK: str = "ok"
INGEST_OUTCOME_READINESS_NOT_READY: str = "readiness_not_ready"
INGEST_OUTCOME_PROVIDER_FAILED: str = "provider_failed"
INGEST_OUTCOME_PROVIDER_RETURNED_ZERO: str = "provider_returned_zero"
INGEST_OUTCOME_ALL_MALFORMED: str = "all_malformed"
INGEST_OUTCOME_ALL_DUPLICATES: str = "all_duplicates"
INGEST_OUTCOME_TRANSPORT_REFUSED: str = "transport_refused"
INGEST_OUTCOME_MAX_ATTEMPTS_EXHAUSTED: str = "max_attempts_exhausted"


INGEST_RUNNER_OUTCOMES: tuple[str, ...] = (
    INGEST_OUTCOME_OK,
    INGEST_OUTCOME_READINESS_NOT_READY,
    INGEST_OUTCOME_PROVIDER_FAILED,
    INGEST_OUTCOME_PROVIDER_RETURNED_ZERO,
    INGEST_OUTCOME_ALL_MALFORMED,
    INGEST_OUTCOME_ALL_DUPLICATES,
    INGEST_OUTCOME_TRANSPORT_REFUSED,
    INGEST_OUTCOME_MAX_ATTEMPTS_EXHAUSTED,
)


# ---------------------------------------------------------------------------
# Retry cap default
# ---------------------------------------------------------------------------
#
# Default total attempt cap for a future bounded runner. Stage
# 22.1 ships only the constant; no policy that consumes it.


DEFAULT_RETRY_MAX_ATTEMPTS: int = 3


# ---------------------------------------------------------------------------
# Stage 22 forbidden routing tokens (locally re-declared)
# ---------------------------------------------------------------------------
#
# The Stage 20 closure handoff (Sections C, G) and the Stage 21
# closure both forbid subscriber / public / paid routing. Stage
# 22 inherits this prohibition and re-declares the locked tuple
# locally so the Stage 22 routing-scan boundary test does not
# need to reach into Stage 21. The Stage 22 test
# ``test_no_public_routing.py`` mirrors the Stage 21 AUDIT-004
# identifier-aware scanner.


STAGE22_FORBIDDEN_ROUTING_TOKENS: tuple[str, ...] = (
    "subscriber",
    "subscribers",
    "subscriber_channel",
    "public_channel",
    "public_signal",
    "public_dispatch",
    "paid_signal",
    "paid_signals",
    "paid_channel",
    "paid_dispatch",
)


# Identifier explicit-allow set: identifiers that legitimately
# contain a forbidden routing token as a snake-component. Adding
# to this tuple requires a STAGE22_VERSION bump and an operator
# review. Stage 22.1 inherits the Stage 21 invariant name
# ``safe_for_public_dispatch`` because the locked dispatch flag
# may travel through Stage 22 records as a typed field on Stage
# 21 contracts (e.g. ``TransportPayload``). Stage 22.1 itself
# does not declare any record carrying this name; the entry is
# locked here pre-emptively so the scanner remains consistent
# with Stage 21.


STAGE22_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS: tuple[str, ...] = (
    "safe_for_public_dispatch",
    "SAFE_FOR_PUBLIC_DISPATCH",
)


# ---------------------------------------------------------------------------
# Stage 22 forbidden vocabulary (boundary scanner input)
# ---------------------------------------------------------------------------
#
# Identifier-position substrings the Stage 22 production source
# MUST NOT define. These are concerns that belong to strictly
# later stages or are forever forbidden in Stage 22:
#   * ``scheduler`` / ``daemon`` / ``orchestrator`` / ``run_loop``
#     / ``worker`` -- long-running infra (out of scope for Stage
#     22's bounded-runner posture; bounded-runner does NOT use
#     these names).
#   * ``telegram`` / ``axiom`` / ``jito`` -- wrong-stage concerns
#     (X / execution-fee / monetization paths).
#   * ``eligibility`` -- Stage 20 alert-eligibility scoring; out
#     of scope for ingest hardening.
#
# IMPORTANT: ``retry`` / ``dedupe`` / ``capture`` / ``classify`` /
# ``ingest`` / ``failure`` / ``ledger`` / ``archive`` /
# ``quarantine`` are NOT on this list -- Stage 22 is the
# legitimate home for that vocabulary.


STAGE22_FORBIDDEN_VOCABULARY: tuple[str, ...] = (
    "scheduler",
    "daemon",
    "orchestrator",
    "run_loop",
    "worker",
    "telegram",
    "axiom",
    "jito",
    "eligibility",
)
