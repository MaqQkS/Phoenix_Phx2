"""Stage 30.13.0 spec-lock tests.

Pins the locked Stage 30.13.0 contract: the SPEC_LOCK.md exists and names the locked
decision ladder + four-count ledger + non-goals + handoff, and the code-level invariants
the doc locks (the single accept decision / reason, the hard seed cap, the literal pump
suffix, the closed-set decision / reason vocabularies).
"""

from __future__ import annotations

from pathlib import Path

from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    SEED_DECISION_ACCEPTED,
    SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
    STAGE30_13_MAX_SEED_HARD_CAP,
    STAGE30_13_PUMP_MINT_SUFFIX,
    STAGE30_13_SEED_ACCEPT_DECISION,
    STAGE30_13_SEED_ACCEPT_REASON,
    STAGE30_13_SEED_DECISIONS,
    STAGE30_13_SEED_REASONS,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
SPEC_LOCK_PATH: Path = (
    PHX2_ROOT / "stage30" / "STAGE_30_13_0_WS_AUTO_SEED_SPEC_LOCK.md"
)


def _spec_text() -> str:
    return SPEC_LOCK_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Doc presence + locked clauses
# ---------------------------------------------------------------------------


def test_spec_lock_doc_exists() -> None:
    assert SPEC_LOCK_PATH.is_file()


def test_spec_lock_names_every_seed_reason() -> None:
    text = _spec_text()
    for reason in STAGE30_13_SEED_REASONS:
        assert reason in text, f"spec-lock must name seed reason {reason!r}"


def test_spec_lock_names_every_seed_decision() -> None:
    text = _spec_text()
    for decision in STAGE30_13_SEED_DECISIONS:
        assert decision in text, f"spec-lock must name seed decision {decision!r}"


def test_spec_lock_locks_four_counts_and_invariants() -> None:
    text = _spec_text()
    for token in ("accepted", "rejected", "duplicate", "error", "records_seen"):
        assert token in text
    assert "len(outcomes) == accepted + rejected + duplicate + error" in text
    assert "len(seeded_summaries) == accepted" in text


def test_spec_lock_locks_pump_suffix_and_no_age_bound() -> None:
    text = _spec_text()
    assert "pump" in text
    assert "No migration-age bound in Build #24." in text


def test_spec_lock_locks_no_send_and_handoff() -> None:
    text = _spec_text()
    assert "no-send" in text
    assert "STAGE_30_13_3_REAL_WS_CAPTURE_HANDOFF.md" in text


def test_spec_lock_lists_non_goals() -> None:
    text = _spec_text()
    for surface in (
        "real WebSocket",
        "live send",
        "durable",
        "no tag",
        "no push",
    ):
        assert surface in text


# ---------------------------------------------------------------------------
# Code-level invariants the doc locks
# ---------------------------------------------------------------------------


def test_single_accept_decision_and_reason() -> None:
    assert STAGE30_13_SEED_ACCEPT_DECISION == SEED_DECISION_ACCEPTED == "ACCEPTED"
    assert (
        STAGE30_13_SEED_ACCEPT_REASON
        == SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION
        == "SEEDED_FRESH_PUMP_MIGRATION"
    )


def test_hard_seed_cap_is_ten() -> None:
    assert STAGE30_13_MAX_SEED_HARD_CAP == 10


def test_pump_suffix_is_literal_pump() -> None:
    assert STAGE30_13_PUMP_MINT_SUFFIX == "pump"


def test_decision_and_reason_vocabularies_are_locked() -> None:
    assert STAGE30_13_SEED_DECISIONS == (
        "ACCEPTED",
        "REJECTED",
        "DUPLICATE",
        "ERROR",
    )
    assert STAGE30_13_SEED_REASONS == (
        "SEEDED_FRESH_PUMP_MIGRATION",
        "NOT_PRESENT_MIGRATION",
        "NOT_PUMP_SUFFIX",
        "INCOMPLETE_EVIDENCE",
        "DUPLICATE_MINT",
        "WS_CAPTURE_FAILED",
        "NOT_A_RECORD",
    )
