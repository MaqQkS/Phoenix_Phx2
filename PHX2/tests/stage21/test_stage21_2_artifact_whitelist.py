"""Stage 21.2 remediation R5: artifact-whitelist tests.

Pins the behavior of ``PHX2.tests.stage21._artifact_scan_helpers``:

  * ``KNOWN_SAFE_KEYPATHS`` is locked to a single entry,
    ``("run_metadata", "safe_for_public_dispatch")``.
  * ``strip_known_safe_keys`` removes only that exact keypath,
    only when the value is the literal Python ``False``, and
    never mutates the input.
  * ``cleaned_artifact_text`` handles both JSON and JSONL
    artifacts via parse + strip + re-serialize (no substring
    replacement anywhere).

The negative tests exercise the cases the prior global
``.replace("safe_for_public_dispatch", "")`` substring strip
would have hidden:

  * an ``unsafe_for_public_dispatch`` key (substring overlap
    with the locked key name),
  * the locked key with a ``True`` value,
  * the locked key with the string ``"false"``,
  * the locked key at a non-canonical keypath.

Each of these cases must NOT be stripped by the new whitelist,
so the substring scan downstream still trips on the bare
``public_dispatch`` forbidden token.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from PHX2.tests.stage21._artifact_scan_helpers import (
    KNOWN_SAFE_KEYPATHS,
    cleaned_artifact_text,
    cleaned_artifact_text_from_path,
    strip_known_safe_keys,
)


# ---------------------------------------------------------------------------
# KNOWN_SAFE_KEYPATHS is locked at exactly one entry
# ---------------------------------------------------------------------------


def test_known_safe_keypaths_is_exactly_locked():
    """The whitelist set is exactly the one locked Stage 21 invariant keypath."""
    assert KNOWN_SAFE_KEYPATHS == (
        ("run_metadata", "safe_for_public_dispatch"),
    )


def test_known_safe_keypaths_contains_one_entry():
    assert len(KNOWN_SAFE_KEYPATHS) == 1


def test_known_safe_keypaths_does_not_include_top_level_variant():
    """Top-level ``safe_for_public_dispatch`` is NOT whitelisted."""
    assert ("safe_for_public_dispatch",) not in KNOWN_SAFE_KEYPATHS


def test_known_safe_keypaths_does_not_include_safe_for_live_dispatch():
    """The live-dispatch variant is NOT whitelisted (it does not exist in Stage 21.2)."""
    assert ("safe_for_live_dispatch",) not in KNOWN_SAFE_KEYPATHS
    assert (
        "run_metadata",
        "safe_for_live_dispatch",
    ) not in KNOWN_SAFE_KEYPATHS


# ---------------------------------------------------------------------------
# Positive: real manifest with locked invariant value False is stripped
# ---------------------------------------------------------------------------


def _representative_manifest():
    """Return a representative Stage 21.2 manifest dict shape."""
    return {
        "run_metadata": {
            "run_id": "stage21_2_test_run",
            "stage21_version": "stage21_v0_private_preview_foundation",
            "stage21_2_stage_label": "21.2",
            "generated_at_utc_iso": "2026-05-17T12:00:00Z",
            "safe_for_public_dispatch": False,
        },
        "locked_markers": {
            "stage": "21.2",
            "visibility": "private_preview",
            "operator_only": True,
            "live_mode": False,
            "dispatch_target": "fake_private_transport",
        },
        "counts": {
            "fake_events_received": 1,
            "duplicates_skipped": 0,
        },
    }


def test_real_manifest_with_safe_for_public_dispatch_false_is_stripped():
    """Locked invariant value False at the locked keypath is stripped."""
    cleaned = strip_known_safe_keys(_representative_manifest())
    assert "safe_for_public_dispatch" not in cleaned["run_metadata"]
    # Other run_metadata keys remain.
    assert cleaned["run_metadata"]["run_id"] == "stage21_2_test_run"
    assert cleaned["run_metadata"]["stage21_2_stage_label"] == "21.2"


def test_real_manifest_strip_followed_by_substring_scan_passes():
    """The full scan path (strip + re-serialize + scan) clears the manifest."""
    raw = json.dumps(_representative_manifest(), sort_keys=True)
    cleaned_text = cleaned_artifact_text(raw, is_jsonl=False)
    # The locked invariant is gone, so the bare ``public_dispatch``
    # forbidden token must NOT appear anywhere in the cleaned text.
    assert "public_dispatch" not in cleaned_text


# ---------------------------------------------------------------------------
# Negative: unsafe variants remain and trip the scan
# ---------------------------------------------------------------------------


def test_unsafe_for_public_dispatch_key_is_not_stripped():
    """A substring-overlap key ``unsafe_for_public_dispatch`` is NOT stripped.

    The prior global substring strip would have removed
    ``safe_for_public_dispatch`` substring from inside the
    longer key name; the JSON-aware whitelist must NOT.
    """
    mf = {
        "run_metadata": {
            "unsafe_for_public_dispatch": False,
        },
    }
    cleaned = strip_known_safe_keys(mf)
    assert "unsafe_for_public_dispatch" in cleaned["run_metadata"]
    cleaned_text = cleaned_artifact_text(
        json.dumps(mf, sort_keys=True), is_jsonl=False
    )
    # The bare ``public_dispatch`` token still appears in the
    # cleaned text via the unsafe variant.
    assert "public_dispatch" in cleaned_text


def test_safe_for_public_dispatch_true_is_not_stripped():
    """The locked key with value ``True`` is NOT stripped."""
    mf = {
        "run_metadata": {
            "safe_for_public_dispatch": True,
        },
    }
    cleaned = strip_known_safe_keys(mf)
    assert "safe_for_public_dispatch" in cleaned["run_metadata"]
    cleaned_text = cleaned_artifact_text(
        json.dumps(mf, sort_keys=True), is_jsonl=False
    )
    assert "public_dispatch" in cleaned_text


def test_safe_for_public_dispatch_string_false_is_not_stripped():
    """The locked key with value string ``"false"`` is NOT stripped."""
    mf = {
        "run_metadata": {
            "safe_for_public_dispatch": "false",
        },
    }
    cleaned = strip_known_safe_keys(mf)
    assert "safe_for_public_dispatch" in cleaned["run_metadata"]
    cleaned_text = cleaned_artifact_text(
        json.dumps(mf, sort_keys=True), is_jsonl=False
    )
    assert "public_dispatch" in cleaned_text


def test_safe_for_public_dispatch_int_zero_is_not_stripped():
    """Integer ``0`` is NOT identity-equal to ``False`` and is NOT stripped."""
    mf = {
        "run_metadata": {
            "safe_for_public_dispatch": 0,
        },
    }
    cleaned = strip_known_safe_keys(mf)
    assert "safe_for_public_dispatch" in cleaned["run_metadata"]


def test_safe_for_public_dispatch_none_is_not_stripped():
    """None is NOT identity-equal to False and is NOT stripped."""
    mf = {
        "run_metadata": {
            "safe_for_public_dispatch": None,
        },
    }
    cleaned = strip_known_safe_keys(mf)
    assert "safe_for_public_dispatch" in cleaned["run_metadata"]


def test_safe_for_public_dispatch_at_top_level_is_not_stripped():
    """The locked key at top level (NOT under run_metadata) is NOT stripped."""
    mf = {
        "safe_for_public_dispatch": False,
    }
    cleaned = strip_known_safe_keys(mf)
    assert "safe_for_public_dispatch" in cleaned
    cleaned_text = cleaned_artifact_text(
        json.dumps(mf, sort_keys=True), is_jsonl=False
    )
    # The bare ``public_dispatch`` token still appears.
    assert "public_dispatch" in cleaned_text


def test_safe_for_public_dispatch_at_wrong_nested_keypath_is_not_stripped():
    """The locked key under a different parent (not run_metadata) is NOT stripped."""
    mf = {
        "other_section": {
            "safe_for_public_dispatch": False,
        },
    }
    cleaned = strip_known_safe_keys(mf)
    assert "safe_for_public_dispatch" in cleaned["other_section"]


def test_missing_keypath_is_no_op():
    """A keypath that does not exist is silently skipped."""
    mf = {"run_metadata": {"run_id": "x"}}
    cleaned = strip_known_safe_keys(mf)
    assert cleaned == mf


def test_missing_run_metadata_parent_is_no_op():
    """If even the parent is missing, strip is a no-op."""
    mf = {"counts": {"x": 1}}
    cleaned = strip_known_safe_keys(mf)
    assert cleaned == mf


def test_strip_returns_deep_copy_does_not_mutate_input():
    """Input must NOT be mutated; output is a deep copy."""
    mf = _representative_manifest()
    snapshot = copy.deepcopy(mf)
    cleaned = strip_known_safe_keys(mf)
    assert mf == snapshot, "input was mutated"
    # And the cleaned output is a different object.
    assert cleaned is not mf
    assert cleaned["run_metadata"] is not mf["run_metadata"]
    # Mutating cleaned does not affect the original.
    cleaned["run_metadata"]["new_field"] = "x"
    assert "new_field" not in mf["run_metadata"]


# ---------------------------------------------------------------------------
# JSONL handling
# ---------------------------------------------------------------------------


def test_jsonl_strip_works_line_by_line():
    """JSONL artifacts are parsed line-by-line; each line cleaned independently."""
    line_1 = json.dumps(_representative_manifest(), sort_keys=True)
    line_2 = json.dumps(
        {
            "run_metadata": {
                "safe_for_public_dispatch": True,  # not stripped
                "run_id": "y",
            },
        },
        sort_keys=True,
    )
    raw = line_1 + "\n" + line_2 + "\n"
    cleaned = cleaned_artifact_text(raw, is_jsonl=True)
    # Line 1 is clean (locked False was stripped).
    # Line 2 still carries safe_for_public_dispatch=True (NOT stripped).
    lines = [ln for ln in cleaned.split("\n") if ln]
    assert len(lines) == 2
    parsed_1 = json.loads(lines[0])
    parsed_2 = json.loads(lines[1])
    assert "safe_for_public_dispatch" not in parsed_1["run_metadata"]
    assert parsed_2["run_metadata"]["safe_for_public_dispatch"] is True


def test_jsonl_helper_preserves_trailing_newline_structure():
    """JSONL with trailing newline yields the same line count back."""
    line_1 = json.dumps({"a": 1}, sort_keys=True)
    raw = line_1 + "\n"
    cleaned = cleaned_artifact_text(raw, is_jsonl=True)
    assert cleaned == line_1 + "\n"


def test_jsonl_empty_input_is_returned_unchanged():
    """Empty JSONL artifact is returned unchanged."""
    assert cleaned_artifact_text("", is_jsonl=True) == ""


def test_json_empty_input_is_returned_unchanged():
    """Empty JSON artifact is returned unchanged."""
    assert cleaned_artifact_text("", is_jsonl=False) == ""


def test_json_whitespace_only_input_is_returned_unchanged():
    """Whitespace-only input is returned unchanged."""
    assert cleaned_artifact_text("   \n  ", is_jsonl=False) == "   \n  "


# ---------------------------------------------------------------------------
# No substring replacement anywhere
# ---------------------------------------------------------------------------


def test_strip_does_not_substring_replace_within_string_values():
    """If a string VALUE somewhere contains the locked-key substring,
    the value is NOT modified.

    Stage 21.2 artifacts never embed ``safe_for_public_dispatch``
    as a string value, but this test pins the behavior so a
    future leak through a string value would not be hidden by
    the whitelist.
    """
    mf = {
        "run_metadata": {
            "safe_for_public_dispatch": False,  # this IS stripped
        },
        "note": "the literal safe_for_public_dispatch invariant",
    }
    cleaned = strip_known_safe_keys(mf)
    assert "safe_for_public_dispatch" not in cleaned["run_metadata"]
    # The string value is preserved verbatim; no substring strip.
    assert (
        cleaned["note"]
        == "the literal safe_for_public_dispatch invariant"
    )


def test_strip_does_not_recursively_strip_at_unrelated_nesting():
    """A nested mapping with the locked KEY but wrong PARENT path is NOT stripped."""
    mf = {
        "wrapped": {
            "run_metadata": {
                "safe_for_public_dispatch": False,
            },
        },
    }
    cleaned = strip_known_safe_keys(mf)
    # The keypath traversal is anchored at the JSON root. A
    # nested ``run_metadata.safe_for_public_dispatch`` inside a
    # ``wrapped`` parent is NOT removed.
    assert (
        cleaned["wrapped"]["run_metadata"]["safe_for_public_dispatch"]
        is False
    )


# ---------------------------------------------------------------------------
# Path-based helper
# ---------------------------------------------------------------------------


def test_cleaned_artifact_text_from_path_json(tmp_path: Path):
    """The .json suffix routes to whole-file JSON parsing."""
    target = tmp_path / "stage21_2_manifest.json"
    target.write_text(
        json.dumps(_representative_manifest(), sort_keys=True),
        encoding="utf-8",
    )
    cleaned = cleaned_artifact_text_from_path(target)
    parsed = json.loads(cleaned)
    assert "safe_for_public_dispatch" not in parsed["run_metadata"]


def test_cleaned_artifact_text_from_path_jsonl(tmp_path: Path):
    """The .jsonl suffix routes to line-by-line JSON parsing."""
    target = tmp_path / "stage21_2_ping_ledger.jsonl"
    line_1 = json.dumps({"a": 1}, sort_keys=True)
    line_2 = json.dumps({"b": 2}, sort_keys=True)
    target.write_text(line_1 + "\n" + line_2 + "\n", encoding="utf-8")
    cleaned = cleaned_artifact_text_from_path(target)
    out_lines = [ln for ln in cleaned.split("\n") if ln]
    assert len(out_lines) == 2
    assert json.loads(out_lines[0]) == {"a": 1}
    assert json.loads(out_lines[1]) == {"b": 2}


# ---------------------------------------------------------------------------
# Identity sanity (CPython invariant): False is interned
# ---------------------------------------------------------------------------


def test_python_false_identity_is_what_we_rely_on():
    """``json.loads('false') is False`` (CPython) -- the contract.

    The whitelist's identity check ``val is False`` relies on
    Python's interned ``False`` singleton. ``json.loads('false')``
    returns the singleton boolean ``False``, so the identity
    check fires. ``json.loads('0')`` returns the integer ``0``,
    not ``False``, and the identity check does NOT fire.
    """
    assert json.loads("false") is False
    assert json.loads("0") is not False
    assert json.loads("true") is True
    assert json.loads("true") is not False
    assert json.loads("null") is None
    assert json.loads("null") is not False
