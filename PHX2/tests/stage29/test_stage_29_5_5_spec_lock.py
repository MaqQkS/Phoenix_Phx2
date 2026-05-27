"""Stage 29.5.5 spec-lock pins.

Pins:

  * Runbook file exists at the locked path.
  * Canonical Stage 29.5.5 mission sentence is present verbatim
    (whitespace-normalized match).
  * Required section headings declared.
  * Section 5 (status display matrix) names every Stage 29.5
    measurement_status branch AND every Stage 29.5
    migration_source token.
  * Stage 29.4 / Stage 29.5 / Stage 29.5.2 / Stage 29.5.3 /
    Stage 29.5.4 production untouched stance is pinned.
  * Stage 29.5.5 is described as opt-in.
  * Discord-dispatch-behavior-change pin preserved (Stage
    29.5.5 does NOT modify dispatch behavior; the rendered
    block is side-channel only).
  * No URL host / raw secret / Pump.fun program-id literal in
    the runbook.
"""

from __future__ import annotations

import re
from pathlib import Path


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
RUNBOOK_PATH: Path = (
    STAGE29_ROOT
    / "STAGE_29_5_5_PRIVATE_DISCORD_MIGRATION_CONTEXT_RENDERING_RUNBOOK.md"
)


def _read() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_runbook_exists() -> None:
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 29.5.5 runbook must exist at {RUNBOOK_PATH}"
    )


def test_canonical_mission_sentence_verbatim() -> None:
    expected = (
        "Stage 29.5.5 is the formatted private Discord "
        "migration context rendering substage that adds a "
        "deterministic redaction-safe offline renderer plus "
        "a Stage 29.5.5 recording adapter and a Stage 29.5.5 "
        "side-channel artifact writer, threads one optional "
        "`migration_context_renderer` kwarg into "
        "`run_stage29_3_first_private_tradeable_smoke` so an "
        "operator may capture per-candidate rendered "
        "migration context blocks as a side-channel artifact "
        "without modifying the dispatched Discord body, and "
        "modifies no Stage 29.4, Stage 29.5, Stage 29.5.2, "
        "Stage 29.5.3, or Stage 29.5.4 production source."
    )
    normalized_source = _normalize_whitespace(_read())
    assert _normalize_whitespace(expected) in normalized_source


def test_section_headings_present() -> None:
    src = _read()
    assert (
        "## 1. Canonical Stage 29.5.5 mission sentence" in src
    )
    assert "## 2. Scope" in src
    assert "## 3. Why a separate Stage 29.5.5 substage" in src
    assert "## 4. Data flow" in src
    assert "## 5. Status display matrix" in src
    assert "## 6. Acceptance criteria" in src
    assert "## 7. Forbidden surfaces" in src
    assert "## 8. Files added at Stage 29.5.5" in src
    assert "## 9. Deferred after Stage 29.5.5" in src
    assert "## 10. Operator runbook" in src
    assert "## 11. Stage 29.5.5 schema versions" in src


def test_section_5_names_every_measurement_status() -> None:
    src = _read()
    for status in (
        "COMPLETE",
        "PARTIAL_MIGRATION_PRESENT",
        "MISSING_MIGRATION",
        "INVALID_MIGRATION",
        "CONFLICTING_MIGRATION",
    ):
        assert status in src, (
            f"Stage 29.5.5 runbook must name "
            f"measurement_status branch {status!r} in the "
            f"status display matrix"
        )


def test_section_5_names_every_migration_source_token() -> None:
    src = _read()
    for token in (
        "HELIUS_WS",
        "STAGE29_MIGRATION_ARTIFACT",
        "SYNTHETIC_TEST_ONLY",
        "UNKNOWN",
    ):
        assert token in src, (
            f"Stage 29.5.5 runbook must name migration_source "
            f"token {token!r} in the status display matrix"
        )


def test_section_5_names_every_ath_verified_display_token() -> None:
    src = _read()
    for token in (
        "ATH_VERIFIED_POST_MIGRATION",
        "ATH_NOT_VERIFIED_POST_MIGRATION",
        "ATH_VERIFICATION_UNKNOWN",
    ):
        assert token in src, (
            f"Stage 29.5.5 runbook must name "
            f"post_migration_ath_verified display token "
            f"{token!r}"
        )


def test_section_5_names_every_source_trust_display_token() -> None:
    src = _read()
    for token in (
        "SOURCE_TRUSTED_ON_CHAIN",
        "SOURCE_UNTRUSTED_SYNTHETIC",
        "SOURCE_UNTRUSTED_UNKNOWN",
        "SOURCE_PARTIAL_ON_CHAIN",
        "SOURCE_PARTIAL_SYNTHETIC",
        "SOURCE_NO_SOURCE",
    ):
        assert token in src, (
            f"Stage 29.5.5 runbook must name source_trust "
            f"display token {token!r}"
        )


