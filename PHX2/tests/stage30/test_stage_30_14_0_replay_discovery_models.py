"""Stage 30.14.0 replay-discovery model tests.

Offline / pure. Asserts the leaf model layer's vocabulary, predicates, immutable carriers,
and field-name helpers. No live call, no provider, no env read, no file write.
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.stage30.stage30_14_0_replay_discovery_models import (
    STAGE30_14_0_SCHEMA_VERSION,
    STAGE30_14_MAX_FAKE_DISPATCHES,
    STAGE30_14_MAX_RECHECKS,
    STAGE30_14_MAX_SEED,
    STAGE30_14_REDACTED_UNSAFE_ID,
    STAGE30_14_REDACTION_STATUS_REDACTED,
    STAGE30_14_REDACTION_STATUS_VIOLATION,
    STAGE30_14_REDACTION_STATUSES,
    Stage30_14DispatchTrace,
    Stage30_14ShadowDispatchResult,
    dispatch_trace_field_names,
    is_locked_cap,
    is_nonblank_str,
    is_safe_echo_id,
    shadow_dispatch_result_field_names,
)


def _trace() -> Stage30_14DispatchTrace:
    return Stage30_14DispatchTrace(
        discovered_mint="MintAbc123pump",
        dispatched_mint="MintAbc123pump",
        mint_traces_through=True,
        seeds_accepted=1,
        rechecks_bridged=1,
        dispatched=1,
        would_send_recorded=1,
        real_send_performed=False,
        real_send_guard_invoked=False,
        transport_client_kind="Stage30_11_5RecordingFakeTransportClient",
        ledger_kind="InMemoryPingDedupeLedger",
        redaction_status=STAGE30_14_REDACTION_STATUS_REDACTED,
    )


# ---------------------------------------------------------------------------
# 1. Caps + locked-cap predicate
# ---------------------------------------------------------------------------


def test_caps_are_all_one() -> None:
    assert STAGE30_14_MAX_SEED == 1
    assert STAGE30_14_MAX_RECHECKS == 1
    assert STAGE30_14_MAX_FAKE_DISPATCHES == 1


def test_is_locked_cap_accepts_only_the_exact_cap() -> None:
    assert is_locked_cap(1, 1) is True
    assert is_locked_cap(2, 1) is False
    assert is_locked_cap(0, 1) is False


def test_is_locked_cap_rejects_bool_and_non_int() -> None:
    assert is_locked_cap(True, 1) is False
    assert is_locked_cap(False, 1) is False
    assert is_locked_cap("1", 1) is False
    assert is_locked_cap(1.0, 1) is False
    assert is_locked_cap(None, 1) is False


# ---------------------------------------------------------------------------
# 2. Redaction vocabulary
# ---------------------------------------------------------------------------


def test_redaction_statuses_are_the_two_tokens() -> None:
    assert STAGE30_14_REDACTION_STATUSES == (
        STAGE30_14_REDACTION_STATUS_REDACTED,
        STAGE30_14_REDACTION_STATUS_VIOLATION,
    )
    assert STAGE30_14_REDACTION_STATUS_REDACTED == "REDACTED"
    assert STAGE30_14_REDACTION_STATUS_VIOLATION == "REDACTION_VIOLATION"
    assert STAGE30_14_REDACTED_UNSAFE_ID == "REDACTED_UNSAFE_ID"


def test_schema_version_is_pinned() -> None:
    assert STAGE30_14_0_SCHEMA_VERSION == (
        "stage30_14_0_v0_real_discovery_replay_shadow_dispatch"
    )


# ---------------------------------------------------------------------------
# 3. Safe-shape predicates
# ---------------------------------------------------------------------------


def test_is_nonblank_str() -> None:
    assert is_nonblank_str("x") is True
    assert is_nonblank_str("") is False
    assert is_nonblank_str("   ") is False
    assert is_nonblank_str(None) is False
    assert is_nonblank_str(1) is False


def test_is_safe_echo_id() -> None:
    assert is_safe_echo_id("MintAbc123pump") is True
    assert is_safe_echo_id("cand_id-1") is True
    assert is_safe_echo_id("") is False
    assert is_safe_echo_id("a b") is False
    assert is_safe_echo_id("a/b") is False
    assert is_safe_echo_id("a:b") is False
    assert is_safe_echo_id("x" * 129) is False
    assert is_safe_echo_id(None) is False


# ---------------------------------------------------------------------------
# 4. Immutable carriers + field-name helpers
# ---------------------------------------------------------------------------


def test_dispatch_trace_field_names() -> None:
    assert dispatch_trace_field_names() == (
        "discovered_mint",
        "dispatched_mint",
        "mint_traces_through",
        "seeds_accepted",
        "rechecks_bridged",
        "dispatched",
        "would_send_recorded",
        "real_send_performed",
        "real_send_guard_invoked",
        "transport_client_kind",
        "ledger_kind",
        "redaction_status",
    )


def test_shadow_dispatch_result_field_names() -> None:
    assert shadow_dispatch_result_field_names() == (
        "seed_result",
        "dry_run",
        "trace",
    )


def test_dispatch_trace_is_frozen() -> None:
    trace = _trace()
    with pytest.raises(dataclasses.FrozenInstanceError):
        trace.dispatched = 99  # type: ignore[misc]


def test_shadow_dispatch_result_carries_components() -> None:
    trace = _trace()
    result = Stage30_14ShadowDispatchResult(
        seed_result="SEED", dry_run="DRY", trace=trace
    )
    assert result.seed_result == "SEED"
    assert result.dry_run == "DRY"
    assert result.trace is trace
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.seed_result = "X"  # type: ignore[misc]
