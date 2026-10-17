from PHX2.free_tier_producer.launcher_contract import (
    CANONICAL_GAP_RECOVERY_MODE,
    CANONICAL_MIGRATION_SOURCE_MODE,
    canonical_launcher_arguments,
    validate_launcher_arguments,
)
from PHX2.watchdog.launcher_template import (
    render_live_launcher,
    validate_live_launcher_text,
)


HEAD = "a" * 40
BASELINE = ("b" * 64) + ":2928:8"


def test_all_canonical_bounded_launchers_use_helius_live_epoch():
    for launcher in (
        "launch_pressure_24h_01.ps1",
        "launch_soak_02h_01.ps1",
        "launch_window_04.ps1",
    ):
        argv = canonical_launcher_arguments(
            launcher=launcher,
            expected_head=HEAD,
            ledger_baseline=BASELINE,
        )
        assert CANONICAL_GAP_RECOVERY_MODE == "live_epoch"
        assert CANONICAL_MIGRATION_SOURCE_MODE == "HELIUS_PRIMARY"
        # Bounded six-hour DEX candidate recovery is part of the armed
        # contract (2026-07-30 remediation); historical RPC replay below
        # stays absent.
        assert argv.count("--enable-dexscreener-restart-backfill") == 1
        assert "--enable-helius-http-recovery" in argv
        assert "--helius-parity-late-match-seconds" not in argv
        assert not any(token.startswith("--chainstack") for token in argv)
        assert argv[argv.index("--migration-source-mode") + 1] == (
            CANONICAL_MIGRATION_SOURCE_MODE
        )
        assert argv[argv.index("--env") + 1].endswith(
            r"Phoenix_PHX2\.env")
        assert r"C:\Users\BalaC\Documents\phx2.env" not in argv
        assert not any(
            token.startswith("--rpc-recovery-") for token in argv)
        assert validate_launcher_arguments(
            argv, expected_head=HEAD).allowed is True


def test_live_24x7_launcher_has_no_historical_rpc_flags():
    text = render_live_launcher(
        expected_head=HEAD, ledger_baseline=BASELINE)
    assert '"live_epoch"' in text
    assert text.count('"--enable-dexscreener-restart-backfill"') == 1
    assert text.count('"--enable-helius-http-recovery"') == 1
    assert "--rpc-recovery-" not in text
    assert validate_live_launcher_text(
        text, expected_head=HEAD, ledger_baseline=BASELINE) == []


def test_launcher_contract_rejects_historical_rpc_flag():
    argv = canonical_launcher_arguments(
        launcher="launch_pressure_24h_01.ps1",
        expected_head=HEAD,
        ledger_baseline=BASELINE,
    )
    argv.extend(["--rpc-recovery-commitment", "confirmed"])
    verdict = validate_launcher_arguments(argv, expected_head=HEAD)
    assert verdict.allowed is False
    assert "LAUNCHER_HISTORICAL_RPC_FLAG_PRESENT" in verdict.refusals
