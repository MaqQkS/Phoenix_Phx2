"""Stage 30.13.2 end-to-end fake-send proof tests.

Offline / fake-provider only. Proves the WHOLE Build #24 path -- a fresh pump-suffix
migrated mint discovered over a FAKE WS transport, auto-seeded, then flowed through the
existing committed Stage 30.11.23 -> 30.11.22 recheck/fake-send chain (over FAKE
Birdeye-style sources + a recording FAKE dispatch client + an in-memory ledger) --
reaches a RECORDED would-send, NEVER a real send, with the dispatched mint tracing to the
discovered summary. A non-pump mint and a malformed payload are filtered/failed-closed
BEFORE any dispatch.

The fakes (WS transport, Birdeye transport, sources, clocks) live HERE. No real send, no
network, no env, no Stage 30.11.16 guard.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Mapping, Optional

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
    BIRDEYE_PATH_TOKEN_OVERVIEW,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
    Stage29_2BirdeyeHttpTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_price_source import (
    Stage29_2BirdeyePriceSource,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)
from PHX2.stage29.stage29_5_helius_ws_adapter import (
    STAGE29_5_HELIUS_WS_MIGRATION_KIND,
    Stage29_5WebSocketTransport,
)
from PHX2.stage30.stage30_4_3_market_context_birdeye_source import (
    Stage30_4_3BirdeyeMarketContextSource,
)
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    make_constant_clock,
)
from PHX2.stage30.stage30_11_13_fake_composer_proof import (
    PROOF_CREATED_AT,
    PROOF_CURRENT_PRICE,
    PROOF_LATER_LOWER,
    PROOF_LIQUIDITY_USD,
    PROOF_MARKET_CAP_USD,
    PROOF_MIGRATION_ANCHOR,
    PROOF_MIGRATION_SOURCE,
    PROOF_MINT,
    PROOF_PEAK_ATH,
)
from PHX2.stage30.stage30_11_22_real_fed_dry_run_models import (
    STAGE30_11_22_REDACTION_STATUS_REDACTED,
)
from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    SEED_REASON_NOT_PUMP_SUFFIX,
    SEED_REASON_WS_CAPTURE_FAILED,
)
from PHX2.stage30.stage30_13_2_fake_end_to_end_proof import (
    Stage30_13_2EndToEndProofResult,
    run_stage30_13_2_fake_end_to_end_proof,
)


# A fresh pump-suffix migrated mint: a real-base58-shaped 44-char mint ending in the
# literal pump suffix (PROOF_MINT with its last 4 chars swapped for "pump"). The fake
# Birdeye transport is path-routed (mint-agnostic), so it enriches this mint exactly as
# it enriches PROOF_MINT.
_E2E_PUMP_MINT: str = PROOF_MINT[:-4] + "pump"
_NON_PUMP_MINT: str = PROOF_MINT  # real base58, ends "faNe" -> not a pump suffix

_POOL = "P" * 44
_PROG = "G" * 44
_QUOTE = "Q" * 44

_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"


def _now_utc() -> datetime:
    return datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _ws_clock() -> str:
    return PROOF_CREATED_AT


def _ws_msg(base_mint: str) -> bytes:
    return json.dumps(
        {
            "kind": STAGE29_5_HELIUS_WS_MIGRATION_KIND,
            "base_mint": base_mint,
            "pool_account": _POOL,
            "pool_program_id": _PROG,
            "quote_mint": _QUOTE,
            "migration_timestamp_utc": PROOF_MIGRATION_ANCHOR,
            "migration_slot": 318000000,
            "migration_signature": "e2e-sig",
            "source_event_ref": PROOF_MIGRATION_SOURCE,
        }
    ).encode("utf-8")


class _FakeWebSocketTransport(Stage29_5WebSocketTransport):
    """In-memory fake: yields preset byte messages, then None."""

    def __init__(self, messages: List[Optional[bytes]]) -> None:
        self._messages = list(messages)
        self.close_called = 0

    def recv_one_message(self, timeout_seconds: float) -> Optional[bytes]:
        if not self._messages:
            return None
        return self._messages.pop(0)

    def close(self) -> None:
        self.close_called += 1


class FakeBirdeyeTransport(Stage29_2BirdeyeHttpTransport):
    """Path-routed fake transport serving price + token-overview + ohlcv (mint-agnostic)."""

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        if path == BIRDEYE_PATH_PRICE:
            return self._ok(
                {
                    "success": True,
                    "data": {
                        "value": float(PROOF_CURRENT_PRICE),
                        "updateUnixTime": int(_now_utc().timestamp()),
                    },
                }
            )
        if path == BIRDEYE_PATH_TOKEN_OVERVIEW:
            return self._ok(
                {
                    "success": True,
                    "data": {
                        "marketCap": int(PROOF_MARKET_CAP_USD),
                        "liquidity": int(PROOF_LIQUIDITY_USD),
                    },
                }
            )
        if path == BIRDEYE_PATH_OHLCV:
            return self._ok(
                {
                    "success": True,
                    "data": {
                        "items": [
                            {
                                "h": PROOF_PEAK_ATH,
                                "unixTime": _unix("2026-06-06T06:15:00Z"),
                            },
                            {
                                "h": PROOF_LATER_LOWER,
                                "unixTime": _unix("2026-06-06T07:30:00Z"),
                            },
                        ]
                    },
                }
            )
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
            http_status_code=0,
            body=None,
            fetched_at_utc=_FETCHED_AT,
        )

    def _ok(self, body: dict) -> Stage29_2BirdeyeHttpResult:
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body=body,
            fetched_at_utc=_FETCHED_AT,
        )


def _endpoint_secret() -> Stage29_2BirdeyeEndpointSecret:
    return Stage29_2BirdeyeEndpointSecret(_api_key=_GOOD_KEY, _base_url=_GOOD_URL)


def _run_e2e(messages=None, **kwargs) -> Stage30_13_2EndToEndProofResult:
    if messages is None:
        messages = [_ws_msg(_E2E_PUMP_MINT)]
    bird = FakeBirdeyeTransport()
    return run_stage30_13_2_fake_end_to_end_proof(
        _FakeWebSocketTransport(messages),
        clock=_ws_clock,
        price_source=Stage29_2BirdeyePriceSource(
            transport=bird,
            endpoint_secret=_endpoint_secret(),
            timeout_seconds=10,
        ),
        market_context_source=Stage30_4_3BirdeyeMarketContextSource(
            transport=bird,
            endpoint_secret=_endpoint_secret(),
            timeout_seconds=10,
        ),
        ath_transport=bird,
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        now_seconds=make_constant_clock(Decimal(0)),
        created_at_utc=PROOF_CREATED_AT,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Happy path: a fresh pump mint flows WS -> seed -> fake dispatch
# ---------------------------------------------------------------------------


def test_fresh_pump_mint_flows_end_to_end_to_fake_dispatch() -> None:
    proof = _run_e2e()
    assert isinstance(proof, Stage30_13_2EndToEndProofResult)

    # Discovery + auto-seed: exactly one fresh pump mint seeded.
    assert proof.seed_proof.auto_seed_result.summary.accepted == 1
    assert proof.seed_proof.seeded_token_mints == (_E2E_PUMP_MINT,)

    # Bridge + dry-run: the discovered summary bridged and reached ONE recorded
    # would-send (a FAKE dispatch), never a real send.
    assert proof.dry_run.inputs.report.bridged == 1
    assert proof.dry_run.report.dispatched == 1
    assert proof.dry_run.report.would_send_recorded == 1
    assert (
        proof.dry_run.report.redaction_status
        == STAGE30_11_22_REDACTION_STATUS_REDACTED
    )
    # No real send.
    assert proof.dry_run.report.attestation.real_send_performed is False
    assert proof.dry_run.report.attestation.real_send_guard_invoked is False
    # The dispatched mint traces to the WS-discovered pump-suffix summary.
    assert proof.dry_run.client.token_mints == [_E2E_PUMP_MINT]


# ---------------------------------------------------------------------------
# 2. The pump-suffix filter gates the end-to-end path
# ---------------------------------------------------------------------------


def test_non_pump_mint_is_filtered_before_any_dispatch() -> None:
    proof = _run_e2e([_ws_msg(_NON_PUMP_MINT)])
    s = proof.seed_proof.auto_seed_result.summary
    assert s.accepted == 0
    assert s.rejected == 1
    assert (
        proof.seed_proof.auto_seed_result.outcomes[0].seed_reason
        == SEED_REASON_NOT_PUMP_SUFFIX
    )
    assert proof.seed_proof.seeded_token_mints == ()
    # Nothing to bridge -> nothing dispatched.
    assert proof.dry_run.inputs.report.bridged == 0
    assert proof.dry_run.report.dispatched == 0
    assert proof.dry_run.report.would_send_recorded == 0
    assert proof.dry_run.client.attempted == 0


# ---------------------------------------------------------------------------
# 3. A malformed capture fails closed end-to-end
# ---------------------------------------------------------------------------


def test_malformed_ws_payload_fails_closed_with_no_dispatch() -> None:
    proof = _run_e2e([b"{not-json"])
    s = proof.seed_proof.auto_seed_result.summary
    assert s.error == 1
    assert s.accepted == 0
    assert (
        proof.seed_proof.auto_seed_result.outcomes[0].seed_reason
        == SEED_REASON_WS_CAPTURE_FAILED
    )
    assert proof.seed_proof.seeded_token_mints == ()
    assert proof.dry_run.report.dispatched == 0
    assert proof.dry_run.report.would_send_recorded == 0
    assert proof.dry_run.client.attempted == 0
