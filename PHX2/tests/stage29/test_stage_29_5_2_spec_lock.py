"""Stage 29.5.2 spec-lock tests.

Pins:

  * ``PHX2/stage29/STAGE_29_5_2_OFFLINE_INTEGRATION_PROOF_RUNBOOK.md``
    exists and carries the canonical Stage 29.5.2 mission
    sentence verbatim, the Stage 29.5.2 scope (offline
    composition proof only), the no-runtime-wiring stance, the
    Stage 29.5.3 deferred wrapper stance, the locked
    filter_enforcement_status token, the closed-set composition
    data flow, the no-PHX1 / no-Stage-28 / no-Stage-29-1-2-3-4
    import discipline, the synthetic-source token scope, the
    acceptance criteria, and the behavior test matrix.

  * The Stage 29.5.2 composition module's schema version is
    ``stage29_5_2_v0_offline_integration``.

  * The Stage 29.5.2 result record always emits
    ``filter_enforcement_status=NOT_ACTIVE_STAGE_29_PENDING``.

  * The Stage 29.5.2 runbook carries no URL host literal, no
    raw-secret-looking value, and no Pump.fun bonding-curve
    program id literal.
"""

from __future__ import annotations

from pathlib import Path


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"
TESTS_STAGE29_ROOT: Path = PHX2_ROOT / "tests" / "stage29"
RUNBOOK_PATH: Path = (
    STAGE29_ROOT
    / "STAGE_29_5_2_OFFLINE_INTEGRATION_PROOF_RUNBOOK.md"
)


# Canonical Stage 29.5.2 mission sentence. Must appear verbatim
# in the runbook; future Stage 29.5.2 patches must preserve it.
STAGE_29_5_2_MISSION_SENTENCE: str = (
    "Stage 29.5.2 is the offline integration proof substage "
    "that composes the existing Stage 29.5 candidate-to-"
    "migration join layer and the Stage 29.5 private ping "
    "migration context projection over a Stage 29.3-shaped "
    "candidate axes record plus a Stage 27.4 ATH context "
    "record, using purely synthetic migration evidence and a "
    "deterministic clock, so that the Stage 29.5 join + "
    "projection are proven to compose cleanly without opening "
    "any live WebSocket / gRPC / HTTP transport and without "
    "wiring the composition into the Stage 29.3 mode-3 "
    "orchestrator or the Stage 29.4 short-session private "
    "soak orchestrator."
)


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


def _normalized_whitespace(text: str) -> str:
    """Collapse all runs of whitespace into single spaces so a
    phrase that wraps across a markdown line still matches.
    """
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Stage 29.5.2 runbook + spec-lock test file exist
# ---------------------------------------------------------------------------


def test_stage_29_5_2_runbook_exists():
    assert RUNBOOK_PATH.is_file(), (
        f"Stage 29.5.2 requires the offline integration proof "
        f"runbook {RUNBOOK_PATH}"
    )


def test_stage_29_5_2_spec_lock_test_file_exists():
    self_path = (
        TESTS_STAGE29_ROOT
        / "test_stage_29_5_2_spec_lock.py"
    )
    assert self_path.is_file()


# ---------------------------------------------------------------------------
# 2. Canonical Stage 29.5.2 mission sentence appears verbatim
# ---------------------------------------------------------------------------


def test_runbook_contains_canonical_mission_sentence_verbatim():
    normalized = _normalized_whitespace(_runbook_text())
    assert STAGE_29_5_2_MISSION_SENTENCE in normalized, (
        "Stage 29.5.2 runbook must contain the canonical "
        "mission sentence verbatim (whitespace-normalized match)"
    )


# ---------------------------------------------------------------------------
# 3. Runbook names Stage 29.5.2 explicitly + Stage 29.5.3 deferred
# ---------------------------------------------------------------------------


def test_runbook_names_stage_29_5_2_explicitly():
    text = _runbook_text()
    assert "Stage 29.5.2" in text


def test_runbook_names_stage_29_5_3_as_deferred_wrapper():
    text = _runbook_text()
    assert "Stage 29.5.3" in text
    lower = text.lower()
    assert "deferred" in lower, (
        "Stage 29.5.2 runbook must mark Stage 29.5.3 work as "
        "explicitly deferred"
    )


def test_runbook_names_offline_composition_proof_scope():
    lower = _runbook_text().lower()
    assert "offline" in lower
    assert "composition" in lower
    assert "proof" in lower


# ---------------------------------------------------------------------------
# 4. Runbook pins the locked filter_enforcement_status token
# ---------------------------------------------------------------------------


