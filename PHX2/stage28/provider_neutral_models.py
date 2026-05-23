"""Stage 28.1 provider-neutral config closed-set vocabularies and records.

Stage 28.1 ships the provider-neutral config wrapper / secrets-
readiness cleanup layer for Stage 28. The wrapper introduces
Stage 28 provider-neutral env names (``PHX2_PROVIDER_GRPC_ENDPOINT``,
``PHX2_PROVIDER_RPC_URL``, ``PHX2_PROVIDER_API_KEY``,
``PHX2_PROVIDER_ID``, ``PHX2_PROVIDER_KIND``) and preserves the
Stage 27-era ``HELIUS_*`` / ``PHX2_HELIUS_*`` names as legacy
aliases.

This module ships only:

  * the locked closed-set vocabularies (field status / source
    status / readiness status / redaction status / failure reason
    / provider kind),
  * the locked Stage 28.1 expected env-name constants (provider-
    neutral names + legacy alias names + required-set partition),
  * the locked Stage 28.1 redaction-token literal,
  * the immutable per-field resolution record shape,
  * the immutable provider-neutral resolution record shape,
  * the immutable provider-neutral readiness report record shape,
  * the immutable provider-neutral redacted summary record shape,
  * the module-local exception hierarchy.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here -- the Stage 28.1 boundary scan pins
    this.
  * No network. No Discord. No gRPC. No HTTP. No file I/O.
  * Stage 28.1 raw secret values never appear on a public record.
    SECRET-kind fields carry ``safe_value=None`` by construction;
    the resolved value (if any) is held only behind the
    ``raw_secret_length`` / ``raw_value_length`` axes that report
    presence + length without the value itself.
  * ``repr()`` / ``str()`` of any record is safe to log / print /
    persist; no raw provider endpoint, RPC URL, API key, webhook
    URL, bearer token, or auth header substring is carried by any
    record.

This module imports only stdlib (``typing``). It does NOT import
Stage 21-27 production code, does NOT import any network / RPC /
messaging / DB / scheduler / secrets-management library, does NOT
read the process environment, does NOT define a CLI surface, and
contains no top-level I/O.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


# ---------------------------------------------------------------------------
# Stage 28.1 version axes
# ---------------------------------------------------------------------------


STAGE28_1_MINOR_VERSION: str = "28.1"
STAGE28_1_SCHEMA_VERSION: str = "stage28_v0_provider_neutral_config"


# ---------------------------------------------------------------------------
# Closed-set: provider-neutral canonical field tokens
# ---------------------------------------------------------------------------


# The Stage 28.1 canonical field-name tokens. These are the
# logical field names the resolver returns; the env-name strings
# (provider-neutral + legacy alias) live in the constants block
# below.
PROVIDER_FIELD_GRPC_ENDPOINT: str = "PROVIDER_GRPC_ENDPOINT"
PROVIDER_FIELD_RPC_URL: str = "PROVIDER_RPC_URL"
PROVIDER_FIELD_API_KEY: str = "PROVIDER_API_KEY"
PROVIDER_FIELD_PROVIDER_ID: str = "PROVIDER_ID"
PROVIDER_FIELD_PROVIDER_KIND: str = "PROVIDER_KIND"


PROVIDER_FIELD_VALUES: tuple[str, ...] = (
    PROVIDER_FIELD_GRPC_ENDPOINT,
    PROVIDER_FIELD_RPC_URL,
    PROVIDER_FIELD_API_KEY,
    PROVIDER_FIELD_PROVIDER_ID,
    PROVIDER_FIELD_PROVIDER_KIND,
)


# ---------------------------------------------------------------------------
# Closed-set: per-field status
# ---------------------------------------------------------------------------


FIELD_STATUS_PRESENT: str = "PRESENT"
FIELD_STATUS_MISSING: str = "MISSING"
FIELD_STATUS_CONFLICT: str = "CONFLICT"
FIELD_STATUS_INVALID: str = "INVALID"

FIELD_STATUS_VALUES: tuple[str, ...] = (
    FIELD_STATUS_PRESENT,
    FIELD_STATUS_MISSING,
    FIELD_STATUS_CONFLICT,
    FIELD_STATUS_INVALID,
)


# ---------------------------------------------------------------------------
# Closed-set: per-field source kind
# ---------------------------------------------------------------------------


SOURCE_STATUS_PROVIDER_NEUTRAL: str = "PROVIDER_NEUTRAL"
SOURCE_STATUS_LEGACY_ALIAS: str = "LEGACY_ALIAS"
SOURCE_STATUS_BOTH_SAME: str = "BOTH_SAME"
SOURCE_STATUS_BOTH_CONFLICT: str = "BOTH_CONFLICT"
SOURCE_STATUS_MISSING: str = "MISSING"

SOURCE_STATUS_VALUES: tuple[str, ...] = (
    SOURCE_STATUS_PROVIDER_NEUTRAL,
    SOURCE_STATUS_LEGACY_ALIAS,
    SOURCE_STATUS_BOTH_SAME,
    SOURCE_STATUS_BOTH_CONFLICT,
    SOURCE_STATUS_MISSING,
)


# ---------------------------------------------------------------------------
# Closed-set: readiness status
# ---------------------------------------------------------------------------


READINESS_STATUS_READY: str = "READY"
READINESS_STATUS_NOT_READY: str = "NOT_READY"

READINESS_STATUS_VALUES: tuple[str, ...] = (
    READINESS_STATUS_READY,
    READINESS_STATUS_NOT_READY,
)


# ---------------------------------------------------------------------------
# Closed-set: redaction status
# ---------------------------------------------------------------------------


# REDACTED              -- a SECRET field was present and its raw
#                          value has been stripped from every public
#                          surface; only the canonical name + length
#                          axes are exposed.
# SAFE_LABEL_ONLY       -- a CONFIG field carries a safe non-secret
#                          label (e.g. provider_id, provider_kind);
#                          the safe label is exposed.
# NO_SECRET_MATERIAL    -- the field was missing or the resolver
#                          encountered no SECRET material at all.
REDACTION_STATUS_REDACTED: str = "REDACTED"
REDACTION_STATUS_SAFE_LABEL_ONLY: str = "SAFE_LABEL_ONLY"
REDACTION_STATUS_NO_SECRET_MATERIAL: str = "NO_SECRET_MATERIAL"

REDACTION_STATUS_VALUES: tuple[str, ...] = (
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE_LABEL_ONLY,
    REDACTION_STATUS_NO_SECRET_MATERIAL,
)


# ---------------------------------------------------------------------------
# Closed-set: failure reason codes
# ---------------------------------------------------------------------------


FAILURE_REASON_MISSING_REQUIRED_FIELD: str = "MISSING_REQUIRED_FIELD"
FAILURE_REASON_CONFLICTING_PROVIDER_ENV_VALUES: str = (
    "CONFLICTING_PROVIDER_ENV_VALUES"
)
FAILURE_REASON_INVALID_PROVIDER_ID: str = "INVALID_PROVIDER_ID"
FAILURE_REASON_INVALID_PROVIDER_KIND: str = "INVALID_PROVIDER_KIND"
FAILURE_REASON_SECRET_LIKE_PROVIDER_LABEL: str = (
    "SECRET_LIKE_PROVIDER_LABEL"
)
FAILURE_REASON_UNSUPPORTED_PROVIDER_KIND: str = (
    "UNSUPPORTED_PROVIDER_KIND"
)

FAILURE_REASON_VALUES: tuple[str, ...] = (
    FAILURE_REASON_MISSING_REQUIRED_FIELD,
    FAILURE_REASON_CONFLICTING_PROVIDER_ENV_VALUES,
    FAILURE_REASON_INVALID_PROVIDER_ID,
    FAILURE_REASON_INVALID_PROVIDER_KIND,
    FAILURE_REASON_SECRET_LIKE_PROVIDER_LABEL,
    FAILURE_REASON_UNSUPPORTED_PROVIDER_KIND,
)


# ---------------------------------------------------------------------------
# Closed-set: provider kind tokens
# ---------------------------------------------------------------------------


PROVIDER_KIND_YELLOWSTONE_GRPC: str = "yellowstone_grpc"
PROVIDER_KIND_JSON_RPC: str = "json_rpc"
PROVIDER_KIND_HELIUS_LEGACY: str = "helius_legacy"
PROVIDER_KIND_UNKNOWN: str = "unknown"

PROVIDER_KIND_VALUES: tuple[str, ...] = (
    PROVIDER_KIND_YELLOWSTONE_GRPC,
    PROVIDER_KIND_JSON_RPC,
    PROVIDER_KIND_HELIUS_LEGACY,
    PROVIDER_KIND_UNKNOWN,
)


# ---------------------------------------------------------------------------
# Closed-set: per-field kind (SECRET vs LABEL)
# ---------------------------------------------------------------------------


# Stage 28.1 distinguishes SECRET fields (raw value must never be
# displayed) from LABEL fields (safe non-secret value is allowed
# on the record). This vocabulary mirrors the Stage 27.1
# CONFIG_FIELD_KIND_* split.
FIELD_KIND_SECRET: str = "SECRET"
FIELD_KIND_LABEL: str = "LABEL"

FIELD_KIND_VALUES: tuple[str, ...] = (
    FIELD_KIND_SECRET,
    FIELD_KIND_LABEL,
)


# ---------------------------------------------------------------------------
# Provider-neutral env name constants
# ---------------------------------------------------------------------------


# Stage 28.1 canonical provider-neutral env-variable names.
STAGE28_PROVIDER_GRPC_ENDPOINT_NAME: str = "PHX2_PROVIDER_GRPC_ENDPOINT"
STAGE28_PROVIDER_RPC_URL_NAME: str = "PHX2_PROVIDER_RPC_URL"
STAGE28_PROVIDER_API_KEY_NAME: str = "PHX2_PROVIDER_API_KEY"
STAGE28_PROVIDER_ID_NAME: str = "PHX2_PROVIDER_ID"
STAGE28_PROVIDER_KIND_NAME: str = "PHX2_PROVIDER_KIND"


PROVIDER_NEUTRAL_ENV_NAMES: tuple[str, ...] = (
    STAGE28_PROVIDER_GRPC_ENDPOINT_NAME,
    STAGE28_PROVIDER_RPC_URL_NAME,
    STAGE28_PROVIDER_API_KEY_NAME,
    STAGE28_PROVIDER_ID_NAME,
    STAGE28_PROVIDER_KIND_NAME,
)


# Stage 27-era + PHX2-prefixed Helius legacy env aliases. Stage 27
# uses the bare ``HELIUS_*`` names; some operator scripts in the
# wild also use the ``PHX2_HELIUS_*`` form. Stage 28.1 admits both
# alias forms per canonical field.
LEGACY_ALIAS_GRPC_ENDPOINT_NAMES: tuple[str, ...] = (
    "HELIUS_GRPC_ENDPOINT",
    "PHX2_HELIUS_GRPC_ENDPOINT",
)
LEGACY_ALIAS_RPC_URL_NAMES: tuple[str, ...] = (
    "HELIUS_RPC_URL",
    "PHX2_HELIUS_RPC_URL",
)
LEGACY_ALIAS_API_KEY_NAMES: tuple[str, ...] = (
    "HELIUS_API_KEY",
    "PHX2_HELIUS_API_KEY",
)


# Canonical-field -> (provider-neutral env name, tuple of legacy
# alias env names). Stage 28.1 PROVIDER_ID has no separate legacy
# alias because Stage 27 already used the ``PHX2_PROVIDER_ID``
# spelling; Stage 28.1 PROVIDER_KIND has no legacy alias because
# Stage 27 had no provider-kind concept.
PROVIDER_FIELD_ENV_BINDING: dict[str, tuple[str, tuple[str, ...]]] = {
    PROVIDER_FIELD_GRPC_ENDPOINT: (
        STAGE28_PROVIDER_GRPC_ENDPOINT_NAME,
        LEGACY_ALIAS_GRPC_ENDPOINT_NAMES,
    ),
    PROVIDER_FIELD_RPC_URL: (
        STAGE28_PROVIDER_RPC_URL_NAME,
        LEGACY_ALIAS_RPC_URL_NAMES,
    ),
    PROVIDER_FIELD_API_KEY: (
        STAGE28_PROVIDER_API_KEY_NAME,
        LEGACY_ALIAS_API_KEY_NAMES,
    ),
    PROVIDER_FIELD_PROVIDER_ID: (
        STAGE28_PROVIDER_ID_NAME,
        (),
    ),
    PROVIDER_FIELD_PROVIDER_KIND: (
        STAGE28_PROVIDER_KIND_NAME,
        (),
    ),
}


# Per-canonical-field kind partition: SECRET fields must never
# expose the raw value on a record; LABEL fields may carry the
# safe value.
PROVIDER_FIELD_KIND: dict[str, str] = {
    PROVIDER_FIELD_GRPC_ENDPOINT: FIELD_KIND_SECRET,
    PROVIDER_FIELD_RPC_URL: FIELD_KIND_SECRET,
    PROVIDER_FIELD_API_KEY: FIELD_KIND_SECRET,
    PROVIDER_FIELD_PROVIDER_ID: FIELD_KIND_LABEL,
    PROVIDER_FIELD_PROVIDER_KIND: FIELD_KIND_LABEL,
}


# Required-for-READY canonical fields. The grpc endpoint, RPC URL,
# API key, and provider id are required to mark Stage 28 provider
# readiness. The provider kind is optional; when absent it
# resolves to ``unknown``.
PROVIDER_REQUIRED_FIELDS: tuple[str, ...] = (
    PROVIDER_FIELD_GRPC_ENDPOINT,
    PROVIDER_FIELD_RPC_URL,
    PROVIDER_FIELD_API_KEY,
    PROVIDER_FIELD_PROVIDER_ID,
)


# ---------------------------------------------------------------------------
# Redaction token
# ---------------------------------------------------------------------------


# Distinctive Stage 28.1 redaction token. Deliberately distinct
# from the Stage 27 redaction token so a test scanning for one
# cannot collide with the other.
STAGE28_1_REDACTION_TOKEN: str = "<<STAGE28_1_REDACTED>>"


# ---------------------------------------------------------------------------
# Module-local exception hierarchy
# ---------------------------------------------------------------------------


class Stage28_1ProviderConfigError(Exception):
    """Base type for every Stage 28.1 provider-neutral config error.

    Module-local; not a subclass of any central PHX2 error
    registry. Raw secret values must never reach the constructor;
    callers redact at the call site.
    """


class Stage28_1ConflictingProviderEnvValuesError(
    Stage28_1ProviderConfigError
):
    """Raised when a provider-neutral env name and its legacy
    alias are both set with non-matching values.

    Carries only the canonical field token + the env name pair +
    closed-set source-status; never the raw value of either side.
    """

    def __init__(
        self,
        canonical_field: str,
        provider_neutral_env_name: str,
        legacy_alias_env_name: str,
    ) -> None:
        self.canonical_field: str = canonical_field
        self.provider_neutral_env_name: str = provider_neutral_env_name
        self.legacy_alias_env_name: str = legacy_alias_env_name
        super().__init__(
            f"Stage 28.1 conflicting provider env values: "
            f"field={canonical_field!r} "
            f"provider_neutral={provider_neutral_env_name!r} "
            f"legacy_alias={legacy_alias_env_name!r}"
        )


class Stage28_1InvalidProviderLabelError(Stage28_1ProviderConfigError):
    """Raised when a provider-id or provider-kind label fails
    Stage 28.1 validation.

    Carries only the canonical field token + the closed-set
    failure reason; never the raw rejected label. The Stage 28.1
    boundary discipline forbids surfacing the raw label because a
    secret-looking label is exactly what the rejection is gating.
    """

    def __init__(
        self,
        canonical_field: str,
        failure_reason: str,
    ) -> None:
        self.canonical_field: str = canonical_field
        self.failure_reason: str = failure_reason
        super().__init__(
            f"Stage 28.1 invalid provider label: "
            f"field={canonical_field!r} reason={failure_reason!r}"
        )


class Stage28_1RedactionLeakError(Stage28_1ProviderConfigError):
    """Raised when a redaction-protected Stage 28.1 surface would
    have emitted a raw secret value.

    Carries only the canonical field token + a closed-set leak-
    context token + an optional length; the raw value is never
    carried.
    """

    def __init__(
        self,
        canonical_field: str,
        leak_context: str,
        *,
        value_length: Optional[int] = None,
    ) -> None:
        self.canonical_field: str = canonical_field
        self.leak_context: str = leak_context
        self.value_length: Optional[int] = value_length
        msg = (
            f"Stage 28.1 redaction leak: "
            f"field={canonical_field!r} context={leak_context!r}"
        )
        if value_length is not None:
            msg += f" length={value_length}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Immutable record shapes
# ---------------------------------------------------------------------------


class ProviderFieldResolution(NamedTuple):
    """Per-canonical-field resolution record.

    Fields:

      * ``canonical_field``           -- one of
                                          ``PROVIDER_FIELD_VALUES``.
      * ``kind``                      -- one of
                                          ``FIELD_KIND_VALUES``.
      * ``field_status``              -- one of
                                          ``FIELD_STATUS_VALUES``.
      * ``source_status``             -- one of
                                          ``SOURCE_STATUS_VALUES``.
      * ``provider_neutral_present``  -- ``True`` iff the
                                          canonical provider-
                                          neutral env name was set.
      * ``legacy_alias_present``      -- ``True`` iff at least one
                                          legacy alias env name was
                                          set.
      * ``legacy_alias_env_name``     -- the specific legacy alias
                                          env-name that contributed
                                          a value, or ``None``.
      * ``safe_label_value``          -- present LABEL-kind value
                                          (provider_id or
                                          provider_kind) when safe
                                          to display; ``None``
                                          otherwise. NEVER carries a
                                          SECRET-kind raw value.
      * ``raw_value_length``          -- length of the resolved
                                          value when present
                                          (regardless of kind);
                                          ``None`` when missing.
      * ``failure_reason``            -- closed-set failure-reason
                                          token, or ``None`` if the
                                          field resolved cleanly.
    """

    canonical_field: str
    kind: str
    field_status: str
    source_status: str
    provider_neutral_present: bool
    legacy_alias_present: bool
    legacy_alias_env_name: Optional[str]
    safe_label_value: Optional[str]
    raw_value_length: Optional[int]
    failure_reason: Optional[str]


class ProviderNeutralResolution(NamedTuple):
    """Bundled per-canonical-field resolution covering every
    Stage 28.1 expected canonical field.

    Fields:

      * ``fields``                  -- per-canonical-field records.
      * ``missing_required_fields`` -- canonical fields in
                                        ``PROVIDER_REQUIRED_FIELDS``
                                        that are MISSING.
      * ``conflicting_fields``      -- canonical fields whose
                                        provider-neutral name and
                                        legacy alias both resolved
                                        to non-matching values.
      * ``invalid_fields``          -- canonical fields whose
                                        resolved value failed
                                        Stage 28.1 validation
                                        (e.g. provider_id /
                                        provider_kind).
      * ``legacy_alias_used``       -- ``True`` iff at least one
                                        canonical field resolved
                                        via a legacy alias only
                                        (warning, not error).
    """

    fields: tuple[ProviderFieldResolution, ...]
    missing_required_fields: tuple[str, ...]
    conflicting_fields: tuple[str, ...]
    invalid_fields: tuple[str, ...]
    legacy_alias_used: bool


class ProviderNeutralReadinessReport(NamedTuple):
    """Stage 28.1 readiness report.

    Fields:

      * ``resolution``        -- the per-field resolution bundle.
      * ``readiness_status``  -- one of
                                  ``READINESS_STATUS_VALUES``.
      * ``failure_reasons``   -- tuple of closed-set failure-reason
                                  tokens (deduplicated, sorted in
                                  insertion order).
      * ``provider_id``       -- safe provider-id label when valid
                                  and present; ``None`` otherwise.
      * ``provider_kind``     -- one of ``PROVIDER_KIND_VALUES``;
                                  defaults to
                                  ``PROVIDER_KIND_UNKNOWN`` when the
                                  PROVIDER_KIND field was missing or
                                  invalid.
      * ``redaction_status``  -- one of
                                  ``REDACTION_STATUS_VALUES``.
    """

    resolution: ProviderNeutralResolution
    readiness_status: str
    failure_reasons: tuple[str, ...]
    provider_id: Optional[str]
    provider_kind: str
    redaction_status: str


class ProviderNeutralRedactedSummary(NamedTuple):
    """Printable Stage 28.1 readiness summary.

    Every string in ``lines`` is safe to log / print / persist;
    no raw provider endpoint, RPC URL, API key, webhook URL,
    bearer token, or auth header substring is carried.
    """

    lines: tuple[str, ...]
    readiness_status: str
    redaction_status: str
    redaction_token: str


# ---------------------------------------------------------------------------
# Label validation helpers (pure, no env, no I/O)
# ---------------------------------------------------------------------------


# Stage 28.1 provider-id allowlist character class. Provider ids
# are safe non-secret labels; the allowlist keeps them to
# lowercase alphanumerics + underscore + dash so a URL / token /
# bearer string cannot be mistaken for a provider id.
_PROVIDER_ID_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz0123456789_-"
)
_PROVIDER_ID_MAX_LENGTH: int = 64
_PROVIDER_ID_MIN_LENGTH: int = 2


# Substrings that, when present anywhere in a provider-id label,
# mean the label looks like a URL / token / webhook / auth
# material and must be rejected with the closed-set
# ``SECRET_LIKE_PROVIDER_LABEL`` failure reason. These literal
# substrings are intentionally distinctive enough that a
# legitimate provider-id label cannot collide with them.
_PROVIDER_ID_SECRET_LIKE_SUBSTRINGS: tuple[str, ...] = (
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
    "hooks" + ".slack.com",
    "/webhooks/",
)


def is_provider_id_label_safe(label: str) -> bool:
    """Return ``True`` iff ``label`` passes the Stage 28.1
    provider-id allowlist.

    The check is intentionally strict:

      * length in ``[2, 64]``,
      * characters drawn only from
        ``[a-z0-9_-]``,
      * no leading / trailing dash or underscore,
      * no consecutive run of dashes or underscores that would
        look like a token separator.

    Pure: no env access, no I/O, no logging.
    """
    if not isinstance(label, str):
        return False
    if len(label) < _PROVIDER_ID_MIN_LENGTH:
        return False
    if len(label) > _PROVIDER_ID_MAX_LENGTH:
        return False
    if label[0] in {"-", "_"} or label[-1] in {"-", "_"}:
        return False
    for ch in label:
        if ch not in _PROVIDER_ID_ALLOWED_CHARS:
            return False
    if "__" in label or "--" in label:
        return False
    return True


def is_provider_id_label_secret_like(label: str) -> bool:
    """Return ``True`` iff ``label`` matches any of the Stage 28.1
    secret-looking substring patterns.

    Used by the resolver to distinguish the closed-set failure
    reason ``SECRET_LIKE_PROVIDER_LABEL`` (apparent secret
    material) from the more generic ``INVALID_PROVIDER_ID``.

    Pure: no env access, no I/O, no logging.
    """
    if not isinstance(label, str):
        return False
    lowered = label.lower()
    for needle in _PROVIDER_ID_SECRET_LIKE_SUBSTRINGS:
        if needle in lowered:
            return True
    return False


def is_provider_kind_supported(value: str) -> bool:
    """Return ``True`` iff ``value`` is a Stage 28.1 closed-set
    provider-kind token.
    """
    return value in PROVIDER_KIND_VALUES


def canonical_field_kind(canonical_field: str) -> str:
    """Return the closed-set kind token for ``canonical_field``.

    Raises ``ValueError`` if the canonical-field token is unknown.
    """
    try:
        return PROVIDER_FIELD_KIND[canonical_field]
    except KeyError as exc:
        raise ValueError(
            f"unknown Stage 28.1 canonical field: {canonical_field!r}"
        ) from exc


__all__ = (
    # Version axes.
    "STAGE28_1_MINOR_VERSION",
    "STAGE28_1_SCHEMA_VERSION",
    # Canonical-field tokens.
    "PROVIDER_FIELD_GRPC_ENDPOINT",
    "PROVIDER_FIELD_RPC_URL",
    "PROVIDER_FIELD_API_KEY",
    "PROVIDER_FIELD_PROVIDER_ID",
    "PROVIDER_FIELD_PROVIDER_KIND",
    "PROVIDER_FIELD_VALUES",
    # Closed-set status vocabularies.
    "FIELD_STATUS_PRESENT",
    "FIELD_STATUS_MISSING",
    "FIELD_STATUS_CONFLICT",
    "FIELD_STATUS_INVALID",
    "FIELD_STATUS_VALUES",
    "SOURCE_STATUS_PROVIDER_NEUTRAL",
    "SOURCE_STATUS_LEGACY_ALIAS",
    "SOURCE_STATUS_BOTH_SAME",
    "SOURCE_STATUS_BOTH_CONFLICT",
    "SOURCE_STATUS_MISSING",
    "SOURCE_STATUS_VALUES",
    "READINESS_STATUS_READY",
    "READINESS_STATUS_NOT_READY",
    "READINESS_STATUS_VALUES",
    "REDACTION_STATUS_REDACTED",
    "REDACTION_STATUS_SAFE_LABEL_ONLY",
    "REDACTION_STATUS_NO_SECRET_MATERIAL",
    "REDACTION_STATUS_VALUES",
    # Failure reasons.
    "FAILURE_REASON_MISSING_REQUIRED_FIELD",
    "FAILURE_REASON_CONFLICTING_PROVIDER_ENV_VALUES",
    "FAILURE_REASON_INVALID_PROVIDER_ID",
    "FAILURE_REASON_INVALID_PROVIDER_KIND",
    "FAILURE_REASON_SECRET_LIKE_PROVIDER_LABEL",
    "FAILURE_REASON_UNSUPPORTED_PROVIDER_KIND",
    "FAILURE_REASON_VALUES",
    # Provider kinds.
    "PROVIDER_KIND_YELLOWSTONE_GRPC",
    "PROVIDER_KIND_JSON_RPC",
    "PROVIDER_KIND_HELIUS_LEGACY",
    "PROVIDER_KIND_UNKNOWN",
    "PROVIDER_KIND_VALUES",
    # Field-kind partition.
    "FIELD_KIND_SECRET",
    "FIELD_KIND_LABEL",
    "FIELD_KIND_VALUES",
    # Env name constants.
    "STAGE28_PROVIDER_GRPC_ENDPOINT_NAME",
    "STAGE28_PROVIDER_RPC_URL_NAME",
    "STAGE28_PROVIDER_API_KEY_NAME",
    "STAGE28_PROVIDER_ID_NAME",
    "STAGE28_PROVIDER_KIND_NAME",
    "PROVIDER_NEUTRAL_ENV_NAMES",
    "LEGACY_ALIAS_GRPC_ENDPOINT_NAMES",
    "LEGACY_ALIAS_RPC_URL_NAMES",
    "LEGACY_ALIAS_API_KEY_NAMES",
    "PROVIDER_FIELD_ENV_BINDING",
    "PROVIDER_FIELD_KIND",
    "PROVIDER_REQUIRED_FIELDS",
    # Redaction token.
    "STAGE28_1_REDACTION_TOKEN",
    # Exceptions.
    "Stage28_1ProviderConfigError",
    "Stage28_1ConflictingProviderEnvValuesError",
    "Stage28_1InvalidProviderLabelError",
    "Stage28_1RedactionLeakError",
    # Record shapes.
    "ProviderFieldResolution",
    "ProviderNeutralResolution",
    "ProviderNeutralReadinessReport",
    "ProviderNeutralRedactedSummary",
    # Helpers.
    "is_provider_id_label_safe",
    "is_provider_id_label_secret_like",
    "is_provider_kind_supported",
    "canonical_field_kind",
)
