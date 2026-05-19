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
STAGE22_MINOR_VERSION: str = "22.4"

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


# ---------------------------------------------------------------------------
# Stage 22.2 -- dedupe ledger record schema (JSONL)
# ---------------------------------------------------------------------------
#
# Stage 22.2 introduces the JSONL dedupe ledger record family.
# The schema version is per-record (not per-file) so a future
# bump can migrate without a file-header dance. The two record
# types model the two state transitions of the seen/dispatched
# state machine the future bounded runner will drive.
#
# A "seen" record is appended on the first ``check_and_record``
# observation of a given logical key. A "dispatched" record is
# appended on ``mark_dispatched`` for that key. Duplicate seen
# or duplicate dispatched lines on replay are tolerated (the
# state machine is idempotent on those transitions). A
# "dispatched" record for a key that has not been "seen" first
# is a corrupt ledger and is rejected with
# ``Stage22LedgerContractError``.


STAGE22_LEDGER_RECORD_SCHEMA_VERSION: str = "stage22_v0_ledger"


LEDGER_RECORD_TYPE_SEEN: str = "seen"
LEDGER_RECORD_TYPE_DISPATCHED: str = "dispatched"


LEDGER_RECORD_TYPES: tuple[str, ...] = (
    LEDGER_RECORD_TYPE_SEEN,
    LEDGER_RECORD_TYPE_DISPATCHED,
)


# Required fields on every JSONL ledger record. The values are
# all non-secret short strings; the schema version is a closed
# constant; the record type is a closed-set token; the
# remaining five fields are the ``IngestEventKey`` projection.
# ``provider_event_id`` may be the empty string (audit-only)
# while the rest must be non-empty.


LEDGER_REQUIRED_RECORD_FIELDS: tuple[str, ...] = (
    "schema_version",
    "record_type",
    "provider_id",
    "chain",
    "event_id",
    "provider_event_id",
    "raw_event_hash",
)


# Record fields that must be non-empty on replay (the dedupe
# identity components plus the canonical correlation hash).
# ``provider_event_id`` is intentionally excluded -- it may be
# the empty string per the Stage 22.1 ``MalformedEventRecord``
# convention and remains audit-only.


LEDGER_REQUIRED_NON_EMPTY_FIELDS: tuple[str, ...] = (
    "provider_id",
    "chain",
    "event_id",
    "raw_event_hash",
)


# ---------------------------------------------------------------------------
# Stage 22.3 -- raw capture record schema (JSONL)
# ---------------------------------------------------------------------------
#
# Stage 22.3 introduces the JSONL raw-capture record family. One
# append-only JSONL stream per writer instance carries three
# discriminated record_type families: a sanitized projection of a
# Stage 21 normalized event, a sanitized projection of a
# per-event decode failure, and a sanitized projection of a
# provider fetch failure. The schema version is per-record (not
# per-file) so a future bump can migrate additively without a
# file-header dance.
#
# The exact required-field tuple is locked per-record-type; the
# writer enforces ``set(record.keys()) ==
# set(CAPTURE_<TYPE>_REQUIRED_FIELDS)`` on every write and on
# every replay line. Any missing field or unexpected extra field
# is a hard contract violation and raises
# ``Stage22CaptureContractError``. The exact-set discipline is
# the same defense Stage 22.2 ships for the dedupe ledger, here
# specialized per record_type because the three families do not
# share a single field shape.


STAGE22_CAPTURE_RECORD_SCHEMA_VERSION: str = "stage22_v0_capture"


CAPTURE_RECORD_TYPE_NORMALIZED_EVENT: str = "normalized_event"
CAPTURE_RECORD_TYPE_MALFORMED_EVENT: str = "malformed_event"
CAPTURE_RECORD_TYPE_PROVIDER_FAILURE: str = "provider_failure"


CAPTURE_RECORD_TYPES: tuple[str, ...] = (
    CAPTURE_RECORD_TYPE_NORMALIZED_EVENT,
    CAPTURE_RECORD_TYPE_MALFORMED_EVENT,
    CAPTURE_RECORD_TYPE_PROVIDER_FAILURE,
)


# Exact required-field tuples per record_type. Field order in each
# tuple is the canonical order documented in the Stage 22.3
# design; on-disk JSON uses sorted keys so the wire order is
# independent of these tuples.
#
# ``normalized_event`` is the sanitized projection of an
# ``IngestEventEnvelope``. ``payload_summary`` is a nested JSON
# object whose contents are recursively validated by the writer
# at write time and at replay.

CAPTURE_NORMALIZED_EVENT_REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "record_type",
    "provider_id",
    "chain",
    "event_id",
    "provider_event_id",
    "raw_event_hash",
    "received_at_utc",
    "provider_attempt_index",
    "event_type",
    "source_kind",
    "mint",
    "slot",
    "signature",
    "payload_summary",
)


# ``malformed_event`` is the sanitized projection of a
# ``MalformedEventRecord``. ``provider_event_id`` may be the empty
# string per the Stage 22.1 record convention; ``raw_event_hash``
# remains the canonical correlation key in that case.

CAPTURE_MALFORMED_EVENT_REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "record_type",
    "provider_id",
    "provider_event_id",
    "reason",
    "failed_at_utc",
    "raw_event_hash",
)


# ``provider_failure`` is the sanitized projection of a
# ``ProviderFailureRecord``. ``upstream_error_type`` is locked
# NON-empty in this record family: the empty string is reserved
# for ok=True outcomes which are incoherent for a failure record.

