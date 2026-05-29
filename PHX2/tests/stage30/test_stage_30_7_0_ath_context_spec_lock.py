"""Stage 30.7.0 ATH context bridge spec-lock pin tests.

Pure read-only repo inspection. No live network calls, no env
reads, no Discord traffic, no provider calls. The test does not
shell out to ``git`` and does not pin any git-SHA snapshot; it
asserts the Stage 30.7.0 contract via direct filesystem inspection
of the three-file inventory (spec lock markdown + manifest module +
this pin test) plus substring / line-parse / AST matches against
those files.

Pinned contract:

  * The spec doc, the manifest, and this pin test exist.
  * The spec doc carries the thirteen required section headings in
    order.
  * The spec pins that Stage 30.7.0 is spec lock and tests only with
    zero production .py beyond the manifest.
  * The spec pins the ATH context purpose (compact ATH display
    context, preserve MC / LP / Mig, support later drawdown / tier,
    treat ATH as evidence-backed not guessed).
  * The spec preserves the compact line shape MC | ATH | Mig.
  * The spec pins the Stage-30-owned ATH contract and the no-direct-
    dependency-on-messy-or-live-provider-code boundary.
  * The spec requires ATH Unknown for missing / error / stale /
    conflicting / bad-unit / bad-value evidence.
  * The spec requires source dominance.
  * The spec requires unit / currency safety.
  * The spec forbids raw / provider / URL / secret leakage.
  * The spec defers drawdown / tier recomputation.
  * The spec declares the Stage 30.7.0 non-goals.
  * The spec declares the future slices (30.7.1 .. 30.7.5).
  * The spec forbids ATH implementation in this stage.
  * The spec forbids live / provider / Discord / runtime changes and
    commit / tag / push.
  * The Stage 30.7.0 inventory delta admits only the spec doc plus
    the manifest (no Stage 30.7.1+ implementation file); no runtime
    production file is changed.
  * The manifest is constants-only (no Call, no def / class, only
    ``__future__`` + ``typing`` imports).
  * No Stage 30.7.0 Python file carries a forbidden runtime import or
    a forbidden Stage 21-29 / PHX1 import.
  * No Stage 30.7.0 file carries a forbidden secret / transport /
    URL-scheme / raw-payload text needle (split-literal needles so
    this test's own source carries none of them either).

Stage 30.7.0 is a spec-lock / handoff document only. This test makes
no live call, sends no Discord message, and changes no runtime
behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Tuple

from PHX2.stage30.stage30_7_manifest import (
    STAGE30_7_0_MINOR_VERSION,
    STAGE30_7_0_TEST_BASENAMES,
    STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_0,
    STAGE30_7_ATH_BASIS_VALUES,
    STAGE30_7_ATH_SOURCE_STATUS_VALUES,
    STAGE30_7_ATH_STATUS_VALUES,
    STAGE30_7_ATH_UNIT_VALUES,
    STAGE30_7_COMPACT_DISPLAY_UNKNOWN,
    STAGE30_7_FORBIDDEN_RUNTIME_IMPORTS,
    STAGE30_7_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_7_MANIFEST_BASENAME,
    STAGE30_7_MINOR_VERSION,
    STAGE30_7_PRESERVED_COMPACT_LINE_SHAPE,
    STAGE30_7_REUSED_COMPACT_SLOT_FIELD,
    STAGE30_7_SPEC_BASENAME,
    STAGE30_7_SUBSTAGE_SEQUENCE,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
SPEC_LOCK_PATH: Path = STAGE30_ROOT / STAGE30_7_SPEC_BASENAME
MANIFEST_PATH: Path = STAGE30_ROOT / STAGE30_7_MANIFEST_BASENAME
TEST_PATH: Path = (
    TESTS_STAGE30_ROOT / "test_stage_30_7_0_ath_context_spec_lock.py"
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
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


def _all_30_7_0_files() -> Dict[str, str]:
    return {
        "spec": _spec_text(),
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _python_30_7_0_files() -> Dict[str, str]:
    return {
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _is_real_import_line(line: str) -> bool:
    """Return True iff ``line`` is an actual Python import statement
    (not a comment, not a string-literal line inside a tuple).
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
    """Return the module token from an ``import X`` or ``from X
    import Y`` line. Empty string on malformed.
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


def test_spec_doc_exists() -> None:
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 30.7.0 requires the spec-lock document "
        f"{SPEC_LOCK_PATH}"
    )


def test_manifest_exists() -> None:
    assert MANIFEST_PATH.is_file(), (
        f"Stage 30.7.0 requires the manifest module {MANIFEST_PATH}"
    )


def test_pin_test_file_exists() -> None:
    assert TEST_PATH.is_file(), (
        f"Stage 30.7.0 requires the pin test {TEST_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Minor version + basename pins
# ---------------------------------------------------------------------------


def test_minor_versions_pinned() -> None:
    assert STAGE30_7_MINOR_VERSION == "30.7"
    assert STAGE30_7_0_MINOR_VERSION == "30.7.0"


def test_spec_basename_pinned() -> None:
    assert STAGE30_7_SPEC_BASENAME == (
        "STAGE_30_7_0_ATH_CONTEXT_SPEC_LOCK.md"
    )


def test_manifest_basename_pinned() -> None:
    assert STAGE30_7_MANIFEST_BASENAME == "stage30_7_manifest.py"


def test_test_basenames_pinned() -> None:
    assert STAGE30_7_0_TEST_BASENAMES == (
        "test_stage_30_7_0_ath_context_spec_lock.py",
    )


# ---------------------------------------------------------------------------
# 3. Required section headings, in order
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: Tuple[str, ...] = (
    "# PHX2 Stage 30.7.0 — ATH Context Bridge Spec Lock",
    "## 1. Stage 30.7 scope and stance",
    "## 2. Starting point",
    "## 3. Stage 30-owned ATH contract",
    "## 4. Display vocabulary and rendering",
    "## 5. Evidence confidence",
    "## 6. Unit and currency safety",
    "## 7. Source dominance",
    "## 8. Drawdown and tier dependency",
    "## 9. Sanitization and no raw leakage",
    "## 10. Prior art and reuse",
    "## 11. Non-goals",
    "## 12. Future slices",
    "## 13. Forbidden terms and secret hygiene",
)


def test_spec_contains_all_required_section_headings() -> None:
    text = _spec_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30.7.0 spec lock missing required section "
            f"heading: {heading!r}"
        )


def test_spec_section_headings_appear_in_order() -> None:
    text = _spec_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30.7.0 spec lock section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


# ---------------------------------------------------------------------------
# 4. (Test req 2) Stage 30.7.0 is spec-only
# ---------------------------------------------------------------------------


def test_spec_lock_only_stance_pinned_in_doc() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "Stage 30.7.0 is spec lock and tests only",
        "ZERO production `.py` file beyond the manifest",
    ):
        assert phrase in normalized, (
            f"Stage 30.7.0 spec doc must pin the spec-lock-only "
            f"stance; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 5. (Test req A) ATH context purpose
# ---------------------------------------------------------------------------


_REQUIRED_PURPOSE_PHRASES: Tuple[str, ...] = (
    "Provide compact ATH display context for private operator pings.",
    "Preserve the existing `MC` / `LP` and `Mig` behavior exactly.",
    "Support later, accurate drawdown / tier context",
    "Treat ATH as evidence-backed, not guessed.",
)


def test_spec_pins_ath_context_purpose() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_PURPOSE_PHRASES:
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must pin the ATH context "
            f"purpose; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 6. (Test req 3) compact line shape MC | ATH | Mig preserved
# ---------------------------------------------------------------------------


def test_spec_preserves_compact_line_shape() -> None:
    text = _spec_text()
    assert STAGE30_7_PRESERVED_COMPACT_LINE_SHAPE in text, (
        "Stage 30.7.0 spec lock must preserve the compact line "
        f"shape; missing {STAGE30_7_PRESERVED_COMPACT_LINE_SHAPE!r}"
    )
    # The line shape carries the three tokens in order.
    assert STAGE30_7_PRESERVED_COMPACT_LINE_SHAPE == (
        "• MC: <mc> | ATH: <ath> | Mig: <mig>"
    )


def test_spec_pins_starting_and_target_body_lines() -> None:
    text = _spec_text()
    for line in (
        "• MC: $X | ATH: Unknown | Mig: Known",
        "• MC: $X | ATH: $Y | Mig: Known",
    ):
        assert line in text, (
            "Stage 30.7.0 spec lock must show the sanitized "
            f"starting / target body line; missing {line!r}"
        )


# ---------------------------------------------------------------------------
# 7. (Test req B) Stage 30-owned ATH contract + provider boundary
# ---------------------------------------------------------------------------


def test_spec_pins_stage30_owned_contract() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "Stage 30 owns the compact ATH projection contract.",
        "the Stage 30 compact runtime must not directly depend on "
        "messy or live provider code",
    ):
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must pin the Stage-30-owned ATH "
            f"contract / provider boundary; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 8. (Test req C) display vocabulary / rendering
# ---------------------------------------------------------------------------


_REQUIRED_DISPLAY_PHRASES: Tuple[str, ...] = (
    "No verbose ATH debug text in the compact line.",
    "No raw provider IDs, signatures, or URLs in the display.",
    "a `$Y` formatted ATH value",
)


def test_spec_pins_display_vocabulary() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_DISPLAY_PHRASES:
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must pin the compact ATH display "
            f"vocabulary; missing {phrase!r}"
        )


def test_spec_pins_reused_slot_field() -> None:
    text = _spec_text()
    assert STAGE30_7_REUSED_COMPACT_SLOT_FIELD == "ath_mc_text"
    assert STAGE30_7_REUSED_COMPACT_SLOT_FIELD in text, (
        "Stage 30.7.0 spec lock must name the reused compact "
        f"display slot {STAGE30_7_REUSED_COMPACT_SLOT_FIELD!r}"
    )
    assert STAGE30_7_COMPACT_DISPLAY_UNKNOWN == "Unknown"


# ---------------------------------------------------------------------------
# 9. (Test req D) evidence confidence statuses + source statuses
# ---------------------------------------------------------------------------


def test_ath_status_values_pinned_in_manifest() -> None:
    assert STAGE30_7_ATH_STATUS_VALUES == (
        "ATH_KNOWN",
        "ATH_UNVERIFIED",
        "ATH_UNKNOWN",
    )


def test_ath_source_status_values_pinned_in_manifest() -> None:
    assert STAGE30_7_ATH_SOURCE_STATUS_VALUES == (
        "PRESENT",
        "UNAVAILABLE",
        "ERROR",
        "STALE",
        "CONFLICTING",
    )


def test_spec_references_all_ath_status_tokens() -> None:
    text = _spec_text()
    for token in STAGE30_7_ATH_STATUS_VALUES:
        assert token in text, (
            "Stage 30.7.0 spec lock must reference the ATH "
            f"confidence-status token; missing {token!r}"
        )


def test_spec_references_all_ath_source_status_tokens() -> None:
    text = _spec_text()
    for token in STAGE30_7_ATH_SOURCE_STATUS_VALUES:
        assert token in text, (
            "Stage 30.7.0 spec lock must reference the ATH "
            f"source-status token; missing {token!r}"
        )


def test_spec_pins_known_ath_requirements() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "a positive finite ATH value,",
        "a trusted source status (`PRESENT`),",
        "a compatible price / market context",
        "no redaction or safety failure,",
        "no conflicting evidence.",
    ):
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must pin the Known-ATH "
            f"requirements; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 10. (Test req 4) ATH Unknown for missing / error / stale /
#     conflicting / bad-unit / bad-value evidence
# ---------------------------------------------------------------------------


_REQUIRED_UNKNOWN_DOMINANCE_PHRASES: Tuple[str, ...] = (
    "source missing",
    "source error",
    "source stale",
    "conflicting evidence",
    "non-finite value",
    "zero or negative value",
    "redaction unsafe",
    "incompatible unit",
)


def test_spec_requires_ath_unknown_for_degraded_evidence() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_UNKNOWN_DOMINANCE_PHRASES:
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must require ATH Unknown for "
            f"degraded evidence; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 11. (Test req 5 + G) source dominance
# ---------------------------------------------------------------------------


def test_spec_requires_source_dominance() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "A bad source status dominates the claimed ATH value.",
        "A `PRESENT` source status can display a known ATH only when "
        "the value and the unit are valid",
    ):
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must require source dominance; "
            f"missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 12. (Test req 6 + E) unit / currency safety
# ---------------------------------------------------------------------------


_REQUIRED_UNIT_SAFETY_PHRASES: Tuple[str, ...] = (
    "ATH must not mix incompatible units.",
    "USD-denominated ATH context.",
    "SOL-denominated ATH context, if supported later.",
    "Never treat USD as SOL or SOL as USD.",
    "`Unknown` if the unit is unsupported or ambiguous.",
)


def test_spec_requires_unit_currency_safety() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_UNIT_SAFETY_PHRASES:
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must require unit / currency "
            f"safety; missing {phrase!r}"
        )


def test_ath_unit_values_pinned_in_manifest() -> None:
    assert STAGE30_7_ATH_UNIT_VALUES == ("USD", "SOL", "UNKNOWN")
    text = _spec_text()
    for token in STAGE30_7_ATH_UNIT_VALUES:
        assert token in text, (
            "Stage 30.7.0 spec lock must reference the ATH unit "
            f"token; missing {token!r}"
        )


# ---------------------------------------------------------------------------
# 13. (Test req D honesty axis) ATH basis closed set
# ---------------------------------------------------------------------------


def test_ath_basis_values_pinned_in_manifest() -> None:
    assert STAGE30_7_ATH_BASIS_VALUES == (
        "ATH_MARKET_CAP_OBSERVED",
        "ATH_PRICE_DERIVED",
        "ATH_BASIS_NONE",
    )
    text = _spec_text()
    for token in STAGE30_7_ATH_BASIS_VALUES:
        assert token in text, (
            "Stage 30.7.0 spec lock must reference the ATH basis "
            f"token; missing {token!r}"
        )


def test_spec_pins_price_derived_ath_honesty_rule() -> None:
    normalized = _normalized(_spec_text())
    assert (
        "A price-derived ATH market cap that assumes current supply "
        "is NEVER promoted to `ATH_KNOWN`"
    ) in normalized, (
        "Stage 30.7.0 spec lock must pin the price-derived ATH "
        "honesty rule (no current-supply ATH market cap is KNOWN)"
    )


# ---------------------------------------------------------------------------
# 14. (Test req F) drawdown / tier dependency deferred
# ---------------------------------------------------------------------------


def test_spec_defers_drawdown_and_tier() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "Stage 30.7.0 does not implement drawdown or tier "
        "recomputation.",
        "The tier decision and the drop display must only become "
        "trusted after the ATH source and unit are valid.",
        "If the ATH is unknown, the drop and tier display may remain "
        "the existing placeholder or stay conservative.",
    ):
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must defer drawdown / tier "
            f"recomputation; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 15. (Test req 7 + H) forbid raw / provider / URL / secret leakage
# ---------------------------------------------------------------------------


_REQUIRED_NO_LEAKAGE_PHRASES: Tuple[str, ...] = (
    "raw transaction signatures",
    "raw event logs",
    "raw provider payloads",
    "provider URLs or provider host addresses",
    "a private transport destination",
    "Discord message body text",
    "any secret, signed-token credential, or environment value",
)


def test_spec_forbids_raw_provider_url_secret_leakage() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_NO_LEAKAGE_PHRASES:
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must forbid raw / provider / "
            f"URL / secret leakage; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 16. (Prior art) Stage 25 / 27 / 29 ATH evidence reuse
# ---------------------------------------------------------------------------


_REQUIRED_PRIOR_ART_PHRASES: Tuple[str, ...] = (
    "the Stage 25 ATH candidate builder",
    "the Stage 27.4 ATH context record",
    "the Stage 29.2 Birdeye ATH source",
    "the Stage 30 compact runtime must NOT depend on it directly",
    "The no-evidence fallback mirrors the Stage 29.3 no-evidence "
    "source",
)


def test_spec_pins_prior_art_and_reuse() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_PRIOR_ART_PHRASES:
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must pin the Stage 25 / 27 / 29 "
            f"ATH evidence prior art; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 17. (Test req 8 + I) non-goals declared
# ---------------------------------------------------------------------------


_REQUIRED_NON_GOAL_PHRASES: Tuple[str, ...] = (
    "implement the ATH bridge,",
    "call Birdeye, call Dexscreener, or call any provider,",
    "change the renderer or the runtime,",
    "write a database or files,",
    "compress archives,",
    "implement a dedupe or storage writer,",
    "implement filters or enforcement,",
    "route public or subscriber pings,",
    "trade or sign transactions.",
)


def test_spec_declares_non_goals() -> None:
    normalized = _normalized(_spec_text())
    assert "Stage 30.7.0 explicitly does NOT" in normalized, (
        "Stage 30.7.0 spec lock must declare an explicit non-goals "
        "list"
    )
    for phrase in _REQUIRED_NON_GOAL_PHRASES:
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must declare the non-goal; "
            f"missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 18. (Test req 9 + J) future slices declared
# ---------------------------------------------------------------------------


def test_substage_sequence_pinned_in_manifest() -> None:
    assert STAGE30_7_SUBSTAGE_SEQUENCE == (
        "30.7.0",
        "30.7.1",
        "30.7.2",
        "30.7.3",
        "30.7.4",
        "30.7.5",
    )


_REQUIRED_FUTURE_SLICE_PHRASES: Tuple[str, ...] = (
    "Stage 30.7.0 — ATH context bridge spec lock and tests only",
    "Stage 30.7.1 — ATH context models + pure projection adapter",
    "Stage 30.7.2 — fake-wire the ATH projection into the compact "
    "ping",
    "Stage 30.7.3 — bridge sanitized Stage 25 / 27 / 29 ATH evidence "
    "into",
    "Stage 30.7.4 — offline runtime proof with `MC` + `Mig` + `ATH`",
    "Stage 30.7.5 — controlled live ATH probe / dry-run only",
)


def test_spec_declares_future_slices() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_FUTURE_SLICE_PHRASES:
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must declare the future slice; "
            f"missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 19. (Test req 11) ATH implementation forbidden in this stage
# ---------------------------------------------------------------------------


def test_spec_forbids_ath_implementation_here() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "Stage 30.7.0 is NOT the ATH bridge implementation",
        "There is no ATH bridge implementation at Stage 30.7.0.",
    ):
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must forbid ATH implementation "
            f"in this stage; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 20. (Test req 10) live / provider / Discord / runtime forbidden
# ---------------------------------------------------------------------------


_REQUIRED_NO_LIVE_PHRASES: Tuple[str, ...] = (
    "There is no live provider call during Stage 30.7.0 "
    "implementation.",
    "There is no Discord send during Stage 30.7.0 implementation.",
    "There is no candidate scan during Stage 30.7.0 implementation.",
    "There is no runtime logic change and no Stage 25 / 27 / 28 / 29 "
    "production change at Stage 30.7.0.",
    "There is no Stage 30.1 / 30.2 / 30.3 / 30.4 / 30.5 / 30.6 "
    "runtime change at Stage 30.7.0.",
    "There is no database migration and no filesystem writer at "
    "Stage 30.7.0.",
    "There is no compression and no archive implementation at Stage "
    "30.7.0.",
    "There is no filter and no enforcement at Stage 30.7.0.",
)


def test_spec_forbids_live_provider_discord_runtime() -> None:
    normalized = _normalized(_spec_text())
    for phrase in _REQUIRED_NO_LIVE_PHRASES:
        assert phrase in normalized, (
            "Stage 30.7.0 spec lock must forbid live / provider / "
            f"Discord / runtime changes; missing {phrase!r}"
        )


def test_spec_forbids_commit_tag_push() -> None:
    normalized = _normalized(_spec_text())
    assert (
        "There is no commit, no tag, and no push performed by "
        "Stage 30.7.0 implementation."
    ) in normalized, (
        "Stage 30.7.0 spec lock must pin no commit / tag / push"
    )


# ---------------------------------------------------------------------------
# 21. (Test req 13 + 14) inventory allowlist admits only 30.7.0 files;
#     no Stage 30.7.1+ implementation file; no runtime file changed.
# ---------------------------------------------------------------------------


def test_allowed_basenames_are_only_spec_and_manifest() -> None:
    """The Stage 30.7.0 production-inventory delta is exactly the new
    spec lock plus the new manifest. Stage 30.7.0 modifies NO Stage
    30.1 / 30.2 / 30.3 / 30.4 / 30.5 / 30.6 runtime file.
    """
    assert STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_0 == (
        STAGE30_7_SPEC_BASENAME,
        STAGE30_7_MANIFEST_BASENAME,
    )
    for basename in STAGE30_7_ALLOWED_STAGE30_BASENAMES_FOR_30_7_0:
        assert (STAGE30_ROOT / basename).is_file()


def test_only_stage30_7_production_files_are_spec_and_manifest() -> None:
    """Every Stage 30.7 entry under ``PHX2/stage30/`` must be exactly
    the 30.7.0 spec doc + manifest plus the 30.7.1 ATH context models +
    pure projection adapter plus the 30.7.2 compact ATH runtime adapter
    plus the 30.7.3 sanitized upstream ATH-evidence bridge plus the
    30.7.4 closure-audit doc + handoff doc + constants-only manifest. NO
    Stage 30.7.5+ production file (a controlled live ATH probe) may exist
    yet.

    Stage 30.7.1 narrowly widened this self-guard to admit exactly the
    two 30.7.1 production files; Stage 30.7.2 narrowly widened it again
    to admit exactly the one 30.7.2 runtime adapter; Stage 30.7.3
    narrowly widened it again to admit exactly the one 30.7.3 sanitized
    ATH bridge; Stage 30.7.4 narrowly widened it again to admit exactly
    the two closure docs + the constants-only 30.7.4 manifest; none
    admitted any Stage 30.7.5+ file.
    """
    observed = {
        entry.name
        for entry in STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and (
            entry.name.startswith("stage30_7")
            or entry.name.startswith("STAGE_30_7")
        )
    }
    allowed = {
        STAGE30_7_SPEC_BASENAME,
        STAGE30_7_MANIFEST_BASENAME,
        # Stage 30.7.1 offline ATH context models + projection adapter.
        "stage30_7_ath_context_models.py",
        "stage30_7_ath_context_projection.py",
        # Stage 30.7.2 opt-in compact ATH runtime adapter (the duck-typed
        # resolver + projection-to-text converter).
        "stage30_7_compact_ath_runtime_adapter.py",
        # Stage 30.7.3 offline sanitized upstream ATH-evidence bridge.
        "stage30_7_sanitized_ath_bridge.py",
        # Stage 30.7.4 closure audit + handoff docs + constants-only
        # closure manifest (no runtime production code).
        "STAGE_30_7_ATH_CONTEXT_CLOSURE_AUDIT.md",
        "STAGE_30_7_ATH_CONTEXT_HANDOFF.md",
        "stage30_7_4_manifest.py",
    }
    assert observed == allowed, (
        "Stage 30.7 production entries must be exactly the spec lock "
        f"+ manifest (30.7.0) + the 30.7.1 models / projection + the "
        f"30.7.2 runtime adapter + the 30.7.3 sanitized ATH bridge + the "
        f"30.7.4 closure docs / manifest; "
        f"unexpected entries: {sorted(observed - allowed)}"
    )


def test_only_stage30_7_test_file_is_the_pin_test() -> None:
    """Stage 30.7.0 shipped only the pin test; Stage 30.7.1 adds its
    four offline test modules; Stage 30.7.2 adds its four runtime-adapter
    test modules; Stage 30.7.3 adds its four sanitized-ATH-bridge test
    modules; Stage 30.7.4 adds its four closure-audit / handoff /
    boundaries / manifest test modules. NO Stage 30.7.5+ test file may
    exist yet.

    Stage 30.7.1 narrowly widened this self-guard to admit exactly the
    four 30.7.1 test files; Stage 30.7.2 narrowly widened it again to
    admit exactly the four 30.7.2 test files; Stage 30.7.3 narrowly
    widened it again to admit exactly the four 30.7.3 test files; Stage
    30.7.4 narrowly widened it again to admit exactly the four 30.7.4
    test files; none admitted any Stage 30.7.5+ test.
    """
    observed = {
        entry.name
        for entry in TESTS_STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and entry.name.startswith("test_stage_30_7")
    }
    allowed = {
        "test_stage_30_7_0_ath_context_spec_lock.py",
        # Stage 30.7.1 offline ATH context test additions.
        "test_stage_30_7_1_ath_context_models.py",
        "test_stage_30_7_1_ath_context_projection.py",
        "test_stage_30_7_1_boundaries.py",
        "test_stage_30_7_1_manifest.py",
        # Stage 30.7.2 opt-in compact ATH runtime adapter test additions.
        "test_stage_30_7_2_compact_ath_runtime_adapter.py",
        "test_stage_30_7_2_runtime_integration.py",
        "test_stage_30_7_2_boundaries.py",
        "test_stage_30_7_2_manifest.py",
        # Stage 30.7.3 sanitized upstream ATH-evidence bridge test additions.
        "test_stage_30_7_3_sanitized_ath_bridge.py",
        "test_stage_30_7_3_runtime_integration.py",
        "test_stage_30_7_3_boundaries.py",
        "test_stage_30_7_3_manifest.py",
        # Stage 30.7.4 closure-audit + handoff test additions.
        "test_stage_30_7_4_closure_audit.py",
        "test_stage_30_7_4_handoff.py",
        "test_stage_30_7_4_boundaries.py",
        "test_stage_30_7_4_manifest.py",
    }
    assert observed == allowed, (
        "Stage 30.7 test entries must be exactly the 30.7.0 pin test "
        f"+ the four 30.7.1 test modules + the four 30.7.2 test modules "
        f"+ the four 30.7.3 test modules + the four 30.7.4 test modules; "
        f"unexpected entries: {sorted(observed - allowed)}"
    )


# ---------------------------------------------------------------------------
# 22. (Test req 12) manifest is constants-only
# ---------------------------------------------------------------------------


def test_manifest_is_constants_only() -> None:
    """AST proof: the manifest contains no function / class
    definition and no Call node anywhere (constants-only; the
    split-literal needle concatenations use ``+`` BinOps, never
    Calls), and imports only ``__future__`` + ``typing``.
    """
    tree = ast.parse(_manifest_text())

    # No def / class anywhere.
    for node in ast.walk(tree):
        assert not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ), (
            "Stage 30.7.0 manifest must be constants-only "
            "(no def / class)"
        )
        assert not isinstance(node, ast.Call), (
            "Stage 30.7.0 manifest must be constants-only "
            "(no Call -- no implicit I/O at import time)"
        )

    # Only __future__ + typing imports at module level.
    allowed_import_roots = {"__future__", "typing"}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                "Stage 30.7.0 manifest may only import "
                f"__future__ / typing; saw {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, (
                    "Stage 30.7.0 manifest may only import "
                    f"__future__ / typing; saw {alias.name!r}"
                )


# ---------------------------------------------------------------------------
# 23. No forbidden runtime / Stage 21-29 / PHX1 imports in 30.7.0 files
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
    "sqlite3",
    "zstandard",
    "zstd",
)


def test_no_forbidden_runtime_imports_in_30_7_0_files() -> None:
    py_files = _python_30_7_0_files()
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
                    f"Stage 30.7.0 file {filename!r} imports "
                    f"forbidden module {module!r} on line "
                    f"{line.rstrip()!r}"
                )


def test_no_stage21_29_or_phx1_imports_in_30_7_0_files() -> None:
    py_files = _python_30_7_0_files()
    for filename, text in py_files.items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for stage_n in range(21, 30):
                forbidden_prefix = f"PHX2.stage{stage_n}"
                assert not module.startswith(forbidden_prefix), (
                    f"Stage 30.7.0 file {filename!r} imports "
                    f"forbidden Stage 21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.7.0 file {filename!r} imports forbidden "
                f"PHX1 module {module!r}"
            )


def test_forbidden_runtime_imports_tuple_is_non_empty() -> None:
    assert len(STAGE30_7_FORBIDDEN_RUNTIME_IMPORTS) >= 20, (
        "STAGE30_7_FORBIDDEN_RUNTIME_IMPORTS must enumerate the "
        "forbidden runtime import surfaces"
    )


# ---------------------------------------------------------------------------
# 24. No forbidden secret / transport / URL / raw-payload text needle
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles_in_30_7_0_files() -> None:
    """Case-insensitive substring scan over the spec lock, the
    manifest, and this test file. The manifest's
    ``STAGE30_7_FORBIDDEN_TEXT_NEEDLES`` tuple uses split-literal
    forms so the manifest source itself does not carry the bare
    needles; this test imports the values at runtime and scans every
    Stage 30.7.0 file.
    """
    files = _all_30_7_0_files()
    for filename, text in files.items():
        lower = text.lower()
        for needle in STAGE30_7_FORBIDDEN_TEXT_NEEDLES:
            needle_lower = needle.lower()
            assert needle_lower not in lower, (
                f"Stage 30.7.0 file {filename!r} carries forbidden "
                f"text needle {needle!r}"
            )


def test_forbidden_text_needles_tuple_is_non_empty() -> None:
    assert len(STAGE30_7_FORBIDDEN_TEXT_NEEDLES) >= 12, (
        "STAGE30_7_FORBIDDEN_TEXT_NEEDLES must enumerate the "
        "forbidden text needles"
    )
