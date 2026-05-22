"""Stage 27.7a operator runbook + dry-run smoke checklist + manifest tests.

Pins:

  * ``PHX2/stage27/STAGE_27_OPERATOR_RUNBOOK.md`` exists and
    carries the dry-run-only status, the no-Discord posture, the
    smoke run instructions, the expected artifact shape, the
    expected smoke summary counters, the pair-aware behavior
    table (SOL / USDC / UNKNOWN / DISAGREE), the env-read boundary
    pin, the measurement warning notes, and the Stage 27.7b /
    28 / 29 deferral language.
  * ``PHX2/stage27/STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md`` exists
    and carries the pre/post checklist (untracked paths, no tag,
    no sender, no live API, env-read boundary, output root,
    redaction, no enforcement language, pair-aware verdicts).
  * ``PHX2/stage27/stage27_7_manifest.py`` exposes the locked
    Stage 27.7a production / test basename inventories and schema
    axes.
  * Neither markdown document carries a URL host literal, a
    webhook URL literal, or a raw secret canary.
"""

from __future__ import annotations

from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE27_ROOT: Path = PHX2_ROOT / "stage27"


RUNBOOK_PATH: Path = STAGE27_ROOT / "STAGE_27_OPERATOR_RUNBOOK.md"
CHECKLIST_PATH: Path = (
    STAGE27_ROOT / "STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md"
)


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _checklist_text() -> str:
    return CHECKLIST_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# Document existence
# ---------------------------------------------------------------------------


def test_operator_runbook_doc_exists():
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 27.7a requires {RUNBOOK_PATH}"
    )


def test_dry_run_smoke_checklist_doc_exists():
    assert CHECKLIST_PATH.is_file(), (
        f"Stage 27.7a requires {CHECKLIST_PATH}"
    )


# ---------------------------------------------------------------------------
# Runbook: required positive phrases
# ---------------------------------------------------------------------------


_RUNBOOK_REQUIRED_PHRASES: tuple[str, ...] = (
    # Stage scope context
    "Stage 27.7a",
    "operator runbook",
    "dry-run smoke",
    # What Stage 27 does
    "private live PHX1-parity tradeable ping runner",
    "Stage 27.0",
    "Stage 27.1",
    "Stage 27.2",
    "Stage 27.3",
    "Stage 27.4",
    "Stage 27.5",
    "Stage 27.6",
    # Dry-run-only status
    "dry-run only",
    # How to run smoke
    "run_dry_run_smoke",
    "build_default_smoke_events",
    "build_default_smoke_sources",
    # Artifact output shape
    "ping_<ping_id>_payload.json",
    "ping_<ping_id>_provenance.json",
    "run_<run_id>_summary.json",
    # Smoke summary counters
    "smoke_id",
    "events_seen",
    "candidates_assembled",
    "pings_rendered",
    "artifacts_written",
    "duplicates_skipped",
    "unknown_suppressed",
    "disagree_suppressed",
    "usdc_observe_only_count",
    "errors",
    "output_root",
    "schema_version",
    # Pair-aware behavior
    "EXISTING_SOL_LANE",
    "USDC_OBSERVE_ONLY",
    "UNKNOWN_PAIR_OBSERVE_ONLY",
    "DISAGREE_PAIR_OBSERVE_ONLY",
    "LIVE_SUPPRESS_UNKNOWN",
    "LIVE_SUPPRESS_DISAGREE",
    # Verify no Discord send / no real API keys
    "no Discord send",
    "no real API keys",
    "live_secrets_readiness.py",
    # Measurement warnings
    "RENDERED_WITH_WARNINGS",
    # Stage 27.7b deferral
    "Stage 27.7b",
    # Stage 28 / 29 deferral
    "Stage 28",
    "Stage 29",
    # Closure conditions
    "closure conditions",
    # Tag is operator-only
    "operator-only",
)


@pytest.mark.parametrize("phrase", _RUNBOOK_REQUIRED_PHRASES)
def test_runbook_contains_required_phrase(phrase):
    text = _runbook_text()
    assert phrase in text, (
        f"operator runbook missing required phrase {phrase!r}"
    )


def test_runbook_states_no_discord_sending_in_27_7a():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "stage 27.7a" in normalized
    assert (
        "no discord send" in normalized
        or "must not" in normalized
    )
    # Stage 27.7b is where the live smoke lives, not 27.7a.
    assert (
        "stage 27.7b" in normalized
        and "controlled live smoke" in normalized
    )


