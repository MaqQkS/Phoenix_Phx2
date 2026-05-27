"""Stage 29.5.5 no-public / no-enforcement / no-trading /
no-social pins.

Pins (across all Stage 29.5.5 production source AND the
rendered block ``body_text`` AND the side-channel artifact
JSON):

  * NO public / subscriber / paid-tier routing identifier.
  * NO Telegram / X / social sidecar identifier.
  * NO automated trading / position-sizing / trade-execution
    identifier.
  * NO wallet / private-key / signer identifier.
  * NO BUY / SELL / APPROVED / GATE / BLOCK / EXECUTE /
    POSITION-SIZE / AUTO-TRADE verdict-language token in the
    rendered ``body_text``.
  * NO enforcement-activation language (no
    ``ENFORCEMENT_ACTIVE`` / no
    ``ENFORCEMENT_ENABLED`` / no
    ``approval_gate`` / no ``enforce_policy``).
"""

from __future__ import annotations

import ast
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
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_SOURCE_HELIUS_WS,
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


PHX2_ROOT: Path = (
    Path(__file__).resolve().parent.parent.parent
)
STAGE29_ROOT: Path = PHX2_ROOT / "stage29"

_STAGE_29_5_5_PRODUCTION_PY_BASENAMES: tuple[str, ...] = (
    "stage29_5_5_render_models.py",
    "stage29_5_5_private_discord_migration_context_renderer.py",
    "stage29_5_5_migration_context_recorder.py",
    "stage29_5_5_side_channel_artifact_writer.py",
    "stage29_5_5_manifest.py",
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


# Forbidden identifier substrings (concatenated literally so
# this test file does not itself trip a self-referential scan).
_FORBIDDEN_IDENTIFIER_SUBSTRINGS: tuple[str, ...] = (
    "public" + "_router",
    "subscriber" + "_router",
    "paid" + "_tier_router",
    "telegram" + "_sender",
    "telegram" + "_client",
    "x" + "_social",
    "social" + "_sidecar",
    "tweet" + "_ranking",
    "enforcement" + "_gate",
    "enforce" + "_policy",
    "approval" + "_gate",
    "auto" + "_trade",
    "position" + "_size",
    "trade" + "_executor",
    "wallet" + "_signer",
    "private" + "_key_loader",
    "execute" + "_trade",
)


# Trading-verdict language tokens (these should never appear
# in the rendered body_text).
_FORBIDDEN_BODY_VERDICT_TOKENS: tuple[str, ...] = (
    "BUY",
    "SELL",
    "APPROVED",
    "GATE",
    "ENFORCEMENT",
    "EXECUTE",
    "POSITION-SIZE",
    "AUTO-TRADE",
    "AUTOTRADE",
    "ENFORCEMENT_ACTIVE",
    "ENFORCEMENT_ENABLED",
)


def _extract_all_identifiers(source: str) -> set[str]:
    tree = ast.parse(source)
    idents: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
    return idents


# ---------------------------------------------------------------------------
# Production source identifier scan
# ---------------------------------------------------------------------------


def test_no_forbidden_identifier_in_production_source() -> None:
    for name in _STAGE_29_5_5_PRODUCTION_PY_BASENAMES:
        source = (
            STAGE29_ROOT / name
        ).read_text(encoding="utf-8")
        idents = _extract_all_identifiers(source)
        for ident in idents:
            lower = ident.lower()
            for needle in (
                _FORBIDDEN_IDENTIFIER_SUBSTRINGS
            ):
                assert needle not in lower, (
                    f"{name}: forbidden identifier substring "
                    f"{needle!r} in identifier {ident!r}"
                )


# ---------------------------------------------------------------------------
# Rendered block body_text trading-verdict scan
# ---------------------------------------------------------------------------


def _build_projection() -> (
    Stage29_5PrivatePingMigrationContext
):
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=MEASUREMENT_STATUS_COMPLETE,
        warnings=(),
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=12345,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        post_migration_ath_verified=True,
        join_status_echoed=MIGRATION_JOIN_STATUS_JOINED,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_OBSERVED_AT,
    )


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_BODY_VERDICT_TOKENS
)
def test_rendered_body_text_carries_no_trading_verdict_token(
    needle: str,
) -> None:
    projection = _build_projection()
    block = render_private_discord_migration_context_block(
        projection,
    )
    assert needle not in block.body_text, (
        f"Stage 29.5.5 rendered body_text contains "
        f"forbidden trading-verdict token {needle!r}; "
        f"body: {block.body_text!r}"
    )


# Note: the substring "BLOCK" alone would collide with
# "rendered_migration_context_block" (lowercase) and other
# legitimate naming; we excluded it from the trading-verdict
# token list. We pin the trading-verdict intent by checking
# that no SOLO uppercase "BLOCK" line appears in the body
# (i.e. no line whose stripped value is exactly "BLOCK").


def test_rendered_body_text_carries_no_solo_uppercase_block_line() -> None:
    projection = _build_projection()
    block = render_private_discord_migration_context_block(
        projection,
    )
    for line in block.body_text.splitlines():
        assert line.strip() != "BLOCK", (
            "Stage 29.5.5 rendered body_text must not "
            "contain a solo uppercase 'BLOCK' line (would "
            "imply a trading verdict)"
        )


def test_rendered_body_text_does_not_say_enforcement_active() -> None:
    projection = _build_projection()
    block = render_private_discord_migration_context_block(
        projection,
    )
    lower = block.body_text.lower()
    assert "enforcement_active" not in lower
    assert "enforcement_enabled" not in lower
    assert "enforce_policy" not in lower


# ---------------------------------------------------------------------------
# Side-channel artifact JSON scans
# ---------------------------------------------------------------------------


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
            prefix="phx2_stage29_5_5_no_public_test_",
        ),
    )


def _build_artifact_path() -> Path:
    def evidence_provider(m: str):
        return (_evidence(),)

    def ath_provider(m: str):
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
    assert path is not None
    return path


def test_artifact_content_does_not_contain_trading_verdict_tokens() -> None:
    artifact_path = _build_artifact_path()
    content = artifact_path.read_text(encoding="utf-8")
    for needle in _FORBIDDEN_BODY_VERDICT_TOKENS:
        assert needle not in content, (
            f"Stage 29.5.5 side-channel artifact carries "
            f"forbidden trading-verdict token {needle!r}"
        )


def test_artifact_content_does_not_contain_forbidden_routing_identifiers() -> None:
    artifact_path = _build_artifact_path()
    content = artifact_path.read_text(encoding="utf-8").lower()
    for needle in _FORBIDDEN_IDENTIFIER_SUBSTRINGS:
        assert needle not in content, (
            f"Stage 29.5.5 side-channel artifact carries "
            f"forbidden routing/social/trading identifier "
            f"{needle!r}"
        )


def test_artifact_content_pins_locked_enforcement() -> None:
    artifact_path = _build_artifact_path()
    bundle = json.loads(
        artifact_path.read_text(encoding="utf-8"),
    )
    assert (
        bundle["filter_enforcement_status"]
        == FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    )
