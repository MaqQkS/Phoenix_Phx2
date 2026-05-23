"""Stage 28.1 provider-neutral readiness boundary.

This module is the SINGLE Stage 28 surface that reads the process
environment for Stage 28.1 provider-neutral env names. Every
other Stage 28.1 module receives an explicit ``Mapping[str, str]``
projected through this boundary, mirroring the Stage 27.1
``live_secrets_readiness`` discipline.

The boundary scan asserts ``os.environ`` / ``os.getenv`` /
``os.environb`` appear only here in the Stage 28 production tree.

Stage 28.1 readiness composes the per-canonical-field
``ProviderNeutralResolution`` (from
``provider_neutral_config``) into a
``ProviderNeutralReadinessReport`` whose ``readiness_status`` is
``READY`` only when:

  * every required canonical field resolved cleanly (no MISSING,
    no CONFLICT, no INVALID), AND
  * the provider_id label, if present, passed validation, AND
  * the provider_kind label, if present, is in the closed set.

The readiness layer does NOT:

  * call any provider (no Helius / Chainstack / Yellowstone gRPC
    / Birdeye client),
  * send anything to Discord,
  * make any network request,
  * validate by reaching the remote endpoint,
  * persist anything to disk,
  * cache any raw secret value beyond function-local scope.

This module imports stdlib (``os`` / ``typing``) plus the Stage
28.1 models + config modules. It does NOT import Stage 21-26
production code; it may optionally read Stage 27-locked legacy
env names through its own ``os.environ`` read, but does NOT
import the Stage 27 readiness module (the Stage 28.1 boundary
keeps Stage 28 readable as a standalone wrapper).
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

from PHX2.stage28.provider_neutral_config import (
    resolve_provider_neutral_config,
)
from PHX2.stage28.provider_neutral_models import (
    FAILURE_REASON_INVALID_PROVIDER_KIND,
    FIELD_KIND_SECRET,
    FIELD_STATUS_CONFLICT,
    FIELD_STATUS_INVALID,
    FIELD_STATUS_MISSING,
    LEGACY_ALIAS_API_KEY_NAMES,
    LEGACY_ALIAS_GRPC_ENDPOINT_NAMES,
    LEGACY_ALIAS_RPC_URL_NAMES,
    PROVIDER_FIELD_PROVIDER_ID,
    PROVIDER_FIELD_PROVIDER_KIND,
    PROVIDER_KIND_UNKNOWN,
    PROVIDER_NEUTRAL_ENV_NAMES,
    PROVIDER_REQUIRED_FIELDS,
    READINESS_STATUS_NOT_READY,
    READINESS_STATUS_READY,
    REDACTION_STATUS_NO_SECRET_MATERIAL,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE_LABEL_ONLY,
    STAGE28_1_REDACTION_TOKEN,
    Stage28_1RedactionLeakError,
    ProviderNeutralReadinessReport,
    ProviderNeutralRedactedSummary,
    ProviderNeutralResolution,
)


# ---------------------------------------------------------------------------
# Stage 28.1 env-name surface
# ---------------------------------------------------------------------------


# The exact set of env names Stage 28.1 reads from ``os.environ``.
# Locked here so the boundary scan can pin it -- if Stage 28.1
# ever needs to read a new env name, the addition must land here
# explicitly.
STAGE28_1_READ_ENV_NAMES: tuple[str, ...] = (
    PROVIDER_NEUTRAL_ENV_NAMES
    + LEGACY_ALIAS_GRPC_ENDPOINT_NAMES
    + LEGACY_ALIAS_RPC_URL_NAMES
    + LEGACY_ALIAS_API_KEY_NAMES
)


# ---------------------------------------------------------------------------
# Env projection
# ---------------------------------------------------------------------------


def _read_env_value(
    name: str,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """Return the env value for ``name``, or ``None`` if not set.

    When ``env`` is provided, the projection runs against the
    caller-supplied mapping (the testing path). When ``env`` is
    ``None``, the projection runs against ``os.environ`` -- this
    is the ONLY production env-read site in the Stage 28 tree.
    """
    if env is not None:
        value = env.get(name)
    else:
        value = os.environ.get(name)
    if value is None:
        return None
    return value


def project_stage28_1_env(
    env: Optional[Mapping[str, str]] = None,
) -> dict[str, str]:
    """Project the Stage 28.1 env-name surface into a plain dict.

    The returned dict contains only Stage 28.1 names whose values
    were set (non-``None``); empty-string values are preserved
    because the resolver classifies them as missing/empty.

    Pure with respect to a caller-supplied ``env``: when ``env``
    is supplied, only that mapping is consulted. When ``env`` is
    ``None``, the function reads ``os.environ`` (the Stage 28
    env-read boundary).
    """
    projected: dict[str, str] = {}
    for name in STAGE28_1_READ_ENV_NAMES:
        value = _read_env_value(name, env=env)
        if value is None:
            continue
        projected[name] = value
    return projected


# ---------------------------------------------------------------------------
# Readiness aggregation
# ---------------------------------------------------------------------------


def _classify_redaction_status(
    resolution: ProviderNeutralResolution,
) -> str:
    """Return the closed-set redaction-status token for a resolution.

    Rules:

      * If any SECRET-kind canonical field resolved to PRESENT
        (regardless of source), the public surface is
        ``REDACTED`` -- a secret was handled and the raw value
        has been stripped.
      * Else if any LABEL-kind canonical field exposed a safe
        label, the public surface is ``SAFE_LABEL_ONLY``.
      * Else ``NO_SECRET_MATERIAL``.
    """
    saw_secret_present = False
    saw_label = False
    for record in resolution.fields:
        if record.kind == FIELD_KIND_SECRET:
            if record.field_status not in (
                FIELD_STATUS_MISSING,
                FIELD_STATUS_CONFLICT,
                FIELD_STATUS_INVALID,
            ):
                saw_secret_present = True
        else:
            if record.safe_label_value is not None:
                saw_label = True
    if saw_secret_present:
        return REDACTION_STATUS_REDACTED
    if saw_label:
        return REDACTION_STATUS_SAFE_LABEL_ONLY
    return REDACTION_STATUS_NO_SECRET_MATERIAL


def _extract_safe_provider_id(
    resolution: ProviderNeutralResolution,
) -> Optional[str]:
    for record in resolution.fields:
        if record.canonical_field == PROVIDER_FIELD_PROVIDER_ID:
            return record.safe_label_value
    return None


def _extract_provider_kind(
    resolution: ProviderNeutralResolution,
) -> tuple[str, Optional[str]]:
    """Return ``(provider_kind, failure_reason_or_None)``.

    Missing PROVIDER_KIND defaults to ``unknown`` with no failure.
    INVALID PROVIDER_KIND defaults to ``unknown`` with the
    closed-set ``INVALID_PROVIDER_KIND`` failure reason recorded
    on the readiness report.
    """
    for record in resolution.fields:
        if record.canonical_field != PROVIDER_FIELD_PROVIDER_KIND:
            continue
        if (
            record.field_status == FIELD_STATUS_MISSING
            or record.safe_label_value is None
        ):
            if record.field_status == FIELD_STATUS_INVALID:
                return PROVIDER_KIND_UNKNOWN, FAILURE_REASON_INVALID_PROVIDER_KIND
            return PROVIDER_KIND_UNKNOWN, None
        return record.safe_label_value, None
    return PROVIDER_KIND_UNKNOWN, None


def _collect_failure_reasons(
    resolution: ProviderNeutralResolution,
    provider_kind_failure: Optional[str],
) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for record in resolution.fields:
        if record.failure_reason is None:
            continue
        # Only required-field MISSING counts as a failure.
        if (
            record.field_status == FIELD_STATUS_MISSING
            and record.canonical_field not in PROVIDER_REQUIRED_FIELDS
        ):
            continue
        seen[record.failure_reason] = None
    if provider_kind_failure is not None:
        seen[provider_kind_failure] = None
    return tuple(seen.keys())


def assess_provider_neutral_readiness(
    resolution: ProviderNeutralResolution,
) -> ProviderNeutralReadinessReport:
    """Compose a ``ProviderNeutralReadinessReport`` from a
    ``ProviderNeutralResolution``.

    Pure: no env access, no I/O.
    """
    provider_kind, provider_kind_failure = _extract_provider_kind(
        resolution
    )
    provider_id = _extract_safe_provider_id(resolution)
    failure_reasons = _collect_failure_reasons(
        resolution, provider_kind_failure
    )
    if failure_reasons:
        readiness_status = READINESS_STATUS_NOT_READY
    else:
        readiness_status = READINESS_STATUS_READY
    redaction_status = _classify_redaction_status(resolution)
    return ProviderNeutralReadinessReport(
        resolution=resolution,
        readiness_status=readiness_status,
        failure_reasons=failure_reasons,
        provider_id=provider_id,
        provider_kind=provider_kind,
        redaction_status=redaction_status,
    )


def detect_stage28_1_readiness(
    env: Optional[Mapping[str, str]] = None,
) -> ProviderNeutralReadinessReport:
    """Top-level Stage 28.1 readiness entry point.

    Projects the Stage 28.1 env name surface through the env-read
    boundary, runs the provider-neutral resolver, and assesses
    readiness.

    When ``env`` is ``None`` the function reads ``os.environ``
    (the production path). Tests pass an explicit ``env`` mapping
    to keep the readiness layer deterministic.
    """
    projected = project_stage28_1_env(env=env)
    resolution = resolve_provider_neutral_config(projected)
    return assess_provider_neutral_readiness(resolution)


# ---------------------------------------------------------------------------
# Redacted summary builder
# ---------------------------------------------------------------------------


def _resolution_value_token(
    record_kind: str,
    record_status: str,
    safe_label_value: Optional[str],
) -> str:
    """Return the safe display token for one resolution record."""
    if record_status == FIELD_STATUS_MISSING:
        return "<missing>"
    if record_status == FIELD_STATUS_CONFLICT:
        return "<conflict>"
    if record_status == FIELD_STATUS_INVALID:
        return "<invalid>"
    if record_kind == FIELD_KIND_SECRET:
        return STAGE28_1_REDACTION_TOKEN
    if safe_label_value is None:
        return STAGE28_1_REDACTION_TOKEN
    return safe_label_value


def build_redacted_summary(
    report: ProviderNeutralReadinessReport,
) -> ProviderNeutralRedactedSummary:
    """Render a safe-to-display summary of ``report``.

    Every line carries only canonical-field names + closed-set
    status tokens + (for LABEL-kind fields) the safe label. No
    raw secret value, no raw endpoint, no raw RPC URL, no raw
    API-key substring, no raw webhook URL leaks here.

    Defensive: if a SECRET-kind record ever carries a non-``None``
    ``safe_label_value``, the function raises
    ``Stage28_1RedactionLeakError`` so the regression fails closed
    instead of leaking silently.
    """
    lines: list[str] = []
    lines.append(
        f"Stage28.1 provider-neutral readiness | "
        f"status={report.readiness_status} "
        f"provider_kind={report.provider_kind} "
        f"provider_id={report.provider_id or '<missing>'} "
        f"redaction_status={report.redaction_status}"
    )
    if report.resolution.legacy_alias_used:
        lines.append(
            "legacy_alias_used=true (prefer provider-neutral env "
            "names going forward)"
        )

    for record in report.resolution.fields:
        if (
            record.kind == FIELD_KIND_SECRET
            and record.safe_label_value is not None
        ):
            raise Stage28_1RedactionLeakError(
                canonical_field=record.canonical_field,
                leak_context="readiness_summary_secret_safe_label",
                value_length=record.raw_value_length,
            )
        token = _resolution_value_token(
            record.kind, record.field_status, record.safe_label_value
        )
        legacy_marker = (
            f" legacy_env={record.legacy_alias_env_name!r}"
            if record.legacy_alias_env_name is not None
            else ""
        )
        fr = (
            f" failure_reason={record.failure_reason}"
            if record.failure_reason is not None
            else ""
        )
        lines.append(
            f"  {record.canonical_field}: kind={record.kind} "
            f"status={record.field_status} "
            f"source={record.source_status} "
            f"length={record.raw_value_length} "
            f"value={token}"
            f"{legacy_marker}{fr}"
        )

    if report.failure_reasons:
        lines.append(
            f"failure_reasons={list(report.failure_reasons)!r}"
        )

    return ProviderNeutralRedactedSummary(
        lines=tuple(lines),
        readiness_status=report.readiness_status,
        redaction_status=report.redaction_status,
        redaction_token=STAGE28_1_REDACTION_TOKEN,
    )


__all__ = (
    "STAGE28_1_READ_ENV_NAMES",
    "project_stage28_1_env",
    "assess_provider_neutral_readiness",
    "detect_stage28_1_readiness",
    "build_redacted_summary",
)
