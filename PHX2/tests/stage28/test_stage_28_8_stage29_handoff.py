"""Stage 28.8 Stage 29 handoff-doc tests.

Pins:

  * ``PHX2/stage28/STAGE_29_HANDOFF.md`` exists.
  * The handoff doc declares the Stage 29 mission as approved
    enforcement / live gating for private pings.
  * Stage 29 starts with 29.0 spec lock / enforcement charter.
  * The handoff separates observe-only / shadow / enforced gate
    modes.
  * The handoff includes the proposed Stage 29 outline
    (29.0 -> 29.7).
  * The handoff explicitly forbids public routing, subscriber
    routing, paid tiers, Telegram, X / social, automated
    trading, wallet / private-key / signer logic, trade
    execution, position sizing, and public dashboard / control
    server.
  * Stage 30+ owns the X / social sidecar.
  * The handoff doc carries no URL host literal and no raw
    secret-looking value.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
HANDOFF_PATH: Path = STAGE28_ROOT / "STAGE_29_HANDOFF.md"


def _handoff_text() -> str:
    return HANDOFF_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Doc exists
# ---------------------------------------------------------------------------


def test_stage29_handoff_doc_exists():
    assert HANDOFF_PATH.is_file(), (
        f"Stage 28.8 requires the Stage 29 handoff doc "
        f"{HANDOFF_PATH}"
    )


def test_handoff_title_is_locked():
    text = _handoff_text()
    assert "PHX2 Stage 29 Handoff" in text


# ---------------------------------------------------------------------------
# 2. Stage 29 mission
# ---------------------------------------------------------------------------


def test_handoff_pins_stage_29_mission():
    normalized = _normalized_whitespace(_handoff_text())
    assert (
        "Stage 29 is **approved enforcement / live gating for "
        "private pings**."
    ) in normalized


def test_handoff_says_no_audience_broadening():
    normalized = _normalized_whitespace(_handoff_text())
    assert "Stage 29 does not broaden audience" in normalized


# ---------------------------------------------------------------------------
# 3. Inputs from Stage 28
# ---------------------------------------------------------------------------


_STAGE_28_INPUT_PHRASES: tuple[str, ...] = (
    "bounded private session runner (Stage 28.6)",
    "restart-safe dispatch ledger (Stage 28.2)",
    "failure classifier (Stage 28.3a)",
    "bounded retry policy (Stage 28.3b)",
    "audited private Discord transport (Stage 28.4)",
    (
        "heartbeat / health snapshot / final-summary / CLI "
        "status artifacts (Stage 28.5)"
    ),
    (
        "longer-session offline smoke harness and the "
        "controlled live smoke runbook (Stage 28.7)"
    ),
)


@pytest.mark.parametrize("phrase", _STAGE_28_INPUT_PHRASES)
def test_handoff_lists_each_stage_28_input(phrase):
    normalized = _normalized_whitespace(_handoff_text())
    assert phrase in normalized, (
        f"handoff missing Stage 28 input phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 4. Upstream evidence from Stage 26
# ---------------------------------------------------------------------------


_STAGE_26_EVIDENCE_PHRASES: tuple[str, ...] = (
    "policy candidate artifacts (Stage 26.5)",
    "threshold candidates (Stage 26.4)",
    "operator review packets (Stage 26.6)",
    "approved / reviewed policies only",
)


@pytest.mark.parametrize("phrase", _STAGE_26_EVIDENCE_PHRASES)
def test_handoff_lists_each_stage_26_evidence(phrase):
    normalized = _normalized_whitespace(_handoff_text())
    assert phrase in normalized, (
        f"handoff missing Stage 26 evidence phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 5. Required starting point: Stage 29.0 spec lock / enforcement
#    charter only
# ---------------------------------------------------------------------------


def test_handoff_requires_29_0_spec_lock_only():
    normalized = _normalized_whitespace(_handoff_text())
    assert (
        "Stage 29.0 must be **spec lock / enforcement charter "
        "only**."
    ) in normalized


def test_handoff_29_0_must_not_ship_implementation():
    normalized = _normalized_whitespace(_handoff_text())
    assert (
        "Stage 29.0 must NOT ship a runtime policy reader"
    ) in normalized


# ---------------------------------------------------------------------------
# 6. Observe-only vs enforced gates
# ---------------------------------------------------------------------------


_GATE_MODE_TERMS: tuple[str, ...] = (
    "observe-only",
    "shadow",
    "enforced",
)


@pytest.mark.parametrize("term", _GATE_MODE_TERMS)
def test_handoff_separates_each_gate_mode(term):
    text = _handoff_text()
    assert term in text, (
        f"handoff missing gate-mode term {term!r}"
    )


def test_handoff_says_every_enforced_gate_versioned_and_approved():
    normalized = _normalized_whitespace(_handoff_text())
    assert (
        "Every enforced gate must be **explicitly versioned "
        "and approved**."
    ) in normalized


def test_handoff_says_suppress_allow_reasons_recorded():
    normalized = _normalized_whitespace(_handoff_text())
    assert (
        "Every gate decision must carry a **closed-set "
        "suppress / allow reason**"
    ) in normalized


# ---------------------------------------------------------------------------
# 7. Proposed Stage 29 outline
# ---------------------------------------------------------------------------


_STAGE_29_OUTLINE_PHRASES: tuple[str, ...] = (
    "**29.0** spec lock / enforcement charter",
    (
        "**29.1** approved policy-candidate reader and approval "
        "evidence pinning"
    ),
    "**29.2** observe-only gate evaluator",
    "**29.3** private-runner shadow gate artifacts",
    "**29.4** enforced private dispatch gate adapter",
    (
        "**29.5** fail-closed reason codes and operator audit "
        "artifacts"
    ),
    "**29.6** controlled private enforcement smoke runbook",
    "**29.7** closure audit / Stage 30+ handoff",
)


@pytest.mark.parametrize("phrase", _STAGE_29_OUTLINE_PHRASES)
def test_handoff_pins_each_stage_29_outline_entry(phrase):
    normalized = _normalized_whitespace(_handoff_text())
    assert phrase in normalized, (
        f"handoff missing Stage 29 outline phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 8. Stage 29 must-not surfaces
# ---------------------------------------------------------------------------


_STAGE_29_MUST_NOT_PHRASES: tuple[str, ...] = (
    "public routing",
    "subscriber routing",
    "paid tiers",
    "Telegram",
    "X/social",
    "automated trading",
    "wallet/private-key/signer logic",
    "trade execution",
    "position sizing",
    "public dashboard/control server",
)


@pytest.mark.parametrize("phrase", _STAGE_29_MUST_NOT_PHRASES)
def test_handoff_lists_each_stage_29_must_not(phrase):
    text = _handoff_text()
    assert phrase in text, (
        f"handoff missing Stage 29 must-not phrase {phrase!r}"
    )


def test_handoff_explicitly_says_stage_29_must_not_include():
    text = _handoff_text()
    assert "Stage 29 must not include" in text


# ---------------------------------------------------------------------------
# 9. Stage 30+ ownership
# ---------------------------------------------------------------------------


def test_handoff_says_stage_30_owns_x_social_sidecar():
    normalized = _normalized_whitespace(_handoff_text())
    assert "Stage 30+ owns the X / social sidecar" in normalized


def test_handoff_lists_stage_30_surfaces():
    normalized = _normalized_whitespace(_handoff_text())
    for phrase in (
        "X / social sidecar",
        "provider-agnostic social event schema",
        "social boost / annotation, not the core brain",
    ):
        assert phrase in normalized, (
            f"handoff missing Stage 30+ surface {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 10. Doc carries no URL / raw-secret literal
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
def test_handoff_has_no_url_literal(needle):
    text = _handoff_text()
    assert needle not in text, (
        f"handoff must not contain URL literal {needle!r}"
    )


_FORBIDDEN_SECRET_LOOKING_PATTERNS: tuple[str, ...] = (
    r"Authorization:\s*\S+",
    r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}",
    r"\bsk-[A-Za-z0-9_-]{8,}\b",
    r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b",
)


@pytest.mark.parametrize(
    "pattern", _FORBIDDEN_SECRET_LOOKING_PATTERNS
)
def test_handoff_has_no_secret_looking_raw_value(pattern):
    assert not re.search(pattern, _handoff_text())


_FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES: tuple[str, ...] = (
    "DISCORD_WEBHOOK_URL=",
    "HELIUS_API_KEY=",
    "HELIUS_RPC_URL=",
    "HELIUS_GRPC_ENDPOINT=",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES
)
def test_handoff_has_no_raw_secret_assignment_name(needle):
    text = _handoff_text()
    assert needle not in text
