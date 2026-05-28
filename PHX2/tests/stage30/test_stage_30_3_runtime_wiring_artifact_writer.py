"""Stage 30.3 runtime-wiring JSONL artifact writer tests.

Covers JSONL append behavior, deterministic encoding, locked
basename, output-dir safety gating, no-parent-autocreation, the
forbidden-field-name guard, the wrapper-order tuple serialisation,
and the None-slot JSON null encoding.

Discipline: no env reads, no network, no provider calls, no
operator-channel send. Stdlib + pytest only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from PHX2.stage30 import stage30_3_compact_runtime_models as _models
from PHX2.stage30.stage30_3_compact_runtime_models import (
    COMPACT_OUTCOME_RENDERED,
    COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
    STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
    STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION,
    Stage30_3CompactRuntimeError,
    Stage30_3RuntimeWiringArtifactRecord,
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
)
from PHX2.stage30.stage30_3_runtime_wiring_artifact_writer import (
    append_runtime_wiring_record,
    encode_runtime_wiring_jsonl_line,
    runtime_wiring_record_to_dict,
)


# Fake non-WSOL base58-shape token mint fixture. The Stage 30.3
# writer tests deliberately avoid the canonical WSOL mint literal
# so a regression in the writer's redaction / encoding path cannot
# silently slip the WSOL substring through the boundary scan.
# ``_WSOL_MINT_LITERAL`` is the canonical WSOL constant kept only
# for explicit absence assertions on the JSONL artifact.
_SAFE_MINT: str = (
    "FakeMintPhx2NotWso1ForTestBase58222222222222"
)
_WSOL_MINT_LITERAL: str = (
    "So11111111111111111111111111111111111111112"
)
_SAFE_TS: str = "2026-05-27T12:00:00Z"


def _make_record(**overrides: Any) -> Stage30_3RuntimeWiringArtifactRecord:
    defaults: Dict[str, Any] = {
        "schema_version": STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION,
        "session_id": "sess-001",
        "candidate_id": "cand-001",
        "ping_id": "cand-001",
        "mint": _SAFE_MINT,
        "wrapper_order": (
            WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
            WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
        ),
        "compact_outcome": COMPACT_OUTCOME_RENDERED,
        "compact_outcome_reason": None,
        "tier_token": "Tier 1",
        "tier_reason": "TIER_1_IN_BAND",
        "basis": "price-basis",
        "original_content_length_chars": 500,
        "compact_content_length_chars": 200,
        "compact_body_sha256_hex_prefix_16": "0123456789abcdef",
        "tier_snapshot_path_basename": (
            "stage30_1_tier_decisions.jsonl"
        ),
        "compact_snapshot_path_basename": (
            "stage30_2_compact_pings.jsonl"
        ),
        "forwarded_to_inner_transport": True,
        "created_at_utc": _SAFE_TS,
    }
    defaults.update(overrides)
    return Stage30_3RuntimeWiringArtifactRecord(**defaults)


# ---------------------------------------------------------------------------
# Locked basename pin
# ---------------------------------------------------------------------------


def test_locked_basename_pin() -> None:
    assert (
        STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
        == "stage30_3_runtime_wiring.jsonl"
    )


# ---------------------------------------------------------------------------
# Record-to-dict
# ---------------------------------------------------------------------------


def test_record_to_dict_keys_match_fields() -> None:
    rec = _make_record()
    projected = runtime_wiring_record_to_dict(rec)
    assert set(projected.keys()) == set(
        Stage30_3RuntimeWiringArtifactRecord._fields
    )


def test_record_to_dict_wrapper_order_serialises_as_list() -> None:
    rec = _make_record()
    projected = runtime_wiring_record_to_dict(rec)
    assert isinstance(projected["wrapper_order"], list)
    assert projected["wrapper_order"] == [
        WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
        WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    ]


def test_record_to_dict_rejects_non_record() -> None:
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        runtime_wiring_record_to_dict(
            {"not": "a record"}  # type: ignore[arg-type]
        )
    assert (
        excinfo.value.reason
        == "RUNTIME_WIRING_RECORD_INVALID_TYPE"
    )


# ---------------------------------------------------------------------------
# Deterministic JSONL encoding
# ---------------------------------------------------------------------------


def test_encode_jsonl_line_is_deterministic() -> None:
    rec = _make_record()
    line_a = encode_runtime_wiring_jsonl_line(rec)
    line_b = encode_runtime_wiring_jsonl_line(rec)
    assert line_a == line_b


def test_encode_jsonl_line_ends_with_lf() -> None:
    rec = _make_record()
    line = encode_runtime_wiring_jsonl_line(rec)
    assert line.endswith("\n")
    assert "\n" not in line[:-1]


def test_encode_jsonl_line_is_compact_sorted_json() -> None:
    rec = _make_record()
    line = encode_runtime_wiring_jsonl_line(rec).rstrip("\n")
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
    parsed = json.loads(encode_runtime_wiring_jsonl_line(rec))
    assert (
        parsed["schema_version"]
        == STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION
    )


def test_encode_jsonl_line_none_slots_serialise_as_null() -> None:
    rec = _make_record(
        compact_outcome=COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
        compact_outcome_reason=None,
        tier_token=None,
        tier_reason=None,
        compact_content_length_chars=None,
        compact_body_sha256_hex_prefix_16=None,
        tier_snapshot_path_basename=None,
        compact_snapshot_path_basename=None,
        forwarded_to_inner_transport=False,
        candidate_id=None,
        ping_id=None,
        mint=None,
        original_content_length_chars=None,
    )
    parsed = json.loads(encode_runtime_wiring_jsonl_line(rec))
    assert parsed["compact_outcome_reason"] is None
    assert parsed["tier_token"] is None
    assert parsed["tier_reason"] is None
    assert parsed["compact_content_length_chars"] is None
    assert parsed["compact_body_sha256_hex_prefix_16"] is None
    assert parsed["tier_snapshot_path_basename"] is None
    assert parsed["compact_snapshot_path_basename"] is None
    assert parsed["candidate_id"] is None
    assert parsed["ping_id"] is None
    assert parsed["mint"] is None
    assert parsed["original_content_length_chars"] is None


def test_encode_jsonl_line_no_extra_whitespace_no_indent() -> None:
    rec = _make_record()
    line = encode_runtime_wiring_jsonl_line(rec).rstrip("\n")
    assert ", " not in line
    assert ": " not in line


# ---------------------------------------------------------------------------
# Append-only writer
# ---------------------------------------------------------------------------


def test_append_writes_locked_basename(tmp_path: Path) -> None:
    rec = _make_record()
    out = append_runtime_wiring_record(
        output_dir=tmp_path, record=rec
    )
    assert (
        out == tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    )


def test_append_two_byte_identical_records_two_byte_identical_lines(
    tmp_path: Path,
) -> None:
    rec = _make_record()
    append_runtime_wiring_record(output_dir=tmp_path, record=rec)
    append_runtime_wiring_record(output_dir=tmp_path, record=rec)
    target = tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    content = target.read_bytes()
    lines = [line for line in content.split(b"\n") if line]
    assert len(lines) == 2
    assert lines[0] == lines[1]


def test_append_does_not_autocreate_parent(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist_xyzzy"
    rec = _make_record()
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        append_runtime_wiring_record(
            output_dir=nonexistent, record=rec
        )
    assert (
        excinfo.value.reason == "OUTPUT_DIR_UNSAFE_OR_MISSING"
    )
    assert not nonexistent.exists()


def test_append_rejects_non_path(tmp_path: Path) -> None:
    rec = _make_record()
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        append_runtime_wiring_record(
            output_dir=str(tmp_path),  # type: ignore[arg-type]
            record=rec,
        )
    assert (
        excinfo.value.reason == "OUTPUT_DIR_UNSAFE_OR_MISSING"
    )


def test_append_rejects_non_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not_a_dir"
    file_path.write_text("x")
    rec = _make_record()
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        append_runtime_wiring_record(
            output_dir=file_path, record=rec
        )
    assert (
        excinfo.value.reason == "OUTPUT_DIR_UNSAFE_OR_MISSING"
    )


def test_append_rejects_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "no_such_dir"
    rec = _make_record()
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        append_runtime_wiring_record(
            output_dir=missing, record=rec
        )
    assert (
        excinfo.value.reason == "OUTPUT_DIR_UNSAFE_OR_MISSING"
    )


def test_append_rejects_non_record(tmp_path: Path) -> None:
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        append_runtime_wiring_record(
            output_dir=tmp_path,
            record={"not": "a record"},  # type: ignore[arg-type]
        )
    assert (
        excinfo.value.reason
        == "RUNTIME_WIRING_RECORD_INVALID_TYPE"
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
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        append_runtime_wiring_record(
            output_dir=bad_dir, record=rec
        )
    assert (
        excinfo.value.reason == "OUTPUT_DIR_UNSAFE_OR_MISSING"
    )


# ---------------------------------------------------------------------------
# Forbidden-field-name guard
# ---------------------------------------------------------------------------


def test_forbidden_field_name_guard_fires_when_real_field_listed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When FORBIDDEN_RECORD_FIELD_NAMES is monkeypatched to
    include a real Stage 30.3 field name, the writer's forbidden-
    field-name guard fires before the file is written.
    """
    # Monkeypatch the FORBIDDEN tuple to include the real
    # 'candidate_id' field name so the substring scan fires.
    bad_tuple = tuple(
        list(_models.FORBIDDEN_RECORD_FIELD_NAMES) + ["candidate_id"]
    )
    monkeypatch.setattr(
        _models, "FORBIDDEN_RECORD_FIELD_NAMES", bad_tuple
    )
    rec = _make_record()
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        append_runtime_wiring_record(
            output_dir=tmp_path, record=rec
        )
    assert (
        excinfo.value.reason == "RECORD_HAS_FORBIDDEN_FIELD_NAME"
    )
    # File NOT written.
    target = tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    assert not target.exists()


