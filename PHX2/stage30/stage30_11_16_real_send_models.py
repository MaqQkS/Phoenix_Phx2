"""Stage 30.11.16 real private transport guard models.

Stage 30.11.16 ships the passive, pure, stdlib-only MODEL layer for the
no-send-by-default real private transport GUARD -- the separate, explicitly
operator-authorized seam that sits BETWEEN the committed Stage 30.11.15 deduped
no-send compose result and an INJECTED Stage 28-shaped audited private transport.
This module ships only the carriers + closed-set vocabularies + pure safe-shape
predicates the guard composes:

  * the operator AUTHORIZATION sentinel (a typed record the ceremony must
    explicitly construct -- it carries an ``authorized`` flag, the locked confirm
    token, a safe operator label / reason, and a caller-injected timestamp);
  * the private-only TRANSPORT TARGET identity (a safe label + visibility class
    ONLY -- it carries NO url, NO host, NO env value);
  * the per-call real-send RESULT (a redaction-safe record carrying ONLY
    closed-set tokens + safe ids + safe flags -- never a body, a url, an
    exception string, or any secret);
  * the closed-set decision / reason vocabularies they share;
  * the pure safe-shape predicates (the safe operator-token shape mirrored BY
    VALUE from the audited transport's safe-identity rule, the locked
    private-operator identity check, the minimal ``{"content": ...}`` payload
    check, and the strict authorization-sentinel validator).

This module is the MODEL layer ONLY. It implements NO guard (that is
``stage30_11_16_real_private_transport_guard``), runs NO compose, calls NO
transport, sends NO message, reads NO process environment, opens NO network
connection, opens NO database, writes NO file, reserves NO dispatch, signs
nothing, trades nothing, and edits NO composer / dedupe / ATH-anchoring /
market-freshness / Stage 30.12 renderer / tier-band file. Stage 30.11.16 is fake
/ no-send by default: the real one-send ceremony remains a SEPARATE, explicitly
operator-authorized step this slice does not run.

The guard reuses the existing audited private transport (the Stage 28.4 audited
HTTP primitive wrapped by the Stage 28.9 private webhook wrapper) WITHOUT
importing it: the ceremony INJECTS that wrapper as a duck-typed
``send_one_audited_post(webhook_identity=..., payload=...)`` transport, and this
slice mirrors the two transport constants it needs (the safe private-operator
identity label + the safe-identity shape) BY VALUE rather than importing Stage
28. That keeps Stage 30.11.16 inside the closed Stage 30 dependency boundary.

Discipline:

  * Stdlib only (``dataclasses`` / ``typing``).
  * Imports NO PHX2 module (a pure leaf; mirrors the Stage 30.11.15 / 30.11.3
    model modules). The mirrored Stage 28 constants are redeclared BY VALUE; a
    manifest pin test cross-checks the mirror.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, url, host, or request-metadata
    reference; no wallet / signing / trading surface; no public / subscriber
    routing.
  * No PHX1 import. No Stage 21-29 production import.
  * No ``time`` / ``datetime`` import; timestamps are caller-injected.
  * No module-level Call node (no implicit I/O at import time; the
    ``@dataclass(frozen=True)`` decorators are decorator-list Calls, not
    body-statement Calls).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Minor version + schema identity
# ---------------------------------------------------------------------------


STAGE30_11_16_MINOR_VERSION: str = "30.11.16"


# The Stage 30.11.16 real-send guard schema version. Names the
# authorization / target / result shapes; distinct from the Stage 30.11.15 ping
# dedupe schema version. Mirrored BY VALUE by the Stage 30.11 manifest section;
# this module imports no Stage 30.11 manifest.
STAGE30_11_16_REAL_SEND_SCHEMA_VERSION: str = "stage30_11_16_v0_real_send_guard"


# The safe-shape source-stage provenance token (names the slice; never a secret
# / host / transport destination).
STAGE30_11_16_SOURCE_STAGE: str = "30.11.16"


# ---------------------------------------------------------------------------
# Locked guardrail constants
# ---------------------------------------------------------------------------


# The locked private-only target identity label. Mirrors the audited transport's
# safe private-operator identity label BY VALUE (the Stage 28.4
# ``WEBHOOK_IDENTITY_PRIVATE_OPERATOR``); a manifest pin test cross-checks the
# mirror. The guard accepts NO other identity (private-only).
STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY: str = "PRIVATE_OPERATOR_WEBHOOK"


# The locked private-only visibility class. A target whose visibility differs is
# refused (no public / subscriber / paid-tier visibility ever reaches the guard).
STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY: str = "PRIVATE_OPERATOR_ONLY"


# The ONLY key a Stage 30.11.16 forwarded payload may carry. The guard builds
# exactly ``{"content": dispatched_body}`` and refuses any payload whose key set
# is not exactly this single key -- so a routing / subscriber / audience field can
# never be smuggled through (an allowlist, strictly stronger than a denylist).
STAGE30_11_16_PAYLOAD_CONTENT_KEY: str = "content"


# The locked operator authorization confirm token. A valid authorization sentinel
# must carry EXACTLY this value -- a second, independent positive assertion (on
# top of ``authorized is True``) so a real send can never be reached by an
# accidentally-constructed record.
STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN: str = (
    "I_AUTHORIZE_ONE_REAL_PRIVATE_OPERATOR_SEND"
)


# The committed Stage 30.11.13 dispatched compose-decision token the guard
# requires on the consumed compose result. Mirrored BY VALUE from the composer's
# ``COMPOSE_DECISION_DISPATCHED``; a manifest pin test cross-checks the mirror so
# the guard never imports the composer's constant just to read a string.
STAGE30_11_16_REQUIRED_COMPOSE_DECISION: str = "NO_SEND_DISPATCHED"


# The locked one-shot dispatch cap. A guard instance forwards (or records a
# would-send for) AT MOST this many times; a second gate-passing call is refused.
STAGE30_11_16_MAX_DISPATCHES: int = 1


# The single redaction status a Stage 30.11.16 result carries (the record never
# holds a url / body / exception string / secret, so redaction always holds).
STAGE30_11_16_REDACTION_STATUS_REDACTED: str = "REDACTED"


# The safe placeholder echoed on a result when the bound target identity is not a
# safe operator token (a url-shaped / dotted / slashed value). Guarantees the
# result's ``webhook_identity`` is never an unvalidated string.
STAGE30_11_16_REDACTED_UNSAFE_IDENTITY: str = "REDACTED_UNSAFE_TARGET_IDENTITY"


# The safe placeholder echoed in place of a consumed-result id (the token mint /
# candidate id) that is not a safe-echo id -- it carries a newline / control /
# whitespace / path / url / quote character or is over-long. Guarantees the
# result's echoed ids are never an unvalidated raw string, so a forged id can
# never smuggle injected text into the redaction-safe result record.
STAGE30_11_16_REDACTED_UNSAFE_ID: str = "REDACTED_UNSAFE_ID"


# ---------------------------------------------------------------------------
# Closed-set: real-send decision
# ---------------------------------------------------------------------------
#
# Exactly one decision per guard call. ``FORWARDED_TO_TRANSPORT`` is the only
# decision on which the injected transport was reached (in tests a recording
# FAKE; a real audited transport ONLY at the separate operator-authorized
# ceremony). ``WOULD_SEND_NO_TRANSPORT`` is the no-send default (all gates passed
# but no transport was injected; nothing is reached). ``REFUSED`` covers every
# fail-closed path. Mirrored BY VALUE by the Stage 30.11 manifest.


REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT: str = "WOULD_SEND_NO_TRANSPORT"
REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT: str = "FORWARDED_TO_TRANSPORT"
REAL_SEND_DECISION_REFUSED: str = "REFUSED"


STAGE30_11_16_REAL_SEND_DECISIONS: Tuple[str, ...] = (
    REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT,
    REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT,
    REAL_SEND_DECISION_REFUSED,
)


def is_real_send_decision(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set real-send decision.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_16_REAL_SEND_DECISIONS


# ---------------------------------------------------------------------------
# Closed-set: real-send reason
# ---------------------------------------------------------------------------
#
# Exactly one reason per decision. The two pass reasons accompany the two
# non-refused decisions; every other reason is a fail-closed refusal. Mirrored BY
# VALUE by the Stage 30.11 manifest.


# Pass reasons.
REAL_SEND_REASON_WOULD_SEND_RECORDED_NO_TRANSPORT: str = (
    "WOULD_SEND_RECORDED_NO_TRANSPORT"
)
REAL_SEND_REASON_FORWARDED_ONE_PRIVATE_OPERATOR_MESSAGE: str = (
    "FORWARDED_ONE_PRIVATE_OPERATOR_MESSAGE"
)

# Refusal reasons.
REAL_SEND_REASON_NOT_AUTHORIZED: str = "NOT_AUTHORIZED"
REAL_SEND_REASON_INVALID_AUTHORIZATION_TYPE: str = "INVALID_AUTHORIZATION_TYPE"
REAL_SEND_REASON_INVALID_COMPOSE_RESULT: str = "INVALID_COMPOSE_RESULT"
REAL_SEND_REASON_COMPOSE_NOT_DISPATCHED: str = "COMPOSE_NOT_DISPATCHED"
REAL_SEND_REASON_DEDUPE_NOT_ALLOWED: str = "DEDUPE_NOT_ALLOWED"
REAL_SEND_REASON_SNAPSHOT_MISSING: str = "SNAPSHOT_MISSING"
# The consumed compose result carried a snapshot that is PRESENT but is NOT a
# real committed Stage 30.11.13 ``Stage30_11_13ComposedSnapshot`` (a forged /
# wrong-type inner object). Distinct from ``SNAPSHOT_MISSING`` (the snapshot is
# absent / ``None``): a non-``None`` snapshot that fails the real-type
# provenance check fails closed here, so a forged inner object can never be
# forwarded as if it came from the real composer + the real frozen snapshot.
REAL_SEND_REASON_INVALID_SNAPSHOT_PROVENANCE: str = "INVALID_SNAPSHOT_PROVENANCE"
REAL_SEND_REASON_BODY_MISSING: str = "BODY_MISSING"
REAL_SEND_REASON_INVALID_TARGET_IDENTITY: str = "INVALID_TARGET_IDENTITY"
REAL_SEND_REASON_FORBIDDEN_PAYLOAD_FIELD: str = "FORBIDDEN_PAYLOAD_FIELD"
REAL_SEND_REASON_CAP_EXHAUSTED: str = "CAP_EXHAUSTED"
REAL_SEND_REASON_TRANSPORT_EXCEPTION: str = "TRANSPORT_EXCEPTION"


STAGE30_11_16_REAL_SEND_REASONS: Tuple[str, ...] = (
    REAL_SEND_REASON_WOULD_SEND_RECORDED_NO_TRANSPORT,
    REAL_SEND_REASON_FORWARDED_ONE_PRIVATE_OPERATOR_MESSAGE,
    REAL_SEND_REASON_NOT_AUTHORIZED,
    REAL_SEND_REASON_INVALID_AUTHORIZATION_TYPE,
    REAL_SEND_REASON_INVALID_COMPOSE_RESULT,
    REAL_SEND_REASON_COMPOSE_NOT_DISPATCHED,
    REAL_SEND_REASON_DEDUPE_NOT_ALLOWED,
    REAL_SEND_REASON_SNAPSHOT_MISSING,
    REAL_SEND_REASON_INVALID_SNAPSHOT_PROVENANCE,
    REAL_SEND_REASON_BODY_MISSING,
    REAL_SEND_REASON_INVALID_TARGET_IDENTITY,
    REAL_SEND_REASON_FORBIDDEN_PAYLOAD_FIELD,
    REAL_SEND_REASON_CAP_EXHAUSTED,
    REAL_SEND_REASON_TRANSPORT_EXCEPTION,
)


def is_real_send_reason(value: object) -> bool:
    """Return ``True`` iff ``value`` is a closed-set real-send reason.

    Pure / total; never raises.
    """
    return isinstance(value, str) and value in STAGE30_11_16_REAL_SEND_REASONS


# ---------------------------------------------------------------------------
# Pure safe-shape predicates
# ---------------------------------------------------------------------------


def is_nonblank_str(value: object) -> bool:
    """Return ``True`` iff ``value`` is a non-empty, non-blank string.

    Pure / total; never raises. Mirrors the Stage 30.11.15 / 30.11.3 non-blank
    check BY VALUE.
    """
    return isinstance(value, str) and value.strip() != ""


def is_safe_operator_token(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-display operator token.

    Safe tokens are non-empty strings of length 1..64 made of ``A-Z`` / ``0-9`` /
    ``_`` starting with an uppercase letter. The shape mirrors the audited
    transport's safe-identity rule (the Stage 28.4
    ``is_safe_webhook_identity_label``) BY VALUE so the operator label / reason /
    target identity all share one safe shape; Stage 30.11.16 imports no Stage 28
    helper. Pure / total; never raises.
    """
    if not isinstance(value, str):
        return False
    if value == "":
        return False
    if len(value) > 64:
        return False
    first = value[0]
    if not ("A" <= first <= "Z"):
        return False
    for ch in value[1:]:
        if "A" <= ch <= "Z":
            continue
        if "0" <= ch <= "9":
            continue
        if ch == "_":
            continue
        return False
    return True


