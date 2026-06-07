"""Stage 30.11.0 dip-gated live dispatch wiring spec-lock pin tests.

Pure read-only repo inspection. No live network calls, no env reads, no
Discord traffic, no provider calls. The test does not shell out to ``git``
and does not pin any git-SHA snapshot; it asserts the Stage 30.11.0 contract
via direct filesystem inspection of the three-file inventory (spec lock
markdown + manifest module + this pin test) plus substring / line-parse / AST
matches against those files, plus membership checks against the Stage 30.0
inventory allowlist.

Pinned contract:

  * The spec doc and the manifest exist; the pin test exists.
  * The Stage 30.0 inventory allowlist admits exactly the Stage 30.11.0 files
    and no Stage 30.11.1+ file.
  * The spec doc locks the purpose (the dip-gated live dispatch wiring) and
    the spec-lock-only stance.
  * The spec doc locks the why-now finding: the committed Stage 30.9.3 dip
    gate seam is offline and not wired into the live path; the only committed
    live path is the ungated Stage 29.3 smoke.
  * The spec doc locks the gate placement + only-PASS send: the committed dip
    gate runs BEFORE dispatch reservation / the private send; only a
    PASS_TO_DISPATCH candidate may reserve a dispatch / drive the private
    send; a non-dip skip is a normal no-send, never a transport-layer
    (PAYLOAD_REFUSED-style) veto.
  * The spec doc locks the existing reuse surfaces (the committed Stage 30.9.3
    seam, the Stage 30.10 dip-gate stack, decide_tier / TierDecisionRecord /
    tier_token, the ATH / migration / market context, the Stage 28-30 live
    session + gates).
  * The spec doc locks the wall-clock max_runtime_seconds bound.
  * The spec doc locks the permitted scope expansion (the runtime slices may
    compose the committed live surfaces behind the dip gate).
  * The spec doc locks the dip-gate decision tokens + the live result counter
    axes (with a caller-injected created_at_utc; no wall clock on the proof).
  * The spec doc forbids public / subscriber / paid routing, Telegram, X /
    social, trading, wallet, signing, enforcement, the direct reuse of the
    ungated Stage 29.3 send path, and Stage 31; it states Stage 30.9.2 is
    paused, not abandoned.
  * The manifest is constants-only (no def / class / Call; imports only
    ``__future__`` + ``typing``; no PHX2 import).
  * No Stage 30.11.1+ runtime / bridge / seam / sink file exists; no Stage
    30.11.1+ / Stage 31 file is admitted.
  * No Stage 30.11.0 Python file carries a forbidden runtime / Stage 21-29 /
    PHX1 import or a forbidden secret / transport text needle.

Stage 30.11.0 is a spec-lock / handoff document only. This test makes no live
call, sends no Discord message, and changes no runtime behavior.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, Tuple

from PHX2.stage30.stage30_11_manifest import (
    STAGE30_11_0_MINOR_VERSION,
    STAGE30_11_0_SPEC_VERSION,
    STAGE30_11_0_TEST_BASENAMES,
    STAGE30_11_1_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_1_TEST_BASENAMES,
    STAGE30_11_2_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_2_TEST_BASENAMES,
    STAGE30_11_3_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_3_TEST_BASENAMES,
    STAGE30_11_4_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_4_TEST_BASENAMES,
    STAGE30_11_5_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_5_TEST_BASENAMES,
    STAGE30_11_6_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_6_TEST_BASENAMES,
    STAGE30_11_7_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_7_TEST_BASENAMES,
    STAGE30_11_8_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_8_TEST_BASENAMES,
    STAGE30_11_9_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_9_TEST_BASENAMES,
    STAGE30_11_10_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_10_TEST_BASENAMES,
    STAGE30_11_11_ALLOWED_STAGE30_BASENAMES,
    STAGE30_11_11_TEST_BASENAMES,
    STAGE30_11_ALLOWED_INITIAL_FILES,
    STAGE30_11_ALLOWED_STDLIB_IMPORTS,
    STAGE30_11_ALWAYS_ZERO_AXES,
    STAGE30_11_EXISTING_REUSE_SURFACES,
    STAGE30_11_FAILURE_BEHAVIOR,
    STAGE30_11_FORBIDDEN_RUNTIME_IMPORTS,
    STAGE30_11_FORBIDDEN_SURFACES,
    STAGE30_11_FORBIDDEN_TEXT_NEEDLES,
    STAGE30_11_GATE_DECISIONS,
    STAGE30_11_GATE_PASS_DECISION,
    STAGE30_11_GATE_PLACEMENT,
    STAGE30_11_MANIFEST_BASENAME,
    STAGE30_11_NEXT_ALLOWED_STAGE,
    STAGE30_11_ONLY_PASS_SEND_RULE,
    STAGE30_11_PERMITTED_SCOPE_NOTE,
    STAGE30_11_PLANNED_SUBSTAGES,
    STAGE30_11_PURPOSE,
    STAGE30_11_RESULT_COUNTER_AXES,
    STAGE30_11_RUNTIME_BOUND,
    STAGE30_11_SCANNED_PRODUCTION_BASENAMES,
    STAGE30_11_SPEC_LOCK_FILENAME,
    STAGE30_11_SPEC_LOCK_PATH_PARTS,
    STAGE30_11_STAGE_30_9_2_STATUS,
    STAGE30_11_STAGE_ID,
    STAGE30_11_SUBSTAGE_ROADMAP,
    STAGE30_11_WHY_NOW_FINDINGS,
)

# The single source of truth for the Stage 30.0 inventory allowlist. The
# Stage 30.11.0 inventory-pin tests read these frozensets directly so the
# allowlist (not a duplicated copy) is what is asserted to admit exactly the
# Stage 30.11.0 files.
from PHX2.tests.stage30.test_stage_30_0_spec_lock import (
    _STAGE30_ALLOWED_BASENAMES,
    _TESTS_STAGE30_ALLOWED_BASENAMES,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
TESTS_STAGE30_ROOT: Path = PHX2_ROOT / "tests" / "stage30"
SPEC_LOCK_PATH: Path = STAGE30_ROOT / STAGE30_11_SPEC_LOCK_FILENAME
MANIFEST_PATH: Path = STAGE30_ROOT / STAGE30_11_MANIFEST_BASENAME
TEST_PATH: Path = TESTS_STAGE30_ROOT / STAGE30_11_0_TEST_BASENAMES[0]


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
    """Collapse all runs of whitespace into single spaces so a phrase that
    wraps across a markdown line still matches.
    """
    return " ".join(text.split())


def _all_30_11_0_files() -> Dict[str, str]:
    return {
        "spec": _spec_text(),
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _python_30_11_0_files() -> Dict[str, str]:
    return {
        "manifest": _manifest_text(),
        "test": _test_text(),
    }


def _is_real_import_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if stripped.startswith("\"") or stripped.startswith("'"):
        return False
    return stripped.startswith("import ") or stripped.startswith("from ")


def _extract_imported_module(line: str) -> str:
    stripped = line.strip()
    tokens = stripped.split()
    if len(tokens) < 2:
        return ""
    if tokens[0] in ("import", "from"):
        return tokens[1]
    return ""


# Matches any Stage 30.11.<N> minor-version token in a basename (both the
# production ``stage30_11_<N>`` and the test ``stage_30_11_<N>`` spellings).
# A captured N >= 12 names a future Stage 30.11.12+ file; N in {0, 1, 2, 3, 4, 5, 6,
# 7, 8, 9, 10} is the Stage 30.11.0 scaffold (the spec doc + this pin test) / the
# now-admitted Stage 30.11.1 assembly bridge slice / the now-admitted Stage 30.11.2
# runtime gate seam slice / the now-admitted Stage 30.11.3 private sink adapter
# slice / the now-admitted Stage 30.11.4 offline end-to-end proof slice / the
# now-admitted Stage 30.11.5 controlled live ceremony wiring slice / the
# now-admitted Stage 30.11.6 real candidate source / harvest seam slice / the
# now-admitted Stage 30.11.7 candidate dip-enrichment bridge slice / the
# now-admitted Stage 30.11.8 narrow migration-confirmation bridge slice / the
# now-admitted Stage 30.11.9 mint-keyed migration evidence-source slice / the
# now-admitted Stage 30.11.10 real ATH-resolver bridge slice / the now-admitted
# Stage 30.11.11 migration-anchored ATH source slice and is allowed.
# The Stage 30.11.0 manifest basename (``stage30_11_manifest.py``) carries no
# digit after ``stage30_11_`` and so matches no token at all.
_STAGE_30_11_MINOR_RE = re.compile(r"stage_?30_11_(\d+)")

# Matches a Stage 31 token (``stage31`` / ``stage_31``); not admitted yet.
_STAGE_31_RE = re.compile(r"stage_?31\b")


def _future_30_11_violations(basenames) -> list:
    violations = []
    for basename in basenames:
        for match in _STAGE_30_11_MINOR_RE.finditer(basename.lower()):
            if int(match.group(1)) >= 12:
                violations.append(basename)
    return violations


# ---------------------------------------------------------------------------
# 1. Files exist
# ---------------------------------------------------------------------------


def test_spec_doc_exists() -> None:
    assert SPEC_LOCK_PATH.is_file(), (
        f"Stage 30.11.0 requires the spec-lock document {SPEC_LOCK_PATH}"
    )


def test_manifest_exists() -> None:
    assert MANIFEST_PATH.is_file(), (
        f"Stage 30.11.0 requires the manifest module {MANIFEST_PATH}"
    )


def test_pin_test_file_exists() -> None:
    assert TEST_PATH.is_file(), (
        f"Stage 30.11.0 requires the pin test {TEST_PATH}"
    )


def test_spec_lock_path_parts_resolve_to_the_doc() -> None:
    assert STAGE30_11_SPEC_LOCK_PATH_PARTS == (
        "PHX2",
        "stage30",
        STAGE30_11_SPEC_LOCK_FILENAME,
    )
    resolved = PHX2_ROOT.parent.joinpath(*STAGE30_11_SPEC_LOCK_PATH_PARTS)
    assert resolved == SPEC_LOCK_PATH
    assert resolved.is_file()


# ---------------------------------------------------------------------------
# 2. Version + basename + stage id pins
# ---------------------------------------------------------------------------


def test_stage_id_and_minor_version_pinned() -> None:
    assert STAGE30_11_STAGE_ID == "30.11"
    assert STAGE30_11_0_MINOR_VERSION == "30.11.0"


def test_spec_version_pinned() -> None:
    assert STAGE30_11_0_SPEC_VERSION == (
        "stage30_11_v0_dip_gated_live_dispatch_wiring"
    )


def test_basenames_pinned() -> None:
    assert STAGE30_11_SPEC_LOCK_FILENAME == (
        "STAGE_30_11_0_DIP_GATED_LIVE_DISPATCH_WIRING_SPEC_LOCK.md"
    )
    assert STAGE30_11_MANIFEST_BASENAME == "stage30_11_manifest.py"
    assert STAGE30_11_0_TEST_BASENAMES == (
        "test_stage_30_11_0_dip_gated_live_dispatch_wiring_spec_lock.py",
    )


def test_next_allowed_stage_is_30_11_1() -> None:
    assert STAGE30_11_NEXT_ALLOWED_STAGE == "30.11.1"


# ---------------------------------------------------------------------------
# 3. Required section headings, in order
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: Tuple[str, ...] = (
    "# PHX2 Stage 30.11.0",
    "## 1. Purpose",
    "## 2. Non-purpose",
    "## 3. Why now",
    "## 4. Gate placement and only-PASS send",
    "## 5. Existing logic reuse",
    "## 6. Runtime bound",
    "## 7. Permitted scope expansion",
    "## 8. Dip-gate decisions and result counters",
    "## 9. Failure behavior",
    "## 10. Future slices",
    "## 11. Stage 30.9.2 and 30.9.3 relationship",
    "## 12. Forbidden surfaces",
    "## 13. Forbidden terms and secret hygiene",
)


def test_spec_contains_all_required_section_headings() -> None:
    text = _spec_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30.11.0 spec lock missing required section heading: "
            f"{heading!r}"
        )


def test_spec_section_headings_appear_in_order() -> None:
    text = _spec_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30.11.0 spec lock section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


def test_spec_lock_only_stance_pinned_in_doc() -> None:
    normalized = _normalized(_spec_text())
    for phrase in (
        "Stage 30.11.0 is spec lock and tests only",
        "ZERO production `.py` file beyond the constants-only manifest",
    ):
        assert phrase in normalized, (
            f"Stage 30.11.0 spec doc must pin the spec-lock-only stance; "
            f"missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 4. Purpose: dip-gated live dispatch wiring
# ---------------------------------------------------------------------------


def test_purpose_pinned_in_manifest_and_spec() -> None:
    assert STAGE30_11_PURPOSE == "dip-gated live dispatch wiring"
    normalized = _normalized(_spec_text()).lower()
    assert "dip-gated live dispatch wiring" in normalized, (
        "Stage 30.11.0 spec lock must state its purpose is the dip-gated live "
        "dispatch wiring"
    )


def test_spec_says_must_not_ping_every_migrated_or_tradeable() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "must not ping every migrated token" in lowered, (
        "Stage 30.11.0 spec lock must state the bot must not ping every "
        "migrated token"
    )
    assert "must not ping every tradeable candidate" in lowered, (
        "Stage 30.11.0 spec lock must state the bot must not ping every "
        "tradeable candidate"
    )


# ---------------------------------------------------------------------------
# 5. Why-now finding
# ---------------------------------------------------------------------------


def test_spec_locks_the_why_now_finding() -> None:
    lowered = _normalized(_spec_text()).lower()
    for phrase in (
        "nothing committed assembles a live candidate",
        "nothing committed wires the stage 30.9.3 seam",
        "the only committed live path is the ungated stage 29.3 smoke",
    ):
        assert phrase in lowered, (
            f"Stage 30.11.0 spec lock must lock the why-now finding {phrase!r}"
        )


def test_why_now_findings_manifest_covers_required_terms() -> None:
    joined = " | ".join(STAGE30_11_WHY_NOW_FINDINGS).lower()
    for token in (
        "pure / offline",
        "nothing committed assembles a live candidate",
        "nothing committed wires the stage 30.9.3 seam",
        "the only committed live path is the ungated stage 29.3 smoke",
        "no native wall-clock runtime bound",
    ):
        assert token in joined, (
            f"STAGE30_11_WHY_NOW_FINDINGS must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 6. Gate placement + only-PASS send
# ---------------------------------------------------------------------------


def test_spec_says_gate_before_dispatch_reservation_and_send() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "before dispatch reservation" in lowered, (
        "Stage 30.11.0 spec lock must require the gate run BEFORE dispatch "
        "reservation"
    )
    assert "before the private discord send" in lowered, (
        "Stage 30.11.0 spec lock must require the gate run BEFORE the private "
        "Discord send"
    )


def test_spec_says_only_pass_may_reserve_and_send() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "only a `pass_to_dispatch` candidate may reserve a dispatch" in lowered, (
        "Stage 30.11.0 spec lock must state only a PASS_TO_DISPATCH candidate "
        "may reserve a dispatch"
    )
    assert "the real send is impossible without a" in lowered, (
        "Stage 30.11.0 spec lock must state the real send is impossible "
        "without a PASS_TO_DISPATCH decision"
    )


def test_spec_says_no_transport_layer_veto_for_non_dip_skip() -> None:
    text = _spec_text()
    lowered = _normalized(text).lower()
    assert "transport-layer veto" in lowered, (
        "Stage 30.11.0 spec lock must forbid a transport-layer veto"
    )
    assert "non-dip skip" in lowered, (
        "Stage 30.11.0 spec lock must name a normal non-dip skip"
    )
    assert "PAYLOAD_REFUSED" in text, (
        "Stage 30.11.0 spec lock must name the PAYLOAD_REFUSED-style transport "
        "veto it must not reuse for a non-dip skip"
    )
    assert "not a dispatch failure" in lowered, (
        "Stage 30.11.0 spec lock must state a non-dip skip is not a dispatch "
        "failure"
    )


def test_gate_placement_manifest_covers_required_terms() -> None:
    joined = " | ".join(STAGE30_11_GATE_PLACEMENT)
    for token in (
        "committed dip gate evaluated BEFORE dispatch reservation",
        "committed dip gate evaluated BEFORE the private Discord send",
        "only a PASS candidate may reserve a dispatch",
        "only a PASS candidate may drive the private send",
        "non-dip skip is a normal no-send, NOT a dispatch failure",
        "no transport-layer veto for a normal non-dip skip",
        "no PAYLOAD_REFUSED-style transport veto for a normal non-dip skip",
    ):
        assert token in joined, (
            f"STAGE30_11_GATE_PLACEMENT must name {token!r}"
        )


def test_only_pass_send_rule_manifest_covers_required_terms() -> None:
    joined = " | ".join(STAGE30_11_ONLY_PASS_SEND_RULE)
    for token in (
        "the real dispatch sink is invoked ONLY for a PASS candidate",
        "the real dispatch sink is invoked ONLY within the dispatch cap",
        "the real dispatch sink is invoked ONLY within the private-send cap",
        "a non-dip / invalid candidate can never reach the real sink",
        "the real send is impossible without a PASS decision",
    ):
        assert token in joined, (
            f"STAGE30_11_ONLY_PASS_SEND_RULE must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 7. Existing reuse surfaces
# ---------------------------------------------------------------------------


def test_spec_locks_existing_reuse_surfaces() -> None:
    text = _spec_text()
    for surface in (
        "run_dip_filtered_live_gate_integration",
        "evaluate_dip_filtered_live_gate",
        "Stage30_9_3LiveGateInput",
        "decide_tier",
        "TierDecisionRecord",
        "tier_token",
    ):
        assert surface in text, (
            "Stage 30.11.0 spec lock must lock reuse of the existing surface "
            f"{surface!r}"
        )
    lowered = _normalized(text).lower()
    for phrase in (
        "existing ath context",
        "existing migration context",
    ):
        assert phrase in lowered, (
            "Stage 30.11.0 spec lock must lock reuse of the existing context "
            f"{phrase!r}"
        )


def test_existing_reuse_surfaces_manifest_covers_required_names() -> None:
    joined = " | ".join(STAGE30_11_EXISTING_REUSE_SURFACES)
    for surface in (
        "run_dip_filtered_live_gate_integration",
        "evaluate_dip_filtered_live_gate",
        "Stage30_9_3LiveGateInput",
        "decide_tier",
        "TierDecisionRecord",
        "tier_token",
        "existing ATH context",
        "existing migration context",
        "existing MC / LP / current market context",
        "existing Stage 28 / 29 / 30 live session + gates",
    ):
        assert surface in joined, (
            f"STAGE30_11_EXISTING_REUSE_SURFACES must name {surface!r}"
        )


# ---------------------------------------------------------------------------
# 8. Runtime bound (max_runtime_seconds) + permitted scope
# ---------------------------------------------------------------------------


def test_spec_locks_runtime_bound() -> None:
    text = _spec_text()
    lowered = _normalized(text).lower()
    assert "max_runtime_seconds" in text, (
        "Stage 30.11.0 spec lock must name the max_runtime_seconds bound"
    )
    assert "wall-clock" in lowered, (
        "Stage 30.11.0 spec lock must state the bound is a wall-clock cap"
    )
    assert "no broad always-on daemon" in lowered, (
        "Stage 30.11.0 spec lock must forbid a broad always-on daemon"
    )


def test_runtime_bound_manifest_covers_required_terms() -> None:
    joined = " | ".join(STAGE30_11_RUNTIME_BOUND)
    for token in (
        "max_runtime_seconds is an explicit wall-clock cap",
        "the wiring stops cleanly when max_runtime_seconds elapses",
        "no broad always-on daemon",
        "no background service",
        "no autorestart loop",
    ):
        assert token in joined, (
            f"STAGE30_11_RUNTIME_BOUND must name {token!r}"
        )


def test_spec_locks_permitted_scope_expansion() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "compose the committed live surfaces behind the dip gate" in lowered, (
        "Stage 30.11.0 spec lock must permit composing the committed live "
        "surfaces behind the dip gate"
    )
    assert "the manifest is constants-only" in lowered, (
        "Stage 30.11.0 spec lock must state the spec-lock manifest is "
        "constants-only"
    )


def test_permitted_scope_note_manifest_covers_required_terms() -> None:
    joined = " | ".join(STAGE30_11_PERMITTED_SCOPE_NOTE).lower()
    for token in (
        "compose the committed live surfaces behind the dip gate",
        "import nothing",
        "never forks or reimplements",
        "no new provider, no new runner, no new readiness gate",
    ):
        assert token in joined, (
            f"STAGE30_11_PERMITTED_SCOPE_NOTE must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 9. Dip-gate decisions + result counter axes
# ---------------------------------------------------------------------------


def test_gate_decisions_are_the_committed_closed_set() -> None:
    assert STAGE30_11_GATE_DECISIONS == (
        "PASS_TO_DISPATCH",
        "SKIP_BEFORE_DISPATCH",
        "INVALID_INPUT",
    )
    assert STAGE30_11_GATE_PASS_DECISION == "PASS_TO_DISPATCH"


def test_spec_locks_gate_decisions() -> None:
    text = _spec_text()
    for decision in STAGE30_11_GATE_DECISIONS:
        assert decision in text, (
            "Stage 30.11.0 spec lock must lock the dip-gate decision "
            f"{decision!r}"
        )


def test_result_counter_axes_pinned() -> None:
    assert STAGE30_11_RESULT_COUNTER_AXES == (
        "candidates_seen",
        "candidates_evaluated",
        "candidates_passed_gate",
        "candidates_skipped_before_dispatch",
        "invalid_inputs",
        "dispatch_attempts_reserved",
        "dispatch_failures_recorded",
        "transport_veto_count",
        "payload_refused_count",
        "private_discord_sends",
        "created_at_utc",
    )
    assert STAGE30_11_ALWAYS_ZERO_AXES == (
        "dispatch_failures_recorded",
        "transport_veto_count",
        "payload_refused_count",
    )


def test_spec_locks_result_counter_axes_and_injected_clock() -> None:
    text = _spec_text()
    for field in STAGE30_11_RESULT_COUNTER_AXES:
        assert field in text, (
            "Stage 30.11.0 spec lock must lock the result counter axis "
            f"{field!r}"
        )
    lowered = _normalized(text).lower()
    assert "always 0 for a dip-gated skip" in lowered, (
        "Stage 30.11.0 spec lock must state the failure / veto / refused axes "
        "are always 0 for a dip-gated skip"
    )
    assert "caller-injected" in lowered, (
        "Stage 30.11.0 spec lock must state created_at_utc is caller-injected"
    )


# ---------------------------------------------------------------------------
# 10. Stage 30.9.2 paused, not abandoned; 30.9.3 committed the seam
# ---------------------------------------------------------------------------


def test_spec_says_stage_30_9_2_paused_not_abandoned() -> None:
    lowered = _normalized(_spec_text()).lower()
    assert "stage 30.9.2 is paused, not abandoned" in lowered, (
        "Stage 30.11.0 spec lock must state Stage 30.9.2 is paused, not "
        "abandoned"
    )
    assert "stage 30.9.3 committed the pure" in lowered, (
        "Stage 30.11.0 spec lock must state Stage 30.9.3 committed the pure / "
        "offline dip-gate seam"
    )


def test_stage_30_9_2_status_manifest_pinned() -> None:
    assert STAGE30_11_STAGE_30_9_2_STATUS == "paused, not abandoned"


# ---------------------------------------------------------------------------
# 11. Forbid public / social / trading / wallet / enforcement / ungated reuse
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
            "Stage 30.11.0 spec lock must forbid the surface "
            f"{token!r}"
        )
    lowered = _normalized(text).lower()
    assert "ungated stage 29.3 send path" in lowered, (
        "Stage 30.11.0 spec lock must forbid the direct reuse of the ungated "
        "Stage 29.3 send path"
    )


def test_forbidden_surfaces_cover_all_listed_scopes() -> None:
    assert isinstance(STAGE30_11_FORBIDDEN_SURFACES, tuple)
    assert len(STAGE30_11_FORBIDDEN_SURFACES) >= 20
    joined = " | ".join(STAGE30_11_FORBIDDEN_SURFACES)
    for token in (
        "new live runner",
        "new provider",
        "new readiness gate",
        "direct Stage 28 suppression-logic edit",
        "transport-layer veto for non-dip skip",
        "PAYLOAD_REFUSED for normal non-dip skip",
        "non-dip counted as dispatch failure",
        "ungated Stage 29.3 send path reused directly",
        "public routing",
        "subscriber routing",
        "paid tiers",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet / signing",
        "enforcement activation",
        "database implementation",
        "SQLite implementation",
        "zstd implementation",
        "zstd dependency",
        "compression implementation",
        "default storage root",
        "broad always-on daemon",
        "background service",
        "commit",
        "tag",
        "push",
        "Stage 30.11.1+ implementation file",
        "Stage 31",
    ):
        assert token in joined, (
            f"Stage 30.11 forbidden surfaces must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 12. Failure behavior + substage roadmap
# ---------------------------------------------------------------------------


def test_failure_behavior_is_fail_closed() -> None:
    joined = " | ".join(STAGE30_11_FAILURE_BEHAVIOR).lower()
    for token in (
        "readiness failure => no provider call, no discord send",
        "non-pass candidate => suppressed before reservation, no send",
        "max_runtime_seconds elapsed => clean bounded stop",
        "fail closed on any unknown / missing input, never fail open",
    ):
        assert token in joined, (
            f"STAGE30_11_FAILURE_BEHAVIOR must state {token!r}"
        )


def test_planned_substages_are_exactly_five() -> None:
    assert STAGE30_11_PLANNED_SUBSTAGES == (
        "30.11.0",
        "30.11.1",
        "30.11.2",
        "30.11.3",
        "30.11.4",
    )


def test_spec_locks_future_substages() -> None:
    text = _spec_text()
    for substage in (
        "Stage 30.11.0",
        "Stage 30.11.1",
        "Stage 30.11.2",
        "Stage 30.11.3",
        "Stage 30.11.4",
    ):
        assert substage in text, (
            "Stage 30.11.0 spec lock must define the future stage; missing "
            f"{substage!r}"
        )


def test_substage_roadmap_manifest_covers_five_slices() -> None:
    joined = " | ".join(STAGE30_11_SUBSTAGE_ROADMAP)
    for token in ("30.11.0", "30.11.1", "30.11.2", "30.11.3", "30.11.4"):
        assert token in joined, (
            f"STAGE30_11_SUBSTAGE_ROADMAP must name {token!r}"
        )


# ---------------------------------------------------------------------------
# 13. Manifest is constants-only
# ---------------------------------------------------------------------------


def test_manifest_is_constants_only() -> None:
    """AST proof: the manifest contains no function / class definition and no
    Call node anywhere (constants-only; the split-literal needle
    concatenations use ``+`` BinOps, never Calls), and imports only
    ``__future__`` + ``typing`` (no PHX2 import).
    """
    tree = ast.parse(_manifest_text())

    for node in ast.walk(tree):
        assert not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ), "Stage 30.11.0 manifest must be constants-only (no def / class)"
        assert not isinstance(node, ast.Call), (
            "Stage 30.11.0 manifest must be constants-only (no Call -- no "
            "implicit I/O at import time)"
        )

    allowed_import_roots = set(STAGE30_11_ALLOWED_STDLIB_IMPORTS)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") in allowed_import_roots, (
                "Stage 30.11.0 manifest may only import __future__ / typing; "
                f"saw {node.module!r}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_import_roots, (
                    "Stage 30.11.0 manifest may only import __future__ / "
                    f"typing; saw {alias.name!r}"
                )


def test_manifest_imports_no_phx2_module() -> None:
    for line in _manifest_text().split("\n"):
        if not _is_real_import_line(line):
            continue
        module = _extract_imported_module(line)
        assert not module.startswith("PHX2"), (
            "Stage 30.11.0 manifest must import no PHX2 module; saw "
            f"{module!r}"
        )


def test_allowed_initial_files_are_exactly_spec_and_manifest() -> None:
    assert STAGE30_11_ALLOWED_INITIAL_FILES == (
        STAGE30_11_SPEC_LOCK_FILENAME,
        STAGE30_11_MANIFEST_BASENAME,
    )
    py_additions = [
        name
        for name in STAGE30_11_ALLOWED_INITIAL_FILES
        if name.endswith(".py")
    ]
    assert py_additions == [STAGE30_11_MANIFEST_BASENAME]
    assert STAGE30_11_SCANNED_PRODUCTION_BASENAMES == (
        STAGE30_11_MANIFEST_BASENAME,
    )


# ---------------------------------------------------------------------------
# 14. No forbidden runtime / Stage 21-29 / PHX1 imports; no env read
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


def test_no_forbidden_runtime_imports_in_30_11_0_files() -> None:
    for filename, text in _python_30_11_0_files().items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for prefix in _FORBIDDEN_MODULE_PREFIXES:
                assert not (
                    module == prefix or module.startswith(prefix + ".")
                ), (
                    f"Stage 30.11.0 file {filename!r} imports forbidden "
                    f"module {module!r} on line {line.rstrip()!r}"
                )


def test_no_os_environ_or_getenv_in_30_11_0_files() -> None:
    for filename, text in _python_30_11_0_files().items():
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in (
                    "environ",
                    "getenv",
                    "environb",
                ), (
                    f"Stage 30.11.0 file {filename!r} must not read env via "
                    f"os.{node.attr}"
                )


def test_no_stage21_29_or_phx1_imports_in_30_11_0_files() -> None:
    """Neither the manifest NOR this pin test imports a Stage 21-29 / Stage
    29.5 / PHX1 production module. (The pin test legitimately imports the
    Stage 30.0 sibling TEST module to read the inventory allowlist -- a
    ``PHX2.tests`` import -- and the Stage 30.11 manifest -- a
    ``PHX2.stage30`` import -- both outside the forbidden Stage 21-29
    production range.)
    """
    for filename, text in _python_30_11_0_files().items():
        for line in text.split("\n"):
            if not _is_real_import_line(line):
                continue
            module = _extract_imported_module(line)
            for stage_n in range(21, 30):
                assert not module.startswith(f"PHX2.stage{stage_n}"), (
                    f"Stage 30.11.0 file {filename!r} imports forbidden Stage "
                    f"21-29 module {module!r}"
                )
            assert not module.startswith("PHX1"), (
                f"Stage 30.11.0 file {filename!r} imports forbidden PHX1 "
                f"module {module!r}"
            )


def test_forbidden_runtime_imports_tuple_is_non_empty() -> None:
    assert len(STAGE30_11_FORBIDDEN_RUNTIME_IMPORTS) >= 20, (
        "STAGE30_11_FORBIDDEN_RUNTIME_IMPORTS must enumerate the forbidden "
        "runtime import surfaces"
    )


# ---------------------------------------------------------------------------
# 15. No forbidden secret / transport text needle in any Stage 30.11.0 file
# ---------------------------------------------------------------------------


def test_no_forbidden_text_needles_in_30_11_0_files() -> None:
    """Case-insensitive substring scan over the spec lock, the manifest, and
    this test file. The manifest's ``STAGE30_11_FORBIDDEN_TEXT_NEEDLES`` tuple
    uses split-literal forms so the manifest source itself does not carry the
    bare needles; this test imports the values at runtime and scans every
    Stage 30.11.0 file.
    """
    for filename, text in _all_30_11_0_files().items():
        lower = text.lower()
        for needle in STAGE30_11_FORBIDDEN_TEXT_NEEDLES:
            needle_lower = needle.lower()
            assert needle_lower not in lower, (
                f"Stage 30.11.0 file {filename!r} carries forbidden text "
                f"needle {needle!r}"
            )


def test_forbidden_text_needles_tuple_is_non_empty() -> None:
    assert len(STAGE30_11_FORBIDDEN_TEXT_NEEDLES) >= 12, (
        "STAGE30_11_FORBIDDEN_TEXT_NEEDLES must enumerate the forbidden text "
        "needles"
    )


# ---------------------------------------------------------------------------
# 16. No Stage 30.11.1+ file exists yet; no Stage 31 file
# ---------------------------------------------------------------------------


def test_stage30_11_production_entries_are_the_admitted_inventory() -> None:
    """Every Stage 30.11 entry under ``PHX2/stage30/`` must be exactly the
    Stage 30.11.0 spec doc + constants-only manifest PLUS the now-admitted
    Stage 30.11.1 offline live-candidate assembly bridge production files
    (bridge models + bridge + fake bridge proof) PLUS the now-admitted Stage
    30.11.2 runtime gate seam production files (runtime gate models + seam +
    fake runtime gate proof) PLUS the now-admitted Stage 30.11.3 private sink
    adapter production files (private sink models + adapter + fake private sink
    proof) PLUS the now-admitted Stage 30.11.4 offline end-to-end proof
    production files (end-to-end proof models + end-to-end proof). NO Stage
    30.11.5+ runtime / sink / proof module may exist yet.
    """
    observed = {
        entry.name
        for entry in STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and (
            entry.name.startswith("stage30_11")
            or entry.name.startswith("STAGE_30_11")
        )
    }
    allowed = (
        {
            STAGE30_11_SPEC_LOCK_FILENAME,
            STAGE30_11_MANIFEST_BASENAME,
        }
        | set(STAGE30_11_1_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_2_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_3_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_4_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_5_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_6_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_7_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_8_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_9_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_10_ALLOWED_STAGE30_BASENAMES)
        | set(STAGE30_11_11_ALLOWED_STAGE30_BASENAMES)
    )
    assert observed == allowed, (
        "Stage 30.11 production entries must be exactly the Stage 30.11.0 "
        "spec lock + manifest plus the Stage 30.11.1 assembly bridge files "
        "plus the Stage 30.11.2 runtime gate seam files plus the Stage 30.11.3 "
        "private sink adapter files plus the Stage 30.11.4 offline end-to-end "
        "proof files; "
        f"unexpected entries: {sorted(observed - allowed)}"
    )


def test_stage30_11_test_entries_are_the_admitted_inventory() -> None:
    """Every Stage 30.11 test under ``PHX2/tests/stage30/`` must be exactly
    the Stage 30.11.0 spec-lock pin test PLUS the now-admitted Stage 30.11.1
    assembly bridge test files PLUS the now-admitted Stage 30.11.2 runtime gate
    seam test files PLUS the now-admitted Stage 30.11.3 private sink adapter
    test files PLUS the now-admitted Stage 30.11.4 offline end-to-end proof test
    files. NO Stage 30.11.5+ test may exist yet.
    """
    observed = {
        entry.name
        for entry in TESTS_STAGE30_ROOT.iterdir()
        if entry.name != "__pycache__"
        and entry.name.startswith("test_stage_30_11")
    }
    allowed = (
        {STAGE30_11_0_TEST_BASENAMES[0]}
        | set(STAGE30_11_1_TEST_BASENAMES)
        | set(STAGE30_11_2_TEST_BASENAMES)
        | set(STAGE30_11_3_TEST_BASENAMES)
        | set(STAGE30_11_4_TEST_BASENAMES)
        | set(STAGE30_11_5_TEST_BASENAMES)
        | set(STAGE30_11_6_TEST_BASENAMES)
        | set(STAGE30_11_7_TEST_BASENAMES)
        | set(STAGE30_11_8_TEST_BASENAMES)
        | set(STAGE30_11_9_TEST_BASENAMES)
        | set(STAGE30_11_10_TEST_BASENAMES)
        | set(STAGE30_11_11_TEST_BASENAMES)
    )
    assert observed == allowed, (
        "Stage 30.11 test entries must be exactly the 30.11.0 pin test plus "
        "the Stage 30.11.1 assembly bridge tests plus the Stage 30.11.2 "
        "runtime gate seam tests plus the Stage 30.11.3 private sink adapter "
        "tests plus the Stage 30.11.4 offline end-to-end proof tests; "
        f"unexpected entries: {sorted(observed - allowed)}"
    )


# ---------------------------------------------------------------------------
# 17. Stage 30.0 allowlist admits exactly the 30.11.0 files; no 30.11.1+ /
#     Stage 31 file admitted.
# ---------------------------------------------------------------------------


def test_stage30_0_allowlist_admits_the_30_11_0_files() -> None:
    assert STAGE30_11_SPEC_LOCK_FILENAME in _STAGE30_ALLOWED_BASENAMES
    assert STAGE30_11_MANIFEST_BASENAME in _STAGE30_ALLOWED_BASENAMES
    assert (
        STAGE30_11_0_TEST_BASENAMES[0] in _TESTS_STAGE30_ALLOWED_BASENAMES
    )
    assert SPEC_LOCK_PATH.is_file()
    assert MANIFEST_PATH.is_file()
    assert TEST_PATH.is_file()


def test_stage30_0_allowlist_admits_no_stage_30_11_5_plus_file() -> None:
    """No Stage 30.11.11+ production / test basename is admitted by the Stage
    30.0 allowlist yet. The Stage 30.11.0 scaffold carries minor token 0 (the
    spec doc + pin test) or no minor token (the manifest); the now-admitted Stage
    30.11.1..30.11.10 slices carry minor tokens 1..10 (the assembly bridge,
    runtime gate seam, private sink adapter, offline end-to-end proof, controlled
    live ceremony wiring, real candidate source / harvest seam, candidate
    dip-enrichment bridge, narrow migration-confirmation bridge, mint-keyed
    migration evidence-source, and real ATH-resolver bridge slices); the guard
    catches ANY Stage 30.11.<N>=11+ token (30_11_11, 30_11_12, ...).
    """
    production = _future_30_11_violations(_STAGE30_ALLOWED_BASENAMES)
    assert production == [], (
        "Stage 30.0 production allowlist must not admit a Stage 30.11.11+ file "
        f"yet; saw {production!r}"
    )
    tests = _future_30_11_violations(_TESTS_STAGE30_ALLOWED_BASENAMES)
    assert tests == [], (
        "Stage 30.0 test allowlist must not admit a Stage 30.11.11+ test file "
        f"yet; saw {tests!r}"
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
    """The planned-substage tuple stops at 30.11.4; it admits no 30.12 and no
    31 token.
    """
    assert STAGE30_11_PLANNED_SUBSTAGES[-1] == "30.11.4"
    joined = " ".join(STAGE30_11_PLANNED_SUBSTAGES)
    assert "30.12" not in joined
    assert "31" not in joined
