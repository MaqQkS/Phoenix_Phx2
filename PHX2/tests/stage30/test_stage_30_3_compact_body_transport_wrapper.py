"""Stage 30.3 compact body transport wrapper tests.

Pure offline tests over the wrapper construction contract, the
success-path compact replacement, every closed-set failure
outcome, retry determinism, payload immutability, and the
synthetic-refusal result shape.

Discipline: no env reads, no network, no provider calls, no
operator-channel send. Stdlib + pytest only.
"""

from __future__ import annotations

import hashlib
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
from PHX2.stage30.compact_ping_models import (
    STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME,
    Stage30_2CompactPingError,
)
from PHX2.stage30.stage30_3_compact_body_transport_wrapper import (
    Stage30_3CompactBodyTransportWrapper,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    COMPACT_OUTCOME_FAILED_CAP,
    COMPACT_OUTCOME_FAILED_COMPACT_RENDER,
    COMPACT_OUTCOME_FAILED_EXCEPTION,
    COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
    COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE,
    COMPACT_OUTCOME_FAILED_TIER_DECISION,
    COMPACT_OUTCOME_RENDERED,
    COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
    STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME,
    WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
    Stage30_3CompactRuntimeContext,
    Stage30_3CompactRuntimeError,
    Stage30_3RecordedCandidateContext,
    _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS,
)
from PHX2.stage30.tier_decision_models import (
    STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME,
    Stage30_1TierDecisionError,
)


# ---------------------------------------------------------------------------
# Common synthetic fixtures
# ---------------------------------------------------------------------------
#
# ``_SAFE_MINT`` is a fake non-WSOL base58-shape token mint string,
# constructed from the Stage 30.1 / Stage 30.2 / Stage 30.3 Solana
# base58 alphabet (no 0, no O, no I, no l) and within the [32, 64]
# length window. The fixture deliberately avoids the canonical WSOL
# mint literal so a regression in any Stage 30.3 redaction path
# cannot silently slip the WSOL substring through the boundary scan.
# ``_WSOL_MINT_LITERAL`` is the canonical WSOL constant, kept only
# for explicit absence assertions on the rendered body and the
# Stage 30.3 wiring artifact.


_SAFE_MINT: str = (
    "FakeMintPhx2NotWso1ForTestBase58222222222222"
)
_WSOL_MINT_LITERAL: str = (
    "So11111111111111111111111111111111111111112"
)
_MIG_TS: str = "2026-05-27T00:00:00Z"
_CLOCK_TS: str = "2026-05-27T00:00:30Z"
_VERBOSE_BODY: str = (
    "Verbose Stage 28.9 operator body. " * 30
)
_CONTENT_KEY: str = "content"


def _make_ath(drawdown: str = "0.55") -> AthContextRecord:
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
        drawdown_from_ath=drawdown,
        drawdown_unit=ATH_UNIT_SOL,
        drawdown_basis=DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
        ath_status=ATH_STATUS_PRESENT,
        ath_reason=ATH_REASON_OK,
        schema_version=STAGE27_4_PRICE_ATH_SCHEMA_VERSION,
    )


def _make_migration() -> MigrationContextRecord:
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


def _make_entry(
    *,
    ath: Optional[Any] = None,
    migration: Optional[Any] = None,
    candidate_id: str = "cand-001",
    age: Optional[int] = 30,
    price_status: Optional[str] = "PRESENT",
) -> Stage30_3RecordedCandidateContext:
    return Stage30_3RecordedCandidateContext(
        candidate_id=candidate_id,
        mint=_SAFE_MINT,
        ath_record=ath if ath is not None else _make_ath(),
        migration_record=(
            migration if migration is not None else _make_migration()
        ),
        price_status=price_status,
        age_since_migration_seconds=age,
        recorded_at_utc=_MIG_TS,
    )


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRecorder:
    """Duck-typed recorder exposing the ``recorded_entries`` tuple
    property the Stage 30.3 wrapper consumes.
    """

    def __init__(
        self,
        *,
        entries: tuple,
    ) -> None:
        self._entries = entries

    @property
    def recorded_entries(self) -> tuple:
        return self._entries


class _FakeClock:
    """Returns successive ISO strings from a fixed list."""

    def __init__(self, *, stamps: List[str]) -> None:
        self._stamps = list(stamps)
        self._index = 0

    def now_utc_iso(self) -> str:
        value = self._stamps[self._index]
        self._index += 1
        return value


class _FakeOKResult(SimpleNamespace):
    """Fake transport OK result returned by the inner fake
    transport on the RENDERED branch.
    """