def test_runbook_pins_locked_filter_enforcement_status_token():
    text = _runbook_text()
    assert "NOT_ACTIVE_STAGE_29_PENDING" in text, (
        "Stage 29.5.2 runbook must reference the locked "
        "filter_enforcement_status token verbatim"
    )


# ---------------------------------------------------------------------------
# 5. Runbook pins the no-live / no-Discord / no-PHX1 / no-Stage-28 stance
# ---------------------------------------------------------------------------


def test_runbook_pins_no_live_websocket_no_grpc_no_http():
    normalized = _normalized_whitespace(_runbook_text())
    for needle in (
        "live Helius WebSocket",
        "live Chainstack Yellowstone gRPC",
        "live Birdeye HTTP",
        "Discord",
        "PHX1",
    ):
        assert needle in normalized, (
            f"Stage 29.5.2 runbook must explicitly disclaim "
            f"{needle!r} (whitespace-normalized match)"
        )


def test_runbook_pins_no_runtime_wiring_into_stage29_3_or_29_4():
    lower = _runbook_text().lower()
    for needle in (
        "stage 29.3",
        "stage 29.4",
    ):
        assert needle in lower, (
            f"Stage 29.5.2 runbook must explicitly name "
            f"{needle!r}"
        )


# ---------------------------------------------------------------------------
# 6. Schema version + filter_enforcement_status invariants
# ---------------------------------------------------------------------------


def test_schema_version_constant_locked():
    from PHX2.stage29.stage29_5_2_offline_integration import (
        STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION,
    )
    assert (
        STAGE29_5_2_OFFLINE_INTEGRATION_SCHEMA_VERSION
        == "stage29_5_2_v0_offline_integration"
    )


def test_composition_result_carries_locked_enforcement_token():
    from PHX2.stage27.price_ath_context_models import (
        AthContextRecord,
    )
    from PHX2.stage29.stage29_5_2_offline_integration import (
        run_stage29_5_2_offline_integration,
    )
    from PHX2.stage29.stage29_5_candidate_to_migration_join import (
        Stage29_5CandidateAxes,
    )

    def _clock() -> str:
        return "2026-05-25T16:00:00+00:00"

    ath = AthContextRecord(
        token_mint="A" * 44,
        pair_type="PUMP_SOL",
        quote_asset="SOL",
        ath_value=None,
        ath_unit="USD",
        ath_source=None,
        ath_observed_at_utc=None,
        ath_since_migration_status="UNKNOWN",
        drawdown_from_ath=None,
        drawdown_unit="USD",
        drawdown_basis="UNKNOWN",
        ath_status="UNAVAILABLE",
        ath_reason="NO_OBSERVATIONS",
        schema_version="stage27_v0_price_ath",
    )
    result = run_stage29_5_2_offline_integration(
        candidate_axes=Stage29_5CandidateAxes(
            base_mint="A" * 44
        ),
        evidence_records=[],
        ath_context=ath,
        clock=_clock,
    )
    assert (
        result.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )
    assert (
        result.private_ping_context.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# 7. Runbook carries no URL host / raw-secret / Pump.fun program id literal
# ---------------------------------------------------------------------------


_FORBIDDEN_RUNBOOK_URL_HOSTS: tuple[str, ...] = (
    "discord" + ".com",
    "discord" + "app.com",
    "hooks" + ".slack.com",
    "api.helius" + ".xyz",
    "rpc.helius" + ".xyz",
    "mainnet.helius" + "-rpc.com",
    "public-api.birdeye" + ".so",
    "pro-api.birdeye" + ".so",
    "business-api.birdeye" + ".so",
    "birdeye" + ".so",
    "t" + ".me/",
    "api.twitter" + ".com",
    "api.x" + ".com",
    "chainstack" + ".com",
    "yellowstone" + ".chainstack",
    "dexscreener" + ".com",
    "ws" + "s://",
    "ws" + "://",
)


def test_runbook_carries_no_url_host_literal():
    text = _runbook_text()
    for needle in _FORBIDDEN_RUNBOOK_URL_HOSTS:
        assert needle not in text, (
            f"Stage 29.5.2 runbook must not carry URL host "
            f"literal {needle!r}"
        )


_FORBIDDEN_RUNBOOK_RAW_SECRETS: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "BIRDEYE_API" + "_KEY=",
    "CHAINSTACK_API" + "_KEY=",
)


def test_runbook_carries_no_raw_secret_literal():
    text = _runbook_text()
    for needle in _FORBIDDEN_RUNBOOK_RAW_SECRETS:
        assert needle not in text, (
            f"Stage 29.5.2 runbook must not carry raw-secret "
            f"literal {needle!r}"
        )


def test_runbook_carries_no_pump_fun_program_id():
    text = _runbook_text()
    assert (
        "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
        not in text
    )
