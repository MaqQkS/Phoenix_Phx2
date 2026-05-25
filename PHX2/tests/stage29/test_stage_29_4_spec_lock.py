"""Stage 29.4 spec-lock tests.

Pins:

  * ``PHX2/stage29/STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md``
    exists and carries the canonical Stage 29.4 mission sentence
    verbatim, the three operator-supplied ceremony modes, the
    operator-supplied soak bounds, the closed-set Stage 29.4 soak
    outcomes, the cross-pass in-memory dedupe semantics, the Stage
    29.4 acceptance artifact bundle, the reused production
    modules, the Stage 29.4.0 file inventory, the Stage 29.4.1
    planned inventory, the offline Stage 29.4.0 acceptance
    criteria, the future live soak acceptance criteria, the
    forbidden surfaces, and the explicit deferral of the Stage
    29.3 artifact-projection caveat.
  * Stage 29.4.0 ships ZERO runtime production code: no
    ``stage29_4_*.py`` file exists under ``PHX2/stage29/`` at
    Stage 29.4.0.
  * The Stage 29.4.0 commit ships exactly two new tracked files
    (this runbook + this test file) plus narrow test-files-only
    allowlist widenings in the Stage 28.8 / 28.9 / 28.10 / 28.11
    boundary tests and in the Stage 29.0 spec-lock test.
  * The Stage 29.4 runbook carries no URL literal, no webhook
    host literal, and no raw secret-looking value.
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
    / "STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md"
)


# Canonical Stage 29.4 mission sentence. Must appear verbatim in
# the runbook; future Stage 29.4 patches must preserve it.
STAGE_29_4_MISSION_SENTENCE: str = (
    "Stage 29.4 is the bounded short-session private tradeable "
    "soak around the Stage 29.3 first private tradeable smoke. "
    "It composes Stage 29.3 single-shot ceremonies into a "
    "bounded outer loop over a caller-supplied wall-clock window "
    "with caller-supplied caps on dispatches, suppressions, and "
    "passes, plus a cross-pass in-memory dedupe layer that "
    "prevents the same on-chain event from producing two private "
    "operator pings."
)


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Stage 29.4 runbook file exists; spec-lock test file exists
# ---------------------------------------------------------------------------


def test_stage_29_4_runbook_exists():
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 29.4.0 requires the runbook document "
        f"{RUNBOOK_PATH}"
    )


def test_stage_29_4_spec_lock_test_file_exists():
    self_path = (
        TESTS_STAGE29_ROOT / "test_stage_29_4_spec_lock.py"
    )
    assert self_path.is_file(), (
        f"Stage 29.4.0 requires the spec-lock test file "
        f"{self_path}"
    )


# ---------------------------------------------------------------------------
# 2. Canonical Stage 29.4 mission sentence appears verbatim
# ---------------------------------------------------------------------------


def test_runbook_contains_canonical_mission_sentence_verbatim():
    normalized = _normalized_whitespace(_runbook_text())
    assert STAGE_29_4_MISSION_SENTENCE in normalized, (
        "Stage 29.4 runbook must contain the canonical mission "
        "sentence verbatim (whitespace-normalized match)"
    )


def test_runbook_names_stage_29_4_explicitly():
    text = _runbook_text()
    assert "Stage 29.4" in text


def test_runbook_names_stage_29_4_0_explicitly():
    text = _runbook_text()
    assert "Stage 29.4.0" in text


def test_runbook_names_stage_29_4_1_explicitly():
    text = _runbook_text()
    assert "Stage 29.4.1" in text


# ---------------------------------------------------------------------------
# 3. Three operator-supplied ceremony modes are pinned verbatim
# ---------------------------------------------------------------------------


_STAGE_29_4_MODE_TOKENS: tuple[str, ...] = (
    "READINESS_ONLY",
    "CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY",
    "SHORT_SESSION_PRIVATE_SOAK_DRY_RUN",
)


@pytest.mark.parametrize("token", _STAGE_29_4_MODE_TOKENS)
def test_runbook_names_each_mode_token(token):
    text = _runbook_text()
    assert token in text, (
        f"Stage 29.4 runbook missing mode token {token!r}"
    )


def test_runbook_says_modes_one_two_three_sequentially():
    normalized = _normalized_whitespace(_runbook_text())
    assert "Run modes 1 -> 2 -> 3 sequentially" in normalized


def test_runbook_says_modes_1_and_2_are_aliases_of_stage_29_3():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Modes 1 and 2 are aliases of the Stage 29.3 "
        "single-shot modes"
    ) in normalized


# ---------------------------------------------------------------------------
# 4. Operator-supplied soak bounds with recommended ranges
# ---------------------------------------------------------------------------


_STAGE_29_4_BOUND_LABELS: tuple[str, ...] = (
    "wall_clock_seconds",
    "max_dispatches",
    "max_passes",
    "max_total_retries",
    "max_consecutive_suppressions",
    "heartbeat_cadence_seconds",
)


@pytest.mark.parametrize(
    "label", _STAGE_29_4_BOUND_LABELS
)
def test_runbook_names_each_bound_label(label):
    text = _runbook_text()
    assert label in text, (
        f"Stage 29.4 runbook missing bound label {label!r}"
    )


_STAGE_29_4_BOUND_RANGE_PHRASES: tuple[str, ...] = (
    "600 to 1800",
    "3 to 5",
    "3 to 60",
    "3 to 20",
    "10 to 60",
    "exactly 0",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_4_BOUND_RANGE_PHRASES
)
def test_runbook_documents_each_bound_range(phrase):
    text = _runbook_text()
    assert phrase in text, (
        f"Stage 29.4 runbook missing bound range phrase "
        f"{phrase!r}"
    )


def test_runbook_says_stage_29_4_inherits_per_pass_internal_locks():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.4 inherits the Stage 29.3 per-pass internal "
        "locks verbatim"
    ) in normalized


def test_runbook_says_each_pass_uses_max_events_1_max_dispatches_1():
    text = _runbook_text()
    assert "max_events=1" in text
    assert "max_dispatches=1" in text
    assert "max_total_retries=0" in text


def test_runbook_refuses_unbounded_calls():
    text = _runbook_text()
    assert "rejects unbounded calls" in text


# ---------------------------------------------------------------------------
# 5. Closed-set Stage 29.4 soak outcomes (exactly 8 tokens, locked)
# ---------------------------------------------------------------------------


_STAGE_29_4_SOAK_OUTCOMES: tuple[str, ...] = (
    "COMPLETED_AT_DISPATCH_CAP",
    "COMPLETED_AT_WALL_CLOCK",
    "COMPLETED_AT_PASS_CAP",
    "BROKE_ON_SUPPRESSION_CIRCUIT",
    "BROKE_ON_REFUSED_READINESS",
    "BROKE_ON_FAILED_PASS",
    "NO_DISPATCHES_NO_EVENTS",
    "REFUSED_INVALID_BOUNDS",
)


@pytest.mark.parametrize("token", _STAGE_29_4_SOAK_OUTCOMES)
def test_runbook_names_each_soak_outcome_token(token):
    text = _runbook_text()
    assert token in text, (
        f"Stage 29.4 runbook missing soak outcome token "
        f"{token!r}"
    )


def test_runbook_says_exactly_one_of_eight_tokens():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "carries exactly one of the eight tokens"
    ) in normalized


# ---------------------------------------------------------------------------
# 6. Cross-pass in-memory dedupe semantics
# ---------------------------------------------------------------------------


_STAGE_29_4_DEDUPE_OUTCOMES: tuple[str, ...] = (
    "NEW",
    "DUPLICATE_SUPPRESSED_SOAK",
)


@pytest.mark.parametrize(
    "token", _STAGE_29_4_DEDUPE_OUTCOMES
)
def test_runbook_names_each_dedupe_outcome_token(token):
    text = _runbook_text()
    assert token in text, (
        f"Stage 29.4 runbook missing dedupe outcome token "
        f"{token!r}"
    )


_STAGE_29_4_DEDUPE_DISCIPLINE_PHRASES: tuple[str, ...] = (
    "Stage 29.4 mode 3 maintains a cross-pass dedupe index in "
    "process memory only",
    "NEVER persisted to disk",
    "NEVER survives the Stage 29.4 soak call",
    "no duplicate private operator ping is ever sent within a "
    "single soak call",
    "dedupe layer is the sole mechanism that enforces this "
    "guarantee",
    "Stage 29.4 dedupe semantics do NOT extend across separate "
    "soak calls",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_4_DEDUPE_DISCIPLINE_PHRASES
)
def test_runbook_pins_each_dedupe_discipline_phrase(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.4 runbook missing dedupe discipline phrase "
        f"{phrase!r}"
    )


# ---------------------------------------------------------------------------
# 7. Acceptance artifact bundle (exactly 4 filenames, pinned)
# ---------------------------------------------------------------------------


_STAGE_29_4_ARTIFACT_FILENAMES: tuple[str, ...] = (
    "stage29_4_soak_summary.json",
    "stage29_4_heartbeat.jsonl",
    "stage29_4_health_snapshot.json",
    "stage29_4_redaction_scan.json",
)


@pytest.mark.parametrize(
    "filename", _STAGE_29_4_ARTIFACT_FILENAMES
)
def test_runbook_names_each_artifact_filename(filename):
    text = _runbook_text()
    assert filename in text, (
        f"Stage 29.4 runbook missing artifact filename "
        f"{filename!r}"
    )


def test_runbook_says_stage_29_4_0_ships_none_of_artifact_files():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.4.0 ships none of these artifact files"
    ) in normalized


# ---------------------------------------------------------------------------
# 8. Reused production modules (Stage 29.4 makes ZERO edits)
# ---------------------------------------------------------------------------


_STAGE_29_4_REUSED_MODULES: tuple[str, ...] = (
    "Stage 27 live candidate assembler",
    "Stage 27 pair classifier",
    "Stage 27 private ping renderer",
    "Stage 27.4 `PriceContextSource` / `AthContextSource` "
    "Protocols",
    "Stage 27.6 `Stage27_6Sources` bundle",
    "Stage 28.2 restart-safe dispatch ledger",
    "Stage 28.4 audited private operator-only Discord HTTP "
    "transport",
    "Stage 28.5 heartbeat / health snapshot / final summary "
    "writers",
    "Stage 28.6 bounded private session runner",
    "Stage 28.9 default candidate assembler + private webhook "
    "transport + orchestrator",
    "Stage 28.11 Chainstack Yellowstone readiness env-read "
    "boundary",
    "Stage 29.1 PumpSwap hint-aware decoder",
    "Stage 29.2 Birdeye readiness env-read boundary + price "
    "source + ATH source + HTTP transport",
    "Stage 29.3 single-shot first private tradeable smoke "
    "orchestrator entry point",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_4_REUSED_MODULES
)
def test_runbook_lists_each_reused_module(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.4 runbook missing reused module phrase "
        f"{phrase!r}"
    )


def test_runbook_says_stage_29_4_does_not_reimplement_stage_29_3_chain():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "It does NOT reimplement the Stage 29.3 chain"
    ) in normalized


def test_runbook_pins_stage_29_4_0_zero_runtime_production_code():
    text = _runbook_text()
    assert "Stage 29.4.0 ships zero runtime production code" in (
        text
    )


def test_runbook_pins_stage_29_4_0_makes_zero_production_edits():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.4.0 makes ZERO production-code edits to any "
        "of them"
    ) in normalized
    assert (
        "Stage 29.4.1 also makes ZERO production-code edits to "
        "any of them"
    ) in normalized


# ---------------------------------------------------------------------------
# 9. Stage 29.4.0 file inventory (this commit ships only these)
# ---------------------------------------------------------------------------


_STAGE_29_4_0_NEW_FILES: tuple[str, ...] = (
    "PHX2/stage29/STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md",
    "PHX2/tests/stage29/test_stage_29_4_spec_lock.py",
)


@pytest.mark.parametrize("path", _STAGE_29_4_0_NEW_FILES)
def test_runbook_lists_each_new_tracked_file(path):
    text = _runbook_text()
    assert path in text, (
        f"Stage 29.4 runbook missing new tracked file {path!r}"
    )


_STAGE_29_4_0_TOUCHED_TEST_FILES: tuple[str, ...] = (
    "PHX2/tests/stage28/test_stage_28_8_boundaries.py",
    "PHX2/tests/stage28/test_stage_28_9_boundaries.py",
    "PHX2/tests/stage28/test_stage_28_10_boundaries.py",
    "PHX2/tests/stage28/test_stage_28_11_boundaries.py",
    "PHX2/tests/stage29/test_stage_29_0_spec_lock.py",
)


@pytest.mark.parametrize(
    "path", _STAGE_29_4_0_TOUCHED_TEST_FILES
)
def test_runbook_lists_each_touched_boundary_test_file(path):
    text = _runbook_text()
    assert path in text, (
        f"Stage 29.4 runbook missing touched test file path "
        f"{path!r}"
    )


# ---------------------------------------------------------------------------
# 10. Stage 29.4.1 planned production inventory (NOT shipped at 29.4.0)
# ---------------------------------------------------------------------------


_STAGE_29_4_1_PLANNED_PROD_BASENAMES: tuple[str, ...] = (
    "stage29_4_soak_models.py",
    "stage29_4_dedupe_index.py",
    "stage29_4_soak_orchestrator.py",
    "stage29_4_soak_artifact_writer.py",
    "stage29_4_manifest.py",
)


@pytest.mark.parametrize(
    "basename", _STAGE_29_4_1_PLANNED_PROD_BASENAMES
)
def test_runbook_lists_each_planned_29_4_1_production_basename(
    basename,
):
    text = _runbook_text()
    assert basename in text, (
        f"Stage 29.4 runbook missing planned Stage 29.4.1 "
        f"production basename {basename!r}"
    )


@pytest.mark.parametrize(
    "basename", _STAGE_29_4_1_PLANNED_PROD_BASENAMES
)
def test_no_stage_29_4_1_production_basename_exists_at_29_4_0(
    basename,
):
    # Stage 29.4.0 is spec-lock-only; no Stage 29.4.1 production
    # .py file may exist under PHX2/stage29/ until Stage 29.4.1
    # is authorized on a separate commit.
    assert not (STAGE29_ROOT / basename).exists(), (
        f"Stage 29.4.0 is spec-lock-only; Stage 29.4.1 "
        f"production basename {basename!r} must NOT exist under "
        f"PHX2/stage29/ at Stage 29.4.0"
    )


def test_no_stage29_4_production_py_module_exists():
    # Any other ``stage29_4_*.py`` basename also blocked. Only
    # the runbook .md file ships at Stage 29.4.0.
    for entry in STAGE29_ROOT.iterdir():
        if entry.is_dir():
            continue
        name = entry.name
        if name.startswith("stage29_4") and name.endswith(".py"):
            raise AssertionError(
                f"Stage 29.4.0 is spec-lock-only; no "
                f"stage29_4_*.py module may exist under "
                f"PHX2/stage29/ at Stage 29.4.0 (found "
                f"{name!r})"
            )


# ---------------------------------------------------------------------------
# 11. Offline Stage 29.4.0 acceptance criteria
# ---------------------------------------------------------------------------


_STAGE_29_4_0_OFFLINE_ACCEPTANCE_PHRASES: tuple[str, ...] = (
    "The Stage 29.4 spec-lock test passes against this runbook",
    "The full Stage 29 test suite passes",
    "The four touched Stage 28 boundary tests pass",
    "The Stage 29.0 spec-lock test passes with its widened "
    "allowlist unions",
    "No Stage 27 / Stage 28 / Stage 29.1 / Stage 29.2 / Stage "
    "29.3 production .py file is modified at Stage 29.4.0",
    "No live Chainstack gRPC call is performed during the "
    "Stage 29.4.0 work",
    "No live Birdeye HTTP call is performed during the Stage "
    "29.4.0 work",
    "No private operator Discord send is performed during the "
    "Stage 29.4.0 work",
    "No commit / tag / push is performed by the automated "
    "agent",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_4_0_OFFLINE_ACCEPTANCE_PHRASES
)
def test_runbook_lists_each_offline_acceptance_phrase(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.4 runbook missing offline acceptance phrase "
        f"{phrase!r}"
    )


# ---------------------------------------------------------------------------
# 12. Future live soak acceptance criteria
# ---------------------------------------------------------------------------


_STAGE_29_4_LIVE_ACCEPTANCE_PHRASES: tuple[str, ...] = (
    "At least one Stage 29.4 mode-3 pass reaches the closed-"
    "set Stage 29.3 `DISPATCHED` outcome",
    "`dispatch_failure_total` is `0`",
    "`redaction_status` is `SAFE`",
    "`filter_enforcement_status` is "
    "`NOT_ACTIVE_STAGE_29_PENDING` on every dispatched ping "
    "ledger record",
    "No duplicate private operator ping is sent during the "
    "soak",
    "`RESERVE -> PRE_SEND -> TERMINAL`",
    "terminal status `DISPATCHED_OK`",
    "`ping_type=PRIVATE_OPERATOR_OBSERVE`",
    "Audience invoked is the private operator only",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_4_LIVE_ACCEPTANCE_PHRASES
)
def test_runbook_lists_each_live_acceptance_phrase(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.4 runbook missing live acceptance phrase "
        f"{phrase!r}"
    )


def test_runbook_says_no_dispatch_soak_is_legitimate_result():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "is a legitimate non-error soak result"
    ) in normalized


# ---------------------------------------------------------------------------
# 13. Forbidden surfaces under Stage 29.4
# ---------------------------------------------------------------------------


_STAGE_29_4_FORBIDDEN_SURFACE_PHRASES: tuple[str, ...] = (
    "daemon / systemd / watchdog / autorestart service",
    "infinite loop / unbounded session",
    "Stage 26 policy enforcement activation",
    "public routing",
    "subscriber routing",
    "paid-tier routing",
    "Telegram sender / Telegram client",
    "X / social sidecar",
    "automated trading / position sizing / trade execution",
    "wallet / private-key / signer logic",
    "public dashboard / HTTP control server",
    "new env name",
    "new third-party runtime dependency",
    "PHX1 / Phoenix_Bot import path",
    "Pump.fun bonding-curve decoder",
    "Dexscreener as a dispatch authority",
    "Helius as a price source",
    "third or fourth provider beyond Stage 28.11 (Chainstack) "
    "+ Stage 29.2 (Birdeye)",
    "persistent dedupe index",
    "Stage 29.5+ implementation",
)


@pytest.mark.parametrize(
    "phrase", _STAGE_29_4_FORBIDDEN_SURFACE_PHRASES
)
def test_runbook_lists_each_forbidden_surface(phrase):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.4 runbook missing forbidden surface "
        f"{phrase!r}"
    )


def test_runbook_pins_zero_env_read_in_stage_29_4_production():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.4 production source under `PHX2/stage29/` "
        "must contain zero `os.environ` / `os.getenv` / "
        "`os.environb` calls"
    ) in normalized


def test_runbook_pins_no_time_sleep_or_threading_or_async():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.4 must not introduce any `time.sleep(`-driven "
        "scheduling, any `threading.Thread`, any `asyncio` "
        "event loop, any `subprocess`, any `multiprocessing`"
    ) in normalized


# ---------------------------------------------------------------------------
# 14. Stage 29.3 artifact-projection caveat documented as deferred
# ---------------------------------------------------------------------------


_STAGE_29_3_CAVEAT_PHRASES: tuple[str, ...] = (
    "Stage 29.3 mode-3 ceremonies currently emit per-event "
    "Stage 29.3 artifact files",
    "show the safe-shape default projection (`NO_EXTRACTION` "
    "/ `MISSING`)",
    "Section 12.6 of the Stage 29.3 runbook",
    "Stage 29.4 acceptance does NOT depend on this projection "
    "being cleaned up",
    "Threading the live extraction + Birdeye price / ATH "
    "evidence back onto the per-event mode-3 artifact files "
    "is reserved for a separate operator-gated substage",
    "explicitly NOT part of Stage 29.4",
)


@pytest.mark.parametrize("phrase", _STAGE_29_3_CAVEAT_PHRASES)
def test_runbook_pins_each_artifact_projection_caveat_phrase(
    phrase,
):
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.4 runbook missing artifact-projection "
        f"caveat phrase {phrase!r}"
    )


def test_runbook_pins_authoritative_proof_axes():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "the Stage 28.9 health-snapshot counters"
    ) in normalized
    assert (
        "the Stage 28.2 dispatch ledger terminal record"
    ) in normalized


# ---------------------------------------------------------------------------
# 15. Closed-set vocabularies summary section
# ---------------------------------------------------------------------------


def test_runbook_contains_closed_set_vocabularies_summary():
    text = _runbook_text()
    assert "Stage 29.4 closed-set vocabularies" in text


def test_runbook_pins_filter_enforcement_status_locked():
    text = _runbook_text()
    assert "NOT_ACTIVE_STAGE_29_PENDING" in text


def test_runbook_pins_redaction_status_safe_and_redacted():
    text = _runbook_text()
    assert "`SAFE`" in text
    assert "`REDACTED`" in text


# ---------------------------------------------------------------------------
# 16. Stage 29.4 inventory under PHX2/stage29/ at Stage 29.4.0
# ---------------------------------------------------------------------------


_STAGE_29_4_0_REQUIRED_PROD_ENTRY: str = (
    "STAGE_29_4_SHORT_SESSION_PRIVATE_SOAK_RUNBOOK.md"
)


def test_stage29_4_runbook_admitted_under_phx2_stage29():
    actual = {entry.name for entry in STAGE29_ROOT.iterdir()}
    assert _STAGE_29_4_0_REQUIRED_PROD_ENTRY in actual, (
        f"Stage 29.4.0 requires "
        f"{_STAGE_29_4_0_REQUIRED_PROD_ENTRY!r} under "
        f"PHX2/stage29/"
    )


def test_stage29_4_spec_lock_test_admitted_under_tests_stage29():
    actual = {entry.name for entry in TESTS_STAGE29_ROOT.iterdir()}
    assert "test_stage_29_4_spec_lock.py" in actual, (
        "Stage 29.4.0 requires test_stage_29_4_spec_lock.py "
        "under PHX2/tests/stage29/"
    )


# ---------------------------------------------------------------------------
# 17. Runbook carries no URL / webhook host / raw secret literal
# ---------------------------------------------------------------------------


# Concatenated literally so this test file does not itself trip a
# downstream string-leak scan that flags the canonical URL / host
# / secret-shape substrings.
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
        f"Stage 29.4 runbook must not contain URL literal "
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


# Concatenated literally so this test file does not itself trip a
# raw-secret-assignment scan.
_FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES: tuple[str, ...] = (
    "webhook" + "_url" + "=",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
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
        f"Stage 29.4 runbook must not carry raw "
        f"secret-assignment name {needle!r}"
    )


# ---------------------------------------------------------------------------
# 18. Runbook explicitly defers Stage 29.4.1 + Stage 29.5+
# ---------------------------------------------------------------------------


def test_runbook_says_stage_29_4_1_is_reserved_at_29_4_0():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "Stage 29.4.1 is reserved at Stage 29.4.0"
    ) in normalized


def test_runbook_says_stage_29_5_plus_blocked():
    text = _runbook_text()
    assert "Stage 29.5+ implementation" in text


def test_runbook_says_stage_29_4_inherits_per_pass_stage_29_3_locks():
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "outer loop runs multiple passes, not multiple "
        "dispatches per pass"
    ) in normalized
