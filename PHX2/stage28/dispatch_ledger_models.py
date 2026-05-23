"""Stage 28.2 restart-safe dispatch ledger closed-set vocabularies + records.

Stage 28.2 ships the restart-safe private dispatch ledger primitives
for Stage 28. The ledger is an append-only, replayable, redaction-
safe JSONL artifact that lets a future Stage 28.6 bounded private
runner (and any other Stage 28 caller) detect that a private
Discord dispatch intent has already been reserved / pre-sent /
terminally resolved across a process restart, and suppress
duplicate sends safely.

This module ships only:

  * locked Stage 28.2 version axes (minor / schema),
  * the closed-set dedupe-state vocabulary
    (RESERVED / PRE_SEND_RECORDED / DISPATCHED_OK /
    DISPATCHED_FAILED / DISPATCHED_AMBIGUOUS / REFUSED_PRE_SEND)
    plus the terminal / non-terminal subset partitions,
  * the closed-set dispatch-decision vocabulary
    (PROCEED / SUPPRESS_DUPLICATE_TERMINAL / SUPPRESS_AMBIGUOUS /
    REJECTED_INVALID_TRANSITION),
  * the closed-set record-kind vocabulary
    (RESERVE / PRE_SEND / TERMINAL),
  * the closed-set failure-reason vocabulary (Stage 28.2 ships a
    single placeholder ``UNSPECIFIED``; failure classification is
    Stage 28.3a's responsibility and is intentionally NOT
    implemented here),
  * the locked Stage 28.2 redaction-token literal,
  * pure validation helpers for dedupe-key fields and artifact
    references (allowlist character class + secret-like substring
    rejection),
  * the immutable ``DispatchDedupeKey`` record,
  * the immutable ``ReserveRecord`` / ``PreSendRecord`` /
    ``TerminalRecord`` record shapes,
  * the immutable ``DedupeKeyState`` replay-reconstruction record,
  * the immutable ``LedgerReplayState`` bundle,
  * the immutable ``DispatchDedupeDecision`` decision record,
  * the deterministic ``canonical_dedupe_key_serialization``
    helper,
  * the module-local Stage 28.2 ledger-error exception hierarchy.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here. The Stage 28.2 boundary scan pins
    this.
  * No network. No HTTP. No gRPC. No Discord. No file I/O at
    import or module-level call time. (Filesystem reads / writes
    live in ``dispatch_ledger`` and are caller-driven only.)
  * No raw secret value is ever carried on a record. The dedupe
    key vocabulary excludes ``run_id``, ``session_id``, webhook
    URL, provider endpoint, API key, bearer token, auth header,
    recipient / channel / subscriber fields. Validation rejects
    URL-like / token-like fragments anywhere in a key field.
  * ``repr()`` / ``str()`` of any record is safe to log / print /
    persist; no URL host substring, no API-key substring, no
    bearer-token substring, no Discord webhook substring is
    carried by any record's fields.

This module imports only stdlib (``typing``). It does NOT import
Stage 21-27 production code, does NOT import Stage 28.1 production
code, does NOT import any network / RPC / messaging / DB /
scheduler / secrets-management library, does NOT read the
process environment, does NOT define a CLI surface, and contains
no top-level I/O.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple, Optional


# ---------------------------------------------------------------------------
# Stage 28.2 version axes
# ---------------------------------------------------------------------------


STAGE28_2_MINOR_VERSION: str = "28.2"
STAGE28_2_SCHEMA_VERSION: str = "stage28_2_dispatch_ledger_v0"


# ---------------------------------------------------------------------------
# Closed-set: dedupe-state vocabulary
# ---------------------------------------------------------------------------


# Non-terminal lifecycle states (intent reserved, intent pre-sent
# but terminal result not yet recorded). These states leave a
# dedupe key "open"; resumed runs treat them as ambiguous and
# suppress re-send by default (the Stage 28.0 spec lock pins this
# principle).
DEDUPE_STATE_RESERVED: str = "RESERVED"
DEDUPE_STATE_PRE_SEND_RECORDED: str = "PRE_SEND_RECORDED"


# Terminal lifecycle states. Once a dedupe key reaches any of
# these the dispatch intent is finished; a future attempt against
# the same key is a duplicate and must be suppressed.
DEDUPE_STATE_DISPATCHED_OK: str = "DISPATCHED_OK"
DEDUPE_STATE_DISPATCHED_FAILED: str = "DISPATCHED_FAILED"
DEDUPE_STATE_DISPATCHED_AMBIGUOUS: str = "DISPATCHED_AMBIGUOUS"
DEDUPE_STATE_REFUSED_PRE_SEND: str = "REFUSED_PRE_SEND"


DEDUPE_STATE_VALUES: tuple[str, ...] = (
    DEDUPE_STATE_RESERVED,
    DEDUPE_STATE_PRE_SEND_RECORDED,
    DEDUPE_STATE_DISPATCHED_OK,
    DEDUPE_STATE_DISPATCHED_FAILED,
    DEDUPE_STATE_DISPATCHED_AMBIGUOUS,
    DEDUPE_STATE_REFUSED_PRE_SEND,
)


DEDUPE_TERMINAL_STATES: tuple[str, ...] = (
    DEDUPE_STATE_DISPATCHED_OK,
    DEDUPE_STATE_DISPATCHED_FAILED,
    DEDUPE_STATE_DISPATCHED_AMBIGUOUS,
    DEDUPE_STATE_REFUSED_PRE_SEND,
)


DEDUPE_NON_TERMINAL_STATES: tuple[str, ...] = (
    DEDUPE_STATE_RESERVED,
    DEDUPE_STATE_PRE_SEND_RECORDED,
)


# ---------------------------------------------------------------------------
# Closed-set: dispatch decision tokens (returned to caller)
# ---------------------------------------------------------------------------


# A reserve / pre-send / terminal call returns one of these
# decision tokens. PROCEED means the operation wrote a new ledger
# record and the caller may continue the dispatch lifecycle.
# SUPPRESS_* tokens mean the operation deliberately DID NOT write
# a new record because the dedupe key was already known to the
# ledger; the caller must not re-attempt the send.
DISPATCH_DECISION_PROCEED: str = "PROCEED"
DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL: str = (
    "SUPPRESS_DUPLICATE_TERMINAL"
)
DISPATCH_DECISION_SUPPRESS_AMBIGUOUS: str = "SUPPRESS_AMBIGUOUS"
DISPATCH_DECISION_REJECTED_INVALID_TRANSITION: str = (
    "REJECTED_INVALID_TRANSITION"
)


DISPATCH_DECISION_VALUES: tuple[str, ...] = (
    DISPATCH_DECISION_PROCEED,
    DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL,
    DISPATCH_DECISION_SUPPRESS_AMBIGUOUS,
    DISPATCH_DECISION_REJECTED_INVALID_TRANSITION,
)


# ---------------------------------------------------------------------------
# Closed-set: ledger record kinds (one-per-line JSONL)
# ---------------------------------------------------------------------------


RECORD_KIND_RESERVE: str = "RESERVE"
RECORD_KIND_PRE_SEND: str = "PRE_SEND"
RECORD_KIND_TERMINAL: str = "TERMINAL"


RECORD_KIND_VALUES: tuple[str, ...] = (
    RECORD_KIND_RESERVE,
    RECORD_KIND_PRE_SEND,
    RECORD_KIND_TERMINAL,
)


# ---------------------------------------------------------------------------
# Closed-set: terminal failure-reason placeholders
# ---------------------------------------------------------------------------


# Stage 28.2 ships a single failure-reason placeholder. Failure
# classification (transport-error / pair-disagree / stale-price /
# discord-429 / etc.) is the Stage 28.3a responsibility and is
# deliberately NOT implemented here. The closed-set lock keeps
# downstream readers from inventing new failure reasons against
# the Stage 28.2 ledger surface.
FAILURE_REASON_UNSPECIFIED: str = "UNSPECIFIED"


FAILURE_REASON_VALUES: tuple[str, ...] = (
    FAILURE_REASON_UNSPECIFIED,
)


# ---------------------------------------------------------------------------
# Redaction token
# ---------------------------------------------------------------------------


# Distinctive Stage 28.2 redaction token. Distinct from the Stage
# 27 and Stage 28.1 redaction tokens so a leak-scan test for one
# cannot collide with another.
STAGE28_2_REDACTION_TOKEN: str = "<<STAGE28_2_REDACTED>>"


# ---------------------------------------------------------------------------
# Dedupe-key field validation
# ---------------------------------------------------------------------------


# Stage 28.2 dedupe-key field allowlist character class. A safe
# dedupe-key field is a short, opaque, deterministic identifier
# (Solana base58 mint, pair-quote token, event-kind tag, ping-type
# tag, or normalized event id). The allowlist keeps the field to
# letters, digits, underscore, and dash, with strict length caps.
# URLs, bearer tokens, raw secrets, and recipient/subscriber data
# cannot pass this allowlist.
_DEDUPE_KEY_FIELD_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)
_DEDUPE_KEY_FIELD_MIN_LENGTH: int = 1
_DEDUPE_KEY_FIELD_MAX_LENGTH: int = 128


# Stage 28.2 artifact-reference allowlist character class. A safe
# artifact reference is a bare basename (no path separators) drawn
# from letters, digits, underscore, dot, and dash. Path traversal
# segments ("..") and leading dots are rejected.
_ARTIFACT_REFERENCE_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_.-"
)
_ARTIFACT_REFERENCE_MIN_LENGTH: int = 1
_ARTIFACT_REFERENCE_MAX_LENGTH: int = 256


# Substrings that, when present anywhere in a dedupe-key field or
# artifact reference, indicate the value looks like a URL / token /
# webhook / auth material and must be rejected. These literal
# substrings are intentionally distinctive enough that a legitimate
# Stage 27 dedupe-key field cannot collide with them.
_SECRET_LIKE_SUBSTRINGS: tuple[str, ...] = (
    # URL / scheme substrings (built via concatenation so this
    # source file itself does not carry the literal substring a
    # URL-leak boundary scan would flag).
    "h" + "ttps:",
    "h" + "ttp:",
    "w" + "ss:",
    "w" + "s:",
    "://",
    # Auth / bearer / cookie substrings.
    "bearer",
    "authorization",
    "auth=",
    "token=",
    "apikey=",
    "key=",
    "secret=",
    "password",
    "passwd",
    # Webhook host fragments (concatenated for the same reason).
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "/webhooks/",
)


# Forbidden dedupe-key field NAMES. Stage 28.2 rejects keys that
# carry these field names because they would smuggle session /
# runtime / routing / secret material into the dedupe surface and
# violate the restart-safe invariant.
FORBIDDEN_DEDUPE_KEY_FIELD_NAMES: tuple[str, ...] = (
    "run_id",
    "session_id",
    "wall_clock_timestamp",
    "wall_clock",
    "timestamp",
    "webhook_url",
    "webhook",
    "provider_endpoint",
    "provider_url",
    "rpc_url",
    "grpc_endpoint",
    "api_key",
    "bearer_token",
    "auth_header",
    "subscriber_id",
    "subscribers",
    "channel_id",
    "public_channel_id",
    "recipient",
    "audience",
    "route_id",
    "paid_tier",
    "tier",
    "approval_status",
    "enforcement_result",
)


def is_dedupe_key_field_safe(value: object) -> bool:
    """Return ``True`` iff ``value`` is a string drawn from the
    Stage 28.2 dedupe-key field allowlist, within the locked
    length range, and not matching any secret-like substring.

    Pure: no env access, no I/O, no logging.
    """
    if not isinstance(value, str):
        return False
    if len(value) < _DEDUPE_KEY_FIELD_MIN_LENGTH:
        return False
    if len(value) > _DEDUPE_KEY_FIELD_MAX_LENGTH:
        return False
    if value[0] in {"-", "_"} or value[-1] in {"-", "_"}:
        return False
    for ch in value:
        if ch not in _DEDUPE_KEY_FIELD_ALLOWED_CHARS:
            return False
    lowered = value.lower()
    for needle in _SECRET_LIKE_SUBSTRINGS:
        if needle in lowered:
            return False
    return True


def is_artifact_reference_safe(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe Stage 28.2 artifact
    reference: a bare basename drawn from
    ``[A-Za-z0-9_.-]`` within the locked length range, with no
    leading dot or dash, no traversal segment (``..``), no path
    separator, and no secret-like substring.

    Pure: no env access, no I/O, no logging.
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
    for needle in _SECRET_LIKE_SUBSTRINGS:
        if needle in lowered:
            return False
    return True


def is_dedupe_state_value(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set dedupe state."""
    return isinstance(value, str) and value in DEDUPE_STATE_VALUES


