"""Stage 30.3 + Stage 29.5.6 wrapper composition test.

Pins the outermost-first wrapper composition contract:

  Stage30_3CompactBodyTransportWrapper      (REPLACES content)
    Stage29_5_6 wrapped transport           (APPENDS migration block)
      fake_inner_transport                  (records final body)

The Stage 30.3 wrapper produces a compact body, the Stage 29.5.6
wrapped transport appends the most recent recorded migration
context block (or its compact fallback) to that compact body,
and the fake inner transport records the final dispatched body.

This is the only Stage 30.3A test allowed to import Stage 29.5.6
modules (per spec). The production Stage 30.3A wrapper / recorder
/ projection / writer modules import zero Stage 29 modules.

Discipline: no env reads, no network, no provider calls, no
operator-channel send. Stdlib + pytest only.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from PHX2.stage27.migration_context_models import (
    MIGRATION_REASON_OK,
    MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
    MIGRATION_STATUS_PRESENT,
    STAGE27_4_MIGRATION_SCHEMA_VERSION,
    MigrationContextRecord,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_REASON_OK,
    ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    ATH_STATUS_PRESENT,
    ATH_UNIT_SOL,
    DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    AthContextRecord,
)
from PHX2.stage29.stage29_5_5_render_models import (
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED,
    STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION,
    Stage29_5_5RenderedMigrationContextBlock,
)
from PHX2.stage29.stage29_5_6_private_ping_migration_context_injector import (
    STAGE29_5_6_CONTENT_MAX_CHARS,
    Stage29_5_6PrivateDiscordBodyInjector,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_SOURCE_HELIUS_WS,
    REDACTION_STATUS_SAFE,
)
from PHX2.stage30.compact_ping_models import (
    STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME,
)
from PHX2.stage30.stage30_3_compact_body_transport_wrapper import (
    Stage30_3CompactBodyTransportWrapper,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    COMPACT_OUTCOME_RENDERED,
    STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION,
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
    Stage30_3CompactRuntimeContext,
    Stage30_3RecordedCandidateContext,
)


# Fake non-WSOL base58-shape token mint string. The Stage 30.3
# composition test deliberately avoids the canonical WSOL mint
# literal so a regression in any Stage 30.3 redaction path cannot
# silently slip the WSOL substring through the boundary scan. The
# canonical WSOL constant is kept only for explicit absence
# assertions on the rendered body and the Stage 30.3 wiring
# artifact.
_SAFE_MINT: str = (
    "FakeMintPhx2NotWso1ForTestBase58222222222222"
)
_WSOL_MINT_LITERAL: str = (
    "So11111111111111111111111111111111111111112"
)
_MIG_TS: str = "2026-05-27T00:00:00Z"
_CLOCK_TS: str = "2026-05-27T00:00:30Z"
_VERBOSE_BODY: str = "Verbose Stage 28.9 operator body. " * 5


# ---------------------------------------------------------------------------
# Stage 29.5.5 rendered block fixture
# ---------------------------------------------------------------------------


def _build_safe_rendered_block() -> Stage29_5_5RenderedMigrationContextBlock:
    return Stage29_5_5RenderedMigrationContextBlock(
        migration_evidence_status_display=(
            MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE
        ),
        migration_evidence_source_trust_display=(
            MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN
        ),
        post_migration_ath_verified_display=(
            POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED
        ),
        migration_timestamp_utc_display="2026-05-27T00:00:00+00:00",
        migration_slot_display="12345",
        migration_source_token=MIGRATION_SOURCE_HELIUS_WS,
        join_status_echoed_token=MIGRATION_JOIN_STATUS_JOINED,
        warnings_display="none",
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_MIG_TS,
        informational_only=True,
        not_a_trading_verdict=True,
        body_text=(
            "Migration evidence: complete\n"
            "Source: trusted on-chain\n"
            "ATH verified: yes\n"
            "informational_only: true\n"
            "not_a_trading_verdict: true"
        ),
        schema_version=(
            STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION
        ),
    )


# ---------------------------------------------------------------------------
# Synthetic Stage 27.4 records for the Stage 30.3 recorded entry
# ---------------------------------------------------------------------------


def _build_ath() -> AthContextRecord:
    return AthContextRecord(
        token_mint=_SAFE_MINT,
        pair_type="PUMPSWAP_AMM",
        quote_asset="SOL",
        ath_value="1.0",
        ath_unit=ATH_UNIT_SOL,
        ath_source="synthetic_test",
        ath_observed_at_utc=_MIG_TS,
        ath_since_migration_status=(
            ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        ),
        drawdown_from_ath="0.55",
        drawdown_unit=ATH_UNIT_SOL,
        drawdown_basis=DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        ath_status=ATH_STATUS_PRESENT,
        ath_reason=ATH_REASON_OK,
        schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _build_migration() -> MigrationContextRecord:
    return MigrationContextRecord(
        token_mint=_SAFE_MINT,
        pair_type="PUMPSWAP_AMM",
        quote_asset="SOL",
        migration_event_id="evt-001",
        migration_timestamp_utc=_MIG_TS,
        migration_source=MIGRATION_SOURCE_ON_CHAIN_MIGRATION_EVENT,
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_reason=MIGRATION_REASON_OK,
        age_since_migration_seconds=30,
        observed_at_utc=_CLOCK_TS,
        source_event_ref="evt-ref-001",
        raw_capture_ref=None,
        schema_version=STAGE27_4_MIGRATION_SCHEMA_VERSION,
    )


def _build_stage30_3_recorder_entry() -> (
    Stage30_3RecordedCandidateContext
):
    return Stage30_3RecordedCandidateContext(
        candidate_id="cand-001",
        mint=_SAFE_MINT,
        ath_record=_build_ath(),
        migration_record=_build_migration(),
        price_status="PRESENT",
        age_since_migration_seconds=30,
        recorded_at_utc=_MIG_TS,
    )


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeStage30_3Recorder:
    """Stage 30.3-shaped duck-typed recorder."""

    def __init__(
        self,
        *,
        entries: tuple,
    ) -> None:
        self._entries = entries

    @property
    def recorded_entries(self) -> tuple:
        return self._entries


class _FakeStage29_5_5Recorder:
    """Stage 29.5.5-shaped duck-typed recorder: each entry exposes
    a ``rendered_block`` attribute the Stage 29.5.6 wrapper reads.
    """

    def __init__(self, *, entries: tuple) -> None:
        self._entries = entries

    @property
    def recorded_entries(self) -> tuple:
        return self._entries


class _FakeOKResult(SimpleNamespace):
    pass


class _RecordingInnerTransport:
    def __init__(self) -> None:
        self.calls: int = 0
        self.received_kwargs: List[Dict[str, Any]] = []

    def send_one_audited_post(
        self, *, webhook_identity: str, payload: object
    ) -> object:
        self.calls += 1
        # Snapshot the payload (shallow copy)
        snapshot: Dict[str, Any] = {}
        if isinstance(payload, dict):
            snapshot = dict(payload)
        self.received_kwargs.append(
            {
                "webhook_identity": webhook_identity,
                "payload": snapshot,
            }
        )
        return _FakeOKResult(ok=True)


class _FakeClock:
    def __init__(self, *, stamps: List[str]) -> None:
        self._stamps = list(stamps)
        self._index = 0

    def now_utc_iso(self) -> str:
        value = self._stamps[self._index]
        self._index += 1
        return value


# ---------------------------------------------------------------------------
# Composition test
# ---------------------------------------------------------------------------


def test_stage30_3_outer_stage29_5_6_inner_composes(
    tmp_path: Path,
) -> None:
    # Stage 29.5.5 rendered block fixture
    rendered_block = _build_safe_rendered_block()
    stage29_5_5_entry = SimpleNamespace(rendered_block=rendered_block)
    stage29_5_5_recorder = _FakeStage29_5_5Recorder(
        entries=(stage29_5_5_entry,)
    )

    # Inner transport at the very innermost layer
    fake_inner_transport = _RecordingInnerTransport()

    # Stage 29.5.6 wrapper
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=stage29_5_5_recorder,
    )
    wrapped_29_5_6 = injector.wrap_transport(fake_inner_transport)

    # Stage 30.3 recorder with one safe entry
    stage30_3_recorder = _FakeStage30_3Recorder(
        entries=(_build_stage30_3_recorder_entry(),)
    )

    # Stage 30.3 wrapper outermost
    context = Stage30_3CompactRuntimeContext(
        session_id="sess-001",
        run_id="run-001",
        basis="price-basis",
        output_dir=tmp_path,
    )
    clock = _FakeClock(stamps=[_CLOCK_TS])
    wrapper_order = (
        WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
        WRAPPER_ORDER_LABEL_STAGE29_5_6_MIGRATION,
        WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    )
    compact_xport = Stage30_3CompactBodyTransportWrapper(
        inner_transport=wrapped_29_5_6,
        recorder=stage30_3_recorder,
        context=context,
        clock=clock,
        wrapper_order=wrapper_order,
    )

    original_payload: Dict[str, Any] = {
        "content": _VERBOSE_BODY,
        "username": "Phoenix Operator",
    }

    compact_xport.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=original_payload,
    )

    # Inner transport received exactly one call.
    assert fake_inner_transport.calls == 1
    inner_payload = fake_inner_transport.received_kwargs[0]["payload"]
    final_content = inner_payload["content"]
    assert final_content.startswith("\U0001f525 PHOENIX")

    # Final content carries the Stage 29.5.6 appended block (either
    # the full rendered body_text OR the compact-fallback header).
    has_full = rendered_block.body_text in final_content
    has_compact_header = "[MIGRATION CONTEXT]" in final_content
    assert has_full or has_compact_header

    # Final content stays within the locked Stage 29.5.6 cap.
    assert len(final_content) <= STAGE29_5_6_CONTENT_MAX_CHARS

    # Non-content payload keys preserved unchanged.
    assert inner_payload["username"] == "Phoenix Operator"

    # Stage 30.2 compact snapshot is just the compact body (no
    # Stage 29.5.6 append).
    compact_snapshot_path = (
        tmp_path / STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    )
    assert compact_snapshot_path.exists()
    compact_lines = [
        json.loads(line)
        for line in compact_snapshot_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line
    ]
    assert len(compact_lines) == 1
    snapshot_body = compact_lines[0]["body_text"]
    assert "[MIGRATION CONTEXT]" not in snapshot_body
    assert rendered_block.body_text not in snapshot_body
    # And the snapshot body is the prefix of the final content.
    assert final_content.startswith(snapshot_body)

    # Stage 30.3 wiring artifact line records the full wrapper order.
    wiring_path = (
        tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    )
    assert wiring_path.exists()
    wiring_lines = [
        json.loads(line)
        for line in wiring_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line
    ]
    assert len(wiring_lines) == 1
    assert wiring_lines[0]["wrapper_order"] == list(wrapper_order)
    assert (
        wiring_lines[0]["compact_outcome"] == COMPACT_OUTCOME_RENDERED
    )

    # Stage 30.3A regression: the test fixture mint is a fake non-
    # WSOL base58 string, so the canonical WSOL literal must not
    # appear anywhere in the rendered body, the wiring artifact,
    # or the Stage 30.2 compact snapshot.
    assert _WSOL_MINT_LITERAL not in final_content
    wiring_text = wiring_path.read_text(encoding="utf-8")
    assert _WSOL_MINT_LITERAL not in wiring_text
    compact_text = compact_snapshot_path.read_text(encoding="utf-8")
    assert _WSOL_MINT_LITERAL not in compact_text

    # Original payload not mutated by either wrapper layer.
    assert original_payload["content"] == _VERBOSE_BODY
    assert original_payload["username"] == "Phoenix Operator"

    # Wrapper counter
    assert compact_xport.outcomes_count(COMPACT_OUTCOME_RENDERED) == 1
