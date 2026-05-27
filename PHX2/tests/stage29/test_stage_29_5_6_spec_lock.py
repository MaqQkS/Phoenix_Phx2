"""Stage 29.5.6 spec-lock pins.

Pins:

  * Runbook file exists at the locked path.
  * Canonical Stage 29.5.6 mission sentence is present verbatim
    (whitespace-normalized match).
  * Required section headings declared.
  * Section 5 (injector behavior matrix) names every closed-set
    mode + outcome branch.
  * Stage 27 / Stage 28 / Stage 29.4 / Stage 29.5 / Stage 29.5.2
    / Stage 29.5.3 / Stage 29.5.4 / Stage 29.5.5 production
    untouched stance is pinned.
  * Stage 29.5.6 is described as opt-in and mode-3-only.
  * Default-byte-equivalent promise present.
  * Combined-content cap pin (1900) present.
  * Acceptance criteria letters A-R named.
  * Stage 29.5.6 schema version pinned in the runbook.
  * Stage 29.6 deferred pin present.
  * No URL host / raw secret / Pump.fun program-id literal in the
    runbook.
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
    / "STAGE_29_5_6_PRIVATE_PING_MIGRATION_CONTEXT_RUNBOOK.md"
)


def _read() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def test_runbook_exists() -> None:
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 29.5.6 runbook must exist at {RUNBOOK_PATH}"
    )


def test_canonical_mission_sentence_verbatim() -> None:
    expected = (
        "Stage 29.5.6 is the private ping body migration "
        "context injection substage that adds a deterministic "
        "redaction-safe transport-wrapper injector which first "
        "tries to append the full already-rendered Stage 29.5.5 "
        "migration context block to the operator-visible "
        "private Discord ping body, falls back to a "
        "deterministic compact migration-context block built "
        "from already-revalidated closed-set / display fields "
        "on the rendered block when the full append would "
        "exceed the local 1900-character combined-body cap, "
        "appends the compact block when the compact append "
        "fits the cap, skips the append entirely only when the "
        "compact append would also overflow (never truncates "
        "the rendered block, never appends a partial / "
        "invented block, never appends raw JSON), threads one "
        "optional `private_discord_body_injector` kwarg into "
        "`run_stage29_3_first_private_tradeable_smoke`, gates "
        "the injection mode-3-only and opt-in, validates the "
        "wrapped transport candidate via "
        "`callable(getattr(candidate, \"send_one_audited_post\", "
        "None))` before replacing the original Stage 28.9 "
        "transport and falls back to the unwrapped transport "
        "on any wrap-time exception or non-conforming "
        "candidate, mutates a copied payload only, "
        "re-validates the rendered block via the Stage 29.5.5 "
        "closed-set safety validator immediately before each "
        "append, and modifies no Stage 27, Stage 28, Stage "
        "29.4, Stage 29.5, Stage 29.5.2, Stage 29.5.3, Stage "
        "29.5.4, or Stage 29.5.5 production source."
    )
    normalized_source = _normalize_whitespace(_read())
    assert _normalize_whitespace(expected) in normalized_source


def test_section_headings_present() -> None:
    src = _read()
    assert "## 1. Canonical Stage 29.5.6 mission sentence" in src
    assert "## 2. Scope" in src
    assert "## 3. Why a separate Stage 29.5.6 substage" in src
    assert "## 4. Data flow" in src
    assert "## 5. Injector behavior matrix" in src
    assert "## 6. Acceptance criteria" in src
    assert "## 7. Forbidden surfaces" in src
    assert "## 8. Files added at Stage 29.5.6" in src
    assert "## 9. Deferred after Stage 29.5.6" in src
    assert "## 10. Operator runbook" in src
    assert "## 11. Stage 29.5.6 schema versions" in src


def test_section_5_names_every_stage_29_3_mode() -> None:
    src = _read()
    for token in (
        "READINESS_ONLY",
        "CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY",
        "ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN",
    ):
        assert token in src, (
            f"Stage 29.5.6 runbook must name Stage 29.3 mode "
            f"{token!r} in the behavior matrix"
        )


def test_section_5_names_every_outcome_branch() -> None:
    src = _read()
    for phrase in (
        "Stage 28.9 body + ",
        "skip",
        "unchanged Stage 28.9 body",
    ):
        assert phrase in src, (
            f"Stage 29.5.6 runbook must describe outcome "
            f"branch {phrase!r}"
        )


def test_stage_29_5_5_production_untouched_pinned() -> None:
    src = _read()
    assert "Stage 29.5.5" in src
    lower = src.lower()
    assert (
        "untouched" in lower or "unchanged" in lower
    )


def test_stage_27_production_untouched_pinned() -> None:
    src = _read()
    assert "Stage 27" in src
    assert (
        "Stage 27.5 private ping renderer" in src
        or "Stage 27 production" in src
    )


def test_stage_28_production_untouched_pinned() -> None:
    src = _read()
    assert "Stage 28" in src
    assert (
        "Stage 28.4 audited HTTP transport" in src
        or "Stage 28.9 dispatch wrapper" in src
    )


def test_stage_29_4_production_untouched_pinned() -> None:
    src = _read()
    assert "Stage 29.4" in src
    lower = src.lower()
    assert (
        "untouched" in lower or "unchanged" in lower
    )


def test_opt_in_phrasing_present() -> None:
    src = _read()
    lower = src.lower()
    assert "opt-in" in lower or "opt in" in lower


def test_mode_3_only_phrasing_present() -> None:
    src = _read()
    assert "mode-3-only" in _normalize_whitespace(src).lower() or (
        "mode-3" in _normalize_whitespace(src).lower()
        and "only" in _normalize_whitespace(src).lower()
    )


def test_byte_equivalent_default_promise_present() -> None:
    src = _read()
    lower = src.lower()
    assert (
        "byte-equivalent" in lower or "byte equivalent" in lower
    ), (
        "Stage 29.5.6 runbook must promise byte-equivalent "
        "default behavior"
    )


def test_combined_content_cap_pin_present() -> None:
    src = _read()
    assert "1900" in src, (
        "Stage 29.5.6 runbook must pin the 1900-character "
        "combined-content cap"
    )


def test_no_truncation_pin_present() -> None:
    src = _read()
    lower = src.lower()
    assert (
        "skipping injection" in lower
        or "skip the append" in lower
        or "never truncate" in lower
    ), (
        "Stage 29.5.6 runbook must pin the skip-on-overflow "
        "(never truncate) discipline"
    )


def test_compact_fallback_described_in_runbook() -> None:
    """Stage 29.5.6 runbook must describe the deterministic
    compact migration-context fallback that the injector builds
    from already-revalidated closed-set / display fields when
    the full rendered block would exceed the 1900-char
    combined-body cap.
    """
    src = _read()
    lower = src.lower()
    assert "compact" in lower, (
        "Stage 29.5.6 runbook must describe the compact "
        "migration-context fallback"
    )
    assert "compact migration-context block" in lower or (
        "compact migration context block" in lower
    )
    # The compact block is built from already-revalidated
    # closed-set / display fields.
    assert (
        "already-revalidated closed-set" in lower
        or "already-revalidated closed-set / display" in lower
    )


def test_full_first_compact_second_described_in_runbook() -> None:
    """Stage 29.5.6 runbook must describe the injector's
    attempt order: full rendered ``body_text`` first, compact
    fallback second.
    """
    src = _read()
    lower = src.lower()
    # Full block first.
    assert (
        "tries the full" in lower
        or "tries to append the full" in lower
        or "attempts the full" in lower
        or "attempt 1 (full)" in lower
    ), (
        "Stage 29.5.6 runbook must say the injector tries / "
        "attempts the full rendered block FIRST"
    )
    # Compact block second.
    assert (
        "falls back to a deterministic compact" in lower
        or "attempt 2 (compact" in lower
        or "compact fallback" in lower
    ), (
        "Stage 29.5.6 runbook must say the injector falls "
        "back to the compact block SECOND"
    )


def test_skip_only_if_compact_overflows_described_in_runbook() -> None:
    """Stage 29.5.6 runbook must say the injector skips only
    when the compact append would ALSO overflow the cap (not
    on every overflow).
    """
    src = _read()
    lower = src.lower()
    assert (
        "skips the append entirely only when the compact "
        "append would also overflow" in lower
        or "skip only if compact" in lower
        or "compact > 1900" in lower
        or "compact append > 1900" in lower
        or "compact > 1900 chars" in lower
    ), (
        "Stage 29.5.6 runbook must pin the skip-only-when-"
        "compact-also-overflows discipline"
    )


def test_callable_send_one_audited_post_guard_described_in_runbook() -> None:
    """Stage 29.5.6 runbook must describe the Stage 29.3
    conformance gate on the wrapped transport candidate: the
    candidate replaces the original transport only when
    ``callable(getattr(candidate, "send_one_audited_post",
    None))`` is true; a non-conforming candidate preserves the
    original transport.
    """
    src = _read()
    assert (
        'callable(getattr(candidate, "send_one_audited_post"'
        in src
    ), (
        "Stage 29.5.6 runbook must describe the "
        "callable(getattr(candidate, 'send_one_audited_post', "
        "None)) conformance gate"
    )
    lower = src.lower()
    assert "non-conforming candidate" in lower or (
        "non-conforming" in lower
    )


def test_compact_block_field_layout_pinned_in_runbook() -> None:
    """Stage 29.5.6 runbook must pin the deterministic compact
    migration-context block layout so the surface stays
    auditable. Every line label MUST appear verbatim in the
    runbook prose.
    """
    src = _read()
    for label_line in (
        "[MIGRATION CONTEXT]",
        "status: <migration_evidence_status_display>",
        "evidence: <migration_evidence_source_trust_display>",
        "ath_context: <post_migration_ath_verified_display>",
        "filter_enforcement_status: NOT_ACTIVE_STAGE_29_PENDING",
        "informational_only: true",
        "not_a_trading_verdict: true",
    ):
        assert label_line in src, (
            f"Stage 29.5.6 runbook must pin the compact block "
            f"line {label_line!r}"
        )


def test_copied_payload_pin_present() -> None:
    src = _read()
    lower = src.lower()
    assert (
        "copied payload" in lower
        or "copy of" in lower
        or "copy(" in lower
        or "fresh `dict(payload)` copy" in lower
        or "copy " in lower
    )


def test_acceptance_criteria_a_through_r_named() -> None:
    """Stage 29.5.6 ships acceptance criteria A through R; the
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
            f"Stage 29.5.6 runbook must name acceptance "
            f"criterion {letter!r}"
        )


