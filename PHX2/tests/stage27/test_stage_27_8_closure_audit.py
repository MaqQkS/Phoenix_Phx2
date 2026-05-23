"""Stage 27.8 closure-audit document tests.

Pins the closure audit as documentation-only proof inventory for
Stage 27, including the accepted live smoke proof, redaction proof,
test proof, git/tag posture, and scope locks. These tests do not
run live smoke and do not read secrets.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent
PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE27_ROOT: Path = PHX2_ROOT / "stage27"
CLOSURE_AUDIT_PATH: Path = STAGE27_ROOT / "STAGE_27_CLOSURE_AUDIT.md"


def _closure_audit_text() -> str:
    return CLOSURE_AUDIT_PATH.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_stage_27_closure_audit_file_exists():
    assert CLOSURE_AUDIT_PATH.is_file(), (
        f"Stage 27.8 requires {CLOSURE_AUDIT_PATH}"
    )


_STAGE_27_COMMITS: tuple[tuple[str, str, str], ...] = (
    (
        "cfaea560ea0c7679904a696e90fbc95ddcc440e9",
        "cfaea56",
        "phx2 stage 27.0: lock private live runner architecture",
    ),
    (
        "e11482d3cfcb68a68ca5d956fea0571f5f8384b5",
        "e11482d",
        "phx2 stage 27.1: operator config and live mode readiness",
    ),
    (
        "0f29f86277f55a6a847b62df7b597b5879b5dd43",
        "0f29f86",
        "phx2 stage 27.2: pair classification contracts and skeleton",
    ),
    (
        "eb22cca5db7acaf3f67d98d943c8b11bc1606dc9",
        "eb22cca",
        "phx2 stage 27.3: provider ingest composition boundary",
    ),
    (
        "fc484cb60e578f2018e0472482b972b29c09c422",
        "fc484cb",
        "phx2 stage 27.4: price migration ath context boundary",
    ),
    (
        "8a5405a59615ab4b3f3499c5898a28b541b11b3a",
        "8a5405a",
        "phx2 stage 27.5: private ping renderer and provenance artifacts",
    ),
    (
        "bde79c46188423a24e4a3bf7969c3c975cfed273",
        "bde79c4",
        "phx2 stage 27.6: bounded dry-run candidate runner",
    ),
    (
        "dbbdb6390db846a00b88bff609b2d6a393005072",
        "dbbdb63",
        "phx2 stage 27.7: operator runbook and dry-run smoke",
    ),
    (
        "0f51912a74e624100157c758a5affda6347d3cad",
        "0f51912",
        "phx2 stage 27.7: controlled private discord smoke",
    ),
    (
        "30d2aa60abc39db455a4836895f042de376def99",
        "30d2aa6",
        "phx2 stage 27.7: remediate webhook identity leak and usdc lane guard",
    ),
)


@pytest.mark.parametrize("full_sha,short_sha,subject", _STAGE_27_COMMITS)
def test_closure_audit_contains_each_stage_27_commit(
    full_sha: str, short_sha: str, subject: str
):
    text = _closure_audit_text()
    assert full_sha in text, f"missing full SHA {full_sha!r}"
    assert short_sha in text, f"missing short SHA {short_sha!r}"
    assert subject in text, f"missing subject {subject!r}"


def test_closure_audit_contains_exact_live_smoke_identity():
    text = _closure_audit_text()
    for phrase in (
        "stage27_7b_scratch_smoke_20260523T013935Z",
        "stage27_7b_scratch_run_20260523T013935Z",
        "stage27_7b_scratch_session_20260523T013935Z",
    ):
        assert phrase in text


def test_closure_audit_contains_live_smoke_transport_proof():
    text = _closure_audit_text()
    for phrase in (
        "exactly one private Discord POST",
        "HTTP 204",
        "transport_status_code: 204",
        "transport_send_count=1",
        "PRIVATE_OPERATOR_WEBHOOK",
        "SOL synthetic smoke payload",
        "no trading verdict",
    ):
        assert phrase in text


def test_closure_audit_contains_redaction_proof():
    text = _closure_audit_text()
    for phrase in (
        "NO_LEAKS_DETECTED",
        "no webhook URL leaked",
        "no API key leaked",
        "no RPC/gRPC endpoint leaked",
        "no bearer token leaked",
        "no raw payload blob leaked",
        "chainstack hits were safe provider_id CONFIG labels only",
    ):
        assert phrase in text


def test_closure_audit_contains_test_proof_counts():
    text = _closure_audit_text()
    assert "1532 passed, 8 skipped" in text
    assert "214 passed" in text
    assert "pre-smoke and post-smoke gates were both green" in text


def test_closure_audit_contains_git_status_proof():
    text = _closure_audit_text()
    for phrase in (
        "PHX2/.stage_17_inputs/",
        "PHX2/docs/stage_summaries/",
        "ROADMAP.md",
        "No tracked files were edited by the smoke",
        "No push was performed",
    ):
        assert phrase in text


def test_closure_audit_states_no_tag_yet_and_operator_authorization():
    normalized = _normalized(_closure_audit_text()).lower()
    assert "no tag exists yet" in normalized
    assert "stage-27-closed" in normalized
    assert "explicit operator authorization" in normalized
    assert "does not create that tag" in normalized


def test_stage_27_closed_tag_exists_and_peels_to_closure_commit():
    """Stage 27.8 closure-audit tag hygiene check.

    The Stage 27.8 closure audit was authored before the operator
    created the annotated ``stage-27-closed`` tag; this test now
    pins the post-authorization state instead of the pre-
    authorization absence:

      * the tag exists,
      * it is an annotated tag (not lightweight),
      * it peels to the Stage 27.8 closure commit (HEAD at the
        time of tag creation).

    The closure-audit document text itself continues to record
    the pre-authorization narrative ("no tag exists yet" /
    "explicit operator authorization" / "does not create that
    tag") because that narrative captures what the closure pass
    itself shipped; the tag was an operator action that happened
    after closure.
    """
    list_result = subprocess.run(
        ["git", "tag", "--list", "stage-27-closed"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert list_result.stdout.strip() == "stage-27-closed", (
        "stage-27-closed annotated tag must exist locally"
    )

    type_result = subprocess.run(
        ["git", "cat-file", "-t", "stage-27-closed"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert type_result.stdout.strip() == "tag", (
        "stage-27-closed must be an annotated tag, not lightweight"
    )

    peel_result = subprocess.run(
        ["git", "rev-parse", "stage-27-closed^{}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert peel_result.stdout.strip() == (
        "f0a23d580b64173be35a31d6646896de7b7339ee"
    ), (
        "stage-27-closed must peel to the Stage 27.8 closure "
        "commit f0a23d580b64173be35a31d6646896de7b7339ee"
    )


def test_closure_audit_lists_scope_exclusions():
    text = _closure_audit_text()
    for phrase in (
        "no public routing",
        "no subscriber routing",
        "no paid tiers",
        "no broad Discord distribution",
        "no Telegram",
        "no X/social",
        "no Stage 29 enforcement",
        "no automated trading",
    ):
        assert phrase in text


def test_closure_audit_contains_required_caveats():
    text = _normalized(_closure_audit_text())
    for phrase in (
        "NotImplementedError by design",
        "out-of-repo scratch transport",
        "not a hardened production daemon",
        "Stage 28 must harden reliability",
        "HELIUS_GRPC_ENDPOINT as a compatibility slot",
        "provider_id=chainstack",
        "Dexscreener is not wired",
    ):
        assert phrase in text


def test_closure_audit_contains_closure_verdict():
    text = _normalized(_closure_audit_text())
    assert (
        "Stage 27 is ready to close after operator review, "
        "assuming tests pass and no closure audit blockers are found."
    ) in text


_FORBIDDEN_SECRET_LOOKING_PATTERNS: tuple[str, ...] = (
    r"https?://",
    r"wss?://",
    r"discord(?:app)?\.com",
    r"hooks\.slack\.com",
    r"Authorization:\s*\S+",
    r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}",
    r"\bsk-[A-Za-z0-9_-]{8,}\b",
    r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b",
    r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b",
    r"\b(?:api|rpc|grpc)\.[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)


@pytest.mark.parametrize("pattern", _FORBIDDEN_SECRET_LOOKING_PATTERNS)
def test_closure_audit_contains_no_secret_looking_raw_values(
    pattern: str,
):
    assert not re.search(pattern, _closure_audit_text(), re.IGNORECASE)


def test_closure_audit_contains_no_raw_secret_assignment_names():
    text = _closure_audit_text()
    for needle in (
        "webhook_url",
        "DISCORD_WEBHOOK_URL=",
        "HELIUS_API_KEY=",
        "HELIUS_RPC_URL=",
        "HELIUS_GRPC_ENDPOINT=",
        "raw_payload",
        "provider_payload",
    ):
        assert needle not in text