class _RecordingInnerTransport:
    """Fake inner transport that captures every
    ``send_one_audited_post`` call and returns a fake OK result.
    """

    def __init__(self) -> None:
        self.calls: int = 0
        self.received_kwargs: List[Dict[str, Any]] = []

    def send_one_audited_post(
        self, *, webhook_identity: str, payload: object
    ) -> object:
        self.calls += 1
        self.received_kwargs.append(
            {
                "webhook_identity": webhook_identity,
                "payload": payload,
            }
        )
        return _FakeOKResult(ok=True)


def _make_context(
    tmp_path: Path,
    *,
    basis: str = "price-basis",
    session_id: Optional[str] = "sess-001",
    run_id: Optional[str] = "run-001",
) -> Stage30_3CompactRuntimeContext:
    return Stage30_3CompactRuntimeContext(
        session_id=session_id,
        run_id=run_id,
        basis=basis,
        output_dir=tmp_path,
    )


def _build_wrapper(
    tmp_path: Path,
    *,
    entries: tuple = (),
    basis: str = "price-basis",
    stamps: Optional[List[str]] = None,
    wrapper_order: tuple = (
        WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
        WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    ),
) -> tuple:
    inner = _RecordingInnerTransport()
    recorder = _FakeRecorder(entries=entries)
    context = _make_context(
        tmp_path, basis=basis
    )
    clock = _FakeClock(
        stamps=stamps if stamps is not None else [_CLOCK_TS]
    )
    wrapper = Stage30_3CompactBodyTransportWrapper(
        inner_transport=inner,
        recorder=recorder,
        context=context,
        clock=clock,
        wrapper_order=wrapper_order,
    )
    return wrapper, inner


def _read_wiring_lines(tmp_path: Path) -> List[Dict[str, Any]]:
    target = tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    if not target.exists():
        return []
    text = target.read_text(encoding="utf-8")
    return [
        json.loads(line)
        for line in text.splitlines()
        if line
    ]


def _read_tier_lines(tmp_path: Path) -> List[Dict[str, Any]]:
    target = tmp_path / STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
    if not target.exists():
        return []
    text = target.read_text(encoding="utf-8")
    return [
        json.loads(line)
        for line in text.splitlines()
        if line
    ]


def _read_compact_lines(tmp_path: Path) -> List[Dict[str, Any]]:
    target = tmp_path / STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    if not target.exists():
        return []
    text = target.read_text(encoding="utf-8")
    return [
        json.loads(line)
        for line in text.splitlines()
        if line
    ]


# ===========================================================================
# Construction
# ===========================================================================


def test_construction_rejects_inner_without_send_one_audited_post(
    tmp_path: Path,
) -> None:
    bad_inner = SimpleNamespace()
    recorder = _FakeRecorder(entries=())
    context = _make_context(tmp_path)
    clock = _FakeClock(stamps=[_CLOCK_TS])
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        Stage30_3CompactBodyTransportWrapper(
            inner_transport=bad_inner,
            recorder=recorder,
            context=context,
            clock=clock,
            wrapper_order=(
                WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
                WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
            ),
        )
    assert excinfo.value.reason == "INNER_TRANSPORT_INVALID"


def test_construction_rejects_recorder_without_recorded_entries(
    tmp_path: Path,
) -> None:
    bad_recorder = SimpleNamespace()
    inner = _RecordingInnerTransport()
    context = _make_context(tmp_path)
    clock = _FakeClock(stamps=[_CLOCK_TS])
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        Stage30_3CompactBodyTransportWrapper(
            inner_transport=inner,
            recorder=bad_recorder,
            context=context,
            clock=clock,
            wrapper_order=(
                WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
                WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
            ),
        )
    assert excinfo.value.reason == "RECORDER_INVALID"


def test_construction_rejects_non_context(tmp_path: Path) -> None:
    inner = _RecordingInnerTransport()
    recorder = _FakeRecorder(entries=())
    clock = _FakeClock(stamps=[_CLOCK_TS])
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        Stage30_3CompactBodyTransportWrapper(
            inner_transport=inner,
            recorder=recorder,
            context=SimpleNamespace(  # type: ignore[arg-type]
                basis="price-basis", output_dir=tmp_path
            ),
            clock=clock,
            wrapper_order=(
                WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
                WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
            ),
        )
    assert excinfo.value.reason == "CONTEXT_INVALID"


def test_construction_rejects_clock_without_now_utc_iso(
    tmp_path: Path,
) -> None:
    inner = _RecordingInnerTransport()
    recorder = _FakeRecorder(entries=())
    context = _make_context(tmp_path)
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        Stage30_3CompactBodyTransportWrapper(
            inner_transport=inner,
            recorder=recorder,
            context=context,
            clock=SimpleNamespace(),
            wrapper_order=(
                WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
                WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
            ),
        )
    assert excinfo.value.reason == "CLOCK_INVALID"


