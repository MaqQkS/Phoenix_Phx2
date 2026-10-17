"""Sanitized Helius shadow parity classification and artifact tests."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from PHX2.free_tier_producer import helius_shadow_parity as parity


def _observation(
    provider: str,
    *,
    identity: str = "signature-1",
    slot: int = 100,
    timestamp: str = "2026-07-29T12:00:00Z",
    migration_type: str | None = "migrate_v2",
    mint: str | None = "Mintpump",
    pool: str | None = "Pool111",
    verdict: str = parity.VERDICT_ADMITTED,
    rejection: str | None = None,
    gap_state: str = "NO_GAP",
    recovery_state: str = "NOT_REQUESTED",
) -> parity.ParityObservation:
    return parity.ParityObservation(
        provider_label=provider,
        signature_or_hash=identity,
        slot=slot,
        receive_timestamp=timestamp,
        migration_type=migration_type,
        mint=mint,
        pool=pool,
        local_decoder_verdict=verdict,
        rejection_reason=rejection,
        bytes=100,
        estimated_credits=0.002,
        reconnect_count=1 if provider != parity.PROVIDER_CHAINSTACK else 0,
        gap_state=gap_state,
        recovery_state=recovery_state,
    )


def _pair(chainstack, helius, *, late=5.0):
    accumulator = parity.HeliusShadowParityAccumulator(
        late_match_seconds=late
    )
    assert accumulator.observe(chainstack) is None
    return accumulator.observe(helius)


def test_match_preserves_first_seen_latency_and_metrics() -> None:
    record = _pair(
        _observation(parity.PROVIDER_CHAINSTACK),
        _observation(
            parity.PROVIDER_HELIUS_WSS,
            timestamp="2026-07-29T12:00:01Z",
        ),
    )
    assert record is not None
    assert record.match_status == parity.MATCH
    assert record.first_seen_provider == parity.PROVIDER_CHAINSTACK
    assert record.latency_difference_seconds == 1.0
    assert record.control_slot == 100
    assert record.shadow_slot == 100
    assert record.bytes == 200
    assert record.estimated_credits == pytest.approx(0.004)


@pytest.mark.parametrize(
    ("change", "expected"),
    (
        ({"slot": 101}, parity.SLOT_MISMATCH),
        ({"migration_type": "migrate"}, parity.DECODE_MISMATCH),
        ({"mint": "Otherpump"}, parity.DECODE_MISMATCH),
        ({"pool": "OtherPool"}, parity.DECODE_MISMATCH),
        ({"verdict": parity.VERDICT_REJECTED}, parity.DECODE_MISMATCH),
        ({"rejection": "OTHER_REASON"}, parity.DECODE_MISMATCH),
    ),
)
def test_pair_mismatch_classifications(change, expected: str) -> None:
    record = _pair(
        _observation(parity.PROVIDER_CHAINSTACK),
        _observation(parity.PROVIDER_HELIUS_WSS, **change),
    )
    assert record is not None
    assert record.match_status == expected


def test_late_match_by_latency() -> None:
    record = _pair(
        _observation(parity.PROVIDER_CHAINSTACK),
        _observation(
            parity.PROVIDER_HELIUS_WSS,
            timestamp="2026-07-29T12:00:06Z",
        ),
        late=5,
    )
    assert record is not None
    assert record.match_status == parity.LATE_MATCH


def test_late_match_after_unmatched_was_emitted() -> None:
    accumulator = parity.HeliusShadowParityAccumulator(
        late_match_seconds=60
    )
    chainstack = _observation(parity.PROVIDER_CHAINSTACK)
    assert accumulator.observe(chainstack) is None
    unmatched = accumulator.finalize_unmatched()
    assert len(unmatched) == 1
    assert unmatched[0].match_status == parity.CHAINSTACK_ONLY
    assert accumulator.finalize_unmatched() == ()
    late = accumulator.observe(
        _observation(
            parity.PROVIDER_HELIUS_WSS,
            timestamp="2026-07-29T12:00:01Z",
        )
    )
    assert late is not None
    assert late.match_status == parity.LATE_MATCH


def test_http_pair_is_classified_as_recovered() -> None:
    record = _pair(
        _observation(parity.PROVIDER_CHAINSTACK),
        _observation(parity.PROVIDER_HELIUS_HTTP),
    )
    assert record is not None
    assert record.match_status == parity.RECOVERED_BY_HELIUS_HTTP
    assert record.provider_label == "PROVIDER_A|PROVIDER_B_HTTP"


@pytest.mark.parametrize(
    ("provider", "expected"),
    (
        (parity.PROVIDER_CHAINSTACK, parity.CHAINSTACK_ONLY),
        (parity.PROVIDER_HELIUS_WSS, parity.HELIUS_ONLY),
    ),
)
def test_unmatched_provider_classifications(
    provider: str, expected: str
) -> None:
    accumulator = parity.HeliusShadowParityAccumulator()
    accumulator.observe(_observation(provider))
    records = accumulator.finalize_unmatched()
    assert len(records) == 1
    assert records[0].match_status == expected


def test_open_gap_classifies_unmatched_as_unresolved() -> None:
    accumulator = parity.HeliusShadowParityAccumulator()
    accumulator.observe(
        _observation(
            parity.PROVIDER_HELIUS_WSS,
            gap_state="GAP_DETECTED",
            recovery_state="PARTIAL",
        )
    )
    records = accumulator.finalize_unmatched()
    assert records[0].match_status == parity.UNRESOLVED
    assert records[0].gap_state == "GAP_DETECTED"
    assert records[0].recovery_state == "PARTIAL"


def test_artifact_writer_emits_required_sanitized_schema(tmp_path: Path) -> None:
    record = _pair(
        _observation(parity.PROVIDER_CHAINSTACK),
        _observation(parity.PROVIDER_HELIUS_WSS),
    )
    assert record is not None
    root = tmp_path / "artifacts" / "helius_shadow_parity"
    path = root / "parity.jsonl"
    writer = parity.HeliusParityArtifactWriter(path, allowed_root=root)
    writer.write(record)
    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    payload = json.loads(rows[0])
    assert set(payload) == {
        "provider_label",
        "signature_or_hash",
        "slot",
        "control_slot",
        "shadow_slot",
        "receive_timestamp",
        "migration_type",
        "mint",
        "pool",
        "local_decoder_verdict",
        "rejection_reason",
        "first_seen_provider",
        "latency_difference_seconds",
        "match_status",
        "bytes",
        "estimated_credits",
        "reconnect_count",
        "gap_state",
        "recovery_state",
    }
    lowered = rows[0].lower()
    for forbidden in (
        "http://",
        "https://",
        "wss://",
        "api-key",
        "authorization",
        "chainstack",
        "api_key",
    ):
        assert forbidden not in lowered


def test_artifact_writer_initializes_fresh_empty_artifact(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts" / "helius_shadow_parity"
    path = root / "empty.jsonl"
    writer = parity.HeliusParityArtifactWriter(path, allowed_root=root)
    writer.initialize()
    assert path.read_bytes() == b""
    with pytest.raises(FileExistsError):
        writer.initialize()


def test_artifact_writer_refuses_outside_root_and_unsafe_text(
    tmp_path: Path,
) -> None:
    root = tmp_path / "allowed"
    with pytest.raises(parity.HeliusParityRecordError):
        parity.HeliusParityArtifactWriter(
            tmp_path / "outside.jsonl",
            allowed_root=root,
        )
    with pytest.raises(parity.HeliusParityRecordError):
        _observation(
            parity.PROVIDER_HELIUS_WSS,
            rejection="failed at wss://secret.invalid/?api-key=value",
        )


def test_parity_module_has_no_delivery_ownership_surface() -> None:
    text = inspect.getsource(parity).lower()
    for token in (
        "telegram_transport",
        "telegram_adapter",
        "delivery_transaction",
        "ping_dedupe.jsonl",
        "reserve_delivery",
        "commit_delivery",
    ):
        assert token not in text
