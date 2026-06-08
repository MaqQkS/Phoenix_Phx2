"""Stage 30.11.15 fake no-send ping dedupe proof.

Offline only. A thin, transport-AGNOSTIC driver for the committed Stage 30.11.15
deduped orchestrator: it builds an in-memory ping dedupe ledger and composes the
SAME deterministic revalidation request TWICE over that one ledger -- proving
the first no-send compose records a would-send and the second IDENTICAL compose
is suppressed as a duplicate (no runner call, no body, transport_attempts 0)
WITHIN the same ledger, with NO real send.

The ATH source transport (and the now-clock) are injected, NOT built here -- the
stage29-shaped fake Birdeye transport lives in the Stage 30.11.15 test (tests
may build provider fakes), so this committed proof imports NO Stage 29 provider
module and stays inside the closed Stage 30 dependency boundary. It opens NO
socket, reads NO env, sends NO Discord, writes NO file (the proof uses the
in-memory ledger; the JSONL cross-run replay is proven in the dedicated ledger
test on a temp path). The real private compact dispatch / Discord send remains a
SEPARATE, explicitly operator-authorized step this proof does NOT build.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
)
from PHX2.stage30.stage30_11_13_fake_composer_proof import (
    PROOF_CREATED_AT,
    default_proof_request,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
)
from PHX2.stage30.stage30_11_15_no_send_dedupe_guard import (
    Stage30_11_15DedupedComposeResult,
    compose_no_send_dispatch_deduped,
)


@dataclass(frozen=True)
class Stage30_11_15FakeDedupeProofResult:
    """The two deduped compose outcomes + their recording clients + the shared
    ledger, so a test can assert the first records a would-send and the second
    identical compose is suppressed with transport_attempts 0.
    """

    first: Stage30_11_15DedupedComposeResult
    second: Stage30_11_15DedupedComposeResult
    first_client: Stage30_11_5RecordingFakeTransportClient
    second_client: Stage30_11_5RecordingFakeTransportClient
    ledger: Any


def run_stage30_11_15_fake_dedupe_proof(
    *,
    ath_transport: object,
    ath_endpoint_secret: object,
    now_utc: object,
    now_seconds: object,
    request: Optional[Any] = None,
    ledger: Optional[Any] = None,
    ttl_seconds: Optional[int] = None,
) -> Stage30_11_15FakeDedupeProofResult:
    """Run the committed Stage 30.11.15 deduped orchestrator TWICE over ONE
    in-memory ledger with the SAME request; return both outcomes + clients +
    the ledger.

    The first compose reserves the key and records a would-send through the
    recording FAKE client (a RECORDED would-send, NEVER a real send); the second
    IDENTICAL compose finds the key within TTL and is suppressed -- no runner
    call, no body, transport_attempts 0 on its own fresh client.
    """
    effective_request = (
        default_proof_request() if request is None else request
    )
    effective_ledger = (
        InMemoryPingDedupeLedger() if ledger is None else ledger
    )
    ttl_kwargs = {} if ttl_seconds is None else {"ttl_seconds": ttl_seconds}

    first_client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc=PROOF_CREATED_AT
    )
    first = compose_no_send_dispatch_deduped(
        effective_request,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        transport_client=first_client,
        now_seconds=now_seconds,
        ledger=effective_ledger,
        **ttl_kwargs,
    )

    second_client = Stage30_11_5RecordingFakeTransportClient(
        created_at_utc=PROOF_CREATED_AT
    )
    second = compose_no_send_dispatch_deduped(
        effective_request,
        ath_transport=ath_transport,
        ath_endpoint_secret=ath_endpoint_secret,
        now_utc=now_utc,
        transport_client=second_client,
        now_seconds=now_seconds,
        ledger=effective_ledger,
        **ttl_kwargs,
    )

    return Stage30_11_15FakeDedupeProofResult(
        first=first,
        second=second,
        first_client=first_client,
        second_client=second_client,
        ledger=effective_ledger,
    )


__all__ = (
    "Stage30_11_15FakeDedupeProofResult",
    "run_stage30_11_15_fake_dedupe_proof",
)
