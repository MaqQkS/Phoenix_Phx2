"""Stage 29.4 soak-models focused tests.

Pins:

  * the three Stage 29.4 probe-mode tokens,
  * the eight Stage 29.4 soak-outcome tokens,
  * the two Stage 29.4 dedupe-outcome tokens,
  * the two Stage 29.4 redaction-status tokens,
  * the locked filter-enforcement-status marker,
  * the recommended bound ranges constants,
  * ``Stage29_4SoakBounds`` validation (positive ints, locked
    ``max_total_retries=0``),
  * ``Stage29_4SoakDedupeKey`` validation (closed-set field
    shapes, secret-like rejection),
  * ``Stage29_4PassRecord`` validation (counters + UTC ISO
    timestamp + locked filter-enforcement-status),
  * ``Stage29_4SoakSummary`` validation (rolled-up counters +
    locked filter-enforcement-status + locked redaction-status),
  * ``build_pass_result`` / ``canonical_soak_dedupe_key_tuple``
    helpers,
  * the module-local exception hierarchy.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_4_soak_models import (
    DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK,
    DEDUPE_OUTCOME_NEW,
    DEDUPE_OUTCOME_VALUES,
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    PASS_RECORD_FIELD_NAMES,
    PER_PASS_MAX_DISPATCHES,
    PER_PASS_MAX_EVENTS,
    PER_PASS_MAX_TOTAL_RETRIES,
    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
    PROBE_MODE_READINESS_ONLY,
    PROBE_MODE_SHORT_SESSION_PRIVATE_SOAK_DRY_RUN,
    PROBE_MODE_VALUES,
    RECOMMENDED_HEARTBEAT_CADENCE_SECONDS_MAX,
    RECOMMENDED_HEARTBEAT_CADENCE_SECONDS_MIN,
    RECOMMENDED_MAX_CONSECUTIVE_SUPPRESSIONS_MAX,
    RECOMMENDED_MAX_CONSECUTIVE_SUPPRESSIONS_MIN,
    RECOMMENDED_MAX_DISPATCHES_MAX,
    RECOMMENDED_MAX_DISPATCHES_MIN,
    RECOMMENDED_MAX_PASSES_MAX,
    RECOMMENDED_MAX_PASSES_MIN,
    RECOMMENDED_WALL_CLOCK_SECONDS_MAX,
    RECOMMENDED_WALL_CLOCK_SECONDS_MIN,
    REDACTION_STATUS_REDACTED,
    REDACTION_STATUS_SAFE,
    REDACTION_STATUS_VALUES,
    SOAK_BOUNDS_FIELD_NAMES,
    SOAK_DEDUPE_KEY_FIELD_NAMES,
    SOAK_OUTCOME_BROKE_ON_FAILED_PASS,
    SOAK_OUTCOME_BROKE_ON_REFUSED_READINESS,
    SOAK_OUTCOME_BROKE_ON_SUPPRESSION_CIRCUIT,
    SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP,
    SOAK_OUTCOME_COMPLETED_AT_PASS_CAP,
    SOAK_OUTCOME_COMPLETED_AT_WALL_CLOCK,
    SOAK_OUTCOME_NO_DISPATCHES_NO_EVENTS,
    SOAK_OUTCOME_REFUSED_INVALID_BOUNDS,
    SOAK_OUTCOME_VALUES,
    SOAK_SUMMARY_COUNTER_FIELD_NAMES,
    SOAK_SUMMARY_FIELD_NAMES,
    SUPPRESSED_PER_OUTCOME_COUNTER_FIELD_NAMES,
    STAGE29_4_HEARTBEAT_SCHEMA_VERSION,
    STAGE29_4_MINOR_VERSION,
    STAGE29_4_REDACTION_TOKEN,
    STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION,
    Stage29_4InvalidBoundsError,
    Stage29_4InvalidDedupeKeyError,
    Stage29_4InvalidPassRecordError,
    Stage29_4InvalidSoakSummaryError,
    Stage29_4PassRecord,
    Stage29_4PassResult,
    Stage29_4SoakBounds,
    Stage29_4SoakDedupeKey,
    Stage29_4SoakError,
    Stage29_4SoakSummary,
    bounds_within_recommended_ranges,
    build_pass_record,
    build_pass_result,
    build_soak_bounds,
    build_soak_dedupe_key,
    build_soak_summary,
    canonical_soak_dedupe_key_tuple,
    is_dedupe_outcome_value,
    is_probe_mode_value,
    is_redaction_status_value,
    is_soak_outcome_value,
    pass_record_to_dict,
    soak_bounds_to_dict,
    soak_summary_to_dict,
)


# ---------------------------------------------------------------------------
# Version axes
# ---------------------------------------------------------------------------


def test_stage29_4_minor_version_is_29_4():
    assert STAGE29_4_MINOR_VERSION == "29.4"


def test_stage29_4_redaction_token_is_distinct():
    # Distinct from Stage 28.x / Stage 29.1 / 29.2 / 29.3 tokens.
    assert STAGE29_4_REDACTION_TOKEN == "<<STAGE29_4_REDACTED>>"


def test_stage29_4_soak_summary_schema_version_locked():
    assert STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION == (
        "stage29_4_soak_summary_v0"
    )


def test_stage29_4_heartbeat_schema_version_locked():
    assert STAGE29_4_HEARTBEAT_SCHEMA_VERSION == (
        "stage29_4_heartbeat_v0"
    )


# ---------------------------------------------------------------------------
# Closed-set probe modes
# ---------------------------------------------------------------------------


def test_probe_mode_values_contains_exactly_three_tokens():
    assert PROBE_MODE_VALUES == (
        PROBE_MODE_READINESS_ONLY,
        PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
        PROBE_MODE_SHORT_SESSION_PRIVATE_SOAK_DRY_RUN,
    )


def test_probe_mode_readiness_only_token_locked():
    assert PROBE_MODE_READINESS_ONLY == "READINESS_ONLY"


def test_probe_mode_connect_only_token_locked():
    assert PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY == (
        "CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY"
    )


def test_probe_mode_soak_token_locked():
    assert PROBE_MODE_SHORT_SESSION_PRIVATE_SOAK_DRY_RUN == (
        "SHORT_SESSION_PRIVATE_SOAK_DRY_RUN"
    )


@pytest.mark.parametrize("token", PROBE_MODE_VALUES)
def test_is_probe_mode_value_accepts_closed_set(token):
    assert is_probe_mode_value(token)


def test_is_probe_mode_value_rejects_unknown():
    assert not is_probe_mode_value("UNKNOWN_MODE")
    assert not is_probe_mode_value(None)
    assert not is_probe_mode_value(7)


# ---------------------------------------------------------------------------
# Closed-set soak outcomes
# ---------------------------------------------------------------------------


_EXPECTED_SOAK_OUTCOME_TOKENS: tuple[str, ...] = (
    "COMPLETED_AT_DISPATCH_CAP",
    "COMPLETED_AT_WALL_CLOCK",
    "COMPLETED_AT_PASS_CAP",
    "BROKE_ON_SUPPRESSION_CIRCUIT",
    "BROKE_ON_REFUSED_READINESS",
    "BROKE_ON_FAILED_PASS",
    "NO_DISPATCHES_NO_EVENTS",
    "REFUSED_INVALID_BOUNDS",
)


def test_soak_outcome_values_contains_exactly_eight_tokens():
    assert set(SOAK_OUTCOME_VALUES) == set(
        _EXPECTED_SOAK_OUTCOME_TOKENS
    )
    assert len(SOAK_OUTCOME_VALUES) == 8


@pytest.mark.parametrize("token", _EXPECTED_SOAK_OUTCOME_TOKENS)
def test_each_soak_outcome_token_in_values(token):
    assert token in SOAK_OUTCOME_VALUES


@pytest.mark.parametrize("token", SOAK_OUTCOME_VALUES)
def test_is_soak_outcome_value_accepts_closed_set(token):
    assert is_soak_outcome_value(token)


def test_is_soak_outcome_value_rejects_unknown():
    assert not is_soak_outcome_value("UNKNOWN_OUTCOME")
    assert not is_soak_outcome_value(None)


def test_soak_outcome_individual_constants_locked():
    assert (
        SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP
        == "COMPLETED_AT_DISPATCH_CAP"
    )
    assert (
        SOAK_OUTCOME_COMPLETED_AT_WALL_CLOCK
        == "COMPLETED_AT_WALL_CLOCK"
    )
    assert (
        SOAK_OUTCOME_COMPLETED_AT_PASS_CAP
        == "COMPLETED_AT_PASS_CAP"
    )
    assert (
        SOAK_OUTCOME_BROKE_ON_SUPPRESSION_CIRCUIT
        == "BROKE_ON_SUPPRESSION_CIRCUIT"
    )
    assert (
        SOAK_OUTCOME_BROKE_ON_REFUSED_READINESS
        == "BROKE_ON_REFUSED_READINESS"
    )
    assert (
        SOAK_OUTCOME_BROKE_ON_FAILED_PASS
        == "BROKE_ON_FAILED_PASS"
    )
    assert (
        SOAK_OUTCOME_NO_DISPATCHES_NO_EVENTS
        == "NO_DISPATCHES_NO_EVENTS"
    )
    assert (
        SOAK_OUTCOME_REFUSED_INVALID_BOUNDS
        == "REFUSED_INVALID_BOUNDS"
    )


# ---------------------------------------------------------------------------
# Closed-set dedupe outcomes
# ---------------------------------------------------------------------------


def test_dedupe_outcome_values_contains_exactly_two_tokens():
    assert DEDUPE_OUTCOME_VALUES == (
        DEDUPE_OUTCOME_NEW,
        DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK,
    )


def test_dedupe_outcome_individual_tokens_locked():
    assert DEDUPE_OUTCOME_NEW == "NEW"
    assert DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK == (
        "DUPLICATE_SUPPRESSED_SOAK"
    )


@pytest.mark.parametrize("token", DEDUPE_OUTCOME_VALUES)
def test_is_dedupe_outcome_value_accepts_closed_set(token):
    assert is_dedupe_outcome_value(token)


def test_is_dedupe_outcome_value_rejects_unknown():
    assert not is_dedupe_outcome_value("UNKNOWN")
    assert not is_dedupe_outcome_value(None)


# ---------------------------------------------------------------------------
# Closed-set redaction status
# ---------------------------------------------------------------------------


def test_redaction_status_values_contains_safe_and_redacted():
    assert REDACTION_STATUS_VALUES == (
        REDACTION_STATUS_SAFE,
        REDACTION_STATUS_REDACTED,
    )


def test_redaction_status_individual_tokens_locked():
    assert REDACTION_STATUS_SAFE == "SAFE"
    assert REDACTION_STATUS_REDACTED == "REDACTED"


@pytest.mark.parametrize("token", REDACTION_STATUS_VALUES)
def test_is_redaction_status_value_accepts_closed_set(token):
    assert is_redaction_status_value(token)


# ---------------------------------------------------------------------------
# Filter enforcement status
# ---------------------------------------------------------------------------


def test_filter_enforcement_status_locked():
    assert (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# Recommended ranges + per-pass locks
# ---------------------------------------------------------------------------


def test_recommended_wall_clock_seconds_range():
    assert RECOMMENDED_WALL_CLOCK_SECONDS_MIN == 600
    assert RECOMMENDED_WALL_CLOCK_SECONDS_MAX == 1800


def test_recommended_max_dispatches_range():
    assert RECOMMENDED_MAX_DISPATCHES_MIN == 3
    assert RECOMMENDED_MAX_DISPATCHES_MAX == 5


def test_recommended_max_passes_range():
    assert RECOMMENDED_MAX_PASSES_MIN == 3
    assert RECOMMENDED_MAX_PASSES_MAX == 60


def test_recommended_max_consecutive_suppressions_range():
    assert RECOMMENDED_MAX_CONSECUTIVE_SUPPRESSIONS_MIN == 3
    assert RECOMMENDED_MAX_CONSECUTIVE_SUPPRESSIONS_MAX == 20


def test_recommended_heartbeat_cadence_seconds_range():
    assert RECOMMENDED_HEARTBEAT_CADENCE_SECONDS_MIN == 10
    assert RECOMMENDED_HEARTBEAT_CADENCE_SECONDS_MAX == 60


def test_per_pass_internal_locks():
    assert PER_PASS_MAX_EVENTS == 1
    assert PER_PASS_MAX_DISPATCHES == 1
    assert PER_PASS_MAX_TOTAL_RETRIES == 0


# ---------------------------------------------------------------------------
# Soak bounds: construction + validation
# ---------------------------------------------------------------------------


def _make_valid_bounds() -> Stage29_4SoakBounds:
    return build_soak_bounds(
        wall_clock_seconds=900,
        max_dispatches=3,
        max_passes=10,
        max_consecutive_suppressions=5,
        heartbeat_cadence_seconds=30,
    )


def test_build_soak_bounds_constructs_valid_record():
    bounds = _make_valid_bounds()
    assert isinstance(bounds, Stage29_4SoakBounds)
    assert bounds.wall_clock_seconds == 900
    assert bounds.max_dispatches == 3
    assert bounds.max_passes == 10
    assert bounds.max_total_retries == 0
    assert bounds.max_consecutive_suppressions == 5
    assert bounds.heartbeat_cadence_seconds == 30


def test_build_soak_bounds_rejects_zero_wall_clock():
    with pytest.raises(Stage29_4InvalidBoundsError) as excinfo:
        build_soak_bounds(
            wall_clock_seconds=0,
            max_dispatches=3,
            max_passes=10,
            max_consecutive_suppressions=5,
            heartbeat_cadence_seconds=30,
        )
    assert excinfo.value.field_name == "wall_clock_seconds"


def test_build_soak_bounds_rejects_negative_wall_clock():
    with pytest.raises(Stage29_4InvalidBoundsError):
        build_soak_bounds(
            wall_clock_seconds=-1,
            max_dispatches=3,
            max_passes=10,
            max_consecutive_suppressions=5,
            heartbeat_cadence_seconds=30,
        )


def test_build_soak_bounds_rejects_zero_max_dispatches():
    with pytest.raises(Stage29_4InvalidBoundsError):
        build_soak_bounds(
            wall_clock_seconds=600,
            max_dispatches=0,
            max_passes=10,
            max_consecutive_suppressions=5,
            heartbeat_cadence_seconds=30,
        )


def test_build_soak_bounds_rejects_zero_max_passes():
    with pytest.raises(Stage29_4InvalidBoundsError):
        build_soak_bounds(
            wall_clock_seconds=600,
            max_dispatches=3,
            max_passes=0,
            max_consecutive_suppressions=5,
            heartbeat_cadence_seconds=30,
        )


def test_build_soak_bounds_rejects_max_total_retries_one():
    with pytest.raises(Stage29_4InvalidBoundsError) as excinfo:
        build_soak_bounds(
            wall_clock_seconds=600,
            max_dispatches=3,
            max_passes=10,
            max_consecutive_suppressions=5,
            heartbeat_cadence_seconds=30,
            max_total_retries=1,
        )
    assert excinfo.value.field_name == "max_total_retries"


def test_build_soak_bounds_rejects_zero_max_suppressions():
    with pytest.raises(Stage29_4InvalidBoundsError):
        build_soak_bounds(
            wall_clock_seconds=600,
            max_dispatches=3,
            max_passes=10,
            max_consecutive_suppressions=0,
            heartbeat_cadence_seconds=30,
        )


def test_build_soak_bounds_rejects_zero_heartbeat_cadence():
    with pytest.raises(Stage29_4InvalidBoundsError):
        build_soak_bounds(
            wall_clock_seconds=600,
            max_dispatches=3,
            max_passes=10,
            max_consecutive_suppressions=5,
            heartbeat_cadence_seconds=0,
        )


def test_build_soak_bounds_rejects_bool_axes():
    with pytest.raises(Stage29_4InvalidBoundsError):
        build_soak_bounds(
            wall_clock_seconds=True,  # type: ignore[arg-type]
            max_dispatches=3,
            max_passes=10,
            max_consecutive_suppressions=5,
            heartbeat_cadence_seconds=30,
        )


def test_soak_bounds_field_names_locked():
    assert SOAK_BOUNDS_FIELD_NAMES == (
        "wall_clock_seconds",
        "max_dispatches",
        "max_passes",
        "max_total_retries",
        "max_consecutive_suppressions",
        "heartbeat_cadence_seconds",
    )


def test_soak_bounds_to_dict_round_trip():
    bounds = _make_valid_bounds()
    projected = soak_bounds_to_dict(bounds)
    assert projected == {
        "wall_clock_seconds": 900,
        "max_dispatches": 3,
        "max_passes": 10,
        "max_total_retries": 0,
        "max_consecutive_suppressions": 5,
        "heartbeat_cadence_seconds": 30,
    }


def test_bounds_within_recommended_ranges_happy_path():
    bounds = _make_valid_bounds()
    assert bounds_within_recommended_ranges(bounds)


def test_bounds_within_recommended_ranges_outside_minimum():
    bounds = build_soak_bounds(
        wall_clock_seconds=5,
        max_dispatches=1,
        max_passes=1,
        max_consecutive_suppressions=1,
        heartbeat_cadence_seconds=1,
    )
    assert not bounds_within_recommended_ranges(bounds)


# ---------------------------------------------------------------------------
# Soak dedupe key: construction + validation
# ---------------------------------------------------------------------------


def _make_valid_dedupe_key() -> Stage29_4SoakDedupeKey:
    return build_soak_dedupe_key(
        token_mint="SoMintAbc123",
        pair_quote_asset="SOL",
        event_kind="pumpswap_swap",
        ping_type="tradeable_private_ping",
        normalized_event_id="evt_abc_123",
    )


def test_build_soak_dedupe_key_constructs_valid_record():
    key = _make_valid_dedupe_key()
    assert isinstance(key, Stage29_4SoakDedupeKey)


def test_soak_dedupe_key_field_names_locked():
    assert SOAK_DEDUPE_KEY_FIELD_NAMES == (
        "token_mint",
        "pair_quote_asset",
        "event_kind",
        "ping_type",
        "normalized_event_id",
    )


@pytest.mark.parametrize(
    "field_name",
    SOAK_DEDUPE_KEY_FIELD_NAMES,
)
def test_build_soak_dedupe_key_rejects_empty_field(
    field_name,
):
    kwargs = {
        "token_mint": "SoMint1",
        "pair_quote_asset": "SOL",
        "event_kind": "pumpswap_swap",
        "ping_type": "tradeable_private_ping",
        "normalized_event_id": "evt1",
    }
    kwargs[field_name] = ""
    with pytest.raises(Stage29_4InvalidDedupeKeyError):
        build_soak_dedupe_key(**kwargs)


def test_build_soak_dedupe_key_rejects_url_like_token_mint():
    # URL-shaped inputs carry "://" and "/" which the locked
    # allowlist character class rejects immediately.
    with pytest.raises(Stage29_4InvalidDedupeKeyError):
        build_soak_dedupe_key(
            token_mint="h" + "ttps://example.com",
            pair_quote_asset="SOL",
            event_kind="pumpswap_swap",
            ping_type="tradeable_private_ping",
            normalized_event_id="evt1",
        )


def test_build_soak_dedupe_key_rejects_bearer_like_normalized_id():
    with pytest.raises(Stage29_4InvalidDedupeKeyError):
        build_soak_dedupe_key(
            token_mint="SoMint1",
            pair_quote_asset="SOL",
            event_kind="pumpswap_swap",
            ping_type="tradeable_private_ping",
            normalized_event_id="bearer_token",
        )


def test_canonical_soak_dedupe_key_tuple_is_deterministic():
    key = _make_valid_dedupe_key()
    tup = canonical_soak_dedupe_key_tuple(key)
    assert tup == (
        "SoMintAbc123",
        "SOL",
        "pumpswap_swap",
        "tradeable_private_ping",
        "evt_abc_123",
    )


def test_canonical_soak_dedupe_key_tuple_rejects_non_key():
    with pytest.raises(Stage29_4InvalidDedupeKeyError):
        canonical_soak_dedupe_key_tuple("not_a_key")  # type: ignore[arg-type]


def test_soak_dedupe_key_equal_when_fields_equal():
    a = _make_valid_dedupe_key()
    b = _make_valid_dedupe_key()
    assert a == b


def test_soak_dedupe_key_distinct_when_fields_differ():
    a = build_soak_dedupe_key(
        token_mint="SoMintAbc",
        pair_quote_asset="SOL",
        event_kind="pumpswap_swap",
        ping_type="tradeable_private_ping",
        normalized_event_id="evt1",
    )
    b = build_soak_dedupe_key(
        token_mint="SoMintXyz",
        pair_quote_asset="SOL",
        event_kind="pumpswap_swap",
        ping_type="tradeable_private_ping",
        normalized_event_id="evt1",
    )
    assert a != b


# ---------------------------------------------------------------------------
# Pass record: construction + validation
# ---------------------------------------------------------------------------


def _make_valid_pass_record() -> Stage29_4PassRecord:
    return build_pass_record(
        pass_index=1,
        stage29_3_outcome="DISPATCHED",
        stage29_3_refusal_reason="NONE",
        dedupe_outcome=DEDUPE_OUTCOME_NEW,
        events_seen=1,
        candidates_dispatched=1,
        candidates_suppressed=0,
        dispatch_success=1,
        dispatch_failure=0,
        consecutive_suppression_streak=0,
        dispatch_success_total_at_tick=1,
        duplicate_suppressed_soak_count_at_tick=0,
        elapsed_at_tick_seconds=12.5,
        utc_iso_timestamp="2026-05-25T17:00:00+00:00",
    )


def test_build_pass_record_constructs_valid_record():
    rec = _make_valid_pass_record()
    assert isinstance(rec, Stage29_4PassRecord)
    assert rec.schema_version == (
        STAGE29_4_HEARTBEAT_SCHEMA_VERSION
    )
    assert rec.filter_enforcement_status == (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    assert rec.redaction_status == REDACTION_STATUS_SAFE


def test_pass_record_field_names_locked():
    expected = (
        "schema_version",
        "pass_index",
        "stage29_3_outcome",
        "stage29_3_refusal_reason",
        "dedupe_outcome",
        "events_seen",
        "candidates_dispatched",
        "candidates_suppressed",
        "dispatch_success",
        "dispatch_failure",
        "consecutive_suppression_streak",
        "dispatch_success_total_at_tick",
        "duplicate_suppressed_soak_count_at_tick",
        "elapsed_at_tick_seconds",
        "utc_iso_timestamp",
        "filter_enforcement_status",
        "redaction_status",
    )
    assert PASS_RECORD_FIELD_NAMES == expected


def test_build_pass_record_rejects_zero_pass_index():
    with pytest.raises(Stage29_4InvalidPassRecordError):
        build_pass_record(
            pass_index=0,
            stage29_3_outcome="DISPATCHED",
            stage29_3_refusal_reason="NONE",
            dedupe_outcome=None,
            events_seen=1,
            candidates_dispatched=1,
            candidates_suppressed=0,
            dispatch_success=1,
            dispatch_failure=0,
            consecutive_suppression_streak=0,
            dispatch_success_total_at_tick=1,
            duplicate_suppressed_soak_count_at_tick=0,
            elapsed_at_tick_seconds=0.0,
            utc_iso_timestamp="2026-05-25T17:00:00+00:00",
        )


def test_build_pass_record_rejects_unsafe_outcome_token():
    with pytest.raises(Stage29_4InvalidPassRecordError):
        build_pass_record(
            pass_index=1,
            stage29_3_outcome="bad outcome with space",
            stage29_3_refusal_reason="NONE",
            dedupe_outcome=None,
            events_seen=0,
            candidates_dispatched=0,
            candidates_suppressed=0,
            dispatch_success=0,
            dispatch_failure=0,
            consecutive_suppression_streak=0,
            dispatch_success_total_at_tick=0,
            duplicate_suppressed_soak_count_at_tick=0,
            elapsed_at_tick_seconds=0.0,
            utc_iso_timestamp="2026-05-25T17:00:00+00:00",
        )


def test_build_pass_record_rejects_unknown_dedupe_outcome():
    with pytest.raises(Stage29_4InvalidPassRecordError):
        build_pass_record(
            pass_index=1,
            stage29_3_outcome="DISPATCHED",
            stage29_3_refusal_reason="NONE",
            dedupe_outcome="UNKNOWN_OUTCOME",
            events_seen=1,
            candidates_dispatched=1,
            candidates_suppressed=0,
            dispatch_success=1,
            dispatch_failure=0,
            consecutive_suppression_streak=0,
            dispatch_success_total_at_tick=1,
            duplicate_suppressed_soak_count_at_tick=0,
            elapsed_at_tick_seconds=0.0,
            utc_iso_timestamp="2026-05-25T17:00:00+00:00",
        )


def test_build_pass_record_rejects_unsafe_utc_iso():
    with pytest.raises(Stage29_4InvalidPassRecordError):
        build_pass_record(
            pass_index=1,
            stage29_3_outcome="DISPATCHED",
            stage29_3_refusal_reason="NONE",
            dedupe_outcome=None,
            events_seen=1,
            candidates_dispatched=1,
            candidates_suppressed=0,
            dispatch_success=1,
            dispatch_failure=0,
            consecutive_suppression_streak=0,
            dispatch_success_total_at_tick=1,
            duplicate_suppressed_soak_count_at_tick=0,
            elapsed_at_tick_seconds=0.0,
            utc_iso_timestamp="not-a-utc-iso-shape",
        )


def test_build_pass_record_rejects_negative_elapsed():
    with pytest.raises(Stage29_4InvalidPassRecordError):
        build_pass_record(
            pass_index=1,
            stage29_3_outcome="DISPATCHED",
            stage29_3_refusal_reason="NONE",
            dedupe_outcome=None,
            events_seen=1,
            candidates_dispatched=1,
            candidates_suppressed=0,
            dispatch_success=1,
            dispatch_failure=0,
            consecutive_suppression_streak=0,
            dispatch_success_total_at_tick=1,
            duplicate_suppressed_soak_count_at_tick=0,
            elapsed_at_tick_seconds=-1.0,
            utc_iso_timestamp="2026-05-25T17:00:00+00:00",
        )


def test_pass_record_to_dict_field_ordering():
    rec = _make_valid_pass_record()
    projected = pass_record_to_dict(rec)
    assert list(projected.keys()) == list(PASS_RECORD_FIELD_NAMES)


# ---------------------------------------------------------------------------
# Pass result envelope
# ---------------------------------------------------------------------------


class _StubSmokeResult:
    def __init__(self) -> None:
        self.tradeable_smoke_outcome = "DISPATCHED"
        self.tradeable_smoke_refusal_reason = "NONE"
        self.events_seen = 1
        self.candidates_dispatched = 1
        self.candidates_suppressed = 0
        self.dispatch_success = 1
        self.dispatch_failure = 0


def test_build_pass_result_with_key_constructs_envelope():
    smoke = _StubSmokeResult()
    key = _make_valid_dedupe_key()
    envelope = build_pass_result(
        smoke_result=smoke, dedupe_key=key,
    )
    assert isinstance(envelope, Stage29_4PassResult)
    assert envelope.smoke_result is smoke
    assert envelope.dedupe_key == key


def test_build_pass_result_without_key_constructs_envelope():
    smoke = _StubSmokeResult()
    envelope = build_pass_result(smoke_result=smoke)
    assert envelope.dedupe_key is None


def test_build_pass_result_rejects_invalid_key_type():
    smoke = _StubSmokeResult()
    with pytest.raises(Stage29_4SoakError):
        build_pass_result(
            smoke_result=smoke,
            dedupe_key="not_a_key",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Soak summary: construction + validation
# ---------------------------------------------------------------------------


def _make_valid_summary() -> Stage29_4SoakSummary:
    bounds = _make_valid_bounds()
    return build_soak_summary(
        soak_outcome=SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP,
        bounds=bounds,
        passes_attempted=3,
        dispatch_success_total=3,
        elapsed_wall_clock_seconds=42.5,
        start_utc_iso="2026-05-25T17:00:00+00:00",
        end_utc_iso="2026-05-25T17:00:42+00:00",
    )


def test_build_soak_summary_constructs_valid_record():
    record = _make_valid_summary()
    assert isinstance(record, Stage29_4SoakSummary)
    assert record.soak_outcome == (
        SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP
    )
    assert record.filter_enforcement_status == (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    assert record.redaction_status == REDACTION_STATUS_SAFE
    assert record.schema_version == (
        STAGE29_4_SOAK_SUMMARY_SCHEMA_VERSION
    )
    assert record.bounds_within_recommended_ranges is True


def test_soak_summary_field_names_locked():
    expected = (
        "schema_version",
        "soak_outcome",
        "passes_attempted",
        "dispatch_success_total",
        "dispatch_failure_total",
        "duplicate_suppressed_soak_count",
        "events_seen_total",
        "suppressed_unknown_pair_count",
        "suppressed_disagree_pair_count",
        "suppressed_usdc_observe_only_count",
        "suppressed_missing_price_count",
        "suppressed_stale_price_count",
        "suppressed_malformed_count",
        "no_event_received_count",
        "consecutive_suppression_streak_max",
        "elapsed_wall_clock_seconds",
        "start_utc_iso",
        "end_utc_iso",
        "bounds",
        "bounds_within_recommended_ranges",
        "filter_enforcement_status",
        "redaction_status",
    )
    assert SOAK_SUMMARY_FIELD_NAMES == expected


def test_soak_summary_counter_field_names_include_per_suppression():
    for name in SUPPRESSED_PER_OUTCOME_COUNTER_FIELD_NAMES:
        assert name in SOAK_SUMMARY_COUNTER_FIELD_NAMES


def test_build_soak_summary_rejects_unknown_outcome():
    bounds = _make_valid_bounds()
    with pytest.raises(Stage29_4InvalidSoakSummaryError):
        build_soak_summary(
            soak_outcome="UNKNOWN_OUTCOME",
            bounds=bounds,
            start_utc_iso="2026-05-25T17:00:00+00:00",
            end_utc_iso="2026-05-25T17:00:00+00:00",
        )


def test_build_soak_summary_rejects_negative_counter():
    bounds = _make_valid_bounds()
    with pytest.raises(Stage29_4InvalidSoakSummaryError):
        build_soak_summary(
            soak_outcome=SOAK_OUTCOME_COMPLETED_AT_PASS_CAP,
            bounds=bounds,
            passes_attempted=-1,
            start_utc_iso="2026-05-25T17:00:00+00:00",
            end_utc_iso="2026-05-25T17:00:00+00:00",
        )


def test_build_soak_summary_rejects_invalid_bounds_type():
    with pytest.raises(Stage29_4InvalidSoakSummaryError):
        build_soak_summary(
            soak_outcome=SOAK_OUTCOME_COMPLETED_AT_PASS_CAP,
            bounds="not a bounds",  # type: ignore[arg-type]
            start_utc_iso="2026-05-25T17:00:00+00:00",
            end_utc_iso="2026-05-25T17:00:00+00:00",
        )


def test_soak_summary_to_dict_preserves_bounds_projection():
    record = _make_valid_summary()
    projected = soak_summary_to_dict(record)
    assert projected["bounds"] == soak_bounds_to_dict(
        record.bounds,
    )
    assert projected["soak_outcome"] == (
        SOAK_OUTCOME_COMPLETED_AT_DISPATCH_CAP
    )
    assert projected["filter_enforcement_status"] == (
        FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
    assert projected["redaction_status"] == (
        REDACTION_STATUS_SAFE
    )
    assert list(projected.keys()) == list(
        SOAK_SUMMARY_FIELD_NAMES
    )


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


def test_invalid_bounds_error_is_soak_error():
    err = Stage29_4InvalidBoundsError(
        field_name="wall_clock_seconds", reason="X",
    )
    assert isinstance(err, Stage29_4SoakError)
    assert err.field_name == "wall_clock_seconds"
    assert err.reason == "X"


def test_invalid_dedupe_key_error_is_soak_error():
    err = Stage29_4InvalidDedupeKeyError(
        field_name="token_mint", reason="Y",
    )
    assert isinstance(err, Stage29_4SoakError)


def test_invalid_pass_record_error_is_soak_error():
    err = Stage29_4InvalidPassRecordError(
        field_name="pass_index", reason="Z",
    )
    assert isinstance(err, Stage29_4SoakError)


def test_invalid_soak_summary_error_is_soak_error():
    err = Stage29_4InvalidSoakSummaryError(
        field_name="soak_outcome", reason="W",
    )
    assert isinstance(err, Stage29_4SoakError)


def test_soak_error_carries_only_safe_token():
    err = Stage29_4SoakError("CLOSED_SET_REASON")
    assert err.reason == "CLOSED_SET_REASON"
    # repr / str must not carry secrets; it only carries the
    # closed-set token.
    assert "CLOSED_SET_REASON" in str(err)
