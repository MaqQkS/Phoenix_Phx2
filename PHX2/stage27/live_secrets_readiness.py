"""Stage 27.1 secrets / config readiness boundary.

This module is the SINGLE Stage 27 surface that reads the process
environment. Every other Stage 27 module receives either a
``Stage27SecretsReadinessReport`` or an explicit ``env`` mapping
that was projected through this boundary. The Stage 27.1 boundary
test scans the Stage 27 production tree to prove the
``os.environ`` / ``os.getenv`` / ``os.environb`` attribute access
appears only here.

Stage 27.1 redaction discipline:

  * ``Stage27ConfigFieldRecord`` instances never carry a raw
    secret value. ``kind=SECRET`` records pin ``safe_value=None``;
    ``kind=CONFIG`` records carry the raw value because it is
    safe to display (paths / numbers / labels / bool literals).
  * ``Stage27SecretsReadinessReport`` carries only names + closed-
    set tokens + lengths; never raw values.
  * ``build_redacted_readiness_summary`` renders only safe lines.

This module performs ONLY readiness detection. It does NOT:

  * call any provider (no Helius / gRPC / Birdeye client),
  * send anything to Discord,
  * make any network request,
  * validate by reaching the remote endpoint,
  * persist anything to disk,
  * cache any raw secret value beyond function-local scope.

This module imports stdlib (``os`` / ``typing``) plus the Stage 27
models / errors modules. It does NOT import any other Stage 27
module so the env-read isolation is unambiguous.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

from PHX2.stage27.live_config_errors import Stage27RedactionLeakError
from PHX2.stage27.live_config_models import (
    CONFIG_FIELD_KIND_CONFIG,
    CONFIG_FIELD_KIND_SECRET,
    MALFORMED_REASON_EMPTY,
    MALFORMED_REASON_NOT_BOOL_LITERAL,
    MALFORMED_REASON_NOT_HTTPS_URL,
    MALFORMED_REASON_NOT_INT,
    MALFORMED_REASON_NOT_POSITIVE_INT,
    MALFORMED_REASON_NO_HOST_PORT,
    SECRET_PRESENCE_MALFORMED,
    SECRET_PRESENCE_MISSING,
    SECRET_PRESENCE_PRESENT,
    STAGE27_ALL_FIELD_NAMES,
    STAGE27_HELIUS_GRPC_ENDPOINT_NAME,
    STAGE27_HELIUS_RPC_URL_NAME,
    STAGE27_LIVE_MODE_ALLOWED_NAME,
    STAGE27_LIVE_REQUIRED_FIELD_NAMES,
    STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME,
    STAGE27_REDACTION_TOKEN,
    STAGE27_RUNNER_MAX_EVENTS_NAME,
    STAGE27_RUNNER_MAX_SECONDS_NAME,
    Stage27ConfigFieldRecord,
    Stage27LiveModeAuthority,
    Stage27RedactedReadinessSummary,
    Stage27RunIdentity,
    Stage27SecretsReadinessReport,
    field_kind_for_name,
)


# ---------------------------------------------------------------------------
# Bool literal allowlist for PHX2_LIVE_MODE_ALLOWED
# ---------------------------------------------------------------------------


# Conservative bool-literal allowlist for the PHX2_LIVE_MODE_ALLOWED
# config flag. Anything outside this set is MALFORMED.
_BOOL_TRUE_LITERALS: frozenset[str] = frozenset(
    {"1", "true", "TRUE", "True", "yes", "YES", "Yes"}
)
_BOOL_FALSE_LITERALS: frozenset[str] = frozenset(
    {"0", "false", "FALSE", "False", "no", "NO", "No", ""}
)


# ---------------------------------------------------------------------------
# Internal env-read primitive
# ---------------------------------------------------------------------------


def _read_env_value(
    name: str,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Return the env value for ``name``, or ``None`` if not set.

    When ``env`` is provided, the projection runs against the
    caller-supplied mapping (the testing path). When ``env`` is
    ``None``, the projection runs against ``os.environ`` -- this
    is the ONLY production env-read site in the Stage 27 tree.
    """
    if env is not None:
        value = env.get(name)
    else:
        value = os.environ.get(name)
    if value is None:
        return None
    return value


# ---------------------------------------------------------------------------
# Format validation
# ---------------------------------------------------------------------------


