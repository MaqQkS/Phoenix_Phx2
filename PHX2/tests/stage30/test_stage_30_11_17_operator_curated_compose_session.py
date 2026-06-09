"""Stage 30.11.17 operator-curated compose session behaviour tests.

Offline / fake-provider only. Proves the bounded session:

  * enforces the candidate cap (list-length) + the composition cap, and raises on
    an out-of-cap config;
  * drives ``compose_no_send_dispatch_deduped`` once per eligible curated entry
    until a cap, reaching ONLY the injected FAKE recording client (a recorded
    would-send, never a real send);
  * classifies per-entry outcomes into dispatched / rejected / dedupe-blocked /
    error;
  * shares ONE injected ledger so a within-run duplicate is suppressed, and uses
    the caller-injected ledger across sessions;
  * rolls up a redaction-safe summary with a stop reason + reconciling counts;
  * never references the operator ceremony ledger path.

The stage29-shaped fake Birdeye transport lives HERE (a test may build a provider
fake). No real send, no network, no env read, no wallet, no trading, no Stage
30.11.16 guard, no live provider.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Mapping

import pytest

from PHX2.stage29.birdeye_constants import (
    BIRDEYE_PATH_OHLCV,
    BIRDEYE_PATH_PRICE,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
    Stage29_2BirdeyeHttpTransport,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
)
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    make_constant_clock,
)
from PHX2.stage30.stage30_11_5_fake_live_wiring_proof import (
    Stage30_11_5RecordingFakeTransportClient,
)
from PHX2.stage30.stage30_11_13_committed_no_send_composer import (
    COMPOSE_DECISION_DISPATCHED,
    COMPOSE_REJECTED_DEDUPE_SUPPRESSED,
    COMPOSE_REJECTED_DEDUPE_UNAVAILABLE,
    COMPOSE_REJECTED_MARKET_CONTEXT_MISSING,
)
from PHX2.stage30.stage30_11_13_fake_composer_proof import (
    PROOF_CREATED_AT,
    PROOF_CURRENT_PRICE,
    PROOF_LATER_LOWER,
    PROOF_MINT,
    PROOF_PEAK_ATH,
    default_proof_request,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_ledger import (
    InMemoryPingDedupeLedger,
    JsonlPingDedupeLedger,
)
from PHX2.stage30.stage30_11_15_ping_dedupe_models import (
    DEDUPE_VERDICT_ALLOWED,
    DEDUPE_VERDICT_SUPPRESSED_DUPLICATE,
    DEDUPE_VERDICT_UNAVAILABLE,
)
from PHX2.stage30.stage30_11_17_operator_curated_candidate_list_models import (
    ENTRY_OUTCOME_DEDUPE_BLOCKED,
    ENTRY_OUTCOME_DISPATCHED,
    ENTRY_OUTCOME_ERROR,
    ENTRY_OUTCOME_REJECTED,
    STAGE30_11_17_REDACTED_UNSAFE_ID,
    STAGE30_11_17_REDACTION_STATUS_REDACTED,
    STOP_REASON_CANDIDATE_CAP,
    STOP_REASON_COMPLETED,
    STOP_REASON_COMPOSITION_CAP,
    Stage30_11_17OperatorCuratedCandidate,
    Stage30_11_17SessionConfig,
    default_session_config,
)
from PHX2.stage30.stage30_11_17_operator_curated_compose_session import (
    Stage30_11_17OperatorCuratedSessionError,
    run_stage30_11_17_operator_curated_compose_session,
)


# A second VALID, render-able base58 mint (the proof mint with a changed prefix;
# NOT the WSOL / quote mint the Stage 30.12 renderer fails closed on) -- mirrors
# the committed Stage 30.11.15 test ``_OTHER_MINT``.
_OTHER_MINT: str = "Fx8km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"

_GOOD_KEY: str = "abcd1234efgh5678ijkl9012mnop3456"
_GOOD_URL: str = "https://aaaa-bbbb.example"
_FETCHED_AT: str = "2026-06-07T07:06:40+00:00"


def _now_utc() -> datetime:
    return datetime(2026, 6, 7, 7, 6, 40, tzinfo=timezone.utc)


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _price_body() -> dict:
    return {
        "success": True,
        "data": {
            "value": PROOF_CURRENT_PRICE,
            "updateUnixTime": int(_now_utc().timestamp()),
        },
    }


def _ohlcv_body_with_peak() -> dict:
    return {
        "success": True,
        "data": {
            "items": [
                {"h": PROOF_PEAK_ATH, "unixTime": _unix("2026-06-06T06:15:00Z")},
                {"h": PROOF_LATER_LOWER, "unixTime": _unix("2026-06-06T07:30:00Z")},
            ]
        },
    }


class FakeComposerBirdeyeTransport(Stage29_2BirdeyeHttpTransport):
    """Path-routed (mint-agnostic) fake Birdeye transport. Opens NO socket."""

    def __init__(self, *, fetched_at_utc: str = _FETCHED_AT) -> None:
        self._fetched_at_utc = fetched_at_utc
        self.calls: list = []

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        self.calls.append({"path": path})
        if path == BIRDEYE_PATH_PRICE:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
                http_status_code=200,
                body=_price_body(),
                fetched_at_utc=self._fetched_at_utc,
            )
        if path == BIRDEYE_PATH_OHLCV:
            return Stage29_2BirdeyeHttpResult(
                refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
                http_status_code=200,
                body=_ohlcv_body_with_peak(),
                fetched_at_utc=self._fetched_at_utc,
            )
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_HTTP_TIMEOUT,
            http_status_code=0,
            body=None,
            fetched_at_utc=self._fetched_at_utc,
        )


def _endpoint_secret() -> Stage29_2BirdeyeEndpointSecret:
    return Stage29_2BirdeyeEndpointSecret(_api_key=_GOOD_KEY, _base_url=_GOOD_URL)


def _rec_client() -> Stage30_11_5RecordingFakeTransportClient:
    return Stage30_11_5RecordingFakeTransportClient(created_at_utc=PROOF_CREATED_AT)


def _curated(request, label=None) -> Stage30_11_17OperatorCuratedCandidate:
    return Stage30_11_17OperatorCuratedCandidate(
        request=request, curated_label=label
    )


def _request_with(**overrides):
    return replace(default_proof_request(), **overrides)


def _run(
    candidates,
    *,
    config=None,
    ledger=None,
    transport_client=None,
    ath_transport=None,
    **kwargs,
):
    return run_stage30_11_17_operator_curated_compose_session(
        candidates,
        config=(
            default_session_config(created_at_utc=PROOF_CREATED_AT)
            if config is None
            else config
        ),
        ledger=InMemoryPingDedupeLedger() if ledger is None else ledger,
        ath_transport=(
            FakeComposerBirdeyeTransport()
            if ath_transport is None
            else ath_transport
        ),
        ath_endpoint_secret=_endpoint_secret(),
        now_utc=_now_utc(),
        transport_client=_rec_client() if transport_client is None else transport_client,
        now_seconds=make_constant_clock(Decimal(0)),
        **kwargs,
    )


# ===========================================================================
# 1. Cap enforcement + config validation
# ===========================================================================


def test_candidate_list_length_cap_enforced() -> None:
    candidates = [_curated(default_proof_request()) for _ in range(5)]
    config = Stage30_11_17SessionConfig(
        max_candidates=3, max_compositions=3, created_at_utc=PROOF_CREATED_AT
    )
    result = _run(candidates, config=config)
    assert result.candidates_seen == 3
    assert result.compositions_attempted == 3
    assert len(result.events) == 3
    assert result.stop_reason == STOP_REASON_CANDIDATE_CAP


def test_composition_cap_enforced() -> None:
    candidates = [_curated(default_proof_request()) for _ in range(5)]
    config = Stage30_11_17SessionConfig(
        max_candidates=5, max_compositions=2, created_at_utc=PROOF_CREATED_AT
    )
    result = _run(candidates, config=config)
    assert result.compositions_attempted == 2
    assert len(result.events) == 2
    assert result.stop_reason == STOP_REASON_COMPOSITION_CAP


def test_out_of_cap_config_raises_before_composing() -> None:
    bad_configs = (
        Stage30_11_17SessionConfig(
            max_candidates=11, max_compositions=11, created_at_utc=PROOF_CREATED_AT
        ),
        Stage30_11_17SessionConfig(
            max_candidates=5, max_compositions=6, created_at_utc=PROOF_CREATED_AT
        ),
        Stage30_11_17SessionConfig(
            max_candidates=0, max_compositions=0, created_at_utc=PROOF_CREATED_AT
        ),
    )
    for config in bad_configs:
        client = _rec_client()
        with pytest.raises(Stage30_11_17OperatorCuratedSessionError):
            run_stage30_11_17_operator_curated_compose_session(
                [_curated(default_proof_request())],
                config=config,
                ledger=InMemoryPingDedupeLedger(),
                ath_transport=FakeComposerBirdeyeTransport(),
                ath_endpoint_secret=_endpoint_secret(),
                now_utc=_now_utc(),
                transport_client=client,
                now_seconds=make_constant_clock(Decimal(0)),
            )
        # Nothing was composed on the out-of-bounds config.
        assert client.attempted == 0


def test_empty_list_completes_with_zero_counts() -> None:
    result = _run([])
    assert result.candidates_seen == 0
    assert result.compositions_attempted == 0
    assert result.events == ()
    assert result.stop_reason == STOP_REASON_COMPLETED
    assert result.redaction_status == STAGE30_11_17_REDACTION_STATUS_REDACTED


# ===========================================================================
# 2. Mixed session: dispatched / dedupe-blocked / rejected + reconciling counts
# ===========================================================================


def test_mixed_session_outcomes_and_counts_reconcile() -> None:
    ledger = InMemoryPingDedupeLedger()
    client = _rec_client()
    candidates = [
        _curated(default_proof_request(), "DIP_A"),                  # DISPATCHED
        _curated(default_proof_request(), "DIP_A_DUP"),              # DEDUPE_BLOCKED
        _curated(_request_with(market_context_status="MISSING"), "BAD_MC"),  # REJECTED
        _curated(_request_with(token_mint=_OTHER_MINT), "DIP_B"),    # DISPATCHED
    ]
    result = _run(candidates, ledger=ledger, transport_client=client)

    assert result.stop_reason == STOP_REASON_COMPLETED
    assert result.candidates_seen == 4
    assert result.compositions_attempted == 4
    assert result.dispatched == 2
    assert result.dedupe_blocked == 1
    assert result.rejected == 1
    assert result.errors == 0
    # Counts reconcile to compositions_attempted.
    assert (
        result.dispatched
        + result.dedupe_blocked
        + result.rejected
        + result.errors
        == result.compositions_attempted
    )

    outcomes = [e.outcome for e in result.events]
    assert outcomes == [
        ENTRY_OUTCOME_DISPATCHED,
        ENTRY_OUTCOME_DEDUPE_BLOCKED,
        ENTRY_OUTCOME_REJECTED,
        ENTRY_OUTCOME_DISPATCHED,
    ]

    # The rejected entry's reason is the market-context fail-closed (NOT a dedupe).
    assert result.events[2].compose_reason == COMPOSE_REJECTED_MARKET_CONTEXT_MISSING
    # The dedupe-blocked entry carries the suppress verdict + reason.
    assert result.events[1].dedupe_verdict == DEDUPE_VERDICT_SUPPRESSED_DUPLICATE
    assert result.events[1].compose_reason == COMPOSE_REJECTED_DEDUPE_SUPPRESSED
    # The dispatched entries carry the allow verdict + the dispatched decision.
    assert result.events[0].compose_decision == COMPOSE_DECISION_DISPATCHED
    assert result.events[0].dedupe_verdict == DEDUPE_VERDICT_ALLOWED
    assert result.redaction_status == STAGE30_11_17_REDACTION_STATUS_REDACTED


# ===========================================================================
# 3. No real send: only the fake recording client is ever reached
# ===========================================================================


def test_no_real_send_only_fake_recording_client_reached() -> None:
    client = _rec_client()
    result = _run([_curated(default_proof_request())], transport_client=client)
    assert result.dispatched == 1
    assert result.would_send_recorded == 1
    # The would-send is a RECORDED fake attempt, never a real send.
    assert client.attempted == 1
    assert client.token_mints == [PROOF_MINT]
    assert result.events[0].transport_attempts == 1
    assert result.events[0].body_present is True
    # The event carries NO body text / url / secret -- only a body_present bool.
    assert not hasattr(result.events[0], "dispatched_body")
    assert not hasattr(result.events[0], "body")


def test_would_send_recorded_equals_dispatched_and_client_attempts() -> None:
    client = _rec_client()
    candidates = [
        _curated(default_proof_request()),                 # DISPATCHED
        _curated(_request_with(token_mint=_OTHER_MINT)),   # DISPATCHED
        _curated(_request_with(market_context_status="MISSING")),  # REJECTED
    ]
    result = _run(candidates, transport_client=client)
    assert result.dispatched == 2
    assert result.would_send_recorded == 2
    assert client.attempted == 2


# ===========================================================================
# 4. Shared / caller-injected ledger
# ===========================================================================


def test_shared_ledger_blocks_duplicate_within_same_session() -> None:
    # Two identical curated entries in ONE session over ONE shared ledger.
    result = _run(
        [_curated(default_proof_request()), _curated(default_proof_request())]
    )
    assert result.dispatched == 1
    assert result.dedupe_blocked == 1
    assert result.events[0].outcome == ENTRY_OUTCOME_DISPATCHED
    assert result.events[1].outcome == ENTRY_OUTCOME_DEDUPE_BLOCKED


def test_caller_injected_ledger_is_used_across_sessions() -> None:
    ledger = InMemoryPingDedupeLedger()
    first = _run([_curated(default_proof_request())], ledger=ledger)
    assert first.dispatched == 1
    # Re-running an identical entry over the SAME injected ledger is suppressed:
    # the caller-injected ledger's reservation persisted (it was actually used).
    second = _run([_curated(default_proof_request())], ledger=ledger)
    assert second.dispatched == 0
    assert second.dedupe_blocked == 1


def test_compose_called_once_per_eligible_entry_until_cap() -> None:
    # Three distinct-mint entries, composition cap of 2 -> exactly two compose
    # calls (two events), the third never composed.
    candidates = [
        _curated(default_proof_request()),
        _curated(_request_with(token_mint=_OTHER_MINT)),
        _curated(_request_with(token_mint=PROOF_MINT, candidate_id="cand_extra")),
    ]
    config = Stage30_11_17SessionConfig(
        max_candidates=3, max_compositions=2, created_at_utc=PROOF_CREATED_AT
    )
    result = _run(candidates, config=config)
    assert result.compositions_attempted == 2
    assert len(result.events) == 2
    assert result.stop_reason == STOP_REASON_COMPOSITION_CAP


# ===========================================================================
# 5. Error outcome (fail-closed dedupe-unavailable)
# ===========================================================================


def test_error_outcome_on_corrupt_ledger(tmp_path) -> None:
    path = tmp_path / "ledger.jsonl"
    path.write_text("corrupt\n", encoding="utf-8")
    client = _rec_client()
    result = _run(
        [_curated(default_proof_request())],
        ledger=JsonlPingDedupeLedger(path=path),
        transport_client=client,
    )
    assert result.errors == 1
    assert result.dispatched == 0
    assert result.events[0].outcome == ENTRY_OUTCOME_ERROR
    assert result.events[0].compose_reason == COMPOSE_REJECTED_DEDUPE_UNAVAILABLE
    assert result.events[0].dedupe_verdict == DEDUPE_VERDICT_UNAVAILABLE
    # No would-send was recorded on the fail-closed dedupe surface.
    assert client.attempted == 0
    assert result.would_send_recorded == 0


# ===========================================================================
# 6. Redaction
# ===========================================================================


def test_unsafe_curated_label_is_redacted_not_echoed() -> None:
    bad_label = "https://evil.example/webhooks/x?token=abc"
    result = _run([_curated(default_proof_request(), bad_label)])
    assert result.events[0].curated_label == STAGE30_11_17_REDACTED_UNSAFE_ID
    # The raw url never appears in any event field.
    for text in (
        result.events[0].curated_label,
        result.events[0].candidate_id,
        result.events[0].token_mint,
    ):
        assert "://" not in text
        assert "evil.example" not in text
    assert result.redaction_status == STAGE30_11_17_REDACTION_STATUS_REDACTED


def test_safe_curated_label_is_echoed() -> None:
    result = _run([_curated(default_proof_request(), "DIP_WATCH_1")])
    assert result.events[0].curated_label == "DIP_WATCH_1"
    assert result.events[0].token_mint == PROOF_MINT


# ===========================================================================
# 7. The operator ceremony ledger path is never referenced
# ===========================================================================


def test_session_source_never_references_operator_ceremony_ledger() -> None:
    from pathlib import Path

    stage30 = Path(__file__).resolve().parent.parent.parent / "stage30"
    for basename in (
        "stage30_11_17_operator_curated_candidate_list_models.py",
        "stage30_11_17_operator_curated_compose_session.py",
        "stage30_11_17_fake_curated_session_proof.py",
    ):
        text = (stage30 / basename).read_text(encoding="utf-8").lower()
        assert "phx2_one_send_ceremony" not in text
        assert "ping_dedupe.jsonl" not in text
