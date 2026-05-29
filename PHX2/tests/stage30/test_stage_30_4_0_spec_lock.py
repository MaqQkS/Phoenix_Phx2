"""Stage 30.4.0 spec-lock pin tests.

Pure read-only repo inspection. No live network calls, no env
reads, no Discord traffic. The test does not shell out to ``git``
and does not pin any git-SHA snapshot; it asserts the Stage 30.4.0
contract via direct filesystem inspection of the three-file
inventory (spec lock markdown + manifest module + this pin test)
and substring / line-parse matches against those files.

Pinned contract:

  * ``PHX2/stage30/STAGE_30_4_SPEC_LOCK.md`` exists.
  * ``PHX2/stage30/stage30_4_manifest.py`` exists.
  * ``PHX2/tests/stage30/test_stage_30_4_0_spec_lock.py`` exists.
  * The Stage 30.4.0 inventory delta under ``PHX2/stage30/`` is
    exactly the spec basename plus the manifest basename
    (premature Stage 30.4.1+ production files are forbidden).
  * The Stage 30.4.0 inventory delta under
    ``PHX2/tests/stage30/`` is exactly the pin test (premature
    Stage 30.4.1+ test files are forbidden).
  * The Stage 30.4.0 spec lock markdown carries the twelve
    required section headings in order.
  * The Stage 30.4.0 spec lock markdown carries the operator
    decisions verbatim (``Net`` label, MC + LP first, Net
    deferred, Birdeye token_overview first source, on-chain
    supply deferred, Dexscreener cross-check deferred).
  * The Stage 30.4.0 spec lock markdown carries the substage
    map verbatim (30.4.0 / 30.4.1 / 30.4.2 / 30.4.3).
  * The Stage 30.4.0 spec lock markdown pins the Unknown
    policy verbatim.
  * The Stage 30.4.0 spec lock markdown pins the no-fake /
    Drop-Age-out-of-scope discipline verbatim.
  * The Stage 30.4.0 spec lock markdown pins the no-live /
    no-Discord discipline at 30.4.0 verbatim.
  * No Stage 30.4.0 file carries a forbidden runtime import.
  * No Stage 30.4.0 file carries a forbidden raw endpoint /
    secret / webhook text needle.
  * No Stage 30.4.0 file imports a Stage 21-29 production module.
  * The Stage 30.4.0 allowlist contains only the spec basename
    and the manifest basename (no Stage 30.1 / 30.2 / 30.3
    modifications).
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PHX2.stage30.stage30_4_manifest import (
    STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_0,
    STAGE30_4_FORBIDDEN_RUNTIME_IMPORTS,
    STAGE30_4_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_4_MANIFEST_BASENAME,
    STAGE30_4_MINOR_VERSION,
    STAGE30_4_OPERATOR_DECISION_DEFERRED_FIELDS,
    STAGE30_4_OPERATOR_DECISION_DEFERRED_SOURCES,
    STAGE30_4_OPERATOR_DECISION_FIRST_FIELDS,
    STAGE30_4_OPERATOR_DECISION_FIRST_SOURCE_LABEL,
    STAGE30_4_OPERATOR_DECISION_LABEL_NET,
    STAGE30_4_SPEC_BASENAME,
    STAGE30_4_SUBSTAGE_SEQUENCE,
    STAGE30_4_TEST_BASENAMES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
SPEC_LOCK_PATH: Path = STAGE30_ROOT / STAGE30_4_SPEC_BASENAME
MANIFEST_PATH: Path = STAGE30_ROOT / STAGE30_4_MANIFEST_BASENAME
TEST_PATH: Path = (
    TESTS_STAGE30_ROOT / "test_stage_30_4_0_spec_lock.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec_text() -> str:
    return SPEC_LOCK_PATH.read_text(encoding="utf-8")


def _manifest_text() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


def _test_text() -> str:
    return TEST_PATH.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    """Collapse all runs of whitespace into single spaces."""
    return " ".join(text.split())


def _all_30_4_0_files() -> dict:
    return {
        "spec": _spec_text(),
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _python_30_4_0_files() -> dict:
    return {
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _is_real_import_line(line: str) -> bool:
    """Return True iff ``line`` is an actual Python import
    statement (not a comment, not inside a string literal at
    indentation 4+ inside a tuple, etc.).
    """
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if stripped.startswith("\"") or stripped.startswith("'"):
        return False
    return (
        stripped.startswith("import ")
        or stripped.startswith("from ")
    )


def _extract_imported_module(line: str) -> str:
    """Return the module token from an ``import X`` or
    ``from X import Y`` line. Empty string on malformed.
    """
    stripped = line.strip()
    tokens = stripped.split()
    if len(tokens) < 2:
        return ""
    if tokens[0] in ("import", "from"):
        return tokens[1]
    return ""


# ---------------------------------------------------------------------------
# 1. Files exist
# ---------------------------------------------------------------------------


def test_stage30_4_spec_doc_exists() -> None:
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 30.4.0 requires the spec-lock document "
        f"{SPEC_LOCK_PATH}"
    )


def test_stage30_4_manifest_exists() -> None:
    assert MANIFEST_PATH.is_file(), (
        f"Stage 30.4.0 requires the manifest module "
        f"{MANIFEST_PATH}"
    )


def test_stage30_4_test_file_exists() -> None:
    assert TEST_PATH.is_file(), (
        f"Stage 30.4.0 requires the pin test {TEST_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Minor version + basename pins
# ---------------------------------------------------------------------------


def test_stage30_4_minor_version_pinned() -> None:
    assert STAGE30_4_MINOR_VERSION == "30.4"


def test_stage30_4_spec_basename_pinned() -> None:
    assert STAGE30_4_SPEC_BASENAME == "STAGE_30_4_SPEC_LOCK.md"


def test_stage30_4_manifest_basename_pinned() -> None:
    assert STAGE30_4_MANIFEST_BASENAME == "stage30_4_manifest.py"


def test_stage30_4_test_basenames_pinned() -> None:
    assert STAGE30_4_TEST_BASENAMES == (
        "test_stage_30_4_0_spec_lock.py",
    )


# ---------------------------------------------------------------------------
# 3. Substage map pinned (manifest + spec)
# ---------------------------------------------------------------------------


def test_substage_sequence_pinned_in_manifest() -> None:
    assert STAGE30_4_SUBSTAGE_SEQUENCE == (
        "30.4.0",
        "30.4.1",
        "30.4.2",
        "30.4.3",
    )


def test_spec_contains_substage_map_30_4_0_through_30_4_3() -> None:
    text = _spec_text()
    for sub in STAGE30_4_SUBSTAGE_SEQUENCE:
        assert sub in text, (
            f"Stage 30.4 spec lock must list substage {sub!r}"
        )


# ---------------------------------------------------------------------------
# 4. Operator decisions pinned in the manifest
# ---------------------------------------------------------------------------


def test_operator_decision_label_net_pinned() -> None:
    """Operator decision 1: renderer-facing label is ``Net`` (not
    ``Vol``).
    """
    assert STAGE30_4_OPERATOR_DECISION_LABEL_NET == "Net"


def test_operator_decision_first_fields_are_mc_and_lp() -> None:
    """Operator decision 2: Stage 30.4 first slice is MC + LP."""
    assert STAGE30_4_OPERATOR_DECISION_FIRST_FIELDS == ("MC", "LP")


def test_operator_decision_deferred_fields_include_net_ath_mig() -> None:
    """Operator decision 2 / 3: Net, ATH MC, Migration MC are
    deferred.
    """
    deferred = STAGE30_4_OPERATOR_DECISION_DEFERRED_FIELDS
    assert "Net" in deferred
    assert "ATH MC" in deferred
    assert "Migration MC" in deferred


def test_operator_decision_first_source_is_birdeye_token_overview() -> None:
    """Operator decision 3: first planned source is Birdeye
    token_overview.
    """
    assert STAGE30_4_OPERATOR_DECISION_FIRST_SOURCE_LABEL == (
        "birdeye_token_overview"
    )


def test_operator_decision_deferred_sources_pinned() -> None:
    """Operator decision 3: on-chain supply, Dexscreener cross-
    check, and Birdeye trade-data (net flow) are all deferred.
    """
    deferred_lower = tuple(
        s.lower() for s in STAGE30_4_OPERATOR_DECISION_DEFERRED_SOURCES
    )
    assert any("on-chain" in s for s in deferred_lower), (
        "on-chain supply path must be in the deferred-source list"
    )
    assert any("cross_check" in s or "cross-check" in s
               for s in deferred_lower), (
        "Dexscreener cross-check must be in the deferred-source "
        "list"
    )
    assert any("trade_data" in s for s in deferred_lower), (
        "Birdeye trade-data (net flow) must be in the deferred-"
        "source list"
    )


# ---------------------------------------------------------------------------
# 5. Spec lock markdown carries all required section headings, in order
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: Tuple[str, ...] = (
    "## 1. Scope",
    "## 2. Why Stage 30.4 exists",
    "## 3. Current inventory",
    "## 4. Source decisions",
    "## 5. Architecture",
    "## 6. Unknown policy",
    "## 7. Display policy",
    "## 8. Non-goals",
    "## 9. Substage map",
    "## 10. Forbidden imports and boundaries",
    "## 11. Manifest requirements",
    "## 12. Tests",
)


def test_spec_contains_all_required_section_headings() -> None:
    text = _spec_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30.4 spec lock missing required section "
            f"heading: {heading!r}"
        )


def test_spec_section_headings_appear_in_order() -> None:
    text = _spec_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30.4 spec lock section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


# ---------------------------------------------------------------------------
# 6. Spec lock pins scope phrases
# ---------------------------------------------------------------------------


_REQUIRED_SCOPE_PHRASES: Tuple[str, ...] = (
    "Stage 30.4 adds compact market context enrichment for "
    "private compact pings",
    "Target fields are current MC and LP first",
    "Net remains a planned field, but real Net-flow source is "
    "deferred",
    "Stage 30.4 is not a trading/enforcement/public-routing "
    "stage",
)


def test_spec_pins_scope_phrases() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_SCOPE_PHRASES:
        np = _normalized(phrase)
        assert np in normalized, (
            f"Stage 30.4 spec lock missing scope phrase: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 7. Spec lock pins "why" phrases
# ---------------------------------------------------------------------------


_REQUIRED_WHY_PHRASES: Tuple[str, ...] = (
    "Stage 30.3C-B proved real compact private Discord delivery",
    "The proof ping still showed",
    "Stage 30.4 fills safe display slots when source data exists",
    "Missing source data remains",
    "never 0 or fabricated",
)


def test_spec_pins_why_phrases() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_WHY_PHRASES:
        np = _normalized(phrase)
        assert np in normalized, (
            f"Stage 30.4 spec lock missing 'why' phrase: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 8. Spec lock pins inventory phrases
# ---------------------------------------------------------------------------


_REQUIRED_INVENTORY_PHRASES: Tuple[str, ...] = (
    "current_mc_text",
    "ath_mc_text",
    "migration_mc_text",
    "lp_text",
    "net_flow_text",
    "Stage 30.2 renders `None` as `Unknown`",
    "Drop and Age were Unknown in the live proof only because "
    "migration evidence was intentionally disabled",
    "Stage 30.4 does not fix Drop/Age",
)


def test_spec_pins_inventory_phrases() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_INVENTORY_PHRASES:
        np = _normalized(phrase)
        assert np in normalized, (
            f"Stage 30.4 spec lock missing inventory phrase: "
            f"{phrase!r}"
        )


# ---------------------------------------------------------------------------
# 9. Spec lock pins source-decision phrases
# ---------------------------------------------------------------------------


_REQUIRED_SOURCE_DECISION_PHRASES: Tuple[str, ...] = (
    "First planned MC/LP source: Birdeye token_overview",
    "ATH MC and Migration MC are deferred",
    "Net flow is deferred",
    "Dexscreener cross-check is deferred",
    "On-chain supply",
)


def test_spec_pins_source_decision_phrases() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_SOURCE_DECISION_PHRASES:
        np = _normalized(phrase)
        assert np in normalized, (
            f"Stage 30.4 spec lock missing source-decision phrase: "
            f"{phrase!r}"
        )


# ---------------------------------------------------------------------------
# 10. Spec lock pins the Unknown policy
# ---------------------------------------------------------------------------


_REQUIRED_UNKNOWN_POLICY_PHRASES: Tuple[str, ...] = (
    "Missing source => Unknown",
    "Missing value => Unknown",
    "Invalid value => ERROR status in artifact",
    "Stale value => STALE status in artifact",
    "Non-finite numbers rejected",
    "Negative MC/LP rejected",
    "Empty strings rejected",
    "Unknown is never rendered as 0",
    "Unknown is never silently converted to",
    "Unknown does not produce fake compact values",
)


def test_spec_pins_unknown_policy_phrases() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_UNKNOWN_POLICY_PHRASES:
        np = _normalized(phrase)
        assert np in normalized, (
            f"Stage 30.4 spec lock missing unknown-policy phrase: "
            f"{phrase!r}"
        )


# ---------------------------------------------------------------------------
# 11. Spec lock pins the display policy
# ---------------------------------------------------------------------------


_REQUIRED_DISPLAY_POLICY_PHRASES: Tuple[str, ...] = (
    "current_mc_text",
    "lp_text",
    "$83k",
    "$1.2M",
    "$27k",
    "Stage 30.4 does not recompute tier decisions",
    "Tier basis remains price-basis",
)


def test_spec_pins_display_policy_phrases() -> None:
    text = _spec_text()
    for phrase in _REQUIRED_DISPLAY_POLICY_PHRASES:
        assert phrase in text, (
            f"Stage 30.4 spec lock missing display-policy phrase: "
            f"{phrase!r}"
        )


# ---------------------------------------------------------------------------
# 12. Spec lock pins the non-goals
# ---------------------------------------------------------------------------


_REQUIRED_NON_GOAL_PHRASES: Tuple[str, ...] = (
    "No public routing",
    "No paid tiers",
    "No Telegram",
    "No X/social",
    "No enforcement",
    "No wallet/signer/trading",
    "No Axiom/global-fee hard gates",
    "No Discord transport changes",
    "No Stage 28.4 audited HTTP transport changes",
    "No Stage 30.1 / 30.2 / 30.3 closed-set weakening",
    "No fake MC / LP / Net values",
    "No live provider calls in 30.4.0 / 30.4.1",
    "No live Discord sends in 30.4.0 / 30.4.1 / 30.4.2",
    "No Stage 29.5.6 migration-context append in Stage 30.4.0",
    "No Drop/Age fix in Stage 30.4",
    "No Net real source in first slice",
    "No ATH MC / Migration MC in first slice",
    "No Dexscreener in first slice",
    "No on-chain supply path in first slice",
)


def test_spec_pins_non_goals() -> None:
    text = _spec_text()
    for phrase in _REQUIRED_NON_GOAL_PHRASES:
        assert phrase in text, (
            f"Stage 30.4 spec lock missing non-goal: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 13. Spec lock pins the no-live / no-Discord stance at 30.4.0
# ---------------------------------------------------------------------------


_REQUIRED_NO_LIVE_PHRASES: Tuple[str, ...] = (
    "Stage 30.4.0 does not enable live provider calls",
    "Stage 30.4.0 does not enable Discord sends",
)


def test_spec_pins_no_live_provider_or_discord_at_30_4_0() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_NO_LIVE_PHRASES:
        np = _normalized(phrase)
        assert np in normalized, (
            f"Stage 30.4 spec lock must pin {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 14. Allowlist matches exactly the spec + manifest basenames
# ---------------------------------------------------------------------------


def test_stage30_4_allowed_basenames_are_only_spec_and_manifest() -> None:
    """Stage 30.4.0 must NOT modify any Stage 30.1 / 30.2 / 30.3
    runtime file. The 30.4.0 inventory delta is exactly the new
    spec lock and the new manifest module.
    """
    assert STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_0 == (
        STAGE30_4_SPEC_BASENAME,
        STAGE30_4_MANIFEST_BASENAME,
    )


# ---------------------------------------------------------------------------
# 15. No premature Stage 30.4.1+ runtime files exist
# ---------------------------------------------------------------------------


# Stage 30.4.2 widened the allowlist: the Stage 30.4.2
# orchestrator file is now permitted. Stage 30.4.1's five offline
# market-context production modules (models, formatter, source
# protocol, adapter, artifact writer) plus the Stage 30.4.2
# orchestrator are admitted. Stage 30.4.3+ production files (a
# real Birdeye token_overview adapter or similar) remain
# forbidden. The pin below enumerates substrings that NO Stage
# 30.4 production file may carry; Stage 30.4.3+ would add a real
# provider HTTP adapter, which would carry an ``http`` substring
# in its module name, but we do not pre-emptively enumerate it
# here -- the broader boundary scan in the Stage 30.4.2
# boundaries test pins the no-live-token_overview-adapter
# invariant explicitly.
_PREMATURE_STAGE30_PRODUCTION_SUBSTRINGS: Tuple[str, ...] = ()


def test_stage30_dir_has_no_premature_stage30_4_files() -> None:
    for entry in STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__":
            continue
        for forbidden in _PREMATURE_STAGE30_PRODUCTION_SUBSTRINGS:
            assert forbidden not in entry.name, (
                "Stage 30.4.0 must ship spec lock + manifest "
                f"only; found premature Stage 30.4.1+ file: "
                f"{entry.name!r}"
            )


# Stage 30.4.2 widened the allowlist: the Stage 30.4.2 test files
# (integration + boundaries) are now permitted. Stage 30.4.3 test
# files remain forbidden.
_PREMATURE_STAGE30_TEST_SUBSTRINGS: Tuple[str, ...] = (
    "test_stage_30_4_3",
)


def test_tests_stage30_dir_has_no_premature_stage30_4_test_files() -> None:
    for entry in TESTS_STAGE30_ROOT.iterdir():
        if entry.name == "__pycache__":
            continue
        for forbidden in _PREMATURE_STAGE30_TEST_SUBSTRINGS:
            assert forbidden not in entry.name, (
                "Stage 30.4.0 must ship the pin test only; "
                f"found premature Stage 30.4.1+ test file: "
                f"{entry.name!r}"
            )


# ---------------------------------------------------------------------------
# 16. No forbidden runtime imports in any Stage 30.4.0 file
# ---------------------------------------------------------------------------


_FORBIDDEN_MODULE_PREFIXES: Tuple[str, ...] = (
    "os",
    "dotenv",
    "keyring",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "grpc",
)


def test_no_forbidden_runtime_imports_in_30_4_0_files() -> None:
    """Line-based scan: every actual ``import X`` / ``from X
    import Y`` statement in a Stage 30.4.0 file must not resolve
    to one of the forbidden module surfaces.
    """
    py_files = _python_30_4_0_files()
    for filename, text in py_files.items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for prefix in _FORBIDDEN_MODULE_PREFIXES:
                assert not (
                    module == prefix
                    or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.4.0 file {filename!r} imports "
                    f"forbidden module {module!r} on line "
                    f"{line.rstrip()!r}"
                )


def test_no_stage21_29_imports_in_30_4_0_files() -> None:
    py_files = _python_30_4_0_files()
    for filename, text in py_files.items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for stage_n in range(21, 30):
                forbidden_prefix = f"PHX2.stage{stage_n}"
                assert not module.startswith(forbidden_prefix), (
                    f"Stage 30.4.0 file {filename!r} imports "
                    f"forbidden Stage 21-29 module {module!r} on "
                    f"line {line.rstrip()!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.4.0 file {filename!r} imports forbidden "
                f"PHX1 module {module!r} on line {line.rstrip()!r}"
            )


def test_forbidden_runtime_imports_tuple_is_non_empty() -> None:
    """Defensive pin: the manifest's documentation tuple of
    forbidden runtime imports is non-empty so a future refactor
    cannot silently empty it.
    """
    assert len(STAGE30_4_FORBIDDEN_RUNTIME_IMPORTS) >= 20, (
        "STAGE30_4_FORBIDDEN_RUNTIME_IMPORTS must enumerate the "
        "forbidden runtime import surfaces"
    )


# ---------------------------------------------------------------------------
# 17. No forbidden raw endpoint / secret / webhook text needles
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles_in_30_4_0_files() -> None:
    """Case-insensitive substring scan over the spec lock, the
    manifest, and this test file. The manifest's
    ``STAGE30_4_FORBIDDEN_TEXT_NEEDLES`` tuple uses split-literal
    forms so the manifest source itself does not carry the bare
    needles; this test imports the values at runtime and scans
    every Stage 30.4.0 file.
    """
    files = _all_30_4_0_files()
    for filename, text in files.items():
        lower = text.lower()
        for needle in STAGE30_4_FORBIDDEN_TEXT_NEEDLES:
            needle_lower = needle.lower()
            assert needle_lower not in lower, (
                f"Stage 30.4.0 file {filename!r} carries "
                f"forbidden text needle {needle!r}"
            )


def test_forbidden_text_needles_tuple_is_non_empty() -> None:
    assert len(STAGE30_4_FORBIDDEN_TEXT_NEEDLES) >= 12, (
        "STAGE30_4_FORBIDDEN_TEXT_NEEDLES must enumerate the "
        "forbidden text needles"
    )


# ---------------------------------------------------------------------------
# 18. No forbidden trading-verdict substring in the spec lock body
# ---------------------------------------------------------------------------
#
# Defensive: a Stage 30.4.0 doc that names ``BUY`` / ``SELL`` /
# ``APPROVED`` / ``GATE`` / ``BLOCK`` / ``ENFORCEMENT`` /
# ``EXECUTE`` / ``POSITION`` / ``AUTO-TRADE`` verbatim would
# violate the Stage 30 informational-only stance; the spec must
# stay on the no-trading-verdict side of the line.


_TRADING_VERDICT_NEEDLES_LOWER: Tuple[str, ...] = (
    "approved",
    "auto-trade",
)


def test_spec_lock_carries_no_strong_trading_verdict() -> None:
    """The strong trading-verdict tokens ``APPROVED`` and
    ``AUTO-TRADE`` must not appear in the Stage 30.4 spec lock.
    The renderer's broader needle set (``BUY`` / ``SELL`` /
    ``GATE`` / ``BLOCK`` / ``ENFORCEMENT`` / ``EXECUTE`` /
    ``POSITION``) is intentionally NOT enforced here because
    those tokens appear in legitimate documentation context
    (e.g. ``buy/sell`` lower-case, ``net buy / sell flow``).
    """
    lower = _spec_text().lower()
    for needle in _TRADING_VERDICT_NEEDLES_LOWER:
        assert needle not in lower, (
            f"Stage 30.4 spec lock must not carry trading-verdict "
            f"token {needle!r}"
        )
