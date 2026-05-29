"""Stage 30.5.3 Stage 29.5 migration-evidence bridge unit tests.

Pins the Stage 30.5.3 offline bridge
(``stage30_5_stage29_migration_bridge``) that converts a sanitized Stage
29.5 migration-evidence summary into the Stage 30.5 migration-context
contract:

  * ``project_stage29_migration_evidence_to_stage30_record`` maps the
    Stage 29.5 ``measurement_status`` (+ ``warnings`` / ``redaction_status``)
    onto the Stage 30.5.1 closed sets (migration_status / migration_basis /
    source_status / source_reason) per the documented table.
  * confirmed (``COMPLETE``)            -> KNOWN / ON_CHAIN_EVENT / PRESENT
                                           -> ``Mig: Known``
  * partial (``PARTIAL_MIGRATION_PRESENT``, no stale)
                                        -> UNVERIFIED / EVIDENCE_PARTIAL /
                                           PRESENT -> ``Mig: Unverified``
  * stale partial                       -> UNKNOWN / NONE / STALE
                                           -> ``Mig: Unknown`` (no Stale word)
  * missing / invalid / conflicting     -> UNKNOWN / NONE / UNAVAILABLE|ERROR
                                           -> ``Mig: Unknown``
  * malformed / None / unrecognized     -> UNKNOWN / NONE / ERROR|UNAVAILABLE
                                           -> ``Mig: Unknown``
  * non-redaction-safe summary          -> UNKNOWN / NONE / ERROR
                                           -> ``Mig: Unknown``
  * the bridge consumes a duck-typed shape (no Stage 29 import required),
    never echoes the token mint into the record, never carries a raw
    identifier, and never emits ``runtime_consumable=True``.

Fake / offline only. No live provider call, no Discord send, no network,
no env read, no filesystem write. Stdlib + pytest only.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from typing import Optional

from PHX2.stage30.stage30_5_compact_migration_runtime_adapter import (
    Stage30_5_2MigrationDisplayResolver,
    resolve_migration_display_text,
)
from PHX2.stage30.stage30_5_migration_context_adapter import (
    project_migration_context,
)
from PHX2.stage30.stage30_5_migration_context_models import (
    MIGRATION_BASIS_EVIDENCE_PARTIAL,
    MIGRATION_BASIS_NONE,
    MIGRATION_BASIS_ON_CHAIN_EVENT,
    MIGRATION_DISPLAY_KNOWN,
    MIGRATION_DISPLAY_UNKNOWN,
    MIGRATION_DISPLAY_UNVERIFIED,
    MIGRATION_STATUS_KNOWN,
    MIGRATION_STATUS_UNKNOWN,
    MIGRATION_STATUS_UNVERIFIED,
    SOURCE_REASON_EVIDENCE_INVALID,
    SOURCE_REASON_EVIDENCE_PARTIAL,
    SOURCE_REASON_SOURCE_ERROR,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_REASON_SOURCE_STALE,
    SOURCE_REASON_SOURCE_UNAVAILABLE,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_STALE,
    SOURCE_STATUS_UNAVAILABLE,
    Stage30_5MigrationContextRecord,
    is_forbidden_record_field_name,
    is_safe_source_label,
    projection_field_names,
    record_field_names,
)
from PHX2.stage30.stage30_5_stage29_migration_bridge import (
    STAGE29_5_MEASUREMENT_STATUS_COMPLETE,
    STAGE29_5_MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    STAGE29_5_MEASUREMENT_STATUS_INVALID_MIGRATION,
    STAGE29_5_MEASUREMENT_STATUS_MISSING_MIGRATION,
    STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    STAGE29_5_RECOGNIZED_MEASUREMENT_STATUS_VALUES,
    STAGE29_5_REDACTION_STATUS_SAFE,
    STAGE29_5_WARNING_MIGRATION_STALE,
    STAGE30_5_3_MINOR_VERSION,
    STAGE30_5_3_SOURCE_LABEL,
    Stage30_5_3SanitizedStage29MigrationEvidence,
    Stage30_5_3Stage29MigrationEvidenceBridge,
    build_stage30_migration_resolver_from_stage29_artifact,
    project_stage29_migration_evidence_to_stage30_record,
)


# ---------------------------------------------------------------------------
# Locked constants + helpers
# ---------------------------------------------------------------------------


_OBS_TS: str = "2026-05-29T00:00:00Z"
_TOKEN_MINT: str = "FakeMintPhx2ForStage305_3Base582222222222222"


def _evidence(
    measurement_status: Optional[str],
    *,
    warnings: tuple = (),
    redaction_status: Optional[str] = STAGE29_5_REDACTION_STATUS_SAFE,
) -> Stage30_5_3SanitizedStage29MigrationEvidence:
    return Stage30_5_3SanitizedStage29MigrationEvidence(
        measurement_status=measurement_status,
        warnings=warnings,
        redaction_status=redaction_status,
    )


def _project(
    evidence: object,
    observed_at_utc: object = _OBS_TS,
) -> Optional[Stage30_5MigrationContextRecord]:
    return project_stage29_migration_evidence_to_stage30_record(
        evidence, observed_at_utc
    )


def _display_via_resolver(
    evidence: object,
    observed_at_utc: Optional[str] = _OBS_TS,
) -> str:
    resolver = build_stage30_migration_resolver_from_stage29_artifact(
        evidence=evidence,
    )
    return resolver.resolve_display_text(
        token_mint=_TOKEN_MINT,
        observed_at_utc=observed_at_utc,
    )


# ---------------------------------------------------------------------------
# 0. Version + documented Stage 29.5 vocabulary mirror
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_5_3_MINOR_VERSION == "30.5.3"


def test_recognized_measurement_status_values_documented() -> None:
    assert STAGE29_5_RECOGNIZED_MEASUREMENT_STATUS_VALUES == (
        "COMPLETE",
        "PARTIAL_MIGRATION_PRESENT",
        "MISSING_MIGRATION",
        "INVALID_MIGRATION",
        "CONFLICTING_MIGRATION",
    )
    assert STAGE29_5_WARNING_MIGRATION_STALE == "MIGRATION_STALE"
    assert STAGE29_5_REDACTION_STATUS_SAFE == "SAFE"


def test_source_label_is_safe_shape() -> None:
    assert STAGE30_5_3_SOURCE_LABEL == "stage29_5_migration_evidence"
    assert is_safe_source_label(STAGE30_5_3_SOURCE_LABEL)


# ---------------------------------------------------------------------------
# 1. Confirmed (COMPLETE) -> KNOWN / ON_CHAIN_EVENT / PRESENT -> Known
# ---------------------------------------------------------------------------


def test_complete_maps_to_known_present_on_chain_event() -> None:
    record = _project(_evidence(STAGE29_5_MEASUREMENT_STATUS_COMPLETE))
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_KNOWN
    assert record.migration_basis == MIGRATION_BASIS_ON_CHAIN_EVENT
    assert record.source_status == SOURCE_STATUS_PRESENT
    assert record.source_reason == SOURCE_REASON_SOURCE_PRESENT
    assert record.runtime_consumable is False
    assert record.token_label is None
    assert record.source_label == STAGE30_5_3_SOURCE_LABEL
    assert record.observed_at_utc == _OBS_TS
    assert (
        _display_via_resolver(_evidence(STAGE29_5_MEASUREMENT_STATUS_COMPLETE))
        == MIGRATION_DISPLAY_KNOWN
    )


# ---------------------------------------------------------------------------
# 2. Partial (no stale) -> UNVERIFIED / EVIDENCE_PARTIAL / PRESENT
# ---------------------------------------------------------------------------


def test_partial_maps_to_unverified_present_evidence_partial() -> None:
    record = _project(
        _evidence(STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT)
    )
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_UNVERIFIED
    assert record.migration_basis == MIGRATION_BASIS_EVIDENCE_PARTIAL
    assert record.source_status == SOURCE_STATUS_PRESENT
    assert record.source_reason == SOURCE_REASON_EVIDENCE_PARTIAL
    assert record.runtime_consumable is False
    assert (
        _display_via_resolver(
            _evidence(
                STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT
            )
        )
        == MIGRATION_DISPLAY_UNVERIFIED
    )


# ---------------------------------------------------------------------------
# 3. Stale partial -> UNKNOWN / NONE / STALE -> Unknown (no Stale word)
# ---------------------------------------------------------------------------


def test_stale_partial_maps_to_unknown_stale_no_stale_word() -> None:
    evidence = _evidence(
        STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        warnings=(STAGE29_5_WARNING_MIGRATION_STALE,),
    )
    record = _project(evidence)
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_UNKNOWN
    assert record.migration_basis == MIGRATION_BASIS_NONE
    assert record.source_status == SOURCE_STATUS_STALE
    assert record.source_reason == SOURCE_REASON_SOURCE_STALE
    display = _display_via_resolver(evidence)
    assert display == MIGRATION_DISPLAY_UNKNOWN
    assert display != "Stale"
    assert "Stale" not in display


def test_stale_warning_alongside_other_warnings_still_degrades() -> None:
    evidence = _evidence(
        STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        warnings=(
            "POST_MIGRATION_ATH_UNVERIFIED",
            STAGE29_5_WARNING_MIGRATION_STALE,
        ),
    )
    record = _project(evidence)
    assert record is not None
    assert record.source_status == SOURCE_STATUS_STALE
    assert _display_via_resolver(evidence) == MIGRATION_DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# 4. Missing -> UNKNOWN / NONE / UNAVAILABLE -> Unknown
# ---------------------------------------------------------------------------


def test_missing_maps_to_unknown_unavailable() -> None:
    record = _project(
        _evidence(STAGE29_5_MEASUREMENT_STATUS_MISSING_MIGRATION)
    )
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_UNKNOWN
    assert record.migration_basis == MIGRATION_BASIS_NONE
    assert record.source_status == SOURCE_STATUS_UNAVAILABLE
    assert record.source_reason == SOURCE_REASON_SOURCE_UNAVAILABLE
    assert (
        _display_via_resolver(
            _evidence(STAGE29_5_MEASUREMENT_STATUS_MISSING_MIGRATION)
        )
        == MIGRATION_DISPLAY_UNKNOWN
    )


# ---------------------------------------------------------------------------
# 5. Invalid -> UNKNOWN / NONE / ERROR -> Unknown
# ---------------------------------------------------------------------------


def test_invalid_maps_to_unknown_error() -> None:
    record = _project(
        _evidence(STAGE29_5_MEASUREMENT_STATUS_INVALID_MIGRATION)
    )
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_UNKNOWN
    assert record.migration_basis == MIGRATION_BASIS_NONE
    assert record.source_status == SOURCE_STATUS_ERROR
    assert record.source_reason == SOURCE_REASON_EVIDENCE_INVALID
    assert (
        _display_via_resolver(
            _evidence(STAGE29_5_MEASUREMENT_STATUS_INVALID_MIGRATION)
        )
        == MIGRATION_DISPLAY_UNKNOWN
    )


# ---------------------------------------------------------------------------
# 6. Conflicting -> conservative UNKNOWN / NONE / ERROR -> Unknown
# ---------------------------------------------------------------------------


def test_conflicting_maps_to_conservative_unknown_error() -> None:
    record = _project(
        _evidence(STAGE29_5_MEASUREMENT_STATUS_CONFLICTING_MIGRATION)
    )
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_UNKNOWN
    assert record.migration_basis == MIGRATION_BASIS_NONE
    assert record.source_status == SOURCE_STATUS_ERROR
    assert record.source_reason == SOURCE_REASON_EVIDENCE_INVALID
    # A conflict is NEVER promoted to Known / Unverified.
    assert (
        _display_via_resolver(
            _evidence(STAGE29_5_MEASUREMENT_STATUS_CONFLICTING_MIGRATION)
        )
        == MIGRATION_DISPLAY_UNKNOWN
    )


# ---------------------------------------------------------------------------
# 7. None evidence -> UNKNOWN / NONE / UNAVAILABLE -> Unknown
# ---------------------------------------------------------------------------


def test_none_evidence_maps_to_unknown_unavailable() -> None:
    record = _project(None)
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_UNKNOWN
    assert record.migration_basis == MIGRATION_BASIS_NONE
    assert record.source_status == SOURCE_STATUS_UNAVAILABLE
    assert record.source_reason == SOURCE_REASON_SOURCE_UNAVAILABLE
    assert _display_via_resolver(None) == MIGRATION_DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# 8. Malformed -> UNKNOWN / NONE / ERROR -> Unknown
# ---------------------------------------------------------------------------


def test_unrecognized_measurement_status_maps_to_unknown_error() -> None:
    record = _project(_evidence("DEFINITELY_MIGRATED_TRUST_ME"))
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_UNKNOWN
    assert record.migration_basis == MIGRATION_BASIS_NONE
    assert record.source_status == SOURCE_STATUS_ERROR
    assert record.source_reason == SOURCE_REASON_SOURCE_ERROR
    assert (
        _display_via_resolver(_evidence("DEFINITELY_MIGRATED_TRUST_ME"))
        == MIGRATION_DISPLAY_UNKNOWN
    )


def test_missing_measurement_status_field_maps_to_unknown_error() -> None:
    # A summary whose measurement_status is None (e.g. a malformed
    # artifact) degrades to Unknown / ERROR.
    record = _project(_evidence(None))
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_UNKNOWN
    assert record.source_status == SOURCE_STATUS_ERROR
    assert record.source_reason == SOURCE_REASON_SOURCE_ERROR


def test_object_without_measurement_status_attr_maps_to_unknown() -> None:
    # A bare object that does not expose measurement_status at all degrades
    # to Unknown (getattr returns None -> malformed path).
    record = _project(SimpleNamespace(unrelated="x"))
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_UNKNOWN
    assert record.source_status == SOURCE_STATUS_ERROR


# ---------------------------------------------------------------------------
# 9. Non-redaction-safe summary degrades even a confirmed COMPLETE
# ---------------------------------------------------------------------------


def test_redacted_summary_degrades_even_complete_to_unknown() -> None:
    evidence = _evidence(
        STAGE29_5_MEASUREMENT_STATUS_COMPLETE,
        redaction_status="REDACTED",
    )
    record = _project(evidence)
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_UNKNOWN
    assert record.migration_basis == MIGRATION_BASIS_NONE
    assert record.source_status == SOURCE_STATUS_ERROR
    assert record.source_reason == SOURCE_REASON_EVIDENCE_INVALID
    assert _display_via_resolver(evidence) == MIGRATION_DISPLAY_UNKNOWN


def test_none_redaction_status_does_not_block_complete() -> None:
    # redaction_status not asserted (None) -> the bridge does not block a
    # COMPLETE reading (it only degrades on a present non-SAFE value).
    evidence = _evidence(
        STAGE29_5_MEASUREMENT_STATUS_COMPLETE,
        redaction_status=None,
    )
    record = _project(evidence)
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_KNOWN
    assert _display_via_resolver(evidence) == MIGRATION_DISPLAY_KNOWN


# ---------------------------------------------------------------------------
# 10. Duck-typed input works WITHOUT importing Stage 29.5
# ---------------------------------------------------------------------------


def test_duck_typed_stage29_5_shape_projects_without_stage29_import() -> None:
    # A SimpleNamespace mirroring a sanitized Stage 29.5 private-ping
    # migration-context record (measurement_status / warnings /
    # redaction_status) projects identically -- the bridge reads the SHAPE
    # via getattr and imports no Stage 29 module.
    duck = SimpleNamespace(
        measurement_status=STAGE29_5_MEASUREMENT_STATUS_COMPLETE,
        warnings=(),
        redaction_status=STAGE29_5_REDACTION_STATUS_SAFE,
        # Extra Stage 29.5 fields the bridge must IGNORE (never read /
        # never echo): a raw signature, a raw event ref, a slot.
        migration_signature="rawsig_DO_NOT_LEAK",
        source_event_ref="rawref_DO_NOT_LEAK",
        migration_slot=12345,
    )
    record = _project(duck)
    assert record is not None
    assert record.migration_status == MIGRATION_STATUS_KNOWN
    assert record.token_label is None
    assert _display_via_resolver(duck) == MIGRATION_DISPLAY_KNOWN


# ---------------------------------------------------------------------------
# 11. observed_at_utc gating: an unsafe / missing clock yields no record
# ---------------------------------------------------------------------------


def test_unsafe_observed_at_utc_returns_none_record() -> None:
    assert _project(_evidence(STAGE29_5_MEASUREMENT_STATUS_COMPLETE), "nope") is (
        None
    )
    assert _project(
        _evidence(STAGE29_5_MEASUREMENT_STATUS_COMPLETE), None
    ) is None


def test_bridge_read_without_clock_returns_none_and_resolves_unknown() -> None:
    bridge = Stage30_5_3Stage29MigrationEvidenceBridge(
        evidence=_evidence(STAGE29_5_MEASUREMENT_STATUS_COMPLETE),
    )
    # No observed_at_utc -> the bridge cannot stamp a record -> None.
    assert bridge.read(_TOKEN_MINT) is None
    # Through the resolver seam a missing clock degrades to Unknown
    # (the projector returns None -> the adapter resolves UNAVAILABLE).
    assert _display_via_resolver(
        _evidence(STAGE29_5_MEASUREMENT_STATUS_COMPLETE),
        observed_at_utc=None,
    ) == MIGRATION_DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# 12. The bridge never echoes the token mint into the record
# ---------------------------------------------------------------------------


def test_bridge_read_does_not_echo_token_mint() -> None:
    bridge = Stage30_5_3Stage29MigrationEvidenceBridge(
        evidence=_evidence(STAGE29_5_MEASUREMENT_STATUS_COMPLETE),
    )
    record = bridge.read(_TOKEN_MINT, _OBS_TS)
    assert record is not None
    assert record.token_label is None
    # The full mint never appears anywhere on the record's string fields.
    for value in (
        record.schema_version,
        record.source_label,
        record.source_status,
        record.source_reason,
        record.observed_at_utc,
    ):
        assert _TOKEN_MINT not in (value or "")


def test_bridge_exposes_evidence_property() -> None:
    ev = _evidence(STAGE29_5_MEASUREMENT_STATUS_COMPLETE)
    bridge = Stage30_5_3Stage29MigrationEvidenceBridge(evidence=ev)
    assert bridge.evidence is ev


# ---------------------------------------------------------------------------
# 13. No raw field leakage: record / projection / input field-name sets
# ---------------------------------------------------------------------------


def test_sanitized_input_carries_only_three_safe_fields() -> None:
    field_names = {
        f.name
        for f in dataclasses.fields(
            Stage30_5_3SanitizedStage29MigrationEvidence
        )
    }
    assert field_names == {
        "measurement_status",
        "warnings",
        "redaction_status",
    }
    for name in field_names:
        assert not is_forbidden_record_field_name(name)


def test_record_and_projection_field_names_carry_no_forbidden_name() -> None:
    for name in record_field_names() + projection_field_names():
        assert not is_forbidden_record_field_name(name), (
            f"Stage 30.5.3 bridge output field {name!r} is forbidden"
        )


def test_projection_runtime_consumable_is_false() -> None:
    # The bridge output, projected through the Stage 30.5.1 adapter, is
    # never runtime-consumable.
    bridge = Stage30_5_3Stage29MigrationEvidenceBridge(
        evidence=_evidence(STAGE29_5_MEASUREMENT_STATUS_COMPLETE),
    )
    projection = project_migration_context(bridge, _TOKEN_MINT, _OBS_TS)
    assert projection.runtime_consumable is False
    assert projection.migration_display_text == MIGRATION_DISPLAY_KNOWN


# ---------------------------------------------------------------------------
# 14. build_stage30_migration_resolver_from_stage29_artifact wiring
# ---------------------------------------------------------------------------


def test_builder_returns_stage30_5_2_resolver() -> None:
    resolver = build_stage30_migration_resolver_from_stage29_artifact(
        evidence=_evidence(STAGE29_5_MEASUREMENT_STATUS_COMPLETE),
    )
    assert isinstance(resolver, Stage30_5_2MigrationDisplayResolver)
    assert isinstance(
        resolver.source, Stage30_5_3Stage29MigrationEvidenceBridge
    )


def test_resolve_migration_display_text_over_bridge_matrix() -> None:
    cases = {
        STAGE29_5_MEASUREMENT_STATUS_COMPLETE: MIGRATION_DISPLAY_KNOWN,
        STAGE29_5_MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT: (
            MIGRATION_DISPLAY_UNVERIFIED
        ),
        STAGE29_5_MEASUREMENT_STATUS_MISSING_MIGRATION: (
            MIGRATION_DISPLAY_UNKNOWN
        ),
        STAGE29_5_MEASUREMENT_STATUS_INVALID_MIGRATION: (
            MIGRATION_DISPLAY_UNKNOWN
        ),
        STAGE29_5_MEASUREMENT_STATUS_CONFLICTING_MIGRATION: (
            MIGRATION_DISPLAY_UNKNOWN
        ),
    }
    observed = set()
    for measurement_status, expected in cases.items():
        bridge = Stage30_5_3Stage29MigrationEvidenceBridge(
            evidence=_evidence(measurement_status),
        )
        display = resolve_migration_display_text(bridge, _TOKEN_MINT, _OBS_TS)
        assert display == expected
        observed.add(display)
    # The display vocabulary never leaves the three closed-set words.
    assert observed <= {"Known", "Unverified", "Unknown"}
    assert "Fresh" not in observed
    assert "Stale" not in observed