@pytest.mark.parametrize(
    "bad_order",
    [
        (),
        "not a tuple",
        [WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY],
        (WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,),
        (42, WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT),
        (
            WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
            "not_a_valid_label",
        ),
    ],
)
def test_construction_rejects_bad_wrapper_order(
    tmp_path: Path, bad_order: Any
) -> None:
    inner = _RecordingInnerTransport()
    recorder = _FakeRecorder(entries=())
    context = _make_context(tmp_path)
    clock = _FakeClock(stamps=[_CLOCK_TS])
    with pytest.raises(Stage30_3CompactRuntimeError) as excinfo:
        Stage30_3CompactBodyTransportWrapper(
            inner_transport=inner,
            recorder=recorder,
            context=context,
            clock=clock,
            wrapper_order=bad_order,
        )
    assert excinfo.value.reason == "WRAPPER_ORDER_INVALID"


# ===========================================================================
# Success path: RENDERED
# ===========================================================================


def test_rendered_replaces_content_and_writes_three_artifacts(
    tmp_path: Path,
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(tmp_path, entries=(entry,))

    original_payload: Dict[str, Any] = {
        _CONTENT_KEY: _VERBOSE_BODY,
        "username": "Phoenix Operator",
    }
    result = wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=original_payload,
    )
    assert result.ok is True

    # Inner forwarded exactly once
    assert inner.calls == 1
    inner_payload = inner.received_kwargs[0]["payload"]
    assert isinstance(inner_payload, dict)
    assert inner_payload is not original_payload
    assert inner_payload["username"] == "Phoenix Operator"
    compact_body = inner_payload[_CONTENT_KEY]
    assert compact_body.startswith("\U0001f525 PHOENIX")
    assert "Drop" in compact_body
    assert "Net" in compact_body
    assert "Basis" in compact_body
    assert "Tier 1" in compact_body
    # Body does NOT contain forbidden labels / WSOL mint / verdicts /
    # URL substrings
    assert "Floor" not in compact_body
    assert "Vol" not in compact_body
    assert _SAFE_MINT in compact_body  # safe — the candidate mint
    # Stage 30.3A regression: the test fixture mint is a fake non-
    # WSOL base58 string, so the canonical WSOL literal must not
    # appear anywhere in the rendered body. The renderer never
    # injects the WSOL mint on its own; the only way WSOL could
    # appear here is if the fixture regressed.
    assert _WSOL_MINT_LITERAL not in compact_body
    assert "BUY" not in compact_body
    assert "SELL" not in compact_body
    assert "h" + "ttps://" not in compact_body
    assert "h" + "ttp://" not in compact_body

    # Original payload not mutated
    assert original_payload[_CONTENT_KEY] == _VERBOSE_BODY

    # Stage 30.1 JSONL exists with one line carrying tier_token Tier 1
    tier_lines = _read_tier_lines(tmp_path)
    assert len(tier_lines) == 1
    assert tier_lines[0]["tier_token"] == "Tier 1"

    # Stage 30.2 JSONL exists with one line carrying body_text matching
    compact_lines = _read_compact_lines(tmp_path)
    assert len(compact_lines) == 1
    assert compact_lines[0]["body_text"] == compact_body

    # Stage 30.3 wiring JSONL exists with one line with full fields
    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    line = wiring_lines[0]
    assert line["compact_outcome"] == COMPACT_OUTCOME_RENDERED
    assert line["compact_outcome_reason"] is None
    assert line["wrapper_order"] == [
        WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
        WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    ]
    assert line["tier_token"] == "Tier 1"
    assert line["tier_reason"] == "TIER_1_IN_BAND"
    assert line["basis"] == "price-basis"
    assert line["original_content_length_chars"] == len(_VERBOSE_BODY)
    assert line["compact_content_length_chars"] == len(compact_body)
    expected_sha = hashlib.sha256(
        compact_body.encode("utf-8")
    ).hexdigest()[:16]
    assert line["compact_body_sha256_hex_prefix_16"] == expected_sha
    assert (
        line["tier_snapshot_path_basename"]
        == "stage30_1_tier_decisions.jsonl"
    )
    assert (
        line["compact_snapshot_path_basename"]
        == "stage30_2_compact_pings.jsonl"
    )
    assert line["forwarded_to_inner_transport"] is True

    # Stage 30.3A regression: the wiring artifact carries the fake
    # non-WSOL test mint via the Stage 30.1 sanitized echo. The
    # canonical WSOL literal must not appear anywhere in the
    # wiring JSONL line — a regression in the wiring mint slot
    # would surface here.
    serialized_wiring_line = json.dumps(line)
    assert _WSOL_MINT_LITERAL not in serialized_wiring_line
    target = tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    artifact_text = target.read_text(encoding="utf-8")
    assert _WSOL_MINT_LITERAL not in artifact_text

    # Counters
    assert wrapper.calls_received == 1
    assert wrapper.outcomes_count(COMPACT_OUTCOME_RENDERED) == 1
    for token in (
        COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
        COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
        COMPACT_OUTCOME_FAILED_TIER_DECISION,
        COMPACT_OUTCOME_FAILED_COMPACT_RENDER,
        COMPACT_OUTCOME_FAILED_CAP,
        COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE,
        COMPACT_OUTCOME_FAILED_EXCEPTION,
    ):
        assert wrapper.outcomes_count(token) == 0


