"""Stage 29.5.4 spec-lock pins.

Pins:

  * Runbook file exists at the locked path.
  * Canonical Stage 29.5.4 mission sentence is present verbatim
    (whitespace-normalized match).
  * Section 1 ("Canonical Stage 29.5.4 mission sentence")
    declares the mission.
  * Section 5 ("Behavior matrix (closed-set)") names every
    Stage 29.5 measurement_status branch.
  * Discord rendering is explicitly named as deferred to Stage
    29.5.5.
  * Stage 29.4 / Stage 29.5 / Stage 29.5.2 / Stage 29.5.3
    production untouched stance is pinned.
  * Stage 29.5.4 is described as opt-in.
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
    / "STAGE_29_5_4_MIGRATION_CONTEXT_INJECTION_RUNBOOK.md"
)


def _read() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_runbook_exists() -> None:
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 29.5.4 runbook must exist at {RUNBOOK_PATH}"
    )


def test_canonical_mission_sentence_verbatim() -> None:
    expected = (
        "Stage 29.5.4 is the direct opt-in migration context "
        "injection substage that lets an operator thread the "
        "Stage 29.5.2 offline composition into the Stage 29.3 "
        "private tradeable ping path via a single optional "
        "`migration_source` kwarg on "
        "`run_stage29_3_first_private_tradeable_smoke`, while "
        "preserving `Stage29_3NoMigrationEvidenceSource` as the "
        "hard default and modifying no Stage 29.4, Stage 29.5, "
        "Stage 29.5.2, or Stage 29.5.3 production source."
    )
    normalized_source = _normalize_whitespace(_read())
    assert _normalize_whitespace(expected) in normalized_source


def test_section_headings_present() -> None:
    src = _read()
    assert (
        "## 1. Canonical Stage 29.5.4 mission sentence" in src
    )
    assert "## 2. Scope" in src
    assert "## 3. Why a separate Stage 29.5.4 substage" in src
    assert "## 4. Data flow" in src
    assert "## 5. Behavior matrix" in src
    assert "## 6. Acceptance criteria" in src
    assert "## 7. Forbidden surfaces" in src
    assert "## 8. Files added at Stage 29.5.4" in src
    assert "## 9. Deferred after Stage 29.5.4" in src
    assert "## 10. Operator runbook" in src
    assert "## 11. Stage 29.5.4 schema version" in src


def test_behavior_matrix_names_every_measurement_status() -> None:
    src = _read()
    for status in (
        "COMPLETE",
        "PARTIAL_MIGRATION_PRESENT",
        "MISSING_MIGRATION",
        "INVALID_MIGRATION",
        "CONFLICTING_MIGRATION",
    ):
        assert status in src, (
            f"Stage 29.5.4 runbook must name measurement_status "
            f"branch {status!r} in the behavior matrix"
        )


def test_discord_rendering_deferred_to_29_5_5() -> None:
    src = _read()
    lower = src.lower()
    assert "discord rendering" in lower or (
        "formatted discord rendering" in lower
    )
    assert "stage 29.5.5" in lower, (
        "Stage 29.5.4 runbook must explicitly defer formatted "
        "Discord rendering to Stage 29.5.5"
    )


def test_stage_29_4_production_untouched_pinned() -> None:
    src = _read()
    assert "Stage 29.4" in src
    assert (
        "untouched" in src or "unchanged" in src or (
            "no Stage 29.4" in src.lower()
            or "zero stage 29.4" in src.lower()
        )
    ), (
        "Stage 29.5.4 runbook must pin Stage 29.4 production as "
        "untouched / unchanged"
    )


def test_stage_29_5_production_untouched_pinned() -> None:
    src = _read()
    lower = src.lower()
    assert "stage 29.5" in lower
    assert (
        "manifest inventory change" in lower
        or "production source" in lower
        or "manifest inventory" in lower
    )


def test_opt_in_phrasing_present() -> None:
    src = _read()
    lower = src.lower()
    assert "opt-in" in lower or "opt in" in lower, (
        "Stage 29.5.4 runbook must describe the injection as "
        "opt-in"
    )


def test_default_remains_no_migration_evidence_source() -> None:
    src = _read()
    assert "Stage29_3NoMigrationEvidenceSource" in src, (
        "Stage 29.5.4 runbook must reference the default "
        "Stage29_3NoMigrationEvidenceSource fallback class"
    )


def test_byte_equivalent_default_promise_present() -> None:
    src = _read()
    lower = src.lower()
    assert "byte-equivalent" in lower or (
        "byte equivalent" in lower
    ), (
        "Stage 29.5.4 runbook must promise byte-equivalent "
        "default behavior"
    )


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
            f"Stage 29.5.4 runbook must not carry URL host "
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
            f"Stage 29.5.4 runbook must not carry raw-secret-"
            f"shaped literal {needle!r}"
        )


def test_no_pump_fun_program_id_in_runbook() -> None:
    src = _read()
    assert (
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P" not in src
    )


def test_no_phx1_substring_in_runbook() -> None:
    src = _read()
    lower = src.lower()
    assert "phoenix_bot" not in lower, (
        "Stage 29.5.4 runbook must not carry the 'Phoenix_Bot' "
        "substring; use 'legacy phoenix-1' or similar synonym"
    )


def test_acceptance_criteria_a_through_p_named() -> None:
    """Stage 29.5.4 ships 16 acceptance criteria A through P; the
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
    ):
        assert f"**{letter}.**" in src, (
            f"Stage 29.5.4 runbook must name acceptance "
            f"criterion {letter!r}"
        )


def test_schema_version_pinned_in_runbook() -> None:
    src = _read()
    assert (
        "stage29_5_4_v0_migration_context_source_adapter" in src
    )
