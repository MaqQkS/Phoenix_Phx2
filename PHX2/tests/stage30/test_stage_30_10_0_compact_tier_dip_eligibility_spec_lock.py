"""Stage 30.10.0 compact tier-dip eligibility gate spec-lock pin tests.

Pure read-only repo inspection. No live network calls, no env reads, no
Discord traffic, no provider calls. The test does not shell out to ``git``
and does not pin any git-SHA snapshot; it asserts the Stage 30.10.0
contract via direct filesystem inspection of the three-file inventory
(spec lock markdown + manifest module + this pin test) plus substring /
line-parse / AST matches against those files, plus membership checks
against the Stage 30.0 inventory allowlist.

Pinned contract:

  * The spec doc and the manifest exist; the pin test exists.
  * The Stage 30.0 inventory allowlist admits exactly the Stage 30.10.0
    files and no Stage 30.10.1+ file.
  * The spec doc locks the purpose (the compact tier-dip eligibility gate)
    and the spec-lock-only stance.
  * The spec doc locks the read-only audit findings: the bot must not ping
    every migrated token; the tier / ATH / drawdown signals must become
    dispatch eligibility, not display-only.
  * The spec doc locks the gate placement: the gate runs BEFORE dispatch
    reservation / the private send; a non-dip skip is a normal no-send,
    never a transport-layer (``PAYLOAD_REFUSED``-style) veto.
  * The spec doc locks the existing reuse surfaces (``decide_tier`` /
    ``TierDecisionRecord`` / the tier projection / the ATH / migration /
    market context / the Stage 30.9 compact lane / the Stage 28-30 live
    runner + gates).
  * The spec doc locks the default fail-closed policy (allow Tier 1 / Tier
    2 / Tier 3; suppress Tier Unknown / Tier Not Applicable / missing ATH /
    missing migration / missing market context) and the explicit config
    fields.
  * The spec doc locks the eligibility-decision closed set + the
    per-candidate audit-record fields (with a caller-injected
    ``created_at_utc``; no wall clock).
  * The spec doc forbids public / subscriber / paid routing, Telegram, X /
    social, trading, wallet, signing, enforcement, and Stage 31; it states
    Stage 30.9.2 is paused, not abandoned.
  * The manifest is constants-only (no def / class / Call; imports only
    ``__future__`` + ``typing``; no PHX2 import).
  * No Stage 30.10.1+ runtime / classifier / model file exists; no Stage
    30.10.1+ / Stage 31 file is admitted.
  * No Stage 30.10.0 Python file carries a forbidden runtime / Stage
    21-29 / PHX1 import or a forbidden secret / transport text needle.

Stage 30.10.0 is a spec-lock / handoff document only. This test makes no
live call, sends no Discord message, and changes no runtime behavior.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Tuple

from PHX2.stage30.stage30_10_manifest import (
    STAGE30_10_0_MINOR_VERSION,
    STAGE30_10_0_SPEC_VERSION,
    STAGE30_10_0_TEST_BASENAMES,
    STAGE30_10_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_10_1_TEST_BASENAMES,
    STAGE30_10_ALLOWED_INITIAL_FILES,
    STAGE30_10_ALLOWED_STDLIB_IMPORTS,
    STAGE30_10_ALLOWED_TIER_TOKENS,
    STAGE30_10_AUDIT_RECORD_FIELDS,
    STAGE30_10_DEFAULT_ALLOWED_TIERS,
    STAGE30_10_DEFAULT_FAIL_CLOSED_ON_UNKNOWN,
    STAGE30_10_DEFAULT_POLICY_STANCE,
    STAGE30_10_DEFAULT_REQUIRE_CURRENT_MARKET_CONTEXT,
    STAGE30_10_DEFAULT_REQUIRE_MIGRATION_PRESENT,
    STAGE30_10_DEFAULT_REQUIRE_POST_MIGRATION_ATH,
    STAGE30_10_ELIGIBILITY_DECISIONS,
    STAGE30_10_EXISTING_REUSE_SURFACES,
    STAGE30_10_FAILURE_BEHAVIOR,
    STAGE30_10_FORBIDDEN_RUNTIME_IMPORTS,
    STAGE30_10_FORBIDDEN_SURFACES,
    STAGE30_10_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_10_GATE_PLACEMENT,
    STAGE30_10_LOCKED_AUDIT_FINDINGS,
    STAGE30_10_MANIFEST_BASENAME,
    STAGE30_10_NEXT_ALLOWED_STAGE,
    STAGE30_10_PLANNED_SUBSTAGES,
    STAGE30_10_POLICY_FIELDS,
    STAGE30_10_PURPOSE,
    STAGE30_10_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_10_SEND_ALLOWED_DECISION,
    STAGE30_10_SPEC_LOCK_FILENAME,
    STAGE30_10_SPEC_LOCK_PATH_PARTS,
    STAGE30_10_STAGE_30_9_2_STATUS,
    STAGE30_10_STAGE_ID,
    STAGE30_10_SUBSTAGE_ROADMAP,
    STAGE30_10_SUPPRESSED_TIER_TOKENS,
)

# The single source of truth for the Stage 30.0 inventory allowlist. The
# Stage 30.10.0 inventory-pin tests read these frozensets directly so the
# allowlist (not a duplicated copy) is what is asserted to admit exactly
# the Stage 30.10.0 files.
from PHX2.tests.stage30.test_stage_30_0_spec_lock import (
    _STAGE30_ALLOWED_BASENAMES,
    _TESTS_STAGE30_ALLOWED_BASENAMES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
SPEC_LOCK_PATH: Path = STAGE30_ROOT / STAGE30_10_SPEC_LOCK_FILENAME
MANIFEST_PATH: Path = STAGE30_ROOT / STAGE30_10_MANIFEST_BASENAME
TEST_PATH: Path = TESTS_STAGE30_ROOT / STAGE30_10_0_TEST_BASENAMES[0]


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
    """Collapse all runs of whitespace into single spaces so a phrase
    that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


