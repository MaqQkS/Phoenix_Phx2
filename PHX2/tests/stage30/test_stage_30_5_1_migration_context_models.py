"""Stage 30.5.1 migration-context model-layer tests.

Pure-Python tests over the committed Stage 30.5.0 closed-set
vocabularies (migration_status / migration_basis / source_status),
the Stage 30.5.1 source-reason / display closed sets, and the
immutable record / projection shapes with construction-time
validation. No live network, no env, no Discord, no provider call.
"""

from __future__ import annotations

import dataclasses
from typing import Tuple

from PHX2.stage30.stage30_5_migration_context_models import (
    FORBIDDEN_RECORD_FIELD_NAMES,
    MIGRATION_BASIS_EVIDENCE_PARTIAL,
    MIGRATION_BASIS_NONE,
    MIGRATION_BASIS_ON_CHAIN_EVENT,
    MIGRATION_BASIS_VALUES,
    MIGRATION_DISPLAY_KNOWN,
    MIGRATION_DISPLAY_UNKNOWN,
    MIGRATION_DISPLAY_UNVERIFIED,
    MIGRATION_DISPLAY_VALUES,
    MIGRATION_STATUS_KNOWN,
    MIGRATION_STATUS_UNKNOWN,
    MIGRATION_STATUS_UNVERIFIED,
    MIGRATION_STATUS_VALUES,
    SOURCE_REASON_EVIDENCE_INVALID,
    SOURCE_REASON_EVIDENCE_PARTIAL,
    SOURCE_REASON_SOURCE_ERROR,
    SOURCE_REASON_SOURCE_NOT_CONFIGURED,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_REASON_SOURCE_STALE,
    SOURCE_REASON_SOURCE_UNAVAILABLE,
    SOURCE_REASON_VALUES,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_STALE,
    SOURCE_STATUS_UNAVAILABLE,
    SOURCE_STATUS_VALUES,
    STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
    STAGE30_5_1_MINOR_VERSION,
    Stage30_5MigrationContextError,
    Stage30_5MigrationContextProjection,
    Stage30_5MigrationContextRecord,
    display_text_for_status,
    is_forbidden_record_field_name,
    is_migration_basis_value,
    is_migration_display_value,
    is_migration_status_value,
    is_safe_iso8601_utc,
    is_safe_source_label,
    is_safe_token_label,
    is_source_reason_value,
    is_source_status_value,
    projection_field_names,
    record_field_names,
)


_VALID_TS: str = "2026-05-29T00:02:00Z"
_VALID_EVENT_TS: str = "2026-05-29T00:00:00Z"


# ---------------------------------------------------------------------------
# Valid-record / valid-projection kwargs helpers
# ---------------------------------------------------------------------------


def _valid_record_kwargs(**overrides) -> dict:
    base = dict(
        schema_version=STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
        token_label="ABcd...WXyz",
        migration_status=MIGRATION_STATUS_KNOWN,
        migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
        migration_event_time_utc=_VALID_EVENT_TS,
        migration_age_seconds=120,
        source_label="stage29_5_migration_evidence",
        source_status=SOURCE_STATUS_PRESENT,
        source_reason=SOURCE_REASON_SOURCE_PRESENT,
        runtime_consumable=False,
        observed_at_utc=_VALID_TS,
    )
    base.update(overrides)
    return base


def _valid_projection_kwargs(**overrides) -> dict:
    base = dict(
        schema_version=STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION,
        migration_display_text=MIGRATION_DISPLAY_KNOWN,
        migration_status=MIGRATION_STATUS_KNOWN,
        migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
        source_status=SOURCE_STATUS_PRESENT,
        source_reason=SOURCE_REASON_SOURCE_PRESENT,
        source_label="stage29_5_migration_evidence",
        runtime_consumable=False,
    )
    base.update(overrides)
    return base


def _expect_record_error(reason: str, **overrides) -> None:
    try:
        Stage30_5MigrationContextRecord(**_valid_record_kwargs(**overrides))
    except Stage30_5MigrationContextError as exc:
        assert exc.reason == reason, (
            f"expected reason {reason!r}, got {exc.reason!r}"
        )
    else:
        raise AssertionError(
            f"expected Stage30_5MigrationContextError({reason!r})"
        )


