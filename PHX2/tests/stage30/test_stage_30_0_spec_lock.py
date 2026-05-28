"""Stage 30.0 spec-lock pins.

Pure read-only repo inspection. No live network calls, no env
reads, no Discord traffic. The test does not shell out to ``git``
and does not pin any git-SHA snapshot; it asserts the Stage 30.0
contract via direct filesystem inspection of the four-file
inventory and substring / regex matches against the spec-lock
markdown.

Pinned contract:

  * ``PHX2/stage30/`` and ``PHX2/tests/stage30/`` package dirs
    exist and carry the expected package markers.
  * ``PHX2/stage30/STAGE_30_SPEC_LOCK.md`` exists.
  * The Stage 30.0 inventory under ``PHX2/stage30/`` is exactly
    ``__init__.py`` + ``STAGE_30_SPEC_LOCK.md`` (no production
    ``.py``, no extra markdown).
  * The Stage 30.0 inventory under ``PHX2/tests/stage30/`` is
    exactly ``__init__.py`` + ``test_stage_30_0_spec_lock.py``.
  * The spec-lock markdown contains the ten required section
    headings.
  * The spec-lock markdown declares the exact tier bands
    (0.50-0.60 / 0.62-0.80 / 0.82-0.95) with the intentional
    gaps.
  * The spec-lock markdown declares the preferred drawdown
    formula ``drawdown_from_ath = (current_mc - ath_mc) / ath_mc``.
  * The spec-lock markdown explicitly says Stage 30 NEVER
    fabricates MC, supply, ATH MC, or current MC.
  * The spec-lock markdown explicitly says missing MC / LP / Vol
    values render as the literal ``Unknown`` (not ``0``).
  * The spec-lock markdown declares the hard forbidden scope
    (no public routing, no paid/subscriber routing, no
    enforcement, no automated trading, no wallet/signing, no
    Telegram, no X/social, no Stage 31).
  * The spec-lock markdown pins that Stage 30.0 is spec lock
    only.
  * The spec-lock markdown pins that live Discord / provider
    calls require separate explicit operator authorization.
"""

from __future__ import annotations

import re
from pathlib import Path


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
SPEC_LOCK_PATH: Path = STAGE30_ROOT / "STAGE_30_SPEC_LOCK.md"


def _spec_lock_text() -> str:
    return SPEC_LOCK_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Stage 30 package + tests package + spec lock file exist
# ---------------------------------------------------------------------------


def test_stage30_package_dir_exists() -> None:
    assert STAGE30_ROOT.is_dir(), (
        f"Stage 30.0 requires the package dir {STAGE30_ROOT}"
    )


def test_stage30_tests_package_dir_exists() -> None:
    assert TESTS_STAGE30_ROOT.is_dir(), (
        f"Stage 30.0 requires the tests package dir "
        f"{TESTS_STAGE30_ROOT}"
    )


def test_stage30_package_init_exists() -> None:
    init_path = STAGE30_ROOT / "__init__.py"
    assert init_path.is_file(), (
        f"Stage 30.0 requires the package marker {init_path}"
    )


def test_stage30_tests_package_init_exists() -> None:
    init_path = TESTS_STAGE30_ROOT / "__init__.py"
    assert init_path.is_file(), (
        f"Stage 30.0 requires the tests package marker "
        f"{init_path}"
    )


def test_stage30_spec_lock_doc_exists() -> None:
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 30.0 requires the spec-lock document "
        f"{SPEC_LOCK_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Stage 30.0 inventory is exactly four files (no production .py beyond
#    the package marker, no extra markdown, no orphaned test).
# ---------------------------------------------------------------------------


_STAGE30_ALLOWED_BASENAMES: frozenset = frozenset(
    {
        "__init__.py",
        "STAGE_30_SPEC_LOCK.md",
        # Stage 30.1 production additions.
        "tier_decision_models.py",
        "tier_decision_projector.py",
        "tier_decision_artifact_writer.py",
        "stage30_1_manifest.py",
        # Stage 30.2 production additions.
        "compact_ping_models.py",
        "compact_ping_renderer.py",
        "compact_ping_artifact_writer.py",
        "stage30_2_manifest.py",
        # Stage 30.3A production additions.
        "stage30_3_compact_runtime_models.py",
        "stage30_3_compact_candidate_projection.py",
        "stage30_3_compact_candidate_context_recorder.py",
        "stage30_3_compact_body_transport_wrapper.py",
        "stage30_3_runtime_wiring_artifact_writer.py",
        "stage30_3_manifest.py",
        # Stage 30.3B production additions.
        "stage30_3_compact_runtime_session_orchestrator.py",
    }
)


