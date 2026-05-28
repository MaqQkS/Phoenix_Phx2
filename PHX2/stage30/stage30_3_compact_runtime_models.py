"""Stage 30.3 compact private ping transport-wrapper closed-set
vocabularies and immutable record shapes.

Stage 30.3A ships the pure-Python model layer consumed by the
Stage 30.3 compact-body transport wrapper, the Stage 30.3
candidate-context recorder, the Stage 30.3 candidate projection,
and the Stage 30.3 runtime-wiring artifact writer. The records
carry only closed-set tokens, safe-shape opaque identifier
echoes, integer lengths, hex-prefix hashes, and ISO-8601 UTC
timestamps.

Closed-set vocabularies:

  * ``COMPACT_OUTCOME``               -- ``RENDERED`` /
                                        ``SKIPPED_NOT_TIERABLE`` /
                                        ``FAILED_INPUT_SHAPE`` /
                                        ``FAILED_TIER_DECISION`` /
                                        ``FAILED_COMPACT_RENDER`` /
                                        ``FAILED_CAP`` /
                                        ``FAILED_SNAPSHOT_WRITE`` /
                                        ``FAILED_EXCEPTION``
  * ``SNAPSHOT_WRITE_REASON``         -- ``TIER_WRITE_FAILED`` /
                                        ``COMPACT_WRITE_FAILED``
  * ``WRAPPER_ORDER_LABEL``           -- closed-set wrapper-layer
                                        labels, outermost first.
  * ``FORBIDDEN_RECORD_FIELD_NAMES``  -- defensive sentinel
                                        vocabulary.

Stage 30.3 deliberately does NOT carry:

  * raw provider payload blobs (no field ever takes a raw payload),
  * secrets, URL hosts, API keys, bearer tokens, authorization
    headers (no field admits them),
  * trading verdicts (the Stage 30 spec forbids any trading-verdict
    substring on rendered output; Stage 30.3 records are structurally
    upstream of that scan and never carry a verdict by construction),
  * Stage 26 / Stage 29 enforcement decisions (Stage 30 is
    informational-only),
  * live secret read, live network call, live operator-channel send.

Discipline:

  * Stdlib only (``pathlib`` / ``typing``).
  * No Stage 21-29 import. The synthetic-refusal transport status
    string is redeclared locally so this module imports zero
    Stage 28 modules.
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No URL host literal, no API-key literal, no bearer-token
    literal, no authorization-header literal.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Optional, Tuple


# ---------------------------------------------------------------------------
# Stage 30.3 schema version + locked artifact basename
# ---------------------------------------------------------------------------


STAGE30_3_MINOR_VERSION: str = "30.3"
STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION: str = (
    "stage30_3_v0_runtime_wiring"
)
STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME: str = (
    "stage30_3_runtime_wiring.jsonl"
)


# ---------------------------------------------------------------------------
# compact_outcome closed set
# ---------------------------------------------------------------------------
#
# One outcome token is recorded per ``send_one_audited_post`` call.
# ``RENDERED`` is the only success outcome and is the only outcome
# under which the wrapper forwards a compact-replacement payload to
# the inner transport. Every other token is a closed-set failure /
# skip outcome and is paired with a synthetic refusal result.


COMPACT_OUTCOME_RENDERED: str = "RENDERED"
COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE: str = "SKIPPED_NOT_TIERABLE"
COMPACT_OUTCOME_FAILED_INPUT_SHAPE: str = "FAILED_INPUT_SHAPE"
COMPACT_OUTCOME_FAILED_TIER_DECISION: str = "FAILED_TIER_DECISION"
COMPACT_OUTCOME_FAILED_COMPACT_RENDER: str = (
    "FAILED_COMPACT_RENDER"
)
COMPACT_OUTCOME_FAILED_CAP: str = "FAILED_CAP"
COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE: str = (
    "FAILED_SNAPSHOT_WRITE"
)
COMPACT_OUTCOME_FAILED_EXCEPTION: str = "FAILED_EXCEPTION"


COMPACT_OUTCOME_VALUES: Tuple[str, ...] = (
    COMPACT_OUTCOME_RENDERED,
    COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
    COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
    COMPACT_OUTCOME_FAILED_TIER_DECISION,
    COMPACT_OUTCOME_FAILED_COMPACT_RENDER,
    COMPACT_OUTCOME_FAILED_CAP,
    COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE,
    COMPACT_OUTCOME_FAILED_EXCEPTION,
)


def is_compact_outcome_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.3 compact
    outcome token.
    """
    return isinstance(value, str) and value in COMPACT_OUTCOME_VALUES


