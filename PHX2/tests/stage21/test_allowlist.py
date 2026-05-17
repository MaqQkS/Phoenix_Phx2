"""Stage 21 allowlist tests."""

from __future__ import annotations

import pytest

from PHX2.stage21.allowlist import (
    OperatorAllowlist,
    build_allowlist_from_sequence,
    parse_allowlist,
)
from PHX2.stage21.errors import Stage21ConfigError


def test_parse_allowlist_empty_input_is_fail_closed():
    for raw in (None, "", "   ", "\t\n"):
        allowlist = parse_allowlist(raw)
        assert isinstance(allowlist, OperatorAllowlist)
        assert allowlist.is_empty()
        assert allowlist.fail_closed is True
        assert allowlist.recipients == ()


def test_parse_allowlist_single_token():
    allowlist = parse_allowlist("alice")
    assert allowlist.recipients == ("alice",)
    assert allowlist.fail_closed is False
    assert allowlist.is_empty() is False


def test_parse_allowlist_multiple_tokens_sorted_and_deduplicated():
    allowlist = parse_allowlist("bob, alice, alice, charlie")
    assert allowlist.recipients == ("alice", "bob", "charlie")
    assert allowlist.fail_closed is False


def test_parse_allowlist_tolerates_stray_commas():
    allowlist = parse_allowlist(",alice,,bob,")
    assert allowlist.recipients == ("alice", "bob")
    assert allowlist.fail_closed is False


def test_parse_allowlist_rejects_newline_token():
    with pytest.raises(Stage21ConfigError) as excinfo:
        parse_allowlist("alice,bo\nb")
    assert excinfo.value.code == "E2105"


def test_parse_allowlist_canonicalizes_whitespace():
    allowlist = parse_allowlist("  alice  ,   bob  ")
    assert allowlist.recipients == ("alice", "bob")


def test_contains_returns_true_only_for_present_recipient():
    allowlist = parse_allowlist("alice,bob")
    assert allowlist.contains("alice") is True
    assert allowlist.contains("bob") is True
    assert allowlist.contains("charlie") is False
    # The comparison is exact (no normalization at lookup time).
    assert allowlist.contains("Alice") is False


def test_build_allowlist_from_sequence_validates_each_element():
    allowlist = build_allowlist_from_sequence(["bob", "alice", "alice"])
    assert allowlist.recipients == ("alice", "bob")


def test_build_allowlist_from_sequence_skips_empty_items():
    allowlist = build_allowlist_from_sequence(["", "  ", "alice"])
    assert allowlist.recipients == ("alice",)


def test_build_allowlist_from_sequence_rejects_non_string():
    with pytest.raises(Stage21ConfigError) as excinfo:
        build_allowlist_from_sequence(["alice", 7])  # type: ignore[list-item]
    assert excinfo.value.code == "E2105"


def test_build_allowlist_from_sequence_rejects_comma_token():
    with pytest.raises(Stage21ConfigError) as excinfo:
        build_allowlist_from_sequence(["alice,bob"])
    assert excinfo.value.code == "E2105"


def test_empty_sequence_is_fail_closed():
    allowlist = build_allowlist_from_sequence([])
    assert allowlist.recipients == ()
    assert allowlist.fail_closed is True