_TESTS_STAGE30_ALLOWED_BASENAMES: frozenset = frozenset(
    {
        "__init__.py",
        "test_stage_30_0_spec_lock.py",
        # Stage 30.1 test additions.
        "test_stage_30_1_tier_decision_models.py",
        "test_stage_30_1_tier_decision_projector.py",
        "test_stage_30_1_tier_decision_artifact_writer.py",
        # Stage 30.2 test additions.
        "test_stage_30_2_compact_ping_models.py",
        "test_stage_30_2_compact_ping_renderer.py",
        "test_stage_30_2_compact_ping_artifact_writer.py",
        # Stage 30.3A test additions.
        "test_stage_30_3_compact_runtime_models.py",
        "test_stage_30_3_compact_candidate_projection.py",
        "test_stage_30_3_compact_candidate_context_recorder.py",
        "test_stage_30_3_compact_body_transport_wrapper.py",
        "test_stage_30_3_compact_body_transport_wrapper_composes_with_stage29_5_6.py",
        "test_stage_30_3_runtime_wiring_artifact_writer.py",
        "test_stage_30_3_spec_lock.py",
        # Stage 30.3B test additions.
        "test_stage_30_3_compact_runtime_session_orchestrator.py",
        "test_stage_30_3_compact_runtime_session_orchestrator_redaction_safe.py",
    }
)


def _basenames_of(path: Path) -> frozenset:
    return frozenset(
        entry.name
        for entry in path.iterdir()
        if entry.name != "__pycache__"
    )


def test_stage30_package_dir_inventory_is_minimal() -> None:
    observed = _basenames_of(STAGE30_ROOT)
    extras = observed - _STAGE30_ALLOWED_BASENAMES
    assert not extras, (
        "Stage 30.0 package dir must contain only the "
        "allowed inventory; unexpected entries: "
        f"{sorted(extras)}"
    )
    missing = _STAGE30_ALLOWED_BASENAMES - observed
    assert not missing, (
        "Stage 30.0 package dir is missing required entries: "
        f"{sorted(missing)}"
    )


def test_stage30_tests_package_dir_inventory_is_minimal() -> None:
    observed = _basenames_of(TESTS_STAGE30_ROOT)
    extras = observed - _TESTS_STAGE30_ALLOWED_BASENAMES
    assert not extras, (
        "Stage 30.0 tests package dir must contain only the "
        "allowed inventory; unexpected entries: "
        f"{sorted(extras)}"
    )
    missing = _TESTS_STAGE30_ALLOWED_BASENAMES - observed
    assert not missing, (
        "Stage 30.0 tests package dir is missing required "
        f"entries: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# 3. Spec-lock markdown contains the ten required section headings.
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: tuple = (
    "## 1. Stage 30 stance pin",
    "## 2. Stage 30 substage map",
    "## 3. Hard forbidden scope",
    "## 4. Compact private ping target",
    "## 5. Tier semantics",
    "## 6. Required operator-readable fields",
    "## 7. Bounded private runtime semantics",
    "## 8. Required artifacts",
    "## 9. Ceremony discipline",
    "## 10. Acceptance criteria for Stage 30 overall",
)


def test_spec_lock_contains_all_required_section_headings() -> None:
    text = _spec_lock_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30 spec lock missing required section "
            f"heading: {heading!r}"
        )


def test_spec_lock_section_headings_appear_in_order() -> None:
    text = _spec_lock_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30 spec lock section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


# ---------------------------------------------------------------------------
# 4. Spec-lock markdown declares the exact tier bands with the
#    intentional gaps.
# ---------------------------------------------------------------------------


_REQUIRED_TIER_BAND_LINES: tuple = (
    "**TIER_1**: `0.50 <= drop <= 0.60`",
    "**TIER_2**: `0.62 <= drop <= 0.80`",
    "**TIER_3**: `0.82 <= drop <= 0.95`",
)


def test_spec_lock_declares_exact_tier_bands() -> None:
    text = _spec_lock_text()
    for band_line in _REQUIRED_TIER_BAND_LINES:
        assert band_line in text, (
            f"Stage 30 spec lock missing tier band line: "
            f"{band_line!r}"
        )


