"""Stage 29.5.3 spec-lock tests.

Pins:

  * ``PHX2/stage29/STAGE_29_5_3_SOAK_PASS_WRAPPER_RUNBOOK.md``
    exists and carries the canonical Stage 29.5.3 mission
    sentence verbatim.
  * The runbook names Stage 29.5.3 explicitly, lists the
    Stage 29.5.3 production / test / touched-test inventory,
    documents the closed-set observation status vocabulary,
    documents the locked side-channel artifact basename,
    documents the data-flow diagram, the acceptance criteria,
    and the deferred-after-29.5.3 list.
  * The runbook carries no URL host literal, no API key
    pattern, no raw webhook URL, no auth header.
  * The runbook carries no actual PHX1 import statement.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"
RUNBOOK_PATH: Path = (
    STAGE29_ROOT
    / "STAGE_29_5_3_SOAK_PASS_WRAPPER_RUNBOOK.md"
)


STAGE_29_5_3_MISSION_SENTENCE: str = (
    "Stage 29.5.3 is the runtime-adjacent soak pass-entrypoint "
    "wrapper and side-channel artifact surface substage that "
    "lets an operator thread the Stage 29.5.2 offline migration "
    "context composition into the Stage 29.4 short-session "
    "private soak path without modifying any Stage 29.3 or "
    "Stage 29.4 production source."
)


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Runbook + spec-lock test file exist
# ---------------------------------------------------------------------------


def test_stage_29_5_3_runbook_exists() -> None:
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 29.5.3 requires the runbook document "
        f"{RUNBOOK_PATH}"
    )


def test_stage_29_5_3_spec_lock_test_file_exists() -> None:
    self_path = (
        TESTS_STAGE29_ROOT / "test_stage_29_5_3_spec_lock.py"
    )
    assert self_path.is_file()


# ---------------------------------------------------------------------------
# 2. Canonical Stage 29.5.3 mission sentence verbatim
# ---------------------------------------------------------------------------


def test_runbook_contains_canonical_mission_sentence_verbatim() -> None:
    normalized = _normalized_whitespace(_runbook_text())
    assert STAGE_29_5_3_MISSION_SENTENCE in normalized, (
        "Stage 29.5.3 runbook must contain the canonical "
        "mission sentence verbatim (whitespace-normalized "
        "match)"
    )


def test_runbook_names_stage_29_5_3_explicitly() -> None:
    text = _runbook_text()
    assert "Stage 29.5.3" in text


# ---------------------------------------------------------------------------
# 3. Stage 29.5.3 inventory listed in the runbook
# ---------------------------------------------------------------------------


_STAGE_29_5_3_NEW_PRODUCTION_PATHS: tuple[str, ...] = (
    "PHX2/stage29/stage29_5_3_wrapped_pass_models.py",
    "PHX2/stage29/stage29_5_3_soak_pass_wrapper.py",
    "PHX2/stage29/stage29_5_3_side_channel_artifact_writer.py",
    "PHX2/stage29/stage29_5_3_manifest.py",
    "PHX2/stage29/STAGE_29_5_3_SOAK_PASS_WRAPPER_RUNBOOK.md",
)


@pytest.mark.parametrize(
    "path", _STAGE_29_5_3_NEW_PRODUCTION_PATHS,
)
def test_runbook_lists_each_new_production_file(
    path: str,
) -> None:
    text = _runbook_text()
    assert path in text


_STAGE_29_5_3_NEW_TEST_PATHS: tuple[str, ...] = (
    "PHX2/tests/stage29/test_stage_29_5_3_wrapped_pass_models.py",
    "PHX2/tests/stage29/test_stage_29_5_3_soak_pass_wrapper.py",
    "PHX2/tests/stage29/test_stage_29_5_3_side_channel_artifact_writer.py",
    "PHX2/tests/stage29/test_stage_29_5_3_manifest.py",
    "PHX2/tests/stage29/test_stage_29_5_3_boundaries.py",
    "PHX2/tests/stage29/test_stage_29_5_3_no_modification_to_stage_29_3_or_29_4.py",
    "PHX2/tests/stage29/test_stage_29_5_3_spec_lock.py",
)


@pytest.mark.parametrize(
    "path", _STAGE_29_5_3_NEW_TEST_PATHS,
)
def test_runbook_lists_each_new_test_file(path: str) -> None:
    text = _runbook_text()
    assert path in text


_STAGE_29_5_3_TOUCHED_TEST_PATHS: tuple[str, ...] = (
    "PHX2/tests/stage28/test_stage_28_8_boundaries.py",
    "PHX2/tests/stage28/test_stage_28_9_boundaries.py",
    "PHX2/tests/stage28/test_stage_28_10_boundaries.py",
    "PHX2/tests/stage28/test_stage_28_11_boundaries.py",
    "PHX2/tests/stage29/test_stage_29_0_spec_lock.py",
    "PHX2/tests/stage29/test_stage_29_5_manifest.py",
    "PHX2/tests/stage29/test_stage_29_5_spec_lock.py",
)


# Stage 29.5.2 test files MUST NOT be in the Stage 29.5.3 touched-
# test inventory. The Stage 29.5.2 manifest already pins the
# Stage 29.5.3 wrapper surface as forbidden, and the Stage 29.5.2
# boundary test already pins the Stage 29.5.3 identifier
# substrings as forbidden, from their respective Stage 29.5.2
# commits. Neither file requires a Stage 29.5.3 widening; both
# remain byte-for-byte identical to their Stage 29.5.2 state.
_STAGE_29_5_2_FILES_NOT_TOUCHED_AT_29_5_3: tuple[str, ...] = (
    "PHX2/tests/stage29/test_stage_29_5_2_manifest.py",
    "PHX2/tests/stage29/test_stage_29_5_2_boundaries.py",
)


def test_touched_test_inventory_has_exactly_seven_entries() -> None:
    """The Stage 29.5.3 touched-test inventory pins exactly seven
    test files. Earlier runbook drafts claimed nine; Codex flagged
    the inventory drift after observing only seven files actually
    modified at Stage 29.5.3.
    """
    assert len(_STAGE_29_5_3_TOUCHED_TEST_PATHS) == 7, (
        "Stage 29.5.3 widens exactly seven test files (four "
        "Stage 28 boundary tests + three Stage 29 spec-lock / "
        "manifest tests). Updating this constant requires "
        "updating the runbook touched-test inventory too."
    )


@pytest.mark.parametrize(
    "path", _STAGE_29_5_3_TOUCHED_TEST_PATHS,
)
def test_runbook_lists_each_touched_test_file(
    path: str,
) -> None:
    text = _runbook_text()
    assert path in text


@pytest.mark.parametrize(
    "path", _STAGE_29_5_2_FILES_NOT_TOUCHED_AT_29_5_3,
)
def test_runbook_does_not_claim_29_5_2_files_as_touched(
    path: str,
) -> None:
    """Pin that the Stage 29.5.3 runbook does NOT claim
    ``test_stage_29_5_2_manifest.py`` or
    ``test_stage_29_5_2_boundaries.py`` are part of the Stage
    29.5.3 touched-test inventory. The runbook may MENTION them
    in explanatory prose (and does, to call out that they were
    NOT widened at Stage 29.5.3), but the bare-path bullet under
    the inventory section is reserved for files actually modified
    at Stage 29.5.3.

    Inventory drift detection: the runbook source must not
    contain a markdown-bullet line ``- <path>`` for these two
    paths. We scan for the exact bulleted bullet substring so
    explanatory prose that names the file in flowing sentences
    (without a leading dash) does not trip the check.
    """
    text = _runbook_text()
    bulleted = f"- `{path}`\n"
    assert bulleted not in text, (
        f"Stage 29.5.3 runbook must not list {path!r} as a "
        f"bulleted touched-test inventory entry; this file was "
        f"NOT widened at Stage 29.5.3 (the Stage 29.5.2 commit "
        f"already pinned the Stage 29.5.3 surface as forbidden)."
    )


# ---------------------------------------------------------------------------
# 4. Closed-set Stage 29.5.3 observation status vocabulary in runbook
# ---------------------------------------------------------------------------


_OBSERVATION_STATUS_TOKENS: tuple[str, ...] = (
    "NO_CANDIDATE_AXES",
    "COMPOSED",
    "COMPOSITION_REJECTED",
    "PROVIDER_REJECTED",
)


@pytest.mark.parametrize(
    "token", _OBSERVATION_STATUS_TOKENS,
)
def test_runbook_names_each_observation_status_token(
    token: str,
) -> None:
    text = _runbook_text()
    assert token in text


# ---------------------------------------------------------------------------
# 5. Locked Stage 29.5.3 schema version + locked tokens in runbook
# ---------------------------------------------------------------------------


def test_runbook_pins_schema_version() -> None:
    text = _runbook_text()
    assert (
        "stage29_5_3_wrapped_pass_observation_v0" in text
    )


def test_runbook_pins_locked_filter_enforcement_status() -> None:
    text = _runbook_text()
    assert "NOT_ACTIVE_STAGE_29_PENDING" in text


def test_runbook_pins_locked_redaction_status_safe() -> None:
    text = _runbook_text()
    assert "SAFE" in text


def test_runbook_pins_side_channel_artifact_basename() -> None:
    text = _runbook_text()
    assert "stage29_5_3_migration_context.jsonl" in text


# ---------------------------------------------------------------------------
# 6. Forbidden surfaces enumerated in the runbook
# ---------------------------------------------------------------------------


_RUNBOOK_FORBIDDEN_SURFACE_PHRASES: tuple[str, ...] = (
    "production enforcement",
    "public routing",
    "subscriber routing",
    "paid tier routing",
    "Telegram sender",
    "X / social sidecar",
    "automated trading",
    "wallet / private-key / signer logic",
    "Pump.fun bonding-curve decoder",
    "Dexscreener as a dispatch authority",
    "Helius as a price source",
    "PHX1 import path",
    "new env name",
    "new third-party runtime dependency",
    "Stage 29.3 runtime wiring change",
    "Stage 29.4 runtime wiring change",
    "Stage 29.5 manifest inventory change",
    "Stage 29.5.2 manifest inventory change",
    "direct Stage 29.3 migration-context injection",
    "Stage 29.6+ implementation",
    "formatted Discord rendering",
)


@pytest.mark.parametrize(
    "phrase", _RUNBOOK_FORBIDDEN_SURFACE_PHRASES,
)
def test_runbook_lists_each_forbidden_surface(
    phrase: str,
) -> None:
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized, (
        f"Stage 29.5.3 runbook missing forbidden surface "
        f"{phrase!r}"
    )


def test_runbook_says_no_tag_no_push() -> None:
    text = _runbook_text()
    assert (
        "Stage 29.5.3 must not create a "
        "`stage-29-5-3-closed` tag"
    ) in text
    assert (
        "Stage 29.5.3 must not push to any remote" in text
    )


# ---------------------------------------------------------------------------
# 7. Deferred-after-29.5.3 list pinned
# ---------------------------------------------------------------------------


_DEFERRED_AFTER_29_5_3_PHRASES: tuple[str, ...] = (
    "formatted Discord rendering of migration context",
    "live Helius WS migration-evidence ingestion",
    "Stage 26 / Stage 29 policy enforcement activation",
    "direct Stage 29.3 migration-context source swap",
    "Stage 29 closure",
    "Stage 29.6+ implementation",
)


@pytest.mark.parametrize(
    "phrase", _DEFERRED_AFTER_29_5_3_PHRASES,
)
def test_runbook_lists_each_deferred_after_29_5_3_phrase(
    phrase: str,
) -> None:
    normalized = _normalized_whitespace(_runbook_text())
    assert phrase in normalized


# ---------------------------------------------------------------------------
# 8. Runbook carries no URL host literal / no raw secret pattern
# ---------------------------------------------------------------------------


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
    "needle", _FORBIDDEN_URL_LITERAL_SUBSTRINGS,
)
def test_runbook_has_no_url_literal(needle: str) -> None:
    text = _runbook_text()
    assert needle not in text


_FORBIDDEN_SECRET_LOOKING_PATTERNS: tuple[str, ...] = (
    r"Authorization:\s*\S+",
    r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}",
    r"\bsk-[A-Za-z0-9_-]{8,}\b",
    r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b",
)


@pytest.mark.parametrize(
    "pattern", _FORBIDDEN_SECRET_LOOKING_PATTERNS,
)
def test_runbook_has_no_secret_looking_raw_value(
    pattern: str,
) -> None:
    assert not re.search(pattern, _runbook_text())


_FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES: tuple[str, ...] = (
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
    "HELIUS_WS" + "_URL=",
    "HELIUS_WS" + "_ENDPOINT=",
    "BIRDEYE_API" + "_KEY=",
    "PHX2_CHAINSTACK_YELLOWSTONE_X" + "_TOKEN=",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES,
)
def test_runbook_has_no_raw_secret_assignment_name(
    needle: str,
) -> None:
    text = _runbook_text()
    assert needle not in text


# ---------------------------------------------------------------------------
# 9. Runbook has no PHX1 import statement
# ---------------------------------------------------------------------------


def test_runbook_has_no_phx1_import_path() -> None:
    text = _runbook_text()
    forbidden_import_substrings = (
        "from " + "Phoenix_Bot",
        "import " + "Phoenix_Bot",
        "from " + "phoenix_bot",
        "import " + "phoenix_bot",
    )
    for needle in forbidden_import_substrings:
        assert needle not in text


# ---------------------------------------------------------------------------
# 10. Data-flow diagram + acceptance criteria are present
# ---------------------------------------------------------------------------


def test_runbook_has_data_flow_section() -> None:
    text = _runbook_text()
    assert "## 4. Data flow" in text or "Data flow" in text


def test_runbook_has_acceptance_criteria_section() -> None:
    text = _runbook_text()
    assert "acceptance criteria" in text.lower()


def test_runbook_says_wrapper_is_observational_only() -> None:
    normalized = _normalized_whitespace(_runbook_text())
    assert "observational" in normalized.lower()


def test_runbook_says_wrapper_returns_inner_pass_result_unchanged() -> None:
    normalized = _normalized_whitespace(_runbook_text())
    assert (
        "return the inner result by identity"
        in normalized.lower()
        or "echo the inner result by identity"
        in normalized.lower()
        or (
            "return"
            in normalized.lower()
            and "by identity" in normalized.lower()
        )
    )
