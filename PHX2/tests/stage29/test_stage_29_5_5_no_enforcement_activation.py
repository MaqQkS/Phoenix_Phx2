"""Stage 29.5.5 no-enforcement-activation pins.

Pins:

  * The Stage 29.5.5 rendered block ALWAYS carries
    ``filter_enforcement_status = NOT_ACTIVE_STAGE_29_PENDING``
    regardless of inputs.
  * The Stage 29.5.5 side-channel artifact bundle ALWAYS
    carries ``filter_enforcement_status =
    NOT_ACTIVE_STAGE_29_PENDING``.
  * The Stage 29.5.5 rendered block ALWAYS carries
    ``redaction_status = SAFE`` regardless of inputs.
  * The Stage 29.5.5 rendered block ALWAYS pins
    ``informational_only = True`` and
    ``not_a_trading_verdict = True``.
  * The Stage 29.5.5 recorder, renderer, and side-channel
    writer NEVER mutate the projection's locked enforcement /
    redaction tokens.
  * The Stage 29.5.5 production source carries the locked
    enforcement-status token verbatim.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
    MEASUREMENT_STATUS_INVALID_MIGRATION,
    MEASUREMENT_STATUS_MISSING_MIGRATION,
    MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES,
    MIGRATION_JOIN_STATUS_NO_MATCH,
    MIGRATION_JOIN_STATUS_SOURCE_INVALID,
    MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID,
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
    MIGRATION_STATUS_PRESENT,
    REDACTION_STATUS_SAFE,
    Stage29_5MigrationEvidenceRecord,
    Stage29_5PrivatePingMigrationContext,
)
from PHX2.stage29.stage29_5_5_migration_context_recorder import (
    Stage29_5_5MigrationContextRecorder,
)
from PHX2.stage29.stage29_5_5_private_discord_migration_context_renderer import (
    render_private_discord_migration_context_block,
)
from PHX2.stage29.stage29_5_5_side_channel_artifact_writer import (
    Stage29_5_5SideChannelArtifactWriter,
)


_OBSERVED_AT: str = "2026-01-01T00:00:00+00:00"
_MIGRATION_TS: str = "2026-01-01T00:00:05+00:00"
_BASE_MINT: str = "TestBaseMintAAAA1111111111111111111111111A"
_POOL_ACCOUNT: str = (
    "TestPoolXXXXXXX3333333333333333333333333X"
)
_POOL_PROGRAM_ID: str = (
    "PoolProgramIDDDDDDD22222222222222222222222D"
)
_QUOTE_MINT: str = (
    "QuoteMintEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE"
)


def _build_projection(
    *,
    measurement_status: str,
    migration_source: str,
    join_status: str,
    post_migration_ath_verified: bool | None = None,
) -> Stage29_5PrivatePingMigrationContext:
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=measurement_status,
        warnings=(),
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=12345,
        migration_source=migration_source,
        post_migration_ath_verified=(
            post_migration_ath_verified
        ),
        join_status_echoed=join_status,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_OBSERVED_AT,
    )


_MATRIX: tuple[
    tuple[str, str, str, bool | None], ...
] = (
    (
        MEASUREMENT_STATUS_COMPLETE,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_JOIN_STATUS_JOINED,
        True,
    ),
    (
        MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID,
        None,
    ),
    (
        MEASUREMENT_STATUS_MISSING_MIGRATION,
        MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        MIGRATION_JOIN_STATUS_NO_MATCH,
        None,
    ),
    (
        MEASUREMENT_STATUS_INVALID_MIGRATION,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_JOIN_STATUS_SOURCE_INVALID,
        None,
    ),
    (
        MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES,
        None,
    ),
)


@pytest.mark.parametrize(
    (
        "measurement_status",
        "migration_source",
        "join_status",
        "ath_verified",
    ),
    _MATRIX,
)
def test_rendered_block_preserves_locked_enforcement_status(
    measurement_status: str,
    migration_source: str,
    join_status: str,
    ath_verified: bool | None,
) -> None:
    projection = _build_projection(
        measurement_status=measurement_status,
        migration_source=migration_source,
        join_status=join_status,
        post_migration_ath_verified=ath_verified,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert (
        block.filter_enforcement_status
        == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )


@pytest.mark.parametrize(
    (
        "measurement_status",
        "migration_source",
        "join_status",
        "ath_verified",
    ),
    _MATRIX,
)
def test_rendered_block_preserves_safe_redaction_status(
    measurement_status: str,
    migration_source: str,
    join_status: str,
    ath_verified: bool | None,
) -> None:
    projection = _build_projection(
        measurement_status=measurement_status,
        migration_source=migration_source,
        join_status=join_status,
        post_migration_ath_verified=ath_verified,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert block.redaction_status == REDACTION_STATUS_SAFE


@pytest.mark.parametrize(
    (
        "measurement_status",
        "migration_source",
        "join_status",
        "ath_verified",
    ),
    _MATRIX,
)
def test_rendered_block_pins_informational_and_not_trading_flags(
    measurement_status: str,
    migration_source: str,
    join_status: str,
    ath_verified: bool | None,
) -> None:
    projection = _build_projection(
        measurement_status=measurement_status,
        migration_source=migration_source,
        join_status=join_status,
        post_migration_ath_verified=ath_verified,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert block.informational_only is True
    assert block.not_a_trading_verdict is True


@pytest.mark.parametrize(
    (
        "measurement_status",
        "migration_source",
        "join_status",
        "ath_verified",
    ),
    _MATRIX,
)
def test_rendered_block_body_text_pins_enforcement_status(
    measurement_status: str,
    migration_source: str,
    join_status: str,
    ath_verified: bool | None,
) -> None:
    projection = _build_projection(
        measurement_status=measurement_status,
        migration_source=migration_source,
        join_status=join_status,
        post_migration_ath_verified=ath_verified,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert (
        "filter_enforcement_status: "
        "NOT_ACTIVE_STAGE_29_PENDING" in block.body_text
    )


def _evidence() -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=_BASE_MINT,
        pool_account=_POOL_ACCOUNT,
        pool_program_id=_POOL_PROGRAM_ID,
        quote_mint=_QUOTE_MINT,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=12345,
        migration_signature="Sig" + "X" * 60,
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="evt-001",
    )


def _ath_context() -> AthContextRecord:
    return AthContextRecord(
        token_mint=_BASE_MINT,
        pair_type="SOL_PAIR",
        quote_asset="SOL",
        ath_value="123.45",
        ath_unit="SOL",
        ath_source="birdeye",
        ath_observed_at_utc=(
            "2026-01-01T00:01:00+00:00"
        ),
        ath_since_migration_status="POST_MIGRATION_ONLY",
        drawdown_from_ath="0.1",
        drawdown_unit="ratio",
        drawdown_basis="last_price",
        ath_status="PRESENT",
        ath_reason="OK",
        schema_version="stage27_4_v0_ath_context",
    )


def _outside_repo_tmpdir() -> Path:
    return Path(
        tempfile.mkdtemp(
            prefix="phx2_stage29_5_5_enforce_test_",
        ),
    )


def test_side_channel_artifact_pins_locked_enforcement_status() -> None:
    def evidence_provider(token_mint: str):
        return (_evidence(),)

    def ath_provider(token_mint: str):
        return _ath_context()

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=evidence_provider,
        ath_context_provider=ath_provider,
        clock=lambda: _OBSERVED_AT,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )
    rec.read_migration_snapshot(_BASE_MINT)
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    path = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(path.read_text(encoding="utf-8"))
    assert (
        bundle["filter_enforcement_status"]
        == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )


def test_locked_enforcement_token_verbatim_in_production_source() -> None:
    """The Stage 29.5.5 render models module and the manifest
    module must reference the locked enforcement token
    verbatim (the render models module re-imports the constant
    from Stage 29.5; the manifest re-exports it). The recorder
    and the renderer flow the token through the projection
    they consume without needing to reference the literal; the
    side-channel writer reads it from the rendered block at
    runtime.
    """
    stage29_root = (
        Path(__file__).resolve().parent.parent.parent
        / "stage29"
    )
    for name in (
        "stage29_5_5_render_models.py",
        "stage29_5_5_manifest.py",
    ):
        source = (
            stage29_root / name
        ).read_text(encoding="utf-8")
        assert (
            "NOT_ACTIVE_STAGE_29_PENDING" in source
            or "FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING"
            in source
        ), (
            f"{name}: Stage 29.5.5 must reference the locked "
            f"enforcement token verbatim"
        )
