"""Stage 30.13.1 seed-only fake proof tests.

Offline only. Drives the REAL committed Stage 29.5 Helius WS adapter over a deterministic
fake WebSocket transport through the Stage 30.13.0 auto-seeder, and pins:

  * a fresh pump-suffix migrated mint with complete evidence is discovered + seeded;
  * a non-pump mint / a non-PRESENT record / an incomplete-evidence pump mint are
    rejected with the right reasons;
  * a repeat pump mint is deduped;
  * a malformed transport surfaces as a fail-closed WS_CAPTURE_FAILED error;
  * the proof STOPS at the seeded watchlist (no recheck / fake-send).

No real socket, no network, no env, no Discord, no durable ledger.
"""

from __future__ import annotations

import json
from typing import List, Optional

from PHX2.stage29.stage29_5_helius_ws_adapter import (
    STAGE29_5_HELIUS_WS_MIGRATION_KIND,
    Stage29_5WebSocketTransport,
)
from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    SEED_REASON_DUPLICATE_MINT,
    SEED_REASON_INCOMPLETE_EVIDENCE,
    SEED_REASON_NOT_PRESENT_MIGRATION,
    SEED_REASON_NOT_PUMP_SUFFIX,
    SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
    SEED_REASON_WS_CAPTURE_FAILED,
    STAGE30_13_REDACTION_STATUS_REDACTED,
)
from PHX2.stage30.stage30_13_1_fake_seed_only_proof import (
    Stage30_13_1SeedOnlyProofResult,
    run_stage30_13_1_fake_seed_only_proof,
)


_PUMP_A = "A" * 40 + "pump"
_PUMP_B = "B" * 40 + "pump"
_PUMP_C = "C" * 40 + "pump"
_NON_PUMP = "D" * 44
_POOL = "P" * 44
_PROG = "G" * 44
_QUOTE = "Q" * 44
_TS = "2026-06-06T06:00:00Z"
_OBS = "2026-06-07T02:00:00+00:00"
_CREATED = "2026-06-07T03:00:00+00:00"


def _msg(base_mint: str, *, full: bool = True, drop_axis: Optional[str] = None) -> bytes:
    payload = {
        "kind": STAGE29_5_HELIUS_WS_MIGRATION_KIND,
        "base_mint": base_mint,
        "pool_account": _POOL,
        "pool_program_id": _PROG,
        "quote_mint": _QUOTE,
        "migration_timestamp_utc": _TS,
    }
    if full:
        payload["migration_slot"] = 123456
        payload["migration_signature"] = "sig-x"
        payload["source_event_ref"] = "ref-x"
    if drop_axis is not None:
        payload.pop(drop_axis, None)
    return json.dumps(payload).encode("utf-8")


class _FakeWebSocketTransport(Stage29_5WebSocketTransport):
    """In-memory fake: yields preset byte messages, then None (end of stream)."""

    def __init__(self, messages: List[Optional[bytes]]) -> None:
        self._messages = list(messages)
        self.close_called = 0

    def recv_one_message(self, timeout_seconds: float) -> Optional[bytes]:
        if not self._messages:
            return None
        return self._messages.pop(0)

    def close(self) -> None:
        self.close_called += 1


def _fixed_clock() -> str:
    return _OBS


def _run(messages, *, max_seed: int = 10) -> Stage30_13_1SeedOnlyProofResult:
    return run_stage30_13_1_fake_seed_only_proof(
        _FakeWebSocketTransport(messages),
        clock=_fixed_clock,
        created_at_utc=_CREATED,
        max_seed=max_seed,
    )


# ---------------------------------------------------------------------------
# 1. Mixed clean batch -> discovered + seeded + classified
# ---------------------------------------------------------------------------


def test_mixed_clean_batch_seeds_fresh_pump_and_classifies_rest() -> None:
    proof = _run(
        [
            _msg(_PUMP_A),                              # ACCEPTED
            _msg(_PUMP_A),                              # DUPLICATE
            _msg(_NON_PUMP),                           # REJECTED NOT_PUMP_SUFFIX
            _msg(_PUMP_B, drop_axis="pool_account"),  # INVALID -> NOT_PRESENT_MIGRATION
            _msg(_PUMP_C, full=False),                # PRESENT but INCOMPLETE_EVIDENCE
        ]
    )
    assert isinstance(proof, Stage30_13_1SeedOnlyProofResult)
    s = proof.auto_seed_result.summary
    assert (s.accepted, s.duplicate, s.rejected, s.error) == (1, 1, 3, 0)
    assert s.records_seen == 5
    # The fresh pump-suffix mint is the only seeded watchlist entry.
    assert proof.seeded_token_mints == (_PUMP_A,)
    reasons = [o.seed_reason for o in proof.auto_seed_result.outcomes]
    assert reasons == [
        SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
        SEED_REASON_DUPLICATE_MINT,
        SEED_REASON_NOT_PUMP_SUFFIX,
        SEED_REASON_NOT_PRESENT_MIGRATION,
        SEED_REASON_INCOMPLETE_EVIDENCE,
    ]
    assert (
        proof.auto_seed_result.redaction_status
        == STAGE30_13_REDACTION_STATUS_REDACTED
    )


def test_only_accepted_mints_are_seeded() -> None:
    proof = _run([_msg(_PUMP_A), _msg(_PUMP_B), _msg(_PUMP_C)])
    assert proof.auto_seed_result.summary.accepted == 3
    assert set(proof.seeded_token_mints) == {_PUMP_A, _PUMP_B, _PUMP_C}
    assert len(proof.auto_seed_result.seeded_summaries) == 3


# ---------------------------------------------------------------------------
# 2. Malformed transport -> fail-closed WS_CAPTURE_FAILED
# ---------------------------------------------------------------------------


def test_malformed_payload_fails_closed_to_ws_capture_failed() -> None:
    proof = _run([b"{not-json"])
    s = proof.auto_seed_result.summary
    assert s.error == 1
    assert s.accepted == 0
    assert s.records_seen == 0
    assert proof.seeded_token_mints == ()
    assert len(proof.auto_seed_result.outcomes) == 1
    assert (
        proof.auto_seed_result.outcomes[0].seed_reason
        == SEED_REASON_WS_CAPTURE_FAILED
    )


def test_empty_stream_seeds_nothing() -> None:
    proof = _run([])
    s = proof.auto_seed_result.summary
    assert (s.accepted, s.duplicate, s.rejected, s.error, s.records_seen) == (
        0,
        0,
        0,
        0,
        0,
    )
    assert proof.seeded_token_mints == ()


# ---------------------------------------------------------------------------
# 3. Bounded seed cap honored end-to-end
# ---------------------------------------------------------------------------


def test_seed_cap_bounds_the_watchlist() -> None:
    proof = _run([_msg(_PUMP_A), _msg(_PUMP_B), _msg(_PUMP_C)], max_seed=2)
    assert proof.auto_seed_result.summary.records_seen == 2
    assert proof.auto_seed_result.summary.accepted == 2
    assert len(proof.seeded_token_mints) == 2