def is_safe_echo_id(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-to-echo opaque id.

    A safe-echo id is a non-empty string of length 1..128 made ONLY of ASCII
    letters / digits / ``_`` / ``-``. A base58 token mint and an underscore
    candidate id both pass; any newline / control char / whitespace / path /
    url / quote character (or an over-long value) fails. It gates the
    consumed-result ids the guard echoes into its redaction-safe result -- an
    unsafe id is replaced by ``STAGE30_11_16_REDACTED_UNSAFE_ID`` rather than
    echoed raw, so a forged id can never inject text into the result record.
    Deliberately looser than ``is_safe_operator_token`` (which bars a lowercase
    start / non-uppercase body -- too strict for a mixed-case base58 mint). Pure
    / total; never raises.
    """
    if not isinstance(value, str):
        return False
    if value == "" or len(value) > 128:
        return False
    for ch in value:
        if "A" <= ch <= "Z":
            continue
        if "a" <= ch <= "z":
            continue
        if "0" <= ch <= "9":
            continue
        if ch == "_" or ch == "-":
            continue
        return False
    return True


def is_private_operator_identity(value: object) -> bool:
    """Return ``True`` iff ``value`` is EXACTLY the locked private-operator
    identity label (a safe-shape token AND equal to
    ``STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY``).

    The guard accepts no other identity, so a non-private / unsafe identity can
    never reach the transport. Pure / total; never raises.
    """
    return (
        is_safe_operator_token(value)
        and value == STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY
    )


def is_minimal_content_payload(payload: object) -> bool:
    """Return ``True`` iff ``payload`` is EXACTLY ``{"content": <non-blank str>}``.

    An allowlist (strictly stronger than a routing-field denylist): the key set
    must be exactly the single content key, and the value must be a non-blank
    string. Any extra key (a routing / subscriber / audience field) or a
    non-string content fails closed. Pure / total; never raises.
    """
    if not isinstance(payload, dict):
        return False
    if set(payload.keys()) != {STAGE30_11_16_PAYLOAD_CONTENT_KEY}:
        return False
    return is_nonblank_str(payload.get(STAGE30_11_16_PAYLOAD_CONTENT_KEY))


# ---------------------------------------------------------------------------
# Immutable model: operator authorization sentinel
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_16RealSendAuthorization:
    """Immutable explicit operator authorization sentinel for ONE real send.

    The ceremony must construct this record explicitly AND pass it to the guard.
    It carries only safe scalars; no secret, no url, no env value. A valid
    sentinel requires ALL of: ``authorized`` is exactly ``True``,
    ``confirm_token`` equals the locked
    ``STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN``, ``operator_label`` and
    ``authorization_reason`` are safe operator tokens, and ``created_at_utc`` is a
    non-blank caller-injected timestamp.

      * ``authorized``           -- must be exactly ``True`` (a non-``True`` value
                                    is treated as not authorized).
      * ``confirm_token``        -- must equal the locked confirm token (the
                                    second positive assertion).
      * ``operator_label``       -- a safe operator-token provenance label.
      * ``authorization_reason`` -- a safe operator-token reason provenance.
      * ``created_at_utc``       -- caller-injected ISO-8601 UTC timestamp; NEVER
                                    a wall-clock read.
    """

    authorized: bool
    confirm_token: str
    operator_label: str
    authorization_reason: str
    created_at_utc: str


def is_real_send_authorization(value: object) -> bool:
    """Return ``True`` iff ``value`` is a VALID
    ``Stage30_11_16RealSendAuthorization`` sentinel.

    Strict: the right type, ``authorized is True``, the exact confirm token, safe
    operator-token ``operator_label`` / ``authorization_reason``, and a non-blank
    ``created_at_utc``. Pure / total; never raises.
    """
    return (
        isinstance(value, Stage30_11_16RealSendAuthorization)
        and value.authorized is True
        and value.confirm_token == STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN
        and is_safe_operator_token(value.operator_label)
        and is_safe_operator_token(value.authorization_reason)
        and is_nonblank_str(value.created_at_utc)
    )


# ---------------------------------------------------------------------------
# Immutable model: private-only transport target identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_16TransportTarget:
    """Immutable private-only transport target identity.

    Carries ONLY a safe-to-display webhook identity label + a visibility class;
    it carries NO url, NO host, NO env value (the real webhook is bound INSIDE the
    injected audited transport wrapper at ceremony time, never here). A valid
    target requires ``webhook_identity`` to equal the locked private-operator
    identity AND ``visibility`` to equal the locked private-operator visibility.

      * ``webhook_identity`` -- must equal
                                ``STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY``.
      * ``visibility``       -- must equal
                                ``STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY``.
    """

    webhook_identity: str
    visibility: str


def is_valid_transport_target(value: object) -> bool:
    """Return ``True`` iff ``value`` is a VALID private-only
    ``Stage30_11_16TransportTarget`` (locked identity AND locked visibility).

    Pure / total; never raises.
    """
    return (
        isinstance(value, Stage30_11_16TransportTarget)
        and is_private_operator_identity(value.webhook_identity)
        and value.visibility == STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY
    )


# ---------------------------------------------------------------------------
# Immutable model: per-call real-send result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage30_11_16RealSendResult:
    """Immutable per-call Stage 30.11.16 real-send guard result.

    The guard emits exactly one of these per ``authorize_and_dispatch`` call. It
    echoes the safe candidate identity, pins the closed-set ``decision`` /
    ``reason``, records whether a forward happened + whether the injected
    transport was reached + the duck-read transport status / ok flag, echoes the
    safe webhook identity label, and records whether the one-shot cap was
    consumed. It carries ONLY safe scalars + closed-set tokens: NO body, NO url,
    NO exception text, NO secret.

      * ``decision``            -- one of ``STAGE30_11_16_REAL_SEND_DECISIONS``.
      * ``reason``              -- one of ``STAGE30_11_16_REAL_SEND_REASONS``.
      * ``token_mint`` / ``candidate_id`` -- echoed safe-shape ids (``""`` when
                                  unreadable from the consumed result).
      * ``dispatch_forwarded``  -- ``True`` ONLY for ``FORWARDED_TO_TRANSPORT``.
      * ``transport_attempted`` -- ``True`` iff the injected transport was called
                                  (a forward or a transport-exception path).
      * ``transport_status``    -- the duck-read transport status token, or
                                  ``None`` when no transport was reached.
      * ``transport_ok``        -- the duck-read transport ok flag, or ``None``
                                  when no transport was reached / it returned a
                                  non-bool ok (NEVER fabricated to ``True``).
      * ``webhook_identity``    -- the safe-to-display target identity label
                                  (NEVER a url).
      * ``cap_consumed``        -- ``True`` iff this call consumed the one-shot
                                  cap (a gate-passing would-send / forward /
                                  transport-exception).
      * ``redaction_status``    -- the locked ``REDACTED`` token.
      * ``created_at_utc``      -- caller-injected ISO-8601 UTC timestamp; NEVER a
                                  wall-clock read.
    """

    decision: str
    reason: str
    token_mint: str
    candidate_id: str
    dispatch_forwarded: bool
    transport_attempted: bool
    transport_status: Optional[str]
    transport_ok: Optional[bool]
    webhook_identity: str
    cap_consumed: bool
    redaction_status: str
    created_at_utc: str


# ---------------------------------------------------------------------------
# Field-name helpers (pure; read dataclass field names)
# ---------------------------------------------------------------------------


def real_send_authorization_field_names() -> Tuple[str, ...]:
    """Return the authorization sentinel field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_16RealSendAuthorization))