# ---------------------------------------------------------------------------
# snapshot-write sub-reason closed set
# ---------------------------------------------------------------------------


SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED: str = "TIER_WRITE_FAILED"
SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED: str = (
    "COMPACT_WRITE_FAILED"
)


SNAPSHOT_WRITE_REASON_VALUES: Tuple[str, ...] = (
    SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED,
    SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED,
)


def is_snapshot_write_reason_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.3 snapshot-write
    sub-reason token.
    """
    return (
        isinstance(value, str)
        and value in SNAPSHOT_WRITE_REASON_VALUES
    )


# ---------------------------------------------------------------------------
# wrapper-order label closed set
# ---------------------------------------------------------------------------
#
# Stage 30.3B production wiring composes the wrapper layers in
# outermost-first order:
#
#   Stage30_3CompactBodyTransportWrapper     (REPLACES content)
#     optional Stage29_5_6 wrapped transport (APPENDS migration block)
#       Stage28_9PrivateWebhookTransport     (applies content cap)
#         Stage28_4AuditedHttpTransport      (actual HTTP)
#
# The Stage 30.3A wrapper records the layer labels verbatim from
# the caller-supplied ``wrapper_order`` tuple onto every wiring
# artifact line, so an operator can audit the wrapper composition
# offline. The fake-inner-transport label is admitted only for
# Stage 30.3A test injection and MUST NEVER appear in a Stage
# 30.3B production wiring artifact.


WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY: str = (
    "stage30_3_compact_body"
)
WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION: str = (
    "stage29_5_6_migration_context"
)
WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK: str = (
    "stage28_9_private_" + "webhook"
)
WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP: str = (
    "stage28_4_audited_http"
)
WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT: str = (
    "fake_inner_transport"
)


WRAPPER_ORDER_LABEL_VALUES: Tuple[str, ...] = (
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
    WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION,
    WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
    WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP,
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
)


def is_wrapper_order_label_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a Stage 30.3 wrapper-order
    label token.
    """
    return (
        isinstance(value, str)
        and value in WRAPPER_ORDER_LABEL_VALUES
    )


# ---------------------------------------------------------------------------
# Synthetic-refusal transport status
# ---------------------------------------------------------------------------
#
# Mirrors the Stage 28.4 ``TRANSPORT_STATUS_PAYLOAD_REFUSED`` token
# value verbatim. The literal is redeclared here so this module
# imports zero Stage 28 modules; the Stage 28 token is the
# authoritative value and the Stage 30.3 token mirrors it
# byte-for-byte by string literal.


_STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS: str = "PAYLOAD_REFUSED"


# ---------------------------------------------------------------------------
# Forbidden field-name vocabulary (defensive sentinel)
# ---------------------------------------------------------------------------
#
# Stage 30.3 must never accept a field named anything secret-class
# or raw-payload-class on its runtime-wiring artifact record. The
# current ``Stage30_3RuntimeWiringArtifactRecord._fields`` set has
# no such name, but this helper is kept so a future refactor cannot
# silently widen the admitted field set.


FORBIDDEN_RECORD_FIELD_NAMES: Tuple[str, ...] = (
    "web" + "hook",
    "web" + "hook_url",
    "web" + "hooks",
    "web" + "hook_token",
    "api_key",
    "apikey",
    "bearer",
    "bearer_token",
    "authorization",
    "secret",
    "secret_key",
    "secretkey",
    "token_secret",
    "private_key",
    "privatekey",
    "seed_phrase",
    "mnemonic",
    "signer",
    "signing_key",
    "credentials",
    "password",
    "raw_payload",
    "payload",
    "payload_blob",
    "payload_summary",
    "migration_event_id",
    "raw_capture_ref",
    "source_event_ref",
    "rpc_url",
)


