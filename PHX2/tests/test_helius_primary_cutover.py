from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from PHX2.free_tier_producer import free_tier_session as session
from PHX2.free_tier_producer import helius_primary_parity as primary_parity
from PHX2.free_tier_producer import helius_source
from PHX2.free_tier_producer.helius_shadow_parity import (
    CHAINSTACK_ONLY,
    DECODE_MISMATCH,
    HELIUS_ONLY,
    LATE_MATCH,
    MATCH,
    PROVIDER_CHAINSTACK,
    PROVIDER_HELIUS_WSS,
    SLOT_MISMATCH,
    HeliusShadowParityAccumulator,
    ParityObservation,
)
from PHX2.free_tier_producer.launcher_contract import (
    CANONICAL_MIGRATION_SOURCE_MODE,
    canonical_launcher_arguments,
    validate_launcher_arguments,
)
from PHX2.free_tier_producer.paid_provider import (
    DISCOVERY_PROVENANCE_HELIUS,
    event_to_candidate,
)
from PHX2.free_tier_producer.source_continuity import SourceContinuityTracker
from PHX2.models.market_data_source import (
    MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION,
)
from PHX2.stage28.chainstack_yellowstone_models import build_normalized_event
from PHX2.watchdog.launcher_template import (
    render_live_launcher,
    validate_live_launcher_text,
)


HEAD = "a" * 40
BASELINE = ("b" * 64) + ":8797:24"
MINT = "7YttLkHDoNj9wyDur5U4DqA4AwT3N8X9psJf7GmZpump"
POOL = "8YttLkHDoNj9wyDur5U4DqA4AwT3N8X9psJf7GmZpump"
QUOTE = "So11111111111111111111111111111111111111112"


@pytest.mark.parametrize(
    ("mode", "authority", "chainstack_shadow", "helius_shadow"),
    [
        (helius_source.CHAINSTACK_PRIMARY, "CHAINSTACK", False, False),
        (
            helius_source.HELIUS_PRIMARY_CHAINSTACK_SHADOW,
            "HELIUS",
            True,
            False,
        ),
        (helius_source.HELIUS_PRIMARY, "HELIUS", False, False),
    ],
)
def test_all_source_modes_have_one_authoritative_owner(
    mode: str,
    authority: str,
    chainstack_shadow: bool,
    helius_shadow: bool,
) -> None:
    selection = helius_source.load_source_selection(
        {helius_source.MIGRATION_SOURCE_ENV: mode},
        explicit_mode=mode,
    )
    assert selection.authoritative_source == authority
    assert selection.chainstack_shadow_enabled is chainstack_shadow
    assert selection.helius_shadow_enabled is helius_shadow
    assert selection.candidate_pipeline_owners == 1
    assert selection.telegram_owners == 1
    assert selection.delivery_owner_count == 1
    assert selection.paid_ledger_writers == 1


def test_source_mode_missing_unsupported_and_mismatch_refuse() -> None:
    with pytest.raises(helius_source.HeliusSourceConfigurationError):
        helius_source.load_source_selection({})
    with pytest.raises(helius_source.HeliusSourceConfigurationError):
        helius_source.load_source_selection(
            {helius_source.MIGRATION_SOURCE_ENV: "AUTO"}
        )
    with pytest.raises(helius_source.HeliusSourceConfigurationError):
        helius_source.load_source_selection(
            {helius_source.MIGRATION_SOURCE_ENV: helius_source.HELIUS_SHADOW}
        )
    with pytest.raises(helius_source.HeliusSourceConfigurationError):
        helius_source.load_source_selection(
            {
                helius_source.MIGRATION_SOURCE_ENV:
                    helius_source.CHAINSTACK_PRIMARY
            },
            explicit_mode=helius_source.HELIUS_PRIMARY,
        )


def _helius_primary_plan():
    selection = helius_source.load_source_selection(
        {
            helius_source.MIGRATION_SOURCE_ENV:
                helius_source.HELIUS_PRIMARY
        },
        explicit_mode=helius_source.HELIUS_PRIMARY,
    )
    return helius_source.build_production_source_runtime_plan(
        selection,
        http_recovery_enabled=True,
    )


