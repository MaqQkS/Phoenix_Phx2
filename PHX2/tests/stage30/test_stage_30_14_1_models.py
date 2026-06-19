"""Stage 30.14.1 evidence-artifact models leaf tests.

Pure model-layer tests: schema identity, the locked 15-field list, caps + cap predicates,
closed-set load / verify vocabularies, redaction tokens + self-scan, the safe-shape
predicates, the pump-suffix mirror (pinned BY VALUE vs the committed Stage 30.13.0), the
``source_ref`` builder mirror (pinned BY VALUE vs the committed Stage 29.5.7), ``safe_echo``,
and the dataclass carriers + field-name helpers.
"""

from __future__ import annotations

from PHX2.stage29.stage29_5_7_helius_raw_migration_models import (
    build_source_ref,
)
from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    is_pump_suffix_mint as committed_is_pump_suffix_mint,
)
from PHX2.stage30 import stage30_14_1_evidence_artifact_models as models


# ---------------------------------------------------------------------------
# 1. Schema identity + required-field list
# ---------------------------------------------------------------------------


def test_schema_versions_are_distinct_named_constants() -> None:
    assert (
        models.BUILD26_1_CAPTURE_EVIDENCE_SCHEMA_VERSION
        == "build26_1_v0_capture_evidence"
    )
    assert (
        models.STAGE30_14_1_VERIFY_SCHEMA_VERSION
        == "stage30_14_1_v0_evidence_load_replay_verify"
    )
    assert models.STAGE30_14_1_MINOR_VERSION == "30.14.1"


def test_required_fields_are_the_locked_fifteen() -> None:
    assert models.BUILD26_1_REQUIRED_FIELDS == (
        "schema_version",
        "token_mint",
        "migration_status",
        "migration_source",
        "pool_account",
        "pool_program_id",
        "quote_mint",
        "migration_event_time_utc",
        "migration_slot",
        "migration_signature",
        "source_ref",
        "observed_at_utc",
        "measurement_status",
        "redaction_status",
        "warnings",
    )
    assert len(models.BUILD26_1_REQUIRED_FIELDS) == 15
    assert len(set(models.BUILD26_1_REQUIRED_FIELDS)) == 15


# ---------------------------------------------------------------------------
# 2. Caps + cap predicates
# ---------------------------------------------------------------------------


def test_cap_defaults_within_hard_ceilings() -> None:
    assert models.STAGE30_14_1_DEFAULT_MAX_BYTES == 1_048_576
    assert models.STAGE30_14_1_HARD_MAX_BYTES == 8_388_608
    assert models.STAGE30_14_1_DEFAULT_MAX_LINES == 128
    assert models.STAGE30_14_1_HARD_MAX_LINES == 4096
    assert models.STAGE30_14_1_DEFAULT_MAX_ACCEPTED == 64
    assert models.STAGE30_14_1_HARD_MAX_ACCEPTED == 256
    assert models.STAGE30_14_1_DEFAULT_MAX_REPLAY == 8
    assert models.STAGE30_14_1_HARD_MAX_REPLAY == 64


def test_cap_predicates_fail_closed() -> None:
    for predicate, hard in (
        (models.is_within_byte_cap, models.STAGE30_14_1_HARD_MAX_BYTES),
        (models.is_within_line_cap, models.STAGE30_14_1_HARD_MAX_LINES),
        (models.is_within_accepted_cap, models.STAGE30_14_1_HARD_MAX_ACCEPTED),
        (models.is_within_replay_cap, models.STAGE30_14_1_HARD_MAX_REPLAY),
    ):
        assert predicate(1) is True
        assert predicate(hard) is True
        assert predicate(0) is False
        assert predicate(-1) is False
        assert predicate(hard + 1) is False
        assert predicate(True) is False  # bool is not a budget
        assert predicate(1.0) is False
        assert predicate("1") is False
        assert predicate(None) is False


# ---------------------------------------------------------------------------
# 3. Closed-set vocabularies
# ---------------------------------------------------------------------------


def test_load_decisions_and_reasons_closed_set() -> None:
    assert models.STAGE30_14_1_LOAD_DECISIONS == ("ACCEPTED", "REJECTED")
    assert models.is_load_decision("ACCEPTED") is True
    assert models.is_load_decision("nope") is False

    assert (
        models.LOAD_REASON_ACCEPTED_FRESH_EVIDENCE
        in models.STAGE30_14_1_LOAD_REASONS
    )
    # The accept reason is exactly one; every other reason is a reject reason.
    assert (
        models.STAGE30_14_1_LOAD_REASONS
        == (models.LOAD_REASON_ACCEPTED_FRESH_EVIDENCE,)
        + models.STAGE30_14_1_LOAD_REJECT_REASONS
    )
    for reason in models.STAGE30_14_1_LOAD_REASONS:
        assert models.is_load_reason(reason) is True
    assert models.is_load_reason("GARBAGE") is False
    # No duplicate tokens across the reject set.
    assert len(set(models.STAGE30_14_1_LOAD_REJECT_REASONS)) == len(
        models.STAGE30_14_1_LOAD_REJECT_REASONS
    )