def _all_30_10_0_files() -> Dict[str, str]:
    return {
        "spec": _spec_text(),
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _python_30_10_0_files() -> Dict[str, str]:
    return {
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _is_real_import_line(line: str) -> bool:
    """Return True iff ``line`` is an actual Python import statement (not a
    comment, not a string-literal line inside a tuple).
    """
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if stripped.startswith("\"") or stripped.startswith("'"):
        return False
    return stripped.startswith("import ") or stripped.startswith("from ")


def _extract_imported_module(line: str) -> str:
    """Return the module token from an ``import X`` or ``from X import Y``
    line. Empty string on malformed.
    """
    stripped = line.strip()
    tokens = stripped.split()
    if len(tokens) < 2:
        return ""
    if tokens[0] in ("import", "from"):
        return tokens[1]
    return ""


# Matches any Stage 30.10.<N> minor-version token in a basename (both the
# production ``stage30_10_<N>`` and the test ``stage_30_10_<N>`` spellings).
# A captured N >= 2 names a future Stage 30.10.2+ file; N in {0, 1} is the
# Stage 30.10.0 scaffold / the now-admitted Stage 30.10.1 eligibility model +
# classifier slice and is allowed. The Stage 30.10.0 manifest basename
# (``stage30_10_manifest.py``) carries no digit after ``stage30_10_`` and so
# matches no token at all.
_STAGE_30_10_MINOR_RE = re.compile(r"stage_?30_10_(\d+)")

# Matches a Stage 31 token (``stage31`` / ``stage_31``); not admitted yet.
_STAGE_31_RE = re.compile(r"stage_?31\b")


def _future_30_10_violations(basenames) -> list:
    violations = []
    for basename in basenames:
        for match in _STAGE_30_10_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 2:
                violations.append(basename)
    return violations


# ---------------------------------------------------------------------------
# 1. (Group 1) files exist
# ---------------------------------------------------------------------------


def test_spec_doc_exists() -> None:
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 30.10.0 requires the spec-lock document {SPEC_LOCK_PATH}"
    )


def test_manifest_exists() -> None:
    assert MANIFEST_PATH.is_file(), (
        f"Stage 30.10.0 requires the manifest module {MANIFEST_PATH}"
    )


def test_pin_test_file_exists() -> None:
    assert TEST_PATH.is_file(), (
        f"Stage 30.10.0 requires the pin test {TEST_PATH}"
    )


def test_spec_lock_path_parts_resolve_to_the_doc() -> None:
    assert STAGE30_10_SPEC_LOCK_PATH_PARTS == (
        "PHX2",
        "stage30",
        STAGE30_10_SPEC_LOCK_FILENAME,
    )
    resolved = PHX2_ROOT.parent.joinpath(*STAGE30_10_SPEC_LOCK_PATH_PARTS)
    assert resolved == SPEC_LOCK_PATH
    assert resolved.is_file()


# ---------------------------------------------------------------------------
# 2. Version + basename + stage id pins
# ---------------------------------------------------------------------------


def test_stage_id_and_minor_version_pinned() -> None:
    assert STAGE30_10_STAGE_ID == "30.10"
    assert STAGE30_10_0_MINOR_VERSION == "30.10.0"


def test_spec_version_pinned() -> None:
    assert STAGE30_10_0_SPEC_VERSION == (
        "stage30_10_v0_compact_tier_dip_eligibility"
    )


def test_basenames_pinned() -> None:
    assert STAGE30_10_SPEC_LOCK_FILENAME == (
        "STAGE_30_10_0_COMPACT_TIER_DIP_ELIGIBILITY_SPEC_LOCK.md"
    )
    assert STAGE30_10_MANIFEST_BASENAME == "stage30_10_manifest.py"
    assert STAGE30_10_0_TEST_BASENAMES == (
        "test_stage_30_10_0_compact_tier_dip_eligibility_spec_lock.py",
    )


def test_next_allowed_stage_is_30_10_1() -> None:
    assert STAGE30_10_NEXT_ALLOWED_STAGE == "30.10.1"


# ---------------------------------------------------------------------------
# 3. Required section headings, in order
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: Tuple[str, ...] = (
    "# PHX2 Stage 30.10.0",
    "## 1. Purpose",
    "## 2. Non-purpose",
    "## 3. Locked audit findings",
    "## 4. Gate placement",
    "## 5. Existing logic reuse",
    "## 6. Eligibility policy",
    "## 7. Policy config",
    "## 8. Eligibility decisions and audit record",
    "## 9. Failure behavior",
    "## 10. Future slices",
    "## 11. Stage 30.9.2 relationship",
    "## 12. Forbidden surfaces",
    "## 13. Forbidden terms and secret hygiene",
)


def test_spec_contains_all_required_section_headings() -> None:
    text = _spec_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30.10.0 spec lock missing required section heading: "
            f"{heading!r}"
        )


