"""Stage 30.7.4 closure-audit document tests.

Asserts the Stage 30.7.4 closure-audit markdown
(``STAGE_30_7_ATH_CONTEXT_CLOSURE_AUDIT.md``) exists and contains the
mandated closure content:

  * all four Stage 30.7 commit SHAs (30.7.0..30.7.3),
  * the final compact proof line,
  * the final Stage 30.7 data path,
  * the safety invariants,
  * the redaction fail-closed invariants,
  * the unit / basis honesty outcomes,
  * the explicit "did NOT solve" list,
  * the Stage 30.8 next-stage recommendation.

Doc only. No live call, no env read, no provider, no Discord.
"""

from __future__ import annotations

from pathlib import Path

from PHX2.stage30.stage30_7_4_manifest import (
    STAGE30_7_0_COMMIT,
    STAGE30_7_1_COMMIT,
    STAGE30_7_2_COMMIT,
    STAGE30_7_3_COMMIT,
    STAGE30_7_4_CLOSURE_AUDIT_BASENAME,
    STAGE30_7_4_COMPACT_PROOF_LINE,
    STAGE30_7_4_FINAL_DATA_PATH,
    STAGE30_7_4_NEXT_RECOMMENDED_STAGE,
    STAGE30_7_4_NEXT_RECOMMENDED_STAGE_TITLE,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
AUDIT_PATH: Path = STAGE30_ROOT / STAGE30_7_4_CLOSURE_AUDIT_BASENAME


def _audit_text() -> str:
    return AUDIT_PATH.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    """Collapse runs of whitespace so a phrase that wraps across a
    markdown line still matches.
    """
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Doc exists
# ---------------------------------------------------------------------------


def test_closure_audit_doc_exists() -> None:
    assert AUDIT_PATH.is_file(), (
        f"Stage 30.7.4 requires {STAGE30_7_4_CLOSURE_AUDIT_BASENAME}"
    )
    assert _audit_text().strip() != ""


# ---------------------------------------------------------------------------
# 2. All four commit SHAs
# ---------------------------------------------------------------------------


def test_audit_mentions_all_four_commit_shas() -> None:
    text = _audit_text()
    for sha in (
        STAGE30_7_0_COMMIT,
        STAGE30_7_1_COMMIT,
        STAGE30_7_2_COMMIT,
        STAGE30_7_3_COMMIT,
    ):
        assert sha in text, (
            f"closure audit must cite commit SHA {sha!r}"
        )


def test_audit_labels_the_commit_chain_substages() -> None:
    text = _audit_text()
    for substage in ("30.7.0", "30.7.1", "30.7.2", "30.7.3"):
        assert substage in text, (
            f"closure audit must label substage {substage!r}"
        )


# ---------------------------------------------------------------------------
# 3. Final proof line
# ---------------------------------------------------------------------------


def test_audit_contains_final_proof_line() -> None:
    assert STAGE30_7_4_COMPACT_PROOF_LINE in _audit_text(), (
        "closure audit must contain the final compact proof line "
        f"{STAGE30_7_4_COMPACT_PROOF_LINE!r}"
    )


# ---------------------------------------------------------------------------
# 4. Final data path
# ---------------------------------------------------------------------------


def test_audit_contains_final_data_path() -> None:
    text = _audit_text()
    for hop in STAGE30_7_4_FINAL_DATA_PATH:
        assert hop in text, (
            f"closure audit must contain data-path hop {hop!r}"
        )


# ---------------------------------------------------------------------------
# 5. Safety invariants
# ---------------------------------------------------------------------------


def test_audit_contains_safety_invariants() -> None:
    text = _audit_text()
    for invariant in (
        "offline only",
        "no live/provider/Discord",
        "no env reads",
        "no DB/filesystem writer",
        "no zstd",
        "no enforcement/public routing/trading/wallet/social",
        "no drawdown/tier recomputation",
        "no Stage 25/27/28/29 production imports",
        "no Stage 29.5 production imports",
        "compact renderer/model untouched",
    ):
        assert invariant in text, (
            f"closure audit must state safety invariant {invariant!r}"
        )


# ---------------------------------------------------------------------------
# 6. Redaction fail-closed invariants
# ---------------------------------------------------------------------------


def test_audit_contains_redaction_fail_closed_invariants() -> None:
    text = _audit_text()
    normalized = _normalized(text)
    assert "redaction_safe=False" in text, (
        "closure audit must state the carrier defaults "
        "redaction_safe=False"
    )
    assert "fails closed" in text or "fail closed" in text
    # Duck-typed missing redaction proof + bridge non-True both fail closed.
    assert "missing the `redaction_safe`" in text or (
        "missing" in normalized and "redaction" in normalized
    )
    assert "exactly `True`" in text or "exactly True" in text


# ---------------------------------------------------------------------------
# 7. Unit / basis honesty
# ---------------------------------------------------------------------------


def test_audit_contains_unit_basis_honesty() -> None:
    normalized = _normalized(_audit_text())
    for phrase in (
        "USD observed market-cap",
        "price-derived ATH remains",
        "USDC",
        "SOL",
        "conflicting",
    ):
        assert phrase in normalized, (
            f"closure audit must state unit/basis honesty {phrase!r}"
        )


# ---------------------------------------------------------------------------
# 8. What Stage 30.7 did NOT solve
# ---------------------------------------------------------------------------


def test_audit_lists_what_was_not_solved() -> None:
    text = _audit_text()
    for item in (
        "live ATH sourcing",
        "storage/session persistence",
        "zstd/day rolling",
        "drawdown from ATH",
        "tier dip",
        "enforcement",
        "public routing",
        "wallet/trading",
    ):
        assert item in text, (
            f"closure audit must list deferred item {item!r}"
        )


# ---------------------------------------------------------------------------
# 9. Stage 30.8 recommendation
# ---------------------------------------------------------------------------


def test_audit_recommends_stage_30_8() -> None:
    text = _audit_text()
    assert "Stage 30.8" in text, (
        "closure audit must recommend Stage 30.8"
    )
    assert STAGE30_7_4_NEXT_RECOMMENDED_STAGE == "30.8"
    # The title may wrap across markdown lines, so match on normalized
    # whitespace.
    assert STAGE30_7_4_NEXT_RECOMMENDED_STAGE_TITLE in _normalized(text), (
        "closure audit must state the Stage 30.8 recommendation title"
    )