def test_spec_lock_preserves_intentional_tier_gaps() -> None:
    """Stage 30 must not silently force in-gap drops into a tier;
    the spec lock must explicitly name the gap discipline.
    """
    normalized = _normalized_whitespace(_spec_lock_text())
    required_gap_phrases = (
        # 0.60-0.62 gap pin
        "0.60-0.62",
        # 0.80-0.82 gap pin
        "0.80-0.82",
        # > 0.95 graveyard pin
        "> 0.95",
        # < 0.50 pre-tier pin
        "< 0.50",
        # no internal rounding pin
        "NEVER rounds `drop` before tier comparison",
    )
    for phrase in required_gap_phrases:
        assert phrase in normalized, (
            f"Stage 30 spec lock must explicitly name the "
            f"tier-band gap discipline: missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 5. Spec-lock markdown declares the preferred drawdown formula.
# ---------------------------------------------------------------------------


def test_spec_lock_declares_preferred_drawdown_formula() -> None:
    text = _spec_lock_text()
    formula = "drawdown_from_ath = (current_mc - ath_mc) / ath_mc"
    assert formula in text, (
        "Stage 30 spec lock must declare the preferred drawdown "
        f"formula verbatim: missing {formula!r}"
    )


def test_spec_lock_declares_equivalent_drop_formula() -> None:
    text = _spec_lock_text()
    formula = "drop = (ath_mc - current_mc) / ath_mc"
    assert formula in text, (
        "Stage 30 spec lock must declare the equivalent positive "
        f"drop formula verbatim: missing {formula!r}"
    )


def test_spec_lock_declares_abs_drop_relation() -> None:
    text = _spec_lock_text()
    relation = "drop = abs(drawdown_from_ath)"
    assert relation in text, (
        "Stage 30 spec lock must declare the abs() relation "
        f"between drop and drawdown_from_ath: missing {relation!r}"
    )


# ---------------------------------------------------------------------------
# 6. Spec-lock markdown explicitly forbids fabricating MC / supply.
# ---------------------------------------------------------------------------


def test_spec_lock_forbids_fabricating_mc_or_supply() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required_phrases = (
        # Tier model NEVER fabricates MC inputs.
        "NEVER fabricates",
        # Specifically names the three forbidden fabrications.
        "ath_mc",
        "current_mc",
        "circulating supply",
    )
    for phrase in required_phrases:
        assert phrase in normalized, (
            "Stage 30 spec lock must explicitly forbid "
            f"fabricating MC/supply inputs; missing {phrase!r}"
        )


def test_spec_lock_forbids_fabricating_mc_supply_in_basis_section() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required = (
        "Stage 30 NEVER fabricates MC, supply, ATH MC, or "
        "current MC."
    )
    assert required in normalized, (
        "Stage 30 spec lock must pin the no-fabrication "
        f"discipline verbatim in the basis section: missing "
        f"{required!r}"
    )


# ---------------------------------------------------------------------------
# 7. Spec-lock markdown says missing MC/LP/Net values render as Unknown.
# ---------------------------------------------------------------------------


def test_spec_lock_says_missing_values_render_as_unknown() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required = (
        "Missing `MC`, `LP`, or `Net` values render as the "
        "literal string `Unknown`"
    )
    assert required in normalized, (
        "Stage 30 spec lock must pin the missing-as-Unknown "
        f"rendering rule verbatim: missing {required!r}"
    )


def test_spec_lock_forbids_zero_as_missing_sentinel() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required_phrases = (
        "never `0`",
        "never `0.0`",
    )
    for phrase in required_phrases:
        assert phrase in normalized, (
            "Stage 30 spec lock must forbid 0 / 0.0 as a "
            f"missing-value sentinel: missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 8. Spec-lock markdown declares the hard forbidden scope.
# ---------------------------------------------------------------------------


_REQUIRED_FORBIDDEN_SCOPE_PHRASES: tuple = (
    "route to any public audience",
    "paid or subscriber",
    "Stage 26 or Stage 29 enforcement",
    "sign, route, or execute any trade",
    "wallet, private key, seed",
    "Telegram",
    "X / Twitter / social",
    "Stage 31",
)


def test_spec_lock_declares_hard_forbidden_scope() -> None:
    text = _spec_lock_text()
    for phrase in _REQUIRED_FORBIDDEN_SCOPE_PHRASES:
        assert phrase in text, (
            "Stage 30 spec lock must declare the hard forbidden "
            f"scope; missing {phrase!r}"
        )


def test_spec_lock_forbids_raw_provider_blobs_in_artifacts() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required = "raw provider blob"
    assert required in normalized, (
        "Stage 30 spec lock must forbid raw provider blobs in "
        f"artifacts: missing {required!r}"
    )


def test_spec_lock_forbids_printing_live_secrets() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required_phrases = (
        "live secret",
        "API key",
        "webhook URL",
    )
    for phrase in required_phrases:
        assert phrase in normalized, (
            "Stage 30 spec lock must forbid printing live "
            f"secrets; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 9. Spec-lock markdown says Stage 30.0 is spec lock only.
# ---------------------------------------------------------------------------


def test_spec_lock_pins_stage_30_0_is_spec_lock_only() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required = "Stage 30.0 is spec lock only"
    assert required in normalized, (
        "Stage 30 spec lock must pin that Stage 30.0 is spec "
        f"lock only: missing {required!r}"
    )


def test_spec_lock_pins_stage_30_0_zero_production_code() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required_phrases = (
        "ZERO production .py file beyond the package marker",
        "ZERO renderer",
        "ZERO tier model",
        "ZERO runner",
        "ZERO transport wrapper",
        "ZERO artifact writer",
    )
    for phrase in required_phrases:
        assert phrase in normalized, (
            "Stage 30 spec lock must pin the Stage 30.0 "
            f"zero-production-code stance: missing {phrase!r}"
        )


def test_spec_lock_lists_substage_map_30_0_through_30_4() -> None:
    text = _spec_lock_text()
    required_substages = (
        "Stage 30.0",
        "Stage 30.1",
        "Stage 30.2",
        "Stage 30.3",
        "Stage 30.4",
    )
    for substage in required_substages:
        assert substage in text, (
            "Stage 30 spec lock must list the full substage "
            f"map 30.0..30.4: missing {substage!r}"
        )


# ---------------------------------------------------------------------------
# 10. Spec-lock markdown says live Discord / provider calls require
#     separate explicit operator authorization.
# ---------------------------------------------------------------------------


def test_spec_lock_requires_explicit_authorization_for_live_calls() -> None:
    normalized = _normalized_whitespace(_spec_lock_text())
    required_phrases = (
        # Implementation substages must not send live Discord.
        "MUST NOT send live Discord during implementation",
        # Implementation substages must not call live providers.
        "MUST NOT call live gRPC / HTTP / WebSocket providers",
        # Live ceremony requires separate explicit authorization.
        "separate explicit operator authorization",
    )
    for phrase in required_phrases:
        assert phrase in normalized, (
            "Stage 30 spec lock must require separate explicit "
            f"authorization for live calls: missing {phrase!r}"
        )


def test_spec_lock_requires_explicit_authorization_for_tag_push_close() -> (
    None
):
    normalized = _normalized_whitespace(_spec_lock_text())
    required = (
        "MUST NOT tag, push, or close Stage 29 or Stage 30 "
        "without separate explicit operator authorization"
    )
    assert required in normalized, (
        "Stage 30 spec lock must require separate explicit "
        f"authorization for tag / push / close: missing "
        f"{required!r}"
    )


# ---------------------------------------------------------------------------
# 11. Defensive pins: spec lock carries no URL host, no webhook host
#     literal, no bearer / API-key prefix, and no Phoenix_Bot legacy
#     reference.
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_PATTERNS: tuple = (
    r"https?://",
    r"discord\.com/api/webhooks",
    r"discordapp\.com",
    r"api\.birdeye\.so",
    r"helius-rpc\.com",
    r"chainstack\.com",
    r"Bearer\s+[A-Za-z0-9]",
    r"Phoenix_Bot",
)


def test_spec_lock_carries_no_url_or_secret_literal() -> None:
    text = _spec_lock_text()
    for pattern in _FORBIDDEN_URL_PATTERNS:
        match = re.search(pattern, text)
        assert match is None, (
            "Stage 30 spec lock must not carry URL / host / "
            f"bearer / legacy literal matching {pattern!r}; "
            f"found: {match.group(0) if match else None!r}"
        )


# ---------------------------------------------------------------------------
# 12. Defensive pin: spec lock pins the example compact ping shape.
# ---------------------------------------------------------------------------


def test_spec_lock_contains_compact_ping_header_marker() -> None:
    text = _spec_lock_text()
    required_substrings = (
        "PHOENIX",
        "[Tier 3]",
        "\U0001f9e0 State",
        "MC: $",
        "ATH: $",
        "Mig: $",
        "Drop: -",
        "Age:",
        "Net:",
        "LP: $",
    )
    for substring in required_substrings:
        assert substring in text, (
            "Stage 30 spec lock must carry the compact ping "
            f"example shape; missing {substring!r}"
        )