def _expect_projection_error(reason: str, **overrides) -> None:
    try:
        Stage30_5MigrationContextProjection(
            **_valid_projection_kwargs(**overrides)
        )
    except Stage30_5MigrationContextError as exc:
        assert exc.reason == reason, (
            f"expected reason {reason!r}, got {exc.reason!r}"
        )
    else:
        raise AssertionError(
            f"expected Stage30_5MigrationContextError({reason!r})"
        )


# ---------------------------------------------------------------------------
# Version + schema version
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_5_1_MINOR_VERSION == "30.5.1"


def test_schema_version_pinned() -> None:
    assert (
        STAGE30_5_1_MIGRATION_CONTEXT_SCHEMA_VERSION
        == "stage30_5_1_v0_migration_context"
    )


# ---------------------------------------------------------------------------
# migration_status closed set (committed Stage 30.5.0 contract)
# ---------------------------------------------------------------------------


def test_migration_status_closed_set_pinned() -> None:
    assert MIGRATION_STATUS_KNOWN == "KNOWN"
    assert MIGRATION_STATUS_UNVERIFIED == "UNVERIFIED"
    assert MIGRATION_STATUS_UNKNOWN == "UNKNOWN"
    assert MIGRATION_STATUS_VALUES == (
        MIGRATION_STATUS_KNOWN,
        MIGRATION_STATUS_UNVERIFIED,
        MIGRATION_STATUS_UNKNOWN,
    )


def test_is_migration_status_value_accepts_each_token() -> None:
    for token in MIGRATION_STATUS_VALUES:
        assert is_migration_status_value(token)


def test_is_migration_status_value_rejects_synonyms_and_nontypes() -> None:
    assert not is_migration_status_value("known")
    assert not is_migration_status_value("VERIFIED")
    assert not is_migration_status_value("")
    assert not is_migration_status_value(None)
    assert not is_migration_status_value(0)
    assert not is_migration_status_value(False)
    assert not is_migration_status_value(b"KNOWN")


# ---------------------------------------------------------------------------
# migration_basis closed set (committed Stage 30.5.0 contract)
# ---------------------------------------------------------------------------


def test_migration_basis_closed_set_pinned() -> None:
    assert MIGRATION_BASIS_ON_CHAIN_EVENT == "ON_CHAIN_EVENT"
    assert MIGRATION_BASIS_EVIDENCE_PARTIAL == "EVIDENCE_PARTIAL"
    assert MIGRATION_BASIS_NONE == "NONE"
    assert MIGRATION_BASIS_VALUES == (
        MIGRATION_BASIS_ON_CHAIN_EVENT,
        MIGRATION_BASIS_EVIDENCE_PARTIAL,
        MIGRATION_BASIS_NONE,
    )


def test_migration_basis_omits_deferred_richer_tokens() -> None:
    """The richer Stage 29.5 basis distinctions stay deferred; they
    must NOT be in the Stage 30.5.1 closed set.
    """
    for deferred in (
        "ON_CHAIN_MIGRATION_EVENT",
        "TRUSTED_MIGRATION_ARTIFACT",
        "EVIDENCE_PRESENT_UNVERIFIED",
        "SOURCE_MISSING",
        "SOURCE_INVALID",
        "SOURCE_CONFLICTING",
    ):
        assert deferred not in MIGRATION_BASIS_VALUES


def test_is_migration_basis_value_accepts_each_token() -> None:
    for token in MIGRATION_BASIS_VALUES:
        assert is_migration_basis_value(token)


def test_is_migration_basis_value_rejects_synonyms() -> None:
    assert not is_migration_basis_value("on_chain_event")
    assert not is_migration_basis_value("NONE_")
    assert not is_migration_basis_value(None)


# ---------------------------------------------------------------------------
# source_status closed set (UNAVAILABLE / PRESENT / ERROR / STALE)
# ---------------------------------------------------------------------------


def test_source_status_closed_set_pinned() -> None:
    assert SOURCE_STATUS_UNAVAILABLE == "UNAVAILABLE"
    assert SOURCE_STATUS_PRESENT == "PRESENT"
    assert SOURCE_STATUS_ERROR == "ERROR"
    assert SOURCE_STATUS_STALE == "STALE"
    assert SOURCE_STATUS_VALUES == (
        SOURCE_STATUS_UNAVAILABLE,
        SOURCE_STATUS_PRESENT,
        SOURCE_STATUS_ERROR,
        SOURCE_STATUS_STALE,
    )


