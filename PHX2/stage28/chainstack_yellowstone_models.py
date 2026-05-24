"""Stage 28.10 Chainstack Yellowstone provider boundary models.

Stage 28.10 is a post-Stage-28-closure, post-Stage-28.9 narrow
amendment that defines the protocol / fake / models surface for a
future real Chainstack Yellowstone gRPC provider client. The
amendment ships NO real provider client, NO grpc / grpcio /
protobuf imports, NO generated *_pb2.py / *_pb2_grpc.py stubs, NO
real network access, NO real Discord send, NO Stage 29
enforcement, NO public / subscriber / paid-tier routing, NO
Telegram, NO X / social, NO automated trading, NO wallet /
private-key / signer logic, NO position sizing, and NO trade
execution.

The Stage 28.10 module ships only:

  * the sanitized payload model the future real provider client
    must project upstream Chainstack Yellowstone events into,
  * the closed-set provider-kind / auth-mode / quote-asset /
    pair-type / bonding-curve-version hint vocabularies the
    payload uses,
  * the immutable provider boundary config model + builder,
  * the module-local exception hierarchy,
  * the Stage 28.10 normalized-event dataclass that the
    Stage 28.10 event source produces (structurally compatible
    with the Stage 27.3 ``NormalizedEventLike`` Protocol and
    extended with hint attributes).

The Stage 28.10 model module imports only stdlib (``typing``)
plus the Stage 28.5 ``is_safe_identifier`` / ``is_safe_counter_value``
helpers. It does NOT import Stage 21-27 production code, does
NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network. No HTTP. No gRPC. No socket. No file I/O at
    import or call time.
  * No sleep. No backoff execution. No scheduling. No queue. No
    threads. No async. No subprocess.
  * No raw secret value is ever carried on a Stage 28.10 record.
    Provider IDs / provider kinds / endpoint labels pass the
    locked safe-label allowlist; raw endpoints, tokens,
    usernames, and passwords are never persisted on a Stage
    28.10 model record.
  * ``repr()`` / ``str()`` of any Stage 28.10 record is safe to
    log / print / persist; the dataclass shape exposes only
    closed-set field values and safe counters / identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from PHX2.stage28.health_status_models import (
    is_safe_counter_value,
    is_safe_identifier,
)


# ---------------------------------------------------------------------------
# Stage 28.10 version axes
# ---------------------------------------------------------------------------


STAGE28_10_MINOR_VERSION: str = "28.10"
STAGE28_10_SCHEMA_VERSION: str = (
    "stage28_10_chainstack_yellowstone_v0"
)


# Distinctive Stage 28.10 redaction token. Distinct from the Stage
# 27 / 28.1 / 28.2 / 28.3a / 28.3b / 28.4 / 28.5 / 28.6 / 28.7 /
# 28.9 redaction tokens so a leak-scan test for one cannot collide
# with another.
STAGE28_10_REDACTION_TOKEN: str = "<<STAGE28_10_REDACTED>>"


# ---------------------------------------------------------------------------
# Closed-set: provider kind (Stage 28.10 is one specific provider)
# ---------------------------------------------------------------------------


PROVIDER_KIND_CHAINSTACK_YELLOWSTONE: str = (
    "CHAINSTACK_YELLOWSTONE"
)


PROVIDER_KIND_VALUES: tuple[str, ...] = (
    PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
)


def is_provider_kind_value(value: object) -> bool:
    return isinstance(value, str) and value in PROVIDER_KIND_VALUES


# ---------------------------------------------------------------------------
# Closed-set: auth mode
# ---------------------------------------------------------------------------


AUTH_MODE_XTOKEN: str = "XTOKEN"
AUTH_MODE_USERNAME_PASSWORD: str = "USERNAME_PASSWORD"
AUTH_MODE_UNKNOWN: str = "UNKNOWN"


AUTH_MODE_VALUES: tuple[str, ...] = (
    AUTH_MODE_XTOKEN,
    AUTH_MODE_USERNAME_PASSWORD,
    AUTH_MODE_UNKNOWN,
)


def is_auth_mode_value(value: object) -> bool:
    return isinstance(value, str) and value in AUTH_MODE_VALUES


# ---------------------------------------------------------------------------
# Closed-set: chain
# ---------------------------------------------------------------------------


CHAIN_SOLANA: str = "SOLANA"


CHAIN_VALUES: tuple[str, ...] = (CHAIN_SOLANA,)


def is_chain_value(value: object) -> bool:
    return isinstance(value, str) and value in CHAIN_VALUES


# ---------------------------------------------------------------------------
# Closed-set: source kind
# ---------------------------------------------------------------------------


SOURCE_KIND_FAKE: str = "FAKE"
SOURCE_KIND_PROTOCOL: str = "PROTOCOL"


SOURCE_KIND_VALUES: tuple[str, ...] = (
    SOURCE_KIND_FAKE,
    SOURCE_KIND_PROTOCOL,
)


def is_source_kind_value(value: object) -> bool:
    return isinstance(value, str) and value in SOURCE_KIND_VALUES


# ---------------------------------------------------------------------------
# Closed-set: event type (Stage 28.10 carries the upstream Yellowstone
# event-type string in normalized form so the Stage 27.3 adapter can
# map it via its ``_EVENT_TYPE_TO_EVENT_KIND`` table without Stage
# 28.10 reaching across the boundary)
# ---------------------------------------------------------------------------


EVENT_TYPE_SWAP: str = "swap"
EVENT_TYPE_MIGRATION: str = "migration"
EVENT_TYPE_MINT: str = "mint"


EVENT_TYPE_VALUES: tuple[str, ...] = (
    EVENT_TYPE_SWAP,
    EVENT_TYPE_MIGRATION,
    EVENT_TYPE_MINT,
)


def is_event_type_value(value: object) -> bool:
    return isinstance(value, str) and value in EVENT_TYPE_VALUES


# ---------------------------------------------------------------------------
# Closed-set: instruction kind (Stage 28.10 owns the safe-shape hint
# alphabet for the upstream Solana instruction kind; the real
# provider client will project upstream instructions onto this set)
# ---------------------------------------------------------------------------


INSTRUCTION_KIND_PUMP_SWAP: str = "PUMP_SWAP"
INSTRUCTION_KIND_PUMP_MIGRATION: str = "PUMP_MIGRATION"
INSTRUCTION_KIND_PUMP_CREATE: str = "PUMP_CREATE"
INSTRUCTION_KIND_UNKNOWN: str = "UNKNOWN"


INSTRUCTION_KIND_VALUES: tuple[str, ...] = (
    INSTRUCTION_KIND_PUMP_SWAP,
    INSTRUCTION_KIND_PUMP_MIGRATION,
    INSTRUCTION_KIND_PUMP_CREATE,
    INSTRUCTION_KIND_UNKNOWN,
)


def is_instruction_kind_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in INSTRUCTION_KIND_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: provider quote-asset hint, pair-type hint, and
# bonding-curve-version hint. These values mirror the Stage 27.2
# closed sets (``QUOTE_ASSET_*`` / ``PAIR_TYPE_*`` /
# ``BONDING_CURVE_VERSION_*``) by string equality so the Stage 28.10
# candidate assembler can forward them to
# ``adapt_normalized_event_to_ingest_input`` verbatim. Stage 28.10
# models do NOT import the Stage 27.2 constants module; the strings
# are pinned here defensively and the boundary tests pin their match.
# ---------------------------------------------------------------------------


QUOTE_ASSET_HINT_SOL: str = "SOL"
QUOTE_ASSET_HINT_USDC: str = "USDC"
QUOTE_ASSET_HINT_UNKNOWN: str = "UNKNOWN"


QUOTE_ASSET_HINT_VALUES: tuple[str, ...] = (
    QUOTE_ASSET_HINT_SOL,
    QUOTE_ASSET_HINT_USDC,
    QUOTE_ASSET_HINT_UNKNOWN,
)


def is_quote_asset_hint_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in QUOTE_ASSET_HINT_VALUES
    )


PAIR_TYPE_HINT_PUMP_SOL: str = "PUMP_SOL"
PAIR_TYPE_HINT_PUMP_USDC: str = "PUMP_USDC"
PAIR_TYPE_HINT_UNKNOWN: str = "UNKNOWN"


PAIR_TYPE_HINT_VALUES: tuple[str, ...] = (
    PAIR_TYPE_HINT_PUMP_SOL,
    PAIR_TYPE_HINT_PUMP_USDC,
    PAIR_TYPE_HINT_UNKNOWN,
)


def is_pair_type_hint_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in PAIR_TYPE_HINT_VALUES
    )


BONDING_CURVE_VERSION_HINT_SOL_LEGACY: str = "SOL_LEGACY"
BONDING_CURVE_VERSION_HINT_USDC_FIXED: str = "USDC_FIXED"
BONDING_CURVE_VERSION_HINT_UNKNOWN: str = "UNKNOWN"


BONDING_CURVE_VERSION_HINT_VALUES: tuple[str, ...] = (
    BONDING_CURVE_VERSION_HINT_SOL_LEGACY,
    BONDING_CURVE_VERSION_HINT_USDC_FIXED,
    BONDING_CURVE_VERSION_HINT_UNKNOWN,
)


def is_bonding_curve_version_hint_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and value in BONDING_CURVE_VERSION_HINT_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: redaction status
# ---------------------------------------------------------------------------


REDACTION_STATUS_SAFE: str = "SAFE"
REDACTION_STATUS_REDACTED: str = "REDACTED"


REDACTION_STATUS_VALUES: tuple[str, ...] = (
    REDACTION_STATUS_SAFE,
    REDACTION_STATUS_REDACTED,
)


def is_redaction_status_value(value: object) -> bool:
    return (
        isinstance(value, str) and value in REDACTION_STATUS_VALUES
    )


# ---------------------------------------------------------------------------
# Safe-label / safe-substring validators
# ---------------------------------------------------------------------------


_SAFE_FIELD_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)
_SAFE_FIELD_MIN_LENGTH: int = 1
_SAFE_FIELD_MAX_LENGTH: int = 64


# Substrings that indicate URL / secret material. Concatenated
# literally so the leak scanner does not flag the canonical
# secret-shape prefixes in this module's source.
_FORBIDDEN_SECRET_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps:",
    "h" + "ttp:",
    "w" + "ss:",
    "w" + "s:",
    "://",
    "bearer",
    "authorization",
    "auth=",
    "auth_token",
    "access_token",
    "refresh_token",
    "token=",
    "apikey=",
    "api_key",
    "api-key",
    "key=",
    "secret=",
    "password",
    "passwd",
    "x-token",
    "x_token",
    "xtoken",
    "webhook",
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "/webhooks/",
    "s" + "k-",
    "p" + "k-",
)


# ---------------------------------------------------------------------------
# Private-key-like detector
# ---------------------------------------------------------------------------


# Bitcoin WIF (wallet-import-format) base58 private-key prefixes.
# Stage 28.10 rejects values starting with these as the audit-required
# strict-private-key-like ban; the tradeoff is that legitimate Solana
# mints / signatures starting with these chars (a small fraction of
# the base58 prefix space) are also rejected. Stage 28.10 test
# fixtures avoid these prefixes by construction.
_PRIVATE_KEY_LIKE_WIF_PREFIXES: tuple[str, ...] = (
    "5K", "5J", "5H", "5L",
)


# Length at which a pure-hex string is treated as private-key-like.
# 64 hex chars = 32 bytes (the Solana Ed25519 raw key size); 128 hex
# chars = 64 bytes (the Solana keypair raw bytes). Legitimate Solana
# mints / signatures use base58, not hex, so any pure-hex string of
# this length is suspicious.
_PRIVATE_KEY_LIKE_HEX_MIN_LENGTH: int = 64


# Length at which a base64-padded string is treated as private-key-
# like. Legitimate Solana mints / signatures use base58, not base64,
# and never carry the "=" padding char of base64.
_PRIVATE_KEY_LIKE_BASE64_PADDED_MIN_LENGTH: int = 44


_HEX_ALPHABET: frozenset[str] = frozenset(
    "0123456789abcdefABCDEF"
)


def _looks_private_key_like(value: object) -> bool:
    """Return ``True`` iff ``value`` resembles raw private-key or
    raw-secret material that must never appear on a public Stage
    28.10 record.

    Conservatively flags:

      * Bitcoin WIF base58 prefixes (``5K`` / ``5J`` / ``5H`` /
        ``5L``) — classic private-key markers. The audit treats
        any string carrying one of these prefixes as private-key-
        like even when length / character set otherwise pass.
      * Bracketed JSON arrays (``[1,2,3,...]``) — Solana keypair
        JSON export format for raw 64-byte keypair bytes.
      * Pure hex strings ≥ 64 chars — raw 32 / 64 byte private-key
        material hex-encoded. Legitimate Solana mints / signatures
        use base58, not hex.
      * Base64-padded strings ≥ 44 chars ending in ``"="`` — raw
        key bytes base64-encoded. Legitimate Solana mints /
        signatures use base58, never base64 with ``"="`` padding.

    Pure / deterministic. Returns ``False`` for non-string /
    empty values; the caller is responsible for the upstream
    ``isinstance`` / non-empty checks.
    """
    if not isinstance(value, str) or value == "":
        return False
    if (
        len(value) >= 2
        and value[:2] in _PRIVATE_KEY_LIKE_WIF_PREFIXES
    ):
        return True
    if value.startswith("["):
        return True
    if len(value) >= _PRIVATE_KEY_LIKE_HEX_MIN_LENGTH:
        if all(ch in _HEX_ALPHABET for ch in value):
            return True
    if (
        len(value) >= _PRIVATE_KEY_LIKE_BASE64_PADDED_MIN_LENGTH
        and value.endswith("=")
    ):
        return True
    return False


def is_safe_provider_label(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape provider /
    endpoint label (no URL substring, no secret substring, no
    private-key-like shape, short, allowlisted characters only).

    Pure / deterministic. No env access, no I/O, no logging.
    """
    if not isinstance(value, str):
        return False
    if len(value) < _SAFE_FIELD_MIN_LENGTH:
        return False
    if len(value) > _SAFE_FIELD_MAX_LENGTH:
        return False
    if value[0] in {"-", "_"} or value[-1] in {"-", "_"}:
        return False
    for ch in value:
        if ch not in _SAFE_FIELD_ALLOWED_CHARS:
            return False
    lowered = value.lower()
    for needle in _FORBIDDEN_SECRET_SUBSTRINGS:
        if needle in lowered:
            return False
    if _looks_private_key_like(value):
        return False
    return True