def test_structural_and_verify_error_reasons_closed_set() -> None:
    for reason in models.STAGE30_14_1_LOAD_ERROR_REASONS:
        assert models.is_load_error_reason(reason) is True
    assert models.is_load_error_reason("nope") is False
    for reason in models.STAGE30_14_1_VERIFY_ERROR_REASONS:
        assert models.is_verify_error_reason(reason) is True
    assert models.is_verify_error_reason("nope") is False


def test_redaction_statuses() -> None:
    assert models.STAGE30_14_1_REDACTION_STATUSES == (
        "REDACTED",
        "REDACTION_VIOLATION",
    )
    assert models.STAGE30_14_1_REDACTED_UNSAFE_ID == "REDACTED_UNSAFE_ID"


# ---------------------------------------------------------------------------
# 4. Redaction self-scan + safe-shape predicates
# ---------------------------------------------------------------------------


def test_redaction_scan_flags_scheme_and_needles() -> None:
    assert models.are_strings_redaction_safe(("ABC", "abc-123", "")) is True
    assert (
        models.are_strings_redaction_safe(("a" + "://" + "b",)) is False
    )
    assert (
        models.are_strings_redaction_safe(("see disc" + "ord.com here",))
        is False
    )
    # Non-string entries are skipped, not crashed on.
    assert models.are_strings_redaction_safe(("ok", 5, None)) is True


def test_safe_echo_and_safe_echo_id() -> None:
    assert models.is_safe_echo_id("Abc_123-XYZ") is True
    assert models.is_safe_echo_id("has space") is False
    assert models.is_safe_echo_id("a/b") is False
    assert models.is_safe_echo_id("") is False
    assert models.is_safe_echo_id("x" * 129) is False

    assert models.safe_echo(None) == ""
    assert models.safe_echo("") == ""
    assert models.safe_echo("Good-Mint_1") == "Good-Mint_1"
    assert models.safe_echo("bad/value") == models.STAGE30_14_1_REDACTED_UNSAFE_ID
    assert models.safe_echo(123) == models.STAGE30_14_1_REDACTED_UNSAFE_ID


def test_is_nonblank_str() -> None:
    assert models.is_nonblank_str("x") is True
    assert models.is_nonblank_str("   ") is False
    assert models.is_nonblank_str("") is False
    assert models.is_nonblank_str(None) is False


# ---------------------------------------------------------------------------
# 5. Mirrors pinned BY VALUE against the committed sources
# ---------------------------------------------------------------------------


def test_pump_suffix_mirror_matches_committed_stage30_13_0() -> None:
    samples = (
        "Synth26Evidence" + ("A" * 25) + "pump",   # base58 pump, len 44
        "Synth26Evidence" + ("A" * 25) + "fane",   # base58 non-pump
        "P" * 44,                                    # base58 non-pump
        "short" + "pump",                            # too short
        "x" * 65 + "pump",                           # too long
        "has space pump",                            # whitespace -> not base58
        "lllOOO000pump",                             # ambiguous chars -> not base58
        "",
        None,
        123,
        True,
    )
    for value in samples:
        assert models.is_pump_suffix_mint(value) == (
            committed_is_pump_suffix_mint(value)
        ), value


def test_source_ref_mirror_matches_committed_stage29_5_7() -> None:
    cases = (
        ("abc123", 0),
        ("build26-1c-synth-sig", 318000000),
        ("Zz9", 1),
    )
    for signature, slot in cases:
        assert models.build_expected_source_ref(signature, slot) == (
            build_source_ref(signature, slot)
        )
    assert (
        models.build_expected_source_ref("sig", 7)
        == "helius:sig:sig:slot:7"
    )


# ---------------------------------------------------------------------------
# 6. Carriers + field-name helpers
# ---------------------------------------------------------------------------


def test_persisted_attestation_carrier_is_frozen() -> None:
    att = models.Stage30_14_1PersistedAttestation(
        token_mint="m",
        measurement_status="COMPLETE",
        migration_event_time_utc="2026-06-06T06:14:10Z",
        warnings=(),
        redaction_status="SAFE",
        source_ref="helius:sig:s:slot:1",
    )
    assert att.warnings == ()
    try:
        att.token_mint = "other"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("attestation must be frozen")


def test_field_name_helpers() -> None:
    assert models.evidence_load_outcome_field_names() == (
        "token_mint",
        "load_decision",
        "load_reason",
        "created_at_utc",
    )
    assert models.evidence_load_summary_field_names() == (
        "lines_seen",
        "accepted",
        "rejected",
        "duplicate",
        "created_at_utc",
    )
    assert models.persisted_attestation_field_names() == (
        "token_mint",
        "measurement_status",
        "migration_event_time_utc",
        "warnings",
        "redaction_status",
        "source_ref",
    )
    assert "shadow_results" in models.replay_verify_result_field_names()
    assert "attestation_roundtrip_ok" in (
        models.replay_verify_outcome_field_names()
    )
    assert "accepted_records" in models.evidence_load_result_field_names()