def test_runbook_documents_dry_run_only_status():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "dry-run only" in normalized
    # The runbook must document the LIVE_ALLOWED fail-closed
    # behavior — either via the literal "fail-close" / "fail
    # closes" or via the "refuses ... LIVE" phrasing.
    has_fail_close_language = (
        "live_allowed" in normalized
        and (
            "fail-close" in normalized
            or "fail closes" in normalized
            or "fail-closes" in normalized
        )
    )
    has_refuse_language = (
        "refuse" in normalized and "live" in normalized
    )
    assert has_fail_close_language or has_refuse_language


def test_runbook_documents_env_read_boundary_pin():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "live_secrets_readiness.py" in normalized
    assert (
        "no new env reads" in normalized
        or "does not add a new env-read site" in normalized
    )


def test_runbook_documents_pair_aware_table():
    text = _runbook_text()
    # The table must mention every pair-aware class explicitly.
    for token in (
        "SOL",
        "USDC",
        "UNKNOWN",
        "DISAGREE",
        "EXISTING_SOL_LANE",
        "USDC_OBSERVE_ONLY",
        "UNKNOWN_PAIR_OBSERVE_ONLY",
        "DISAGREE_PAIR_OBSERVE_ONLY",
        "LIVE_ALLOWED",
        "LIVE_SUPPRESS_UNKNOWN",
        "LIVE_SUPPRESS_DISAGREE",
    ):
        assert token in text, (
            f"operator runbook missing pair-aware token {token!r}"
        )


def test_runbook_documents_stage_27_7b_handoff():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "stage 27.7b" in normalized
    assert (
        "private discord ping smoke" in normalized
        or "controlled live smoke" in normalized
    )
    assert (
        "explicit operator authorization" in normalized
        or "explicit operator argument" in normalized
        or "per-substage operator authorization" in normalized
    )


def test_runbook_documents_stage_28_hardening_handoff():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "stage 28" in normalized
    assert "hardening" in normalized


def test_runbook_documents_stage_29_enforcement_handoff():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "stage 29" in normalized
    assert (
        "approved enforcement" in normalized
        or "enforcement" in normalized
    )


# ---------------------------------------------------------------------------
# Runbook: forbidden URL / leak literal
# ---------------------------------------------------------------------------


_FORBIDDEN_DOC_URL_LITERALS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "public-api.birdeye" + ".so",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
)


@pytest.mark.parametrize(
    "doc_path", [RUNBOOK_PATH, CHECKLIST_PATH]
)
def test_doc_has_no_url_literal(doc_path):
    text = doc_path.read_text(encoding="utf-8")
    for needle in _FORBIDDEN_DOC_URL_LITERALS:
        assert needle not in text, (
            f"{doc_path.name}: forbidden URL literal {needle!r}"
        )


# ---------------------------------------------------------------------------
# Checklist: required positive phrases
# ---------------------------------------------------------------------------


_CHECKLIST_REQUIRED_PHRASES: tuple[str, ...] = (
    "Stage 27.7a",
    "dry-run only",
    "git status",
    "stage-27",
    "No `stage-27` tag",
    "Discord sender",
    "No live provider",
    "live_secrets_readiness.py",
    "output_root",
    "redacted",
    "webhook",
    "raw payload",
    "UNKNOWN",
    "DISAGREE",
    "USDC",
    "EXISTING_SOL_LANE",
    "USDC_OBSERVE_ONLY",
    "UNKNOWN_PAIR_OBSERVE_ONLY",
    "DISAGREE_PAIR_OBSERVE_ONLY",
    "LIVE_SUPPRESS_UNKNOWN",
    "LIVE_SUPPRESS_DISAGREE",
    "BUY",
    "SELL",
    "APPROVED",
    "enforcement",
    "schema_version",
    "DRY_RUN",
)


@pytest.mark.parametrize("phrase", _CHECKLIST_REQUIRED_PHRASES)
def test_checklist_contains_required_phrase(phrase):
    text = _checklist_text()
    assert phrase in text, (
        f"dry-run smoke checklist missing required phrase "
        f"{phrase!r}"
    )


def test_checklist_includes_no_live_api_check():
    normalized = _normalized_whitespace(_checklist_text()).lower()
    assert "no live" in normalized
    assert (
        "helius" in normalized
        or "birdeye" in normalized
        or "no live provider" in normalized
    )


def test_checklist_includes_no_discord_send_check():
    normalized = _normalized_whitespace(_checklist_text()).lower()
    assert "discord send" in normalized or "discord_sender" in normalized
    assert "stage 27.7b" in normalized