_SAFE_LONG_FIELD_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_.-:"
)
_SAFE_LONG_FIELD_MAX_LENGTH: int = 128


def is_safe_payload_string(value: object) -> bool:
    """Return ``True`` iff ``value`` is a safe-shape payload field
    (e.g. a mint address, signature, normalized event id).

    Longer than ``is_safe_provider_label`` because Solana mints /
    signatures legitimately reach into the 88 character range, but
    still strictly allowlisted: alphanumerics + ``_.-:`` only.

    Additionally rejects values that look like raw private-key or
    raw-secret material via ``_looks_private_key_like`` (WIF
    prefixes, bracketed JSON arrays, long pure-hex strings,
    base64-padded strings). The audit-required tradeoff is that
    legitimate Solana mints / signatures starting with the WIF
    prefixes (a small fraction of the base58 prefix space) are
    rejected; Stage 28.10 test fixtures avoid these prefixes by
    construction.
    """
    if not isinstance(value, str):
        return False
    if value == "":
        return False
    if len(value) > _SAFE_LONG_FIELD_MAX_LENGTH:
        return False
    for ch in value:
        if ch not in _SAFE_LONG_FIELD_ALLOWED_CHARS:
            return False
    lowered = value.lower()
    for needle in _FORBIDDEN_SECRET_SUBSTRINGS:
        if needle in lowered:
            return False
    if _looks_private_key_like(value):
        return False
    return True