def test_source_status_includes_stale() -> None:
    """Stage 30.5.1 source_status conforms to the committed Stage
    30.5.0 four-token set: STALE IS a valid source_status (it is a
    source-status token only; there is no Mig: Stale display token).
    """
    assert "STALE" in SOURCE_STATUS_VALUES
    assert len(SOURCE_STATUS_VALUES) == 4


def test_is_source_status_value_accepts_each_token() -> None:
    for token in SOURCE_STATUS_VALUES:
        assert is_source_status_value(token)


def test_is_source_status_value_rejects_synonyms() -> None:
    assert not is_source_status_value("present")
    assert not is_source_status_value("stale")  # lowercase is not the token
    assert not is_source_status_value("MISSING")
    assert not is_source_status_value(None)


# ---------------------------------------------------------------------------
# source_reason closed set
# ---------------------------------------------------------------------------


def test_source_reason_closed_set_pinned() -> None:
    assert SOURCE_REASON_SOURCE_PRESENT == "SOURCE_PRESENT"
    assert SOURCE_REASON_EVIDENCE_PARTIAL == "EVIDENCE_PARTIAL"
    assert SOURCE_REASON_EVIDENCE_INVALID == "EVIDENCE_INVALID"
    assert SOURCE_REASON_SOURCE_UNAVAILABLE == "SOURCE_UNAVAILABLE"
    assert SOURCE_REASON_SOURCE_NOT_CONFIGURED == "SOURCE_NOT_CONFIGURED"
    assert SOURCE_REASON_SOURCE_ERROR == "SOURCE_ERROR"
    assert SOURCE_REASON_SOURCE_STALE == "SOURCE_STALE"


def test_source_reason_values_contains_all_tokens() -> None:
    assert set(SOURCE_REASON_VALUES) == {
        SOURCE_REASON_SOURCE_PRESENT,
        SOURCE_REASON_EVIDENCE_PARTIAL,
        SOURCE_REASON_EVIDENCE_INVALID,
        SOURCE_REASON_SOURCE_UNAVAILABLE,
        SOURCE_REASON_SOURCE_NOT_CONFIGURED,
        SOURCE_REASON_SOURCE_ERROR,
        SOURCE_REASON_SOURCE_STALE,
    }


def test_source_reason_omits_deferred_richer_tokens() -> None:
    for deferred in (
        "SOURCE_MISSING",
        "SOURCE_INVALID",
        "SOURCE_CONFLICTING",
        "AMBIGUOUS_EVIDENCE",
        "UNSUPPORTED_STATUS",
    ):
        assert deferred not in SOURCE_REASON_VALUES


def test_is_source_reason_value_accepts_each_token() -> None:
    for token in SOURCE_REASON_VALUES:
        assert is_source_reason_value(token)


def test_is_source_reason_value_rejects_synonyms() -> None:
    assert not is_source_reason_value("present")
    assert not is_source_reason_value("")
    assert not is_source_reason_value(None)


# ---------------------------------------------------------------------------
# migration display tokens + status -> display mapping
# ---------------------------------------------------------------------------


def test_migration_display_closed_set_pinned() -> None:
    assert MIGRATION_DISPLAY_KNOWN == "Known"
    assert MIGRATION_DISPLAY_UNVERIFIED == "Unverified"
    assert MIGRATION_DISPLAY_UNKNOWN == "Unknown"
    assert MIGRATION_DISPLAY_VALUES == (
        MIGRATION_DISPLAY_KNOWN,
        MIGRATION_DISPLAY_UNVERIFIED,
        MIGRATION_DISPLAY_UNKNOWN,
    )


def test_display_does_not_carry_fresh_or_stale() -> None:
    for deferred in ("Fresh", "Stale"):
        assert deferred not in MIGRATION_DISPLAY_VALUES


def test_is_migration_display_value() -> None:
    for token in MIGRATION_DISPLAY_VALUES:
        assert is_migration_display_value(token)
    assert not is_migration_display_value("known")
    assert not is_migration_display_value(None)


