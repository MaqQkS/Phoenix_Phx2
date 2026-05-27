"""Stage 30.1 tier decision artifact writer tests.

Covers JSONL append behavior, deterministic encoding, locked
basename, output-dir safety gating, no-parent-autocreation, the
forbidden-record-field-name guard, and a defensive content scan
that confirms the artifact carries no URL / webhook / secret-like
substring under normal operation.

Discipline: no env reads, no network, no Discord, no provider
calls. Stdlib + pytest only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from PHX2.stage30.tier_decision_artifact_writer import (
    STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME,
    append_tier_decision_record,
    encode_tier_decision_jsonl_line,
    tier_decision_record_to_dict,
)
from PHX2.stage30.tier_decision_models import (
    BASIS_PRICE,
    STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
    Stage30_1TierDecisionError,
    TIER_REASON_TIER_1_IN_BAND,
    TIER_TOKEN_TIER_1,
    TierDecisionRecord,
)


_SAFE_MINT: str = "So11111111111111111111111111111111111111112"
_SAFE_CREATED_AT: str = "2026-05-27T12:00:00Z"


def _make_record(**overrides: Any) -> TierDecisionRecord:
    defaults: Dict[str, Any] = {
        "schema_version": STAGE30_1_TIER_DECISION_SCHEMA_VERSION,
        "session_id": "sess-001",
        "ping_id": "ping-001",
        "candidate_id": "cand-001",
        "mint": _SAFE_MINT,
        "basis": BASIS_PRICE,
        "drawdown_from_ath_raw": "0.55",
        "drop_positive": "0.55",
        "ath_status": "PRESENT",
        "ath_since_migration_status": "POST_MIGRATION_ONLY",
        "migration_status": "PRESENT",
        "tier_token": TIER_TOKEN_TIER_1,
        "tier_reason": TIER_REASON_TIER_1_IN_BAND,
        "created_at_utc": _SAFE_CREATED_AT,
    }
    defaults.update(overrides)
    return TierDecisionRecord(**defaults)


# ---------------------------------------------------------------------------
# Locked basename pin
# ---------------------------------------------------------------------------


def test_locked_basename_pin() -> None:
    assert (
        STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
        == "stage30_1_tier_decisions.jsonl"
    )


# ---------------------------------------------------------------------------
# Record-to-dict shape
# ---------------------------------------------------------------------------


def test_record_to_dict_has_exact_keys() -> None:
    rec = _make_record()
    projected = tier_decision_record_to_dict(rec)
    assert set(projected.keys()) == set(TierDecisionRecord._fields)


def test_record_to_dict_value_passthrough() -> None:
    rec = _make_record()
    projected = tier_decision_record_to_dict(rec)
    for name in TierDecisionRecord._fields:
        assert projected[name] == getattr(rec, name)


_FORBIDDEN_KEY_SUBSTRINGS: tuple[str, ...] = (
    "webhook",
    "api_key",
    "apikey",
    "bearer",
    "authorization",
    "secret",
    "private_key",
    "credentials",
    "raw_payload",
    "payload",
    "migration_event_id",
    "raw_capture_ref",
    "source_event_ref",
)


def test_record_to_dict_no_forbidden_keys() -> None:
    rec = _make_record()
    projected = tier_decision_record_to_dict(rec)
    for key in projected.keys():
        lowered = key.lower()
        for needle in _FORBIDDEN_KEY_SUBSTRINGS:
            assert needle not in lowered, (
                f"key {key!r} carries forbidden substring {needle!r}"
            )


def test_record_to_dict_rejects_non_record() -> None:
    with pytest.raises(Stage30_1TierDecisionError):
        tier_decision_record_to_dict(
            {"not": "a record"}  # type: ignore[arg-type]
        )


def test_record_to_dict_rejects_namedtuple_lookalike() -> None:
    from collections import namedtuple

    Other = namedtuple("Other", TierDecisionRecord._fields)
    fake = Other(*[None] * len(TierDecisionRecord._fields))
    with pytest.raises(Stage30_1TierDecisionError):
        tier_decision_record_to_dict(fake)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Deterministic JSONL encoding
# ---------------------------------------------------------------------------


def test_encode_jsonl_line_is_deterministic() -> None:
    rec = _make_record()
    line_a = encode_tier_decision_jsonl_line(rec)
    line_b = encode_tier_decision_jsonl_line(rec)
    assert line_a == line_b


def test_encode_jsonl_line_ends_with_lf() -> None:
    rec = _make_record()
    line = encode_tier_decision_jsonl_line(rec)
    assert line.endswith("\n")
    assert "\n" not in line[:-1]


def test_encode_jsonl_line_is_compact_sorted_json() -> None:
    rec = _make_record()
    line = encode_tier_decision_jsonl_line(rec).rstrip("\n")
    parsed = json.loads(line)
    re_encoded = json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    assert line == re_encoded


def test_encode_jsonl_line_carries_locked_schema_version() -> None:
    rec = _make_record()
    parsed = json.loads(encode_tier_decision_jsonl_line(rec))
    assert parsed["schema_version"] == "stage30_1_v0_tier_decision"


def test_encode_jsonl_line_none_serializes_as_null() -> None:
    rec = _make_record(
        ping_id=None,
        candidate_id=None,
        session_id=None,
        mint=None,
        drawdown_from_ath_raw=None,
        drop_positive=None,
    )
    parsed = json.loads(encode_tier_decision_jsonl_line(rec))
    assert parsed["ping_id"] is None
    assert parsed["candidate_id"] is None
    assert parsed["session_id"] is None
    assert parsed["mint"] is None
    assert parsed["drawdown_from_ath_raw"] is None
    assert parsed["drop_positive"] is None


def test_encode_jsonl_line_no_extra_whitespace_no_indent() -> None:
    rec = _make_record()
    line = encode_tier_decision_jsonl_line(rec).rstrip("\n")
    # Compact JSON: no key indent / colon-space pairs. The compact
    # separators are ``(",", ":")`` (no spaces).
    assert ", " not in line
    assert ": " not in line


# ---------------------------------------------------------------------------
# Append-only JSONL writer
# ---------------------------------------------------------------------------


def test_append_writes_one_line_with_lf_terminator(
    tmp_path: Path,
) -> None:
    rec = _make_record()
    out = append_tier_decision_record(
        output_dir=tmp_path, record=rec
    )
    assert (
        out == tmp_path / STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
    )
    content = out.read_bytes()
    assert content.endswith(b"\n")
    assert content.count(b"\n") == 1


def test_append_two_records_writes_two_lines(
    tmp_path: Path,
) -> None:
    rec_a = _make_record(ping_id="ping-001")
    rec_b = _make_record(ping_id="ping-002")
    append_tier_decision_record(output_dir=tmp_path, record=rec_a)
    append_tier_decision_record(output_dir=tmp_path, record=rec_b)
    out = tmp_path / STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
    content = out.read_text(encoding="utf-8")
    lines = content.split("\n")
    # Two records + trailing empty string after final newline.
    assert len(lines) == 3
    assert lines[-1] == ""
    parsed_a = json.loads(lines[0])
    parsed_b = json.loads(lines[1])
    assert parsed_a["ping_id"] == "ping-001"
    assert parsed_b["ping_id"] == "ping-002"


def test_append_byte_deterministic_across_two_writes(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    rec = _make_record()
    dir_a = tmp_path_factory.mktemp("a")
    dir_b = tmp_path_factory.mktemp("b")
    append_tier_decision_record(output_dir=dir_a, record=rec)
    append_tier_decision_record(output_dir=dir_b, record=rec)
    bytes_a = (
        dir_a / STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
    ).read_bytes()
    bytes_b = (
        dir_b / STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
    ).read_bytes()
    assert bytes_a == bytes_b


def test_append_does_not_autocreate_parent(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist_xyzzy"
    rec = _make_record()
    with pytest.raises(Stage30_1TierDecisionError):
        append_tier_decision_record(
            output_dir=nonexistent, record=rec
        )
    assert not nonexistent.exists()


def test_append_rejects_non_path(tmp_path: Path) -> None:
    rec = _make_record()
    with pytest.raises(Stage30_1TierDecisionError):
        append_tier_decision_record(
            output_dir=str(tmp_path),  # type: ignore[arg-type]
            record=rec,
        )


def test_append_rejects_non_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not_a_dir"
    file_path.write_text("x")
    rec = _make_record()
    with pytest.raises(Stage30_1TierDecisionError):
        append_tier_decision_record(
            output_dir=file_path, record=rec
        )


def test_append_rejects_non_record(tmp_path: Path) -> None:
    with pytest.raises(Stage30_1TierDecisionError):
        append_tier_decision_record(
            output_dir=tmp_path,
            record={"not": "a record"},  # type: ignore[arg-type]
        )


def test_append_rejects_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_dir"
    rec = _make_record()
    with pytest.raises(Stage30_1TierDecisionError):
        append_tier_decision_record(
            output_dir=missing, record=rec
        )


# ---------------------------------------------------------------------------
# Output-dir safety gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unsafe_subdir_name",
    [
        "discord" + ".com",
        "discord" + "app.com",
        "hooks" + ".slack.com",
        "my_dir_with_sk-key",
        "my_dir_with_pk-key",
    ],
)
def test_append_rejects_dir_containing_forbidden_substring(
    tmp_path: Path, unsafe_subdir_name: str
) -> None:
    bad_dir = tmp_path / unsafe_subdir_name
    bad_dir.mkdir()
    rec = _make_record()
    with pytest.raises(Stage30_1TierDecisionError):
        append_tier_decision_record(
            output_dir=bad_dir, record=rec
        )


# ---------------------------------------------------------------------------
# Defensive artifact content scan
# ---------------------------------------------------------------------------


_FORBIDDEN_CONTENT_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    "hooks" + ".slack.com",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-live-",
    "s" + "k-test-",
    "p" + "k-live-",
    "p" + "k-test-",
    "Phoenix" + "_Bot",
    "phoenix" + "_bot",
)


def test_artifact_contents_carry_no_forbidden_substring(
    tmp_path: Path,
) -> None:
    rec = _make_record()
    out = append_tier_decision_record(
        output_dir=tmp_path, record=rec
    )
    content = out.read_text(encoding="utf-8")
    lowered = content.lower()
    for needle in _FORBIDDEN_CONTENT_SUBSTRINGS:
        assert needle.lower() not in lowered, (
            f"artifact carries forbidden substring: {needle!r}"
        )


def test_artifact_contents_are_valid_jsonl(tmp_path: Path) -> None:
    rec_a = _make_record(ping_id="ping-A")
    rec_b = _make_record(ping_id="ping-B")
    append_tier_decision_record(output_dir=tmp_path, record=rec_a)
    append_tier_decision_record(output_dir=tmp_path, record=rec_b)
    out = tmp_path / STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
    text = out.read_text(encoding="utf-8")
    for line in text.splitlines():
        parsed = json.loads(line)
        assert isinstance(parsed, dict)
        assert (
            parsed["schema_version"]
            == STAGE30_1_TIER_DECISION_SCHEMA_VERSION
        )


# ---------------------------------------------------------------------------
# Smoke: no socket calls under writer
# ---------------------------------------------------------------------------


def test_append_does_not_open_socket(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import socket as _socket

    def _explode(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "socket.socket called inside Stage 30.1 writer"
        )

    monkeypatch.setattr(_socket, "socket", _explode)
    rec = _make_record()
    append_tier_decision_record(output_dir=tmp_path, record=rec)


def test_append_does_not_read_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import os as _os

    sentinel: Dict[str, int] = {"calls": 0}
    real_get = _os.environ.get

    def _tracker(key: str, default: object = None) -> object:
        sentinel["calls"] += 1
        return real_get(key, default)

    monkeypatch.setattr(_os.environ, "get", _tracker)
    rec = _make_record()
    append_tier_decision_record(output_dir=tmp_path, record=rec)
    assert sentinel["calls"] == 0