def transport_target_field_names() -> Tuple[str, ...]:
    """Return the transport target field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_16TransportTarget))


def real_send_result_field_names() -> Tuple[str, ...]:
    """Return the real-send result field names as a tuple."""
    return tuple(f.name for f in fields(Stage30_11_16RealSendResult))


__all__ = (
    # Minor version + schema identity.
    "STAGE30_11_16_MINOR_VERSION",
    "STAGE30_11_16_REAL_SEND_SCHEMA_VERSION",
    "STAGE30_11_16_SOURCE_STAGE",
    # Locked guardrail constants.
    "STAGE30_11_16_PRIVATE_OPERATOR_IDENTITY",
    "STAGE30_11_16_PRIVATE_OPERATOR_VISIBILITY",
    "STAGE30_11_16_PAYLOAD_CONTENT_KEY",
    "STAGE30_11_16_AUTHORIZATION_CONFIRM_TOKEN",
    "STAGE30_11_16_REQUIRED_COMPOSE_DECISION",
    "STAGE30_11_16_MAX_DISPATCHES",
    "STAGE30_11_16_REDACTION_STATUS_REDACTED",
    "STAGE30_11_16_REDACTED_UNSAFE_IDENTITY",
    "STAGE30_11_16_REDACTED_UNSAFE_ID",
    # Decisions.
    "REAL_SEND_DECISION_WOULD_SEND_NO_TRANSPORT",
    "REAL_SEND_DECISION_FORWARDED_TO_TRANSPORT",
    "REAL_SEND_DECISION_REFUSED",
    "STAGE30_11_16_REAL_SEND_DECISIONS",
    "is_real_send_decision",
    # Reasons.
    "REAL_SEND_REASON_WOULD_SEND_RECORDED_NO_TRANSPORT",
    "REAL_SEND_REASON_FORWARDED_ONE_PRIVATE_OPERATOR_MESSAGE",
    "REAL_SEND_REASON_NOT_AUTHORIZED",
    "REAL_SEND_REASON_INVALID_AUTHORIZATION_TYPE",
    "REAL_SEND_REASON_INVALID_COMPOSE_RESULT",
    "REAL_SEND_REASON_COMPOSE_NOT_DISPATCHED",
    "REAL_SEND_REASON_DEDUPE_NOT_ALLOWED",
    "REAL_SEND_REASON_SNAPSHOT_MISSING",
    "REAL_SEND_REASON_INVALID_SNAPSHOT_PROVENANCE",
    "REAL_SEND_REASON_BODY_MISSING",
    "REAL_SEND_REASON_INVALID_TARGET_IDENTITY",
    "REAL_SEND_REASON_FORBIDDEN_PAYLOAD_FIELD",
    "REAL_SEND_REASON_CAP_EXHAUSTED",
    "REAL_SEND_REASON_TRANSPORT_EXCEPTION",
    "STAGE30_11_16_REAL_SEND_REASONS",
    "is_real_send_reason",
    # Safe-shape predicates.
    "is_nonblank_str",
    "is_safe_operator_token",
    "is_safe_echo_id",
    "is_private_operator_identity",
    "is_minimal_content_payload",
    # Models.
    "Stage30_11_16RealSendAuthorization",
    "is_real_send_authorization",
    "Stage30_11_16TransportTarget",
    "is_valid_transport_target",
    "Stage30_11_16RealSendResult",
    # Field-name helpers.
    "real_send_authorization_field_names",
    "transport_target_field_names",
    "real_send_result_field_names",
)
