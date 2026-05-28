"""Stage 30.3 compact runtime models tests.

Pure read-only tests over the Stage 30.3 closed-set token
vocabularies, immutable record shapes, forbidden-field-name
guard, and the module-local exception.

Discipline: no env reads, no network, no provider calls, no
operator-channel send. Stdlib + pytest only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PHX2.stage30.stage30_3_compact_runtime_models import (
    COMPACT_OUTCOME_FAILED_CAP,
    COMPACT_OUTCOME_FAILED_COMPACT_RENDER,
    COMPACT_OUTCOME_FAILED_EXCEPTION,
    COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
    COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE,
    COMPACT_OUTCOME_FAILED_TIER_DECISION,
    COMPACT_OUTCOME_RENDERED,
    COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
    COMPACT_OUTCOME_VALUES,
    FORBIDDEN_RECORD_FIELD_NAMES,
    SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED,
    SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED,
    SNAPSHOT_WRITE_REASON_VALUES,
    STAGE30_3_MINOR_VERSION,
    STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
    STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION,
    Stage30_3CompactRuntimeContext,
    Stage30_3CompactRuntimeError,
    Stage30_3RecordedCandidateContext,
    Stage30_3RuntimeWiringArtifactRecord,
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP,
    WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
    WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION,
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
    WRAPPER_ORDER_LABEL_VALUES,
    _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS,
    is_compact_outcome_value,
    is_forbidden_record_field_name,
    is_snapshot_write_reason_value,
    is_wrapper_order_label_value,
)


# ---------------------------------------------------------------------------
# Locked version + basename pins
# ---------------------------------------------------------------------------


def test_minor_version_pin() -> None:
    assert STAGE30_3_MINOR_VERSION == "30.3"


def test_runtime_wiring_schema_version_pin() -> None:
    assert (
        STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION
        == "stage30_3_v0_runtime_wiring"
    )


def test_runtime_wiring_artifact_basename_pin() -> None:
    assert (
        STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
        == "stage30_3_runtime_wiring.jsonl"
    )


def test_synthetic_refusal_transport_status_pin() -> None:
    # Mirrors the Stage 28.4
    # ``TRANSPORT_STATUS_PAYLOAD_REFUSED`` token value verbatim
    # (the Stage 30.3 module redeclares the literal locally so it
    # imports zero Stage 28 modules).
    assert (
        _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS
        == "PAYLOAD_REFUSED"
    )


# ---------------------------------------------------------------------------
# Compact-outcome closed set
# ---------------------------------------------------------------------------


def test_compact_outcome_values_order_and_membership() -> None:
    assert COMPACT_OUTCOME_VALUES == (
        COMPACT_OUTCOME_RENDERED,
        COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
        COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
        COMPACT_OUTCOME_FAILED_TIER_DECISION,
        COMPACT_OUTCOME_FAILED_COMPACT_RENDER,
        COMPACT_OUTCOME_FAILED_CAP,
        COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE,
        COMPACT_OUTCOME_FAILED_EXCEPTION,
    )


def test_compact_outcome_values_are_unique() -> None:
    assert len(COMPACT_OUTCOME_VALUES) == len(set(COMPACT_OUTCOME_VALUES))


def test_compact_outcome_token_literals() -> None:
    assert COMPACT_OUTCOME_RENDERED == "RENDERED"
    assert COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE == "SKIPPED_NOT_TIERABLE"
    assert COMPACT_OUTCOME_FAILED_INPUT_SHAPE == "FAILED_INPUT_SHAPE"
    assert COMPACT_OUTCOME_FAILED_TIER_DECISION == "FAILED_TIER_DECISION"
    assert (
        COMPACT_OUTCOME_FAILED_COMPACT_RENDER == "FAILED_COMPACT_RENDER"
    )
    assert COMPACT_OUTCOME_FAILED_CAP == "FAILED_CAP"
    assert (
        COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE == "FAILED_SNAPSHOT_WRITE"
    )
    assert COMPACT_OUTCOME_FAILED_EXCEPTION == "FAILED_EXCEPTION"


@pytest.mark.parametrize("token", COMPACT_OUTCOME_VALUES)
def test_is_compact_outcome_value_true_for_every_token(
    token: str,
) -> None:
    assert is_compact_outcome_value(token) is True


@pytest.mark.parametrize(
    "value",
    [None, 0, 1.5, [], (), {}, "rendered", "Rendered", "", "FOO"],
)
def test_is_compact_outcome_value_false_for_non_members(
    value: object,
) -> None:
    assert is_compact_outcome_value(value) is False


def test_compact_outcome_membership_round_trip() -> None:
    for token in COMPACT_OUTCOME_VALUES:
        assert is_compact_outcome_value(token)
        assert token in COMPACT_OUTCOME_VALUES


# ---------------------------------------------------------------------------
# Snapshot-write sub-reason closed set
# ---------------------------------------------------------------------------


def test_snapshot_write_reason_values_order_and_membership() -> None:
    assert SNAPSHOT_WRITE_REASON_VALUES == (
        SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED,
        SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED,
    )


def test_snapshot_write_reason_literals() -> None:
    assert (
        SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED == "TIER_WRITE_FAILED"
    )
    assert (
        SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED
        == "COMPACT_WRITE_FAILED"
    )


@pytest.mark.parametrize("token", SNAPSHOT_WRITE_REASON_VALUES)
def test_is_snapshot_write_reason_value_true_for_every_token(
    token: str,
) -> None:
    assert is_snapshot_write_reason_value(token) is True


@pytest.mark.parametrize(
    "value",
    [None, 0, 1.5, [], (), {}, "tier_write_failed", "TIER", ""],
)
def test_is_snapshot_write_reason_value_false_for_non_members(
    value: object,
) -> None:
    assert is_snapshot_write_reason_value(value) is False


# ---------------------------------------------------------------------------
# Wrapper-order label closed set
# ---------------------------------------------------------------------------


def test_wrapper_order_label_values_membership() -> None:
    expected = (
        WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
        WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION,
        WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK,
        WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP,
        WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    )
    assert WRAPPER_ORDER_LABEL_VALUES == expected


def test_wrapper_order_label_literals() -> None:
    assert (
        WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY
        == "stage30_3_compact_body"
    )
    assert (
        WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION
        == "stage29_5_6_migration_context"
    )
    assert (
        WRAPPER_ORDER_LABEL_STAGE28_9_PRIVATE_WEBHOOK
        == "stage28_9_private_" + "webhook"
    )
    assert (
        WRAPPER_ORDER_LABEL_STAGE28_4_AUDITED_HTTP
        == "stage28_4_audited_http"
    )
    assert (
        WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT
        == "fake_inner_transport"
    )


@pytest.mark.parametrize("label", WRAPPER_ORDER_LABEL_VALUES)
def test_is_wrapper_order_label_value_true_for_every_label(
    label: str,
) -> None:
    assert is_wrapper_order_label_value(label) is True


@pytest.mark.parametrize(
    "value", [None, 0, [], (), "", "stage30_3", "fake"],
)
def test_is_wrapper_order_label_value_false_for_non_members(
    value: object,
) -> None:
    assert is_wrapper_order_label_value(value) is False


# ---------------------------------------------------------------------------
# Forbidden-field-name vocabulary
# ---------------------------------------------------------------------------


def test_forbidden_record_field_names_covers_documented_tokens() -> None:
    expected_tokens = {
        "web" + "hook",
        "web" + "hook_url",
        "web" + "hooks",
        "web" + "hook_token",
        "api_key",
        "apikey",
        "bearer",
        "bearer_token",
        "authorization",
        "secret",
        "secret_key",
        "secretkey",
        "token_secret",
        "private_key",
        "privatekey",
        "seed_phrase",
        "mnemonic",
        "signer",
        "signing_key",
        "credentials",
        "password",
        "raw_payload",
        "payload",
        "payload_blob",
        "payload_summary",
        "migration_event_id",
        "raw_capture_ref",
        "source_event_ref",
        "rpc_url",
    }
    observed = set(FORBIDDEN_RECORD_FIELD_NAMES)
    missing = expected_tokens - observed
    assert not missing, (
        "FORBIDDEN_RECORD_FIELD_NAMES missing documented tokens: "
        f"{sorted(missing)!r}"
    )


@pytest.mark.parametrize("token", FORBIDDEN_RECORD_FIELD_NAMES)
def test_is_forbidden_record_field_name_true_for_every_token(
    token: str,
) -> None:
    assert is_forbidden_record_field_name(token) is True


def test_is_forbidden_record_field_name_case_insensitive_substring() -> None:
    # Substring containment
    assert is_forbidden_record_field_name("my_secret_field") is True
    # Case-insensitive
    assert is_forbidden_record_field_name("MY_API_KEY") is True
    assert is_forbidden_record_field_name("BearerToken") is True


@pytest.mark.parametrize(
    "value",
    [None, 0, 1.5, [], (), {}, "candidate_id", "tier_token", "basis"],
)
def test_is_forbidden_record_field_name_false_for_safe_values(
    value: object,
) -> None:
    assert is_forbidden_record_field_name(value) is False


def test_wiring_record_fields_have_no_forbidden_name() -> None:
    for name in Stage30_3RuntimeWiringArtifactRecord._fields:
        assert not is_forbidden_record_field_name(name), (
            f"Stage30_3RuntimeWiringArtifactRecord field "
            f"{name!r} matches forbidden-field-name vocabulary"
        )


def test_recorded_candidate_context_fields_have_no_forbidden_name() -> None:
    for name in Stage30_3RecordedCandidateContext._fields:
        assert not is_forbidden_record_field_name(name), (
            f"Stage30_3RecordedCandidateContext field "
            f"{name!r} matches forbidden-field-name vocabulary"
        )


def test_compact_runtime_context_fields_have_no_forbidden_name() -> None:
    for name in Stage30_3CompactRuntimeContext._fields:
        assert not is_forbidden_record_field_name(name), (
            f"Stage30_3CompactRuntimeContext field "
            f"{name!r} matches forbidden-field-name vocabulary"
        )


# ---------------------------------------------------------------------------
# NamedTuple equality
# ---------------------------------------------------------------------------


def test_compact_runtime_context_namedtuple_equality(
    tmp_path: Path,
) -> None:
    ctx_a = Stage30_3CompactRuntimeContext(
        session_id="sess-001",
        run_id="run-001",
        basis="price-basis",
        output_dir=tmp_path,
    )
    ctx_b = Stage30_3CompactRuntimeContext(
        session_id="sess-001",
        run_id="run-001",
        basis="price-basis",
        output_dir=tmp_path,
    )
    assert ctx_a == ctx_b
    assert hash(ctx_a) == hash(ctx_b)


def test_recorded_candidate_context_namedtuple_equality() -> None:
    entry_a = Stage30_3RecordedCandidateContext(
        candidate_id="cand-001",
        mint="So11111111111111111111111111111111111111112",
        ath_record=None,
        migration_record=None,
        price_status="PRESENT",
        age_since_migration_seconds=42,
        recorded_at_utc="2026-05-27T00:00:00Z",
    )
    entry_b = Stage30_3RecordedCandidateContext(
        candidate_id="cand-001",
        mint="So11111111111111111111111111111111111111112",
        ath_record=None,
        migration_record=None,
        price_status="PRESENT",
        age_since_migration_seconds=42,
        recorded_at_utc="2026-05-27T00:00:00Z",
    )
    assert entry_a == entry_b


def test_runtime_wiring_record_namedtuple_equality() -> None:
    rec_a = Stage30_3RuntimeWiringArtifactRecord(
        schema_version=STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION,
        session_id="sess-001",
        candidate_id="cand-001",
        ping_id="cand-001",
        mint="So11111111111111111111111111111111111111112",
        wrapper_order=(
            WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
            WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
        ),
        compact_outcome=COMPACT_OUTCOME_RENDERED,
        compact_outcome_reason=None,
        tier_token="Tier 1",
        tier_reason="TIER_1_IN_BAND",
        basis="price-basis",
        original_content_length_chars=500,
        compact_content_length_chars=200,
        compact_body_sha256_hex_prefix_16="0123456789abcdef",
        tier_snapshot_path_basename="stage30_1_tier_decisions.jsonl",
        compact_snapshot_path_basename="stage30_2_compact_pings.jsonl",
        forwarded_to_inner_transport=True,
        created_at_utc="2026-05-27T00:00:00Z",
    )
    rec_b = Stage30_3RuntimeWiringArtifactRecord(
        schema_version=STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION,
        session_id="sess-001",
        candidate_id="cand-001",
        ping_id="cand-001",
        mint="So11111111111111111111111111111111111111112",
        wrapper_order=(
            WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
            WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
        ),
        compact_outcome=COMPACT_OUTCOME_RENDERED,
        compact_outcome_reason=None,
        tier_token="Tier 1",
        tier_reason="TIER_1_IN_BAND",
        basis="price-basis",
        original_content_length_chars=500,
        compact_content_length_chars=200,
        compact_body_sha256_hex_prefix_16="0123456789abcdef",
        tier_snapshot_path_basename="stage30_1_tier_decisions.jsonl",
        compact_snapshot_path_basename="stage30_2_compact_pings.jsonl",
        forwarded_to_inner_transport=True,
        created_at_utc="2026-05-27T00:00:00Z",
    )
    assert rec_a == rec_b


# ---------------------------------------------------------------------------
# Module-local exception
# ---------------------------------------------------------------------------


def test_compact_runtime_error_carries_reason() -> None:
    exc = Stage30_3CompactRuntimeError("INNER_TRANSPORT_INVALID")
    assert exc.reason == "INNER_TRANSPORT_INVALID"
    assert "INNER_TRANSPORT_INVALID" in str(exc)
    assert "Stage 30.3" in str(exc)


def test_compact_runtime_error_is_exception_subclass() -> None:
    exc = Stage30_3CompactRuntimeError("WRAPPER_ORDER_INVALID")
    assert isinstance(exc, Exception)
