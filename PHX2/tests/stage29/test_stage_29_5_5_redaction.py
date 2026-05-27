"""Stage 29.5.5 redaction tests.

Pins that the Stage 29.5.5 rendered block AND the Stage 29.5.5
side-channel artifact carry:

  * NO URL host literal (no ``discord.com`` / ``discordapp.com``
    / ``hooks.slack.com`` / ``api.helius.xyz`` /
    ``rpc.helius.xyz`` / ``mainnet.helius-rpc.com`` /
    ``public-api.birdeye.so`` / ``pro-api.birdeye.so`` /
    ``birdeye.so`` / ``t.me/`` / ``api.twitter.com`` /
    ``api.x.com`` / ``chainstack.com`` /
    ``yellowstone.chainstack`` / ``dexscreener.com`` /
    ``ws[s]://``).
  * NO raw API-key shape (``Bearer ...`` / ``Authorization:
    ...`` / ``sk-...`` / ``pk-...`` / ``DISCORD_WEBHOOK_URL=`` /
    ``HELIUS_API_KEY=`` / ``HELIUS_WS_URL=`` /
    ``BIRDEYE_API_KEY=`` / ``CHAINSTACK_API_KEY=``).
  * NO raw payload / wallet-key / signer field.
  * NO public / subscriber / paid-tier routing identifier in
    the output.
  * NO PHX1 / Phoenix_Bot path substring.

The redaction scan runs across the rendered block's
``body_text``, the rendered block's projected JSON shape, AND
the side-channel artifact JSON content (for representative
status × source × ATH combinations).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Sequence

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
    MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
    MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
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
from PHX2.stage29.stage29_5_5_render_models import (
    Stage29_5_5RenderedMigrationContextBlock,
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


# Forbidden substrings concatenated literally so this test file
# itself does NOT trip a downstream string-leak scan over its
# own pinned vocabulary.
_FORBIDDEN_URL_HOSTS: tuple[str, ...] = (
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
    "h" + "ttps://",
    "h" + "ttp://",
    "pump" + ".fun",
)


_FORBIDDEN_RAW_SECRET_NEEDLES: tuple[str, ...] = (
    "B" + "earer ",
    "A" + "uthorization:",
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_WS" + "_URL=",
    "HELIUS_WS" + "_ENDPOINT=",
    "BIRDEYE_API" + "_KEY=",
    "CHAINSTACK_API" + "_KEY=",
    "PHX2_CHAINSTACK_YELLOWSTONE_X" + "_TOKEN=",
)


# Pump.fun bonding-curve program id literal concatenated.
_PUMP_FUN_PROGRAM_ID: str = (
    "6EF8rrec" + "thR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
)


_FORBIDDEN_ROUTING_IDENTIFIERS: tuple[str, ...] = (
    "public_router",
    "subscriber_router",
    "paid_tier_router",
    "telegram_sender",
    "telegram_client",
    "x_social",
    "social_sidecar",
    "wallet_signer",
    "private_key",
    "auto_trade",
    "trade_executor",
    "position_sizer",
)


_FORBIDDEN_PHX1_NEEDLES: tuple[str, ...] = (
    "phoenix_bot",
    "phx1",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _evidence(
    *,
    token_mint: str = _BASE_MINT,
    source: str = MIGRATION_SOURCE_HELIUS_WS,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=source,
        base_mint=token_mint,
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


def _build_projection(
    *,
    measurement_status: str,
    migration_source: str,
    join_status: str,
    has_timestamp: bool = True,
    has_slot: bool = True,
) -> Stage29_5PrivatePingMigrationContext:
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=measurement_status,
        warnings=(),
        migration_timestamp_utc=(
            _MIGRATION_TS if has_timestamp else None
        ),
        migration_slot=12345 if has_slot else None,
        migration_source=migration_source,
        post_migration_ath_verified=(
            True
            if measurement_status
            == MEASUREMENT_STATUS_COMPLETE
            else None
        ),
        join_status_echoed=join_status,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_OBSERVED_AT,
    )


def _scan_for_forbidden_substrings(
    text: str,
) -> list[str]:
    text_lower = text.lower()
    hits: list[str] = []
    for needle in _FORBIDDEN_URL_HOSTS:
        if needle.lower() in text_lower:
            hits.append(needle)
    for needle in _FORBIDDEN_RAW_SECRET_NEEDLES:
        if needle in text:
            hits.append(needle)
    if _PUMP_FUN_PROGRAM_ID in text:
        hits.append(_PUMP_FUN_PROGRAM_ID)
    for needle in _FORBIDDEN_ROUTING_IDENTIFIERS:
        if needle in text_lower:
            hits.append(needle)
    for needle in _FORBIDDEN_PHX1_NEEDLES:
        if needle in text_lower:
            hits.append(needle)
    return hits


def _outside_repo_tmpdir() -> Path:
    return Path(
        tempfile.mkdtemp(prefix="phx2_stage29_5_5_test_"),
    )


# ---------------------------------------------------------------------------
# Rendered block body_text redaction (representative cases)
# ---------------------------------------------------------------------------


_PROJECTION_MATRIX: tuple[
    tuple[str, str, str], ...
] = (
    # (measurement_status, migration_source, join_status)
    (
        MEASUREMENT_STATUS_COMPLETE,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_JOIN_STATUS_JOINED,
    ),
    (
        MEASUREMENT_STATUS_COMPLETE,
        MIGRATION_SOURCE_STAGE29_MIGRATION_ARTIFACT,
        MIGRATION_JOIN_STATUS_JOINED,
    ),
    (
        MEASUREMENT_STATUS_COMPLETE,
        MIGRATION_SOURCE_SYNTHETIC_TEST_ONLY,
        MIGRATION_JOIN_STATUS_JOINED,
    ),
    (
        MEASUREMENT_STATUS_COMPLETE,
        MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        MIGRATION_JOIN_STATUS_JOINED,
    ),
    (
        MEASUREMENT_STATUS_PARTIAL_MIGRATION_PRESENT,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_JOIN_STATUS_TIME_WINDOW_INVALID,
    ),
    (
        MEASUREMENT_STATUS_MISSING_MIGRATION,
        MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        MIGRATION_JOIN_STATUS_NO_MATCH,
    ),
    (
        MEASUREMENT_STATUS_INVALID_MIGRATION,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_JOIN_STATUS_SOURCE_INVALID,
    ),
    (
        MEASUREMENT_STATUS_CONFLICTING_MIGRATION,
        MIGRATION_SOURCE_HELIUS_WS,
        MIGRATION_JOIN_STATUS_MULTIPLE_MATCHES,
    ),
)


@pytest.mark.parametrize(
    ("measurement_status", "migration_source", "join_status"),
    _PROJECTION_MATRIX,
)
def test_rendered_body_text_carries_no_forbidden_substring(
    measurement_status: str,
    migration_source: str,
    join_status: str,
) -> None:
    projection = _build_projection(
        measurement_status=measurement_status,
        migration_source=migration_source,
        join_status=join_status,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    hits = _scan_for_forbidden_substrings(block.body_text)
    assert not hits, (
        f"Stage 29.5.5 rendered body_text carries forbidden "
        f"substring(s) {hits!r}; body: {block.body_text!r}"
    )


@pytest.mark.parametrize(
    ("measurement_status", "migration_source", "join_status"),
    _PROJECTION_MATRIX,
)
def test_rendered_block_field_values_carry_no_forbidden_substring(
    measurement_status: str,
    migration_source: str,
    join_status: str,
) -> None:
    projection = _build_projection(
        measurement_status=measurement_status,
        migration_source=migration_source,
        join_status=join_status,
    )
    block = render_private_discord_migration_context_block(
        projection,
    )
    # Scan every string-valued field on the rendered block.
    string_field_values = [
        block.migration_evidence_status_display,
        block.migration_evidence_source_trust_display,
        block.post_migration_ath_verified_display,
        block.migration_timestamp_utc_display,
        block.migration_slot_display,
        block.migration_source_token,
        block.join_status_echoed_token,
        block.warnings_display,
        block.redaction_status,
        block.filter_enforcement_status,
        block.observed_at_utc,
        block.schema_version,
    ]
    for value in string_field_values:
        hits = _scan_for_forbidden_substrings(value)
        assert not hits, (
            f"Stage 29.5.5 rendered block field carries "
            f"forbidden substring(s) {hits!r} in value "
            f"{value!r}"
        )


def test_rendered_block_redaction_status_is_safe() -> None:
    for (
        measurement_status,
        migration_source,
        join_status,
    ) in _PROJECTION_MATRIX:
        projection = _build_projection(
            measurement_status=measurement_status,
            migration_source=migration_source,
            join_status=join_status,
        )
        block = render_private_discord_migration_context_block(
            projection,
        )
        assert (
            block.redaction_status == REDACTION_STATUS_SAFE
        )


# ---------------------------------------------------------------------------
# Side-channel artifact JSON redaction (representative case)
# ---------------------------------------------------------------------------


def test_side_channel_artifact_json_carries_no_forbidden_substring() -> None:
    def evidence_provider(token_mint: str):
        return (_evidence(token_mint=token_mint),)

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
    artifact_path = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert artifact_path is not None
    content = artifact_path.read_text(encoding="utf-8")
    hits = _scan_for_forbidden_substrings(content)
    assert not hits, (
        f"Stage 29.5.5 side-channel artifact JSON carries "
        f"forbidden substring(s) {hits!r}"
    )


def test_side_channel_artifact_json_parses_with_pinned_flags() -> None:
    def evidence_provider(token_mint: str):
        return (_evidence(token_mint=token_mint),)

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
    artifact_path = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(
        artifact_path.read_text(encoding="utf-8"),
    )
    assert bundle["informational_only"] is True
    assert bundle["not_a_trading_verdict"] is True
    assert bundle["redaction_status"] == "SAFE"
    assert (
        bundle["filter_enforcement_status"]
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# Side-channel JSON redaction of snapshot_summary audit identifiers
# ---------------------------------------------------------------------------


def _malicious_evidence(
    *,
    token_mint: str = _BASE_MINT,
    source_event_ref: str,
    migration_signature: str,
) -> Stage29_5MigrationEvidenceRecord:
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=token_mint,
        pool_account=_POOL_ACCOUNT,
        pool_program_id=_POOL_PROGRAM_ID,
        quote_mint=_QUOTE_MINT,
        migration_timestamp_utc=_MIGRATION_TS,
        migration_slot=12345,
        migration_signature=migration_signature,
        observed_at_utc=_OBSERVED_AT,
        source_event_ref=source_event_ref,
    )


def test_malicious_source_event_ref_never_appears_in_side_channel_json() -> None:
    """A maliciously-crafted ``source_event_ref`` carrying a raw
    webhook URL MUST NOT survive into the side-channel artifact
    JSON. The Stage 29.5.5 writer redacts unsafe snapshot_summary
    audit identifiers to ``None``.
    """
    malicious_ref = (
        "h" + "ttps://discord" + ".com/api/webhooks/123/abcXYZ"
    )

    def evidence_provider(token_mint: str):
        return (
            _malicious_evidence(
                token_mint=token_mint,
                source_event_ref=malicious_ref,
                migration_signature="Sig" + "X" * 60,
            ),
        )

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
    artifact_path = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert artifact_path is not None
    content = artifact_path.read_text(encoding="utf-8")
    # The raw URL string MUST NOT appear anywhere in the
    # serialized JSON.
    assert malicious_ref not in content
    # The serialized JSON must not carry any forbidden substring.
    hits = _scan_for_forbidden_substrings(content)
    assert not hits, (
        f"Stage 29.5.5 side-channel artifact JSON leaked "
        f"forbidden substring(s) {hits!r}"
    )
    # snapshot_summary.source_event_ref must be redacted to null.
    bundle = json.loads(content)
    ss = bundle["entries"][0]["snapshot_summary"]
    assert ss["source_event_ref"] is None
    # raw_capture_ref is always None in this snapshot mapping.
    assert ss["raw_capture_ref"] is None


def test_malicious_migration_signature_never_appears_in_side_channel_json() -> None:
    """A maliciously-crafted ``migration_signature`` (which the
    recorder uses to populate ``snapshot.migration_event_id``)
    carrying an embedded raw URL substring MUST NOT survive into
    the side-channel artifact JSON.
    """
    malicious_signature = (
        "Sig"
        + "X" * 10
        + "h" + "ttps://example" + ".com/webhook"
        + "Y" * 10
    )

    def evidence_provider(token_mint: str):
        return (
            _malicious_evidence(
                token_mint=token_mint,
                source_event_ref="evt-001",
                migration_signature=malicious_signature,
            ),
        )

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
    artifact_path = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert artifact_path is not None
    content = artifact_path.read_text(encoding="utf-8")
    assert "h" + "ttps://" not in content
    assert "webhook" not in content
    bundle = json.loads(content)
    ss = bundle["entries"][0]["snapshot_summary"]
    # migration_event_id MUST be redacted to None because the raw
    # signature carries a forbidden URL substring.
    assert ss["migration_event_id"] is None


def test_custom_renderer_unsafe_body_text_rejected_or_not_written() -> None:
    """A custom renderer attempting to inject a raw URL / API-key
    / webhook substring into the rendered block's ``body_text``
    is REJECTED at dataclass construction time by the Stage
    29.5.5 ``__post_init__`` validator. The recorder catches the
    resulting ``ValueError`` as a Phase 2 failure: no entry is
    appended, the Phase 1 snapshot survives unchanged, and the
    side-channel JSON either no-ops (zero entries) OR carries no
    unsafe body_text.
    """
    def custom_renderer_with_unsafe_body(projection):
        # Constructing a block with a forbidden substring in
        # body_text MUST raise during __post_init__.
        return Stage29_5_5RenderedMigrationContextBlock(
            migration_evidence_status_display=(
                "MIGRATION_EVIDENCE_COMPLETE"
            ),
            migration_evidence_source_trust_display=(
                "SOURCE_TRUSTED_ON_CHAIN"
            ),
            post_migration_ath_verified_display=(
                "ATH_VERIFIED_POST_MIGRATION"
            ),
            migration_timestamp_utc_display=_MIGRATION_TS,
            migration_slot_display="12345",
            migration_source_token=MIGRATION_SOURCE_HELIUS_WS,
            join_status_echoed_token=(
                MIGRATION_JOIN_STATUS_JOINED
            ),
            warnings_display="NONE",
            redaction_status=REDACTION_STATUS_SAFE,
            filter_enforcement_status=(
                FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
            ),
            observed_at_utc=_OBSERVED_AT,
            informational_only=True,
            not_a_trading_verdict=True,
            body_text=(
                "leak: "
                + "h"
                + "ttps://discord"
                + ".com/api/webhooks/123"
            ),
        )

    def evidence_provider(token_mint: str):
        return (_evidence(token_mint=token_mint),)

    def ath_provider(token_mint: str):
        return _ath_context()

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=evidence_provider,
        ath_context_provider=ath_provider,
        clock=lambda: _OBSERVED_AT,
        renderer=custom_renderer_with_unsafe_body,
    )
    snapshot = rec.read_migration_snapshot(_BASE_MINT)
    # Phase 1 snapshot is preserved.
    assert (
        snapshot.migration_source
        == "ON_CHAIN_MIGRATION_EVENT"
    )
    # Phase 2 failed (renderer raised ValueError at dataclass
    # construction); zero entries recorded.
    assert rec.recorded_entries == ()
    # Side-channel writer no-ops because the recorder has no
    # entries.
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None


def test_construct_rendered_block_with_forbidden_body_text_raises() -> None:
    """Direct dataclass construction with a forbidden substring
    in ``body_text`` MUST raise ``ValueError`` so the closed-set
    redaction contract cannot be bypassed by a hand-crafted
    block.
    """
    with pytest.raises(ValueError):
        Stage29_5_5RenderedMigrationContextBlock(
            migration_evidence_status_display=(
                "MIGRATION_EVIDENCE_COMPLETE"
            ),
            migration_evidence_source_trust_display=(
                "SOURCE_TRUSTED_ON_CHAIN"
            ),
            post_migration_ath_verified_display=(
                "ATH_VERIFIED_POST_MIGRATION"
            ),
            migration_timestamp_utc_display=_MIGRATION_TS,
            migration_slot_display="12345",
            migration_source_token=MIGRATION_SOURCE_HELIUS_WS,
            join_status_echoed_token=(
                MIGRATION_JOIN_STATUS_JOINED
            ),
            warnings_display="NONE",
            redaction_status=REDACTION_STATUS_SAFE,
            filter_enforcement_status=(
                FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
            ),
            observed_at_utc=_OBSERVED_AT,
            informational_only=True,
            not_a_trading_verdict=True,
            body_text=(
                "leak "
                + "h" + "ttps://" + "example" + ".com"
            ),
        )
