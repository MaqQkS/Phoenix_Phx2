"""Stage 30.4.1 compact market context model-layer tests.

Pure-Python tests over the closed-set vocabularies and the
immutable record shape. No live network, no env, no Discord.
"""

from __future__ import annotations

from typing import Tuple

from PHX2.stage30.stage30_4_compact_market_context_models import (
    FORBIDDEN_RECORD_FIELD_NAMES,
    NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
    NET_FLOW_BASIS_UNKNOWN,
    NET_FLOW_BASIS_VALUES,
    NET_FLOW_BASIS_VOLUME_USD_DELTA_24H,
    SOURCE_REASON_MC_VALUE_INVALID,
    SOURCE_REASON_LP_VALUE_INVALID,
    SOURCE_REASON_NET_VALUE_INVALID,
    SOURCE_REASON_SOURCE_BASIS_INVALID,
    SOURCE_REASON_SOURCE_NOT_CONFIGURED,
    SOURCE_REASON_SOURCE_OBSERVATION_TIMESTAMP_MALFORMED,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_REASON_SOURCE_REASON_MALFORMED,
    SOURCE_REASON_SOURCE_STALE,
    SOURCE_REASON_VALUES,
    SOURCE_STATUS_ERROR,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_STALE,
    SOURCE_STATUS_UNAVAILABLE,
    SOURCE_STATUS_VALUES,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION,
    STAGE30_4_1_MINOR_VERSION,
    STATUS_ERROR,
    STATUS_KNOWN,
    STATUS_STALE,
    STATUS_UNKNOWN,
    STATUS_VALUES,
    Stage30_4CompactMarketContextError,
    Stage30_4CompactMarketContextRecord,
    is_forbidden_record_field_name,
    is_net_flow_basis_value,
    is_source_reason_value,
    is_source_status_value,
    is_status_value,
)


# ---------------------------------------------------------------------------
# Schema version + basenames
# ---------------------------------------------------------------------------


def test_minor_version_pinned() -> None:
    assert STAGE30_4_1_MINOR_VERSION == "30.4.1"


def test_schema_version_pinned() -> None:
    assert (
        STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION
        == "stage30_4_1_v0_compact_market_context"
    )


def test_artifact_basename_pinned() -> None:
    assert (
        STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME
        == "stage30_4_compact_market_context.jsonl"
    )


# ---------------------------------------------------------------------------
# STATUS closed set
# ---------------------------------------------------------------------------


def test_status_closed_set_pinned() -> None:
    assert STATUS_UNKNOWN == "UNKNOWN"
    assert STATUS_KNOWN == "KNOWN"
    assert STATUS_ERROR == "ERROR"
    assert STATUS_STALE == "STALE"
    assert STATUS_VALUES == (
        STATUS_UNKNOWN,
        STATUS_KNOWN,
        STATUS_ERROR,
        STATUS_STALE,
    )


def test_is_status_value_accepts_each_token() -> None:
    for token in STATUS_VALUES:
        assert is_status_value(token)


def test_is_status_value_rejects_synonyms_and_nontypes() -> None:
    assert not is_status_value("unknown")
    assert not is_status_value("ok")
    assert not is_status_value("")
    assert not is_status_value(None)
    assert not is_status_value(0)
    assert not is_status_value(False)
    assert not is_status_value(b"KNOWN")


# ---------------------------------------------------------------------------
# SOURCE_STATUS closed set
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


def test_is_source_status_value_accepts_each_token() -> None:
    for token in SOURCE_STATUS_VALUES:
        assert is_source_status_value(token)


def test_is_source_status_value_rejects_synonyms() -> None:
    assert not is_source_status_value("present")
    assert not is_source_status_value("KNOWN")
    assert not is_source_status_value(None)


# ---------------------------------------------------------------------------
# SOURCE_REASON closed set
# ---------------------------------------------------------------------------


def test_source_reason_closed_set_pinned() -> None:
    assert SOURCE_REASON_SOURCE_NOT_CONFIGURED == "SOURCE_NOT_CONFIGURED"
    assert SOURCE_REASON_SOURCE_PRESENT == "SOURCE_PRESENT"
    assert SOURCE_REASON_SOURCE_STALE == "SOURCE_STALE"
    assert SOURCE_REASON_MC_VALUE_INVALID == "MC_VALUE_INVALID"
    assert SOURCE_REASON_LP_VALUE_INVALID == "LP_VALUE_INVALID"
    assert SOURCE_REASON_NET_VALUE_INVALID == "NET_VALUE_INVALID"
    assert SOURCE_REASON_SOURCE_OBSERVATION_TIMESTAMP_MALFORMED == (
        "SOURCE_OBSERVATION_TIMESTAMP_MALFORMED"
    )
    assert SOURCE_REASON_SOURCE_BASIS_INVALID == (
        "SOURCE_BASIS_INVALID"
    )
    assert SOURCE_REASON_SOURCE_REASON_MALFORMED == (
        "SOURCE_REASON_MALFORMED"
    )