def test_display_text_for_status_maps_each_status() -> None:
    assert (
        display_text_for_status(MIGRATION_STATUS_KNOWN)
        == MIGRATION_DISPLAY_KNOWN
    )
    assert (
        display_text_for_status(MIGRATION_STATUS_UNVERIFIED)
        == MIGRATION_DISPLAY_UNVERIFIED
    )
    assert (
        display_text_for_status(MIGRATION_STATUS_UNKNOWN)
        == MIGRATION_DISPLAY_UNKNOWN
    )


def test_display_text_for_status_falls_back_to_unknown() -> None:
    assert display_text_for_status("BOGUS") == MIGRATION_DISPLAY_UNKNOWN
    assert display_text_for_status(None) == MIGRATION_DISPLAY_UNKNOWN
    assert display_text_for_status("") == MIGRATION_DISPLAY_UNKNOWN
    assert display_text_for_status(123) == MIGRATION_DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# Safe-shape gates
# ---------------------------------------------------------------------------


def test_is_safe_iso8601_utc() -> None:
    assert is_safe_iso8601_utc("2026-05-29T00:00:00Z")
    assert is_safe_iso8601_utc("2026-05-29T00:00:00.123Z")
    assert is_safe_iso8601_utc("2026-05-29T00:00:00+00:00")
    assert not is_safe_iso8601_utc("2026-05-29 00:00:00")
    assert not is_safe_iso8601_utc("not-a-time")
    assert not is_safe_iso8601_utc(None)


def test_is_safe_token_label_rejects_full_mint() -> None:
    assert is_safe_token_label("ABcd...WXyz")
    assert is_safe_token_label("ABcd…WXyz")  # ellipsis form
    assert is_safe_token_label("WSOL")
    # A full base58 mint is 32+ chars and must be cut off.
    assert not is_safe_token_label(
        "So11111111111111111111111111111111111111112"
    )
    assert not is_safe_token_label("abc/def")
    assert not is_safe_token_label(None)


def test_is_safe_source_label() -> None:
    assert is_safe_source_label("stage29_5_migration_evidence")
    assert is_safe_source_label("birdeye_token_overview")
    assert not is_safe_source_label("has space")
    assert not is_safe_source_label("has/slash")
    assert not is_safe_source_label(None)


# ---------------------------------------------------------------------------
# Record shape
# ---------------------------------------------------------------------------


_EXPECTED_RECORD_FIELDS: Tuple[str, ...] = (
    "schema_version",
    "token_label",
    "migration_status",
    "migration_basis",
    "migration_event_time_utc",
    "migration_age_seconds",
    "source_label",
    "source_status",
    "source_reason",
    "runtime_consumable",
    "observed_at_utc",
)


def test_record_has_exactly_expected_fields() -> None:
    assert record_field_names() == _EXPECTED_RECORD_FIELDS


def test_record_carries_no_ath_or_net_fields() -> None:
    names = record_field_names()
    joined = " ".join(names).lower()
    assert "ath" not in joined
    assert "net" not in joined
    # And no numeric migration market-cap value field.
    assert "migration_mc" not in joined
    assert "market_cap" not in joined


# ---------------------------------------------------------------------------
# Valid KNOWN / UNVERIFIED / UNKNOWN records
# ---------------------------------------------------------------------------


def test_valid_known_record() -> None:
    rec = Stage30_5MigrationContextRecord(
        **_valid_record_kwargs(
            migration_status=MIGRATION_STATUS_KNOWN,
            migration_basis=MIGRATION_BASIS_ON_CHAIN_EVENT,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_SOURCE_PRESENT,
        )
    )
    assert rec.migration_status == MIGRATION_STATUS_KNOWN
    assert rec.migration_basis == MIGRATION_BASIS_ON_CHAIN_EVENT
    assert rec.runtime_consumable is False


def test_valid_unverified_record() -> None:
    rec = Stage30_5MigrationContextRecord(
        **_valid_record_kwargs(
            migration_status=MIGRATION_STATUS_UNVERIFIED,
            migration_basis=MIGRATION_BASIS_EVIDENCE_PARTIAL,
            source_status=SOURCE_STATUS_PRESENT,
            source_reason=SOURCE_REASON_EVIDENCE_PARTIAL,
        )
    )
    assert rec.migration_status == MIGRATION_STATUS_UNVERIFIED
    assert rec.migration_basis == MIGRATION_BASIS_EVIDENCE_PARTIAL