def test_helius_only_runtime_plan_constructs_no_chainstack_surface() -> None:
    plan = _helius_primary_plan()
    assert plan.construct_helius_source is True
    assert plan.construct_helius_http_recovery is True
    assert plan.construct_chainstack_source is False
    assert plan.construct_chainstack_grpc_channel is False
    assert plan.construct_chainstack_comparator is False
    assert plan.construct_parity_monitor is False
    assert plan.construct_chainstack_artifact_writer is False
    assert plan.resolve_chainstack_credentials is False
    assert plan.use_chainstack_source_health is False
    assert plan.source_owner_count == 1
    assert plan.candidate_pipeline_owners == 1
    assert plan.telegram_owners == 1
    assert plan.delivery_owner_count == 1
    assert plan.paid_ledger_writers == 1


def test_helius_only_status_projection_is_explicit_and_current_run_only() -> None:
    status = _helius_primary_plan().status_projection()
    assert status == {
        "primary_migration_source": "HELIUS",
        "primary_recovery": "HELIUS_HTTP",
        "recovery_authority": "HELIUS_HTTP",
        "shadow_source": "DISABLED",
        "chainstack_configured_for_runtime": False,
        "chainstack_connected": False,
        "chainstack_comparator": False,
        "chainstack_source_health_enabled": False,
        "candidate_authority": "HELIUS",
        "source_owner_count": 1,
        "candidate_pipeline_owners": 1,
        "telegram_owners": 1,
        "delivery_owner_count": 1,
        "paid_ledger_writers": 1,
    }


def test_helius_only_preflight_never_calls_chainstack_readiness() -> None:
    calls = {"chainstack": 0, "birdeye": 0}

    def forbidden_chainstack():
        calls["chainstack"] += 1
        raise AssertionError("Chainstack readiness must remain unread")

    def ready_birdeye():
        calls["birdeye"] += 1
        return SimpleNamespace(status="READY")

    result = session._detect_paid_preflight_readiness(  # noqa: SLF001
        _helius_primary_plan(),
        chainstack_detector=forbidden_chainstack,
        birdeye_detector=ready_birdeye,
    )
    assert calls == {"chainstack": 0, "birdeye": 1}
    assert result == {
        "chainstack_status": "DISABLED",
        "chainstack_ready": True,
        "birdeye_status": "READY",
        "birdeye_ready": True,
    }


def test_helius_config_reads_only_canonical_names_not_legacy_alias() -> None:
    class TrackingEnvironment(Mapping):
        def __init__(self):
            self.values = {
                "HELIUS_API_KEY": "test-key",
                "HELIUS_RPC_URL": "https://example.test",
                "HELIUS_WS_URL": "wss://example.test",
                "HELIUS_GRPC_ENDPOINT": "must-remain-unread",
            }
            self.lookups = []

        def __getitem__(self, key):
            self.lookups.append(key)
            return self.values[key]

        def __iter__(self):
            return iter(self.values)

        def __len__(self):
            return len(self.values)

        def __contains__(self, key):
            self.lookups.append(key)
            return key in self.values

        def get(self, key, default=None):
            self.lookups.append(key)
            return self.values.get(key, default)

    environ = TrackingEnvironment()
    config = helius_source.load_helius_source_config(environ=environ)
    assert isinstance(config, helius_source.HeliusSourceConfig)
    assert "HELIUS_GRPC_ENDPOINT" not in environ.lookups


def test_helius_only_dotenv_projection_leaves_chainstack_values_unresolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    for name in (
        *session._HELIUS_ONLY_DISABLED_ENV_NAMES,  # noqa: SLF001
        "HELIUS_API_KEY",
        "HELIUS_RPC_URL",
        "HELIUS_WS_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join((
            "HELIUS_API_KEY=test-key",
            "HELIUS_RPC_URL=https://example.test",
            "HELIUS_WS_URL=wss://example.test",
            "PHX2_CHAINSTACK_YELLOWSTONE_GRPC_ENDPOINT=must-remain-unread",
            "PHX2_CHAINSTACK_YELLOWSTONE_X_TOKEN=must-remain-unread",
            "HELIUS_GRPC_ENDPOINT=must-remain-unread",
        )),
        encoding="utf-8",
    )
    loaded = session._load_env_file_for_source_mode(  # noqa: SLF001
        str(env_path),
        helius_source.HELIUS_PRIMARY,
    )
    assert loaded == 3
    assert all(
        name not in session.os.environ
        for name in session._HELIUS_ONLY_DISABLED_ENV_NAMES  # noqa: SLF001
    )