def test_spec_section_headings_appear_in_order() -> None:
    text = _spec_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30.10.0 spec lock section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


def test_spec_lock_only_stance_pinned_in_doc() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "Stage 30.10.0 is spec lock and tests only",
        "ZERO production `.py` file beyond the constants-only manifest",
    ):
        assert phrase in normalized, (
            f"Stage 30.10.0 spec doc must pin the spec-lock-only stance; "
            f"missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 4. Purpose: compact tier-dip eligibility gate
# ---------------------------------------------------------------------------


def test_purpose_pinned_in_manifest_and_spec() -> None:
    assert STAGE30_10_PURPOSE == "compact tier-dip eligibility gate"
    normalized = _normalized(_spec_text()).lower()
    assert "compact tier-dip eligibility gate" in normalized, (
        "Stage 30.10.0 spec lock must state its purpose is the compact "
        "tier-dip eligibility gate"
    )


# ---------------------------------------------------------------------------
# 5. (Test req) audit findings: must not ping every migrated token;
#    tier / ATH / drawdown become dispatch eligibility, not display-only
# ---------------------------------------------------------------------------


def test_spec_says_must_not_ping_every_migrated_or_tradeable() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "must not ping every migrated token" in lowered, (
        "Stage 30.10.0 spec lock must state the bot must not ping every "
        "migrated token"
    )
    assert "must not ping every tradeable candidate" in lowered, (
        "Stage 30.10.0 spec lock must state the bot must not ping every "
        "tradeable candidate"
    )


def test_spec_says_tier_ath_drawdown_become_dispatch_eligibility() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "dispatch eligibility, not display-only" in lowered, (
        "Stage 30.10.0 spec lock must state tier / ATH / drawdown must "
        "become dispatch eligibility, not display-only"
    )
    # The display-only finding names decide_tier explicitly.
    assert "decide_tier" in _spec_text(), (
        "Stage 30.10.0 spec lock must name decide_tier as the existing "
        "tier projector whose output is display-only today"
    )


def test_spec_locks_the_read_only_audit_findings() -> None:
    text = _spec_text()
    for surface in (
        "map_stage27_candidate_to_stage28_6_event",
        "dispatch_allowed = not malformed",
        "Stage28_6BoundedPrivateSessionRunner",
        "Stage30_3CompactBodyTransportWrapper",
    ):
        assert surface in text, (
            "Stage 30.10.0 spec lock must lock the read-only audit finding "
            f"surface {surface!r}"
        )
    lowered = _normalized(text).lower()
    assert "no tier / dip / ath gate exists" in lowered, (
        "Stage 30.10.0 spec lock must state no tier / dip / ATH gate exists "
        "on the dispatch path today"
    )


# ---------------------------------------------------------------------------
# 6. (Test req) gate placement: before dispatch reservation / send; no
#    transport-layer veto for a normal non-dip skip
# ---------------------------------------------------------------------------


def test_spec_says_gate_before_dispatch_reservation_and_send() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "before dispatch reservation" in lowered, (
        "Stage 30.10.0 spec lock must require the gate run BEFORE dispatch "
        "reservation"
    )
    assert "before the private discord send" in lowered, (
        "Stage 30.10.0 spec lock must require the gate run BEFORE the "
        "private Discord send"
    )


def test_spec_says_no_transport_layer_veto_for_non_dip_skip() -> None:
    text = _spec_text()
    lowered = _normalized(text).lower()
    assert "transport-layer veto" in lowered, (
        "Stage 30.10.0 spec lock must forbid a transport-layer veto"
    )
    assert "non-dip skip" in lowered, (
        "Stage 30.10.0 spec lock must name a normal non-dip skip"
    )
    assert "PAYLOAD_REFUSED" in text, (
        "Stage 30.10.0 spec lock must name the PAYLOAD_REFUSED-style "
        "transport veto it must not reuse for a non-dip skip"
    )
    assert "not a dispatch failure" in lowered, (
        "Stage 30.10.0 spec lock must state a non-dip skip is not a "
        "dispatch failure"
    )


def test_gate_placement_manifest_covers_required_terms() -> None:
    joined = " | ".join(STAGE30_10_GATE_PLACEMENT)
    for token in (
        "BEFORE dispatch reservation",
        "BEFORE the private Discord send",
        "NOT a dispatch failure",
        "no transport-layer veto for a normal non-dip skip",
        "no PAYLOAD_REFUSED-style transport veto for a normal non-dip skip",
        "tier / ATH / drawdown become dispatch eligibility, not display-only",
    ):
        assert token in joined, (
            f"STAGE30_10_GATE_PLACEMENT must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 7. (Test req) existing reuse surfaces
# ---------------------------------------------------------------------------


def test_spec_locks_existing_reuse_surfaces() -> None:
    text = _spec_text()
    for surface in (
        "decide_tier",
        "TierDecisionRecord",
        "tier_token",
    ):
        assert surface in text, (
            "Stage 30.10.0 spec lock must lock reuse of the existing "
            f"surface {surface!r}"
        )
    lowered = _normalized(text).lower()
    for phrase in (
        "existing ath context",
        "existing migration context",
        "stage 30.9 compact",
    ):
        assert phrase in lowered, (
            "Stage 30.10.0 spec lock must lock reuse of the existing "
            f"context {phrase!r}"
        )


def test_existing_reuse_surfaces_manifest_covers_required_names() -> None:
    joined = " | ".join(STAGE30_10_EXISTING_REUSE_SURFACES)
    for surface in (
        "decide_tier",
        "TierDecisionRecord",
        "tier_token",
        "existing ATH context",
        "existing migration context",
        "existing MC / LP / current market context",
        "Stage 30.9 compact / artifact lane",
        "existing Stage 28 / 29 / 30 live runner / gates",
    ):
        assert surface in joined, (
            f"STAGE30_10_EXISTING_REUSE_SURFACES must name {surface!r}"
        )


# ---------------------------------------------------------------------------
# 8. (Test req) default eligibility policy + explicit config
# ---------------------------------------------------------------------------


def test_spec_locks_default_policy_tiers_and_suppressions() -> None:
    text = _spec_text()
    # Allowed tier tokens.
    for token in ("Tier 1", "Tier 2", "Tier 3"):
        assert token in text, (
            "Stage 30.10.0 spec lock must allow the tier token "
            f"{token!r}"
        )
    # Suppressed tier tokens + missing-context suppressions.
    for token in (
        "Tier Unknown",
        "Tier Not Applicable",
        "missing ATH",
        "missing migration",
        "missing market context",
    ):
        assert token in text, (
            "Stage 30.10.0 spec lock must suppress "
            f"{token!r}"
        )
    lowered = _normalized(text).lower()
    assert "fail closed, not fail open" in lowered, (
        "Stage 30.10.0 spec lock must state the policy is fail closed, not "
        "fail open"
    )


def test_default_policy_stance_manifest_covers_required_terms() -> None:
    joined = " | ".join(STAGE30_10_DEFAULT_POLICY_STANCE)
    for token in (
        "SEND if tier_token in Tier 1 / Tier 2 / Tier 3",
        "SKIP if Tier Unknown",
        "SKIP if Tier Not Applicable",
        "SKIP if missing ATH",
        "SKIP if missing migration",
        "SKIP if missing drawdown",
        "SKIP if invalid market context",
        "SKIP if current MC / price unavailable",
        "fail closed, not fail open",
    ):
        assert token in joined, (
            f"STAGE30_10_DEFAULT_POLICY_STANCE must name {token!r}"
        )


def test_spec_locks_explicit_policy_config_fields() -> None:
    text = _spec_text()
    for field in (
        "allowed_tiers",
        "require_post_migration_ath",
        "require_migration_present",
        "require_current_market_context",
        "fail_closed_on_unknown",
    ):
        assert field in text, (
            "Stage 30.10.0 spec lock must lock the explicit policy config "
            f"field {field!r}"
        )
    lowered = _normalized(text).lower()
    # Explicit policy object, not a hidden env read.
    assert "explicit policy object" in lowered, (
        "Stage 30.10.0 spec lock must require an explicit policy object"
    )
    assert "no hidden env read" in lowered, (
        "Stage 30.10.0 spec lock must forbid a hidden env read"
    )


def test_policy_fields_manifest_is_the_five_axes() -> None:
    assert STAGE30_10_POLICY_FIELDS == (
        "allowed_tiers",
        "require_post_migration_ath",
        "require_migration_present",
        "require_current_market_context",
        "fail_closed_on_unknown",
    )


def test_policy_default_values_pinned() -> None:
    assert STAGE30_10_DEFAULT_ALLOWED_TIERS == ("TIER_1", "TIER_2", "TIER_3")
    assert STAGE30_10_DEFAULT_REQUIRE_POST_MIGRATION_ATH is True
    assert STAGE30_10_DEFAULT_REQUIRE_MIGRATION_PRESENT is True
    assert STAGE30_10_DEFAULT_REQUIRE_CURRENT_MARKET_CONTEXT is True
    assert STAGE30_10_DEFAULT_FAIL_CLOSED_ON_UNKNOWN is True


def test_allowed_and_suppressed_tier_tokens_pinned() -> None:
    assert STAGE30_10_ALLOWED_TIER_TOKENS == ("Tier 1", "Tier 2", "Tier 3")
    assert STAGE30_10_SUPPRESSED_TIER_TOKENS == (
        "Tier Unknown",
        "Tier Not Applicable",
    )


def test_spec_locks_allowed_tiers_config_tuple() -> None:
    text = _spec_text()
    assert '("TIER_1", "TIER_2", "TIER_3")' in text, (
        "Stage 30.10.0 spec lock must lock the allowed_tiers config tuple "
        'as ("TIER_1", "TIER_2", "TIER_3")'
    )


# ---------------------------------------------------------------------------
# 9. (Test req) eligibility decisions + audit record
# ---------------------------------------------------------------------------


def test_eligibility_decisions_are_the_closed_set() -> None:
    assert STAGE30_10_ELIGIBILITY_DECISIONS == (
        "ELIGIBLE_DIP",
        "SKIPPED_NOT_DIP",
        "SKIPPED_TIER_UNKNOWN",
        "SKIPPED_TIER_NOT_APPLICABLE",
        "SKIPPED_MISSING_ATH",
        "SKIPPED_MISSING_MIGRATION",
        "SKIPPED_MISSING_MARKET_CONTEXT",
        "INVALID_INPUT",
    )
    assert STAGE30_10_SEND_ALLOWED_DECISION == "ELIGIBLE_DIP"


def test_spec_locks_eligibility_decisions() -> None:
    text = _spec_text()
    for decision in STAGE30_10_ELIGIBILITY_DECISIONS:
        assert decision in text, (
            "Stage 30.10.0 spec lock must lock the eligibility decision "
            f"{decision!r}"
        )


def test_audit_record_fields_are_the_ten_axes() -> None:
    assert STAGE30_10_AUDIT_RECORD_FIELDS == (
        "candidate_id",
        "token_mint",
        "tier_token",
        "drawdown_from_ath",
        "drop_positive",
        "migration_status",
        "ath_status",
        "decision",
        "reason",
        "created_at_utc",
    )


def test_spec_locks_audit_record_fields_and_injected_clock() -> None:
    text = _spec_text()
    for field in STAGE30_10_AUDIT_RECORD_FIELDS:
        assert field in text, (
            "Stage 30.10.0 spec lock must lock the audit-record field "
            f"{field!r}"
        )
    lowered = _normalized(text).lower()
    assert "caller-injected" in lowered, (
        "Stage 30.10.0 spec lock must state created_at_utc is "
        "caller-injected"
    )
    assert "never read from a wall clock" in lowered, (
        "Stage 30.10.0 spec lock must state created_at_utc is never read "
        "from a wall clock"
    )


# ---------------------------------------------------------------------------
# 10. (Test req) Stage 30.9.2 paused, not abandoned
# ---------------------------------------------------------------------------


def test_spec_says_stage_30_9_2_paused_not_abandoned() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "stage 30.9.2 is paused, not abandoned" in lowered, (
        "Stage 30.10.0 spec lock must state Stage 30.9.2 is paused, not "
        "abandoned"
    )
    assert (
        "resume only after stage 30.10 proves dip-focused eligibility"
        in lowered
    ), (
        "Stage 30.10.0 spec lock must state Stage 30.9.2 resumes only after "
        "Stage 30.10 proves dip-focused eligibility"
    )


def test_stage_30_9_2_status_manifest_pinned() -> None:
    assert STAGE30_10_STAGE_30_9_2_STATUS == "paused, not abandoned"


# ---------------------------------------------------------------------------
# 11. (Test req) forbid public / social / trading / wallet / enforcement
# ---------------------------------------------------------------------------


def test_spec_forbids_public_social_trading_wallet_enforcement() -> None:
    text = _spec_text()
    for token in (
        "public routing",
        "subscriber routing",
        "paid tiers",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / signing",
        "enforcement activation",
        "Stage 31",
    ):
        assert token in text, (
            "Stage 30.10.0 spec lock must forbid the surface "
            f"{token!r}"
        )


def test_forbidden_surfaces_cover_all_listed_scopes() -> None:
    assert isinstance(STAGE30_10_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_10_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_10_FORBIDDEN_SURFACES)
    for token in (
        "new live runner",
        "new provider",
        "new readiness gate",
        "direct Stage 28 suppression-logic edit",
        "transport-layer veto for non-dip skip",
        "public routing",
        "subscriber routing",
        "paid tiers",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / signing",
        "enforcement activation",
        "auto-buy",
        "strategy execution",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "zstd dependency",
        "compression implementation",
        "default storage root",
        "broad always-on daemon",
        "background service",
        "live run",
        "provider call",
        "Discord send",
        "env read",
        "Stage 25/27/28/29 production import",
        "commit",
        "tag",
        "push",
        "Stage 30.10.1+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.10 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 12. (Test req) failure behavior + substage roadmap
# ---------------------------------------------------------------------------


def test_failure_behavior_is_fail_closed() -> None:
    joined = " | ".join(STAGE30_10_FAILURE_BEHAVIOR).lower()
    for token in (
        "invalid input => invalid_input, no send",
        "missing ath => skipped_missing_ath, no send",
        "eligible dip => eligible_dip, send allowed downstream",
        "fail closed on any unknown / missing input, never fail open",
    ):
        assert token in joined, (
            f"STAGE30_10_FAILURE_BEHAVIOR must state {token!r}"
        )


def test_planned_substages_are_exactly_four() -> None:
    assert STAGE30_10_PLANNED_SUBSTAGES == (
        "30.10.0",
        "30.10.1",
        "30.10.2",
        "30.10.3",
    )


def test_spec_locks_future_substages() -> None:
    text = _spec_text()
    for substage in (
        "Stage 30.10.0",
        "Stage 30.10.1",
        "Stage 30.10.2",
        "Stage 30.10.3",
    ):
        assert substage in text, (
            "Stage 30.10.0 spec lock must define the future stage; missing "
            f"{substage!r}"
        )


def test_substage_roadmap_manifest_covers_four_slices() -> None:
    joined = " | ".join(STAGE30_10_SUBSTAGE_ROADMAP)
    for token in ("30.10.0", "30.10.1", "30.10.2", "30.10.3"):
        assert token in joined, (
            f"STAGE30_10_SUBSTAGE_ROADMAP must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 13. (Group 3) Manifest constants: locked audit findings tuple
# ---------------------------------------------------------------------------


def test_locked_audit_findings_cover_required_terms() -> None:
    joined = " | ".join(STAGE30_10_LOCKED_AUDIT_FINDINGS)
    for token in (
        "tradeable Stage 27.6 candidate from a provider hint event",
        "map_stage27_candidate_to_stage28_6_event sets dispatch_allowed = not malformed",
        "Stage28_6BoundedPrivateSessionRunner",
        "Stage30_3CompactBodyTransportWrapper only blocks render failure",
        "no tier / dip / ATH gate exists on the dispatch path",
        "decide_tier computes drawdown + tier bands but its output is render / display only",
        "tier_token appears in the compact body but is not used to decide whether to send",
        "migration context is trigger / filter / display context, not a dip gate",
        "the bot must not ping every migrated token",
        "the bot must not ping every tradeable candidate",
    ):
        assert token in joined, (
            f"STAGE30_10_LOCKED_AUDIT_FINDINGS must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 14. (Group 4) Boundaries: manifest is constants-only
# ---------------------------------------------------------------------------


def test_manifest_is_constants_only() -> None:
    """AST proof: the manifest contains no function / class definition and
    no Call node anywhere (constants-only; the split-literal needle
    concatenations use ``+`` BinOps, never Calls), and imports only
    ``__future__`` + ``typing`` (no PHX2 import).
    """
    tree = ast.parse(_manifest_text())

    for node in ast.walk(tree):
        assert not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ), "Stage 30.10.0 manifest must be constants-only (no def / class)"
        assert not isinstance(node, ast.Call), (
            "Stage 30.10.0 manifest must be constants-only (no Call -- no "
            "implicit I/O at import time)"
        )

    allowed_import_roots = set(STAGE30_10_ALLOWED_STDLIB_IMPORTS)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                "Stage 30.10.0 manifest may only import __future__ / "
                f"typing; saw {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, (
                    "Stage 30.10.0 manifest may only import __future__ / "
                    f"typing; saw {alias.name!r}"
                )


def test_manifest_imports_no_phx2_module() -> None:
    for line in _manifest_text().split("\n"):
        if not _is_real_import_line(line):
            continue
        module = _extract_imported_module(line)
        assert not module.startswith("PHX2"), (
            "Stage 30.10.0 manifest must import no PHX2 module; saw "
            f"{module!r}"
        )


def test_allowed_initial_files_are_exactly_spec_and_manifest() -> None:
    assert STAGE30_10_ALLOWED_INITIAL_FILES == (
        STAGE30_10_SPEC_LOCK_FILENAME,
        STAGE30_10_MANIFEST_BASENAME,
    )
    # The only NEW production .py is the manifest; the spec lock is
    # markdown.
    py_additions = [
        name
        for name in STAGE30_10_ALLOWED_INITIAL_FILES
        if name.endswith(".py")
    ]
    assert py_additions == [STAGE30_10_MANIFEST_BASENAME]
    assert STAGE30_10_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_10_MANIFEST_BASENAME,
    )


# ---------------------------------------------------------------------------
# 15. (Group 4) Boundaries: no forbidden runtime / Stage 21-29 / PHX1 /
#     network / DB / compression imports; no env read
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
    "http",
    "websocket",
    "websockets",
    "sqlite3",
    "zstandard",
    "zstd",
    "gzip",
    "zlib",
    "lzma",
    "bz2",
)


def test_no_forbidden_runtime_imports_in_30_10_0_files() -> None:
    for filename, text in _python_30_10_0_files().items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for prefix in _FORBIDDEN_MODULE_PREFIXES:
                assert not (
                    module == prefix or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.10.0 file {filename!r} imports forbidden "
                    f"module {module!r} on line {line.rstrip()!r}"
                )


def test_no_os_environ_or_getenv_in_30_10_0_files() -> None:
    """No env read at Stage 30.10.0: no ``os.environ`` / ``os.getenv`` /
    ``os.environb`` appears as an actual attribute access in the manifest or
    test (the manifest names these only as split-literal-free documentation
    strings in the forbidden-import tuple, which are not call sites).
    """
    for filename, text in _python_30_10_0_files().items():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in (
                    "environ",
                    "getenv",
                    "environb",
                ), (
                    f"Stage 30.10.0 file {filename!r} must not read env via "
                    f"os.{node.attr}"
                )


def test_no_stage21_29_or_phx1_imports_in_30_10_0_files() -> None:
    """Neither the manifest NOR this pin test imports a Stage 21-29 /
    Stage 29.5 / PHX1 production module. (The pin test legitimately imports
    the Stage 30.0 sibling TEST module to read the inventory allowlist -- a
    ``PHX2.tests`` import -- and the Stage 30.10 manifest -- a
    ``PHX2.stage30`` import -- both of which are outside the forbidden Stage
    21-29 production range and so pass this scan.)
    """
    for filename, text in _python_30_10_0_files().items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for stage_n in range(21, 30):
                assert not module.startswith(f"PHX2.stage{stage_n}"), (
                    f"Stage 30.10.0 file {filename!r} imports forbidden "
                    f"Stage 21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.10.0 file {filename!r} imports forbidden PHX1 "
                f"module {module!r}"
            )


def test_forbidden_runtime_imports_tuple_is_non_empty() -> None:
    assert len(STAGE30_10_FORBIDDEN_RUNTIME_IMPORTS) >= 20, (
        "STAGE30_10_FORBIDDEN_RUNTIME_IMPORTS must enumerate the forbidden "
        "runtime import surfaces"
    )


# ---------------------------------------------------------------------------
# 16. (Group 4) Boundaries: no Discord / webhook send / secret / transport
#     text needle in any Stage 30.10.0 file
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles_in_30_10_0_files() -> None:
    """Case-insensitive substring scan over the spec lock, the manifest,
    and this test file. The manifest's ``STAGE30_10_FORBIDDEN_TEXT_NEEDLES``
    tuple uses split-literal forms so the manifest source itself does not
    carry the bare needles; this test imports the values at runtime and
    scans every Stage 30.10.0 file. This proves no Discord / webhook send
    surface, no transport scheme, no provider host, and no request
    auth-metadata leaks into the spec-lock files.
    """
    for filename, text in _all_30_10_0_files().items():
        lower = text.lower()
        for needle in STAGE30_10_FORBIDDEN_TEXT_NEEDLES:
            needle_lower = needle.lower()
            assert needle_lower not in lower, (
                f"Stage 30.10.0 file {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_forbidden_text_needles_tuple_is_non_empty() -> None:
    assert len(STAGE30_10_FORBIDDEN_TEXT_NEEDLES) >= 12, (
        "STAGE30_10_FORBIDDEN_TEXT_NEEDLES must enumerate the forbidden "
        "text needles"
    )


# ---------------------------------------------------------------------------
# 17. (Group 4) Boundaries: no Stage 30.10.1+ runtime / classifier / model
#     file exists yet
# ---------------------------------------------------------------------------


def test_stage30_10_production_entries_are_exactly_the_scaffold() -> None:
    """Every Stage 30.10 entry under ``PHX2/stage30/`` must be exactly the
    Stage 30.10.0 spec doc + constants-only manifest plus the Stage 30.10.1
    eligibility model + classifier modules. NO Stage 30.10.2+ runtime /
    wiring module may exist yet.
    """
    observed = {
        entry.name
        for entry in STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and (
            entry.name.startswith("stage30_10")
            or entry.name.startswith("STAGE_30_10")
        )
    }
    allowed = {
        STAGE30_10_SPEC_LOCK_FILENAME,
        STAGE30_10_MANIFEST_BASENAME,
    } | set(STAGE30_10_1_ALLOWED_STAGE30_BASENAMES)
    assert observed == allowed, (
        "Stage 30.10 production entries must be exactly the Stage 30.10.0 "
        "spec lock + manifest plus the Stage 30.10.1 model + classifier; "
        f"unexpected entries: {sorted(observed - allowed)}"
    )


def test_stage30_10_test_entries_are_exactly_the_scaffold() -> None:
    """Every Stage 30.10 test under ``PHX2/tests/stage30/`` must be exactly
    the Stage 30.10.0 spec-lock pin test plus the four Stage 30.10.1 tests
    (models, classifier, boundaries, manifest). NO Stage 30.10.2+ test may
    exist yet.
    """
    observed = {
        entry.name
        for entry in TESTS_STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and entry.name.startswith("test_stage_30_10")
    }
    allowed = {STAGE30_10_0_TEST_BASENAMES[0]} | set(
        STAGE30_10_1_TEST_BASENAMES
    )
    assert observed == allowed, (
        "Stage 30.10 test entries must be exactly the 30.10.0 pin test + the "
        "four Stage 30.10.1 tests; "
        f"unexpected entries: {sorted(observed - allowed)}"
    )


# ---------------------------------------------------------------------------
# 18. (Group 1 + 5) Stage 30.0 allowlist admits exactly the 30.10.0 files;
#     no Stage 30.10.1+ / Stage 31 file admitted.
# ---------------------------------------------------------------------------


def test_stage30_0_allowlist_admits_the_30_10_0_files() -> None:
    assert STAGE30_10_SPEC_LOCK_FILENAME in _STAGE30_ALLOWED_BASENAMES
    assert STAGE30_10_MANIFEST_BASENAME in _STAGE30_ALLOWED_BASENAMES
    assert (
        STAGE30_10_0_TEST_BASENAMES[0] in _TESTS_STAGE30_ALLOWED_BASENAMES
    )
    assert SPEC_LOCK_PATH.is_file()
    assert MANIFEST_PATH.is_file()
    assert TEST_PATH.is_file()


def test_stage30_0_allowlist_admits_no_stage_30_10_2_plus_file() -> None:
    """No Stage 30.10.2+ production / test basename is admitted by the
    Stage 30.0 allowlist yet. The now-admitted Stage 30.10.1 model +
    classifier slice (``stage30_10_1_*`` / ``test_stage_30_10_1_*``) carries
    minor token 1 and is allowed; the guard is generic and catches ANY Stage
    30.10.<N>=2+ token (30_10_2, 30_10_3, ...).
    """
    production = _future_30_10_violations(_STAGE30_ALLOWED_BASENAMES)
    assert production == [], (
        "Stage 30.0 production allowlist must not admit a Stage 30.10.2+ "
        f"file yet; saw {production!r}"
    )
    tests = _future_30_10_violations(_TESTS_STAGE30_ALLOWED_BASENAMES)
    assert tests == [], (
        "Stage 30.0 test allowlist must not admit a Stage 30.10.2+ test "
        f"file yet; saw {tests!r}"
    )


def test_no_stage_31_file_admitted() -> None:
    """Stage 31 is not admitted anywhere: neither the Stage 30.0 allowlists
    nor the on-disk Stage 30 dirs may carry such a file.
    """
    haystacks = (
        _STAGE30_ALLOWED_BASENAMES
        | _TESTS_STAGE30_ALLOWED_BASENAMES
        | {e.name for e in STAGE30_ROOT.iterdir()}
        | {e.name for e in TESTS_STAGE30_ROOT.iterdir()}
    )
    for basename in haystacks:
        lowered = basename.lower()
        assert _STAGE_31_RE.search(lowered) is None, (
            f"Stage 31 file is not admitted yet; offender {basename!r}"
        )


def test_planned_substages_admit_no_future_token() -> None:
    """The planned-substage tuple stops at 30.10.3; it admits no 30.10.4+,
    no 30.11, and no 31 token.
    """
    assert STAGE30_10_PLANNED_SUBSTAGES[-1] == "30.10.3"
    joined = " ".join(STAGE30_10_PLANNED_SUBSTAGES)
    assert "30.10.4" not in joined
    assert "30.11" not in joined
    assert "31" not in joined