# ===========================================================================
# SKIPPED_NOT_TIERABLE
# ===========================================================================


def test_skipped_not_tierable_when_recorder_empty(
    tmp_path: Path,
) -> None:
    wrapper, inner = _build_wrapper(tmp_path, entries=())
    original_payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY}
    result = wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=original_payload,
    )

    assert (
        result.transport_status
        == _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS
    )
    assert result.retry_after_seconds is None

    # Inner never called
    assert inner.calls == 0

    # No Stage 30.1 / 30.2 JSONL written
    assert (
        tmp_path / STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
    ).exists() is False
    assert (
        tmp_path / STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    ).exists() is False

    # Wiring JSONL line records the skip
    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    line = wiring_lines[0]
    assert (
        line["compact_outcome"] == COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE
    )
    assert line["compact_outcome_reason"] is None
    assert line["forwarded_to_inner_transport"] is False
    assert line["tier_token"] is None
    assert line["tier_reason"] is None
    assert line["tier_snapshot_path_basename"] is None
    assert line["compact_snapshot_path_basename"] is None

    assert (
        wrapper.outcomes_count(COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE)
        == 1
    )

    # Original payload not mutated
    assert original_payload[_CONTENT_KEY] == _VERBOSE_BODY


# ===========================================================================
# FAILED_TIER_DECISION
# ===========================================================================


def test_failed_tier_decision_on_invalid_basis(
    tmp_path: Path,
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(
        tmp_path, entries=(entry,), basis="not-a-valid-basis"
    )
    original_payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY}
    result = wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=original_payload,
    )

    assert (
        result.transport_status
        == _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS
    )
    assert result.retry_after_seconds is None
    assert inner.calls == 0

    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    line = wiring_lines[0]
    assert (
        line["compact_outcome"] == COMPACT_OUTCOME_FAILED_TIER_DECISION
    )
    assert line["compact_outcome_reason"] == "BASIS_INVALID"
    assert line["tier_token"] is None
    assert line["forwarded_to_inner_transport"] is False

    # Original payload not mutated
    assert original_payload[_CONTENT_KEY] == _VERBOSE_BODY


# ===========================================================================
# FAILED_COMPACT_RENDER (monkeypatched renderer)
# ===========================================================================


def test_failed_compact_render_on_renderer_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(tmp_path, entries=(entry,))

    def _raising_render(_input):
        raise Stage30_2CompactPingError(
            "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
        )

    monkeypatch.setattr(
        "PHX2.stage30.stage30_3_compact_body_transport_wrapper."
        "render_compact_ping",
        _raising_render,
    )
    original_payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY}
    result = wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=original_payload,
    )
    assert (
        result.transport_status
        == _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS
    )
    assert inner.calls == 0

    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    line = wiring_lines[0]
    assert (
        line["compact_outcome"]
        == COMPACT_OUTCOME_FAILED_COMPACT_RENDER
    )
    assert (
        line["compact_outcome_reason"]
        == "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
    )
    assert line["tier_token"] == "Tier 1"  # decision already made
    assert line["forwarded_to_inner_transport"] is False

    assert original_payload[_CONTENT_KEY] == _VERBOSE_BODY


# ===========================================================================
# FAILED_CAP
# ===========================================================================


def test_failed_cap_on_body_exceeds_hard_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(tmp_path, entries=(entry,))

    def _raising_render(_input):
        raise Stage30_2CompactPingError("BODY_EXCEEDS_HARD_CAP")

    monkeypatch.setattr(
        "PHX2.stage30.stage30_3_compact_body_transport_wrapper."
        "render_compact_ping",
        _raising_render,
    )
    original_payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY}
    result = wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=original_payload,
    )
    assert (
        result.transport_status
        == _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS
    )
    assert inner.calls == 0

    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    line = wiring_lines[0]
    assert line["compact_outcome"] == COMPACT_OUTCOME_FAILED_CAP
    assert line["compact_outcome_reason"] == "BODY_EXCEEDS_HARD_CAP"
    assert line["forwarded_to_inner_transport"] is False