def test_valid_unknown_record() -> None:
    rec = Stage30_5MigrationContextRecord(
        **_valid_record_kwargs(
            token_label=None,
            migration_status=MIGRATION_STATUS_UNKNOWN,
            migration_basis=MIGRATION_BASIS_NONE,
            migration_event_time_utc=None,
            migration_age_seconds=None,
            source_label=None,
            source_status=SOURCE_STATUS_UNAVAILABLE,
            source_reason=SOURCE_REASON_SOURCE_NOT_CONFIGURED,
        )
    )
    assert rec.migration_status == MIGRATION_STATUS_UNKNOWN
    assert rec.migration_basis == MIGRATION_BASIS_NONE
    assert rec.token_label is None
    assert rec.migration_event_time_utc is None
    assert rec.migration_age_seconds is None
    assert rec.source_label is None


# ---------------------------------------------------------------------------
# Invalid closed-set values rejected at construction
# ---------------------------------------------------------------------------


def test_invalid_status_rejected() -> None:
    _expect_record_error(
        "MIGRATION_STATUS_INVALID", migration_status="VERIFIED"
    )
    _expect_record_error(
        "MIGRATION_STATUS_INVALID", migration_status="known"
    )


def test_invalid_basis_rejected() -> None:
    _expect_record_error(
        "MIGRATION_BASIS_INVALID", migration_basis="ON_CHAIN_MIGRATION_EVENT"
    )
    _expect_record_error(
        "MIGRATION_BASIS_INVALID", migration_basis="TRUSTED_MIGRATION_ARTIFACT"
    )


def test_invalid_source_status_rejected() -> None:
    _expect_record_error(
        "SOURCE_STATUS_INVALID", source_status="MISSING"
    )
    _expect_record_error(
        "SOURCE_STATUS_INVALID", source_status="present"
    )


def test_stale_source_status_accepted() -> None:
    """STALE conforms to the committed Stage 30.5.0 four-token
    source_status set and must construct without error.
    """
    assert is_source_status_value(SOURCE_STATUS_STALE)
    rec = Stage30_5MigrationContextRecord(
        **_valid_record_kwargs(
            migration_status=MIGRATION_STATUS_UNKNOWN,
            migration_basis=MIGRATION_BASIS_NONE,
            source_status=SOURCE_STATUS_STALE,
            source_reason=SOURCE_REASON_SOURCE_STALE,
        )
    )
    assert rec.source_status == SOURCE_STATUS_STALE
    assert rec.source_reason == SOURCE_REASON_SOURCE_STALE


def test_invalid_source_reason_rejected() -> None:
    _expect_record_error(
        "SOURCE_REASON_INVALID", source_reason="AMBIGUOUS_EVIDENCE"
    )
    _expect_record_error(
        "SOURCE_REASON_INVALID", source_reason="SOURCE_CONFLICTING"
    )


# ---------------------------------------------------------------------------
# Safe token label behavior at construction
# ---------------------------------------------------------------------------


def test_safe_token_label_accepted_and_full_mint_rejected() -> None:
    rec = Stage30_5MigrationContextRecord(
        **_valid_record_kwargs(token_label="ABcd...WXyz")
    )
    assert rec.token_label == "ABcd...WXyz"
    # None is accepted (degraded / redacted away).
    rec_none = Stage30_5MigrationContextRecord(
        **_valid_record_kwargs(token_label=None)
    )
    assert rec_none.token_label is None
    # A full base58 mint is rejected (never stored).
    _expect_record_error(
        "TOKEN_LABEL_UNSAFE_SHAPE",
        token_label="So11111111111111111111111111111111111111112",
    )
    _expect_record_error(
        "TOKEN_LABEL_UNSAFE_SHAPE", token_label="bad/label"
    )


def test_unsafe_source_label_rejected() -> None:
    _expect_record_error(
        "SOURCE_LABEL_UNSAFE_SHAPE", source_label="has space"
    )


# ---------------------------------------------------------------------------
# runtime_consumable rules
# ---------------------------------------------------------------------------


