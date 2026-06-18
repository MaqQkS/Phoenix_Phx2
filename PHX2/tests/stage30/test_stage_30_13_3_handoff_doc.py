"""Stage 30.13.3 deferred real WS capture handoff-doc tests.

Docs-only substage. Pins that the handoff document exists and carries the required
safety clauses for the future, separate, operator-authorized real read-only Helius WS
capture: read-only / no-send / no-arm / no-durable-ledger / no-gRPC / no-public-routing /
API-key-never-printed / operator-gated / plugs in behind the committed Stage 29.5
transport Protocol / fails closed. Mirrors the committed proof-doc guard pattern
(e.g. test_stage_30_3d_live_proof_doc.py / test_stage_30_4_4_*_doc.py).
"""

from __future__ import annotations

from pathlib import Path


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
HANDOFF_PATH: Path = (
    PHX2_ROOT / "stage30" / "STAGE_30_13_3_REAL_WS_CAPTURE_HANDOFF.md"
)


def _text() -> str:
    return HANDOFF_PATH.read_text(encoding="utf-8")


def test_handoff_doc_exists() -> None:
    assert HANDOFF_PATH.is_file(), (
        f"Stage 30.13.3 requires the handoff document {HANDOFF_PATH}"
    )


def test_handoff_doc_is_docs_only_not_built_not_run() -> None:
    lowered = _text().lower()
    assert "not built" in lowered
    assert "not run" in lowered
    assert "stage 30.13" in lowered


def test_handoff_doc_carries_read_only_no_send_safety_clauses() -> None:
    lowered = _text().lower()
    for clause in (
        "read-only",
        "no send",
        "no real discord",
        "arm",
        "operator-authorized",
        "public",
        "subscriber",
        "grpc",
    ):
        assert clause in lowered, f"handoff doc missing required clause {clause!r}"


def test_handoff_doc_forbids_durable_ledger_and_key_print() -> None:
    lowered = _text().lower()
    assert "durable" in lowered and "ledger" in lowered
    assert "api key" in lowered
    assert "never printed" in lowered
    assert "never committed" in lowered


def test_handoff_doc_names_the_committed_protocol_seam_and_failclosed() -> None:
    text = _text()
    # Plugs in behind the committed Stage 29.5 transport Protocol with no code change.
    assert "Stage29_5WebSocketTransport" in text
    assert "Stage29_5HeliusWebSocketAdapter" in text
    # Fails closed on WS errors via the committed auto-seeder's WS_CAPTURE_FAILED.
    lowered = text.lower()
    assert "fail" in lowered and "closed" in lowered
    assert "WS_CAPTURE_FAILED" in text


def test_handoff_doc_records_the_four_count_ledger() -> None:
    lowered = _text().lower()
    for count in ("accepted", "rejected", "duplicate", "error"):
        assert count in lowered