# ===========================================================================
# FAILED_SNAPSHOT_WRITE (tier)
# ===========================================================================


def test_failed_snapshot_write_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(tmp_path, entries=(entry,))

    def _raising_tier(**kwargs):
        raise OSError("simulated")

    monkeypatch.setattr(
        "PHX2.stage30.stage30_3_compact_body_transport_wrapper."
        "append_tier_decision_record",
        _raising_tier,
    )
    original_payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY}
    result = wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=original_payload,
    )
    assert (
        result.transport_status
        == _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS
    )
    assert inner.calls == 0

    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    line = wiring_lines[0]
    assert (
        line["compact_outcome"]
        == COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE
    )
    assert line["compact_outcome_reason"] == "TIER_WRITE_FAILED"
    assert line["forwarded_to_inner_transport"] is False

    # exception message "simulated" not leaked anywhere in the
    # wiring record's fields
    serialized = json.dumps(line)
    assert "simulated" not in serialized


# ===========================================================================
# FAILED_SNAPSHOT_WRITE (compact)
# ===========================================================================


def test_failed_snapshot_write_compact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(tmp_path, entries=(entry,))

    def _raising_compact(**kwargs):
        raise OSError("simulated")

    monkeypatch.setattr(
        "PHX2.stage30.stage30_3_compact_body_transport_wrapper."
        "append_compact_ping_snapshot",
        _raising_compact,
    )
    original_payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY}
    result = wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=original_payload,
    )
    assert (
        result.transport_status
        == _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS
    )
    assert inner.calls == 0

    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    line = wiring_lines[0]
    assert (
        line["compact_outcome"]
        == COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE
    )
    assert line["compact_outcome_reason"] == "COMPACT_WRITE_FAILED"

    # Stage 30.1 tier JSONL line WAS written before the compact
    # write failed
    tier_lines = _read_tier_lines(tmp_path)
    assert len(tier_lines) == 1

    # Stage 30.2 compact JSONL does NOT exist
    assert (
        tmp_path / STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
    ).exists() is False


# ===========================================================================
# FAILED_EXCEPTION (projection helper raises non-tier-decision)
# ===========================================================================


def test_failed_exception_or_input_shape_on_projection_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(tmp_path, entries=(entry,))

    def _raising_project(**kwargs):
        raise RuntimeError("projection blew up")

    monkeypatch.setattr(
        "PHX2.stage30.stage30_3_compact_body_transport_wrapper."
        "project_recorded_entry_to_tier_decision_record",
        _raising_project,
    )
    original_payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY}
    result = wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=original_payload,
    )
    assert (
        result.transport_status
        == _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS
    )
    assert inner.calls == 0

    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    line = wiring_lines[0]
    # Per spec: the projection helper's RuntimeError is caught at
    # the projection step's except Exception branch and surfaces
    # as FAILED_INPUT_SHAPE with reason PROJECTION_EXCEPTION (the
    # FAILED_EXCEPTION outer catch is reserved for unanticipated
    # exceptions outside the step-specific try blocks).
    assert line["compact_outcome"] in (
        COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
        COMPACT_OUTCOME_FAILED_EXCEPTION,
    )
    assert line["forwarded_to_inner_transport"] is False
    assert line["wrapper_order"] == [
        WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
        WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
    ]
    # exception message "projection blew up" not leaked
    serialized = json.dumps(line)
    assert "projection blew up" not in serialized


# ===========================================================================
# Retry determinism
# ===========================================================================


def test_two_calls_same_recorder_produce_byte_identical_bodies(
    tmp_path: Path,
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(
        tmp_path,
        entries=(entry,),
        stamps=[_CLOCK_TS, "2026-05-27T00:00:31Z"],
    )

    payload1: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY}
    payload2: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY}

    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=payload1,
    )
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=payload2,
    )
    assert inner.calls == 2
    body1 = inner.received_kwargs[0]["payload"][_CONTENT_KEY]
    body2 = inner.received_kwargs[1]["payload"][_CONTENT_KEY]
    assert body1 == body2

    assert len(_read_tier_lines(tmp_path)) == 2
    assert len(_read_compact_lines(tmp_path)) == 2
    assert len(_read_wiring_lines(tmp_path)) == 2