def test_runtime_consumable_false_accepted_true_rejected() -> None:
    """Stage 30.5.1 is offline-only: a record MUST be False;
    True is rejected at construction (not silently normalized).
    """
    rec_false = Stage30_5MigrationContextRecord(
        **_valid_record_kwargs(runtime_consumable=False)
    )
    assert rec_false.runtime_consumable is False
    _expect_record_error(
        "RUNTIME_CONSUMABLE_MUST_BE_FALSE", runtime_consumable=True
    )


def test_runtime_consumable_non_bool_rejected() -> None:
    _expect_record_error(
        "RUNTIME_CONSUMABLE_NOT_BOOL", runtime_consumable=1
    )
    _expect_record_error(
        "RUNTIME_CONSUMABLE_NOT_BOOL", runtime_consumable="False"
    )
    _expect_record_error(
        "RUNTIME_CONSUMABLE_NOT_BOOL", runtime_consumable=None
    )


def test_every_valid_record_has_runtime_consumable_false() -> None:
    """Construction is the only gate; since True is rejected, every
    record that constructs has runtime_consumable False.
    """
    rec = Stage30_5MigrationContextRecord(**_valid_record_kwargs())
    assert rec.runtime_consumable is False


# ---------------------------------------------------------------------------
# Optional migration_event_time / migration_age handling
# ---------------------------------------------------------------------------


def test_optional_event_time_and_age_accept_none_and_valid() -> None:
    rec = Stage30_5MigrationContextRecord(
        **_valid_record_kwargs(
            migration_event_time_utc=None, migration_age_seconds=None
        )
    )
    assert rec.migration_event_time_utc is None
    assert rec.migration_age_seconds is None

    rec2 = Stage30_5MigrationContextRecord(
        **_valid_record_kwargs(
            migration_event_time_utc=_VALID_EVENT_TS,
            migration_age_seconds=0,
        )
    )
    assert rec2.migration_event_time_utc == _VALID_EVENT_TS
    assert rec2.migration_age_seconds == 0


def test_bad_event_time_rejected() -> None:
    _expect_record_error(
        "MIGRATION_EVENT_TIME_UNSAFE_SHAPE",
        migration_event_time_utc="2026/05/29",
    )


def test_bad_age_rejected() -> None:
    _expect_record_error(
        "MIGRATION_AGE_SECONDS_INVALID", migration_age_seconds=-1
    )
    _expect_record_error(
        "MIGRATION_AGE_SECONDS_INVALID", migration_age_seconds=1.5
    )
    # bool must not slip through as an age (bool is an int subclass).
    _expect_record_error(
        "MIGRATION_AGE_SECONDS_INVALID", migration_age_seconds=True
    )


def test_bad_observed_at_and_schema_version_rejected() -> None:
    _expect_record_error(
        "OBSERVED_AT_UTC_UNSAFE_SHAPE", observed_at_utc="bad"
    )
    _expect_record_error("SCHEMA_VERSION_INVALID", schema_version="")
    _expect_record_error("SCHEMA_VERSION_INVALID", schema_version=None)


# ---------------------------------------------------------------------------
# No extra fields admitted (no raw event / source refs)
# ---------------------------------------------------------------------------


def test_record_rejects_extra_fields() -> None:
    for extra in (
        "migration_event_id",
        "source_event_ref",
        "migration_signature",
        "raw_payload",
    ):
        try:
            Stage30_5MigrationContextRecord(
                **_valid_record_kwargs(**{extra: "x"})
            )
        except TypeError:
            pass
        else:
            raise AssertionError(
                f"record must not admit extra field {extra!r}"
            )


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_record_is_frozen() -> None:
    rec = Stage30_5MigrationContextRecord(**_valid_record_kwargs())
    try:
        rec.migration_status = MIGRATION_STATUS_UNKNOWN  # type: ignore[misc]
    except (dataclasses.FrozenInstanceError, AttributeError):
        pass
    else:
        raise AssertionError(
            "Stage30_5MigrationContextRecord must be immutable"
        )


# ---------------------------------------------------------------------------
# Projection shape + validation
# ---------------------------------------------------------------------------


_EXPECTED_PROJECTION_FIELDS: Tuple[str, ...] = (
    "schema_version",
    "migration_display_text",
    "migration_status",
    "migration_basis",
    "source_status",
    "source_reason",
    "source_label",
    "runtime_consumable",
)