def _validate_format(name: str, value: str) -> Optional[str]:
    """Return a closed-set malformed-reason or ``None`` when valid.

    Stage 27.1 keeps the validators light: just enough to gate
    LIVE-mode on obviously broken values. Deeper validation
    (provider liveness, webhook reachability) is intentionally NOT
    done here -- Stage 27.1 must not make network calls.
    """
    if value == "":
        return MALFORMED_REASON_EMPTY

    if name == STAGE27_HELIUS_RPC_URL_NAME:
        if not (value.startswith("https://") or value.startswith("http://")):
            return MALFORMED_REASON_NOT_HTTPS_URL
        return None

    if name == STAGE27_PRIVATE_DISCORD_WEBHOOK_URL_NAME:
        if not value.startswith("https://"):
            return MALFORMED_REASON_NOT_HTTPS_URL
        return None

    if name == STAGE27_HELIUS_GRPC_ENDPOINT_NAME:
        # Accept either ``host:port`` or a URL scheme. Don't try to
        # parse port range -- format check is conservative.
        if value.startswith("https://") or value.startswith("http://"):
            return None
        if ":" not in value or value.endswith(":"):
            return MALFORMED_REASON_NO_HOST_PORT
        return None

    if name == STAGE27_LIVE_MODE_ALLOWED_NAME:
        if value in _BOOL_TRUE_LITERALS or value in _BOOL_FALSE_LITERALS:
            return None
        return MALFORMED_REASON_NOT_BOOL_LITERAL

    if name in (
        STAGE27_RUNNER_MAX_EVENTS_NAME,
        STAGE27_RUNNER_MAX_SECONDS_NAME,
    ):
        try:
            parsed = int(value)
        except ValueError:
            return MALFORMED_REASON_NOT_INT
        if parsed <= 0:
            return MALFORMED_REASON_NOT_POSITIVE_INT
        return None

    # HELIUS_API_KEY, BIRDEYE_API_KEY, PHX2_STAGE27_SCRATCH_DIR,
    # PHX2_PROVIDER_ID: any non-empty value passes Stage 27.1.
    return None


# ---------------------------------------------------------------------------
# Field-level detection
# ---------------------------------------------------------------------------


