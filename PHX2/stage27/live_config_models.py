"""Stage 27.1 closed-set vocabularies and immutable record shapes.

Stage 27.1 ships the in-memory model layer for the operator config
+ secrets-readiness surface. Every record is a frozen
``NamedTuple`` so the entire Stage 27 substage can pass these
records around without any mutable global state, and so that
``repr()`` / ``str()`` of any record never carries a raw secret
value -- because no field on any of these records is ever
populated with a raw secret value in the first place.

Closed-set vocabularies:

  * Live-mode authority states:
      ``DRY_RUN``       -- the default. Neither factor requested LIVE.
      ``LIVE_REFUSED``  -- LIVE was requested but is not allowed
                           (one-factor only, or required secrets
                           missing / malformed).
      ``LIVE_ALLOWED``  -- both factors requested LIVE AND required
                           secrets are present + format-valid.
  * Live-mode resolution reasons (closed set).
  * Secret-presence statuses: ``PRESENT`` / ``MISSING`` /
    ``MALFORMED``.
  * Stage 27 config-field kinds: ``SECRET`` (raw value must never
    be displayed) and ``CONFIG`` (raw value is safe to display).
  * Stage 27 expected env / config variable names, partitioned by
    secret-vs-config kind and by live-required-vs-optional role.
  * The Stage 27 redaction token literal.

This module imports only stdlib (``typing``). It does NOT import
Stage 21-26 production code, does NOT import any network / RPC /
messaging / DB / scheduler / secrets-management library, does NOT
read the process environment, does NOT define a CLI surface, and
contains no top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


# ---------------------------------------------------------------------------
# Stage 27 version axes
# ---------------------------------------------------------------------------


STAGE27_VERSION: str = "stage27_v0_private_live_runner"
STAGE27_MINOR_VERSION: str = "27.1"
STAGE_NAME: str = "stage27"
STAGE_VERSION: str = STAGE27_MINOR_VERSION
STAGE27_DEFAULT_SCHEMA_VERSION: str = "stage27_v0_operator_config"
STAGE27_OPERATOR_CONFIG_SCHEMA_VERSION: str = STAGE27_DEFAULT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Live-mode authority closed set
# ---------------------------------------------------------------------------


LIVE_MODE_AUTHORITY_DRY_RUN: str = "DRY_RUN"
LIVE_MODE_AUTHORITY_LIVE_REFUSED: str = "LIVE_REFUSED"
LIVE_MODE_AUTHORITY_LIVE_ALLOWED: str = "LIVE_ALLOWED"

LIVE_MODE_AUTHORITY_VALUES: tuple[str, ...] = (
    LIVE_MODE_AUTHORITY_DRY_RUN,
    LIVE_MODE_AUTHORITY_LIVE_REFUSED,
    LIVE_MODE_AUTHORITY_LIVE_ALLOWED,
)


# Closed-set reason codes that explain how the authority was resolved.
LIVE_MODE_REASON_DEFAULT_DRY_RUN: str = "DEFAULT_DRY_RUN"
LIVE_MODE_REASON_ONE_FACTOR_ENV_ONLY: str = "ONE_FACTOR_ENV_ONLY"
LIVE_MODE_REASON_ONE_FACTOR_CLI_ONLY: str = "ONE_FACTOR_CLI_ONLY"
LIVE_MODE_REASON_LIVE_SECRETS_MISSING: str = "LIVE_SECRETS_MISSING"
LIVE_MODE_REASON_LIVE_SECRETS_MALFORMED: str = "LIVE_SECRETS_MALFORMED"
LIVE_MODE_REASON_BOTH_FACTORS_AND_SECRETS_OK: str = (
    "BOTH_FACTORS_AND_SECRETS_OK"
)

LIVE_MODE_REASON_VALUES: tuple[str, ...] = (
    LIVE_MODE_REASON_DEFAULT_DRY_RUN,
    LIVE_MODE_REASON_ONE_FACTOR_ENV_ONLY,
    LIVE_MODE_REASON_ONE_FACTOR_CLI_ONLY,
    LIVE_MODE_REASON_LIVE_SECRETS_MISSING,
    LIVE_MODE_REASON_LIVE_SECRETS_MALFORMED,
    LIVE_MODE_REASON_BOTH_FACTORS_AND_SECRETS_OK,
)


# ---------------------------------------------------------------------------
# Secret-presence closed set
# ---------------------------------------------------------------------------


SECRET_PRESENCE_PRESENT: str = "PRESENT"
SECRET_PRESENCE_MISSING: str = "MISSING"
SECRET_PRESENCE_MALFORMED: str = "MALFORMED"

SECRET_PRESENCE_VALUES: tuple[str, ...] = (
    SECRET_PRESENCE_PRESENT,
    SECRET_PRESENCE_MISSING,
    SECRET_PRESENCE_MALFORMED,
)


# Closed-set malformed-reason codes. Stage 27.1 keeps validation
# light: only the format invariants required to gate LIVE mode.
MALFORMED_REASON_EMPTY: str = "EMPTY_VALUE"
MALFORMED_REASON_NOT_HTTPS_URL: str = "NOT_HTTPS_URL"
MALFORMED_REASON_NOT_INT: str = "NOT_INT"
MALFORMED_REASON_NOT_POSITIVE_INT: str = "NOT_POSITIVE_INT"
MALFORMED_REASON_NOT_BOOL_LITERAL: str = "NOT_BOOL_LITERAL"
MALFORMED_REASON_NO_HOST_PORT: str = "NO_HOST_PORT"

MALFORMED_REASON_VALUES: tuple[str, ...] = (
    MALFORMED_REASON_EMPTY,
    MALFORMED_REASON_NOT_HTTPS_URL,
    MALFORMED_REASON_NOT_INT,
    MALFORMED_REASON_NOT_POSITIVE_INT,
    MALFORMED_REASON_NOT_BOOL_LITERAL,
    MALFORMED_REASON_NO_HOST_PORT,
)


# ---------------------------------------------------------------------------
# Config-field kind closed set
# ---------------------------------------------------------------------------


CONFIG_FIELD_KIND_SECRET: str = "SECRET"
CONFIG_FIELD_KIND_CONFIG: str = "CONFIG"

CONFIG_FIELD_KIND_VALUES: tuple[str, ...] = (
    CONFIG_FIELD_KIND_SECRET,
    CONFIG_FIELD_KIND_CONFIG,
)


# ---------------------------------------------------------------------------
# Expected Stage 27 env / config variable names
# ---------------------------------------------------------------------------


# Secret values: raw value must never be displayed.
STAGE27_HELIUS_API_KEY_NAME: str = "HELIUS_API_KEY"
STAGE27_HELIUS_RPC_URL_NAME: str = "HELIUS_RPC_URL"
STAGE27_HELIUS_GRPC_ENDPOINT_NAME: str = "HELIUS_GRPC_ENDPOINT"
STAGE27_BIRDEYE_API_KEY_NAME: str = "BIRDEYE_API_KEY"
STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME: str = (
    "PHX2_PRIVATE_DISCORD_WEBHOOK_URL"
)

# Non-secret config values: raw value is safe to display.
STAGE27_SCRATCH_DIR_NAME: str = "PHX2_STAGE27_SCRATCH_DIR"
STAGE27_LIVE_MODE_ALLOWED_NAME: str = "PHX2_LIVE_MODE_ALLOWED"
STAGE27_PROVIDER_ID_NAME: str = "PHX2_PROVIDER_ID"
STAGE27_RUNNER_MAX_EVENTS_NAME: str = "PHX2_RUNNER_MAX_EVENTS"
STAGE27_RUNNER_MAX_SECONDS_NAME: str = "PHX2_RUNNER_MAX_SECONDS"


STAGE27_SECRET_NAMES: tuple[str, ...] = (
    STAGE27_HELIUS_API_KEY_NAME,
    STAGE27_HELIUS_RPC_URL_NAME,
    STAGE27_HELIUS_GRPC_ENDPOINT_NAME,
    STAGE27_BIRDEYE_API_KEY_NAME,
    STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME,
)

STAGE27_CONFIG_NAMES: tuple[str, ...] = (
    STAGE27_SCRATCH_DIR_NAME,
    STAGE27_LIVE_MODE_ALLOWED_NAME,
    STAGE27_PROVIDER_ID_NAME,
    STAGE27_RUNNER_MAX_EVENTS_NAME,
    STAGE27_RUNNER_MAX_SECONDS_NAME,
)

STAGE27_ALL_FIELD_NAMES: tuple[str, ...] = (
    STAGE27_SECRET_NAMES + STAGE27_CONFIG_NAMES
)


# Required for LIVE mode: every name in this tuple must be PRESENT
# and format-valid for the resolver to allow LIVE.
STAGE27_LIVE_REQUIRED_FIELD_NAMES: tuple[str, ...] = (
    STAGE27_HELIUS_API_KEY_NAME,
    STAGE27_HELIUS_RPC_URL_NAME,
    STAGE27_HELIUS_GRPC_ENDPOINT_NAME,
    STAGE27_BIRDEYE_API_KEY_NAME,
    STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME,
    STAGE27_PROVIDER_ID_NAME,
)


# ---------------------------------------------------------------------------
# Redaction token
# ---------------------------------------------------------------------------


# The single literal marker used in every redacted readiness
# surface to indicate "a secret value was present here but has been
# stripped". The literal is deliberately distinctive so a test
# scanning for the canary value of a fake secret cannot collide
# with a legitimate redaction marker.
STAGE27_REDACTION_TOKEN: str = "<<STAGE27_REDACTED>>"


# ---------------------------------------------------------------------------
# Immutable record shapes
# ---------------------------------------------------------------------------


class Stage27ConfigFieldRecord(NamedTuple):
    """Per-field presence/value record.

    Fields:

      * ``name``             -- env / config variable name (closed-
                                set string).
      * ``kind``             -- one of ``CONFIG_FIELD_KIND_*``.
      * ``presence_status``  -- one of ``SECRET_PRESENCE_*``.
      * ``malformed_reason`` -- closed-set malformed reason or
                                ``None`` when ``presence_status``
                                is not ``MALFORMED``.
      * ``safe_value``       -- the value when it is safe to
                                display (``kind=CONFIG`` and
                                ``presence_status=PRESENT``);
                                ``None`` otherwise. For
                                ``kind=SECRET`` this field is
                                ALWAYS ``None``; the raw secret
                                value is never stored on a
                                ``Stage27ConfigFieldRecord``.
      * ``value_length``     -- length of the raw value when the
                                field was present, regardless of
                                kind. Useful for diagnostic display
                                without leaking the value. ``None``
                                when the field was missing.
    """

    name: str
    kind: str
    presence_status: str
    malformed_reason: Optional[str]
    safe_value: Optional[str]
    value_length: Optional[int]


class Stage27SecretsReadinessReport(NamedTuple):
    """Bundled readiness report covering every Stage 27 expected name.

    Fields:

      * ``fields``                     -- per-name presence records.
      * ``required_live_missing``      -- names that LIVE requires
                                          but are missing.
      * ``required_live_malformed``    -- names that LIVE requires
                                          but are malformed.
      * ``all_required_live_present``  -- ``True`` iff every name
                                          in
                                          ``STAGE27_LIVE_REQUIRED_FIELD_NAMES``
                                          is ``PRESENT`` and not
                                          ``MALFORMED``.
    """

    fields: tuple[Stage27ConfigFieldRecord, ...]
    required_live_missing: tuple[str, ...]
    required_live_malformed: tuple[str, ...]
    all_required_live_present: bool


class Stage27LiveModeAuthority(NamedTuple):
    """Resolved two-factor LIVE-mode authority.

    Fields:

      * ``resolved``                       -- one of
                                              ``LIVE_MODE_AUTHORITY_VALUES``.
      * ``env_flag_set``                   -- ``True`` iff the
                                              ``PHX2_LIVE_MODE_ALLOWED``
                                              env / config flag
                                              parsed as a truthy
                                              bool literal.
      * ``cli_live_requested``             -- ``True`` iff the
                                              caller passed an
                                              explicit operator
                                              LIVE request.
      * ``required_live_secrets_present``  -- mirrors
                                              ``readiness.all_required_live_present``.
      * ``reason_code``                    -- one of
                                              ``LIVE_MODE_REASON_VALUES``.
    """

    resolved: str
    env_flag_set: bool
    cli_live_requested: bool
    required_live_secrets_present: bool
    reason_code: str


class Stage27RunIdentity(NamedTuple):
    """Immutable per-run identity.

    Every field is safe to display and safe to write to artifacts.
    No field carries a raw secret value.
    """

    session_id: str
    run_id: str
    created_at_utc: str
    mode: str
    stage: str
    substage: str
    schema_version: str


class Stage27RedactedReadinessSummary(NamedTuple):
    """Printable summary of operator readiness.

    Every string in ``lines`` is safe to print to a log, write to
    an artifact, or include in an operator status message. None
    of the strings carry a raw secret value, a raw webhook URL, a
    raw RPC / gRPC endpoint, or a raw API-key substring.
    """

    lines: tuple[str, ...]
    mode_label: str
    redaction_token: str


class Stage27OperatorConfig(NamedTuple):
    """Top-level immutable operator config for a Stage 27 invocation.

    Combines:

      * the per-name readiness report,
      * the resolved two-factor LIVE authority,
      * the per-run identity,
      * the printable redacted summary.

    The whole structure is safe to ``repr()`` / ``str()`` without
    leaking a raw secret value.
    """

    readiness: Stage27SecretsReadinessReport
    authority: Stage27LiveModeAuthority
    identity: Stage27RunIdentity
    redacted_summary: Stage27RedactedReadinessSummary


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def is_secret_name(name: str) -> bool:
    """Return ``True`` iff ``name`` is a Stage 27 SECRET-kind field."""
    return name in STAGE27_SECRET_NAMES


def is_config_name(name: str) -> bool:
    """Return ``True`` iff ``name`` is a Stage 27 CONFIG-kind field."""
    return name in STAGE27_CONFIG_NAMES


def is_known_stage27_field_name(name: str) -> bool:
    """Return ``True`` iff ``name`` is in the locked Stage 27 expected set."""
    return name in STAGE27_ALL_FIELD_NAMES


def field_kind_for_name(name: str) -> str:
    """Return the closed-set kind token (``SECRET`` / ``CONFIG``).

    Raises ``ValueError`` if ``name`` is not a known Stage 27 field
    name; module-local because Stage 27 errors are reserved for
    redaction / live-mode / readiness violations, not basic
    lookup-key mistakes.
    """
    if name in STAGE27_SECRET_NAMES:
        return CONFIG_FIELD_KIND_SECRET
    if name in STAGE27_CONFIG_NAMES:
        return CONFIG_FIELD_KIND_CONFIG
    raise ValueError(
        f"unknown Stage 27 field name: {name!r}"
    )
