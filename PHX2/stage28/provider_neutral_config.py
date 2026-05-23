"""Stage 28.1 provider-neutral config resolver.

Pure resolution layer. Given a ``Mapping[str, str]`` of env-like
inputs, ``resolve_provider_neutral_config`` returns an immutable
``ProviderNeutralResolution`` that bundles per-canonical-field
records.

Resolution rules (applied per canonical field):

  * If the provider-neutral env name is present and no legacy
    alias is present, resolve to the provider-neutral value;
    source_status = ``PROVIDER_NEUTRAL``.
  * If a legacy alias is present and the provider-neutral env
    name is absent, resolve to the legacy value; source_status =
    ``LEGACY_ALIAS``.
  * If both are present and identical, resolve to that value;
    source_status = ``BOTH_SAME``.
  * If both are present and different, refuse to resolve;
    source_status = ``BOTH_CONFLICT``; field_status =
    ``CONFLICT``; failure_reason =
    ``CONFLICTING_PROVIDER_ENV_VALUES``. NEITHER raw value is
    surfaced on the record.
  * If neither is present, source_status = ``MISSING``;
    field_status = ``MISSING``; failure_reason =
    ``MISSING_REQUIRED_FIELD`` for required canonical fields.

Per-field validation (after resolution):

  * ``PROVIDER_FIELD_PROVIDER_ID``: must pass
    ``is_provider_id_label_safe``. If it passes a secret-like
    substring check, failure_reason =
    ``SECRET_LIKE_PROVIDER_LABEL``. Otherwise
    ``INVALID_PROVIDER_ID``.
  * ``PROVIDER_FIELD_PROVIDER_KIND``: must be in
    ``PROVIDER_KIND_VALUES``. Missing PROVIDER_KIND is allowed --
    the readiness layer defaults to ``unknown``. An out-of-set
    value is INVALID with failure_reason
    ``UNSUPPORTED_PROVIDER_KIND``.

Discipline:

  * No env reads. ``os.environ`` is never touched here. The
    caller passes an explicit mapping. The Stage 28.1 boundary
    scan asserts the env-read site is exactly the
    ``provider_neutral_readiness`` module.
  * No network, no Discord, no file I/O.
  * Raw SECRET values never reach a public record. SECRET-kind
    canonical fields carry ``safe_label_value=None`` by
    construction; the only axes that leave the resolver for a
    SECRET field are presence flags, source-status, length, and
    failure-reason.
  * Raw LABEL values are exposed only when they pass validation
    (otherwise the ``safe_label_value`` remains ``None`` and the
    failure reason carries the closed-set token).

This module imports only stdlib (``typing``) plus the Stage 28.1
models module. It does NOT import Stage 21-27 production code,
does NOT import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

from typing import Mapping, Optional

from PHX2.stage28.provider_neutral_models import (
    FAILURE_REASON_CONFLICTING_PROVIDER_ENV_VALUES,
    FAILURE_REASON_INVALID_PROVIDER_ID,
    FAILURE_REASON_INVALID_PROVIDER_KIND,
    FAILURE_REASON_MISSING_REQUIRED_FIELD,
    FAILURE_REASON_SECRET_LIKE_PROVIDER_LABEL,
    FAILURE_REASON_UNSUPPORTED_PROVIDER_KIND,
    FIELD_KIND_LABEL,
    FIELD_KIND_SECRET,
    FIELD_STATUS_CONFLICT,
    FIELD_STATUS_INVALID,
    FIELD_STATUS_MISSING,
    FIELD_STATUS_PRESENT,
    PROVIDER_FIELD_ENV_BINDING,
    PROVIDER_FIELD_KIND,
    PROVIDER_FIELD_PROVIDER_ID,
    PROVIDER_FIELD_PROVIDER_KIND,
    PROVIDER_FIELD_VALUES,
    PROVIDER_REQUIRED_FIELDS,
    ProviderFieldResolution,
    ProviderNeutralResolution,
    SOURCE_STATUS_BOTH_CONFLICT,
    SOURCE_STATUS_BOTH_SAME,
    SOURCE_STATUS_LEGACY_ALIAS,
    SOURCE_STATUS_MISSING,
    SOURCE_STATUS_PROVIDER_NEUTRAL,
    canonical_field_kind,
    is_provider_id_label_safe,
    is_provider_id_label_secret_like,
    is_provider_kind_supported,
)


# ---------------------------------------------------------------------------
# Per-canonical-field resolution
# ---------------------------------------------------------------------------


def _select_legacy_alias_value(
    env: Mapping[str, str],
    alias_names: tuple[str, ...],
) -> tuple[Optional[str], Optional[str]]:
    """Return ``(value, env_name)`` for the first present legacy
    alias in ``alias_names``, or ``(None, None)`` if none are set.

    Multiple alias forms (e.g. ``HELIUS_GRPC_ENDPOINT`` and
    ``PHX2_HELIUS_GRPC_ENDPOINT``) are honored in declaration
    order; the first present value wins. This mirrors the Stage
    27 convention of treating the bare ``HELIUS_*`` name as the
    primary legacy form.
    """
    for name in alias_names:
        value = env.get(name)
        if value is not None and value != "":
            return value, name
    return None, None


def _validate_provider_id_resolved(
    raw_value: str,
) -> tuple[Optional[str], str, Optional[str]]:
    """Validate a resolved PROVIDER_ID value.

    Returns ``(safe_label_value, field_status, failure_reason)``.

    Order of checks:

      1. ``is_provider_id_label_secret_like`` -- if true, return
         ``(None, INVALID, SECRET_LIKE_PROVIDER_LABEL)`` so a
         label that smells like a URL / token / bearer is
         distinctly classified.
      2. ``is_provider_id_label_safe`` -- if false, return
         ``(None, INVALID, INVALID_PROVIDER_ID)``.
      3. otherwise return ``(raw_value, PRESENT, None)``.
    """
    if is_provider_id_label_secret_like(raw_value):
        return None, FIELD_STATUS_INVALID, FAILURE_REASON_SECRET_LIKE_PROVIDER_LABEL
    if not is_provider_id_label_safe(raw_value):
        return None, FIELD_STATUS_INVALID, FAILURE_REASON_INVALID_PROVIDER_ID
    return raw_value, FIELD_STATUS_PRESENT, None


def _validate_provider_kind_resolved(
    raw_value: str,
) -> tuple[Optional[str], str, Optional[str]]:
    """Validate a resolved PROVIDER_KIND value.

    Returns ``(safe_label_value, field_status, failure_reason)``.
    PROVIDER_KIND values are closed-set; an unsupported value is
    INVALID with failure_reason ``UNSUPPORTED_PROVIDER_KIND``.
    """
    if not is_provider_kind_supported(raw_value):
        return (
            None,
            FIELD_STATUS_INVALID,
            FAILURE_REASON_UNSUPPORTED_PROVIDER_KIND,
        )
    return raw_value, FIELD_STATUS_PRESENT, None


def _maybe_validate_label(
    canonical_field: str,
    raw_value: str,
) -> tuple[Optional[str], str, Optional[str]]:
    """Dispatch LABEL-kind validation by canonical field.

    SECRET-kind fields are not validated for content here (Stage
    28.1 does not parse URLs / endpoints / API keys); they are
    treated as PRESENT once a non-empty value resolves.
    """
    if canonical_field == PROVIDER_FIELD_PROVIDER_ID:
        return _validate_provider_id_resolved(raw_value)
    if canonical_field == PROVIDER_FIELD_PROVIDER_KIND:
        return _validate_provider_kind_resolved(raw_value)
    # SECRET-kind fields are never assigned a safe_label_value.
    return None, FIELD_STATUS_PRESENT, None


def resolve_canonical_field(
    canonical_field: str,
    env: Mapping[str, str],
) -> ProviderFieldResolution:
    """Resolve one canonical Stage 28.1 field against ``env``.

    Pure: ``env`` is the only input; no ``os.environ`` access.
    """
    if canonical_field not in PROVIDER_FIELD_ENV_BINDING:
        raise ValueError(
            f"unknown Stage 28.1 canonical field: {canonical_field!r}"
        )

    provider_neutral_env_name, alias_names = PROVIDER_FIELD_ENV_BINDING[
        canonical_field
    ]
    kind = canonical_field_kind(canonical_field)

    provider_neutral_value = env.get(provider_neutral_env_name)
    if provider_neutral_value == "":
        provider_neutral_value = None

    legacy_value, legacy_env_name = _select_legacy_alias_value(
        env, alias_names
    )

    provider_neutral_present = provider_neutral_value is not None
    legacy_alias_present = legacy_value is not None

    # Case 1: neither present.
    if not provider_neutral_present and not legacy_alias_present:
        is_required = canonical_field in PROVIDER_REQUIRED_FIELDS
        return ProviderFieldResolution(
            canonical_field=canonical_field,
            kind=kind,
            field_status=FIELD_STATUS_MISSING,
            source_status=SOURCE_STATUS_MISSING,
            provider_neutral_present=False,
            legacy_alias_present=False,
            legacy_alias_env_name=None,
            safe_label_value=None,
            raw_value_length=None,
            failure_reason=(
                FAILURE_REASON_MISSING_REQUIRED_FIELD
                if is_required
                else None
            ),
        )

    # Case 2: both present and they conflict.
    if (
        provider_neutral_present
        and legacy_alias_present
        and provider_neutral_value != legacy_value
    ):
        return ProviderFieldResolution(
            canonical_field=canonical_field,
            kind=kind,
            field_status=FIELD_STATUS_CONFLICT,
            source_status=SOURCE_STATUS_BOTH_CONFLICT,
            provider_neutral_present=True,
            legacy_alias_present=True,
            legacy_alias_env_name=legacy_env_name,
            safe_label_value=None,
            raw_value_length=None,
            failure_reason=FAILURE_REASON_CONFLICTING_PROVIDER_ENV_VALUES,
        )

    # Case 3: at least one is present; pick the resolved value.
    if provider_neutral_present and legacy_alias_present:
        # Both present and identical.
        resolved_value: str = provider_neutral_value  # type: ignore[assignment]
        source_status = SOURCE_STATUS_BOTH_SAME
    elif provider_neutral_present:
        resolved_value = provider_neutral_value  # type: ignore[assignment]
        source_status = SOURCE_STATUS_PROVIDER_NEUTRAL
    else:
        resolved_value = legacy_value  # type: ignore[assignment]
        source_status = SOURCE_STATUS_LEGACY_ALIAS

    safe_label_value, field_status, failure_reason = _maybe_validate_label(
        canonical_field, resolved_value
    )

    # SECRET fields never expose safe_label_value (defensive
    # belt-and-braces: the validator returns ``None`` for SECRET
    # fields, but re-assert here so a future regression cannot
    # leak by widening the validator alone).
    if kind == FIELD_KIND_SECRET:
        safe_label_value = None

    return ProviderFieldResolution(
        canonical_field=canonical_field,
        kind=kind,
        field_status=field_status,
        source_status=source_status,
        provider_neutral_present=provider_neutral_present,
        legacy_alias_present=legacy_alias_present,
        legacy_alias_env_name=legacy_env_name,
        safe_label_value=safe_label_value,
        raw_value_length=len(resolved_value),
        failure_reason=failure_reason,
    )


# ---------------------------------------------------------------------------
# Bulk resolution
# ---------------------------------------------------------------------------


def resolve_provider_neutral_config(
    env: Mapping[str, str],
) -> ProviderNeutralResolution:
    """Resolve every Stage 28.1 canonical field against ``env``.

    Pure: ``env`` is the only input; no ``os.environ`` access.
    Returns a ``ProviderNeutralResolution`` bundle.
    """
    field_records: list[ProviderFieldResolution] = []
    for canonical_field in PROVIDER_FIELD_VALUES:
        field_records.append(
            resolve_canonical_field(canonical_field, env)
        )

    missing_required: list[str] = []
    conflicting: list[str] = []
    invalid: list[str] = []
    legacy_used = False
    for record in field_records:
        if (
            record.canonical_field in PROVIDER_REQUIRED_FIELDS
            and record.field_status == FIELD_STATUS_MISSING
        ):
            missing_required.append(record.canonical_field)
        if record.field_status == FIELD_STATUS_CONFLICT:
            conflicting.append(record.canonical_field)
        if record.field_status == FIELD_STATUS_INVALID:
            invalid.append(record.canonical_field)
        if record.source_status == SOURCE_STATUS_LEGACY_ALIAS:
            legacy_used = True

    return ProviderNeutralResolution(
        fields=tuple(field_records),
        missing_required_fields=tuple(missing_required),
        conflicting_fields=tuple(conflicting),
        invalid_fields=tuple(invalid),
        legacy_alias_used=legacy_used,
    )


__all__ = (
    "resolve_canonical_field",
    "resolve_provider_neutral_config",
)