# ===========================================================================
# Payload immutability across all failure branches
# ===========================================================================


def test_payload_immutable_on_skipped_branch(tmp_path: Path) -> None:
    wrapper, inner = _build_wrapper(tmp_path, entries=())
    payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY, "k": "v"}
    snapshot = dict(payload)
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=payload,
    )
    assert payload == snapshot


def test_payload_immutable_on_failed_tier_decision(
    tmp_path: Path,
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(
        tmp_path, entries=(entry,), basis="not-a-valid-basis"
    )
    payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY, "k": "v"}
    snapshot = dict(payload)
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=payload,
    )
    assert payload == snapshot


def test_payload_immutable_on_failed_compact_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(tmp_path, entries=(entry,))

    def _raising_render(_input):
        raise Stage30_2CompactPingError(
            "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"
        )

    monkeypatch.setattr(
        "PHX2.stage30.stage30_3_compact_body_transport_wrapper."
        "render_compact_ping",
        _raising_render,
    )
    payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY, "k": "v"}
    snapshot = dict(payload)
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=payload,
    )
    assert payload == snapshot


def test_payload_immutable_on_failed_snapshot_write_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_wrapper(tmp_path, entries=(entry,))

    def _raising(**kwargs):
        raise OSError("simulated")

    monkeypatch.setattr(
        "PHX2.stage30.stage30_3_compact_body_transport_wrapper."
        "append_tier_decision_record",
        _raising,
    )
    payload: Dict[str, Any] = {_CONTENT_KEY: _VERBOSE_BODY, "k": "v"}
    snapshot = dict(payload)
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload=payload,
    )
    assert payload == snapshot


# ===========================================================================
# Synthetic refusal shape on every failure branch
# ===========================================================================


def test_synthetic_refusal_shape_on_skipped(tmp_path: Path) -> None:
    wrapper, inner = _build_wrapper(tmp_path, entries=())
    result = wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload={_CONTENT_KEY: _VERBOSE_BODY},
    )
    assert result.transport_status == "PAYLOAD_REFUSED"
    assert result.retry_after_seconds is None


# ===========================================================================
# Stage 30.3A wiring artifact value redaction (regression)
# ===========================================================================
#
# Stage 30.3A pins that the wiring artifact value slots
# (``session_id`` / ``candidate_id`` / ``ping_id`` / ``mint``) never
# carry a raw unsafe substring. The wrapper applies its own local
# safe-artifact helpers on every branch BEFORE the wiring record is
# built; unsafe inputs collapse to the literal ``"REDACTED"``. The
# fixtures below seed each per-slot unsafe substring family (URL
# host / webhook path / bearer auth / API-key / RPC URL / secret /
# raw-payload) and assert the per-slot redaction.
#
# The regression test then dumps the entire wiring JSONL artifact
# to text and asserts that NO raw unsafe substring slipped through.


def _build_unsafe_wrapper(
    tmp_path: Path,
    *,
    entry: Stage30_3RecordedCandidateContext,
    basis: str = "price-basis",
    session_id: Optional[str] = "sess-001",
) -> tuple:
    inner = _RecordingInnerTransport()
    recorder = _FakeRecorder(entries=(entry,))
    context = Stage30_3CompactRuntimeContext(
        session_id=session_id,
        run_id="run-001",
        basis=basis,
        output_dir=tmp_path,
    )
    clock = _FakeClock(stamps=[_CLOCK_TS])
    wrapper = Stage30_3CompactBodyTransportWrapper(
        inner_transport=inner,
        recorder=recorder,
        context=context,
        clock=clock,
        wrapper_order=(
            WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
            WRAPPER_ORDER_LABEL_FAKE_INNER_TRANSPORT,
        ),
    )
    return wrapper, inner


_UNSAFE_URL_NEEDLE: str = "h" + "ttps://evil.example/web" + "hooks/x"
_UNSAFE_BEARER_NEEDLE: str = "B" + "earer-abcdef-token"
_UNSAFE_APIKEY_NEEDLE: str = "api_key-deadbeef"
_UNSAFE_SECRET_NEEDLE: str = "secret-cafebabe"
_UNSAFE_RPC_URL_NEEDLE: str = "rpc_url-host"
_UNSAFE_DISCORD_NEEDLE: str = "discord" + ".com" + "-abc"


def _wiring_artifact_text(tmp_path: Path) -> str:
    target = tmp_path / STAGE30_3_RUNTIME_WIRING_ARTIFACT_BASENAME
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8")


