"""Stage 21 locked constants (foundation only at 21.1).

All Stage 21 version strings, private-preview marker constants,
default-mode flags, and the closed E2100/W2100 code registry live
here. Stage 21 follows the Stage 20 convention of mixing the major
+ minor version into every Stage 21 ID derivation so any drift in
version requires an explicit bump.

Stage 21 is locked observe-only at 21.1: no real provider call,
no real Discord/TG send, no orchestrator, no live runner. The
literal Python ``False`` value of ``SAFE_FOR_PUBLIC_DISPATCH`` is
the dispatch-side gate; it is the analog of Stage 20's
``SAFE_FOR_LIVE_DISPATCH`` and stays ``False`` in source until a
later sub-stage with its own design lock flips it.

This module is the only source of truth for Stage 21 codes.
``PHX2/stage21/errors.py`` reads from ``Stage21ErrorCode`` /
``Stage21WarningCode`` here -- no other location declares Stage 21
codes.
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Mapping


# ---------------------------------------------------------------------------
# Stage 21 version strings
# ---------------------------------------------------------------------------


STAGE21_VERSION: str = "stage21_v0_private_preview_foundation"
# Minor version axis. Bump on every sub-stage merge: 21.1 -> 21.2 -> ...
# Both STAGE21_VERSION and STAGE21_MINOR_VERSION are emitted in any
# Stage 21 manifest and mixed into every Stage 21 ID derivation.
STAGE21_MINOR_VERSION: str = "21.1"

# Stage 21 consumes the closed Stage 20 packet as a deterministic
# input shape; Stage 22 will consume Stage 21's own outputs. The
# Stage 21 -> Stage 22 contract version is reserved here but not
# yet emitted by any 21.1 writer.
STAGE21_CONSUMER_CONTRACT_VERSION: str = "stage21_to_stage22_v0"


# ---------------------------------------------------------------------------
# Private-preview marker constants
# ---------------------------------------------------------------------------
#
# Per the Stage 20 closure handoff (Section C) every Stage 21 preview
# ping must carry an explicit, visible private-preview marker. The
# exact rendered phrasing is a Stage 21 design call; these constants
# are the locked tokens that the renderer / dispatcher MUST embed in
# the rendered output once those modules land. Stage 21.1 ships the
# constants only -- no renderer is implemented here.


PRIVATE_PREVIEW_BANNER_TEXT: str = "PHX2 PRIVATE PREVIEW"
PRIVATE_PREVIEW_OPERATOR_ONLY_TEXT: str = "OPERATOR ONLY"
PRIVATE_PREVIEW_DO_NOT_FORWARD_TEXT: str = (
    "DO NOT FORWARD AS PUBLIC SIGNAL"
)

# Frozen tuple of the three required marker tokens. The Stage 21.2+
# renderer asserts every rendered preview contains each token before
# returning. The order is stable so any drift requires a
# STAGE21_VERSION bump.
PRIVATE_PREVIEW_REQUIRED_TOKENS: tuple[str, ...] = (
    PRIVATE_PREVIEW_BANNER_TEXT,
    PRIVATE_PREVIEW_OPERATOR_ONLY_TEXT,
    PRIVATE_PREVIEW_DO_NOT_FORWARD_TEXT,
)


# ---------------------------------------------------------------------------
# Stage 21 dispatch-safety invariants (hardcoded False in 21.1)
# ---------------------------------------------------------------------------


# Dispatch-side analog of Stage 20's SAFE_FOR_LIVE_DISPATCH. The
# literal Python ``False`` is intentional. Flipping this to True
# requires (a) an explicit operator design lock for the sub-stage
# that introduces real dispatch, and (b) updates to every Stage 21
# secret / boundary test.
SAFE_FOR_PUBLIC_DISPATCH: bool = False

# Default-mode flags. These describe the *intended default* behavior
# of any future Stage 21 runner; Stage 21.1 itself ships no runner.
# Tests assert these defaults stay as locked here so a runner cannot
# silently flip them.
DEFAULT_DRY_RUN: bool = True
DEFAULT_LIVE_PRIVATE: bool = False

# Soft per-run event cap. The runner does not exist yet, but the cap
# is locked here so the eventual runner cannot exceed it without
# bumping the constant. Stage 21.1 ships no runner.
DEFAULT_MAX_EVENTS_PER_RUN: int = 64


# ---------------------------------------------------------------------------
# Stage 21 provider-mode / sink-mode vocabularies
# ---------------------------------------------------------------------------


class ProviderModeName(str, Enum):
    """Closed set of Stage 21 provider mode names.

    Stage 21.1 ships only the FAKE mode wired into the import
    boundary. ``LIVE`` and ``REPLAY`` are reserved -- a later
    sub-stage owns the live adapter and the deterministic replay
    harness.
    """

    FAKE = "FAKE"
    REPLAY = "REPLAY"
    LIVE = "LIVE"


class SinkModeName(str, Enum):
    """Closed set of Stage 21 sink mode names.

    Stage 21.1 ships only the FAKE mode wired into the import
    boundary. ``PRIVATE_PREVIEW`` is reserved for the Stage 21.x
    dispatch sub-stage that introduces the real Discord / Telegram
    sender. No subscriber / public / paid sink will ever be
    introduced in Stage 21.
    """

    FAKE = "FAKE"
    PRIVATE_PREVIEW = "PRIVATE_PREVIEW"


# ---------------------------------------------------------------------------
# Stage 21 closed E-code / W-code registry (E2100..E2199 / W2100..W2199)
# ---------------------------------------------------------------------------
#
# The Stage 21 code range is reserved local to this stage. No prior
# Stage 7..20 code is reused. Stage 21.1 declares the codes that
# 21.1 actively raises plus the codes reserved for the named later
# sub-stages. Reserved codes are listed in the corresponding
# ``CODES_RESERVED_*`` frozensets so the registry test can assert
# every declared code is accounted for as either active or reserved.


class Stage21ErrorCode(str, Enum):
    """Closed set of Stage 21 error codes (E2100..E2199).

    21.1 active codes:
        E2100  config_secret_missing_for_selected_mode
        E2101  config_invalid_mode_value
        E2102  config_invalid_allowlist_value
        E2103  secret_fingerprint_invalid_input
        E2104  credential_attestation_invalid_record
        E2105  allowlist_parser_invalid_token
        E2106  manifest_writer_bad_target_path

    21.2 reserved (renderer + private-preview marker enforcement):
        E2110  preview_marker_missing
        E2111  preview_marker_token_mismatch
        E2112  preview_rendered_payload_too_large
        E2113  candidate_to_ping_mapping_violation

    21.3 reserved (provider adapter):
        E2120  provider_contract_violation
        E2121  provider_event_schema_violation
        E2122  provider_response_unhandled_type

    21.4 reserved (transport adapter):
        E2130  transport_contract_violation
        E2131  transport_target_not_in_allowlist
        E2132  transport_rejected_dispatch_safety_false

    21.5 reserved (minimum-safe local ledger / dedupe scaffold;
                   full retry/dedupe belongs to Stage 22):
        E2140  local_ledger_duplicate_run_id
        E2141  local_ledger_record_invalid_shape
    """

    # 21.1 active
    E2100 = "E2100"
    E2101 = "E2101"
    E2102 = "E2102"
    E2103 = "E2103"
    E2104 = "E2104"
    E2105 = "E2105"
    E2106 = "E2106"
    # 21.2 reserved
    E2110 = "E2110"
    E2111 = "E2111"
    E2112 = "E2112"
    E2113 = "E2113"
    # 21.3 reserved
    E2120 = "E2120"
    E2121 = "E2121"
    E2122 = "E2122"
    # 21.4 reserved
    E2130 = "E2130"
    E2131 = "E2131"
    E2132 = "E2132"
    # 21.5 reserved
    E2140 = "E2140"
    E2141 = "E2141"


class Stage21WarningCode(str, Enum):
    """Closed set of Stage 21 warning codes (W2100..W2199).

    21.1 active warnings:
        W2100  config_optional_secret_missing
        W2101  allowlist_empty_fail_closed
        W2102  credential_attestation_zero_length

    21.2 reserved:
        W2110  preview_marker_replaced
        W2111  candidate_to_ping_skipped

    21.3 reserved:
        W2120  provider_event_dropped_unhandled
        W2121  provider_event_dropped_throttle

    21.4 reserved:
        W2130  transport_target_skipped_not_in_allowlist

    21.5 reserved:
        W2140  local_ledger_already_recorded
    """

    # 21.1 active
    W2100 = "W2100"
    W2101 = "W2101"
    W2102 = "W2102"
    # 21.2 reserved
    W2110 = "W2110"
    W2111 = "W2111"
    # 21.3 reserved
    W2120 = "W2120"
    W2121 = "W2121"
    # 21.4 reserved
    W2130 = "W2130"
    # 21.5 reserved
    W2140 = "W2140"


# Snake_case names for each code. Single source of truth for the
# human-readable name used by error messages and reports.
STAGE21_ERROR_CODE_NAMES: Mapping[str, str] = MappingProxyType({
    "E2100": "config_secret_missing_for_selected_mode",
    "E2101": "config_invalid_mode_value",
    "E2102": "config_invalid_allowlist_value",
    "E2103": "secret_fingerprint_invalid_input",
    "E2104": "credential_attestation_invalid_record",
    "E2105": "allowlist_parser_invalid_token",
    "E2106": "manifest_writer_bad_target_path",
    "E2110": "preview_marker_missing",
    "E2111": "preview_marker_token_mismatch",
    "E2112": "preview_rendered_payload_too_large",
    "E2113": "candidate_to_ping_mapping_violation",
    "E2120": "provider_contract_violation",
    "E2121": "provider_event_schema_violation",
    "E2122": "provider_response_unhandled_type",
    "E2130": "transport_contract_violation",
    "E2131": "transport_target_not_in_allowlist",
    "E2132": "transport_rejected_dispatch_safety_false",
    "E2140": "local_ledger_duplicate_run_id",
    "E2141": "local_ledger_record_invalid_shape",
})


STAGE21_WARNING_CODE_NAMES: Mapping[str, str] = MappingProxyType({
    "W2100": "config_optional_secret_missing",
    "W2101": "allowlist_empty_fail_closed",
    "W2102": "credential_attestation_zero_length",
    "W2110": "preview_marker_replaced",
    "W2111": "candidate_to_ping_skipped",
    "W2120": "provider_event_dropped_unhandled",
    "W2121": "provider_event_dropped_throttle",
    "W2130": "transport_target_skipped_not_in_allowlist",
    "W2140": "local_ledger_already_recorded",
})


# Active-in-21.1 vs reserved-for-later partitions. Used by the
# registry test to assert every declared code is accounted for and
# that no active 21.1 code is shipped without a name entry.
CODES_ACTIVE_IN_STAGE_21_1: frozenset[str] = frozenset({
    "E2100",
    "E2101",
    "E2102",
    "E2103",
    "E2104",
    "E2105",
    "E2106",
})

CODES_RESERVED_FOR_LATER_STAGE_21: frozenset[str] = frozenset({
    # 21.2
    "E2110",
    "E2111",
    "E2112",
    "E2113",
    # 21.3
    "E2120",
    "E2121",
    "E2122",
    # 21.4
    "E2130",
    "E2131",
    "E2132",
    # 21.5
    "E2140",
    "E2141",
})

WARNINGS_ACTIVE_IN_STAGE_21_1: frozenset[str] = frozenset({
    "W2100",
    "W2101",
    "W2102",
})

WARNINGS_RESERVED_FOR_LATER_STAGE_21: frozenset[str] = frozenset({
    "W2110",
    "W2111",
    "W2120",
    "W2121",
    "W2130",
    "W2140",
})


# ---------------------------------------------------------------------------
# Stage 21 env-var names
# ---------------------------------------------------------------------------
#
# The only Stage 21 module permitted to read os.environ / os.getenv
# is ``PHX2/stage21/config.py``. The exact variable names live here
# as constants so the config module can be tested without secrets,
# and so the secret-leak test can assert these strings never leak
# into telemetry / manifest output. The strings themselves are not
# secret; the values they reference are.
#
# NB: every value referenced by one of these names is treated as
# secret-class -- including the webhook URLs.


ENV_VAR_PROVIDER_MODE: str = "PHX2_STAGE21_PROVIDER_MODE"
ENV_VAR_SINK_MODE: str = "PHX2_STAGE21_SINK_MODE"
ENV_VAR_PROVIDER_API_KEY: str = "PHX2_STAGE21_PROVIDER_API_KEY"
ENV_VAR_PROVIDER_RPC_URL: str = "PHX2_STAGE21_PROVIDER_RPC_URL"
ENV_VAR_DISCORD_WEBHOOK_URL: str = "PHX2_STAGE21_DISCORD_WEBHOOK_URL"
ENV_VAR_TELEGRAM_BOT_TOKEN: str = "PHX2_STAGE21_TELEGRAM_BOT_TOKEN"
ENV_VAR_TELEGRAM_CHAT_ID: str = "PHX2_STAGE21_TELEGRAM_CHAT_ID"
ENV_VAR_ALLOWLIST_OPERATOR_IDS: str = "PHX2_STAGE21_ALLOWLIST_OPERATOR_IDS"
ENV_VAR_DRY_RUN: str = "PHX2_STAGE21_DRY_RUN"
ENV_VAR_LIVE_PRIVATE: str = "PHX2_STAGE21_LIVE_PRIVATE"

# Frozen tuple used by both the config module and the secret-leak
# test. Updating this tuple is the single point of change.
STAGE21_SECRET_ENV_VARS: tuple[str, ...] = (
    ENV_VAR_PROVIDER_API_KEY,
    ENV_VAR_PROVIDER_RPC_URL,
    ENV_VAR_DISCORD_WEBHOOK_URL,
    ENV_VAR_TELEGRAM_BOT_TOKEN,
    ENV_VAR_TELEGRAM_CHAT_ID,
)

STAGE21_NON_SECRET_ENV_VARS: tuple[str, ...] = (
    ENV_VAR_PROVIDER_MODE,
    ENV_VAR_SINK_MODE,
    ENV_VAR_ALLOWLIST_OPERATOR_IDS,
    ENV_VAR_DRY_RUN,
    ENV_VAR_LIVE_PRIVATE,
)


# ---------------------------------------------------------------------------
# Fingerprint configuration
# ---------------------------------------------------------------------------


# Length of the truncated sha256 fingerprint emitted by the
# redaction helpers. 12 hex chars matches the locked spec
# (sha256(value).hexdigest()[:12]).
SECRET_FINGERPRINT_HEX_LENGTH: int = 12


# Sentinel string used in public summaries to mark a present-but-
# redacted value. The literal value itself MUST NOT collide with
# any plausible real secret prefix.
REDACTED_VALUE_SENTINEL: str = "<redacted>"


# ---------------------------------------------------------------------------
# Routing tokens forbidden in Stage 21 production source
# ---------------------------------------------------------------------------
#
# The Stage 20 closure handoff (Sections C, G) forbids subscriber /
# public / paid routing in Stage 21. The substring-level test in
# ``test_no_public_routing.py`` asserts none of these tokens appear
# in any Stage 21 production module's source (substring match).
#
# This tuple is intentionally NOT exported via ``__all__`` -- it is
# read by the boundary test only. Keeping it scoped to the
# constants module means any drift in the forbidden set requires
# bumping STAGE21_VERSION (the constants module sources its
# version from the same file).


STAGE21_FORBIDDEN_ROUTING_TOKENS: tuple[str, ...] = (
    # Subscriber-side routing is forever forbidden in Stage 21.
    "subscriber",
    "subscribers",
    "subscriber_channel",
    # Public / paid routing is forever forbidden in Stage 21.
    "public_channel",
    "public_signal",
    "public_dispatch",
    "paid_signal",
    "paid_signals",
    "paid_channel",
    "paid_dispatch",
)
# AUDIT-004: ``public_dispatch`` and ``paid_dispatch`` are
# restored to the forbidden set. The earlier exclusion was
# substring-based and produced a false positive on the locked
# Stage 21 invariant name ``safe_for_public_dispatch``. The new
# identifier-aware scanner in
# ``PHX2/tests/stage21/test_no_public_routing.py`` extracts
# identifiers (not raw substrings) and explicitly allows the
# invariant name via ``STAGE21_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS``
# while still flagging any real ``public_dispatch`` /
# ``paid_dispatch`` symbol.

# Locked explicit-allow set: identifiers that legitimately contain
# a forbidden routing token as a sub-component. The scanner
# whitelist is the ONLY way to allow a hit; adding to this tuple
# requires a STAGE21_VERSION bump and an operator review.
STAGE21_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS: tuple[str, ...] = (
    "safe_for_public_dispatch",
    "SAFE_FOR_PUBLIC_DISPATCH",
)


__all__ = [
    "CODES_ACTIVE_IN_STAGE_21_1",
    "CODES_RESERVED_FOR_LATER_STAGE_21",
    "DEFAULT_DRY_RUN",
    "DEFAULT_LIVE_PRIVATE",
    "DEFAULT_MAX_EVENTS_PER_RUN",
    "ENV_VAR_ALLOWLIST_OPERATOR_IDS",
    "ENV_VAR_DISCORD_WEBHOOK_URL",
    "ENV_VAR_DRY_RUN",
    "ENV_VAR_LIVE_PRIVATE",
    "ENV_VAR_PROVIDER_API_KEY",
    "ENV_VAR_PROVIDER_MODE",
    "ENV_VAR_PROVIDER_RPC_URL",
    "ENV_VAR_SINK_MODE",
    "ENV_VAR_TELEGRAM_BOT_TOKEN",
    "ENV_VAR_TELEGRAM_CHAT_ID",
    "PRIVATE_PREVIEW_BANNER_TEXT",
    "PRIVATE_PREVIEW_DO_NOT_FORWARD_TEXT",
    "PRIVATE_PREVIEW_OPERATOR_ONLY_TEXT",
    "PRIVATE_PREVIEW_REQUIRED_TOKENS",
    "ProviderModeName",
    "REDACTED_VALUE_SENTINEL",
    "SAFE_FOR_PUBLIC_DISPATCH",
    "SECRET_FINGERPRINT_HEX_LENGTH",
    "SinkModeName",
    "STAGE21_CONSUMER_CONTRACT_VERSION",
    "STAGE21_ERROR_CODE_NAMES",
    "STAGE21_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS",
    "STAGE21_FORBIDDEN_ROUTING_TOKENS",
    "STAGE21_MINOR_VERSION",
    "STAGE21_NON_SECRET_ENV_VARS",
    "STAGE21_SECRET_ENV_VARS",
    "STAGE21_VERSION",
    "STAGE21_WARNING_CODE_NAMES",
    "Stage21ErrorCode",
    "Stage21WarningCode",
    "WARNINGS_ACTIVE_IN_STAGE_21_1",
    "WARNINGS_RESERVED_FOR_LATER_STAGE_21",
]