def test_source_reason_values_contains_all_tokens() -> None:
    expected = {
        SOURCE_REASON_SOURCE_NOT_CONFIGURED,
        SOURCE_REASON_SOURCE_PRESENT,
        SOURCE_REASON_SOURCE_STALE,
        SOURCE_REASON_MC_VALUE_INVALID,
        SOURCE_REASON_LP_VALUE_INVALID,
        SOURCE_REASON_NET_VALUE_INVALID,
        SOURCE_REASON_SOURCE_OBSERVATION_TIMESTAMP_MALFORMED,
        SOURCE_REASON_SOURCE_BASIS_INVALID,
        SOURCE_REASON_SOURCE_REASON_MALFORMED,
    }
    assert set(SOURCE_REASON_VALUES) == expected


def test_is_source_reason_value_accepts_each_token() -> None:
    for token in SOURCE_REASON_VALUES:
        assert is_source_reason_value(token)


def test_is_source_reason_value_rejects_synonyms() -> None:
    assert not is_source_reason_value("present")
    assert not is_source_reason_value("unknown")
    assert not is_source_reason_value(None)
    assert not is_source_reason_value("")


# ---------------------------------------------------------------------------
# NET_FLOW_BASIS closed set
# ---------------------------------------------------------------------------


def test_net_flow_basis_closed_set_pinned() -> None:
    assert NET_FLOW_BASIS_UNKNOWN == "UNKNOWN"
    assert NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H == (
        "BUY_SELL_USD_DELTA_24H"
    )
    assert NET_FLOW_BASIS_VOLUME_USD_DELTA_24H == (
        "VOLUME_USD_DELTA_24H"
    )
    assert NET_FLOW_BASIS_VALUES == (
        NET_FLOW_BASIS_UNKNOWN,
        NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
        NET_FLOW_BASIS_VOLUME_USD_DELTA_24H,
    )


def test_is_net_flow_basis_value_accepts_each_token() -> None:
    for token in NET_FLOW_BASIS_VALUES:
        assert is_net_flow_basis_value(token)


def test_is_net_flow_basis_value_rejects_synonyms() -> None:
    assert not is_net_flow_basis_value("VOLUME")
    assert not is_net_flow_basis_value("buy_sell_usd_delta_24h")
    assert not is_net_flow_basis_value(None)


# ---------------------------------------------------------------------------
# Record shape
# ---------------------------------------------------------------------------


_EXPECTED_RECORD_FIELDS: Tuple[str, ...] = (
    "schema_version",
    "session_id",
    "run_id",
    "candidate_id",
    "token_label",
    "created_at_utc",
    "market_cap_usd_status",
    "market_cap_usd_value",
    "market_cap_display",
    "liquidity_usd_status",
    "liquidity_usd_value",
    "liquidity_display",
    "net_flow_status",
    "net_flow_usd_value",
    "net_flow_display",
    "net_flow_basis",
    "source_label",
    "source_status",
    "source_reason",
    "runtime_consumable",
)


def test_record_has_exactly_expected_fields() -> None:
    assert (
        Stage30_4CompactMarketContextRecord._fields
        == _EXPECTED_RECORD_FIELDS
    )


def test_record_constructs_with_minimal_unknown_shape() -> None:
    rec = Stage30_4CompactMarketContextRecord(
        schema_version=(
            STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION
        ),
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_label=None,
        created_at_utc="2026-05-28T12:00:00Z",
        market_cap_usd_status=STATUS_UNKNOWN,
        market_cap_usd_value=None,
        market_cap_display=None,
        liquidity_usd_status=STATUS_UNKNOWN,
        liquidity_usd_value=None,
        liquidity_display=None,
        net_flow_status=STATUS_UNKNOWN,
        net_flow_usd_value=None,
        net_flow_display=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label=None,
        source_status=SOURCE_STATUS_UNAVAILABLE,
        source_reason=SOURCE_REASON_SOURCE_NOT_CONFIGURED,
        runtime_consumable=False,
    )
    assert rec.runtime_consumable is False
    assert rec.market_cap_display is None
    assert rec.net_flow_basis == NET_FLOW_BASIS_UNKNOWN