def detect_field_presence(
    name: str,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> Stage27ConfigFieldRecord:
    """Project a single Stage 27 env / config name to a presence record.

    Raw secret values never appear on the returned record. For
    ``kind=CONFIG`` names (paths / labels / numbers / bool
    literals) the safe value IS exposed because the value is
    intentionally non-secret.
    """
    if name not in STAGE27_ALL_FIELD_NAMES:
        raise ValueError(
            f"unknown Stage 27 field name: {name!r}"
        )

    kind = field_kind_for_name(name)
    raw_value = _read_env_value(name, env=env)

    if raw_value is None:
        return Stage27ConfigFieldRecord(
            name=name,
            kind=kind,
            presence_status=SECRET_PRESENCE_MISSING,
            malformed_reason=None,
            safe_value=None,
            value_length=None,
        )

    malformed_reason = _validate_format(name, raw_value)
    value_length = len(raw_value)

    if malformed_reason is not None:
        return Stage27ConfigFieldRecord(
            name=name,
            kind=kind,
            presence_status=SECRET_PRESENCE_MALFORMED,
            malformed_reason=malformed_reason,
            safe_value=None,
            value_length=value_length,
        )

    if kind == CONFIG_FIELD_KIND_SECRET:
        safe_value = None
    else:
        safe_value = raw_value

    return Stage27ConfigFieldRecord(
        name=name,
        kind=kind,
        presence_status=SECRET_PRESENCE_PRESENT,
        malformed_reason=None,
        safe_value=safe_value,
        value_length=value_length,
    )


# ---------------------------------------------------------------------------
# Bulk detection
# ---------------------------------------------------------------------------


def detect_all_stage27_field_presence(
    *,
    env: Optional[Mapping[str, str]] = None,
) -> Stage27SecretsReadinessReport:
    """Project every Stage 27 expected name to a readiness report."""
    field_records = tuple(
        detect_field_presence(name, env=env)
        for name in STAGE27_ALL_FIELD_NAMES
    )

    missing: list[str] = []
    malformed: list[str] = []
    for record in field_records:
        if record.name not in STAGE27_LIVE_REQUIRED_FIELD_NAMES:
            continue
        if record.presence_status == SECRET_PRESENCE_MISSING:
            missing.append(record.name)
        elif record.presence_status == SECRET_PRESENCE_MALFORMED:
            malformed.append(record.name)

    all_present = not missing and not malformed

    return Stage27SecretsReadinessReport(
        fields=field_records,
        required_live_missing=tuple(missing),
        required_live_malformed=tuple(malformed),
        all_required_live_present=all_present,
    )


# ---------------------------------------------------------------------------
# Env-flag interpretation
# ---------------------------------------------------------------------------


def env_flag_is_truthy_from_record(
    record: Stage27ConfigFieldRecord,
) -> bool:
    """Return ``True`` iff the ``PHX2_LIVE_MODE_ALLOWED`` field record
    parses as a truthy bool literal.

    A ``MALFORMED`` or ``MISSING`` flag is treated as falsy. This
    is the conservative fail-closed default.
    """
    if record.name != STAGE27_LIVE_MODE_ALLOWED_NAME:
        raise ValueError(
            f"env_flag_is_truthy_from_record only accepts the "
            f"{STAGE27_LIVE_MODE_ALLOWED_NAME!r} record; got "
            f"{record.name!r}"
        )
    if record.presence_status != SECRET_PRESENCE_PRESENT:
        return False
    return record.safe_value in _BOOL_TRUE_LITERALS


# ---------------------------------------------------------------------------
# Redacted summary builder
# ---------------------------------------------------------------------------


def build_redacted_readiness_summary(
    report: Stage27SecretsReadinessReport,
    authority: Stage27LiveModeAuthority,
    identity: Stage27RunIdentity,
) -> Stage27RedactedReadinessSummary:
    """Render a safe-to-display summary of the readiness report.

    Every emitted line carries only:

      * field NAMES,
      * closed-set tokens (``PRESENT`` / ``MISSING`` /
        ``MALFORMED`` / malformed-reason / kind),
      * the redaction token for any SECRET field that was present,
      * the safe value for CONFIG fields that were present,
      * the mode label.

    The function raises ``Stage27RedactionLeakError`` if its
    internal invariants detect that a SECRET-kind field record
    accidentally carries a non-``None`` ``safe_value``. This is a
    defensive belt-and-braces check; the model layer is supposed
    to enforce the invariant, but this redaction surface re-checks
    so any future regression fails closed here rather than leaking
    silently.
    """
    lines: list[str] = []
    lines.append(
        f"Stage27 operator readiness | session_id={identity.session_id} "
        f"run_id={identity.run_id} mode={authority.resolved}"
    )
    lines.append(
        f"created_at_utc={identity.created_at_utc} "
        f"stage={identity.stage} substage={identity.substage} "
        f"schema_version={identity.schema_version}"
    )
    lines.append(
        f"mode_resolution: env_flag_set={authority.env_flag_set} "
        f"cli_live_requested={authority.cli_live_requested} "
        f"required_live_secrets_present="
        f"{authority.required_live_secrets_present} "
        f"reason={authority.reason_code}"
    )

    for record in report.fields:
        if (
            record.kind == CONFIG_FIELD_KIND_SECRET
            and record.safe_value is not None
        ):
            raise Stage27RedactionLeakError(
                secret_name=record.name,
                leak_context="readiness_summary_secret_safe_value",
                secret_value_length=record.value_length,
            )
        value_token = _value_token_for_record(record)
        lines.append(
            f"  {record.name}: kind={record.kind} "
            f"status={record.presence_status} "
            f"length={record.value_length} value={value_token}"
        )

    if report.required_live_missing:
        lines.append(
            "required_live_missing: "
            f"{list(report.required_live_missing)!r}"
        )
    if report.required_live_malformed:
        lines.append(
            "required_live_malformed: "
            f"{list(report.required_live_malformed)!r}"
        )

    return Stage27RedactedReadinessSummary(
        lines=tuple(lines),
        mode_label=authority.resolved,
        redaction_token=STAGE27_REDACTION_TOKEN,
    )


def _value_token_for_record(record: Stage27ConfigFieldRecord) -> str:
    """Return the safe display token for a field record.

    Rules:

      * ``MISSING`` -- the literal ``"<missing>"`` token.
      * ``MALFORMED`` -- the literal ``"<malformed:REASON>"`` token.
      * ``SECRET`` ``PRESENT`` -- the Stage 27 redaction token.
      * ``CONFIG`` ``PRESENT`` -- the raw safe value (safe by
                                   construction: kind=CONFIG values
                                   are paths / labels / numbers /
                                   bool literals).
    """
    if record.presence_status == SECRET_PRESENCE_MISSING:
        return "<missing>"
    if record.presence_status == SECRET_PRESENCE_MALFORMED:
        reason = record.malformed_reason or "UNKNOWN"
        return f"<malformed:{reason}>"
    if record.kind == CONFIG_FIELD_KIND_SECRET:
        return STAGE27_REDACTION_TOKEN
    if record.safe_value is None:
        return STAGE27_REDACTION_TOKEN
    return record.safe_value


__all__ = (
    "detect_field_presence",
    "detect_all_stage27_field_presence",
    "env_flag_is_truthy_from_record",
    "build_redacted_readiness_summary",
)