_SAFE_ISO_UTC_ALLOWED_CHARS: frozenset[str] = frozenset(
    "0123456789-T:.+Z"
)
_SAFE_ISO_UTC_MIN_LENGTH: int = 20
_SAFE_ISO_UTC_MAX_LENGTH: int = 40


def is_safe_iso_utc(value: object) -> bool:
    """Return ``True`` iff ``value`` looks like a safe ISO-8601 UTC
    timestamp string."""
    if not isinstance(value, str):
        return False
    if len(value) < _SAFE_ISO_UTC_MIN_LENGTH:
        return False
    if len(value) > _SAFE_ISO_UTC_MAX_LENGTH:
        return False
    for ch in value:
        if ch not in _SAFE_ISO_UTC_ALLOWED_CHARS:
            return False
    return True


# ---------------------------------------------------------------------------
# Exception hierarchy (module-local)
# ---------------------------------------------------------------------------


class Stage28_10ChainstackYellowstoneError(Exception):
    """Base type for every Stage 28.10 model / config / payload
    validation error. Module-local; not a subclass of any central
    PHX2 error registry. Raw secret values must never reach the
    constructor; callers redact at the call site.
    """


class Stage28_10InvalidConfigError(
    Stage28_10ChainstackYellowstoneError,
):
    """Raised when a ``Stage28_10ChainstackYellowstoneConfig`` field
    fails the locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.10 invalid provider config: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_10InvalidPayloadError(
    Stage28_10ChainstackYellowstoneError,
):
    """Raised when a ``Stage28_10ChainstackYellowstonePayload``
    field fails the locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.10 invalid provider payload: "
            f"field={field_name!r} reason={reason!r}"
        )


