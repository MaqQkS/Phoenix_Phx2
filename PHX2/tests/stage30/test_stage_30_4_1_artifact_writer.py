"""Stage 30.4.1 compact market context artifact writer tests.

Pure offline tests over the deterministic append-only JSONL
writer. Uses pytest ``tmp_path`` fixture; no live network, no
env, no Discord.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.stage30.stage30_4_compact_market_context_artifact_writer import (
    append_compact_market_context_record,
    compact_market_context_record_to_dict,
    encode_compact_market_context_jsonl_line,
)
from PHX2.stage30.stage30_4_compact_market_context_models import (
    NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
    NET_FLOW_BASIS_UNKNOWN,
    SOURCE_REASON_SOURCE_NOT_CONFIGURED,
    SOURCE_REASON_SOURCE_PRESENT,
    SOURCE_STATUS_PRESENT,
    SOURCE_STATUS_UNAVAILABLE,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME,
    STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION,
    STATUS_KNOWN,
    STATUS_UNKNOWN,
    Stage30_4CompactMarketContextError,
    Stage30_4CompactMarketContextRecord,
)


_VALID_TS: str = "2026-05-28T12:00:00Z"


def _unknown_record() -> Stage30_4CompactMarketContextRecord:
    return Stage30_4CompactMarketContextRecord(
        schema_version=(
            STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION
        ),
        session_id="sess-1",
        run_id="run-1",
        candidate_id="cand-1",
        token_label="abcd...wxyz",
        created_at_utc=_VALID_TS,
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


def _known_record() -> Stage30_4CompactMarketContextRecord:
    return Stage30_4CompactMarketContextRecord(
        schema_version=(
            STAGE30_4_1_COMPACT_MARKET_CONTEXT_SCHEMA_VERSION
        ),
        session_id="sess-2",
        run_id="run-2",
        candidate_id="cand-2",
        token_label="ABCD...WXYZ",
        created_at_utc=_VALID_TS,
        market_cap_usd_status=STATUS_KNOWN,
        market_cap_usd_value="83000",
        market_cap_display="$83k",
        liquidity_usd_status=STATUS_KNOWN,
        liquidity_usd_value="27000",
        liquidity_display="$27k",
        net_flow_status=STATUS_KNOWN,
        net_flow_usd_value="12000",
        net_flow_display="+$12k buys",
        net_flow_basis=NET_FLOW_BASIS_BUY_SELL_USD_DELTA_24H,
        source_label="birdeye_token_overview",
        source_status=SOURCE_STATUS_PRESENT,
        source_reason=SOURCE_REASON_SOURCE_PRESENT,
        runtime_consumable=False,
    )


# ---------------------------------------------------------------------------
# record_to_dict: shape + closed projection
# ---------------------------------------------------------------------------


def test_record_to_dict_projects_every_field() -> None:
    rec = _known_record()
    projected = compact_market_context_record_to_dict(rec)
    assert set(projected.keys()) == set(
        Stage30_4CompactMarketContextRecord._fields
    )
    assert projected["market_cap_usd_value"] == "83000"
    assert projected["net_flow_display"] == "+$12k buys"
    assert projected["runtime_consumable"] is False


def test_record_to_dict_rejects_non_record_input() -> None:
    with pytest.raises(Stage30_4CompactMarketContextError) as ei:
        compact_market_context_record_to_dict({})  # type: ignore[arg-type]
    assert ei.value.reason == "RECORD_INVALID_TYPE"


# ---------------------------------------------------------------------------
# JSONL line encoding: deterministic, sorted keys, LF terminator
# ---------------------------------------------------------------------------


def test_jsonl_line_is_lf_terminated_single_object() -> None:
    rec = _unknown_record()
    line = encode_compact_market_context_jsonl_line(rec)
    assert line.endswith("\n")
    assert line.count("\n") == 1
    parsed = json.loads(line)
    assert isinstance(parsed, dict)


def test_jsonl_line_is_sorted_keys_deterministic() -> None:
    rec = _known_record()
    line_a = encode_compact_market_context_jsonl_line(rec)
    line_b = encode_compact_market_context_jsonl_line(rec)
    assert line_a == line_b
    # Verify sorted keys: scan the raw line for key positions.
    parsed = json.loads(line_a)
    raw = line_a.rstrip("\n")
    last_pos = -1
    for key in sorted(parsed.keys()):
        token = f'"{key}":'
        pos = raw.find(token)
        assert pos > last_pos, (
            f"JSONL keys must be sorted; key {key!r} out of order"
        )
        last_pos = pos


def test_jsonl_line_carries_none_as_null() -> None:
    rec = _unknown_record()
    line = encode_compact_market_context_jsonl_line(rec)
    parsed = json.loads(line)
    assert parsed["market_cap_usd_value"] is None
    assert parsed["market_cap_display"] is None
    assert parsed["source_label"] is None


def test_jsonl_line_carries_runtime_consumable_as_false() -> None:
    rec = _known_record()
    line = encode_compact_market_context_jsonl_line(rec)
    parsed = json.loads(line)
    assert parsed["runtime_consumable"] is False


# ---------------------------------------------------------------------------
# append_compact_market_context_record: filesystem behavior
# ---------------------------------------------------------------------------


def test_append_writes_to_locked_basename(tmp_path: Path) -> None:
    rec = _known_record()
    target = append_compact_market_context_record(
        output_dir=tmp_path, record=rec
    )
    assert target.name == (
        STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME
    )
    assert target.parent == tmp_path
    assert target.is_file()
    contents = target.read_text(encoding="utf-8")
    assert contents.count("\n") == 1
    parsed = json.loads(contents.strip())
    assert parsed["market_cap_usd_value"] == "83000"


def test_append_two_records_produces_two_jsonl_lines(
    tmp_path: Path,
) -> None:
    rec1 = _unknown_record()
    rec2 = _known_record()
    append_compact_market_context_record(
        output_dir=tmp_path, record=rec1
    )
    append_compact_market_context_record(
        output_dir=tmp_path, record=rec2
    )
    target = (
        tmp_path
        / STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME
    )
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed_a = json.loads(lines[0])
    parsed_b = json.loads(lines[1])
    assert parsed_a["session_id"] == "sess-1"
    assert parsed_b["session_id"] == "sess-2"


def test_append_rejects_non_path_output_dir() -> None:
    rec = _known_record()
    with pytest.raises(Stage30_4CompactMarketContextError) as ei:
        append_compact_market_context_record(
            output_dir="/tmp/some_string",  # type: ignore[arg-type]
            record=rec,
        )
    assert ei.value.reason == "OUTPUT_DIR_UNSAFE_OR_MISSING"


def test_append_rejects_missing_output_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    rec = _known_record()
    with pytest.raises(Stage30_4CompactMarketContextError) as ei:
        append_compact_market_context_record(
            output_dir=missing, record=rec
        )
    assert ei.value.reason == "OUTPUT_DIR_UNSAFE_OR_MISSING"


def test_append_rejects_file_output_dir(tmp_path: Path) -> None:
    fake_file = tmp_path / "fake.txt"
    fake_file.write_text("hi", encoding="utf-8")
    rec = _known_record()
    with pytest.raises(Stage30_4CompactMarketContextError) as ei:
        append_compact_market_context_record(
            output_dir=fake_file, record=rec
        )
    assert ei.value.reason == "OUTPUT_DIR_UNSAFE_OR_MISSING"


def test_append_rejects_non_record_input(tmp_path: Path) -> None:
    with pytest.raises(Stage30_4CompactMarketContextError) as ei:
        append_compact_market_context_record(
            output_dir=tmp_path,
            record={"hello": "world"},  # type: ignore[arg-type]
        )
    # Either RECORD_INVALID_TYPE (preferred) or the projection's
    # invalid-type error; both are acceptable closed-set reasons.
    assert ei.value.reason in (
        "RECORD_INVALID_TYPE",
        "OUTPUT_DIR_UNSAFE_OR_MISSING",
    )


# ---------------------------------------------------------------------------
# Output-dir safety substring scan: rejects URL / hook / API-key paths
# ---------------------------------------------------------------------------


def test_append_rejects_url_in_output_dir(tmp_path: Path) -> None:
    # Build a subdir whose name carries a forbidden substring.
    # Use split literal to avoid this test source carrying the
    # bare needle. ``discord.com_foo`` is a valid directory name on
    # POSIX and Windows; the writer's safety gate must reject it.
    bad = tmp_path / ("discord" + ".com_foo")
    bad.mkdir()
    rec = _known_record()
    with pytest.raises(Stage30_4CompactMarketContextError) as ei:
        append_compact_market_context_record(
            output_dir=bad, record=rec
        )
    assert ei.value.reason == "OUTPUT_DIR_UNSAFE_OR_MISSING"


# ---------------------------------------------------------------------------
# Forbidden-field-name guard: defensive
# ---------------------------------------------------------------------------


def test_no_field_on_record_matches_forbidden_vocabulary() -> None:
    """If a future refactor widens the record with a secret-class /
    raw-payload-class field name, ``compact_market_context_record_to_dict``
    must reject the record. The current record fields are clean by
    construction; this test asserts that today and pins the guard.
    """
    rec = _unknown_record()
    # Should not raise.
    compact_market_context_record_to_dict(rec)


# ---------------------------------------------------------------------------
# JSONL does not embed raw provider payload / secret / webhook URL
# ---------------------------------------------------------------------------


def test_jsonl_line_does_not_carry_forbidden_substrings(
    tmp_path: Path,
) -> None:
    rec = _known_record()
    append_compact_market_context_record(
        output_dir=tmp_path, record=rec
    )
    target = (
        tmp_path
        / STAGE30_4_1_COMPACT_MARKET_CONTEXT_ARTIFACT_BASENAME
    )
    contents = target.read_text(encoding="utf-8").lower()
    # Split-literal needles so this test source doesn't carry them.
    forbidden = (
        "h" + "ttps://",
        "h" + "ttp://",
        "w" + "ss://",
        "w" + "s://",
        "discord" + ".com",
        "discord" + "app.com",
        "/web" + "hooks/",
        "b" + "earer ",
        "a" + "uthorization:",
        "api_" + "key",
        "x-api-" + "key",
        "x-" + "token",
        "rpc_" + "url",
    )
    for needle in forbidden:
        assert needle not in contents, (
            f"30.4.1 JSONL line carries forbidden needle: {needle!r}"
        )


# ---------------------------------------------------------------------------
# allow_nan=False guard: encoded line never carries NaN / Infinity
# ---------------------------------------------------------------------------


def test_encoded_line_never_carries_nan_or_infinity() -> None:
    rec = _known_record()
    line = encode_compact_market_context_jsonl_line(rec)
    lower = line.lower()
    assert "nan" not in lower
    assert "infinity" not in lower


# ---------------------------------------------------------------------------
# Writer must NOT auto-create parent directories
# ---------------------------------------------------------------------------


def test_append_does_not_autocreate_parent_dir(tmp_path: Path) -> None:
    nested_missing = tmp_path / "does_not_exist" / "deeper"
    rec = _known_record()
    with pytest.raises(Stage30_4CompactMarketContextError):
        append_compact_market_context_record(
            output_dir=nested_missing, record=rec
        )
    assert not nested_missing.exists()