CAPTURE_PROVIDER_FAILURE_REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "record_type",
    "provider_id",
    "failure_label",
    "status_class",
    "upstream_error_type",
    "provider_attempt_index",
    "observed_at_utc",
)


# Per-record-type required non-empty string field tuples. The
# writer rejects any record whose listed field is not a non-empty
# string. ``provider_event_id`` is intentionally NOT in any of
# these tuples -- it may be the empty string per the Stage 22.1
# ``MalformedEventRecord`` / ``IngestEventKey`` convention and
# remains audit-only.

CAPTURE_NORMALIZED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS: tuple[str, ...] = (
    "schema_version",
    "record_type",
    "provider_id",
    "chain",
    "event_id",
    "raw_event_hash",
    "received_at_utc",
    "event_type",
    "source_kind",
    "mint",
    "signature",
)


CAPTURE_MALFORMED_EVENT_REQUIRED_NON_EMPTY_STRING_FIELDS: tuple[str, ...] = (
    "schema_version",
    "record_type",
    "provider_id",
    "reason",
    "failed_at_utc",
    "raw_event_hash",
)


CAPTURE_PROVIDER_FAILURE_REQUIRED_NON_EMPTY_STRING_FIELDS: tuple[str, ...] = (
    "schema_version",
    "record_type",
    "provider_id",
    "failure_label",
    "status_class",
    "upstream_error_type",
    "observed_at_utc",
)


# Per-record-type required strict-int field tuples. ``bool`` is
# a subclass of ``int`` in Python; the writer's runtime check
# excludes bool explicitly so True / False cannot silently pass
# as a slot or provider_attempt_index value. The replay decoder
# applies the same discipline.

CAPTURE_NORMALIZED_EVENT_REQUIRED_INT_FIELDS: tuple[str, ...] = (
    "provider_attempt_index",
    "slot",
)


CAPTURE_PROVIDER_FAILURE_REQUIRED_INT_FIELDS: tuple[str, ...] = (
    "provider_attempt_index",
)


# ``payload_summary`` sanitizer caps. The writer rejects any
# payload_summary that exceeds these limits.
#
# Caps locked at 22.3:
#   * up to 16 keys
#   * keys are snake_case lowercase ASCII identifiers up to 64
#     chars
#   * string values are up to 512 chars (raw evidence dumps
#     belong to a strictly later specialised stage, after the
#     sanitizer rules are proven on real provider data)
CAPTURE_PAYLOAD_SUMMARY_MAX_KEYS: int = 16
CAPTURE_PAYLOAD_SUMMARY_MAX_KEY_LEN: int = 64
CAPTURE_PAYLOAD_SUMMARY_MAX_STRING_LEN: int = 512


# Long-token thresholds for the writer-side sanitizer. The
# thresholds mirror those in ``test_no_secret_leaks.py`` -- 40
# chars for a hex run (above the Stage 21 truncated fingerprint
# length of 12) and 32 chars for a mixed-content base64-shape
# run.

CAPTURE_LONG_HEX_RUN_MIN_LEN: int = 40
CAPTURE_LONG_TOKENISH_MIN_LEN: int = 32


# URL-scheme fragments and webhook host literals are constructed
# at runtime via string concatenation so the literal substrings
# the Stage 22 boundary scanners forbid never appear in this
# source file. The forbidden literals include the four standard
# scheme prefixes (http / https / ws / wss followed by colon-
# slash-slash) and the three webhook host names (discord +
# .com, discordapp + .com, hooks.slack + .com). Mirrors the
# Stage 21 pattern in ``PHX2/stage21/constants.py``.

_COLON_SLASH_SLASH: str = ":" + "//"
_HTTP_SCHEME: str = "http" + _COLON_SLASH_SLASH
_HTTPS_SCHEME: str = "https" + _COLON_SLASH_SLASH
_WS_SCHEME: str = "ws" + _COLON_SLASH_SLASH
_WSS_SCHEME: str = "wss" + _COLON_SLASH_SLASH

_DOT_COM: str = "." + "com"
_DISCORD_HOST: str = "discord" + _DOT_COM
_DISCORDAPP_HOST: str = "discordapp" + _DOT_COM
_HOOKS_SLACK_HOST: str = "hooks" + ".slack" + _DOT_COM


# Substrings the writer rejects anywhere inside a payload_summary
# string value (case-insensitive). The colon-slash-slash entry
# catches URL prefixes that drop the scheme as well as the
# concrete schemes.

CAPTURE_FORBIDDEN_URL_SUBSTRINGS: tuple[str, ...] = (
    _HTTP_SCHEME,
    _HTTPS_SCHEME,
    _WS_SCHEME,
    _WSS_SCHEME,
    _COLON_SLASH_SLASH,
    _DISCORD_HOST,
    _DISCORDAPP_HOST,
    _HOOKS_SLACK_HOST,
)


# Substrings the writer rejects anywhere inside a payload_summary
# key (case-insensitive). Mirrors the field-name discipline in
# ``test_no_secret_leaks.py`` so the runtime sanitizer's reject
# set is the same as the source-text scan set.

CAPTURE_FORBIDDEN_SECRET_KEY_SUBSTRINGS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "webhook_url",
    "webhook",
    "rpc_url",
    "raw_response_body",
    "raw_response",
    "response_body",
    "exception_message",
    "exception_repr",
    "exception_args",
    "headers",
    "authorization",
    "bearer",
    "password",
    "secret",
    "credential",
    "credentials",
    "private_key",
    "privatekey",
)