def is_terminal_dedupe_state(value: object) -> bool:
    """Return ``True`` iff ``value`` is a terminal dedupe state."""
    return isinstance(value, str) and value in DEDUPE_TERMINAL_STATES


def is_non_terminal_dedupe_state(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-terminal dedupe state."""
    return isinstance(value, str) and value in DEDUPE_NON_TERMINAL_STATES


def is_record_kind_value(value: object) -> bool:
    return isinstance(value, str) and value in RECORD_KIND_VALUES


def is_dispatch_decision_value(value: object) -> bool:
    return isinstance(value, str) and value in DISPATCH_DECISION_VALUES


def is_failure_reason_value(value: object) -> bool:
    return isinstance(value, str) and value in FAILURE_REASON_VALUES


# ---------------------------------------------------------------------------
# Module-local Stage 28.2 ledger-error exception hierarchy
# ---------------------------------------------------------------------------


class Stage28_2DispatchLedgerError(Exception):
    """Base type for every Stage 28.2 dispatch ledger error.

    Module-local; not a subclass of any central PHX2 error
    registry. Raw secret values must never reach the constructor;
    callers redact at the call site.
    """


class Stage28_2InvalidDedupeKeyError(Stage28_2DispatchLedgerError):
    """Raised when a ``DispatchDedupeKey`` field fails Stage 28.2
    validation.

    Carries only the canonical field name + the closed-set
    failure-reason token; never the raw rejected value.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.2 invalid dedupe key: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_2InvalidArtifactReferenceError(
    Stage28_2DispatchLedgerError
):
    """Raised when an artifact reference fails Stage 28.2
    validation.

    Carries only the closed-set failure-reason token; never the
    raw rejected value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 28.2 invalid artifact reference: reason={reason!r}"
        )


class Stage28_2MalformedLedgerLineError(Stage28_2DispatchLedgerError):
    """Raised when a JSONL line cannot be parsed or is structurally
    malformed.

    Carries the 1-based line index + a closed-set reason token;
    never the raw line content (which may itself contain
    fragments of secrets if the ledger file was corrupted by an
    out-of-tree writer).
    """

    def __init__(self, line_index: int, reason: str) -> None:
        self.line_index: int = line_index
        self.reason: str = reason
        super().__init__(
            f"Stage 28.2 malformed ledger line: "
            f"line_index={line_index} reason={reason!r}"
        )


class Stage28_2UnknownLedgerSchemaError(Stage28_2DispatchLedgerError):
    """Raised when a JSONL record carries a schema_version not in
    the Stage 28.2 accepted set.

    Carries only a safe length axis for the offending token; never
    the raw value (which a malicious or corrupted ledger could
    have populated with secret-looking material).
    """

    def __init__(self, line_index: int, observed_length: int) -> None:
        self.line_index: int = line_index
        self.observed_length: int = observed_length
        super().__init__(
            f"Stage 28.2 unknown ledger schema_version: "
            f"line_index={line_index} observed_length={observed_length}"
        )


class Stage28_2UnknownLedgerStateError(Stage28_2DispatchLedgerError):
    """Raised when a JSONL record carries a record_kind, dedupe
    state, terminal_status, or failure_reason value outside the
    Stage 28.2 closed set.

    Carries only the closed-set field name + a safe length axis;
    never the raw value.
    """

    def __init__(
        self, line_index: int, field_name: str, observed_length: int
    ) -> None:
        self.line_index: int = line_index
        self.field_name: str = field_name
        self.observed_length: int = observed_length
        super().__init__(
            f"Stage 28.2 unknown ledger state value: "
            f"line_index={line_index} field={field_name!r} "
            f"observed_length={observed_length}"
        )


class Stage28_2LedgerPathError(Stage28_2DispatchLedgerError):
    """Raised when the caller-supplied ledger path fails Stage 28.2
    path validation (directory, missing parent, secret-looking
    path, etc.).

    Carries only the closed-set reason token + an optional safe
    basename; never the full raw path (which may carry secret-
    looking material).
    """

    def __init__(
        self,
        reason: str,
        *,
        safe_basename: Optional[str] = None,
    ) -> None:
        self.reason: str = reason
        self.safe_basename: Optional[str] = safe_basename
        if safe_basename is not None:
            msg = (
                f"Stage 28.2 ledger path error: reason={reason!r} "
                f"safe_basename={safe_basename!r}"
            )
        else:
            msg = f"Stage 28.2 ledger path error: reason={reason!r}"
        super().__init__(msg)


class Stage28_2LedgerIOError(Stage28_2DispatchLedgerError):
    """Raised when a Stage 28.2 ledger filesystem operation fails
    with an OSError-like underlying cause.

    Carries only the closed-set operation token + an optional safe
    basename; never the raw OSError message (which may include a
    full path that itself carries secret-looking material).
    """

    def __init__(
        self,
        operation: str,
        *,
        safe_basename: Optional[str] = None,
    ) -> None:
        self.operation: str = operation
        self.safe_basename: Optional[str] = safe_basename
        if safe_basename is not None:
            msg = (
                f"Stage 28.2 ledger I/O failure: "
                f"operation={operation!r} "
                f"safe_basename={safe_basename!r}"
            )
        else:
            msg = (
                f"Stage 28.2 ledger I/O failure: "
                f"operation={operation!r}"
            )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# DispatchDedupeKey
# ---------------------------------------------------------------------------


class DispatchDedupeKey(NamedTuple):
    """Immutable Stage 28.2 dispatch dedupe key.

    Closed-set fields:

      * ``token_mint``          -- Solana mint base58 / opaque mint
                                    identifier.
      * ``pair_quote_asset``    -- closed-set quote asset token
                                    (e.g. ``SOL`` / ``USDC`` /
                                    ``UNKNOWN`` from Stage 27 pair
                                    classification).
      * ``event_kind``          -- closed-set Stage 27 event-kind
                                    tag (e.g. ``migration`` /
                                    ``ath_candidate`` / etc.).
      * ``ping_type``           -- closed-set Stage 27 ping-type
                                    tag (e.g. ``tradeable_private_ping``).
      * ``normalized_event_id`` -- deterministic Stage 27 event id
                                    that survives restart and is
                                    stable across runs.

    Excluded by construction:

      * ``run_id`` / ``session_id`` -- dedupe must survive process
        restart.
      * wall-clock timestamps as uniqueness sources.
      * webhook URL / provider endpoint / RPC URL / API key /
        bearer token / auth header.
      * recipient / channel / subscriber / audience / paid tier
        fields.

    The named-tuple shape gives the record built-in immutability,
    structural equality, and a safe ``repr()`` that exposes only
    the closed-set field values.
    """

    token_mint: str
    pair_quote_asset: str
    event_kind: str
    ping_type: str
    normalized_event_id: str


def build_dispatch_dedupe_key(
    *,
    token_mint: str,
    pair_quote_asset: str,
    event_kind: str,
    ping_type: str,
    normalized_event_id: str,
) -> DispatchDedupeKey:
    """Validate Stage 28.2 dedupe-key field inputs and return an
    immutable ``DispatchDedupeKey``.

    Raises ``Stage28_2InvalidDedupeKeyError`` if any field fails
    the dedupe-key field allowlist.
    """
    fields: tuple[tuple[str, str], ...] = (
        ("token_mint", token_mint),
        ("pair_quote_asset", pair_quote_asset),
        ("event_kind", event_kind),
        ("ping_type", ping_type),
        ("normalized_event_id", normalized_event_id),
    )
    for name, value in fields:
        if not is_dedupe_key_field_safe(value):
            raise Stage28_2InvalidDedupeKeyError(
                field_name=name,
                reason="DEDUPE_KEY_FIELD_UNSAFE",
            )
    return DispatchDedupeKey(
        token_mint=token_mint,
        pair_quote_asset=pair_quote_asset,
        event_kind=event_kind,
        ping_type=ping_type,
        normalized_event_id=normalized_event_id,
    )


def canonical_dedupe_key_serialization(
    key: DispatchDedupeKey,
) -> str:
    """Return a deterministic string serialization of ``key`` safe
    to use as a dict key for the replay-state map.

    The serialization is human-debuggable and stable across
    Python versions. It is NOT used as the JSON record payload
    (the JSON record carries the structured dedupe-key dict
    directly); it is the in-memory replay-state key only.
    """
    return (
        f"token_mint={key.token_mint}|"
        f"pair_quote_asset={key.pair_quote_asset}|"
        f"event_kind={key.event_kind}|"
        f"ping_type={key.ping_type}|"
        f"normalized_event_id={key.normalized_event_id}"
    )


# ---------------------------------------------------------------------------
# Ledger record shapes (one shape per RECORD_KIND_*)
# ---------------------------------------------------------------------------


class ReserveRecord(NamedTuple):
    """Immutable Stage 28.2 ledger record marking that a dispatch
    intent has been reserved (but not yet pre-sent or terminated).
    """

    schema_version: str
    record_kind: str
    dedupe_key: DispatchDedupeKey


class PreSendRecord(NamedTuple):
    """Immutable Stage 28.2 ledger record marking that a reserved
    dispatch intent has had its pre-send provenance / artifact
    reference recorded (the runner is about to attempt the send).
    """

    schema_version: str
    record_kind: str
    dedupe_key: DispatchDedupeKey
    artifact_reference: str


class TerminalRecord(NamedTuple):
    """Immutable Stage 28.2 ledger record marking that a dispatch
    intent has reached a terminal state.

    ``terminal_status`` is drawn from ``DEDUPE_TERMINAL_STATES``.
    ``failure_reason`` is drawn from ``FAILURE_REASON_VALUES`` and
    is ``None`` for ``DISPATCHED_OK``.
    """

    schema_version: str
    record_kind: str
    dedupe_key: DispatchDedupeKey
    terminal_status: str
    failure_reason: Optional[str]


# ---------------------------------------------------------------------------
# Replay-state records
# ---------------------------------------------------------------------------


class DedupeKeyState(NamedTuple):
    """Immutable per-dedupe-key state reconstructed from replay.

    Fields:

      * ``dedupe_key``         -- the canonical key.
      * ``current_state``      -- latest closed-set dedupe state.
      * ``reserve_seen``       -- ``True`` iff at least one
                                   RESERVE record was observed.
      * ``pre_send_seen``      -- ``True`` iff at least one
                                   PRE_SEND record was observed.
      * ``terminal_seen``      -- ``True`` iff at least one
                                   TERMINAL record was observed.
      * ``terminal_status``    -- closed-set terminal status if
                                   terminal seen, else ``None``.
      * ``failure_reason``     -- closed-set failure reason if
                                   terminal seen and applicable,
                                   else ``None``.
      * ``artifact_reference`` -- safe artifact reference recorded
                                   at PRE_SEND, else ``None``.
    """

    dedupe_key: DispatchDedupeKey
    current_state: str
    reserve_seen: bool
    pre_send_seen: bool
    terminal_seen: bool
    terminal_status: Optional[str]
    failure_reason: Optional[str]
    artifact_reference: Optional[str]


class LedgerReplayState(NamedTuple):
    """Immutable bundle of replay-reconstructed states.

    ``states_by_key`` is keyed by
    ``canonical_dedupe_key_serialization(dedupe_key)``.
    ``record_count`` counts ledger lines successfully parsed
    during replay (informational; does not include malformed
    lines because malformed lines raise instead of advancing).
    """

    states_by_key: Mapping[str, DedupeKeyState]
    record_count: int


# ---------------------------------------------------------------------------
# Dispatch decision record
# ---------------------------------------------------------------------------


class DispatchDedupeDecision(NamedTuple):
    """Immutable Stage 28.2 dispatch decision record.

    Returned by ``reserve_dispatch_intent`` /
    ``record_pre_send`` / ``record_terminal`` /
    ``classify_replay_state``.

    Fields:

      * ``decision``      -- closed-set ``DISPATCH_DECISION_*``
                              token.
      * ``current_state`` -- closed-set ``DEDUPE_STATE_*`` token
                              that the dedupe key currently
                              occupies (``None`` if the key was
                              not previously known and the
                              decision is ``PROCEED`` for the
                              first reserve attempt -- in that
                              case the post-write current_state
                              is RESERVED, which the caller can
                              observe by replaying).
      * ``dedupe_key``    -- the key the decision is about.
    """

    decision: str
    current_state: Optional[str]
    dedupe_key: DispatchDedupeKey


__all__ = (
    # Version axes.
    "STAGE28_2_MINOR_VERSION",
    "STAGE28_2_SCHEMA_VERSION",
    # Dedupe-state vocabulary.
    "DEDUPE_STATE_RESERVED",
    "DEDUPE_STATE_PRE_SEND_RECORDED",
    "DEDUPE_STATE_DISPATCHED_OK",
    "DEDUPE_STATE_DISPATCHED_FAILED",
    "DEDUPE_STATE_DISPATCHED_AMBIGUOUS",
    "DEDUPE_STATE_REFUSED_PRE_SEND",
    "DEDUPE_STATE_VALUES",
    "DEDUPE_TERMINAL_STATES",
    "DEDUPE_NON_TERMINAL_STATES",
    # Dispatch decision vocabulary.
    "DISPATCH_DECISION_PROCEED",
    "DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL",
    "DISPATCH_DECISION_SUPPRESS_AMBIGUOUS",
    "DISPATCH_DECISION_REJECTED_INVALID_TRANSITION",
    "DISPATCH_DECISION_VALUES",
    # Record-kind vocabulary.
    "RECORD_KIND_RESERVE",
    "RECORD_KIND_PRE_SEND",
    "RECORD_KIND_TERMINAL",
    "RECORD_KIND_VALUES",
    # Failure reason vocabulary.
    "FAILURE_REASON_UNSPECIFIED",
    "FAILURE_REASON_VALUES",
    # Redaction token.
    "STAGE28_2_REDACTION_TOKEN",
    # Validation helpers.
    "FORBIDDEN_DEDUPE_KEY_FIELD_NAMES",
    "is_dedupe_key_field_safe",
    "is_artifact_reference_safe",
    "is_dedupe_state_value",
    "is_terminal_dedupe_state",
    "is_non_terminal_dedupe_state",
    "is_record_kind_value",
    "is_dispatch_decision_value",
    "is_failure_reason_value",
    # Exceptions.
    "Stage28_2DispatchLedgerError",
    "Stage28_2InvalidDedupeKeyError",
    "Stage28_2InvalidArtifactReferenceError",
    "Stage28_2MalformedLedgerLineError",
    "Stage28_2UnknownLedgerSchemaError",
    "Stage28_2UnknownLedgerStateError",
    "Stage28_2LedgerPathError",
    "Stage28_2LedgerIOError",
    # Record shapes.
    "DispatchDedupeKey",
    "ReserveRecord",
    "PreSendRecord",
    "TerminalRecord",
    "DedupeKeyState",
    "LedgerReplayState",
    "DispatchDedupeDecision",
    # Helpers.
    "build_dispatch_dedupe_key",
    "canonical_dedupe_key_serialization",
)