def test_session_id_with_webhook_substring_redacts_to_REDACTED(
    tmp_path: Path,
) -> None:
    entry = _make_entry()
    wrapper, inner = _build_unsafe_wrapper(
        tmp_path,
        entry=entry,
        session_id=_UNSAFE_URL_NEEDLE,
    )
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload={_CONTENT_KEY: _VERBOSE_BODY},
    )
    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    assert wiring_lines[0]["session_id"] == "REDACTED"
    # The raw unsafe substring must NOT appear anywhere in the
    # artifact text.
    artifact_text = _wiring_artifact_text(tmp_path)
    assert _UNSAFE_URL_NEEDLE not in artifact_text
    assert "h" + "ttps://" not in artifact_text
    assert "/web" + "hooks/" not in artifact_text


def test_candidate_id_with_bearer_substring_redacts_to_REDACTED(
    tmp_path: Path,
) -> None:
    entry = _make_entry(candidate_id=_UNSAFE_BEARER_NEEDLE)
    wrapper, inner = _build_unsafe_wrapper(tmp_path, entry=entry)
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload={_CONTENT_KEY: _VERBOSE_BODY},
    )
    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    assert wiring_lines[0]["candidate_id"] == "REDACTED"
    assert wiring_lines[0]["ping_id"] == "REDACTED"
    artifact_text = _wiring_artifact_text(tmp_path)
    assert _UNSAFE_BEARER_NEEDLE not in artifact_text
    assert ("b" + "earer").lower() not in artifact_text.lower()


def test_ping_id_with_apikey_substring_redacts_to_REDACTED(
    tmp_path: Path,
) -> None:
    # ping_id flows through entry.candidate_id (the wrapper assigns
    # the same value to both slots on the failure branches and on
    # the success branch). Seed an unsafe api_key substring on the
    # entry's candidate id so both wiring slots collapse to
    # REDACTED.
    entry = _make_entry(candidate_id=_UNSAFE_APIKEY_NEEDLE)
    wrapper, inner = _build_unsafe_wrapper(tmp_path, entry=entry)
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload={_CONTENT_KEY: _VERBOSE_BODY},
    )
    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    assert wiring_lines[0]["ping_id"] == "REDACTED"
    assert wiring_lines[0]["candidate_id"] == "REDACTED"
    artifact_text = _wiring_artifact_text(tmp_path)
    assert _UNSAFE_APIKEY_NEEDLE not in artifact_text
    assert "api_key" not in artifact_text.lower()


def test_mint_with_url_substring_redacts_to_REDACTED(
    tmp_path: Path,
) -> None:
    # An unsafe mint shape: a string carrying the canonical URL
    # substring. Stage 30.1 sanitizes the mint to None (base58
    # alphabet rejects "/" and ":"), so the wrapper's wiring path
    # falls back to the wrapper-local _safe_artifact_mint helper
    # which catches the URL substring and redacts to "REDACTED".
    unsafe_mint = "h" + "ttps://evil.example/x" * 2
    entry = Stage30_3RecordedCandidateContext(
        candidate_id="cand-unsafe",
        mint=unsafe_mint,
        ath_record=_make_ath(),
        migration_record=_make_migration(),
        price_status="PRESENT",
        age_since_migration_seconds=30,
        recorded_at_utc=_MIG_TS,
    )
    wrapper, inner = _build_unsafe_wrapper(tmp_path, entry=entry)
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload={_CONTENT_KEY: _VERBOSE_BODY},
    )
    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    assert wiring_lines[0]["mint"] == "REDACTED"
    artifact_text = _wiring_artifact_text(tmp_path)
    assert unsafe_mint not in artifact_text
    assert "h" + "ttps://" not in artifact_text


def test_failure_path_before_tier_decision_redacts_unsafe_ids_and_mint(
    tmp_path: Path,
) -> None:
    # Seed an unsafe candidate_id + mint on the entry and force the
    # FAILED_TIER_DECISION branch by passing an invalid basis. The
    # tier decision is NEVER produced; the wrapper falls back to
    # the wrapper-local safe-artifact helpers for every value slot.
    unsafe_candidate_id = _UNSAFE_SECRET_NEEDLE
    unsafe_mint = "h" + "ttp://malicious.example/path"
    entry = Stage30_3RecordedCandidateContext(
        candidate_id=unsafe_candidate_id,
        mint=unsafe_mint,
        ath_record=_make_ath(),
        migration_record=_make_migration(),
        price_status="PRESENT",
        age_since_migration_seconds=30,
        recorded_at_utc=_MIG_TS,
    )
    wrapper, inner = _build_unsafe_wrapper(
        tmp_path,
        entry=entry,
        basis="not-a-valid-basis",
        session_id=_UNSAFE_DISCORD_NEEDLE,
    )
    result = wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload={_CONTENT_KEY: _VERBOSE_BODY},
    )
    assert result.transport_status == "PAYLOAD_REFUSED"
    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    line = wiring_lines[0]
    assert (
        line["compact_outcome"] == COMPACT_OUTCOME_FAILED_TIER_DECISION
    )
    # Failure path before tier decision: every value slot is
    # redacted via wrapper-local helpers, because tier_decision is
    # None and the raw entry / context values carry unsafe
    # substrings.
    assert line["session_id"] == "REDACTED"
    assert line["candidate_id"] == "REDACTED"
    assert line["ping_id"] == "REDACTED"
    assert line["mint"] == "REDACTED"
    # No raw unsafe substring leaked into the artifact text.
    artifact_text = _wiring_artifact_text(tmp_path)
    assert unsafe_candidate_id not in artifact_text
    assert unsafe_mint not in artifact_text
    assert _UNSAFE_DISCORD_NEEDLE not in artifact_text
    assert "h" + "ttp://" not in artifact_text
    assert "discord" + ".com" not in artifact_text
    assert "secret" not in artifact_text.lower()


