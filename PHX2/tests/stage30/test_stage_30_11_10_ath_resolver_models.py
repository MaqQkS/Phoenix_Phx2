"""Stage 30.11.10 ATH-resolver models tests.

Pins the Stage 30.11.10 model layer:

  * the minor + schema version,
  * the committed-shape ATH context record / resolution / summary / run-result field
    NAMES (cross-checked against the manifest and against the committed Stage 30.11.7
    ATH resolver result fields BY VALUE -- so the committed Stage 30.11.7 adapter reads
    a Stage 30.11.10 resolution duck-typed),
  * the committed Stage 27.4 ATH vocabulary the resolver mirrors BY VALUE (cross-checked
    against the real Stage 27.4 constants),
  * the record field NAMES are a SUBSET of the committed Stage 27.4 ``AthContextRecord``
    field names BY VALUE (so a real Stage 27.4 record is consumed via attribute access),
  * the closed-set decision / reason vocabularies + their membership helpers,
  * the expected proof baseline,
  * the fail-closed defaults (a bare resolver result can never resolve).

The committed Stage 30.11.7 + Stage 27.4 surfaces are imported by this TEST (a test
file is not boundary-scanned); the Stage 30.11.10 PRODUCTION modules import only their
own siblings. Pure / offline. No live call, no provider, no private send, no env read.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_10_ATH_CONTEXT_RECORD_FIELDS,
    STAGE30_11_10_ATH_DECISIONS,
    STAGE30_11_10_ATH_PASS_DECISION,
    STAGE30_11_10_ATH_PASS_REASON,
    STAGE30_11_10_ATH_REASONS,
    STAGE30_11_10_ATH_RESOLUTION_FIELDS,
    STAGE30_11_10_ATH_RESOLVER_RUN_RESULT_FIELDS,
    STAGE30_11_10_ATH_RESOLVER_SCHEMA_VERSION,
    STAGE30_11_10_ATH_RESOLVER_SUMMARY_FIELDS,
    STAGE30_11_10_ATH_STATUS_PRESENT as M_ATH_STATUS_PRESENT,
    STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH as M_DD_BASIS,
    STAGE30_11_10_EXPECTED_BASES_SEEN,
    STAGE30_11_10_EXPECTED_RESOLVED,
    STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT,
    STAGE30_11_10_EXPECTED_UNRESOLVED,
    STAGE30_11_10_MINOR_VERSION,
)
from PHX2.stage30.stage30_11_10_ath_resolver_models import (
    ATH_DECISION_RESOLVED,
    ATH_DECISION_UNRESOLVED,
    ATH_REASON_RESOLVED_POST_MIGRATION_ATH,
    STAGE30_11_10_ATH_RESOLVER_SCHEMA_VERSION as MODELS_SCHEMA_VERSION,
    STAGE30_11_10_ATH_STATUS_PRESENT,
    STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    STAGE30_11_10_MINOR_VERSION as MODELS_MINOR_VERSION,
    Stage30_11_10AthContextRecord,
    Stage30_11_10AthResolution,
    ath_context_record_field_names,
    ath_resolution_field_names,
    ath_resolver_run_result_field_names,
    ath_resolver_summary_field_names,
    is_ath_decision,
    is_ath_reason,
    is_nonblank_str,
)

# Committed Stage 30.11.7 ATH resolver result field names (the contract this slice
# mirrors BY VALUE) + the real Stage 27.4 vocabulary (the source shape).
from PHX2.stage30.stage30_11_7_candidate_enrichment_models import (
    ath_resolution_field_names as stage_30_11_7_ath_resolution_field_names,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_STATUS_PRESENT as STAGE27_4_ATH_STATUS_PRESENT,
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY as STAGE27_4_POST_MIG_ONLY,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH as STAGE27_4_DD_BASIS_FROM_POST_MIG,
    AthContextRecord as Stage27_4AthContextRecord,
)


# ---------------------------------------------------------------------------
# 1. Minor + schema version (mirrored against the manifest)
# ---------------------------------------------------------------------------


def test_minor_version_pinned_and_matches_manifest() -> None:
    assert MODELS_MINOR_VERSION == "30.11.10"
    assert MODELS_MINOR_VERSION == STAGE30_11_10_MINOR_VERSION


def test_schema_version_pinned_and_matches_manifest() -> None:
    assert MODELS_SCHEMA_VERSION == "stage30_11_10_v0_ath_resolver"
    assert MODELS_SCHEMA_VERSION == STAGE30_11_10_ATH_RESOLVER_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 2. Field tuples (mirrored from models; resolution mirrors Stage 30.11.7 BY VALUE)
# ---------------------------------------------------------------------------


def test_field_tuples_match_models() -> None:
    assert STAGE30_11_10_ATH_CONTEXT_RECORD_FIELDS == (
        ath_context_record_field_names()
    )
    assert STAGE30_11_10_ATH_RESOLUTION_FIELDS == ath_resolution_field_names()
    assert STAGE30_11_10_ATH_RESOLVER_SUMMARY_FIELDS == (
        ath_resolver_summary_field_names()
    )
    assert STAGE30_11_10_ATH_RESOLVER_RUN_RESULT_FIELDS == (
        ath_resolver_run_result_field_names()
    )


def test_resolution_gate_facing_fields_equal_stage_30_11_7_by_value() -> None:
    # The committed Stage 30.11.7 enrichment adapter reads exactly these fields off the
    # injected ATH resolver result; they MUST be present on the Stage 30.11.10
    # resolution BY VALUE so the adapter reads it duck-typed.
    stage_30_11_7_fields = set(stage_30_11_7_ath_resolution_field_names())
    my_fields = set(ath_resolution_field_names())
    assert stage_30_11_7_fields <= my_fields, (
        f"Stage 30.11.7 ATH fields {sorted(stage_30_11_7_fields)} must be a subset "
        f"of the Stage 30.11.10 resolution fields {sorted(my_fields)}"
    )
    for name in (
        "present",
        "fresh",
        "post_migration_ath_verified",
        "drawdown_from_ath",
        "source_ref",
    ):
        assert name in my_fields, name


def test_record_fields_are_a_subset_of_committed_stage_27_4_ath_record() -> None:
    # The Stage 30.11.10 committed-shape record carries a SUBSET of the real Stage 27.4
    # AthContextRecord field names BY VALUE, so a real Stage 27.4 record is consumed via
    # attribute access exactly as this fake record is.
    real_fields = set(Stage27_4AthContextRecord._fields)
    my_record_fields = set(ath_context_record_field_names())
    assert my_record_fields <= real_fields, (
        f"Stage 30.11.10 record fields {sorted(my_record_fields)} must be a subset of "
        f"the committed Stage 27.4 AthContextRecord fields {sorted(real_fields)}"
    )
    # The exact fields the resolver reads are all present on the real record.
    for name in (
        "token_mint",
        "ath_status",
        "drawdown_basis",
        "drawdown_from_ath",
        "ath_source",
    ):
        assert name in real_fields, name


# ---------------------------------------------------------------------------
# 3. Mirrored Stage 27.4 vocabulary equals the real Stage 27.4 constants BY VALUE
# ---------------------------------------------------------------------------


def test_mirrored_ath_tokens_equal_real_stage_27_4_constants() -> None:
    assert STAGE30_11_10_ATH_STATUS_PRESENT == STAGE27_4_ATH_STATUS_PRESENT
    assert STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH == (
        STAGE27_4_DD_BASIS_FROM_POST_MIG
    )
    assert STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY == (
        STAGE27_4_POST_MIG_ONLY
    )
    # And the manifest mirrors them BY VALUE too.
    assert M_ATH_STATUS_PRESENT == STAGE27_4_ATH_STATUS_PRESENT
    assert M_DD_BASIS == STAGE27_4_DD_BASIS_FROM_POST_MIG


# ---------------------------------------------------------------------------
# 4. Closed-set decision / reason vocabularies + membership helpers
# ---------------------------------------------------------------------------


def test_decisions_pinned_and_match_manifest() -> None:
    assert STAGE30_11_10_ATH_DECISIONS == (
        ATH_DECISION_RESOLVED,
        ATH_DECISION_UNRESOLVED,
    )
    assert STAGE30_11_10_ATH_PASS_DECISION == ATH_DECISION_RESOLVED
    for d in STAGE30_11_10_ATH_DECISIONS:
        assert is_ath_decision(d)
    for bad in ("resolved_ath", "", None, 5, True):
        assert not is_ath_decision(bad)


def test_reasons_pinned_and_match_manifest() -> None:
    # The manifest mirrors the same closed set BY VALUE.
    assert ATH_REASON_RESOLVED_POST_MIGRATION_ATH in STAGE30_11_10_ATH_REASONS
    assert STAGE30_11_10_ATH_PASS_REASON == ATH_REASON_RESOLVED_POST_MIGRATION_ATH
    assert set(STAGE30_11_10_ATH_REASONS) == {
        "RESOLVED_POST_MIGRATION_ATH",
        "BLANK_CANDIDATE_MINT",
        "MISSING_MIGRATION_ANCHOR",
        "MISSING_ATH_SOURCE",
        "ATH_SOURCE_ERROR",
        "ATH_SOURCE_UNAVAILABLE",
        "ATH_MINT_MISMATCH",
        "ATH_NOT_PRESENT",
        "PRE_MIGRATION_ATH_NOT_VERIFIED",
        "MISSING_DRAWDOWN",
    }
    # Exactly one pass reason; the rest are distinct fail-closed reasons.
    assert len(STAGE30_11_10_ATH_REASONS) == 10
    assert len(set(STAGE30_11_10_ATH_REASONS)) == 10
    for r in STAGE30_11_10_ATH_REASONS:
        assert is_ath_reason(r)
    for bad in ("nope", "", None, 7):
        assert not is_ath_reason(bad)


# ---------------------------------------------------------------------------
# 5. Expected proof baseline
# ---------------------------------------------------------------------------


def test_expected_proof_baseline_pinned() -> None:
    assert STAGE30_11_10_EXPECTED_BASES_SEEN == 9
    assert STAGE30_11_10_EXPECTED_RESOLVED == 1
    assert STAGE30_11_10_EXPECTED_UNRESOLVED == 8
    assert (
        STAGE30_11_10_EXPECTED_RESOLVED
        + STAGE30_11_10_EXPECTED_UNRESOLVED
        == STAGE30_11_10_EXPECTED_BASES_SEEN
    )
    assert STAGE30_11_10_EXPECTED_RESOLVED_TOKEN_MINT == "mint-resolved"


# ---------------------------------------------------------------------------
# 6. Fail-closed defaults (a bare record can never resolve)
# ---------------------------------------------------------------------------


def test_record_defaults_are_fail_closed() -> None:
    rec = Stage30_11_10AthContextRecord()
    assert rec.token_mint is None
    assert rec.ath_status is None
    assert rec.ath_since_migration_status is None
    assert rec.drawdown_basis is None
    assert rec.drawdown_from_ath is None
    assert rec.ath_source is None


def test_records_and_resolutions_are_immutable() -> None:
    rec = Stage30_11_10AthContextRecord(token_mint="m")
    res = Stage30_11_10AthResolution(
        present=True,
        fresh=True,
        post_migration_ath_verified=True,
        drawdown_from_ath="1",
        token_mint="m",
        decision=ATH_DECISION_RESOLVED,
        reason=ATH_REASON_RESOLVED_POST_MIGRATION_ATH,
        source_ref=None,
    )
    for obj, attr, val in (
        (rec, "token_mint", "other"),
        (res, "present", False),
    ):
        try:
            setattr(obj, attr, val)
            raised = False
        except Exception:
            raised = True
        assert raised, f"{type(obj).__name__}.{attr} must be frozen"


# ---------------------------------------------------------------------------
# 7. is_nonblank_str helper
# ---------------------------------------------------------------------------


def test_is_nonblank_str() -> None:
    for good in ("m", " mint ", "x"):
        assert is_nonblank_str(good)
    for bad in (None, "", "   ", 5, True, b"m", []):
        assert not is_nonblank_str(bad)