def test_helius_primary_factory_constructs_wss_and_http_recovery_offline() -> None:
    config = helius_source.load_helius_source_config(
        environ={
            "HELIUS_API_KEY": "test-key",
            "HELIUS_RPC_URL": "https://example.test",
            "HELIUS_WS_URL": "wss://example.test",
        }
    )
    factory = helius_source.build_helius_primary_source_factory(
        config=config,
        continuity=SourceContinuityTracker(),
    )
    source = factory()
    assert isinstance(source, helius_source.HeliusEnhancedWssSource)
    assert source._gap_recoverer is not None  # noqa: SLF001
    assert type(source._gap_recoverer).__name__ == (  # noqa: SLF001
        "HeliusSlotGapRecoverer"
    )


def test_helius_primary_contract_requires_config_recovery_and_tight_filter() -> None:
    selection = helius_source.load_source_selection(
        {
            helius_source.MIGRATION_SOURCE_ENV:
                helius_source.HELIUS_PRIMARY
        }
    )
    broad = helius_source.approved_tight_subscription_request(1)
    broad["params"][0]["accountRequired"] = broad["params"][0][
        "accountRequired"
    ][:1]
    verdict = helius_source.validate_production_source_contract(
        selection=selection,
        helius_configured=False,
        http_recovery_enabled=False,
        subscription_request=broad,
        send_authority_count=2,
        chainstack_candidate_authority=True,
        chainstack_comparator_enabled=True,
    )
    assert set(verdict.refusals) == {
        "HELIUS_CONFIGURATION_REQUIRED",
        "HELIUS_HTTP_RECOVERY_REQUIRED",
        "HELIUS_TIGHT_FILTER_REQUIRED",
        "SINGLE_SEND_AUTHORITY_REQUIRED",
        "HELIUS_ONLY_CHAINSTACK_RUNTIME_FORBIDDEN",
    }
    missing_filter = helius_source.validate_production_source_contract(
        selection=selection,
        helius_configured=True,
        http_recovery_enabled=True,
        subscription_request={},
    )
    assert missing_filter.refusals == ("HELIUS_TIGHT_FILTER_REQUIRED",)


def test_helius_event_projects_to_authoritative_candidate_labels() -> None:
    event = build_normalized_event(
        event_id="helius_sig",
        provider_event_id="sig",
        provider_name=helius_source.HELIUS_SOURCE_IDENTITY,
        mint=MINT,
        event_type="migration",
        observed_at_utc="2026-07-30T12:00:00Z",
        raw_event_hash="helius_" + ("c" * 64),
        quote_mint=QUOTE,
        pool_account=POOL,
        pool_program_id=helius_source.PUMPSWAP_PROGRAM_ID,
        base_mint=MINT,
    )
    candidate = event_to_candidate(event)
    assert candidate is not None
    assert candidate["discovery_provider"] == "HELIUS_PRIMARY"
    assert candidate["discovery_provenance"] == DISCOVERY_PROVENANCE_HELIUS
    assert candidate["current_data_source"] == (
        MARKET_DATA_SOURCE_PAID_MARKET_AND_LIVE_MIGRATION
    )


def test_chainstack_shadow_has_zero_production_authority_or_delivery_imports() -> None:
    comparator = primary_parity.ChainstackShadowComparator
    assert comparator.candidate_authority is False
    assert comparator.canonical_state_authority is False
    assert comparator.source_recovery_authority is False
    assert comparator.send_authority is False
    assert comparator.reservation_authority is False
    assert comparator.ledger_authority is False

    tree = ast.parse(inspect.getsource(primary_parity))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith("PHX2.delivery") for name in imported)
    assert not any("ledger" in name.lower() for name in imported)


def test_production_parity_ignores_non_migration_source_diagnostics(
    tmp_path: Path,
) -> None:
    monitor = primary_parity.ProductionParityMonitor(
        output_path=tmp_path / "parity.jsonl",
        allowed_root=tmp_path,
        now_fn=lambda: "2026-07-30T12:01:00Z",
    )
    monitor.observe_helius_decoder(
        {
            "signature_or_hash": "ordinary_pump_transaction",
            "slot": 100,
            "receive_timestamp": "2026-07-30T12:00:00Z",
            "migration_type": None,
            "mint": None,
            "pool": None,
            "local_decoder_verdict": "REJECTED",
            "rejection_reason": "NOT_MIGRATION",
            "bytes": 100,
            "estimated_credits": 0.00001,
            "migration_comparison_scope": False,
        },
        reconnect_count=0,
        gap_state="NO_GAP",
        recovery_state="NOT_REQUESTED",
    )
    assert monitor.snapshot()["records"] == 0
    assert (tmp_path / "parity.jsonl").read_text(encoding="utf-8") == ""