def test_checklist_includes_no_env_read_check():
    normalized = _normalized_whitespace(_checklist_text()).lower()
    assert "env-read boundary" in normalized
    assert "live_secrets_readiness.py" in normalized


def test_checklist_includes_no_enforcement_language_check():
    normalized = _normalized_whitespace(_checklist_text()).lower()
    # The checklist must call out the forbidden enforcement
    # vocabulary explicitly.
    assert "no buy" in normalized
    assert "sell" in normalized
    assert "approved" in normalized
    assert "enforcement" in normalized


def test_checklist_includes_no_tag_or_push_check():
    text = _checklist_text()
    assert "stage-27" in text
    normalized = _normalized_whitespace(text).lower()
    assert "no tag was created" in normalized or (
        "no `stage-27` tag" in normalized
    )
    assert "no push occurred" in normalized or "push" in normalized


def test_checklist_includes_pair_aware_check_per_class():
    text = _checklist_text()
    # Every pair-aware class must have its expected lane / policy
    # tokens called out.
    for token in (
        "SOL",
        "USDC",
        "UNKNOWN",
        "DISAGREE",
        "EXISTING_SOL_LANE",
        "USDC_OBSERVE_ONLY",
        "UNKNOWN_PAIR_OBSERVE_ONLY",
        "DISAGREE_PAIR_OBSERVE_ONLY",
        "LIVE_SUPPRESS_UNKNOWN",
        "LIVE_SUPPRESS_DISAGREE",
    ):
        assert token in text, (
            f"checklist missing pair-aware token {token!r}"
        )


def test_checklist_includes_redaction_check():
    text = _checklist_text()
    # The checklist must require artifacts be redacted with no
    # secret / webhook URL / API key literal.
    assert "redacted" in text or "Redacted" in text
    assert "API" in text


def test_checklist_includes_smoke_summary_counters():
    text = _checklist_text()
    for field in (
        "mode",
        "events_seen",
        "pings_rendered",
        "unknown_suppressed",
        "disagree_suppressed",
        "usdc_observe_only_count",
        "duplicates_skipped",
        "schema_version",
    ):
        assert field in text, (
            f"checklist missing smoke summary field {field!r}"
        )


# ---------------------------------------------------------------------------
# Stage 27.7a manifest
# ---------------------------------------------------------------------------


def test_stage_27_7_manifest_exposes_minor_version():
    from PHX2.stage27 import stage27_7_manifest as mfst

    assert mfst.STAGE27_7A_MINOR_VERSION == "27.7a"


def test_stage_27_7_manifest_exposes_smoke_summary_schema_version():
    from PHX2.stage27 import stage27_7_manifest as mfst

    assert mfst.STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION == (
        "stage27_v0_dry_run_smoke_summary"
    )


def test_stage_27_7_manifest_lists_production_py_basenames():
    from PHX2.stage27.stage27_7_manifest import (
        STAGE27_7A_PRODUCTION_PY_BASENAMES,
    )

    assert STAGE27_7A_PRODUCTION_PY_BASENAMES == (
        "dry_run_smoke_harness.py",
        "stage27_7_manifest.py",
    )


def test_stage_27_7_manifest_lists_production_md_basenames():
    from PHX2.stage27.stage27_7_manifest import (
        STAGE27_7A_PRODUCTION_MD_BASENAMES,
    )

    assert STAGE27_7A_PRODUCTION_MD_BASENAMES == (
        "STAGE_27_OPERATOR_RUNBOOK.md",
        "STAGE_27_DRY_RUN_SMOKE_CHECKLIST.md",
    )


def test_stage_27_7_manifest_combined_basenames_are_concat():
    from PHX2.stage27.stage27_7_manifest import (
        STAGE27_7A_PRODUCTION_BASENAMES,
        STAGE27_7A_PRODUCTION_MD_BASENAMES,
        STAGE27_7A_PRODUCTION_PY_BASENAMES,
    )

    assert set(STAGE27_7A_PRODUCTION_BASENAMES) == (
        set(STAGE27_7A_PRODUCTION_PY_BASENAMES)
        | set(STAGE27_7A_PRODUCTION_MD_BASENAMES)
    )


def test_stage_27_7_manifest_lists_test_basenames():
    from PHX2.stage27.stage27_7_manifest import (
        STAGE27_7A_TEST_BASENAMES,
    )

    assert set(STAGE27_7A_TEST_BASENAMES) >= {
        "test_stage_27_7_dry_run_smoke_harness.py",
        "test_stage_27_7_operator_runbook.py",
        "test_stage_27_7_boundaries.py",
    }