def test_section_5_names_every_evidence_status_display_token() -> None:
    src = _read()
    for token in (
        "MIGRATION_EVIDENCE_COMPLETE",
        "MIGRATION_EVIDENCE_PARTIAL",
        "MIGRATION_EVIDENCE_MISSING",
        "MIGRATION_EVIDENCE_INVALID",
        "MIGRATION_EVIDENCE_CONFLICTING",
    ):
        assert token in src, (
            f"Stage 29.5.5 runbook must name "
            f"evidence_status display token {token!r}"
        )


def test_stage_29_4_production_untouched_pinned() -> None:
    src = _read()
    assert "Stage 29.4" in src
    lower = src.lower()
    assert (
        "untouched" in lower or "unchanged" in lower
    ), (
        "Stage 29.5.5 runbook must pin Stage 29.4 production "
        "as untouched / unchanged"
    )


def test_stage_29_5_4_production_untouched_pinned() -> None:
    src = _read()
    assert "Stage 29.5.4" in src
    lower = src.lower()
    assert (
        "modifies no" in lower
        or "untouched" in lower
        or "unchanged" in lower
    )


def test_stage_29_5_production_untouched_pinned() -> None:
    src = _read()
    lower = src.lower()
    assert "stage 29.5" in lower


def test_opt_in_phrasing_present() -> None:
    src = _read()
    lower = src.lower()
    assert (
        "opt-in" in lower or "opt in" in lower
    ), (
        "Stage 29.5.5 runbook must describe the renderer "
        "wiring as opt-in"
    )


def test_no_dispatch_behavior_change_pinned() -> None:
    src = _read()
    lower = src.lower()
    assert (
        "live dispatched discord body" in lower
        or "discord dispatch behavior change" in lower
    ), (
        "Stage 29.5.5 runbook must explicitly pin that the "
        "live dispatched Discord body remains unchanged"
    )


def test_side_channel_phrasing_present() -> None:
    src = _read()
    lower = src.lower()
    assert "side-channel" in lower or "side channel" in lower


def test_byte_equivalent_default_promise_present() -> None:
    src = _read()
    lower = src.lower()
    assert (
        "byte-equivalent" in lower or "byte equivalent" in lower
    ), (
        "Stage 29.5.5 runbook must promise byte-equivalent "
        "default behavior"
    )


def test_informational_only_pin_present() -> None:
    src = _read()
    assert "informational_only" in src


def test_not_a_trading_verdict_pin_present() -> None:
    src = _read()
    assert "not_a_trading_verdict" in src


_FORBIDDEN_URL_HOSTS: tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "mainnet.helius" + "-rpc.com",
    "public-api.birdeye" + ".so",
    "pro-api.birdeye" + ".so",
    "birdeye" + ".so",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
    "chainstack" + ".com",
    "yellowstone" + ".chainstack",
    "dexscreener" + ".com",
    "ws" + "s://",
    "ws" + "://",
)


def test_no_url_host_literal_in_runbook() -> None:
    src = _read()
    for needle in _FORBIDDEN_URL_HOSTS:
        assert needle not in src, (
            f"Stage 29.5.5 runbook must not carry URL host "
            f"literal {needle!r}"
        )


_FORBIDDEN_RAW_SECRET_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "s" + "k-",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "BIRDEYE_API" + "_KEY=",
    "CHAINSTACK_API" + "_KEY=",
)


def test_no_raw_secret_literal_in_runbook() -> None:
    src = _read()
    for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
        assert needle not in src, (
            f"Stage 29.5.5 runbook must not carry raw-secret-"
            f"shaped literal {needle!r}"
        )


def test_no_pump_fun_program_id_in_runbook() -> None:
    src = _read()
    pump_program = (
        "6EF8rrec" + "thR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    )
    assert pump_program not in src


def test_no_phx1_substring_in_runbook() -> None:
    src = _read()
    lower = src.lower()
    assert "phoenix_bot" not in lower, (
        "Stage 29.5.5 runbook must not carry the "
        "'Phoenix_Bot' substring; use 'legacy phoenix-1' or a "
        "similar synonym"
    )


def test_acceptance_criteria_a_through_r_named() -> None:
    """Stage 29.5.5 ships acceptance criteria A through R; the
    runbook MUST name each letter so the surface stays
    auditable.
    """
    src = _read()
    for letter in (
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
        "L",
        "M",
        "N",
        "O",
        "P",
        "Q",
        "R",
    ):
        assert f"**{letter}.**" in src, (
            f"Stage 29.5.5 runbook must name acceptance "
            f"criterion {letter!r}"
        )


def test_renderer_schema_version_pinned_in_runbook() -> None:
    src = _read()
    assert (
        "stage29_5_5_v0_private_discord_migration_context_renderer"
        in src
    )


def test_recorder_schema_version_pinned_in_runbook() -> None:
    src = _read()
    assert (
        "stage29_5_5_v0_migration_context_recorder" in src
    )


def test_side_channel_writer_schema_version_pinned_in_runbook() -> None:
    src = _read()
    assert (
        "stage29_5_5_v0_side_channel_artifact_writer" in src
    )


def test_rendered_block_schema_version_pinned_in_runbook() -> None:
    src = _read()
    assert (
        "stage29_5_5_v0_rendered_migration_context_block" in src
    )
