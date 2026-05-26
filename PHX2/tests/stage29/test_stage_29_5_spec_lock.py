"""Stage 29.5 spec-lock tests.

Pins:

  * ``PHX2/stage29/STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md``
    exists and carries the canonical Stage 29.5 mission
    sentence verbatim, the Stage 29.5 purpose, the Stage
    29.5.0 spec-lock-only scope, the Stage 29.5.1 planned
    scope, the PHX1 read-only design reference constraint
    (no PHX1 imports, no direct PHX1 spaghetti copy), the
    closed-set migration / source / join-status /
    measurement-status / warning-code vocabularies, the
    reused production modules, the Stage 29.5.0 file
    inventory, the Stage 29.5.1 planned production
    inventory, the Stage 29.5.1 testing discipline (fake /
    offline tests first, no invention discipline), the
    offline Stage 29.5.0 acceptance criteria, the
    forbidden surfaces, the carried-over Stage 29.3 /
    Stage 29.4 artifact-projection caveats, the closed-set
    vocabularies summary, and the Stage 29.5.0 spec-only
    scope locks.
  * Stage 29.5.0 ships ZERO runtime production code: no
    ``stage29_5_*.py`` file exists under ``PHX2/stage29/``
    at Stage 29.5.0.
  * The Stage 29.5.0 commit ships exactly two new tracked
    files (this runbook + this test file) plus narrow
    test-files-only allowlist widenings in the Stage 28.8 /
    28.9 / 28.10 / 28.11 boundary tests and in the Stage
    29.0 spec-lock test.
  * The Stage 29.5 runbook carries no URL literal, no
    webhook host literal, and no raw secret-looking value.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"
RUNBOOK_PATH: Path = (
    STAGE29_ROOT
    / "STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md"
)


# Canonical Stage 29.5 mission sentence. Must appear verbatim
# in the runbook; future Stage 29.5 patches must preserve it.
STAGE_29_5_MISSION_SENTENCE: str = (
    "Stage 29.5 is the Helius WebSocket migration evidence "
    "adapter and live private ping context join substage that "
    "lands a deferred Helius WS migration evidence boundary, a "
    "candidate-to-migration join layer, and a private ping "
    "migration context projection so that the existing Stage "
    "28.9 private operator ping render path can surface "
    "post-migration ATH verification context without modifying "
    "any Stage 27 / Stage 28 / Stage 29.1 / Stage 29.2 / Stage "
    "29.3 / Stage 29.4 production source at Stage 29.5.0."
)


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Stage 29.5 spec-lock file exists; spec-lock test file exists
# ---------------------------------------------------------------------------


def test_stage_29_5_runbook_exists():
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 29.5.0 requires the spec-lock runbook "
        f"document {RUNBOOK_PATH}"
    )


def test_stage_29_5_spec_lock_test_file_exists():
    self_path = (
        TESTS_STAGE29_ROOT / "test_stage_29_5_spec_lock.py"
    )
    assert self_path.is_file(), (
        f"Stage 29.5.0 requires the spec-lock test file "
        f"{self_path}"
    )


# ---------------------------------------------------------------------------
# 2. Canonical Stage 29.5 mission sentence appears verbatim
# ---------------------------------------------------------------------------


def test_runbook_contains_canonical_mission_sentence_verbatim():
    normalized = _normalized_whitespace(_runbook_text())
    assert STAGE_29_5_MISSION_SENTENCE in normalized, (
        "Stage 29.5 runbook must contain the canonical mission "
        "sentence verbatim (whitespace-normalized match)"
    )


def test_runbook_names_stage_29_5_explicitly():
    text = _runbook_text()
    assert "Stage 29.5" in text


def test_runbook_names_stage_29_5_0_explicitly():
    text = _runbook_text()
    assert "Stage 29.5.0" in text


def test_runbook_names_stage_29_5_1_explicitly():
    text = _runbook_text()
    assert "Stage 29.5.1" in text


# ---------------------------------------------------------------------------
# 3. Stage 29.5 purpose pinned
# ---------------------------------------------------------------------------


_STAGE_29_5_PURPOSE_PHRASES: tuple[str, ...] = (
    "Helius WebSocket migration evidence adapter",
    "candidate-to-migration join",
    "private ping migration context projection",
    "post-migration ATH verification context",
    "observational only",
    "Stage 29.5 does NOT change how Stage 28.9 dispatches",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_5_PURPOSE_PHRASES
)
def test_runbook_pins_each_purpose_phrase(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.5 runbook missing purpose phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 4. Stage 29.5.0 vs Stage 29.5.1 split is pinned
# ---------------------------------------------------------------------------


def test_runbook_says_stage_29_5_0_is_spec_lock_only():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.5.0 is a spec-lock-only pass"
    ) in normalized


def test_runbook_says_stage_29_5_0_ships_zero_runtime_production_code():
    text = _runbook_text()
    assert "Stage 29.5.0 ships zero runtime production code" in (
        text
    )


def test_runbook_says_stage_29_5_1_is_reserved_at_29_5_0():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.5.1 is reserved at Stage 29.5.0"
    ) in normalized


_STAGE_29_5_0_ZERO_EDIT_PHRASES: tuple[str, ...] = (
    "Stage 29.5.0 makes zero edits to Stage 27 / Stage 28 / "
    "Stage 29.1 / Stage 29.2 / Stage 29.3 / Stage 29.4 "
    "production source",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_5_0_ZERO_EDIT_PHRASES
)
def test_runbook_pins_stage_29_5_0_zero_edits(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.5 runbook missing zero-edit phrase "
        f"{phrase!r}"
    )


# ---------------------------------------------------------------------------
# 5. Stage 29.5.1 planned scope axes pinned
# ---------------------------------------------------------------------------


_STAGE_29_5_1_PLANNED_AXES: tuple[str, ...] = (
    "migration evidence models",
    "Helius WS adapter boundary AND artifact reader",
    "candidate-to-migration join logic",
    "private ping context projection",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_5_1_PLANNED_AXES
)
def test_runbook_pins_each_stage_29_5_1_planned_axis(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.5 runbook missing Stage 29.5.1 planned axis "
        f"{phrase!r}"
    )


# ---------------------------------------------------------------------------
# 6. PHX1 read-only design reference / no-import / no-spaghetti-copy
# ---------------------------------------------------------------------------


_PHX1_READ_ONLY_PHRASES: tuple[str, ...] = (
    "PHX1 (the legacy `Phoenix_Bot` codebase) may be consulted "
    "as a read-only design reference",
    "must NOT import any PHX1 module",
    "must NOT copy PHX1 source verbatim",
    "must NOT carry a PHX1 / Phoenix_Bot path substring",
    "PHX1 is a read-only design reference only",
    "PHX1 has a known spaghetti-copy risk",
    "Stage 29.5 implementation must NOT adopt PHX1's module "
    "shape",
)


@pytest.mark.parametrize("phrase", _PHX1_READ_ONLY_PHRASES)
def test_runbook_pins_each_phx1_read_only_phrase(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.5 runbook missing PHX1 read-only phrase "
        f"{phrase!r}"
    )


# ---------------------------------------------------------------------------
# 7. Closed-set migration_status tokens
# ---------------------------------------------------------------------------


_STAGE_29_5_MIGRATION_STATUS_TOKENS: tuple[str, ...] = (
    "PRESENT",
    "MISSING",
    "CONFLICTING",
    "INVALID",
    "STALE",
)


@pytest.mark.parametrize(
    "token", _STAGE_29_5_MIGRATION_STATUS_TOKENS
)
def test_runbook_names_each_migration_status_token(token):
    text = _runbook_text()
    assert token in text, (
        f"Stage 29.5 runbook missing migration_status token "
        f"{token!r}"
    )


def test_runbook_pins_migration_status_label():
    text = _runbook_text()
    assert "migration_status" in text


# ---------------------------------------------------------------------------
# 8. Closed-set migration_source tokens
# ---------------------------------------------------------------------------


_STAGE_29_5_MIGRATION_SOURCE_TOKENS: tuple[str, ...] = (
    "HELIUS_WS",
    "STAGE29_MIGRATION_ARTIFACT",
    "SYNTHETIC_TEST_ONLY",
    "UNKNOWN",
)


@pytest.mark.parametrize(
    "token", _STAGE_29_5_MIGRATION_SOURCE_TOKENS
)
def test_runbook_names_each_migration_source_token(token):
    text = _runbook_text()
    assert token in text, (
        f"Stage 29.5 runbook missing migration_source token "
        f"{token!r}"
    )


def test_runbook_pins_migration_source_label():
    text = _runbook_text()
    assert "migration_source" in text


# ---------------------------------------------------------------------------
# 9. Closed-set migration_join_status tokens
# ---------------------------------------------------------------------------


_STAGE_29_5_MIGRATION_JOIN_STATUS_TOKENS: tuple[str, ...] = (
    "JOINED",
    "NO_MATCH",
    "MULTIPLE_MATCHES",
    "SOURCE_INVALID",
    "TIME_WINDOW_INVALID",
    "PAIR_MISMATCH",
)


@pytest.mark.parametrize(
    "token", _STAGE_29_5_MIGRATION_JOIN_STATUS_TOKENS
)
def test_runbook_names_each_migration_join_status_token(token):
    text = _runbook_text()
    assert token in text, (
        f"Stage 29.5 runbook missing migration_join_status "
        f"token {token!r}"
    )


def test_runbook_pins_migration_join_status_label():
    text = _runbook_text()
    assert "migration_join_status" in text


# ---------------------------------------------------------------------------
# 10. Closed-set measurement_status tokens
# ---------------------------------------------------------------------------


_STAGE_29_5_MEASUREMENT_STATUS_TOKENS: tuple[str, ...] = (
    "MISSING_MIGRATION",
    "PARTIAL_MIGRATION_PRESENT",
    "COMPLETE",
    "INVALID_MIGRATION",
    "CONFLICTING_MIGRATION",
)


@pytest.mark.parametrize(
    "token", _STAGE_29_5_MEASUREMENT_STATUS_TOKENS
)
def test_runbook_names_each_measurement_status_token(token):
    text = _runbook_text()
    assert token in text, (
        f"Stage 29.5 runbook missing measurement_status token "
        f"{token!r}"
    )


def test_runbook_pins_measurement_status_label():
    text = _runbook_text()
    assert "measurement_status" in text


# ---------------------------------------------------------------------------
# 11. Closed-set warning codes
# ---------------------------------------------------------------------------


_STAGE_29_5_WARNING_CODES: tuple[str, ...] = (
    "MIGRATION_MISSING",
    "POST_MIGRATION_ATH_UNVERIFIED",
    "MIGRATION_SOURCE_UNKNOWN",
    "MIGRATION_CONFLICT",
    "MIGRATION_STALE",
    "MIGRATION_TIMESTAMP_INVALID",
    "MIGRATION_PAIR_MISMATCH",
    "MIGRATION_SLOT_MISSING",
)


@pytest.mark.parametrize(
    "code", _STAGE_29_5_WARNING_CODES
)
def test_runbook_names_each_warning_code(code):
    text = _runbook_text()
    assert code in text, (
        f"Stage 29.5 runbook missing warning code {code!r}"
    )


def test_runbook_says_warning_codes_are_observational_only():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "The warning codes are observational only"
    ) in normalized
    assert (
        "Stage 29.5 must not gate dispatch on any warning code"
    ) in normalized


# ---------------------------------------------------------------------------
# 12. Filter enforcement status locked
# ---------------------------------------------------------------------------


def test_runbook_pins_filter_enforcement_status_locked():
    text = _runbook_text()
    assert "NOT_ACTIVE_STAGE_29_PENDING" in text


def test_runbook_pins_filter_enforcement_status_preserved_verbatim():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.5 must preserve this token verbatim"
    ) in normalized


# ---------------------------------------------------------------------------
# 13. Reused production modules
# ---------------------------------------------------------------------------


_STAGE_29_5_REUSED_MODULES: tuple[str, ...] = (
    "Stage 27 live candidate assembler",
    "Stage 27 pair classifier",
    "Stage 27 private ping renderer",
    "Stage 27.4 `PriceContextSource` and `AthContextSource` "
    "Protocols",
    "Stage 27.6 `Stage27_6Sources` bundle and run-local "
    "dedupe",
    "Stage 28.2 restart-safe dispatch ledger",
    "Stage 28.4 audited private operator-only Discord HTTP "
    "transport",
    "Stage 28.5 heartbeat and health snapshot and final "
    "summary writers",
    "Stage 28.6 bounded private session runner",
    "Stage 28.9 default candidate assembler and private "
    "webhook transport and orchestrator",
    "Stage 28.11 Chainstack Yellowstone readiness env-read "
    "boundary",
    "Stage 29.1 PumpSwap hint-aware decoder",
    "Stage 29.2 Birdeye readiness env-read boundary and "
    "price source and ATH source and HTTP transport",
    "Stage 29.3 single-shot first private tradeable smoke "
    "orchestrator entry point",
    "Stage 29.4 short-session private soak orchestrator "
    "entry point",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_5_REUSED_MODULES
)
def test_runbook_lists_each_reused_module(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.5 runbook missing reused module phrase "
        f"{phrase!r}"
    )


def test_runbook_says_stage_29_5_does_not_reimplement():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.5 does NOT reimplement any of these surfaces"
    ) in normalized


# ---------------------------------------------------------------------------
# 14. Stage 29.5.0 file inventory
# ---------------------------------------------------------------------------


_STAGE_29_5_0_NEW_FILES: tuple[str, ...] = (
    "PHX2/stage29/STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md",
    "PHX2/tests/stage29/test_stage_29_5_spec_lock.py",
)


@pytest.mark.parametrize("path", _STAGE_29_5_0_NEW_FILES)
def test_runbook_lists_each_new_tracked_file(path):
    text = _runbook_text()
    assert path in text, (
        f"Stage 29.5 runbook missing new tracked file {path!r}"
    )


_STAGE_29_5_0_TOUCHED_TEST_FILES: tuple[str, ...] = (
    "PHX2/tests/stage28/test_stage_28_8_boundaries.py",
    "PHX2/tests/stage28/test_stage_28_9_boundaries.py",
    "PHX2/tests/stage28/test_stage_28_10_boundaries.py",
    "PHX2/tests/stage28/test_stage_28_11_boundaries.py",
    "PHX2/tests/stage29/test_stage_29_0_spec_lock.py",
)


@pytest.mark.parametrize(
    "path", _STAGE_29_5_0_TOUCHED_TEST_FILES
)
def test_runbook_lists_each_touched_boundary_test_file(path):
    text = _runbook_text()
    assert path in text, (
        f"Stage 29.5 runbook missing touched test file path "
        f"{path!r}"
    )


# ---------------------------------------------------------------------------
# 15. Stage 29.5.1 planned production basenames (NOT shipped at Stage 29.5.0)
# ---------------------------------------------------------------------------


_STAGE_29_5_1_PLANNED_PROD_BASENAMES: tuple[str, ...] = (
    "stage29_5_migration_models.py",
    "stage29_5_helius_ws_adapter.py",
    "stage29_5_migration_artifact_reader.py",
    "stage29_5_candidate_to_migration_join.py",
    "stage29_5_private_ping_context_projection.py",
    "stage29_5_manifest.py",
)


@pytest.mark.parametrize(
    "basename", _STAGE_29_5_1_PLANNED_PROD_BASENAMES
)
def test_runbook_lists_each_planned_29_5_1_production_basename(
    basename,
):
    text = _runbook_text()
    assert basename in text, (
        f"Stage 29.5 runbook missing planned Stage 29.5.1 "
        f"production basename {basename!r}"
    )


@pytest.mark.parametrize(
    "basename", _STAGE_29_5_1_PLANNED_PROD_BASENAMES
)
def test_stage_29_5_1_production_basename_present_at_29_5_1(
    basename,
):
    # Stage 29.5.1 (authorized 2026-05-25) materializes the
    # planned Stage 29.5 production basenames. Every planned
    # basename must now be PRESENT under PHX2/stage29/.
    assert (STAGE29_ROOT / basename).is_file(), (
        f"Stage 29.5.1 requires production basename "
        f"{basename!r} under PHX2/stage29/"
    )


def test_only_planned_stage29_5_py_modules_exist_at_29_5_1():
    # Stage 29.5.1 ships exactly the planned Stage 29.5
    # production .py basenames under PHX2/stage29/. No
    # additional ``stage29_5_*.py`` module is admitted; later
    # Stage 29.5 substages must widen this pin explicitly under
    # a separately authorized commit.
    #
    # Stage 29.5.2 narrow amendment (authorized 2026-05-26): the
    # Stage 29.5.2 offline integration proof introduces sibling
    # ``stage29_5_2_*.py`` files under PHX2/stage29/. Those files
    # are part of the Stage 29.5.2 inventory, not the Stage 29.5
    # inventory; the Stage 29.5 inventory stays pinned at the
    # six-file tuple. This loop excludes ``stage29_5_2_*.py``
    # files so the Stage 29.5 pin remains tight.
    #
    # Stage 29.5.3 narrow amendment (authorized 2026-05-26): the
    # Stage 29.5.3 soak pass-entrypoint wrapper introduces
    # sibling ``stage29_5_3_*.py`` files under PHX2/stage29/.
    # Those files belong to the Stage 29.5.3 inventory, not the
    # Stage 29.5 inventory; the Stage 29.5 pin stays at six
    # files. This loop also excludes ``stage29_5_3_*.py`` files.
    actual: set[str] = set()
    for entry in STAGE29_ROOT.iterdir():
        if entry.is_dir():
            continue
        name = entry.name
        if (
            name.startswith("stage29_5")
            and name.endswith(".py")
            and not name.startswith("stage29_5_2_")
            and not name.startswith("stage29_5_3_")
        ):
            actual.add(name)
    expected = set(_STAGE_29_5_1_PLANNED_PROD_BASENAMES)
    assert actual == expected, (
        f"Stage 29.5.1 admits exactly "
        f"{sorted(expected)!r} under PHX2/stage29/; actual: "
        f"{sorted(actual)!r}"
    )


# ---------------------------------------------------------------------------
# 16. Stage 29.5.1 testing discipline
# ---------------------------------------------------------------------------


_STAGE_29_5_1_TESTING_DISCIPLINE_PHRASES: tuple[str, ...] = (
    "Fake / offline tests first",
    "Closed-set discipline",
    "No invention discipline",
    "Stage 29.5.1 must not introduce a live-network test in "
    "its initial commit",
    "Stage 29.5.1 must never fabricate a migration timestamp",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_5_1_TESTING_DISCIPLINE_PHRASES
)
def test_runbook_pins_each_testing_discipline_phrase(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.5 runbook missing testing discipline "
        f"phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 17. Offline Stage 29.5.0 acceptance criteria
# ---------------------------------------------------------------------------


_STAGE_29_5_0_OFFLINE_ACCEPTANCE_PHRASES: tuple[str, ...] = (
    "The Stage 29.5 spec-lock test passes against this "
    "runbook",
    "The full Stage 29 test suite passes",
    "The four touched Stage 28 boundary tests pass",
    "The Stage 29.0 spec-lock test passes with its widened "
    "allowlist unions",
    "No Stage 27 / Stage 28 / Stage 29.1 / Stage 29.2 / "
    "Stage 29.3 / Stage 29.4 production .py file is "
    "modified at Stage 29.5.0",
    "No live Chainstack gRPC call is performed during the "
    "Stage 29.5.0 work",
    "No live Birdeye HTTP call is performed during the "
    "Stage 29.5.0 work",
    "No live Helius WebSocket call is performed during the "
    "Stage 29.5.0 work",
    "No private operator Discord send is performed during "
    "the Stage 29.5.0 work",
    "No tag is created and no push is performed by the "
    "automated agent",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_5_0_OFFLINE_ACCEPTANCE_PHRASES
)
def test_runbook_lists_each_offline_acceptance_phrase(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.5 runbook missing offline acceptance "
        f"phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 18. Forbidden surfaces under Stage 29.5
# ---------------------------------------------------------------------------


_STAGE_29_5_FORBIDDEN_SURFACE_PHRASES: tuple[str, ...] = (
    "production enforcement",
    "public routing",
    "subscriber routing",
    "paid-tier routing",
    "Telegram sender / Telegram client",
    "X / social sidecar",
    "automated trading / position sizing / trade execution",
    "wallet / private-key / signer logic",
    "private keys",
    "daemon / systemd / watchdog / autorestart service",
    "infinite loop / unbounded session",
    "Discord dispatch behavior change",
    "public dashboard / HTTP control server",
    "new env name",
    "new third-party runtime dependency",
    "PHX1 / Phoenix_Bot import path",
    "direct PHX1 spaghetti copy",
    "Pump.fun bonding-curve decoder",
    "Dexscreener as a dispatch authority",
    "Helius as a price source",
    "third or fourth provider beyond Stage 28.11 (Chainstack) "
    "+ Stage 29.2 (Birdeye) + Stage 29.5 (Helius migration "
    "evidence only)",
    "persistent dedupe index",
    "Stage 29.6+ implementation",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_5_FORBIDDEN_SURFACE_PHRASES
)
def test_runbook_lists_each_forbidden_surface(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.5 runbook missing forbidden surface "
        f"{phrase!r}"
    )


def test_runbook_says_no_tag_no_push():
    text = _runbook_text()
    assert (
        "Stage 29.5.0 must not create a `stage-29-5-0-closed` "
        "tag"
    ) in text
    assert (
        "Stage 29.5.0 must not push to any remote"
    ) in text


def test_runbook_says_no_discord_dispatch_change():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.5 must not modify how Stage 28.4 dispatches"
    ) in normalized


def test_runbook_pins_no_helius_as_price_source():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Helius MUST NOT become a price / ATH provider"
    ) in normalized


# ---------------------------------------------------------------------------
# 19. Stage 29.3 / Stage 29.4 artifact-projection caveat carried forward
# ---------------------------------------------------------------------------


_STAGE_29_3_4_CAVEAT_PHRASES: tuple[str, ...] = (
    "Stage 29.3 mode-3 ceremonies and Stage 29.4 mode-3 "
    "ceremonies emit per-event artifact files",
    "safe-shape default projection (`NO_EXTRACTION` / "
    "`MISSING`)",
    "Stage 29.5 acceptance does NOT depend on those "
    "projections being cleaned up",
    "the Stage 28.9 health-snapshot counters",
    "the Stage 28.2 dispatch ledger terminal record",
    "is reserved for a separate operator-gated substage",
    "explicitly NOT part of Stage 29.5",
)


@pytest.mark.parametrize("phrase", _STAGE_29_3_4_CAVEAT_PHRASES)
def test_runbook_pins_each_artifact_projection_caveat_phrase(
    phrase,
):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.5 runbook missing artifact-projection "
        f"caveat phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 20. Closed-set vocabularies summary section
# ---------------------------------------------------------------------------


def test_runbook_contains_closed_set_vocabularies_summary():
    text = _runbook_text()
    assert "Stage 29.5 closed-set vocabularies" in text


def test_runbook_pins_redaction_status_safe_and_redacted():
    text = _runbook_text()
    assert "`SAFE`" in text
    assert "`REDACTED`" in text


# ---------------------------------------------------------------------------
# 21. Stage 29.5.0 spec-only scope locks
# ---------------------------------------------------------------------------


_STAGE_29_5_0_MUST_NOT_SURFACES: tuple[str, ...] = (
    "migration evidence models in runtime form",
    "Helius WebSocket adapter boundary in runtime form",
    "migration artifact reader in runtime form",
    "candidate-to-migration join logic in runtime form",
    "private ping migration context projection in runtime "
    "form",
    "Stage 29.5 manifest in runtime form",
    "diagnostic Discord smoke",
    "scratch sender of any kind",
    "fake migration timestamps or invented migration slot "
    "values",
    "second env-read site",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_5_0_MUST_NOT_SURFACES
)
def test_runbook_lists_each_stage_29_5_0_must_not_surface(
    phrase,
):
    text = _runbook_text()
    assert phrase in text, (
        f"Stage 29.5 runbook missing Stage 29.5.0 must-not "
        f"surface {phrase!r}"
    )


def test_runbook_explicitly_says_stage_29_5_0_must_not_include():
    text = _runbook_text()
    assert "Stage 29.5.0 must not include" in text


def test_runbook_pins_closed_set_vocabularies_are_names_only_at_29_5_0():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.5.0 must not ship runtime models, enums, or "
        "constants for these vocabularies"
    ) in normalized


# ---------------------------------------------------------------------------
# 22. Runbook carries no URL / webhook host / raw secret literal
# ---------------------------------------------------------------------------


# Concatenated literally so this test file does not itself trip
# a downstream string-leak scan that flags the canonical URL /
# host / secret-shape substrings.
_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
    "birdeye" + ".so",
    "chainstack" + ".com",
    "helius" + ".xyz",
    "helius" + ".rpc.com",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_URL_LITERAL_SUBSTRINGS
)
def test_runbook_has_no_url_literal(needle):
    text = _runbook_text()
    assert needle not in text, (
        f"Stage 29.5 runbook must not contain URL literal "
        f"{needle!r}"
    )


_FORBIDDEN_SECRET_LOOKING_PATTERNS: tuple[str, ...] = (
    r"Authorization:\s*\S+",
    r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}",
    r"\bsk-[A-Za-z0-9_-]{8,}\b",
    r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b",
    r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b",
)


@pytest.mark.parametrize(
    "pattern", _FORBIDDEN_SECRET_LOOKING_PATTERNS
)
def test_runbook_has_no_secret_looking_raw_value(pattern):
    assert not re.search(pattern, _runbook_text())


# Concatenated literally so this test file does not itself trip
# a raw-secret-assignment scan.
_FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES: tuple[str, ...] = (
    "webhook" + "_url" + "=",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
    "HELIUS_WS" + "_URL=",
    "HELIUS_WS" + "_ENDPOINT=",
    "BIRDEYE_API" + "_KEY=",
    "PHX2_CHAINSTACK_YELLOWSTONE_X" + "_TOKEN=",
    "raw_" + "payload",
    "provider_" + "payload",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES
)
def test_runbook_has_no_raw_secret_assignment_name(needle):
    text = _runbook_text()
    assert needle not in text, (
        f"Stage 29.5 runbook must not carry raw "
        f"secret-assignment name {needle!r}"
    )


# ---------------------------------------------------------------------------
# 23. Stage 29.5.0 file inventory enforcement under PHX2/stage29/
# ---------------------------------------------------------------------------


_STAGE_29_5_0_REQUIRED_PROD_ENTRY: str = (
    "STAGE_29_5_MIGRATION_EVIDENCE_SPEC_LOCK.md"
)


def test_stage29_5_runbook_admitted_under_phx2_stage29():
    actual = {entry.name for entry in STAGE29_ROOT.iterdir()}
    assert _STAGE_29_5_0_REQUIRED_PROD_ENTRY in actual, (
        f"Stage 29.5.0 requires "
        f"{_STAGE_29_5_0_REQUIRED_PROD_ENTRY!r} under "
        f"PHX2/stage29/"
    )


def test_stage29_5_spec_lock_test_admitted_under_tests_stage29():
    actual = {entry.name for entry in TESTS_STAGE29_ROOT.iterdir()}
    assert "test_stage_29_5_spec_lock.py" in actual, (
        "Stage 29.5.0 requires test_stage_29_5_spec_lock.py "
        "under PHX2/tests/stage29/"
    )


# ---------------------------------------------------------------------------
# 24. Runbook carries no actual PHX1 import statement
# ---------------------------------------------------------------------------


def test_runbook_has_no_phx1_import_path():
    text = _runbook_text()
    # The runbook discusses PHX1 only as a read-only design
    # reference; it must not carry an executable Python import
    # statement for any PHX1 module. The forbidden import-shape
    # substrings are concatenated literally so this test file
    # does not itself trip a self-referential scan over its own
    # forbidden tuple.
    forbidden_import_substrings = (
        "from " + "Phoenix_Bot",
        "import " + "Phoenix_Bot",
        "from " + "phoenix_bot",
        "import " + "phoenix_bot",
    )
    for needle in forbidden_import_substrings:
        assert needle not in text, (
            f"Stage 29.5 runbook must not carry PHX1 import "
            f"substring {needle!r}"
        )


# ---------------------------------------------------------------------------
# Stage 29.5.1 second remediation: spec-lock reflects shipped state
# ---------------------------------------------------------------------------


_STAGE_29_5_1_ACTUAL_STATE_PHRASES: tuple[str, ...] = (
    # Stage 29.5.1 shipped BOTH surfaces, not "either/or".
    "Stage 29.5.1 ships BOTH a Helius WebSocket "
    "normalized-message adapter boundary AND an artifact "
    "reader",
    # The adapter is Protocol-typed over an injected transport;
    # no real socket-based client is shipped.
    "Protocol-typed over an INJECTED transport",
    # No real WS client at Stage 29.5.1.
    "no real `websockets` / `websocket-client` / `socket` "
    "client is shipped at Stage 29.5.1",
    # Raw Helius JSON-RPC envelopes are refused.
    "Raw Helius JSON-RPC envelopes",
    "REFUSAL_REASON_MALFORMED_PAYLOAD",
    # Runtime integration into Stage 29.3 / 29.4 is deferred.
    "deferred to Stage 29.5.2",
    "offline evidence / projection layer only",
    # Both surfaces stay offline at Stage 29.5.1.
    "ships ZERO real outbound network surface",
)


_STAGE_29_5_1_FORBIDDEN_EITHER_OR_PHRASES: tuple[str, ...] = (
    # Pre-second-remediation language that must no longer be in
    # the runbook.
    "either option (not both at Stage 29.5.1)",
    "may ship either option",
    "OR a paired artifact reader, not both",
    "Helius WS adapter boundary or artifact reader",
)


def test_spec_lock_reflects_29_5_1_adapter_and_artifact_reader_both_present():
    """Stage 29.5.1 second remediation: the spec-lock runbook
    now reflects the actual shipped Stage 29.5.1 state — BOTH
    the Helius WS normalized-message adapter boundary AND the
    artifact reader are present; no real WebSocket client is
    shipped; raw Helius JSON-RPC envelopes are refused; runtime
    integration into the Stage 29.3 / 29.4 private ping path is
    deferred to Stage 29.5.2. The pre-second-remediation
    either/or language must no longer appear.
    """
    text = _runbook_text()
    normalized = _normalized_whitespace(text)
    for phrase in _STAGE_29_5_1_ACTUAL_STATE_PHRASES:
        assert phrase in normalized, (
            f"Stage 29.5 runbook missing actual-state phrase "
            f"{phrase!r}"
        )
    for forbidden in _STAGE_29_5_1_FORBIDDEN_EITHER_OR_PHRASES:
        assert forbidden not in normalized, (
            f"Stage 29.5 runbook must no longer carry stale "
            f"either/or phrase {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# Stage 29.5.1 PASS-WITH-PATCHES: COMPLETE predicate list pinned
# ---------------------------------------------------------------------------


_STAGE_29_5_1_COMPLETE_PREDICATE_PHRASES: tuple[str, ...] = (
    "migration_join_status == JOINED",
    "migration_slot is present",
    "ath_status == PRESENT",
    "ath_value is not None",
    "ath_context.token_mint == join_record.candidate_base_mint",
    "ath_since_migration_status == POST_MIGRATION_ONLY",
    "ath_observed_at_utc parses as strict UTC",
    "ath_observed_at_utc strictly after migration_timestamp_utc",
)


_STAGE_29_5_1_VERIFIED_BOOL_RULE_PHRASES: tuple[str, ...] = (
    # POST-WITH-PATCHES: verified=True is allowed only when
    # every predicate holds.
    "post_migration_ath_verified = True` only when every "
    "predicate holds",
    # verified=False is only allowed when same-token + PRESENT
    # ATH context exists.
    "post_migration_ath_verified = False` is allowed only when",
    # All other uncertain/missing/wrong-token cases collapse to
    # None.
    "wrong-token",
    "collapse to `post_migration_ath_verified = None`",
)


def test_spec_lock_pins_complete_predicate_list():
    """Stage 29.5.1 PASS-WITH-PATCHES: the spec-lock runbook
    Section 6.4 COMPLETE bullet must explicitly list each of
    the 8 hardened predicates the Stage 29.5.1 projection
    enforces. Pre-PASS-WITH-PATCHES the runbook only said
    'timestamp and slot pass validation' without naming the
    individual predicates; Codex flagged the language drift.
    """
    normalized = _normalized_whitespace(_runbook_text())
    for phrase in _STAGE_29_5_1_COMPLETE_PREDICATE_PHRASES:
        assert phrase in normalized, (
            f"Stage 29.5 runbook Section 6.4 COMPLETE bullet "
            f"missing predicate phrase {phrase!r}"
        )


def test_spec_lock_pins_verified_bool_rule_for_same_token_only():
    """Stage 29.5.1 PASS-WITH-PATCHES: the spec-lock runbook
    must state explicitly that:

      * post_migration_ath_verified=True only when every
        predicate holds;
      * post_migration_ath_verified=False is allowed only when
        the ATH context speaks for the same candidate token
        and carries a real PRESENT ATH record;
      * all other uncertain / missing / wrong-token cases
        collapse to None.
    """
    normalized = _normalized_whitespace(_runbook_text())
    for phrase in _STAGE_29_5_1_VERIFIED_BOOL_RULE_PHRASES:
        assert phrase in normalized, (
            f"Stage 29.5 runbook Section 6.4 missing "
            f"verified-bool rule phrase {phrase!r}"
        )