def test_projection_has_exactly_expected_fields() -> None:
    assert projection_field_names() == _EXPECTED_PROJECTION_FIELDS


def test_projection_carries_no_age_time_token_ath_net_fields() -> None:
    joined = " ".join(projection_field_names()).lower()
    assert "age" not in joined
    assert "event_time" not in joined
    assert "token_label" not in joined
    assert "ath" not in joined
    assert "net" not in joined


def test_valid_projection_constructs() -> None:
    proj = Stage30_5MigrationContextProjection(
        **_valid_projection_kwargs()
    )
    assert proj.migration_display_text == MIGRATION_DISPLAY_KNOWN
    assert proj.runtime_consumable is False


def test_projection_invalid_display_rejected() -> None:
    _expect_projection_error(
        "MIGRATION_DISPLAY_INVALID", migration_display_text="known"
    )
    _expect_projection_error(
        "MIGRATION_DISPLAY_INVALID", migration_display_text="Fresh"
    )


def test_projection_invalid_closed_sets_rejected() -> None:
    _expect_projection_error(
        "MIGRATION_STATUS_INVALID", migration_status="VERIFIED"
    )
    _expect_projection_error(
        "SOURCE_STATUS_INVALID", source_status="MISSING"
    )
    _expect_projection_error(
        "RUNTIME_CONSUMABLE_NOT_BOOL", runtime_consumable=1
    )


def test_projection_runtime_consumable_true_rejected() -> None:
    """The projection is offline-only too: runtime_consumable True is
    rejected at construction (the adapter always emits False).
    """
    _expect_projection_error(
        "RUNTIME_CONSUMABLE_MUST_BE_FALSE", runtime_consumable=True
    )


def test_projection_is_frozen() -> None:
    proj = Stage30_5MigrationContextProjection(
        **_valid_projection_kwargs()
    )
    try:
        proj.migration_display_text = "Unknown"  # type: ignore[misc]
    except (dataclasses.FrozenInstanceError, AttributeError):
        pass
    else:
        raise AssertionError(
            "Stage30_5MigrationContextProjection must be immutable"
        )


# ---------------------------------------------------------------------------
# Forbidden field-name guard
# ---------------------------------------------------------------------------


def test_no_record_field_matches_forbidden_vocabulary() -> None:
    for name in record_field_names():
        assert not is_forbidden_record_field_name(name), (
            f"record field {name!r} is on the forbidden-name vocabulary"
        )


def test_no_projection_field_matches_forbidden_vocabulary() -> None:
    for name in projection_field_names():
        assert not is_forbidden_record_field_name(name), (
            f"projection field {name!r} is on the forbidden vocabulary"
        )


def test_forbidden_field_name_guard_matches_substrings() -> None:
    for needle in FORBIDDEN_RECORD_FIELD_NAMES:
        assert is_forbidden_record_field_name(needle)
        assert is_forbidden_record_field_name(f"prefix_{needle}")
        assert is_forbidden_record_field_name(f"{needle}_suffix")


def test_forbidden_field_name_guard_non_strings_return_false() -> None:
    assert not is_forbidden_record_field_name(None)
    assert not is_forbidden_record_field_name(123)
    assert not is_forbidden_record_field_name(b"web" + b"hook")
    assert not is_forbidden_record_field_name([])


def test_forbidden_field_name_guard_is_case_insensitive() -> None:
    assert is_forbidden_record_field_name("A" + "PI_KEY")
    assert is_forbidden_record_field_name("B" + "EARER")


def test_forbidden_vocabulary_includes_migration_audit_ids() -> None:
    """The Stage 30.5.0 §6 audit identifiers must be on the
    forbidden vocabulary so a future refactor cannot add them.
    """
    assert is_forbidden_record_field_name("migration_event_id")
    assert is_forbidden_record_field_name("source_event_ref")
    assert is_forbidden_record_field_name("migration_signature")
    assert is_forbidden_record_field_name("raw_capture_ref")


# ---------------------------------------------------------------------------
# Module-local exception
# ---------------------------------------------------------------------------


def test_module_exception_carries_reason_token() -> None:
    err = Stage30_5MigrationContextError("MIGRATION_STATUS_INVALID")
    assert err.reason == "MIGRATION_STATUS_INVALID"
    assert "MIGRATION_STATUS_INVALID" in str(err)