# ---------------------------------------------------------------------------
# Defensive artifact content scan
# ---------------------------------------------------------------------------


_FORBIDDEN_CONTENT_SUBSTRINGS: tuple = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/web" + "hooks/",
    "hooks" + ".slack.com",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-live-",
    "s" + "k-test-",
    "p" + "k-live-",
    "p" + "k-test-",
    "Phoenix" + "_Bot",
)


def test_artifact_carries_no_forbidden_substring(
    tmp_path: Path,
) -> None:
    rec = _make_record()
    out = append_runtime_wiring_record(
        output_dir=tmp_path, record=rec
    )
    content = out.read_text(encoding="utf-8")
    lowered = content.lower()
    for needle in _FORBIDDEN_CONTENT_SUBSTRINGS:
        assert needle.lower() not in lowered, (
            f"artifact carries forbidden substring: {needle!r}"
        )
    # Stage 30.3A regression: the writer test fixture mint is a
    # fake non-WSOL base58 string, so the canonical WSOL literal
    # must not appear anywhere in the JSONL artifact.
    assert _WSOL_MINT_LITERAL not in content


def test_artifact_contents_are_valid_jsonl(tmp_path: Path) -> None:
    rec_a = _make_record(candidate_id="cand-A")
    rec_b = _make_record(candidate_id="cand-B")
    append_runtime_wiring_record(output_dir=tmp_path, record=rec_a)
    append_runtime_wiring_record(output_dir=tmp_path, record=rec_b)
    out = tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    text = out.read_text(encoding="utf-8")
    for line in text.splitlines():
        parsed = json.loads(line)
        assert isinstance(parsed, dict)
        assert (
            parsed["schema_version"]
            == STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION
        )


# ---------------------------------------------------------------------------
# Smoke: no env / socket calls inside writer
# ---------------------------------------------------------------------------


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
    append_runtime_wiring_record(output_dir=tmp_path, record=rec)
    assert sentinel["calls"] == 0