def test_chainstack_shadow_compares_only_proven_migration_rejections() -> None:
    records = []

    class Monitor:
        def observe(self, record) -> None:
            records.append(record)

    comparator = primary_parity.ChainstackShadowComparator(
        monitor=Monitor(),  # type: ignore[arg-type]
    )
    base = {
        "transaction_signature": "chainstack_signature",
        "slot": 100,
        "reason_codes": ["LOCAL_DECODER_REJECTED"],
        "migration_version": None,
        "token_mint": MINT,
        "pool": POOL,
    }
    comparator._rejection({  # type: ignore[attr-defined]
        **base,
        "classification": "DIRECT_POOL",
    })
    assert records == []
    comparator._rejection({  # type: ignore[attr-defined]
        **base,
        "classification": "MIGRATION_CPI",
    })
    assert len(records) == 1


def _observation(
    provider: str,
    *,
    signature: str = "sig",
    slot: int = 100,
    timestamp: str = "2026-07-30T12:00:00Z",
    mint: str = MINT,
    verdict: str = "ADMITTED",
) -> ParityObservation:
    return ParityObservation(
        provider_label=provider,
        signature_or_hash=signature,
        slot=slot,
        receive_timestamp=timestamp,
        migration_type="migrate_v2",
        mint=mint,
        pool=POOL,
        local_decoder_verdict=verdict,
        rejection_reason=None,
        bytes=100,
        estimated_credits=0.00001,
    )


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda item: item, MATCH),
        (lambda item: replace(item, slot=101), SLOT_MISMATCH),
        (lambda item: replace(item, mint=QUOTE), DECODE_MISMATCH),
        (
            lambda item: replace(
                item,
                receive_timestamp="2026-07-30T12:00:06Z",
            ),
            LATE_MATCH,
        ),
    ],
)
def test_primary_shadow_parity_pair_classifications(mutator, expected) -> None:
    accumulator = HeliusShadowParityAccumulator(late_match_seconds=5)
    assert accumulator.observe(
        _observation(PROVIDER_HELIUS_WSS)
    ) is None
    record = accumulator.observe(
        mutator(_observation(PROVIDER_CHAINSTACK))
    )
    assert record is not None
    assert record.match_status == expected


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        (PROVIDER_CHAINSTACK, CHAINSTACK_ONLY),
        (PROVIDER_HELIUS_WSS, HELIUS_ONLY),
    ],
)
def test_primary_shadow_unmatched_classifications(provider, expected) -> None:
    accumulator = HeliusShadowParityAccumulator(late_match_seconds=5)
    accumulator.observe(_observation(provider))
    records = accumulator.finalize_expired(
        now_timestamp="2026-07-30T12:00:06Z"
    )
    assert [record.match_status for record in records] == [expected]


def test_launcher_requires_exact_cutover_mode_and_http_recovery() -> None:
    argv = canonical_launcher_arguments(
        launcher="launch_pressure_24h_01.ps1",
        expected_head=HEAD,
        ledger_baseline=BASELINE,
    )
    assert argv[argv.index("--migration-source-mode") + 1] == (
        CANONICAL_MIGRATION_SOURCE_MODE
    )
    assert "--enable-helius-http-recovery" in argv
    # Bounded six-hour DEX candidate recovery is part of the armed contract
    # (2026-07-30 remediation): the canonical launcher passes the flag and
    # its ABSENCE is the refusal.
    assert "--enable-dexscreener-restart-backfill" in argv
    assert validate_launcher_arguments(
        argv,
        expected_head=HEAD,
        helius_configured=True,
    ).allowed

    no_backfill = [
        value for value in argv
        if value != "--enable-dexscreener-restart-backfill"
    ]
    verdict = validate_launcher_arguments(
        no_backfill,
        expected_head=HEAD,
        helius_configured=True,
    )
    assert "LAUNCHER_DEX_RESTART_BACKFILL_ABSENT" in verdict.refusals

    missing = list(argv)
    index = missing.index("--migration-source-mode")
    del missing[index:index + 2]
    verdict = validate_launcher_arguments(missing, expected_head=HEAD)
    assert "LAUNCHER_MIGRATION_SOURCE_MODE_ABSENT" in verdict.refusals

    no_recovery = [
        value for value in argv
        if value != "--enable-helius-http-recovery"
    ]
    verdict = validate_launcher_arguments(
        no_recovery,
        expected_head=HEAD,
    )
    assert "LAUNCHER_HELIUS_HTTP_RECOVERY_REQUIRED" in verdict.refusals