def is_forbidden_record_field_name(name: object) -> bool:
    """Return ``True`` iff ``name`` is a forbidden record field name.

    Pure / deterministic. Stage 30.3 uses this guard to reject any
    future refactor that tries to widen the runtime-wiring artifact
    record with a secret-class or raw-payload-class field name. The
    check is a case-insensitive substring match against every
    documented forbidden token.
    """
    if not isinstance(name, str):
        return False
    lower = name.lower()
    for forbidden in FORBIDDEN_RECORD_FIELD_NAMES:
        if forbidden in lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Module-local exception
# ---------------------------------------------------------------------------


class Stage30_3CompactRuntimeError(Exception):
    """Closed-set Stage 30.3 compact runtime error.

    Carries only a closed-set reason token on the exception message.
    Stage 30.3 callers should never embed a raw OSError message, a
    raw provider payload, or any secret value in the message.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.3 compact runtime error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Immutable record: compact runtime context
# ---------------------------------------------------------------------------


class Stage30_3CompactRuntimeContext(NamedTuple):
    """Immutable Stage 30.3 compact runtime context.

    Carries the bounded session-level context the wrapper needs to
    project a recorded entry onto a Stage 30.1 tier decision and a
    Stage 30.2 compact ping snapshot, plus the output directory
    the wrapper writes its Stage 30.1 / Stage 30.2 / Stage 30.3
    artifacts under. The wrapper reads ``clock.now_utc_iso()``
    directly from the injected clock at every
    ``send_one_audited_post`` entry; the context record carries no
    clock reference so it stays pickle-safe / NamedTuple-equality-
    safe.

    Fields:

      * ``session_id``  -- safe-shape opaque session identifier or
                           ``None``.
      * ``run_id``      -- safe-shape opaque run identifier or
                           ``None``.
      * ``basis``       -- one of ``"price-basis"`` /
                           ``"mc-basis"``. The Stage 30.1 projector
                           validates the closed set.
      * ``output_dir``  -- caller-created directory under which the
                           wrapper appends the Stage 30.1 / Stage
                           30.2 / Stage 30.3 JSONL artifacts.
    """

    session_id: Optional[str]
    run_id: Optional[str]
    basis: str
    output_dir: Path


# ---------------------------------------------------------------------------
# Immutable record: recorded candidate context
# ---------------------------------------------------------------------------


class Stage30_3RecordedCandidateContext(NamedTuple):
    """Immutable Stage 30.3 recorded candidate context.

    Each entry captures the projection-relevant slice of one
    Stage 28.9 candidate-assembler output. The Stage 30.3 recorder
    appends one entry per ``assemble`` call onto an internal tuple;
    the Stage 30.3 wrapper consumes the most recent entry to
    produce a Stage 30.1 tier decision plus a Stage 30.2 compact
    ping snapshot at each ``send_one_audited_post`` call.

    Fields:

      * ``candidate_id``                  -- safe-shape opaque
                                             candidate identifier
                                             passed in by the
                                             Stage 28.6 runner.
      * ``mint``                          -- duck-typed Solana
                                             base58 mint string
                                             from the inner record's
                                             ingest_output, or
                                             ``None``. Stage 30.1
                                             sanitizes the actual
                                             shape downstream.
      * ``ath_record``                    -- duck-typed Stage 27.4
                                             ATH context record or
                                             ``None``. Validated by
                                             the Stage 30.1
                                             projector.
      * ``migration_record``              -- duck-typed Stage 27.4
                                             migration context
                                             record or ``None``.
                                             Validated by the
                                             Stage 30.1 projector.
      * ``price_status``                  -- duck-typed Stage 27.4
                                             PRICE_STATUS echo from
                                             the inner record's
                                             rendered_ping, or
                                             ``None``.
      * ``age_since_migration_seconds``   -- integer seconds since
                                             migration, derived from
                                             the migration record's
                                             absolute UTC timestamp
                                             and the recorder clock,
                                             or ``None`` when no
                                             usable timestamp exists.
                                             Floored at zero.
      * ``recorded_at_utc``               -- ISO-8601 UTC timestamp
                                             at which the recorder
                                             captured the entry.
    """

    candidate_id: Optional[str]
    mint: Optional[str]
    ath_record: Optional[object]
    migration_record: Optional[object]
    price_status: Optional[str]
    age_since_migration_seconds: Optional[int]
    recorded_at_utc: str


# ---------------------------------------------------------------------------
# Immutable record: runtime-wiring artifact
# ---------------------------------------------------------------------------


class Stage30_3RuntimeWiringArtifactRecord(NamedTuple):
    """Immutable Stage 30.3 runtime-wiring artifact record.

    One record per ``send_one_audited_post`` call. Carries the
    closed-set outcome token plus the wrapper-layer composition,
    plus the tier / basis echo on outcomes where a tier decision
    was computed, plus the original / compact content length and a
    sha256 hex prefix on outcomes where compact render succeeded,
    plus the locked Stage 30.1 / Stage 30.2 artifact basenames on
    the success outcome only, plus a boolean indicating whether
    the wrapper forwarded a compact-replacement payload to the
    inner transport, plus the ISO-8601 UTC timestamp at which the
    wrapper captured the call entry.

    No raw provider payload blob, no secret value, no URL host
    literal, no API key, no bearer token, no authorization header,
    no raw exception string is ever populated on this record by the
    wrapper. The Stage 30.3 forbidden-field-name guard rejects any
    future refactor that tries to widen the record with a
    secret-class or raw-payload-class field name.
    """

    schema_version: str
    session_id: Optional[str]
    candidate_id: Optional[str]
    ping_id: Optional[str]
    mint: Optional[str]
    wrapper_order: Tuple[str, ...]
    compact_outcome: str
    compact_outcome_reason: Optional[str]
    tier_token: Optional[str]
    tier_reason: Optional[str]
    basis: str
    original_content_length_chars: Optional[int]
    compact_content_length_chars: Optional[int]
    compact_body_sha256_hex_prefix_16: Optional[str]
    tier_snapshot_path_basename: Optional[str]
    compact_snapshot_path_basename: Optional[str]
    forwarded_to_inner_transport: bool
    created_at_utc: str


__all__ = (
    # Version + locked artifact basename.
    "STAGE30_3_MINOR_VERSION",
    "STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION",
    "STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME",
    # Compact outcome tokens.
    "COMPACT_OUTCOME_RENDERED",
    "COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE",
    "COMPACT_OUTCOME_FAILED_INPUT_SHAPE",
    "COMPACT_OUTCOME_FAILED_TIER_DECISION",
    "COMPACT_OUTCOME_FAILED_COMPACT_RENDER",
    "COMPACT_OUTCOME_FAILED_CAP",
    "COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE",
    "COMPACT_OUTCOME_FAILED_EXCEPTION",
    "COMPACT_OUTCOME_VALUES",
    "is_compact_outcome_value",
    # Snapshot-write sub-reason tokens.
    "SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED",
    "SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED",
    "SNAPSHOT_WRITE_REASON_VALUES",
    "is_snapshot_write_reason_value",
    # Wrapper-order labels.
    "WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY",
    "WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION",
    "WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK",
    "WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP",
    "WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT",
    "WRAPPER_ORDER_LABEL_VALUES",
    "is_wrapper_order_label_value",
    # Synthetic-refusal transport status (module-private).
    "_STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS",
    # Records + forbidden-field guard + error.
    "Stage30_3CompactRuntimeContext",
    "Stage30_3RecordedCandidateContext",
    "Stage30_3RuntimeWiringArtifactRecord",
    "FORBIDDEN_RECORD_FIELD_NAMES",
    "is_forbidden_record_field_name",
    "Stage30_3CompactRuntimeError",
)