def test_record_is_immutable_namedtuple() -> None:
    rec = Stage30_4CompactMarketContextRecord(
        schema_version="x",
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_label=None,
        created_at_utc="2026-05-28T12:00:00Z",
        market_cap_usd_status=STATUS_UNKNOWN,
        market_cap_usd_value=None,
        market_cap_display=None,
        liquidity_usd_status=STATUS_UNKNOWN,
        liquidity_usd_value=None,
        liquidity_display=None,
        net_flow_status=STATUS_UNKNOWN,
        net_flow_usd_value=None,
        net_flow_display=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label=None,
        source_status=SOURCE_STATUS_UNAVAILABLE,
        source_reason=SOURCE_REASON_SOURCE_NOT_CONFIGURED,
        runtime_consumable=False,
    )
    try:
        rec.runtime_consumable = True
    except AttributeError:
        pass
    else:
        raise AssertionError(
            "Stage30_4CompactMarketContextRecord must be immutable"
        )


# ---------------------------------------------------------------------------
# Forbidden field-name guard
# ---------------------------------------------------------------------------


def test_no_field_on_record_matches_forbidden_vocabulary() -> None:
    """Every field name on Stage30_4CompactMarketContextRecord must
    pass the forbidden-field-name guard.
    """
    for name in Stage30_4CompactMarketContextRecord._fields:
        assert not is_forbidden_record_field_name(name), (
            f"Stage30_4CompactMarketContextRecord field {name!r} "
            f"is on the forbidden-name vocabulary"
        )


def test_forbidden_field_name_guard_matches_substrings() -> None:
    """The guard must catch any field name that *contains* one of
    the forbidden substrings.
    """
    # Compute live needles from the manifest tuple so the test
    # source doesn't carry the bare strings.
    for needle in FORBIDDEN_RECORD_FIELD_NAMES:
        assert is_forbidden_record_field_name(needle), (
            f"forbidden-name guard must trip on its own vocabulary: "
            f"{needle!r}"
        )
        assert is_forbidden_record_field_name(f"prefix_{needle}"), (
            f"forbidden-name guard must trip on suffix-bearing "
            f"name: prefix_{needle}"
        )
        assert is_forbidden_record_field_name(f"{needle}_suffix"), (
            f"forbidden-name guard must trip on prefix-bearing "
            f"name: {needle}_suffix"
        )


def test_forbidden_field_name_guard_non_strings_return_false() -> None:
    assert not is_forbidden_record_field_name(None)
    assert not is_forbidden_record_field_name(123)
    assert not is_forbidden_record_field_name(b"webhook")
    assert not is_forbidden_record_field_name([])


def test_forbidden_field_name_guard_is_case_insensitive() -> None:
    # Use a split-literal so this test source text doesn't carry
    # the bare needle.
    assert is_forbidden_record_field_name("A" + "PI_KEY")
    assert is_forbidden_record_field_name("B" + "EARER")


# ---------------------------------------------------------------------------
# Module-local exception
# ---------------------------------------------------------------------------


def test_module_exception_carries_reason_token() -> None:
    err = Stage30_4CompactMarketContextError("RECORD_INVALID_TYPE")
    assert err.reason == "RECORD_INVALID_TYPE"
    assert "RECORD_INVALID_TYPE" in str(err)


# ---------------------------------------------------------------------------
# runtime_consumable hard-locked at False in 30.4.1
# ---------------------------------------------------------------------------


def test_record_runtime_consumable_must_be_bool() -> None:
    """Stage 30.4.1 records carry ``runtime_consumable`` as a
    ``bool``. The field is hard-locked to ``False`` by the Stage
    30.4.1 adapter, but the model layer accepts any ``bool`` so
    that a future Stage 30.4.2 / 30.4.3 can flip it without a
    model-layer change.
    """
    # The record itself is structurally a bool field; the
    # "hard-locked False" invariant is enforced by the adapter, not
    # the model. Constructing with True is structurally legal here.
    rec = Stage30_4CompactMarketContextRecord(
        schema_version="x",
        session_id=None,
        run_id=None,
        candidate_id=None,
        token_label=None,
        created_at_utc="2026-05-28T12:00:00Z",
        market_cap_usd_status=STATUS_UNKNOWN,
        market_cap_usd_value=None,
        market_cap_display=None,
        liquidity_usd_status=STATUS_UNKNOWN,
        liquidity_usd_value=None,
        liquidity_display=None,
        net_flow_status=STATUS_UNKNOWN,
        net_flow_usd_value=None,
        net_flow_display=None,
        net_flow_basis=NET_FLOW_BASIS_UNKNOWN,
        source_label=None,
        source_status=SOURCE_STATUS_UNAVAILABLE,
        source_reason=SOURCE_REASON_SOURCE_NOT_CONFIGURED,
        runtime_consumable=True,
    )
    assert isinstance(rec.runtime_consumable, bool)