def test_launcher_authority_inputs_fail_closed() -> None:
    argv = canonical_launcher_arguments(
        launcher="launch_pressure_24h_01.ps1",
        expected_head=HEAD,
        ledger_baseline=BASELINE,
    )
    verdict = validate_launcher_arguments(
        argv,
        expected_head=HEAD,
        helius_configured=False,
        tight_filter_locked=False,
        source_owner_count=2,
        send_authority_count=2,
        chainstack_candidate_authority=True,
        telegram_owner_count=2,
    )
    assert {
        "LAUNCHER_HELIUS_CONFIGURATION_REQUIRED",
        "LAUNCHER_HELIUS_TIGHT_FILTER_REQUIRED",
        "LAUNCHER_SOURCE_OWNER_COUNT_NOT_ONE",
        "LAUNCHER_SEND_AUTHORITY_COUNT_NOT_ONE",
        "LAUNCHER_CHAINSTACK_SHADOW_CANDIDATE_AUTHORITY",
        "LAUNCHER_TELEGRAM_OWNER_COUNT_NOT_ONE",
    }.issubset(set(verdict.refusals))


def test_final_launcher_is_helius_only_without_parity_or_chainstack_args() -> None:
    argv = canonical_launcher_arguments(
        launcher="launch_pressure_24h_01.ps1",
        expected_head=HEAD,
        ledger_baseline=BASELINE,
    )
    assert CANONICAL_MIGRATION_SOURCE_MODE == helius_source.HELIUS_PRIMARY
    assert "--helius-parity-late-match-seconds" not in argv
    assert not any(str(token).startswith("--chainstack") for token in argv)

    text = render_live_launcher(expected_head=HEAD, ledger_baseline=BASELINE)
    assert '$SOURCE_MODE = "HELIUS_PRIMARY"' in text
    assert (
        '$env:PHX2_MIGRATION_SOURCE_MODE = "HELIUS_PRIMARY"' in text
    )
    assert "primary_recovery        = \"HELIUS_HTTP\"" in text
    assert "shadow_source           = \"DISABLED\"" in text
    assert "chainstack_configured_for_runtime = $false" in text
    assert "chainstack_connected    = $false" in text
    assert "chainstack_comparator   = $false" in text
    assert "HELIUS_PRIMARY_CHAINSTACK_SHADOW" not in text
    assert "CHAINSTACK_PRIMARY" not in text
    assert "--helius-parity-late-match-seconds" not in text
    assert validate_live_launcher_text(
        text,
        expected_head=HEAD,
        ledger_baseline=BASELINE,
    ) == []


@pytest.mark.parametrize(
    "forbidden",
    [
        "HELIUS_PRIMARY_CHAINSTACK_SHADOW",
        "CHAINSTACK_PRIMARY",
    ],
)
def test_deployment_validator_refuses_non_final_source_modes(
    forbidden: str,
) -> None:
    text = render_live_launcher(expected_head=HEAD, ledger_baseline=BASELINE)
    broken = text.replace(
        '$SOURCE_MODE = "HELIUS_PRIMARY"',
        f'$SOURCE_MODE = "{forbidden}"',
    )
    assert "LIVE_LAUNCHER_HELIUS_ONLY_CHAINSTACK_RUNTIME_PRESENT" in (
        validate_live_launcher_text(
            broken,
            expected_head=HEAD,
            ledger_baseline=BASELINE,
        )
    )


def test_deployment_validator_refuses_second_source_owner() -> None:
    text = render_live_launcher(expected_head=HEAD, ledger_baseline=BASELINE)
    broken = text.replace(
        "source_owners           = 1",
        "source_owners           = 2",
    )
    assert "LIVE_LAUNCHER_SOURCE_OWNER_COUNT_NOT_ONE" in (
        validate_live_launcher_text(
            broken,
            expected_head=HEAD,
            ledger_baseline=BASELINE,
        )
    )
