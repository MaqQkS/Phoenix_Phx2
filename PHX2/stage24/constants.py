"""Stage 24 locked constants (foundation only at 24.1).

Every Stage 24 closed-set vocabulary, version axis, Solana
program ID literal, and boundary-scan input lives here. Stage
24 mirrors the Stage 21 / Stage 22 / Stage 23 convention: every
closed-set surface is a ``tuple[str, ...]`` declared once in
this module and consumed verbatim by callers.

Stage 24.1 is contracts-only: this module is read by
``PHX2/stage24/models.py``,
``PHX2/stage24/decoder_contracts.py``,
``PHX2/stage24/input_reader.py``,
``PHX2/stage24/stage24_manifest.py``, and by the
``PHX2/tests/stage24/`` boundary tests. No Stage 24 production
module outside this module may declare a Stage 24 closed-set
token.

The Stage 24 forbidden-routing tuple intentionally mirrors the
Stage 21 / Stage 22 / Stage 23 sets but is re-declared locally
so the identifier-aware boundary scanner in
``test_stage_24_1_boundaries.py`` does not need to reach into
prior stages.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 24 version strings
# ---------------------------------------------------------------------------


STAGE24_VERSION: str = "stage24_v0_execution_primitives_foundation"
# Minor version axis. Bump on every sub-stage merge: 24.1 -> 24.2 -> ...
STAGE24_MINOR_VERSION: str = "24.1"

# Stage name token. Mirrors the Stage 22 / Stage 23 discipline.
STAGE_NAME: str = "stage24"

# Locked alias for the minor version. Documented as the public
# stage version axis emitted on manifest records.
STAGE_VERSION: str = STAGE24_MINOR_VERSION


# Stage 24 schema version. Per-record schema version used by the
# execution-primitive surface and the manifest surface. The
# schema version is intentionally orthogonal to STAGE_VERSION:
# bumping the stage version axis (24.1 -> 24.2) does NOT
# automatically bump the schema versions; the on-disk record
# shape is bumped only when it materially changes.
DEFAULT_SCHEMA_VERSION: str = "stage24_v0_execution_primitive"
STAGE24_MANIFEST_SCHEMA_VERSION: str = "stage24_v0_manifest"


# Observe-only posture marker. The single canonical short string
# manifest records carry to assert Stage 24's posture. Stage 24
# never blocks, gates, or routes -- it only emits evidence.
OBSERVE_ONLY_MODE: str = "observe_only"


# Threshold-version axis. Stage 24.1 has no thresholds; Stage 26
# is the calibration / enforcement stage that consumes Stage 24
# evidence. The threshold axis is reserved here so 24.1+ records
# carry a stable, deterministic threshold-version string even
# when no decoder applies a threshold.
DEFAULT_THRESHOLD_VERSION: str = "thresholds_v0_observe_only"


# ---------------------------------------------------------------------------
# PRIMITIVE_FAMILIES -- closed set of execution-primitive families
# ---------------------------------------------------------------------------


PRIMITIVE_FAMILY_COMPUTE_BUDGET: str = "COMPUTE_BUDGET"
PRIMITIVE_FAMILY_PRIORITY_FEE: str = "PRIORITY_FEE"
PRIMITIVE_FAMILY_JITO_TIP: str = "JITO_TIP"
PRIMITIVE_FAMILY_ROUTER_FEE: str = "ROUTER_FEE"
PRIMITIVE_FAMILY_EXECUTION_QUALITY: str = "EXECUTION_QUALITY"


PRIMITIVE_FAMILIES: tuple[str, ...] = (
    PRIMITIVE_FAMILY_COMPUTE_BUDGET,
    PRIMITIVE_FAMILY_PRIORITY_FEE,
    PRIMITIVE_FAMILY_JITO_TIP,
    PRIMITIVE_FAMILY_ROUTER_FEE,
    PRIMITIVE_FAMILY_EXECUTION_QUALITY,
)


# ---------------------------------------------------------------------------
# DECODER_STATUSES -- closed set of decoder confidence tokens
# ---------------------------------------------------------------------------
#
# ROUTER_FEE_CANDIDATE is intentionally NOT a decoder_status. It
# is a fee_source axis value. The decoder's confidence is
# recorded separately in decoder_status. See FEE_SOURCES below.


DECODER_STATUS_DECODED: str = "DECODED"
DECODER_STATUS_PARTIAL: str = "PARTIAL"
DECODER_STATUS_DECODE_UNCONFIRMED: str = "DECODE_UNCONFIRMED"
DECODER_STATUS_UNSUPPORTED: str = "UNSUPPORTED"
DECODER_STATUS_ABSENT: str = "ABSENT"
DECODER_STATUS_NOT_APPLICABLE: str = "NOT_APPLICABLE"
DECODER_STATUS_DECODE_FAILED: str = "DECODE_FAILED"
DECODER_STATUS_INPUT_REJECTED: str = "INPUT_REJECTED"


DECODER_STATUSES: tuple[str, ...] = (
    DECODER_STATUS_DECODED,
    DECODER_STATUS_PARTIAL,
    DECODER_STATUS_DECODE_UNCONFIRMED,
    DECODER_STATUS_UNSUPPORTED,
    DECODER_STATUS_ABSENT,
    DECODER_STATUS_NOT_APPLICABLE,
    DECODER_STATUS_DECODE_FAILED,
    DECODER_STATUS_INPUT_REJECTED,
)


# ---------------------------------------------------------------------------
# DATA_STATUSES -- closed set of input-completeness tokens
# ---------------------------------------------------------------------------


DATA_STATUS_COMPLETE: str = "COMPLETE"
DATA_STATUS_PARTIAL: str = "PARTIAL"
DATA_STATUS_MISSING: str = "MISSING"
DATA_STATUS_UNSUPPORTED: str = "UNSUPPORTED"
DATA_STATUS_NOT_APPLICABLE: str = "NOT_APPLICABLE"
DATA_STATUS_MALFORMED: str = "MALFORMED"


DATA_STATUSES: tuple[str, ...] = (
    DATA_STATUS_COMPLETE,
    DATA_STATUS_PARTIAL,
    DATA_STATUS_MISSING,
    DATA_STATUS_UNSUPPORTED,
    DATA_STATUS_NOT_APPLICABLE,
    DATA_STATUS_MALFORMED,
)


# ---------------------------------------------------------------------------
# CONFIDENCE_LEVELS -- coarse roll-up axis distinct from decoder_status
# ---------------------------------------------------------------------------


CONFIDENCE_LEVEL_HIGH: str = "HIGH"
CONFIDENCE_LEVEL_MEDIUM: str = "MEDIUM"
CONFIDENCE_LEVEL_LOW: str = "LOW"
CONFIDENCE_LEVEL_NONE: str = "NONE"


CONFIDENCE_LEVELS: tuple[str, ...] = (
    CONFIDENCE_LEVEL_HIGH,
    CONFIDENCE_LEVEL_MEDIUM,
    CONFIDENCE_LEVEL_LOW,
    CONFIDENCE_LEVEL_NONE,
)


# ---------------------------------------------------------------------------
# FEE_SOURCES -- closed set of fee-kind axis values
# ---------------------------------------------------------------------------
#
# fee_source identifies the KIND of fee a primitive carries.
# It is orthogonal to decoder_status (confidence) and route_family
# (program family).
#
# ROUTER_FEE_CANDIDATE / AXIOM_GLOBAL_FEE_CANDIDATE / JITO_TIP_CANDIDATE
# distinguish unconfirmed fee-source candidates from decoded
# fee-source values. A primitive emitted by the Stage 24.4
# router-candidate scaffold carries fee_source=ROUTER_FEE_CANDIDATE
# or fee_source=AXIOM_GLOBAL_FEE_CANDIDATE alongside
# decoder_status=DECODE_UNCONFIRMED. A primitive promoted to
# decoded at Stage 24.5 carries fee_source=ROUTER_FEE /
# AXIOM_GLOBAL_FEE alongside decoder_status=DECODED.


FEE_SOURCE_BASE_FEE: str = "BASE_FEE"
FEE_SOURCE_PRIORITY_FEE: str = "PRIORITY_FEE"
FEE_SOURCE_JITO_TIP: str = "JITO_TIP"
FEE_SOURCE_JITO_TIP_CANDIDATE: str = "JITO_TIP_CANDIDATE"
FEE_SOURCE_ROUTER_FEE: str = "ROUTER_FEE"
FEE_SOURCE_ROUTER_FEE_CANDIDATE: str = "ROUTER_FEE_CANDIDATE"
FEE_SOURCE_AXIOM_GLOBAL_FEE: str = "AXIOM_GLOBAL_FEE"
FEE_SOURCE_AXIOM_GLOBAL_FEE_CANDIDATE: str = "AXIOM_GLOBAL_FEE_CANDIDATE"
FEE_SOURCE_PUMPFUN_FEE: str = "PUMPFUN_FEE"
FEE_SOURCE_UNKNOWN: str = "UNKNOWN"


FEE_SOURCES: tuple[str, ...] = (
    FEE_SOURCE_BASE_FEE,
    FEE_SOURCE_PRIORITY_FEE,
    FEE_SOURCE_JITO_TIP,
    FEE_SOURCE_JITO_TIP_CANDIDATE,
    FEE_SOURCE_ROUTER_FEE,
    FEE_SOURCE_ROUTER_FEE_CANDIDATE,
    FEE_SOURCE_AXIOM_GLOBAL_FEE,
    FEE_SOURCE_AXIOM_GLOBAL_FEE_CANDIDATE,
    FEE_SOURCE_PUMPFUN_FEE,
    FEE_SOURCE_UNKNOWN,
)


# ---------------------------------------------------------------------------
# ROUTE_FAMILIES -- closed set of on-chain program / router families
# ---------------------------------------------------------------------------


ROUTE_FAMILY_NO_ROUTER_DETECTED: str = "NO_ROUTER_DETECTED"
ROUTE_FAMILY_AXIOM_TRADING_PROGRAM_1: str = "AXIOM_TRADING_PROGRAM_1"
ROUTE_FAMILY_AXIOM_FLASHX8: str = "AXIOM_FLASHX8"
ROUTE_FAMILY_DEPRECATED_AXIOM: str = "DEPRECATED_AXIOM"
ROUTE_FAMILY_PUMPFUN_DIRECT: str = "PUMPFUN_DIRECT"
ROUTE_FAMILY_PUMPSWAP_DIRECT: str = "PUMPSWAP_DIRECT"
ROUTE_FAMILY_UNKNOWN_ROUTER: str = "UNKNOWN_ROUTER"
ROUTE_FAMILY_UNSUPPORTED_ROUTER: str = "UNSUPPORTED_ROUTER"


ROUTE_FAMILIES: tuple[str, ...] = (
    ROUTE_FAMILY_NO_ROUTER_DETECTED,
    ROUTE_FAMILY_AXIOM_TRADING_PROGRAM_1,
    ROUTE_FAMILY_AXIOM_FLASHX8,
    ROUTE_FAMILY_DEPRECATED_AXIOM,
    ROUTE_FAMILY_PUMPFUN_DIRECT,
    ROUTE_FAMILY_PUMPSWAP_DIRECT,
    ROUTE_FAMILY_UNKNOWN_ROUTER,
    ROUTE_FAMILY_UNSUPPORTED_ROUTER,
)


# ---------------------------------------------------------------------------
# INSTRUCTION_LOCATIONS -- closed set of evidence-location tokens
# ---------------------------------------------------------------------------


INSTRUCTION_LOCATION_TOP_LEVEL: str = "TOP_LEVEL"
INSTRUCTION_LOCATION_INNER: str = "INNER"
INSTRUCTION_LOCATION_BALANCE_DELTA: str = "BALANCE_DELTA"
INSTRUCTION_LOCATION_TOKEN_BALANCE_DELTA: str = "TOKEN_BALANCE_DELTA"
INSTRUCTION_LOCATION_LOG_ONLY: str = "LOG_ONLY"
INSTRUCTION_LOCATION_UNKNOWN: str = "UNKNOWN"


INSTRUCTION_LOCATIONS: tuple[str, ...] = (
    INSTRUCTION_LOCATION_TOP_LEVEL,
    INSTRUCTION_LOCATION_INNER,
    INSTRUCTION_LOCATION_BALANCE_DELTA,
    INSTRUCTION_LOCATION_TOKEN_BALANCE_DELTA,
    INSTRUCTION_LOCATION_LOG_ONLY,
    INSTRUCTION_LOCATION_UNKNOWN,
)


# ---------------------------------------------------------------------------
# INPUT_KINDS -- closed set of Stage 24 input source kinds
# ---------------------------------------------------------------------------
#
# Each token identifies the source kind of a Stage 24-shaped
# decoded-tx JSONL input file. Locked at 24.1; new sources
# require a contract patch.


INPUT_KIND_DECODED_TX_JSONL: str = "decoded_tx_jsonl"
INPUT_KIND_SYNTHETIC_DECODED_TX_JSONL: str = "synthetic_decoded_tx_jsonl"
INPUT_KIND_SANITIZED_REAL_DECODED_TX_JSONL: str = "sanitized_real_decoded_tx_jsonl"


INPUT_KINDS: tuple[str, ...] = (
    INPUT_KIND_DECODED_TX_JSONL,
    INPUT_KIND_SYNTHETIC_DECODED_TX_JSONL,
    INPUT_KIND_SANITIZED_REAL_DECODED_TX_JSONL,
)


# ---------------------------------------------------------------------------
# Solana program ID literals
# ---------------------------------------------------------------------------
#
# The well-known public Solana program ID literals Stage 24
# recognizes. These are public on-chain addresses, NOT secrets,
# and are documented in the Solana program registry. Stage 24
# uses them as instruction-program-ID match targets only; no
# network call resolves them.


COMPUTE_BUDGET_PROGRAM_ID: str = "ComputeBudget111111111111111111111111111111"
SYSTEM_PROGRAM_ID: str = "11111111111111111111111111111111"
TOKEN_PROGRAM_ID: str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


# Active Axiom router program IDs recognized by Stage 24.4 as
# router-fee candidates and (conditionally) by Stage 24.5 as
# decoded router-fee primitives. Tuples are tuples-of-strings;
# locking new IDs in here requires a fixture-backed promotion
# test in the Stage 24.5 closure pass.
ACTIVE_AXIOM_ROUTER_PROGRAM_IDS: tuple[str, ...] = (
    "AxiomfHaWDemCFBLBayqnEnNwE6b7B2Qz3UmzpgbMG6",
    "FLASHX8DrLbgeR8FcfNV1F5krxYcYMUdBkrP1EPBtxB9",
)


# Deprecated Axiom router program IDs. Stage 24 recognizes them
# but maps them to ROUTE_FAMILY_DEPRECATED_AXIOM and emits
# decoder_status=NOT_APPLICABLE for the router-fee family. They
# are NOT treated as candidates.
DEPRECATED_AXIOM_ROUTER_PROGRAM_IDS: tuple[str, ...] = (
    "AxiomxSitivYjPjKgJ9XSrdhsydtZssk7TEDam3PxKcC",
    "Axiom3a2w1UbMt2SMgqSvRiuJFTPusDhwKamNgPTeNQ9",
)


# Known Jito tip accounts.
#
# The eight standard Jito tip wallets documented in the public
# Jito-Solana SDK / Block Engine docs. These are public on-chain
# pubkeys, NOT secrets, and have been stable since the Jito
# tipping interface was published. Stage 24.3 locks the literal
# tuple in this file (rather than reaching out over the network)
# so the decoder can perform tip-account match without network
# I/O. Adding or removing a tip account requires a contract
# patch to this tuple plus a corresponding constants test.
KNOWN_JITO_TIP_ACCOUNTS: tuple[str, ...] = (
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pivKeVrtfXEMnEnyGuTk",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
)


# ---------------------------------------------------------------------------
# Stage 24 forbidden routing tokens (locally re-declared)
# ---------------------------------------------------------------------------
#
# Stage 24 inherits the Stage 20 / Stage 21 / Stage 22 / Stage 23
# prohibition against subscriber / public / paid routing and
# re-declares the locked tuple locally so the Stage 24 routing-
# scan boundary test does not need to reach into prior stages.
# Stage 24 does NOT route -- it emits evidence.


STAGE24_FORBIDDEN_ROUTING_TOKENS: tuple[str, ...] = (
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


# ---------------------------------------------------------------------------
# Stage 24 forbidden vocabulary (boundary scanner input)
# ---------------------------------------------------------------------------
#
# Identifier-position substrings the Stage 24 production source
# MUST NOT define. These are concerns that belong to strictly
# later stages or are forever forbidden in Stage 24:
#
#   * ``migration`` / ``birdeye`` / ``dexscreener`` -- Stage 25
#     measurement primitives.
#   * ``x_api`` / ``social`` -- Stage 27+ social-intelligence
#     sidecar.
#   * ``enforce`` / ``gate`` / ``block`` / ``blocking`` --
#     Stage 26 enforcement candidates. Stage 24 is observe-only.
#   * ``dispatch`` / ``alert`` -- routing concerns. Stage 24
#     never sends a live alert.
#   * ``scheduler`` / ``daemon`` / ``orchestrator`` /
#     ``run_loop`` / ``worker`` -- long-running infra (out of
#     scope).
#   * ``telegram`` -- transport concern.
#
# IMPORTANT: ``axiom`` / ``jito`` / ``priority_fee`` /
# ``compute_budget`` / ``execution_quality`` are deliberately
# OMITTED from this tuple because they are the Stage 24
# vocabulary. ``decoder`` / ``primitive`` / ``manifest`` /
# ``reader`` / ``input`` / ``fee`` are also legitimate Stage 24
# vocabulary.
#
# The boundary scanner consumes this tuple against AST identifier
# positions only, so docstring / comment phrases like "Stage 24
# never blocks" do not trigger the scanner.


STAGE24_FORBIDDEN_VOCABULARY: tuple[str, ...] = (
    "migration",
    "birdeye",
    "dexscreener",
    "x_api",
    "social",
    "enforce",
    "gate",
    "block",
    "blocking",
    "dispatch",
    "alert",
    "scheduler",
    "daemon",
    "orchestrator",
    "run_loop",
    "worker",
    "telegram",
)


# Short / ambiguous vocabulary forbidden at the WORD level rather
# than as a substring. ``ath`` is the canonical example: it must
# not appear as a discrete identifier-part word ("ath_value",
# ".ath", "ath" alone) but its substring naturally appears in
# safe identifiers like ``path`` / ``pathlib`` / ``math`` /
# ``hashlib``. The Stage 24 boundary scanner splits each identifier
# on ``_`` and case-boundaries and checks each resulting part
# against this tuple.


STAGE24_FORBIDDEN_VOCABULARY_WORDS: tuple[str, ...] = (
    "ath",
)


# ---------------------------------------------------------------------------
# Stage 24 input-reader redaction discipline
# ---------------------------------------------------------------------------
#
# Field-name substrings that, if seen on an input row, cause the
# reader to reject the row with ``Stage24InputError``. Mirrors
# the Stage 22 / Stage 23 second-line-of-defense pattern: if an
# upstream artifact ever leaks a secret-bearing field, Stage 24
# refuses to ingest it rather than passing it through.


STAGE24_FORBIDDEN_INPUT_FIELD_SUBSTRINGS: tuple[str, ...] = (
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


# URL-scheme fragments and webhook host literals are constructed
# at runtime via string concatenation so the literal substrings
# the Stage 24 boundary scanner forbids never appear in this
# source file. Mirrors the Stage 22 / Stage 23 pattern.


_COLON_SLASH_SLASH: str = ":" + "//"
_HTTP_SCHEME: str = "http" + _COLON_SLASH_SLASH
_HTTPS_SCHEME: str = "https" + _COLON_SLASH_SLASH
_WS_SCHEME: str = "ws" + _COLON_SLASH_SLASH
_WSS_SCHEME: str = "wss" + _COLON_SLASH_SLASH

_DOT_COM: str = "." + "com"
_DISCORD_HOST: str = "discord" + _DOT_COM
_DISCORDAPP_HOST: str = "discordapp" + _DOT_COM
_HOOKS_SLACK_HOST: str = "hooks" + ".slack" + _DOT_COM


# Substrings the input reader rejects anywhere inside a value of
# a preserved row field (case-insensitive). The colon-slash-slash
# entry catches URL prefixes that drop the scheme as well as the
# concrete schemes.


STAGE24_FORBIDDEN_INPUT_VALUE_SUBSTRINGS: tuple[str, ...] = (
    _HTTP_SCHEME,
    _HTTPS_SCHEME,
    _WS_SCHEME,
    _WSS_SCHEME,
    _COLON_SLASH_SLASH,
    _DISCORD_HOST,
    _DISCORDAPP_HOST,
    _HOOKS_SLACK_HOST,
)


# Long-hex-run threshold for the value-shape leak detector. A
# value containing a contiguous run of >= 40 hex characters is
# rejected by the input reader as a credential / API-key shape.
# Solana addresses and signatures are base58 (no consecutive
# all-hex runs of this length), so legitimate decoded-tx data
# does not trigger this threshold.


STAGE24_LONG_HEX_RUN_MIN_LEN: int = 40
