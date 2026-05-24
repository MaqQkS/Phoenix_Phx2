"""Stage 28.8 closure-audit tests.

Pins:

  * ``PHX2/stage28/STAGE_28_CLOSURE_AUDIT.md`` exists.
  * The closure audit carries the canonical Stage 28 scope
    sentence, the Stage 28.8 closure-only declaration, the
    substage inventory (28.0 -> 28.8), the per-substage commit
    SHAs for 28.0 -> 28.7, the test-gate-proof placeholders,
    the reliability surface evidence, the smoke-proof / live-
    smoke status, the scope exclusions, the known limitations,
    the closure verdict, and the tag instruction.
  * The closure audit does NOT claim a ``stage-28-closed`` tag
    was created.
  * The closure audit carries no URL host literal and no raw
    secret-looking value.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE28_ROOT: Path = PHX2_ROOT / "stage28"
CLOSURE_AUDIT_PATH: Path = STAGE28_ROOT / "STAGE_28_CLOSURE_AUDIT.md"


def _audit_text() -> str:
    return CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Doc exists
# ---------------------------------------------------------------------------


def test_closure_audit_doc_exists():
    assert CLOSURE_AUDIT_PATH.is_file(), (
        f"Stage 28.8 requires the closure audit doc "
        f"{CLOSURE_AUDIT_PATH}"
    )


def test_closure_audit_title_is_locked():
    text = _audit_text()
    assert "PHX2 Stage 28.8 Closure Audit" in text


# ---------------------------------------------------------------------------
# 2. Canonical Stage 28 scope sentence + Stage 28.8 closure-only
#    declaration
# ---------------------------------------------------------------------------


def test_closure_audit_opens_with_scope_statement():
    normalized = _normalized_whitespace(_audit_text())
    expected_scope = (
        "Stage 28 is private live runner reliability hardening."
    )
    assert expected_scope in normalized
    expected_closure_only = (
        "Stage 28.8 is a closure-only pass. It records evidence "
        "and hands approved enforcement / live gating to Stage "
        "29. It adds no runtime feature."
    )
    assert expected_closure_only in normalized


def test_closure_audit_mission_summary_pins_phrases():
    normalized = _normalized_whitespace(_audit_text())
    for phrase in (
        (
            "Stage 28 made the private live runner reliable "
            "enough for controlled private sessions."
        ),
        "Stage 28 does not implement Stage 29 enforcement.",
        "Stage 28 does not broaden audience / distribution.",
    ):
        assert phrase in normalized, (
            f"closure audit missing mission phrase {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 3. Substage inventory complete
# ---------------------------------------------------------------------------


_EXPECTED_SUBSTAGE_PHRASES: tuple[str, ...] = (
    "28.0 spec lock / reliability charter",
    "28.1 provider-neutral config wrapper",
    "28.2 restart-safe dispatch ledger",
    "28.3a failure classification contracts",
    "28.3b bounded retry policy contracts",
    "28.4 audited private Discord HTTP transport",
    "28.5 heartbeat / health snapshot / CLI status artifacts",
    "28.6 bounded private session runner",
    (
        "28.7 longer-session smoke harness + controlled live "
        "smoke runbook"
    ),
    "28.8 closure audit + Stage 29 handoff",
)


@pytest.mark.parametrize("phrase", _EXPECTED_SUBSTAGE_PHRASES)
def test_closure_audit_lists_each_substage(phrase):
    normalized = _normalized_whitespace(_audit_text())
    assert phrase in normalized, (
        f"closure audit missing substage phrase {phrase!r}"
    )


# ---------------------------------------------------------------------------
# 4. Commit inventory pins each Stage 28 SHA
# ---------------------------------------------------------------------------


_EXPECTED_COMMIT_SHAS: tuple[tuple[str, str], ...] = (
    ("28.0", "9f94c98b3116cfe141f8835c7e9e5da5ecfb4413"),
    ("28.1", "2300678561de94230549eadabb9445814cdb9d96"),
    ("28.2", "5a91334c45d8574f480600fd9c5a8d42498f9438"),
    ("28.3a", "2d942636a1d42ec651b1115ede447e19a89f3049"),
    ("28.3b", "c6271d7f14f160e4cf5517e6091b0fbe205226df"),
    ("28.4", "0a05b92b582334932906a2cba5bbc65bf991168c"),
    ("28.5", "bd923482e990021d69b368b3ca79d32a786ec56b"),
    ("28.6", "36d44b551272c3c257da761c27c3196e6889e177"),
    ("28.7", "ea9e741bd62bf8b5d2dcd8acd7d2cd61dc979c86"),
)


@pytest.mark.parametrize(
    "label,sha",
    _EXPECTED_COMMIT_SHAS,
)
def test_closure_audit_lists_each_commit_sha(label, sha):
    text = _audit_text()
    assert label in text, (
        f"closure audit missing substage label {label!r}"
    )
    assert sha in text, (
        f"closure audit missing commit SHA {sha!r} for "
        f"substage {label!r}"
    )


def test_closure_audit_uses_28_8_sha_placeholder():
    """Stage 28.8 implementation does not know its own commit
    SHA. The audit must carry the locked placeholder so the
    operator records the actual SHA after commit.
    """
    text = _audit_text()
    assert "TO_BE_FILLED_BY_COMMIT_REPORT" in text


# ---------------------------------------------------------------------------
# 5. Test-gate-proof placeholders
# ---------------------------------------------------------------------------


_EXPECTED_TEST_GATE_PROOF_LABELS: tuple[str, ...] = (
    "Stage 28 full suite",
    "Stage 27 regression",
    "Stage 25.7 + Stage 26.7 closure audits",
    "Stage 28.8 focused tests",
)


@pytest.mark.parametrize(
    "label", _EXPECTED_TEST_GATE_PROOF_LABELS
)
def test_closure_audit_test_gate_proof_label_present(label):
    text = _audit_text()
    assert label in text, (
        f"closure audit missing test-gate-proof label "
        f"{label!r}"
    )


def test_closure_audit_test_gate_proof_uses_placeholder():
    text = _audit_text()
    assert "TO_BE_FILLED" in text


# ---------------------------------------------------------------------------
# 6. Reliability surface evidence
# ---------------------------------------------------------------------------


_RELIABILITY_SURFACE_PHRASES: tuple[str, ...] = (
    "provider-neutral readiness wrapper",
    "restart-safe dispatch ledger",
    "failure classification contracts",
    "bounded retry policy contracts",
    "audited private Discord HTTP transport",
    (
        "heartbeat / health snapshot / final summary / CLI "
        "status artifacts"
    ),
    "bounded private session runner",
    "longer-session offline smoke harness",
    "controlled live smoke runbook",
)


@pytest.mark.parametrize("phrase", _RELIABILITY_SURFACE_PHRASES)
def test_closure_audit_pins_each_reliability_surface(phrase):
    normalized = _normalized_whitespace(_audit_text())
    assert phrase in normalized, (
        f"closure audit missing reliability surface phrase "
        f"{phrase!r}"
    )


# ---------------------------------------------------------------------------
# 7. Smoke proof / live-smoke status
# ---------------------------------------------------------------------------


def test_closure_audit_smoke_status_references_offline_harness():
    text = _audit_text()
    assert "longer_session_smoke_harness.py" in text
    assert "test_stage_28_7_longer_session_smoke_harness.py" in text


def test_closure_audit_smoke_status_references_runbook():
    text = _audit_text()
    assert "STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md" in text


def test_closure_audit_does_not_claim_automatic_live_smoke():
    normalized = _normalized_whitespace(_audit_text())
    assert (
        "Stage 28.8 does not claim an automatic live smoke was "
        "run."
    ) in normalized
    assert "No live smoke automation is added in 28.8." in (
        normalized
    )


# ---------------------------------------------------------------------------
# 8. Scope exclusions
# ---------------------------------------------------------------------------


_SCOPE_EXCLUSION_PHRASES: tuple[str, ...] = (
    "Stage 29 implementation",
    "enforcement",
    "public routing",
    "subscriber routing",
    "paid tiers",
    "Telegram",
    "X/social",
    "automated trading",
    "wallet/private-key/signer logic",
    "position sizing",
    "trade execution",
    "dashboard/control surface",
    "daemon/systemd/watchdog",
    "live smoke automation",
)


@pytest.mark.parametrize("phrase", _SCOPE_EXCLUSION_PHRASES)
def test_closure_audit_lists_each_scope_exclusion(phrase):
    text = _audit_text()
    assert phrase in text, (
        f"closure audit missing scope exclusion {phrase!r}"
    )


def test_closure_audit_says_stage_28_8_does_not_add():
    text = _audit_text()
    assert "Stage 28.8 does not add" in text


# ---------------------------------------------------------------------------
# 9. Known limitations
# ---------------------------------------------------------------------------


_KNOWN_LIMITATION_PHRASES: tuple[str, ...] = (
    "Stage 28 is private-operator reliability only.",
    (
        "Stage 29 must decide approved enforcement / live "
        "gating"
    ),
    "Stage 30+ owns the X / social sidecar.",
    "Dashboard / read-only analysis UI remains separate",
    "Public / subscriber distribution remains separate",
    "Automated trading / wallet / signer logic remains out of",
)


@pytest.mark.parametrize("phrase", _KNOWN_LIMITATION_PHRASES)
def test_closure_audit_lists_each_known_limitation(phrase):
    normalized = _normalized_whitespace(_audit_text())
    assert phrase in normalized, (
        f"closure audit missing known-limitation phrase "
        f"{phrase!r}"
    )


# ---------------------------------------------------------------------------
# 10. Closure verdict + tag instruction
# ---------------------------------------------------------------------------


def test_closure_audit_says_ready_for_operator_review():
    normalized = _normalized_whitespace(_audit_text())
    assert (
        "Stage 28 is ready for operator review once the Stage "
        "28.8 tests pass."
    ) in normalized


def test_closure_audit_tag_instruction_requires_explicit_authorization():
    text = _audit_text()
    assert (
        "The `stage-28-closed` tag must only be created after"
    ) in text
    assert "explicit operator authorization" in text


def test_closure_audit_says_28_8_must_not_create_tag():
    normalized = _normalized_whitespace(_audit_text())
    assert (
        "Stage 28.8 implementation must not create that tag."
    ) in normalized


def test_closure_audit_does_not_claim_tag_was_created():
    """Stage 28.8 closure audit must NEVER claim the
    ``stage-28-closed`` tag was created. The audit ships before
    the tag and the operator creates the tag explicitly later.
    """
    normalized = _normalized_whitespace(_audit_text()).lower()
    forbidden_claims = (
        "stage-28-closed tag was created",
        "stage-28-closed tag has been created",
        "stage-28-closed tag exists",
        "created the stage-28-closed tag",
        "the stage-28-closed tag is created",
    )
    for claim in forbidden_claims:
        assert claim not in normalized, (
            f"closure audit must not claim {claim!r}"
        )


# ---------------------------------------------------------------------------
# 11. Doc carries no URL / raw-secret literal
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
def test_closure_audit_has_no_url_literal(needle):
    text = _audit_text()
    assert needle not in text, (
        f"closure audit must not contain URL literal {needle!r}"
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
def test_closure_audit_has_no_secret_looking_raw_value(pattern):
    assert not re.search(pattern, _audit_text())


_FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES: tuple[str, ...] = (
    "DISCORD_WEBHOOK_URL=",
    "HELIUS_API_KEY=",
    "HELIUS_RPC_URL=",
    "HELIUS_GRPC_ENDPOINT=",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_RAW_SECRET_ASSIGNMENT_NEEDLES
)
def test_closure_audit_has_no_raw_secret_assignment_name(needle):
    text = _audit_text()
    assert needle not in text