class Stage28_10InvalidNormalizedEventError(
    Stage28_10ChainstackYellowstoneError,
):
    """Raised when a ``Stage28_10NormalizedEvent`` field fails the
    locked validation contract.
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name: str = field_name
        self.reason: str = reason
        super().__init__(
            f"Stage 28.10 invalid normalized event: "
            f"field={field_name!r} reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Stage28_10ChainstackYellowstoneConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage28_10ChainstackYellowstoneConfig:
    """Immutable Stage 28.10 provider boundary config.

    Implemented as a frozen ``@dataclass`` (NOT a ``NamedTuple``)
    so direct construction triggers ``__post_init__`` validation;
    callers cannot bypass the safe-shape checks by skipping the
    ``build_chainstack_yellowstone_config`` factory.

    Carries only safe-shape labels + closed-set vocabulary tokens
    + finite counters. The real endpoint URL, the real X-Token,
    the real username, and the real password are NEVER stored on
    this record; the operator keeps the raw credentials in a
    private object (or external client) and supplies only the
    safe ``endpoint_safe_label`` to identify it.

    Fields:

      * ``provider_id``         -- safe-shape provider id label
                                    (e.g. ``"chainstack_yellowstone_prod"``).
      * ``provider_kind``       -- locked
                                    ``PROVIDER_KIND_CHAINSTACK_YELLOWSTONE``
                                    string.
      * ``endpoint_safe_label`` -- safe-shape short label for the
                                    real endpoint (e.g. a host
                                    nickname); NEVER the raw URL.
      * ``auth_mode``           -- closed-set ``AUTH_MODE_*`` token.
      * ``chain``               -- closed-set ``CHAIN_*`` token.
      * ``max_events``          -- positive ``int`` cap on the
                                    bounded event pull.
      * ``cursor``              -- optional safe-shape cursor token
                                    for resumable iteration.
      * ``redaction_status``    -- locked ``REDACTION_STATUS_SAFE``
                                    on every well-formed config
                                    (the raw endpoint + credentials
                                    live outside this record).
    """

    provider_id: str
    provider_kind: str
    endpoint_safe_label: str
    auth_mode: str
    chain: str
    max_events: int
    cursor: Optional[str] = None
    redaction_status: str = REDACTION_STATUS_SAFE

    def __post_init__(self) -> None:
        _validate_config_fields(self)


def _validate_config_fields(
    record: "Stage28_10ChainstackYellowstoneConfig",
) -> None:
    """Validate every field of a ``Stage28_10ChainstackYellowstoneConfig``.

    Pure / deterministic. The validator runs on every direct
    construction (via ``__post_init__``) AND on every builder call
    so unsafe values cannot leak through either path. Raises
    ``Stage28_10InvalidConfigError`` on the first failing field;
    the error carries only the closed-set field name + reason
    token, never the raw unsafe value.
    """
    if not is_safe_provider_label(record.provider_id):
        raise Stage28_10InvalidConfigError(
            field_name="provider_id",
            reason="PROVIDER_ID_UNSAFE",
        )
    if not is_provider_kind_value(record.provider_kind):
        raise Stage28_10InvalidConfigError(
            field_name="provider_kind",
            reason="PROVIDER_KIND_NOT_CLOSED_SET",
        )
    if not is_safe_provider_label(record.endpoint_safe_label):
        raise Stage28_10InvalidConfigError(
            field_name="endpoint_safe_label",
            reason="ENDPOINT_LABEL_UNSAFE",
        )
    if not is_auth_mode_value(record.auth_mode):
        raise Stage28_10InvalidConfigError(
            field_name="auth_mode",
            reason="AUTH_MODE_NOT_CLOSED_SET",
        )
    if not is_chain_value(record.chain):
        raise Stage28_10InvalidConfigError(
            field_name="chain",
            reason="CHAIN_NOT_CLOSED_SET",
        )
    if (
        isinstance(record.max_events, bool)
        or not isinstance(record.max_events, int)
    ):
        raise Stage28_10InvalidConfigError(
            field_name="max_events",
            reason="VALUE_NOT_INT",
        )
    if record.max_events <= 0:
        raise Stage28_10InvalidConfigError(
            field_name="max_events",
            reason="VALUE_NOT_POSITIVE",
        )
    if record.cursor is not None and not is_safe_provider_label(
        record.cursor,
    ):
        raise Stage28_10InvalidConfigError(
            field_name="cursor",
            reason="CURSOR_UNSAFE",
        )
    if not is_redaction_status_value(record.redaction_status):
        raise Stage28_10InvalidConfigError(
            field_name="redaction_status",
            reason="REDACTION_STATUS_NOT_CLOSED_SET",
        )


def build_chainstack_yellowstone_config(
    *,
    provider_id: object,
    endpoint_safe_label: object,
    auth_mode: object,
    max_events: object,
    cursor: object = None,
    provider_kind: object = PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
    chain: object = CHAIN_SOLANA,
) -> Stage28_10ChainstackYellowstoneConfig:
    """Construct an immutable
    ``Stage28_10ChainstackYellowstoneConfig`` with full validation.

    Thin factory over the dataclass constructor. Validation runs
    in the dataclass ``__post_init__`` (see
    ``_validate_config_fields``); the factory is kept for backwards-
    compatible keyword-only ergonomics + the default ``provider_kind``
    / ``chain`` values. Raises ``Stage28_10InvalidConfigError`` for
    any field that fails the locked allowlist.
    """
    return Stage28_10ChainstackYellowstoneConfig(
        provider_id=provider_id,  # type: ignore[arg-type]
        provider_kind=provider_kind,  # type: ignore[arg-type]
        endpoint_safe_label=(
            endpoint_safe_label  # type: ignore[arg-type]
        ),
        auth_mode=auth_mode,  # type: ignore[arg-type]
        chain=chain,  # type: ignore[arg-type]
        max_events=max_events,  # type: ignore[arg-type]
        cursor=cursor,  # type: ignore[arg-type]
        redaction_status=REDACTION_STATUS_SAFE,
    )


def config_to_dict(
    record: Stage28_10ChainstackYellowstoneConfig,
) -> dict:
    """Project a config record into a deterministic-order dict
    suitable for tests and downstream inspection."""
    if not isinstance(
        record, Stage28_10ChainstackYellowstoneConfig
    ):
        raise Stage28_10InvalidConfigError(
            field_name="record",
            reason="NOT_A_CONFIG_RECORD",
        )
    return {
        "provider_id": record.provider_id,
        "provider_kind": record.provider_kind,
        "endpoint_safe_label": record.endpoint_safe_label,
        "auth_mode": record.auth_mode,
        "chain": record.chain,
        "max_events": record.max_events,
        "cursor": record.cursor,
        "redaction_status": record.redaction_status,
    }


# ---------------------------------------------------------------------------
# Stage28_10ChainstackYellowstonePayload
# ---------------------------------------------------------------------------


STAGE28_10_PAYLOAD_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "provider_event_id",
    "provider_name",
    "source_kind",
    "chain",
    "mint",
    "event_type",
    "observed_at_utc",
    "slot",
    "signature",
    "instruction_kind",
    "decoded_fields",
    "quote_mint",
    "pool_account",
    "pool_program_id",
    "base_mint",
    "bonding_curve_version_hint",
    "provider_quote_asset_hint",
    "provider_pair_type_hint",
    "provider_bonding_curve_version_hint",
    "redaction_status",
)


@dataclass(frozen=True)
class Stage28_10ChainstackYellowstonePayload:
    """Immutable sanitized Stage 28.10 Chainstack Yellowstone
    payload record.

    Implemented as a frozen ``@dataclass`` (NOT a ``NamedTuple``)
    so direct construction triggers ``__post_init__`` validation
    AND so the ``decoded_fields`` mapping can be sanitized in place
    via ``object.__setattr__``; callers cannot bypass the safe-
    shape checks by skipping the
    ``build_chainstack_yellowstone_payload`` factory.

    Carries only safe-extracted fields needed downstream. NO raw
    Yellowstone gRPC payload bytes, NO API key, NO X-Token, NO
    auth header, NO endpoint URL, NO secret. The real provider
    client is responsible for projecting an upstream Yellowstone
    event into this safe record; the Stage 28.10 boundary refuses
    payloads that carry secret-shape substrings or private-key-
    shape values.

    Fields (required first, with-default fields last to satisfy
    the frozen-dataclass field-order rule; the wire / dict order
    is still pinned by ``STAGE28_10_PAYLOAD_FIELD_NAMES`` which
    ``payload_to_dict`` iterates in the original semantic order):

      * ``provider_event_id``                    -- upstream
                                                    Yellowstone
                                                    event id.
      * ``provider_name``                        -- provider name
                                                    label (e.g.
                                                    ``"chainstack_yellowstone_prod"``).
      * ``source_kind``                          -- closed-set
                                                    ``SOURCE_KIND_*``
                                                    token; tests use
                                                    ``FAKE`` /
                                                    ``PROTOCOL``.
      * ``mint``                                 -- base token mint
                                                    string.
      * ``event_type``                           -- closed-set
                                                    ``EVENT_TYPE_*``
                                                    token (Stage
                                                    27.3 adapter
                                                    maps this onto
                                                    its closed-set
                                                    ``EVENT_KIND``).
      * ``observed_at_utc``                      -- ISO-8601 UTC
                                                    string.
      * ``slot``                                 -- non-negative
                                                    ``int`` Solana
                                                    slot.
      * ``signature``                            -- upstream
                                                    transaction
                                                    signature.
      * ``instruction_kind``                     -- closed-set
                                                    ``INSTRUCTION_KIND_*``
                                                    token.
      * ``decoded_fields``                       -- safe mapping of
                                                    safe-string ->
                                                    safe-string
                                                    decoded summary
                                                    fields; never
                                                    a raw payload
                                                    blob.
      * ``chain``                                -- closed-set
                                                    ``CHAIN_*`` token;
                                                    defaults to
                                                    ``CHAIN_SOLANA``.
      * ``quote_mint``                           -- pool-derived
                                                    quote mint;
                                                    ``None`` when
                                                    upstream did not
                                                    expose it.
      * ``pool_account``                         -- on-chain pool
                                                    account; ``None``
                                                    when missing.
      * ``pool_program_id``                      -- on-chain pool
                                                    program id;
                                                    ``None`` when
                                                    missing.
      * ``base_mint``                            -- base mint string
                                                    (when
                                                    disambiguating
                                                    base / quote
                                                    sides); ``None``
                                                    when missing.
      * ``bonding_curve_version_hint``           -- closed-set
                                                    ``BONDING_CURVE_VERSION_HINT_*``
                                                    token; ``None``
                                                    when upstream
                                                    did not promise.
      * ``provider_quote_asset_hint``            -- closed-set
                                                    ``QUOTE_ASSET_HINT_*``
                                                    token; ``None``
                                                    when upstream
                                                    did not promise.
      * ``provider_pair_type_hint``              -- closed-set
                                                    ``PAIR_TYPE_HINT_*``
                                                    token; ``None``
                                                    when upstream
                                                    did not promise.
      * ``provider_bonding_curve_version_hint``  -- closed-set
                                                    ``BONDING_CURVE_VERSION_HINT_*``
                                                    token; ``None``
                                                    when upstream
                                                    did not promise.
      * ``schema_version``                       -- locked Stage
                                                    28.10 schema
                                                    version string;
                                                    defaults to the
                                                    module-level
                                                    constant.
      * ``redaction_status``                     -- locked
                                                    ``REDACTION_STATUS_SAFE``
                                                    on every
                                                    well-formed
                                                    payload.
    """

    provider_event_id: str
    provider_name: str
    source_kind: str
    mint: str
    event_type: str
    observed_at_utc: str
    slot: int
    signature: str
    instruction_kind: str
    decoded_fields: Mapping[str, str]
    chain: str = CHAIN_SOLANA
    quote_mint: Optional[str] = None
    pool_account: Optional[str] = None
    pool_program_id: Optional[str] = None
    base_mint: Optional[str] = None
    bonding_curve_version_hint: Optional[str] = None
    provider_quote_asset_hint: Optional[str] = None
    provider_pair_type_hint: Optional[str] = None
    provider_bonding_curve_version_hint: Optional[str] = None
    schema_version: str = STAGE28_10_SCHEMA_VERSION
    redaction_status: str = REDACTION_STATUS_SAFE

    def __post_init__(self) -> None:
        _validate_payload_fields(self)


_DECODED_FIELDS_MAX_KEYS: int = 16


def _validate_decoded_fields(value: object) -> Mapping[str, str]:
    """Validate a payload's ``decoded_fields`` mapping and return
    a sanitized dict snapshot.

    Pure / deterministic. Raises
    ``Stage28_10InvalidPayloadError`` on the first non-Mapping /
    too-many / unsafe-key / non-string-value / unsafe-value entry.
    The returned snapshot carries only validated entries; the
    frozen dataclass storing the result cannot rebind the field.
    """
    if not isinstance(value, Mapping):
        raise Stage28_10InvalidPayloadError(
            field_name="decoded_fields",
            reason="NOT_A_MAPPING",
        )
    if len(value) > _DECODED_FIELDS_MAX_KEYS:
        raise Stage28_10InvalidPayloadError(
            field_name="decoded_fields",
            reason="TOO_MANY_KEYS",
        )
    safe: dict[str, str] = {}
    for raw_key, raw_val in value.items():
        if not is_safe_provider_label(raw_key):
            raise Stage28_10InvalidPayloadError(
                field_name="decoded_fields",
                reason="KEY_UNSAFE",
            )
        if not isinstance(raw_val, str):
            raise Stage28_10InvalidPayloadError(
                field_name="decoded_fields",
                reason="VALUE_NOT_STRING",
            )
        if not is_safe_payload_string(raw_val):
            raise Stage28_10InvalidPayloadError(
                field_name="decoded_fields",
                reason="VALUE_UNSAFE",
            )
        safe[raw_key] = raw_val
    return safe


def _validate_payload_optional_safe_payload_string(
    record: "Stage28_10ChainstackYellowstonePayload",
    field_name: str,
) -> None:
    value = getattr(record, field_name)
    if value is None:
        return
    if not is_safe_payload_string(value):
        raise Stage28_10InvalidPayloadError(
            field_name=field_name, reason="VALUE_UNSAFE",
        )


def _validate_payload_optional_closed_set_hint(
    record: "Stage28_10ChainstackYellowstonePayload",
    field_name: str,
    closed_set_check: object,
) -> None:
    value = getattr(record, field_name)
    if value is None:
        return
    if not isinstance(value, str):
        raise Stage28_10InvalidPayloadError(
            field_name=field_name, reason="HINT_NOT_STRING",
        )
    if not closed_set_check(value):  # type: ignore[misc]
        raise Stage28_10InvalidPayloadError(
            field_name=field_name,
            reason="HINT_NOT_CLOSED_SET",
        )


def _validate_payload_fields(
    record: "Stage28_10ChainstackYellowstonePayload",
) -> None:
    """Validate every field of a ``Stage28_10ChainstackYellowstonePayload``.

    Pure / deterministic. The validator runs on every direct
    construction (via ``__post_init__``) AND on every builder call
    so unsafe values cannot leak through either path. Raises
    ``Stage28_10InvalidPayloadError`` on the first failing field;
    the error carries only the closed-set field name + reason
    token, never the raw unsafe value.

    Side effect: the ``decoded_fields`` field is replaced in place
    by the sanitized dict snapshot via ``object.__setattr__`` so
    the stored mapping contains only validated entries.
    """
    if record.schema_version != STAGE28_10_SCHEMA_VERSION:
        raise Stage28_10InvalidPayloadError(
            field_name="schema_version",
            reason="SCHEMA_VERSION_NOT_LOCKED",
        )
    if not is_safe_payload_string(record.provider_event_id):
        raise Stage28_10InvalidPayloadError(
            field_name="provider_event_id",
            reason="VALUE_UNSAFE",
        )
    if not is_safe_provider_label(record.provider_name):
        raise Stage28_10InvalidPayloadError(
            field_name="provider_name",
            reason="VALUE_UNSAFE",
        )
    if not is_source_kind_value(record.source_kind):
        raise Stage28_10InvalidPayloadError(
            field_name="source_kind",
            reason="SOURCE_KIND_NOT_CLOSED_SET",
        )
    if not is_chain_value(record.chain):
        raise Stage28_10InvalidPayloadError(
            field_name="chain",
            reason="CHAIN_NOT_CLOSED_SET",
        )
    if not is_safe_payload_string(record.mint):
        raise Stage28_10InvalidPayloadError(
            field_name="mint", reason="VALUE_UNSAFE",
        )
    if not is_event_type_value(record.event_type):
        raise Stage28_10InvalidPayloadError(
            field_name="event_type",
            reason="EVENT_TYPE_NOT_CLOSED_SET",
        )
    if not is_safe_iso_utc(record.observed_at_utc):
        raise Stage28_10InvalidPayloadError(
            field_name="observed_at_utc",
            reason="ISO_UTC_UNSAFE",
        )
    if isinstance(record.slot, bool) or not isinstance(
        record.slot, int,
    ):
        raise Stage28_10InvalidPayloadError(
            field_name="slot", reason="SLOT_NOT_INT",
        )
    if record.slot < 0:
        raise Stage28_10InvalidPayloadError(
            field_name="slot", reason="SLOT_NEGATIVE",
        )
    if not is_safe_payload_string(record.signature):
        raise Stage28_10InvalidPayloadError(
            field_name="signature", reason="VALUE_UNSAFE",
        )
    if not is_instruction_kind_value(record.instruction_kind):
        raise Stage28_10InvalidPayloadError(
            field_name="instruction_kind",
            reason="INSTRUCTION_KIND_NOT_CLOSED_SET",
        )
    safe_decoded = _validate_decoded_fields(record.decoded_fields)
    object.__setattr__(record, "decoded_fields", safe_decoded)

    _validate_payload_optional_safe_payload_string(
        record, "quote_mint",
    )
    _validate_payload_optional_safe_payload_string(
        record, "pool_account",
    )
    _validate_payload_optional_safe_payload_string(
        record, "pool_program_id",
    )
    _validate_payload_optional_safe_payload_string(
        record, "base_mint",
    )
    _validate_payload_optional_closed_set_hint(
        record,
        "bonding_curve_version_hint",
        is_bonding_curve_version_hint_value,
    )
    _validate_payload_optional_closed_set_hint(
        record,
        "provider_quote_asset_hint",
        is_quote_asset_hint_value,
    )
    _validate_payload_optional_closed_set_hint(
        record,
        "provider_pair_type_hint",
        is_pair_type_hint_value,
    )
    _validate_payload_optional_closed_set_hint(
        record,
        "provider_bonding_curve_version_hint",
        is_bonding_curve_version_hint_value,
    )
    if not is_redaction_status_value(record.redaction_status):
        raise Stage28_10InvalidPayloadError(
            field_name="redaction_status",
            reason="REDACTION_STATUS_NOT_CLOSED_SET",
        )


def build_chainstack_yellowstone_payload(
    *,
    provider_event_id: object,
    provider_name: object,
    source_kind: object,
    mint: object,
    event_type: object,
    observed_at_utc: object,
    slot: object,
    signature: object,
    instruction_kind: object,
    decoded_fields: object,
    chain: object = CHAIN_SOLANA,
    quote_mint: object = None,
    pool_account: object = None,
    pool_program_id: object = None,
    base_mint: object = None,
    bonding_curve_version_hint: object = None,
    provider_quote_asset_hint: object = None,
    provider_pair_type_hint: object = None,
    provider_bonding_curve_version_hint: object = None,
) -> Stage28_10ChainstackYellowstonePayload:
    """Construct an immutable
    ``Stage28_10ChainstackYellowstonePayload`` with full
    validation.

    Thin factory over the dataclass constructor. Validation runs
    in the dataclass ``__post_init__`` (see
    ``_validate_payload_fields``). Raises
    ``Stage28_10InvalidPayloadError`` for any field that fails the
    locked allowlist.
    """
    return Stage28_10ChainstackYellowstonePayload(
        provider_event_id=(
            provider_event_id  # type: ignore[arg-type]
        ),
        provider_name=provider_name,  # type: ignore[arg-type]
        source_kind=source_kind,  # type: ignore[arg-type]
        mint=mint,  # type: ignore[arg-type]
        event_type=event_type,  # type: ignore[arg-type]
        observed_at_utc=(
            observed_at_utc  # type: ignore[arg-type]
        ),
        slot=slot,  # type: ignore[arg-type]
        signature=signature,  # type: ignore[arg-type]
        instruction_kind=(
            instruction_kind  # type: ignore[arg-type]
        ),
        decoded_fields=decoded_fields,  # type: ignore[arg-type]
        chain=chain,  # type: ignore[arg-type]
        quote_mint=quote_mint,  # type: ignore[arg-type]
        pool_account=pool_account,  # type: ignore[arg-type]
        pool_program_id=(
            pool_program_id  # type: ignore[arg-type]
        ),
        base_mint=base_mint,  # type: ignore[arg-type]
        bonding_curve_version_hint=(
            bonding_curve_version_hint  # type: ignore[arg-type]
        ),
        provider_quote_asset_hint=(
            provider_quote_asset_hint  # type: ignore[arg-type]
        ),
        provider_pair_type_hint=(
            provider_pair_type_hint  # type: ignore[arg-type]
        ),
        provider_bonding_curve_version_hint=(
            provider_bonding_curve_version_hint  # type: ignore[arg-type]
        ),
        schema_version=STAGE28_10_SCHEMA_VERSION,
        redaction_status=REDACTION_STATUS_SAFE,
    )


def payload_to_dict(
    record: Stage28_10ChainstackYellowstonePayload,
) -> dict:
    """Project a payload record into a deterministic-order dict
    suitable for tests and downstream inspection."""
    if not isinstance(
        record, Stage28_10ChainstackYellowstonePayload
    ):
        raise Stage28_10InvalidPayloadError(
            field_name="record",
            reason="NOT_A_PAYLOAD_RECORD",
        )
    out: dict[str, object] = {}
    for name in STAGE28_10_PAYLOAD_FIELD_NAMES:
        value = getattr(record, name)
        if name == "decoded_fields":
            out[name] = dict(value)
        else:
            out[name] = value
    return out


# ---------------------------------------------------------------------------
# Stage28_10NormalizedEvent
# ---------------------------------------------------------------------------


STAGE28_10_NORMALIZED_EVENT_REQUIRED_FIELDS: tuple[str, ...] = (
    "event_id",
    "provider_event_id",
    "provider_name",
    "mint",
    "event_type",
    "observed_at_utc",
    "raw_event_hash",
)


STAGE28_10_NORMALIZED_EVENT_HINT_FIELDS: tuple[str, ...] = (
    "quote_mint",
    "pool_account",
    "pool_program_id",
    "base_mint",
    "bonding_curve_program_id",
    "bonding_curve_version_hint",
    "provider_quote_asset_hint",
    "provider_pair_type_hint",
    "provider_bonding_curve_version_hint",
)


@dataclass(frozen=True)
class Stage28_10NormalizedEvent:
    """Immutable Stage 28.10 normalized event.

    Implemented as a frozen ``@dataclass`` (NOT a ``NamedTuple``)
    so the Stage 27.3 ``adapt_normalized_event_to_ingest_input``
    structural-type gate (which rejects ``tuple`` / ``Mapping``
    inputs to keep raw payload blobs from smuggling in via
    ``payload_summary`` keys) accepts the record. The record
    structurally satisfies the Stage 27.3 ``NormalizedEventLike``
    Protocol (the upstream required fields are present as
    attributes) AND carries Stage 28.10 pair / pool / bonding-curve
    hint attributes the Stage 28.10 hint-aware candidate assembler
    forwards to ``adapt_normalized_event_to_ingest_input`` so the
    Stage 27 chain does not lose the hint evidence in the
    Yellowstone -> Stage 27 projection.

    Fields:

      * ``event_id``                              -- upstream
                                                     normalized
                                                     event id.
      * ``provider_event_id``                     -- upstream
                                                     provider event
                                                     id.
      * ``provider_name``                         -- upstream
                                                     provider
                                                     identifier.
      * ``mint``                                  -- token mint
                                                     string (the
                                                     base token
                                                     being observed).
      * ``event_type``                            -- upstream
                                                     event-type
                                                     label (Stage
                                                     27.3 adapter
                                                     maps this).
      * ``observed_at_utc``                       -- ISO-8601 UTC
                                                     string.
      * ``raw_event_hash``                        -- upstream
                                                     raw-event
                                                     content hash
                                                     (used as a
                                                     stable
                                                     ``raw_capture_ref``
                                                     handle, NOT
                                                     a payload).
      * ``quote_mint``                            -- pool-derived
                                                     quote mint;
                                                     ``None`` when
                                                     upstream did
                                                     not expose it.
      * ``pool_account``                          -- on-chain pool
                                                     account.
      * ``pool_program_id``                       -- on-chain pool
                                                     program id.
      * ``base_mint``                             -- base mint
                                                     string when
                                                     disambiguating
                                                     base / quote.
      * ``bonding_curve_program_id``              -- bonding-curve
                                                     program id.
      * ``bonding_curve_version_hint``            -- closed-set
                                                     ``BONDING_CURVE_VERSION_HINT_*``
                                                     token.
      * ``provider_quote_asset_hint``             -- closed-set
                                                     ``QUOTE_ASSET_HINT_*``
                                                     token.
      * ``provider_pair_type_hint``               -- closed-set
                                                     ``PAIR_TYPE_HINT_*``
                                                     token.
      * ``provider_bonding_curve_version_hint``   -- closed-set
                                                     ``BONDING_CURVE_VERSION_HINT_*``
                                                     token.
    """

    event_id: str
    provider_event_id: str
    provider_name: str
    mint: str
    event_type: str
    observed_at_utc: str
    raw_event_hash: str
    quote_mint: Optional[str] = None
    pool_account: Optional[str] = None
    pool_program_id: Optional[str] = None
    base_mint: Optional[str] = None
    bonding_curve_program_id: Optional[str] = None
    bonding_curve_version_hint: Optional[str] = None
    provider_quote_asset_hint: Optional[str] = None
    provider_pair_type_hint: Optional[str] = None
    provider_bonding_curve_version_hint: Optional[str] = None

    def __post_init__(self) -> None:
        _validate_normalized_event_fields(self)


_NORMALIZED_EVENT_OPTIONAL_SAFE_STRING_FIELDS: tuple[str, ...] = (
    "quote_mint",
    "pool_account",
    "pool_program_id",
    "base_mint",
    "bonding_curve_program_id",
)


_NORMALIZED_EVENT_OPTIONAL_CLOSED_SET_HINT_FIELDS: tuple[
    tuple[str, object], ...
] = (
    ("bonding_curve_version_hint",
     is_bonding_curve_version_hint_value),
    ("provider_quote_asset_hint",
     is_quote_asset_hint_value),
    ("provider_pair_type_hint",
     is_pair_type_hint_value),
    ("provider_bonding_curve_version_hint",
     is_bonding_curve_version_hint_value),
)


def _validate_normalized_event_fields(
    record: "Stage28_10NormalizedEvent",
) -> None:
    """Validate every field of a ``Stage28_10NormalizedEvent``.

    Pure / deterministic. The validator runs on every direct
    construction (via ``__post_init__``) AND on every builder call
    so unsafe values cannot leak through either path. Raises
    ``Stage28_10InvalidNormalizedEventError`` on the first failing
    field; the error carries only the closed-set field name +
    reason token, never the raw unsafe value.
    """
    if not is_safe_payload_string(record.event_id):
        raise Stage28_10InvalidNormalizedEventError(
            field_name="event_id", reason="VALUE_UNSAFE",
        )
    if not is_safe_payload_string(record.provider_event_id):
        raise Stage28_10InvalidNormalizedEventError(
            field_name="provider_event_id",
            reason="VALUE_UNSAFE",
        )
    if not is_safe_provider_label(record.provider_name):
        raise Stage28_10InvalidNormalizedEventError(
            field_name="provider_name",
            reason="VALUE_UNSAFE",
        )
    if not is_safe_payload_string(record.mint):
        raise Stage28_10InvalidNormalizedEventError(
            field_name="mint", reason="VALUE_UNSAFE",
        )
    if (
        not isinstance(record.event_type, str)
        or record.event_type == ""
    ):
        raise Stage28_10InvalidNormalizedEventError(
            field_name="event_type",
            reason="EVENT_TYPE_EMPTY",
        )
    # The upstream event-type string flows through to Stage 27.3's
    # ``classify_event_kind`` mapping (``swap`` / ``fake_swap`` /
    # ``migration`` / etc.). Stage 28.10 cannot tighten the upstream
    # vocabulary to the Stage 28.10 payload-level closed set
    # (``EVENT_TYPE_VALUES``) because Stage 27.3 admits a broader
    # alphabet, but Stage 28.10 MUST still refuse any value that
    # carries URL / webhook / API-token / private-key-like /
    # bracketed-key-array shape so unsafe strings cannot leak through
    # repr / ``dataclasses.asdict`` / public dict helpers / exception
    # messages. ``is_safe_payload_string`` enforces exactly that
    # discipline (allowlisted chars, no forbidden substrings, no
    # private-key-like shape) while still accepting the legitimate
    # short snake-case Stage 21 / Stage 27 event-type strings.
    if not is_safe_payload_string(record.event_type):
        raise Stage28_10InvalidNormalizedEventError(
            field_name="event_type",
            reason="VALUE_UNSAFE",
        )
    if not is_safe_iso_utc(record.observed_at_utc):
        raise Stage28_10InvalidNormalizedEventError(
            field_name="observed_at_utc",
            reason="ISO_UTC_UNSAFE",
        )
    if not is_safe_payload_string(record.raw_event_hash):
        raise Stage28_10InvalidNormalizedEventError(
            field_name="raw_event_hash",
            reason="VALUE_UNSAFE",
        )
    for field_name in _NORMALIZED_EVENT_OPTIONAL_SAFE_STRING_FIELDS:
        value = getattr(record, field_name)
        if value is None:
            continue
        if not is_safe_payload_string(value):
            raise Stage28_10InvalidNormalizedEventError(
                field_name=field_name, reason="VALUE_UNSAFE",
            )
    for field_name, check in (
        _NORMALIZED_EVENT_OPTIONAL_CLOSED_SET_HINT_FIELDS
    ):
        value = getattr(record, field_name)
        if value is None:
            continue
        if not isinstance(value, str):
            raise Stage28_10InvalidNormalizedEventError(
                field_name=field_name,
                reason="HINT_NOT_STRING",
            )
        if not check(value):  # type: ignore[misc]
            raise Stage28_10InvalidNormalizedEventError(
                field_name=field_name,
                reason="HINT_NOT_CLOSED_SET",
            )


def build_normalized_event(
    *,
    event_id: object,
    provider_event_id: object,
    provider_name: object,
    mint: object,
    event_type: object,
    observed_at_utc: object,
    raw_event_hash: object,
    quote_mint: object = None,
    pool_account: object = None,
    pool_program_id: object = None,
    base_mint: object = None,
    bonding_curve_program_id: object = None,
    bonding_curve_version_hint: object = None,
    provider_quote_asset_hint: object = None,
    provider_pair_type_hint: object = None,
    provider_bonding_curve_version_hint: object = None,
) -> Stage28_10NormalizedEvent:
    """Construct an immutable ``Stage28_10NormalizedEvent`` with
    full validation.

    Thin factory over the dataclass constructor. Validation runs
    in the dataclass ``__post_init__`` (see
    ``_validate_normalized_event_fields``). Raises
    ``Stage28_10InvalidNormalizedEventError`` for any field that
    fails the locked allowlist.
    """
    return Stage28_10NormalizedEvent(
        event_id=event_id,  # type: ignore[arg-type]
        provider_event_id=(
            provider_event_id  # type: ignore[arg-type]
        ),
        provider_name=provider_name,  # type: ignore[arg-type]
        mint=mint,  # type: ignore[arg-type]
        event_type=event_type,  # type: ignore[arg-type]
        observed_at_utc=(
            observed_at_utc  # type: ignore[arg-type]
        ),
        raw_event_hash=raw_event_hash,  # type: ignore[arg-type]
        quote_mint=quote_mint,  # type: ignore[arg-type]
        pool_account=pool_account,  # type: ignore[arg-type]
        pool_program_id=(
            pool_program_id  # type: ignore[arg-type]
        ),
        base_mint=base_mint,  # type: ignore[arg-type]
        bonding_curve_program_id=(
            bonding_curve_program_id  # type: ignore[arg-type]
        ),
        bonding_curve_version_hint=(
            bonding_curve_version_hint  # type: ignore[arg-type]
        ),
        provider_quote_asset_hint=(
            provider_quote_asset_hint  # type: ignore[arg-type]
        ),
        provider_pair_type_hint=(
            provider_pair_type_hint  # type: ignore[arg-type]
        ),
        provider_bonding_curve_version_hint=(
            provider_bonding_curve_version_hint  # type: ignore[arg-type]
        ),
    )


# ---------------------------------------------------------------------------
# Re-export the Stage 28.5 safe-identifier / safe-counter helpers so
# downstream Stage 28.10 modules + tests can import them without
# reaching into Stage 28.5 directly.
# ---------------------------------------------------------------------------


is_safe_identifier_label = is_safe_identifier
is_safe_counter = is_safe_counter_value


__all__ = (
    # Version axes.
    "STAGE28_10_MINOR_VERSION",
    "STAGE28_10_SCHEMA_VERSION",
    "STAGE28_10_REDACTION_TOKEN",
    # Provider-kind vocabulary.
    "PROVIDER_KIND_CHAINSTACK_YELLOWSTONE",
    "PROVIDER_KIND_VALUES",
    "is_provider_kind_value",
    # Auth-mode vocabulary.
    "AUTH_MODE_XTOKEN",
    "AUTH_MODE_USERNAME_PASSWORD",
    "AUTH_MODE_UNKNOWN",
    "AUTH_MODE_VALUES",
    "is_auth_mode_value",
    # Chain vocabulary.
    "CHAIN_SOLANA",
    "CHAIN_VALUES",
    "is_chain_value",
    # Source-kind vocabulary.
    "SOURCE_KIND_FAKE",
    "SOURCE_KIND_PROTOCOL",
    "SOURCE_KIND_VALUES",
    "is_source_kind_value",
    # Event-type vocabulary.
    "EVENT_TYPE_SWAP",
    "EVENT_TYPE_MIGRATION",
    "EVENT_TYPE_MINT",
    "EVENT_TYPE_VALUES",
    "is_event_type_value",
    # Instruction-kind vocabulary.
    "INSTRUCTION_KIND_PUMP_SWAP",
    "INSTRUCTION_KIND_PUMP_MIGRATION",
    "INSTRUCTION_KIND_PUMP_CREATE",
    "INSTRUCTION_KIND_UNKNOWN",
    "INSTRUCTION_KIND_VALUES",
    "is_instruction_kind_value",
    # Quote-asset / pair-type / bonding-curve hint vocabularies.
    "QUOTE_ASSET_HINT_SOL",
    "QUOTE_ASSET_HINT_USDC",
    "QUOTE_ASSET_HINT_UNKNOWN",
    "QUOTE_ASSET_HINT_VALUES",
    "is_quote_asset_hint_value",
    "PAIR_TYPE_HINT_PUMP_SOL",
    "PAIR_TYPE_HINT_PUMP_USDC",
    "PAIR_TYPE_HINT_UNKNOWN",
    "PAIR_TYPE_HINT_VALUES",
    "is_pair_type_hint_value",
    "BONDING_CURVE_VERSION_HINT_SOL_LEGACY",
    "BONDING_CURVE_VERSION_HINT_USDC_FIXED",
    "BONDING_CURVE_VERSION_HINT_UNKNOWN",
    "BONDING_CURVE_VERSION_HINT_VALUES",
    "is_bonding_curve_version_hint_value",
    # Redaction-status vocabulary.
    "REDACTION_STATUS_SAFE",
    "REDACTION_STATUS_REDACTED",
    "REDACTION_STATUS_VALUES",
    "is_redaction_status_value",
    # Safe-shape validators.
    "is_safe_provider_label",
    "is_safe_payload_string",
    "is_safe_iso_utc",
    "is_safe_identifier_label",
    "is_safe_counter",
    # Records + builders.
    "Stage28_10ChainstackYellowstoneConfig",
    "build_chainstack_yellowstone_config",
    "config_to_dict",
    "Stage28_10ChainstackYellowstonePayload",
    "build_chainstack_yellowstone_payload",
    "payload_to_dict",
    "Stage28_10NormalizedEvent",
    "build_normalized_event",
    # Field-name inventories.
    "STAGE28_10_PAYLOAD_FIELD_NAMES",
    "STAGE28_10_NORMALIZED_EVENT_REQUIRED_FIELDS",
    "STAGE28_10_NORMALIZED_EVENT_HINT_FIELDS",
    # Exceptions.
    "Stage28_10ChainstackYellowstoneError",
    "Stage28_10InvalidConfigError",
    "Stage28_10InvalidPayloadError",
    "Stage28_10InvalidNormalizedEventError",
)
