"""Stage 30.11.13 fake committed no-send composer proof.

Offline only. A thin, transport-AGNOSTIC driver for the committed Stage
30.11.13 composer: it bundles the deterministic default revalidation request
+ a committed Stage 30.11.5 recording FAKE dispatch client, and composes one
no-send dispatch over an INJECTED ATH source transport + endpoint secret +
now-clock (a FAKE in every committed proof; a real Birdeye transport at a
future, separately operator-authorized ceremony). It returns the
``(Stage30_11_13ComposeResult, recording_client)`` so a test can assert ONE
immutable revalidation snapshot drove BOTH the dip-gate PASS and the PHOENIX
body, with NO real send.

The ATH source transport (and the now-clock) are injected, NOT built here:
the stage29-shaped fake Birdeye transport lives in the Stage 30.11.13 test
(tests may build provider fakes), so this committed proof imports NO Stage 29
provider module and stays inside the closed Stage 27 / Stage 30 dependency
boundary. It opens NO socket, reads NO env, sends NO Discord, and writes NO
file. The real private compact dispatch / Discord send remains a SEPARATE,
explicitly operator-authorized step this proof does NOT build.
"""

from __future__ import annotations

from typing import Optional, Tuple

from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
)
from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    Stage30_11_13ComposeResult,
    Stage30_11_13RevalidationRequest,
    compose_no_send_dispatch,
)


# Real migrated Pump.fun mint (matches the Stage 30.11.11 fixtures + prior
# ceremonies); a safe-shape base58 the committed Stage 30.12 renderer accepts.
PROOF_MINT: str = "Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
PROOF_CANDIDATE_ID: str = "stage30_11_13_cand_dip"
PROOF_SYMBOL: str = "PHX"
PROOF_MIGRATION_SOURCE: str = "stage30_11_13_proof_anchor"

PROOF_MIGRATION_ANCHOR: str = "2026-06-06T06:14:10Z"
PROOF_CREATED_AT: str = "2026-06-07T07:06:40Z"

# Coherent with the fake source's price body (built in the test) so the ATH-MC
# inference uses the same current price the source measured the drawdown against.
PROOF_CURRENT_PRICE: str = "0.000003053202401565669"
PROOF_PEAK_ATH: str = "0.000028368813970331733"   # the real early peak
PROOF_LATER_LOWER: str = "0.0000133474"           # the clipped-window value
PROOF_MARKET_CAP_USD: str = "9100"
PROOF_LIQUIDITY_USD: str = "6900"
PROOF_AGE_DISPLAY: str = "~24h"


def default_proof_request(
    *,
    current_price: str = PROOF_CURRENT_PRICE,
    current_market_cap_usd: str = PROOF_MARKET_CAP_USD,
    liquidity_usd: Optional[str] = PROOF_LIQUIDITY_USD,
) -> Stage30_11_13RevalidationRequest:
    """Build the deterministic default revalidation request."""
    return Stage30_11_13RevalidationRequest(
        token_mint=PROOF_MINT,
        candidate_id=PROOF_CANDIDATE_ID,
        migration_time_utc=PROOF_MIGRATION_ANCHOR,
        current_price=current_price,
        current_market_cap_usd=current_market_cap_usd,
        created_at_utc=PROOF_CREATED_AT,
        migration_confirmed=True,
        symbol_or_name=PROOF_SYMBOL,
        migration_source=PROOF_MIGRATION_SOURCE,
        liquidity_usd=liquidity_usd,
        age_display=PROOF_AGE_DISPLAY,
    )


def run_stage30_11_13_fake_composer_proof(
    *,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    now_seconds: object,
    request: Optional[Stage30_11_13RevalidationRequest] = None,
    transport_client: Optional[Stage30_11_5RecordingFakeTransportClient] = None,
) -> Tuple[
    Stage30_11_13ComposeResult,
    Stage30_11_5RecordingFakeTransportClient,
]:
    """Run the committed Stage 30.11.13 composer over the INJECTED ATH source
    transport + a recording FAKE dispatch client; return
    ``(result, transport_client)``.

    The default request is composed through the committed Stage 30.11.11
    anchored ATH source (built INSIDE the composer over ``ath_transport``) ->
    Stage 30.11.10 resolver -> Stage 30.1 tier -> Stage 30.4.1 ATH-MC -> ONE
    immutable snapshot -> Stage 30.11.7 enrichment -> Stage 30.11.5 runner ->
    Stage 30.9.3 dip gate -> Stage 30.11.3 sink -> the snapshot-bound Stage
    30.12 PHOENIX body -> the recording FAKE client (a RECORDED would-send,
    NEVER a real send).
    """
    effective_request = default_proof_request() if request is None else request
    effective_client = (
        Stage30_11_5RecordingFakeTransportClient(
            created_at_utc=PROOF_CREATED_AT
        )
        if transport_client is None
        else transport_client
    )
    result = compose_no_send_dispatch(
        effective_request,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        transport_client=effective_client,
        now_seconds=now_seconds,
    )
    return result, effective_client


__all__ = (
    "PROOF_MINT",
    "PROOF_CANDIDATE_ID",
    "PROOF_MIGRATION_ANCHOR",
    "PROOF_CREATED_AT",
    "PROOF_CURRENT_PRICE",
    "PROOF_PEAK_ATH",
    "PROOF_LATER_LOWER",
    "PROOF_MARKET_CAP_USD",
    "PROOF_LIQUIDITY_USD",
    "default_proof_request",
    "run_stage30_11_13_fake_composer_proof",
)