def test_injector_schema_version_pinned_in_runbook() -> None:
    src = _read()
    assert (
        "stage29_5_6_v0_private_discord_body_injector" in src
    )


def test_stage_29_3_zero_stage_29_5_imports_pinned() -> None:
    src = _read()
    lower = src.lower()
    assert "stage 29.3 production" in lower
    assert (
        "zero `stage29_5" in lower
        or "zero stage29_5" in lower
    )


def test_stage_29_6_deferred_pinned() -> None:
    src = _read()
    assert "Stage 29.6" in src


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
            f"Stage 29.5.6 runbook must not carry URL host "
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
            f"Stage 29.5.6 runbook must not carry raw-secret-"
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
        "Stage 29.5.6 runbook must not carry the "
        "'Phoenix_Bot' substring"
    )


def test_no_stage_29_6_plus_basenames_pinned_in_repo() -> None:
    """Stage 29.5.6 must not introduce any Stage 29.6+ basename
    under PHX2/stage29/. The Stage 29.5.6 spec lock blocks
    Stage 29.6 implementation until separately authorized.
    """
    stage29_root: Path = PHX2_ROOT / "stage29"
    forbidden_basename_prefixes = (
        "stage29_6_",
        "stage_29_6_",
    )
    for entry in stage29_root.iterdir():
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        for prefix in forbidden_basename_prefixes:
            assert not entry.name.startswith(prefix), (
                f"Stage 29.5.6 must not introduce Stage 29.6+ "
                f"basename {entry.name!r} under PHX2/stage29/"
            )