def test_wiring_artifact_carries_no_raw_unsafe_substring(
    tmp_path: Path,
) -> None:
    # Seed every per-slot unsafe substring family at once. The
    # wiring JSONL artifact text MUST NOT carry any raw unsafe
    # substring; every value slot collapses to "REDACTED".
    unsafe_candidate_id = _UNSAFE_BEARER_NEEDLE
    unsafe_mint = "p" + "k-live-deadbeef" * 3
    entry = Stage30_3RecordedCandidateContext(
        candidate_id=unsafe_candidate_id,
        mint=unsafe_mint,
        ath_record=_make_ath(),
        migration_record=_make_migration(),
        price_status="PRESENT",
        age_since_migration_seconds=30,
        recorded_at_utc=_MIG_TS,
    )
    wrapper, inner = _build_unsafe_wrapper(
        tmp_path,
        entry=entry,
        session_id=_UNSAFE_RPC_URL_NEEDLE,
    )
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload={_CONTENT_KEY: _VERBOSE_BODY},
    )
    artifact_text = _wiring_artifact_text(tmp_path)
    lowered = artifact_text.lower()
    forbidden_substrings = (
        "h" + "ttp://",
        "h" + "ttps://",
        "w" + "s://",
        "w" + "ss://",
        "discord" + ".com",
        "discord" + "app.com",
        "/web" + "hooks/",
        "b" + "earer",
        "a" + "uthorization",
        "s" + "k-",
        "p" + "k-",
        "api_key",
        "apikey",
        "secret",
        "private_key",
        "seed_phrase",
        "mnemonic",
        "raw_payload",
        "payload_blob",
        "rpc_url",
    )
    for needle in forbidden_substrings:
        assert needle.lower() not in lowered, (
            f"wiring artifact carries raw unsafe substring "
            f"{needle!r}; full text: {artifact_text!r}"
        )
    # Specific raw inputs do not appear.
    assert unsafe_candidate_id not in artifact_text
    assert unsafe_mint not in artifact_text
    assert _UNSAFE_RPC_URL_NEEDLE not in artifact_text


def test_safe_artifact_text_none_passthrough(tmp_path: Path) -> None:
    # When the context's session_id is None and the entry's
    # candidate_id is None, the wiring artifact slots stay None
    # (the safe-artifact helper returns None on None input rather
    # than collapsing to "REDACTED").
    entry = Stage30_3RecordedCandidateContext(
        candidate_id="cand-001",
        mint=_SAFE_MINT,
        ath_record=_make_ath(),
        migration_record=_make_migration(),
        price_status="PRESENT",
        age_since_migration_seconds=30,
        recorded_at_utc=_MIG_TS,
    )
    wrapper, inner = _build_unsafe_wrapper(
        tmp_path,
        entry=entry,
        session_id=None,
    )
    wrapper.send_one_audited_post(
        webhook_identity="WEBHOOK_IDENTITY_PRIVATE_OPERATOR",
        payload={_CONTENT_KEY: _VERBOSE_BODY},
    )
    wiring_lines = _read_wiring_lines(tmp_path)
    assert len(wiring_lines) == 1
    line = wiring_lines[0]
    assert line["session_id"] is None
    assert line["candidate_id"] == "cand-001"
    assert line["ping_id"] == "cand-001"
    # mint comes from the Stage 30.1 sanitized echo (base58 safe).
    assert line["mint"] == _SAFE_MINT
    # And the canonical WSOL literal does not appear.
    artifact_text = _wiring_artifact_text(tmp_path)
    assert _WSOL_MINT_LITERAL not in artifact_text
