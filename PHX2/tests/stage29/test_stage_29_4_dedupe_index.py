"""Stage 29.4 cross-pass in-memory dedupe index focused tests.

Pins:

  * ``Stage29_4SoakDedupeIndex.consume(...)`` returns ``NEW`` on a
    fresh key and records it,
  * a second ``consume(...)`` of the same key returns
    ``DUPLICATE_SUPPRESSED_SOAK`` and does NOT increase the index
    size,
  * ``contains(...)`` is read-only,
  * two ``Stage29_4SoakDedupeIndex`` instances are independent
    (the dedupe index does NOT extend across soak calls),
  * ``size(...)`` reports the safe-shape counter,
  * the index never carries a serializable ``__repr__`` of its
    contents,
  * the index refuses raw tuples / strings (only
    ``Stage29_4SoakDedupeKey`` records are accepted),
  * the index is not persisted to disk by any code path in the
    module (the module has no file I/O surface).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from PHX2.stage29.stage29_4_dedupe_index import (
    Stage29_4SoakDedupeIndex,
    build_dedupe_index,
)
from PHX2.stage29.stage29_4_soak_models import (
    DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK,
    DEDUPE_OUTCOME_NEW,
    Stage29_4InvalidDedupeKeyError,
    build_soak_dedupe_key,
)


def _make_key(suffix: str = "1"):
    return build_soak_dedupe_key(
        token_mint=f"SoMint_{suffix}",
        pair_quote_asset="SOL",
        event_kind="pumpswap_swap",
        ping_type="tradeable_private_ping",
        normalized_event_id=f"evt_{suffix}",
    )


# ---------------------------------------------------------------------------
# Constructor + size
# ---------------------------------------------------------------------------


def test_build_dedupe_index_returns_fresh_empty_instance():
    idx = build_dedupe_index()
    assert isinstance(idx, Stage29_4SoakDedupeIndex)
    assert idx.size() == 0


def test_constructor_starts_empty():
    idx = Stage29_4SoakDedupeIndex()
    assert idx.size() == 0


# ---------------------------------------------------------------------------
# Consume: NEW / DUPLICATE_SUPPRESSED_SOAK behavior
# ---------------------------------------------------------------------------


def test_consume_new_key_returns_NEW():
    idx = build_dedupe_index()
    outcome = idx.consume(_make_key("a"))
    assert outcome == DEDUPE_OUTCOME_NEW
    assert idx.size() == 1


def test_consume_duplicate_key_returns_DUPLICATE_SUPPRESSED_SOAK():
    idx = build_dedupe_index()
    key = _make_key("a")
    first = idx.consume(key)
    second = idx.consume(key)
    assert first == DEDUPE_OUTCOME_NEW
    assert second == DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK


def test_consume_duplicate_does_not_increase_size():
    idx = build_dedupe_index()
    key = _make_key("a")
    idx.consume(key)
    assert idx.size() == 1
    idx.consume(key)
    assert idx.size() == 1


def test_consume_multiple_distinct_keys_all_NEW():
    idx = build_dedupe_index()
    for i in range(5):
        outcome = idx.consume(_make_key(str(i)))
        assert outcome == DEDUPE_OUTCOME_NEW
    assert idx.size() == 5


def test_consume_alternating_distinct_and_duplicate_keys():
    idx = build_dedupe_index()
    key_a = _make_key("a")
    key_b = _make_key("b")
    assert idx.consume(key_a) == DEDUPE_OUTCOME_NEW
    assert idx.consume(key_b) == DEDUPE_OUTCOME_NEW
    assert idx.consume(key_a) == (
        DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK
    )
    assert idx.consume(key_b) == (
        DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK
    )
    assert idx.consume(_make_key("c")) == DEDUPE_OUTCOME_NEW
    assert idx.size() == 3


def test_consume_returns_closed_set_value_only():
    idx = build_dedupe_index()
    outcome_1 = idx.consume(_make_key("a"))
    outcome_2 = idx.consume(_make_key("a"))
    assert outcome_1 in (
        DEDUPE_OUTCOME_NEW,
        DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK,
    )
    assert outcome_2 in (
        DEDUPE_OUTCOME_NEW,
        DEDUPE_OUTCOME_DUPLICATE_SUPPRESSED_SOAK,
    )


# ---------------------------------------------------------------------------
# Contains: read-only
# ---------------------------------------------------------------------------


def test_contains_returns_false_for_unknown_key():
    idx = build_dedupe_index()
    assert idx.contains(_make_key("a")) is False


def test_contains_returns_true_after_consume():
    idx = build_dedupe_index()
    key = _make_key("a")
    idx.consume(key)
    assert idx.contains(key) is True


def test_contains_is_read_only():
    idx = build_dedupe_index()
    key = _make_key("a")
    idx.contains(key)
    idx.contains(key)
    assert idx.size() == 0


# ---------------------------------------------------------------------------
# Type safety
# ---------------------------------------------------------------------------


def test_consume_rejects_raw_tuple():
    idx = build_dedupe_index()
    with pytest.raises(Stage29_4InvalidDedupeKeyError):
        idx.consume(("a", "b", "c", "d", "e"))  # type: ignore[arg-type]


def test_consume_rejects_string():
    idx = build_dedupe_index()
    with pytest.raises(Stage29_4InvalidDedupeKeyError):
        idx.consume("not_a_key")  # type: ignore[arg-type]


def test_consume_rejects_none():
    idx = build_dedupe_index()
    with pytest.raises(Stage29_4InvalidDedupeKeyError):
        idx.consume(None)  # type: ignore[arg-type]


def test_contains_rejects_raw_string():
    idx = build_dedupe_index()
    with pytest.raises(Stage29_4InvalidDedupeKeyError):
        idx.contains("not_a_key")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Independence: two indexes do not share state
# ---------------------------------------------------------------------------


def test_two_indexes_are_independent():
    idx_a = build_dedupe_index()
    idx_b = build_dedupe_index()
    key = _make_key("a")
    idx_a.consume(key)
    # idx_b never saw the key.
    assert idx_b.contains(key) is False
    assert idx_b.consume(key) == DEDUPE_OUTCOME_NEW


def test_dedupe_semantics_do_not_extend_across_soak_calls():
    # Simulate two separate soak ceremonies by building two
    # indexes in sequence. The Stage 29.4 runbook guarantees that
    # the dedupe index in one ceremony does NOT inform the next.
    idx_first = build_dedupe_index()
    key = _make_key("shared")
    assert idx_first.consume(key) == DEDUPE_OUTCOME_NEW
    # First ceremony ends; the index is garbage-collected. A
    # fresh index for the second ceremony does NOT see the key.
    idx_second = build_dedupe_index()
    assert idx_second.contains(key) is False
    assert idx_second.consume(key) == DEDUPE_OUTCOME_NEW


# ---------------------------------------------------------------------------
# __repr__ does NOT expose contents
# ---------------------------------------------------------------------------


def test_repr_exposes_only_size_axis():
    idx = build_dedupe_index()
    rendered = repr(idx)
    assert "Stage29_4SoakDedupeIndex" in rendered
    assert "size=0" in rendered

    idx.consume(_make_key("a"))
    rendered = repr(idx)
    assert "size=1" in rendered
    # The mint / event-id / etc. must NEVER appear in repr.
    assert "SoMint_a" not in rendered
    assert "evt_a" not in rendered


# ---------------------------------------------------------------------------
# Persistence discipline: module source has no file I/O surface
# ---------------------------------------------------------------------------


def test_dedupe_index_module_has_no_file_io_imports():
    module_path = (
        Path(__file__).resolve().parent.parent.parent
        / "stage29"
        / "stage29_4_dedupe_index.py"
    )
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = {
        "json",
        "pickle",
        "shelve",
        "dbm",
        "shutil",
        "os",
        "tempfile",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top not in forbidden_modules, (
                    f"dedupe_index must not import file-I/O "
                    f"module {alias.name!r}"
                )
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            assert mod not in forbidden_modules, (
                f"dedupe_index must not import file-I/O module "
                f"{mod!r}"
            )


def test_dedupe_index_module_has_no_open_or_path_write_attrs():
    module_path = (
        Path(__file__).resolve().parent.parent.parent
        / "stage29"
        / "stage29_4_dedupe_index.py"
    )
    source = module_path.read_text(encoding="utf-8")
    # The module must NEVER call ``open(...)`` or use a
    # ``Path.write_*`` method; those are the file-I/O surfaces.
    forbidden_substrings = (
        "open(",
        ".write_text(",
        ".write_bytes(",
        ".touch(",
        ".mkdir(",
    )
    for needle in forbidden_substrings:
        assert needle not in source, (
            f"dedupe_index must not contain {needle!r} (no "
            f"file-I/O surface allowed)"
        )
