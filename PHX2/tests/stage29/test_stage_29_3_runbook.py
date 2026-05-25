"""Stage 29.3 runbook pins.

The runbook is the operator-facing document for the Stage 29.3
first real private tradeable PHX2 ping ceremony. The test ensures
the operator-critical surfaces (env names, ceremony modes,
closed-set vocabularies, forbidden surfaces, acceptance criteria)
are documented verbatim AND that the doc remains consistent with
the Stage 29.3 production source.
"""

from __future__ import annotations

from pathlib import Path


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
RUNBOOK_PATH: Path = (
    PHX2_ROOT / "stage29"
    / "STAGE_29_3_FIRST_PRIVATE_TRADEABLE_SMOKE_RUNBOOK.md"
)


def _read() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Runbook file existence
# ---------------------------------------------------------------------------


def test_runbook_file_exists():
    assert RUNBOOK_PATH.is_file()


# ---------------------------------------------------------------------------
# Canonical mission sentence
# ---------------------------------------------------------------------------


def test_runbook_contains_canonical_mission_sentence():
    text = _read()
    assert (
        "Stage 29.3 wires the existing Stage 27 / Stage 28.4 "
        "/ Stage 28.6 / Stage 28.9 private dispatch chain to the "
        "Stage 29.1 PumpSwap hint-aware decoder + the Stage 29.2 "
        "Birdeye price / ATH adapter so the operator can drive "
        "exactly one real private tradeable PHX2 ping."
    ) in text


# ---------------------------------------------------------------------------
# Env names (Stage 28.11 + Stage 29.2; zero new env names)
# ---------------------------------------------------------------------------


def test_runbook_lists_stage28_11_env_names():
    text = _read()
    for env_name in (
        "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT",
        "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN",
        "PHX2_STAGE28_11_ALLOW_LIVE_GRPC",
        "PHX2_STAGE28_11_GRPC_TIMEOUT_SECONDS",
    ):
        assert env_name in text, env_name


def test_runbook_lists_stage29_2_env_names():
    text = _read()
    for env_name in (
        "PHX2_STAGE29_2_BIRDEYE_API_KEY",
        "PHX2_STAGE29_2_BIRDEYE_BASE_URL",
        "PHX2_STAGE29_2_ALLOW_LIVE_HTTP",
        "PHX2_STAGE29_2_HTTP_TIMEOUT_SECONDS",
    ):
        assert env_name in text, env_name


def test_runbook_documents_zero_new_env_names():
    text = _read()
    assert "zero new env names" in text.lower()


# ---------------------------------------------------------------------------
# Ceremony modes
# ---------------------------------------------------------------------------


def test_runbook_lists_three_ceremony_modes():
    text = _read()
    for mode in (
        "READINESS_ONLY",
        "CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY",
        "ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN",
    ):
        assert mode in text, mode


# ---------------------------------------------------------------------------
# Acceptance criteria axes
# ---------------------------------------------------------------------------


def test_runbook_lists_mode3_acceptance_axes():
    text = _read()
    for axis in (
        "tradeable_smoke_outcome",
        "tradeable_smoke_refusal_reason",
        "events_seen",
        "candidates_assembled",
        "candidates_dispatched",
        "dispatch_success",
        "dispatch_failure",
        "hint_bearing_payload_present",
        "redaction_status",
        "filter_enforcement_status",
    ):
        assert axis in text, axis


def test_runbook_documents_dispatched_outcome():
    text = _read()
    assert "DISPATCHED" in text


def test_runbook_documents_max_events_1_and_max_dispatches_1():
    text = _read()
    assert "max_events=1" in text or "events_seen` | `1`" in text
    assert (
        "max_dispatches=1" in text
        or "candidates_dispatched` | `1`" in text
    )


# ---------------------------------------------------------------------------
# Forbidden surfaces
# ---------------------------------------------------------------------------


def test_runbook_lists_forbidden_surfaces():
    text = _read()
    for token in (
        "Stage 26 policy enforcement",
        "public routing",
        "subscriber routing",
        "paid",
        "Telegram",
        "X / social",
        "automated trading",
        "wallet",
        "private-key",
        "signer",
        "daemon",
        "watchdog",
        "Dexscreener",
        "Helius",
        "Pump.fun bonding-curve",
        "Phoenix" + "_Bot",
    ):
        assert token in text, token


# ---------------------------------------------------------------------------
# Acceptance artifacts
# ---------------------------------------------------------------------------


def test_runbook_lists_stage29_3_acceptance_artifact_basenames():
    text = _read()
    for basename in (
        "stage29_3_tradeable_smoke_result.json",
        "stage29_3_extracted_hints.json",
        "stage29_3_birdeye_evidence.json",
        "stage29_3_redaction_scan.json",
    ):
        assert basename in text, basename


def test_runbook_lists_stage28_9_companion_basenames():
    text = _read()
    for basename in (
        "stage28_9_dispatch_ledger.jsonl",
        "stage28_9_heartbeat.jsonl",
        "stage28_9_health_snapshot.json",
        "stage28_9_final_run_summary.json",
    ):
        assert basename in text, basename


# ---------------------------------------------------------------------------
# PHX2-replaces-PHX1 acceptance criteria
# ---------------------------------------------------------------------------


def test_runbook_documents_phx2_replaces_phx1_axis():
    text = _read()
    assert "PHX2" in text and "PHX1" in text
    assert "ready to replace PHX1" in text


# ---------------------------------------------------------------------------
# Closed-set vocabulary completeness
# ---------------------------------------------------------------------------


def test_runbook_lists_outcome_vocabulary():
    text = _read()
    for outcome in (
        "DISPATCHED",
        "SUPPRESSED_UNKNOWN_PAIR",
        "SUPPRESSED_DISAGREE_PAIR",
        "SUPPRESSED_USDC_OBSERVE_ONLY",
        "SUPPRESSED_MISSING_PRICE",
        "SUPPRESSED_STALE_PRICE",
        "SUPPRESSED_MALFORMED",
        "NO_EVENT_RECEIVED",
        "READY",
        "CONNECTED",
        "REFUSED",
        "FAILED",
    ):
        assert outcome in text, outcome


def test_runbook_documents_filter_enforcement_pending_marker():
    text = _read()
    assert "NOT_ACTIVE_STAGE_29_PENDING" in text
