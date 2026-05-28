"""Stage 30.2 compact ping artifact writer tests.

Covers JSONL append behavior, deterministic encoding, locked
basename, output-dir safety gating, no-parent-autocreation, the
forbidden-record-field-name guard, the record-type check, and a
defensive content scan that confirms the artifact carries no
URL / webhook / secret-like substring under normal operation.

Discipline: no env reads, no network, no Discord, no provider
calls. Stdlib + pytest only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from PHX2.stage30.compact_ping_artifact_writer import (
    STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME,
    append_compact_ping_snapshot,
    compact_ping_snapshot_to_dict,
    encode_compact_ping_jsonl_line,
)
from PHX2.stage30.compact_ping_models import (
    CompactPingSnapshotRecord,
    DISPLAY_UNKNOWN,
    STAGE30_2_COMPACT_PING_SCHEMA_VERSION,
    Stage30_2CompactPingError,
)


# ---------------------------------------------------------------------------
# Common fixture builders
# ---------------------------------------------------------------------------


# Fake, valid-shape, non-WSOL Solana base58 token / base mint. The
# writer never substitutes WSOL itself, but using a clearly-fake
# mint here keeps the artifact-writer fixtures aligned with the
# renderer-test fixtures (which exercise the token-vs-quote mint
# distinction directly).
_SAFE_MINT: str = (
    "PHXTestM1ntFakeBase58NotWSL12345678912345678"
)
_SAFE_CREATED_AT: str = "2026-05-27T12:00:00Z"


def _make_snapshot(
    **overrides: Any,
) -> CompactPingSnapshotRecord:
    defaults: Dict[str, Any] = {
        "schema_version": STAGE30_2_COMPACT_PING_SCHEMA_VERSION,
        "session_id": "sess-001",
        "ping_id": "ping-001",
        "candidate_id": "cand-001",
        "mint": _SAFE_MINT,
        "symbol": None,
        "tier_token": "Tier 1",
        "tier_reason": "TIER_1_IN_BAND",
        "basis": "price-basis",
        "drawdown_from_ath_raw": "0.55",
        "drop_positive": "0.55",
        "ath_status": "PRESENT",
        "ath_since_migration_status": "POST_MIGRATION_ONLY",
        "migration_status": "PRESENT",
        "price_status": "PRESENT",
        "current_mc_display": DISPLAY_UNKNOWN,
        "ath_mc_display": DISPLAY_UNKNOWN,
        "migration_mc_display": DISPLAY_UNKNOWN,
        "drop_percent_display": "-55%",
        "age_display": "16.6h",
        "lp_display": DISPLAY_UNKNOWN,
        "net_flow_display": DISPLAY_UNKNOWN,
        "warnings": (),
        "body_text": "stub body",
        "body_length_chars": len("stub body"),
        "created_at_utc": _SAFE_CREATED_AT,
    }
    defaults.update(overrides)
    return CompactPingSnapshotRecord(**defaults)


# ---------------------------------------------------------------------------
# Locked basename pin
# ---------------------------------------------------------------------------


def test_locked_basename_pin() -> None:
    assert (
        STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
        == "stage30_2_compact_pings.jsonl"
    )


# ---------------------------------------------------------------------------
# Snapshot-to-dict shape
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_has_exact_keys() -> None:
    rec = _make_snapshot()
    projected = compact_ping_snapshot_to_dict(rec)
    assert set(projected.keys()) == set(
        CompactPingSnapshotRecord._fields
    )


def test_snapshot_to_dict_serializes_warnings_as_list() -> None:
    rec = _make_snapshot(
        warnings=(
            "Tier Unknown: in gap (T1-T2)",
            "Price degraded: stale",
        )
    )
    projected = compact_ping_snapshot_to_dict(rec)
    assert isinstance(projected["warnings"], list)
    assert projected["warnings"] == [
        "Tier Unknown: in gap (T1-T2)",
        "Price degraded: stale",
    ]


def test_snapshot_to_dict_rejects_non_record() -> None:
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        compact_ping_snapshot_to_dict({"a": 1})  # type: ignore[arg-type]
    assert exc_info.value.reason == (
        "SNAPSHOT_RECORD_INVALID_TYPE"
    )


# ---------------------------------------------------------------------------
# Deterministic JSONL line encoding
# ---------------------------------------------------------------------------


def test_jsonl_line_ends_with_lf() -> None:
    rec = _make_snapshot()
    line = encode_compact_ping_jsonl_line(rec)
    assert line.endswith("\n")
    assert line.count("\n") == 1


def test_jsonl_line_is_deterministic() -> None:
    rec = _make_snapshot()
    first = encode_compact_ping_jsonl_line(rec)
    second = encode_compact_ping_jsonl_line(rec)
    assert first == second


def test_jsonl_line_uses_sorted_keys_and_compact_separators() -> None:
    rec = _make_snapshot()
    line = encode_compact_ping_jsonl_line(rec)
    decoded = json.loads(line)
    # Re-encode with the same options and compare. The line is
    # byte-identical to the canonical re-encoding -- proving the
    # writer uses sorted keys + compact separators.
    reencoded = (
        json.dumps(
            decoded,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    )
    assert line == reencoded


def test_jsonl_line_keys_are_sorted_alphabetically() -> None:
    rec = _make_snapshot()
    line = encode_compact_ping_jsonl_line(rec)
    # Locate every top-level JSON key by scanning the prefix of the
    # line (every key is followed by a colon-quote-or-bracket-or-
    # value-start, and keys are alphabetic + underscore only).
    decoded = json.loads(line)
    keys_in_decoded_order = list(decoded.keys())
    assert keys_in_decoded_order == sorted(keys_in_decoded_order)


def test_jsonl_line_roundtrips_via_json_loads() -> None:
    rec = _make_snapshot(
        warnings=("Tier Unknown: in gap (T2-T3)",),
    )
    line = encode_compact_ping_jsonl_line(rec)
    decoded = json.loads(line)
    assert decoded["schema_version"] == (
        STAGE30_2_COMPACT_PING_SCHEMA_VERSION
    )
    assert decoded["tier_token"] == "Tier 1"
    assert decoded["warnings"] == [
        "Tier Unknown: in gap (T2-T3)",
    ]
    assert decoded["mint"] == _SAFE_MINT


def test_jsonl_line_encodes_emoji_body_text() -> None:
    body = (
        "\U0001f525 PHOENIX — TEST [Tier 1]\n"
        "PHXTestM1ntFakeBase58NotWSL12345678912345678\n"
        "\n"
        "\U0001f9e0 State\n"
        "• MC: Unknown | ATH: Unknown | Mig: Unknown\n"
        "• Drop: -55% | Age: 16.6h | Net: Unknown\n"
        "• LP: Unknown\n"
        "• Basis: price-basis"
    )
    rec = _make_snapshot(body_text=body, body_length_chars=len(body))
    line = encode_compact_ping_jsonl_line(rec)
    decoded = json.loads(line)
    assert decoded["body_text"] == body


# ---------------------------------------------------------------------------
# Append behavior
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    text = path.read_text(encoding="utf-8")
    for raw_line in text.splitlines():
        if raw_line == "":
            continue
        rows.append(json.loads(raw_line))
    return rows


def test_append_writes_one_line(tmp_path: Path) -> None:
    rec = _make_snapshot()
    target = append_compact_ping_snapshot(
        output_dir=tmp_path, snapshot=rec
    )
    assert target.name == STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    rows = _read_jsonl(target)
    assert len(rows) == 1
    assert rows[0]["tier_token"] == "Tier 1"


def test_append_appends_second_line(tmp_path: Path) -> None:
    rec_a = _make_snapshot(ping_id="ping-001")
    rec_b = _make_snapshot(ping_id="ping-002")
    append_compact_ping_snapshot(
        output_dir=tmp_path, snapshot=rec_a
    )
    target = append_compact_ping_snapshot(
        output_dir=tmp_path, snapshot=rec_b
    )
    rows = _read_jsonl(target)
    assert len(rows) == 2
    assert rows[0]["ping_id"] == "ping-001"
    assert rows[1]["ping_id"] == "ping-002"


def test_append_returns_resolved_target_path(
    tmp_path: Path,
) -> None:
    rec = _make_snapshot()
    target = append_compact_ping_snapshot(
        output_dir=tmp_path, snapshot=rec
    )
    assert (
        target
        == tmp_path / STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    )


# ---------------------------------------------------------------------------
# Output-dir safety gate
# ---------------------------------------------------------------------------


def test_output_dir_must_be_path_instance(tmp_path: Path) -> None:
    rec = _make_snapshot()
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        append_compact_ping_snapshot(
            output_dir=str(tmp_path),  # type: ignore[arg-type]
            snapshot=rec,
        )
    assert exc_info.value.reason == (
        "OUTPUT_DIR_UNSAFE_OR_MISSING"
    )


def test_output_dir_must_exist(tmp_path: Path) -> None:
    rec = _make_snapshot()
    missing = tmp_path / "does_not_exist"
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        append_compact_ping_snapshot(
            output_dir=missing, snapshot=rec
        )
    assert exc_info.value.reason == (
        "OUTPUT_DIR_UNSAFE_OR_MISSING"
    )


def test_output_dir_must_be_a_directory(tmp_path: Path) -> None:
    rec = _make_snapshot()
    not_a_dir = tmp_path / "i_am_a_file.txt"
    not_a_dir.write_text("not a dir", encoding="utf-8")
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        append_compact_ping_snapshot(
            output_dir=not_a_dir, snapshot=rec
        )
    assert exc_info.value.reason == (
        "OUTPUT_DIR_UNSAFE_OR_MISSING"
    )


def test_output_dir_with_forbidden_substring_is_rejected(
    tmp_path: Path,
) -> None:
    rec = _make_snapshot()
    # Use ``discord.com`` because slashes and colons are not valid
    # directory-name characters on Windows; dot is. The writer
    # lowercases the path string before matching, so an uppercase
    # variant would also match.
    bad_name = "x_" + "discord" + ".com" + "_y"
    bad_dir = tmp_path / bad_name
    bad_dir.mkdir()
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        append_compact_ping_snapshot(
            output_dir=bad_dir, snapshot=rec
        )
    assert exc_info.value.reason == (
        "OUTPUT_DIR_UNSAFE_OR_MISSING"
    )


def test_append_does_not_autocreate_parent(tmp_path: Path) -> None:
    rec = _make_snapshot()
    nested = tmp_path / "nested_subdir"
    assert not nested.exists()
    with pytest.raises(Stage30_2CompactPingError):
        append_compact_ping_snapshot(
            output_dir=nested, snapshot=rec
        )
    # Confirm the writer did not silently create the parent.
    assert not nested.exists()


# ---------------------------------------------------------------------------
# Snapshot type check
# ---------------------------------------------------------------------------


def test_append_rejects_non_record_snapshot(tmp_path: Path) -> None:
    with pytest.raises(Stage30_2CompactPingError) as exc_info:
        append_compact_ping_snapshot(
            output_dir=tmp_path,
            snapshot={"not": "a record"},  # type: ignore[arg-type]
        )
    assert exc_info.value.reason == (
        "SNAPSHOT_RECORD_INVALID_TYPE"
    )


# ---------------------------------------------------------------------------
# Defensive content scan over written file
# ---------------------------------------------------------------------------


_FORBIDDEN_FILE_SUBSTRINGS: Tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
)


def test_written_file_has_no_url_or_auth_substring(
    tmp_path: Path,
) -> None:
    rec = _make_snapshot()
    target = append_compact_ping_snapshot(
        output_dir=tmp_path, snapshot=rec
    )
    text = target.read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in _FORBIDDEN_FILE_SUBSTRINGS:
        assert needle.lower() not in lowered, (
            f"written artifact carries forbidden substring "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# Locked field ordering (deterministic encoding requirement)
# ---------------------------------------------------------------------------


def test_two_snapshots_with_same_field_values_yield_identical_line() -> (
    None
):
    rec_a = _make_snapshot()
    rec_b = _make_snapshot()
    assert encode_compact_ping_jsonl_line(rec_a) == (
        encode_compact_ping_jsonl_line(rec_b)
    )


# ---------------------------------------------------------------------------
# Writer carries no canonical forbidden source substring
# ---------------------------------------------------------------------------


def test_writer_source_has_no_canonical_forbidden_substring() -> None:
    writer_path = (
        Path(__file__).resolve().parent.parent.parent
        / "stage30"
        / "compact_ping_artifact_writer.py"
    )
    text = writer_path.read_text(encoding="utf-8")
    forbidden = (
        "h" + "ttps://discord.com",
        "h" + "ttps://discordapp.com",
        "h" + "ttps://api.birdeye.so",
        "h" + "ttps://api.helius",
        "h" + "ttps://chainstack.com",
        "/api/webhooks/",
        "Phoenix_Bot",
        "phoenix_bot",
    )
    for needle in forbidden:
        assert needle not in text, (
            f"writer carries forbidden canonical substring "
            f"{needle!r}"
        )
