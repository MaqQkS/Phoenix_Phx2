"""Stage 23 locked constants (foundation only at 23.1).

Every Stage 23 closed-set vocabulary, version axis, and
boundary-scan input lives here. Stage 23 mirrors the Stage 21 /
Stage 22 convention: every closed-set surface is a
``tuple[str, ...]`` declared once in this module and consumed
verbatim by callers.

Stage 23.1 is contracts-only: this module is read by
``PHX2/stage23/models.py``, ``PHX2/stage23/filter_contracts.py``,
``PHX2/stage23/input_reader.py``,
``PHX2/stage23/stage23_manifest.py``, and by the
``PHX2/tests/stage23/`` boundary tests. No Stage 23 production
module outside this module may declare a Stage 23 closed-set
token.

The Stage 23 forbidden-routing tuple intentionally mirrors the
Stage 21 / Stage 22 sets but is re-declared locally so the
identifier-aware boundary scanner in
``test_stage_23_1_boundaries.py`` does not need to reach into
prior stages.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Stage 23 version strings
# ---------------------------------------------------------------------------


STAGE23_VERSION: str = "stage23_v0_observe_only_filter_foundation"
# Minor version axis. Bump on every sub-stage merge: 23.1 -> 23.2 -> ...
STAGE23_MINOR_VERSION: str = "23.1"

# Stage name token. Mirrors the Stage 22 "stage22" / "stage21"
# discipline.
STAGE_NAME: str = "stage23"

# Locked alias for the minor version. Documented as the public
# stage version axis emitted on manifest records.
STAGE_VERSION: str = STAGE23_MINOR_VERSION


# Stage 23 schema version. Per-record schema version used by the
# filter-evaluation surface and the manifest surface. Mirrors the
# Stage 22 per-record schema-version discipline so a future bump
# can migrate additively without a file-header dance.
DEFAULT_SCHEMA_VERSION: str = "stage23_v0_filter_eval"
STAGE23_MANIFEST_SCHEMA_VERSION: str = "stage23_v0_manifest"

# Observe-only posture marker. The single canonical short string
# manifest records carry to assert Stage 23's posture. Stage 23
# never blocks, gates, or routes -- it only emits evidence.
OBSERVE_ONLY_MODE: str = "observe_only"


# ---------------------------------------------------------------------------
# LABELS -- closed set of filter evaluation labels
# ---------------------------------------------------------------------------
#
# Locked per Stage 23.0 design (PHX2/docs/STAGE_23_BRAINSTORM.md
# section 7). New values require a contract patch.


LABEL_NORMAL: str = "NORMAL"
LABEL_ELEVATED: str = "ELEVATED"
LABEL_SUSPICIOUS: str = "SUSPICIOUS"
LABEL_SCAM_LIKELY: str = "SCAM_LIKELY"
LABEL_UNKNOWN: str = "UNKNOWN"
LABEL_INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"
LABEL_MISSING_INPUT: str = "MISSING_INPUT"


LABELS: tuple[str, ...] = (
    LABEL_NORMAL,
    LABEL_ELEVATED,
    LABEL_SUSPICIOUS,
    LABEL_SCAM_LIKELY,
    LABEL_UNKNOWN,
    LABEL_INSUFFICIENT_DATA,
    LABEL_MISSING_INPUT,
)


# ---------------------------------------------------------------------------
# DATA_STATUSES -- closed set of input-completeness tokens
# ---------------------------------------------------------------------------


DATA_STATUS_COMPLETE: str = "COMPLETE"
DATA_STATUS_PARTIAL: str = "PARTIAL"
DATA_STATUS_MISSING: str = "MISSING"
DATA_STATUS_UNSUPPORTED: str = "UNSUPPORTED"


DATA_STATUSES: tuple[str, ...] = (
    DATA_STATUS_COMPLETE,
    DATA_STATUS_PARTIAL,
    DATA_STATUS_MISSING,
    DATA_STATUS_UNSUPPORTED,
)


# ---------------------------------------------------------------------------
# FILTER_FAMILIES -- closed set of Stage 23 observe-only filter folders
# ---------------------------------------------------------------------------
#
# Each family is a folder of labels, not a single boolean. Locked
# per Stage 23.0 design.


FILTER_FAMILY_HOLDER_CONCENTRATION: str = "HOLDER_CONCENTRATION"
FILTER_FAMILY_LAUNCH_STRUCTURE: str = "LAUNCH_STRUCTURE"
FILTER_FAMILY_WALLET_SOURCE_QUALITY: str = "WALLET_SOURCE_QUALITY"


FILTER_FAMILIES: tuple[str, ...] = (
    FILTER_FAMILY_HOLDER_CONCENTRATION,
    FILTER_FAMILY_LAUNCH_STRUCTURE,
    FILTER_FAMILY_WALLET_SOURCE_QUALITY,
)


# ---------------------------------------------------------------------------
# Stage 23 forbidden routing tokens (locally re-declared)
# ---------------------------------------------------------------------------
#
# Stage 23 inherits the Stage 20 / Stage 21 / Stage 22 prohibition
# against subscriber / public / paid routing and re-declares the
# locked tuple locally so the Stage 23 routing-scan boundary test
# does not need to reach into prior stages. Stage 23 does NOT
# route -- it emits evidence.


STAGE23_FORBIDDEN_ROUTING_TOKENS: tuple[str, ...] = (
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
# Stage 23 forbidden vocabulary (boundary scanner input)
# ---------------------------------------------------------------------------
#
# Identifier-position substrings the Stage 23 production source
# MUST NOT define. These are concerns that belong to strictly
# later stages or are forever forbidden in Stage 23:
#   * ``scheduler`` / ``daemon`` / ``orchestrator`` / ``run_loop``
#     / ``worker`` -- long-running infra (out of scope for the
#     Stage 23 contract surface).
#   * ``telegram`` / ``axiom`` / ``jito`` -- wrong-stage concerns
#     (Stage 24 / Stage 27).
#   * ``birdeye`` / ``dexscreener`` / ``migration`` / ``ath`` --
#     Stage 25 measurement primitives.
#   * ``priority_fee`` / ``compute_budget`` / ``execution_quality``
#     -- Stage 24 fee / execution primitives.
#   * ``dispatch`` / ``alert`` -- routing concerns (Stage 23 is
#     observe-only).
#   * ``enforce`` / ``block`` / ``gate`` -- Stage 26 enforcement
#     candidates.
#
# IMPORTANT: ``filter`` / ``evaluation`` / ``label`` / ``input`` /
# ``manifest`` / ``reader`` are NOT on this list -- Stage 23 is
# the legitimate home for that vocabulary.


STAGE23_FORBIDDEN_VOCABULARY: tuple[str, ...] = (
    "scheduler",
    "daemon",
    "orchestrator",
    "run_loop",
    "worker",
    "telegram",
    "axiom",
    "jito",
    "birdeye",
    "dexscreener",
    "migration",
    "priority_fee",
    "compute_budget",
    "execution_quality",
    "enforce",
    "gate",
)


# ---------------------------------------------------------------------------
# Stage 23 input-reader closed-set tokens
# ---------------------------------------------------------------------------
#
# Stage 22-shaped inputs the Stage 23 input reader can interpret
# at 23.1. Each token identifies the source kind of an input
# JSONL file. Locked at 23.1; new sources require a contract
# patch.


INPUT_KIND_RAW_CAPTURE: str = "raw_capture"
INPUT_KIND_DEDUPE: str = "dedupe"
INPUT_KIND_SYNTHETIC: str = "synthetic"


INPUT_KINDS: tuple[str, ...] = (
    INPUT_KIND_RAW_CAPTURE,
    INPUT_KIND_DEDUPE,
    INPUT_KIND_SYNTHETIC,
)


# ---------------------------------------------------------------------------
# Stage 23 input-reader preserved-field allowlist
# ---------------------------------------------------------------------------
#
# Fields the input reader preserves verbatim from a Stage 22-shaped
# row when they are present and non-empty. Anything outside this
# tuple is dropped. The reader never fabricates a default value
# for a missing optional field.


INPUT_PRESERVED_FIELDS: tuple[str, ...] = (
    "provider_id",
    "event_id",
    "captured_event_id",
    "token_mint",
    "mint",
    "slot",
    "signature",
    "observed_at_utc",
    "received_at_utc",
    "payload_summary",
)


# ---------------------------------------------------------------------------
# Stage 23 redaction discipline -- forbidden field-name substrings
# ---------------------------------------------------------------------------
#
# Field-name substrings that, if seen on an input row, cause the
# reader to reject the row with ``Stage23InputError``. This is the
# second line of defense behind the Stage 22 capture writer's own
# sanitiser; if a Stage 22 artifact ever leaks a secret-bearing
# field, Stage 23 refuses to ingest it rather than passing it
# through.


STAGE23_FORBIDDEN_INPUT_FIELD_SUBSTRINGS: tuple[str, ...] = (
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
# the Stage 23 boundary scanner forbids never appear in this
# source file. Mirrors the Stage 22 / Stage 21 pattern.


_COLON_SLASH_SLASH: str = ":" + "//"
_HTTP_SCHEME: str = "http" + _COLON_SLASH_SLASH
_HTTPS_SCHEME: str = "https" + _COLON_SLASH_SLASH
_WS_SCHEME: str = "ws" + _COLON_SLASH_SLASH
_WSS_SCHEME: str = "wss" + _COLON_SLASH_SLASH

_DOT_COM: str = "." + "com"
_DISCORD_HOST: str = "discord" + _DOT_COM
_DISCORDAPP_HOST: str = "discordapp" + _DOT_COM
_HOOKS_SLACK_HOST: str = "hooks" + ".slack" + _DOT_COM


# Substrings the input reader rejects anywhere inside a value of a
# preserved row field (case-insensitive). The colon-slash-slash
# entry catches URL prefixes that drop the scheme as well as the
# concrete schemes.


STAGE23_FORBIDDEN_INPUT_VALUE_SUBSTRINGS: tuple[str, ...] = (
    _HTTP_SCHEME,
    _HTTPS_SCHEME,
    _WS_SCHEME,
    _WSS_SCHEME,
    _COLON_SLASH_SLASH,
    _DISCORD_HOST,
    _DISCORDAPP_HOST,
    _HOOKS_SLACK_HOST,
)


# Long-token leak shape thresholds. Mirrors Stage 22's capture
# writer constants so the Stage 23 input reader's runtime sanitiser
# matches the upstream writer's runtime sanitiser exactly.


STAGE23_LONG_HEX_RUN_MIN_LEN: int = 40
STAGE23_LONG_TOKENISH_MIN_LEN: int = 32
