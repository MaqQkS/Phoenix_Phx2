"""Stage 30.4.4 MC / LP private-live proof-doc pins.

Pure read-only repo inspection. No live network calls, no env
reads, no Discord traffic, no provider calls. This test only reads
the sanitized Stage 30.4.4 proof markdown
(``STAGE_30_4_4_MC_LP_PRIVATE_LIVE_PROOF.md``) and asserts:

  * The proof doc exists.
  * It carries the required section headings (scope, the three
    Stage 30.4.3C / 30.4.3D / 30.4.3E proof summaries, limitations
    / handoff, redaction / safety), in order.
  * It carries the three required result codes
    (``PROBE_MAPPED_MC_LP`` / ``DRY_RUN_OK_MAPPED_MC_LP`` /
    ``LIVE_OK_SENT_MAPPED_MC_LP``).
  * It carries the required key findings (the observed real
    ``marketCap`` / ``liquidity`` keys, MC/LP known, Net Unknown).
  * The Stage 30.4.3E delivered proof records HTTP 204,
    DISPATCHED_OK, exactly one Birdeye call, and exactly one
    Discord send.
  * The known-limitation handoff is explicit (Mig / ATH / Net all
    remain Unknown/deferred; Stage 30.4 solved current MC/LP only;
    Stage 30.5 migration context next; Stage 30.6 / 30.5.x ATH
    context after that).
  * It carries NONE of the forbidden secret / header / URL-scheme
    substrings.
  * It does not reproduce a raw provider payload (no fenced code
    block, no raw JSONL object literal).
  * The Stage 30.4.4 manifest entries pin this doc + this test.

Stage 30.4.4 is a documentation / proof record only. This test
makes no live call, sends no Discord message, and changes no
runtime behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
PROOF_DOC_PATH: Path = (
    STAGE30_ROOT / "STAGE_30_4_4_MC_LP_PRIVATE_LIVE_PROOF.md"
)
PROOF_DOC_BASENAME: str = "STAGE_30_4_4_MC_LP_PRIVATE_LIVE_PROOF.md"
TEST_BASENAME: str = (
    "test_stage_30_4_4_mc_lp_private_live_proof_doc.py"
)


def _doc_text() -> str:
    return PROOF_DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. The proof doc exists.
# ---------------------------------------------------------------------------


def test_proof_doc_exists() -> None:
    assert PROOF_DOC_PATH.is_file(), (
        f"Stage 30.4.4 requires the proof doc {PROOF_DOC_PATH}"
    )


# ---------------------------------------------------------------------------
# 2. Required section headings exist, in order.
# ---------------------------------------------------------------------------


_REQUIRED_SECTION_HEADINGS: Tuple[str, ...] = (
    "# PHX2 Stage 30.4.4",
    "## 1. Scope",
    "## 2. Stage 30.4.3C",
    "## 3. Stage 30.4.3D",
    "## 4. Stage 30.4.3E",
    "## 5. Known limitations and handoff",
    "## 6. Redaction and safety",
)


def test_proof_doc_contains_required_section_headings() -> None:
    text = _doc_text()
    for heading in _REQUIRED_SECTION_HEADINGS:
        assert heading in text, (
            f"Stage 30.4.4 proof doc missing required section "
            f"heading: {heading!r}"
        )


def test_proof_doc_section_headings_appear_in_order() -> None:
    text = _doc_text()
    last_index = -1
    for heading in _REQUIRED_SECTION_HEADINGS:
        index = text.find(heading)
        assert index > last_index, (
            f"Stage 30.4.4 proof doc section heading out of order: "
            f"{heading!r}"
        )
        last_index = index


def test_proof_doc_names_all_three_stage_30_4_3_events() -> None:
    text = _doc_text()
    for token in ("Stage 30.4.3C", "Stage 30.4.3D", "Stage 30.4.3E"):
        assert token in text, (
            f"Stage 30.4.4 proof doc must name the {token!r} event"
        )


# ---------------------------------------------------------------------------
# 3. Required result codes.
# ---------------------------------------------------------------------------


_REQUIRED_RESULT_CODES: Tuple[str, ...] = (
    "PROBE_MAPPED_MC_LP",
    "DRY_RUN_OK_MAPPED_MC_LP",
    "LIVE_OK_SENT_MAPPED_MC_LP",
)


def test_proof_doc_contains_required_result_codes() -> None:
    text = _doc_text()
    for code in _REQUIRED_RESULT_CODES:
        assert code in text, (
            f"Stage 30.4.4 proof doc missing required result code: "
            f"{code!r}"
        )


# ---------------------------------------------------------------------------
# 4. Required key findings (observed real keys + mapping outcome).
# ---------------------------------------------------------------------------


_REQUIRED_KEY_FINDINGS: Tuple[str, ...] = (
    # The real Birdeye token_overview keys actually observed.
    "marketCap",
    "liquidity",
    # MC + LP mapped; Net deferred.
    "MC/LP known",
    "Net Unknown",
)


def test_proof_doc_contains_required_key_findings() -> None:
    text = _doc_text()
    for finding in _REQUIRED_KEY_FINDINGS:
        assert finding in text, (
            f"Stage 30.4.4 proof doc missing required key finding: "
            f"{finding!r}"
        )


def test_proof_doc_pins_basis_price_basis() -> None:
    text = _doc_text()
    assert "price-basis" in text, (
        "Stage 30.4.4 proof doc must record the tier basis as "
        "price-basis"
    )


# ---------------------------------------------------------------------------
# 5. Stage 30.4.3E delivered-proof specifics.
# ---------------------------------------------------------------------------


_REQUIRED_30_4_3E_TOKENS: Tuple[str, ...] = (
    "HTTP 204",
    "DISPATCHED_OK",
    "exactly one Birdeye call",
    "exactly one Discord send",
)


def test_proof_doc_records_30_4_3e_delivered_proof() -> None:
    text = _doc_text()
    for token in _REQUIRED_30_4_3E_TOKENS:
        assert token in text, (
            f"Stage 30.4.4 proof doc must record the Stage 30.4.3E "
            f"delivered proof token: {token!r}"
        )


def test_proof_doc_records_redaction_safe() -> None:
    text = _doc_text()
    assert "redaction SAFE" in text, (
        "Stage 30.4.4 proof doc must record that each Stage 30.4.3 "
        "event redaction scan was SAFE"
    )


# ---------------------------------------------------------------------------
# 6. Known-limitation / next-stage handoff is explicit.
# ---------------------------------------------------------------------------


_REQUIRED_LIMITATION_PHRASES: Tuple[str, ...] = (
    "Stage 30.4 solved the current MC/LP display only",
    "Net remains deferred and Unknown",
    "Mig remains Unknown",
    "ATH remains Unknown",
)


def test_proof_doc_records_limitations_explicitly() -> None:
    text = _doc_text()
    for phrase in _REQUIRED_LIMITATION_PHRASES:
        assert phrase in text, (
            f"Stage 30.4.4 proof doc must explicitly record the "
            f"limitation: {phrase!r}"
        )


_REQUIRED_HANDOFF_PHRASES: Tuple[str, ...] = (
    "Stage 30.5 = migration context into compact private pings",
    "Stage 30.6 or 30.5.x = ATH context into compact private pings",
)


def test_proof_doc_records_next_stage_handoff() -> None:
    text = _doc_text()
    for phrase in _REQUIRED_HANDOFF_PHRASES:
        assert phrase in text, (
            f"Stage 30.4.4 proof doc must record the next-stage "
            f"handoff: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 7. Forbidden secret / header substrings must be absent.
# ---------------------------------------------------------------------------
#
# Case-insensitive scan. ``HTTP 204`` / ``HTTP 200`` are required
# present tokens and do NOT contain the scheme ``http://``; the
# scheme group below is intentionally the colon-slash-slash form
# only.


_FORBIDDEN_SECRET_SUBSTRINGS: Tuple[str, ...] = (
    "x-api-key",
    "authorization",
    "bearer",
    "webhook url",
    "discord.com/api/webhooks",
    "raw_body",
    "response_body",
    "endpoint_secret",
    "headers",
)


def test_proof_doc_carries_no_forbidden_secret_substring() -> None:
    lowered = _doc_text().lower()
    for needle in _FORBIDDEN_SECRET_SUBSTRINGS:
        assert needle.lower() not in lowered, (
            f"Stage 30.4.4 proof doc must NOT carry forbidden "
            f"secret / header substring {needle!r}"
        )


_FORBIDDEN_URL_SCHEMES: Tuple[str, ...] = (
    "http://",
    "https://",
    "ws://",
    "wss://",
)


def test_proof_doc_carries_no_url_scheme() -> None:
    lowered = _doc_text().lower()
    for scheme in _FORBIDDEN_URL_SCHEMES:
        assert scheme not in lowered, (
            f"Stage 30.4.4 proof doc must carry no URL scheme "
            f"substring {scheme!r}"
        )


# ---------------------------------------------------------------------------
# 8. No raw provider payload vehicle (no fenced code block, no raw
#    JSONL object literal).
# ---------------------------------------------------------------------------


def test_proof_doc_has_no_fenced_code_block() -> None:
    text = _doc_text()
    assert "```" not in text, (
        "Stage 30.4.4 proof doc must not contain a fenced code "
        "block (no raw compact body / raw provider payload paste)"
    )


def test_proof_doc_has_no_raw_jsonl_object() -> None:
    text = _doc_text()
    assert '{"' not in text, (
        "Stage 30.4.4 proof doc must not contain a raw JSONL "
        "object literal (no '{\"...' artifact line)"
    )


# ---------------------------------------------------------------------------
# 9. Stage 30.4.4 manifest entries pin this doc + this test.
# ---------------------------------------------------------------------------
#
# Local imports so a missing/renamed manifest constant fails only
# this pin, not the read-only doc assertions above.


def test_manifest_pins_stage_30_4_4_doc_and_test_basenames() -> None:
    from PHX2.stage30.stage30_4_manifest import (
        STAGE30_4_4_MINOR_VERSION,
        STAGE30_4_4_PRIVATE_LIVE_PROOF_BASENAME,
        STAGE30_4_4_TEST_BASENAMES,
        STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_4,
    )

    assert STAGE30_4_4_MINOR_VERSION == "30.4.4"
    assert (
        STAGE30_4_4_PRIVATE_LIVE_PROOF_BASENAME == PROOF_DOC_BASENAME
    )
    assert STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_4 == (
        STAGE30_4_4_PRIVATE_LIVE_PROOF_BASENAME,
    )
    assert STAGE30_4_4_TEST_BASENAMES == (TEST_BASENAME,)
    # The pinned doc basename must match the file this test reads.
    assert (
        STAGE30_ROOT / STAGE30_4_4_PRIVATE_LIVE_PROOF_BASENAME
        == PROOF_DOC_PATH
    )


def test_manifest_all_exports_stage_30_4_4_surface() -> None:
    import PHX2.stage30.stage30_4_manifest as manifest

    for name in (
        "STAGE30_4_4_MINOR_VERSION",
        "STAGE30_4_4_PRIVATE_LIVE_PROOF_BASENAME",
        "STAGE30_4_ALLOWED_STAGE30_BASENAMES_FOR_30_4_4",
        "STAGE30_4_4_TEST_BASENAMES",
    ):
        assert name in manifest.__all__, (
            f"manifest __all__ must export {name!r}"
        )
