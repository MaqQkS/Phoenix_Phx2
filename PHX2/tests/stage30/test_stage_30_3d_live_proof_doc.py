"""Stage 30.3D proof-doc pins.

Pure read-only repo inspection. No live network calls, no env
reads, no Discord traffic, no provider calls. This test only reads
the sanitized Stage 30.3D proof markdown and asserts:

  * The proof doc exists.
  * It carries the required sanitized milestone tokens.
  * It clearly records the Tier Not Applicable / NA_MIGRATION_MISSING
    limitation and that it does NOT prove fully trade-ready tier
    pings.
  * It carries NONE of the forbidden secret / URL-host / header
    substrings.
  * It does not reproduce the full compact body, the full mint, or
    raw JSONL artifact lines.
  * It carries no URL scheme substring.
  * It restates the ceremony discipline (no commit/tag/push, no
    tracked PHX2 modifications, outputs out-of-repo under
    phx2_scratch).
"""

from __future__ import annotations

import re
from pathlib import Path


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
PROOF_DOC_PATH: Path = (
    STAGE30_ROOT / "STAGE_30_3D_COMPACT_PRIVATE_LIVE_PROOF.md"
)


def _doc_text() -> str:
    return PROOF_DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. The proof doc exists.
# ---------------------------------------------------------------------------


def test_proof_doc_exists() -> None:
    assert PROOF_DOC_PATH.is_file(), (
        f"Stage 30.3D requires the proof doc {PROOF_DOC_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Required sanitized milestone tokens.
# ---------------------------------------------------------------------------


_REQUIRED_MILESTONE_TOKENS: tuple = (
    "Stage 30.3C-B",
    "DISPATCHED_OK",
    "PRIVATE_OPERATOR_WEBHOOK",
    "NOT_ACTIVE_STAGE_29_PENDING",
    "redaction_status = SAFE",
    "total_hits = 0",
    "compact_renders_attempted/succeeded/failed/skipped = 1/1/0/0",
    "Discord send count = 1",
    "Stage 30.4 is deferred",
)


def test_proof_doc_contains_required_milestone_tokens() -> None:
    text = _doc_text()
    for token in _REQUIRED_MILESTONE_TOKENS:
        assert token in text, (
            f"Stage 30.3D proof doc missing required milestone "
            f"token: {token!r}"
        )


# ---------------------------------------------------------------------------
# 3. Tier-limitation clarity.
# ---------------------------------------------------------------------------


_REQUIRED_LIMITATION_PHRASES: tuple = (
    "Tier Not Applicable / NA_MIGRATION_MISSING was expected",
    "migration evidence was intentionally disabled",
    "does not prove fully trade-ready tier pings",
)


def test_proof_doc_records_tier_limitation_clearly() -> None:
    text = _doc_text()
    for phrase in _REQUIRED_LIMITATION_PHRASES:
        assert phrase in text, (
            f"Stage 30.3D proof doc must clearly record the tier "
            f"limitation; missing {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 4. Forbidden secret / URL-host / header substrings must be absent.
# ---------------------------------------------------------------------------


_FORBIDDEN_SECRET_SUBSTRINGS: tuple = (
    "discord.com",
    "discordapp.com",
    "/webhooks/",
    "bearer",
    "authorization",
    "x-api-key",
    "x-token",
    "sk-",
    "pk-",
    "api_key",
    "private_key",
    "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT=",
    "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN=",
    "PHX2_STAGE29_2_BIRDEYE_API_KEY=",
    "PHX2_STAGE30_3C_PRIVATE_DISCORD_WEBHOOK_URL=",
)


def test_proof_doc_carries_no_forbidden_secret_substring() -> None:
    lowered = _doc_text().lower()
    for needle in _FORBIDDEN_SECRET_SUBSTRINGS:
        assert needle.lower() not in lowered, (
            f"Stage 30.3D proof doc must NOT carry forbidden "
            f"secret / header substring {needle!r}"
        )


# ---------------------------------------------------------------------------
# 5. No full compact body, no full mint, no raw JSONL lines.
# ---------------------------------------------------------------------------


def test_proof_doc_has_no_fenced_code_block() -> None:
    """A fenced code block is the only plausible vehicle for a
    pasted raw compact body or raw JSONL artifact line; forbid it
    outright.
    """
    text = _doc_text()
    assert "```" not in text, (
        "Stage 30.3D proof doc must not contain a fenced code "
        "block (no raw compact body / raw JSONL paste)"
    )


def test_proof_doc_has_no_raw_jsonl_object() -> None:
    text = _doc_text()
    assert '{"' not in text, (
        "Stage 30.3D proof doc must not contain a raw JSONL "
        "object literal (no '{\"...' artifact line)"
    )


def test_proof_doc_has_no_full_mint_like_base58_run() -> None:
    """A full Solana mint is a 32-44 char base58 run. The proof
    doc must not reproduce one. (The required HEAD sha is hex with
    ``0`` digits, which is outside the base58 alphabet, so it
    cannot false-positive here.)
    """
    text = _doc_text()
    base58_run = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")
    match = base58_run.search(text)
    assert match is None, (
        "Stage 30.3D proof doc must not reproduce a full mint-like "
        f"base58 run; found {match.group(0) if match else None!r}"
    )


# ---------------------------------------------------------------------------
# 6. No URL scheme substring.
# ---------------------------------------------------------------------------


_FORBIDDEN_URL_SCHEMES: tuple = (
    "http://",
    "https://",
    "ws://",
    "wss://",
)


def test_proof_doc_carries_no_url_scheme() -> None:
    lowered = _doc_text().lower()
    for scheme in _FORBIDDEN_URL_SCHEMES:
        assert scheme not in lowered, (
            f"Stage 30.3D proof doc must carry no URL scheme "
            f"substring {scheme!r}"
        )


# ---------------------------------------------------------------------------
# 7. Ceremony discipline restated.
# ---------------------------------------------------------------------------


_REQUIRED_CEREMONY_PHRASES: tuple = (
    "no commit/tag/push during ceremony",
    "no tracked PHX2 modifications during ceremony",
    "out-of-repo under phx2_scratch",
)


def test_proof_doc_restates_ceremony_discipline() -> None:
    text = _doc_text()
    for phrase in _REQUIRED_CEREMONY_PHRASES:
        assert phrase in text, (
            f"Stage 30.3D proof doc must restate the ceremony "
            f"discipline; missing {phrase!r}"
        )
