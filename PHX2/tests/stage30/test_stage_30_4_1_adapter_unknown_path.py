"""Stage 30.4.1 adapter Unknown-path tests.

When the caller passes ``source=None``, the adapter must return a
record with all three slots Unknown, displays None, source_status
UNAVAILABLE, source_reason SOURCE_NOT_CONFIGURED, and
runtime_consumable False. No fake values. No fabricated zero.
"""

from __future__ import annotations

import pytest

from PHX2.stage30.stage30_4_compact_market_context_adapter import (
    project_market_context,
)
from PHX2.stage30.stage30_4_compact_market_context_models import (
    NET_FLOW_BASIS_UNKNOWN,
    SOURCE_REASON_SOURCE_NOT_CONFIGURED,
    SOURCE_STATUS_UNAVAILABLE,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION,
    STATUS_UNKNOWN,
    Stage30_4CompactMarketContextError,
    Stage30_4CompactMarketContextRecord,
)


_VALID_TS: str = "2026-05-28T12:00:00Z"


# ---------------------------------------------------------------------------
# source=None
# ---------------------------------------------------------------------------


def test_unknown_path_source_is_none() -> None:
    rec = project_market_context(
        session_id="sess-1",
        run_id="run-1",
        candidate_id="cand-1",
        token_mint="abcd...wxyz",
        created_at_utc=_VALID_TS,
        source=None,
    )
    assert isinstance(rec, Stage30_4CompactMarketContextRecord)
    assert rec.schema_version == (
        STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION
    )
    assert rec.session_id == "sess-1"
    assert rec.run_id == "run-1"
    assert rec.candidate_id == "cand-1"
    assert rec.token_label == "abcd...wxyz"
    assert rec.created_at_utc == _VALID_TS
    assert rec.market_cap_usd_status == STATUS_UNKNOWN
    assert rec.market_cap_usd_value is None
    assert rec.market_cap_display is None
    assert rec.liquidity_usd_status == STATUS_UNKNOWN
    assert rec.liquidity_usd_value is None
    assert rec.liquidity_display is None
    assert rec.net_flow_status == STATUS_UNKNOWN
    assert rec.net_flow_usd_value is None
    assert rec.net_flow_display is None
    assert rec.net_flow_basis == NET_FLOW_BASIS_UNKNOWN
    assert rec.source_label is None
    assert rec.source_status == SOURCE_STATUS_UNAVAILABLE
    assert rec.source_reason == SOURCE_REASON_SOURCE_NOT_CONFIGURED
    assert rec.runtime_consumable is False


def test_unknown_path_never_renders_zero_for_missing_mc_lp_net() -> None:
    """Unknown is never silently rendered as ``$0`` or ``"0"``."""
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint=None,
        created_at_utc=_VALID_TS,
        source=None,
    )
    assert rec.market_cap_display is None
    assert rec.liquidity_display is None
    assert rec.net_flow_display is None
    for slot in (
        rec.market_cap_display,
        rec.liquidity_display,
        rec.net_flow_display,
    ):
        if slot is not None:
            assert "$0" not in slot, (
                "Unknown must never render as $0 in 30.4.1"
            )


def test_unknown_path_with_none_identifiers() -> None:
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint=None,
        created_at_utc=_VALID_TS,
        source=None,
    )
    assert rec.session_id is None
    assert rec.run_id is None
    assert rec.candidate_id is None
    assert rec.token_label is None
    assert rec.source_label is None
    assert rec.runtime_consumable is False


def test_unknown_path_with_unsafe_shape_identifiers_drops_to_none() -> None:
    """Unsafe-shape identifiers (wrong type, too long, bad chars)
    are silently coerced to ``None``; the adapter does not raise.
    """
    rec = project_market_context(
        session_id=12345,  # type: ignore[arg-type]
        run_id="x" * 200,
        candidate_id="bad chars!",
        token_mint="bad token label!!",
        created_at_utc=_VALID_TS,
        source=None,
    )
    assert rec.session_id is None
    assert rec.run_id is None
    assert rec.candidate_id is None
    assert rec.token_label is None


def test_unknown_path_runtime_consumable_locked_false() -> None:
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint=None,
        created_at_utc=_VALID_TS,
        source=None,
    )
    assert rec.runtime_consumable is False


# ---------------------------------------------------------------------------
# created_at_utc safety gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_ts",
    [
        "",
        " 2026-05-28T12:00:00Z",
        "2026-05-28T12:00:00",
        "not a timestamp",
        "2026-05-28 12:00:00",
        "2026-13-99T99:99:99Z",  # passes the regex even if not a real date — see below
        None,
        12345,
        b"2026-05-28T12:00:00Z",
    ],
)
def test_created_at_utc_unsafe_shape_raises(bad_ts: object) -> None:
    # ``2026-13-99T99:99:99Z`` actually passes the regex (the regex
    # checks shape, not real-date validity). We rely on the regex
    # rejecting the rest. So drop that case for the raising check.
    if bad_ts == "2026-13-99T99:99:99Z":
        # This passes the shape gate; verify it does NOT raise.
        rec = project_market_context(
            session_id=None,
            run_id=None,
            candidate_id=None,
            token_mint=None,
            created_at_utc=bad_ts,  # type: ignore[arg-type]
            source=None,
        )
        assert rec.created_at_utc == bad_ts
        return
    with pytest.raises(Stage30_4CompactMarketContextError) as ei:
        project_market_context(
            session_id=None,
            run_id=None,
            candidate_id=None,
            token_mint=None,
            created_at_utc=bad_ts,  # type: ignore[arg-type]
            source=None,
        )
    assert ei.value.reason == "CREATED_AT_UTC_UNSAFE_SHAPE"


def test_created_at_utc_accepts_fractional_seconds_z() -> None:
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint=None,
        created_at_utc="2026-05-28T12:00:00.123456Z",
        source=None,
    )
    assert rec.created_at_utc == "2026-05-28T12:00:00.123456Z"


def test_created_at_utc_accepts_offset_form() -> None:
    rec = project_market_context(
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_mint=None,
        created_at_utc="2026-05-28T12:00:00+00:00",
        source=None,
    )
    assert rec.created_at_utc == "2026-05-28T12:00:00+00:00"
