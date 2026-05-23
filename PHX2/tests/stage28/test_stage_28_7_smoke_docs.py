"""Stage 28.7 operator-doc tests.

Pins:

  * The Stage 28.7 longer-session smoke checklist exists.
  * The Stage 28.7 controlled live smoke runbook exists.
  * The checklist names the offline-only nature of Stage 28.7
    production code and the redaction-scan requirement.
  * The runbook requires explicit operator authorization, private
    operator webhook only, max sends == 1, out-of-repo artifact
    directory, redaction scan, and forbids
    public/subscriber/paid/Telegram/X-social/enforcement/
    automated-trading scope.
  * Both docs say Stage 28.7 is NOT Stage 28 closure and NOT
    Stage 29 enforcement; Stage 28.8 is the closure substage.
  * Both docs carry no URL literal, no webhook host literal, no
    raw secret-looking value.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
CHECKLIST_PATH: Path = (
    STAGE28_ROOT / "STAGE_28_LONGER_SESSION_SMOKE_CHECKLIST.md"
)
RUNBOOK_PATH: Path = (
    STAGE28_ROOT / "STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md"
)


def _checklist_text() -> str:
    return CHECKLIST_PATH.read_text(encoding="utf-8")


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Doc files exist
# ---------------------------------------------------------------------------


def test_checklist_doc_exists():
    assert CHECKLIST_PATH.is_file(), (
        f"Stage 28.7 requires {CHECKLIST_PATH}"
    )


def test_controlled_live_smoke_runbook_exists():
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 28.7 requires {RUNBOOK_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Checklist content pins
# ---------------------------------------------------------------------------


_CHECKLIST_REQUIRED_PHRASES: tuple[str, ...] = (
    "Longer-Session Smoke Checklist",
    "offline-only",
    "Stage 28.7",
    "redaction",
    "redaction scan",
    "smoke_status",
    "live_send_attempted",
    "live_send_count",
    "duplicate_suppressed",
    "suppressed_count",
    "heartbeat_count",
    "schema_version",
    "stage28_7_longer_session_smoke_harness_v0",
    "out-of-repo",
)


@pytest.mark.parametrize(
    "phrase", _CHECKLIST_REQUIRED_PHRASES
)
def test_checklist_pins_required_phrase(phrase):
    text = _checklist_text()
    assert phrase in text, (
        f"checklist missing required phrase {phrase!r}"
    )


def test_checklist_pins_no_stage_28_closed_tag():
    normalized = _normalized_whitespace(_checklist_text()).lower()
    assert "stage-28-closed" in normalized
    assert "must not create" in normalized or (
        "must not create the" in normalized
    )


def test_checklist_says_closure_is_stage_28_8():
    text = _checklist_text()
    assert "Stage 28.8" in text
    normalized = _normalized_whitespace(text).lower()
    assert "closure audit" in normalized
    assert "stage 29 handoff" in normalized


def test_checklist_lists_forbidden_routing_surfaces():
    text = _checklist_text()
    for needle in (
        "subscriber router",
        "paid tier router",
        "Telegram",
        "X / social",
        "enforcement gate",
        "automated trading",
        "wallet",
        "private-key",
        "dashboard",
        "watchdog",
    ):
        assert needle in text, (
            f"checklist missing forbidden surface phrase "
            f"{needle!r}"
        )


def test_checklist_forbids_buy_sell_language():
    text = _checklist_text()
    # The doc names the forbidden trading verdict language so a
    # reader sees the explicit denylist.
    for needle in (
        "BUY",
        "SELL",
        "APPROVED",
        "GATE",
        "BLOCK",
        "EXECUTE",
        "POSITION-SIZE",
        "AUTO-TRADE",
        "ENFORCEMENT",
    ):
        assert needle in text, (
            f"checklist missing forbidden trading verdict token "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# 3. Runbook content pins
# ---------------------------------------------------------------------------


_RUNBOOK_REQUIRED_PHRASES: tuple[str, ...] = (
    "Controlled Live Smoke Runbook",
    "Stage 28.7",
    "Explicit operator authorization",
    "private operator webhook",
    "exactly ONE",
    "out-of-repo",
    "redaction",
    "controlled live smoke",
)


@pytest.mark.parametrize(
    "phrase", _RUNBOOK_REQUIRED_PHRASES
)
def test_runbook_pins_required_phrase(phrase):
    text = _runbook_text()
    assert phrase in text, (
        f"runbook missing required phrase {phrase!r}"
    )


def test_runbook_requires_max_sends_equals_one():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "max_live_sends" in normalized
    assert (
        "exactly one" in normalized
        or "exactly 1" in normalized
        or "locked to `1`" in normalized
    )


def test_runbook_requires_operator_live_request_true():
    text = _runbook_text()
    assert "operator_live_request=True" in text
    assert "smoke_dispatch_request=True" in text


def test_runbook_requires_private_webhook_only():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "private operator webhook" in normalized
    assert "no public" in normalized or "public, subscriber" in normalized


def test_runbook_requires_out_of_repo_artifact_dir():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "out-of-repo" in normalized or "outside the tracked" in normalized
    assert "output_dir" in normalized


def test_runbook_requires_redaction_scan():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "redaction scan" in normalized or (
        "scan_stage28_7_artifacts_for_redaction" in normalized
    )


def test_runbook_forbids_public_subscriber_paid_routing():
    text = _runbook_text()
    for needle in (
        "public router",
        "subscriber router",
        "paid tier router",
    ):
        assert needle in text, (
            f"runbook missing forbidden routing phrase {needle!r}"
        )


def test_runbook_forbids_telegram_x_social():
    text = _runbook_text()
    assert "Telegram" in text
    assert "X / social" in text


def test_runbook_forbids_enforcement_and_automated_trading():
    text = _runbook_text()
    assert "Stage 29 enforcement" in text
    assert "automated trading" in text
    assert "wallet" in text
    assert "signer" in text


def test_runbook_says_no_stage_28_closed_tag_in_28_7():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "stage-28-closed" in normalized
    assert "stage 28.7 does not authorize" in normalized or (
        "must not create the" in normalized
    )


def test_runbook_says_28_8_is_closure_plus_stage_29_handoff():
    text = _runbook_text()
    assert "Stage 28.8" in text
    normalized = _normalized_whitespace(text).lower()
    assert "closure audit" in normalized
    assert "stage 29 handoff" in normalized


def test_runbook_requires_final_report_with_run_smoke_ids():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "run_id" in normalized
    assert "session_id" in normalized
    assert "smoke_id" in normalized
    assert "send count" in normalized
    assert "artifact paths" in normalized
    assert "redaction_status" in normalized


def test_runbook_says_stage_28_7_production_is_offline_only():
    normalized = _normalized_whitespace(_runbook_text()).lower()
    assert "production code is offline-only" in normalized or (
        "production harness is offline-only" in normalized
    )


# ---------------------------------------------------------------------------
# 4. Stage 28.8+ surfaces are explicitly excluded
# ---------------------------------------------------------------------------


def test_runbook_pins_stage_28_7_is_not_stage_28_8_closure():
    text = _runbook_text()
    assert "Stage 28.7 is not Stage 28.8 closure" in text or (
        "Stage 28.7 is NOT Stage 28.8 closure" in text
    ) or (
        # accept the lower-case prose form used in the runbook
        "Stage 28.7 is not Stage 28.8" in text
    )


def test_runbook_pins_stage_28_7_is_not_stage_29_enforcement():
    text = _runbook_text()
    assert "Stage 28.7 is not Stage 29 enforcement" in text


def test_runbook_pins_stage_28_7_is_not_stage_30_x_social():
    text = _runbook_text()
    assert "Stage 28.7 is not Stage 30+ X / social" in text


# ---------------------------------------------------------------------------
# 5. Docs carry no URL / raw-secret literal
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discordapp" + ".com",
    "hooks" + ".slack.com",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_URL_LITERAL_SUBSTRINGS
)
def test_checklist_has_no_url_literal(needle):
    text = _checklist_text()
    assert needle not in text, (
        f"checklist must not contain URL literal {needle!r}"
    )


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_URL_LITERAL_SUBSTRINGS
)
def test_runbook_has_no_url_literal(needle):
    text = _runbook_text()
    assert needle not in text, (
        f"runbook must not contain URL literal {needle!r}"
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
def test_checklist_has_no_secret_looking_raw_value(pattern):
    assert not re.search(pattern, _checklist_text())


@pytest.mark.parametrize(
    "pattern", _FORBIDDEN_SECRET_LOOKING_PATTERNS
)
def test_runbook_has_no_secret_looking_raw_value(pattern):
    assert not re.search(pattern, _runbook_text())


_FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES: tuple[str, ...] = (
    "DISCORD_WEBHOOK_URL=",
    "HELIUS_API_KEY=",
    "HELIUS_RPC_URL=",
    "HELIUS_GRPC_ENDPOINT=",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES
)
def test_checklist_has_no_raw_secret_assignment_name(needle):
    text = _checklist_text()
    assert needle not in text


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES
)
def test_runbook_has_no_raw_secret_assignment_name(needle):
    text = _runbook_text()
    assert needle not in text
