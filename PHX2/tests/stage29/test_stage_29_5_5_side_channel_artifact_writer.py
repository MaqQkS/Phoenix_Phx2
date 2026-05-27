"""Stage 29.5.5 side-channel artifact writer tests.

Pins:

  * The writer duck-types ``migration_source.recorded_entries``
    and no-ops when:
      - ``migration_source`` lacks the attribute,
      - ``migration_source.recorded_entries`` is empty,
      - ``migration_source.recorded_entries`` contains a non-
        ``Stage29_5_5RecordedRenderEntry`` element,
      - ``migration_source`` is None.
  * The writer no-ops when ``output_dir`` is not a ``Path``,
    does not exist, is not a directory, or carries a forbidden
    URL / webhook / API-key substring.
  * When inputs are valid the writer writes EXACTLY ONE JSON
    artifact under ``output_dir`` named
    ``stage29_5_5_side_channel_migration_context_artifact.json``.
  * The artifact JSON parses as a dict with the canonical
    schema_version + pinned ``informational_only`` /
    ``not_a_trading_verdict`` / ``filter_enforcement_status`` /
    ``redaction_status`` flags + ``entry_count`` field.
  * The artifact's entries list preserves recorder insertion
    order.
  * The artifact JSON output is deterministic (re-writing the
    same recorder produces the same bytes).
  * The writer is non-raising on JSON encode errors (defensive).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional, Sequence

import pytest

from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage29.stage29_5_5_migration_context_recorder import (
    Stage29_5_5MigrationContextRecorder,
)
from PHX2.stage29.stage29_5_5_private_discord_migration_context_renderer import (
    render_private_discord_migration_context_block,
)
from PHX2.stage29.stage29_5_5_render_models import (
    Stage29_5_5RecordedRenderEntry,
)
from PHX2.stage29.stage29_5_5_side_channel_artifact_writer import (
    STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION,
    STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME,
    STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_WRITER_SCHEMA_VERSION,
    Stage29_5_5SideChannelArtifactWriter,
)


_OBSERVED_AT: str = "2026-01-01T00:00:00+00:00"
_MIGRATION_TS: str = "2026-01-01T00:00:05+00:00"
_BASE_MINT: str = "TestBaseMintAAAA1111111111111111111111111A"
_BASE_MINT_2: str = (
    "TestBaseMintBBBB2222222222222222222222222B"
)
_POOL_ACCOUNT: str = (
    "TestPoolXXXXXXX3333333333333333333333333X"
)
_POOL_PROGRAM_ID: str = (
    "PoolProgramIDDDDDDD22222222222222222222222D"
)
_QUOTE_MINT: str = (
    "QuoteMintEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE"
)


def _evidence(
    *, token_mint: str,
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
        migration_signature="Sig" + "X" * 60,
        observed_at_utc=_OBSERVED_AT,
        source_event_ref="evt-001",
    )


def _ath_context(
    *, token_mint: str,
) -> AthContextRecord:
    return AthContextRecord(
        token_mint=token_mint,
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


def _build_recorder_with_entries(
    *, mints: Sequence[str],
) -> Stage29_5_5MigrationContextRecorder:
    def evidence_provider(token_mint: str):
        return (_evidence(token_mint=token_mint),)

    def ath_provider(token_mint: str) -> Optional[AthContextRecord]:
        return _ath_context(token_mint=token_mint)

    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=evidence_provider,
        ath_context_provider=ath_provider,
        clock=lambda: _OBSERVED_AT,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )
    for mint in mints:
        rec.read_migration_snapshot(mint)
    return rec


def _outside_repo_tmpdir() -> Path:
    return Path(
        tempfile.mkdtemp(prefix="phx2_stage29_5_5_test_"),
    )


# ---------------------------------------------------------------------------
# Schema version pins
# ---------------------------------------------------------------------------


def test_writer_schema_version_pin() -> None:
    assert (
        STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_WRITER_SCHEMA_VERSION
        == "stage29_5_5_v0_side_channel_artifact_writer"
    )


def test_bundle_schema_version_pin() -> None:
    assert (
        STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION
        == "stage29_5_5_v0_side_channel_artifact_bundle"
    )


def test_filename_pin() -> None:
    assert (
        STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
        == "stage29_5_5_side_channel_migration_context_artifact.json"
    )


# ---------------------------------------------------------------------------
# Writer no-op cases (duck-typing)
# ---------------------------------------------------------------------------


def test_writer_noops_when_migration_source_is_none() -> None:
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=None,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_noops_when_source_lacks_recorded_entries() -> None:
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()

    class _NoRecorderLike:
        pass

    result = writer.write_side_channel_artifact(
        output_dir=out,
        migration_source=_NoRecorderLike(),
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_noops_when_recorded_entries_is_empty_tuple() -> None:
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()

    class _EmptyRecorder:
        recorded_entries: tuple = ()

    result = writer.write_side_channel_artifact(
        output_dir=out,
        migration_source=_EmptyRecorder(),
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_noops_when_recorded_entries_is_not_tuple() -> None:
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()

    class _ListRecorder:
        recorded_entries: list = []

    result = writer.write_side_channel_artifact(
        output_dir=out,
        migration_source=_ListRecorder(),
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_noops_when_recorded_entry_is_wrong_type() -> None:
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()

    class _BadRecorder:
        recorded_entries: tuple = ("not-an-entry",)

    result = writer.write_side_channel_artifact(
        output_dir=out,
        migration_source=_BadRecorder(),
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_noops_when_recorder_has_zero_entries() -> None:
    """A recorder with renderer=None has empty recorded_entries.
    The writer must no-op.
    """
    rec = Stage29_5_5MigrationContextRecorder(
        evidence_provider=lambda m: (),
        ath_context_provider=lambda m: None,
        clock=lambda: _OBSERVED_AT,
        renderer=None,
    )
    rec.read_migration_snapshot(_BASE_MINT)
    assert rec.recorded_entries == ()
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None


# ---------------------------------------------------------------------------
# Writer no-op cases (unsafe output_dir)
# ---------------------------------------------------------------------------


def test_writer_noops_when_output_dir_is_not_a_path() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    result = writer.write_side_channel_artifact(
        output_dir="not-a-path",  # type: ignore[arg-type]
        migration_source=rec,
    )
    assert result is None


def test_writer_noops_when_output_dir_does_not_exist() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    nonexistent = Path("X:/this/path/does/not/exist/xyz123")
    result = writer.write_side_channel_artifact(
        output_dir=nonexistent, migration_source=rec,
    )
    assert result is None


def test_writer_noops_when_output_dir_is_a_file() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    tmp = _outside_repo_tmpdir()
    f = tmp / "actually_a_file.txt"
    f.write_text("hi", encoding="utf-8")
    result = writer.write_side_channel_artifact(
        output_dir=f, migration_source=rec,
    )
    assert result is None


def test_writer_noops_when_output_dir_carries_forbidden_substring() -> None:
    """The safe-shape gate refuses paths whose string rendering
    carries any forbidden URL / webhook / API-key substring,
    mirroring the Stage 29.3 mode-3 output_dir safe-shape gate.

    Construct a directory whose basename contains the API-key
    prefix shape ``sk-`` (one of the forbidden substrings); the
    writer must refuse to write.
    """
    tmp = _outside_repo_tmpdir()
    bad_dir = tmp / ("s" + "k-tmp_subdir")
    bad_dir.mkdir(parents=True, exist_ok=True)
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    result = writer.write_side_channel_artifact(
        output_dir=bad_dir, migration_source=rec,
    )
    assert result is None
    assert not (
        bad_dir / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


# ---------------------------------------------------------------------------
# Successful writes
# ---------------------------------------------------------------------------


def test_writer_creates_artifact_file_for_one_entry() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is not None
    assert result.exists()
    assert result.is_file()
    assert (
        result.name
        == STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    )


def test_writer_creates_artifact_file_for_many_entries() -> None:
    rec = _build_recorder_with_entries(
        mints=[_BASE_MINT, _BASE_MINT_2],
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is not None
    bundle = json.loads(
        result.read_text(encoding="utf-8"),
    )
    assert bundle["entry_count"] == 2
    assert len(bundle["entries"]) == 2


def test_artifact_pins_bundle_schema_version() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(result.read_text(encoding="utf-8"))
    assert (
        bundle["schema_version"]
        == STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION
    )


def test_artifact_pins_informational_only_flag() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(result.read_text(encoding="utf-8"))
    assert bundle["informational_only"] is True


def test_artifact_pins_not_a_trading_verdict_flag() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(result.read_text(encoding="utf-8"))
    assert bundle["not_a_trading_verdict"] is True


def test_artifact_pins_filter_enforcement_locked() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(result.read_text(encoding="utf-8"))
    assert (
        bundle["filter_enforcement_status"]
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


def test_artifact_pins_redaction_status_safe() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(result.read_text(encoding="utf-8"))
    assert bundle["redaction_status"] == "SAFE"


def test_artifact_preserves_insertion_order() -> None:
    rec = _build_recorder_with_entries(
        mints=[_BASE_MINT, _BASE_MINT_2],
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(result.read_text(encoding="utf-8"))
    mints_in_order = [
        e["token_mint"] for e in bundle["entries"]
    ]
    assert mints_in_order == [_BASE_MINT, _BASE_MINT_2]


def test_artifact_entry_carries_rendered_block_fields() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(result.read_text(encoding="utf-8"))
    rb = bundle["entries"][0]["rendered_block"]
    assert "migration_evidence_status_display" in rb
    assert "migration_evidence_source_trust_display" in rb
    assert "post_migration_ath_verified_display" in rb
    assert rb["informational_only"] is True
    assert rb["not_a_trading_verdict"] is True
    assert rb["redaction_status"] == "SAFE"
    assert (
        rb["filter_enforcement_status"]
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


def test_artifact_entry_carries_projection_summary() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(result.read_text(encoding="utf-8"))
    ps = bundle["entries"][0]["projection_summary"]
    assert "measurement_status" in ps
    assert "warnings" in ps
    assert isinstance(ps["warnings"], list)
    assert (
        ps["filter_enforcement_status"]
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )
    assert ps["redaction_status"] == "SAFE"


def test_artifact_entry_carries_snapshot_summary() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    bundle = json.loads(result.read_text(encoding="utf-8"))
    ss = bundle["entries"][0]["snapshot_summary"]
    assert "migration_source" in ss
    assert (
        ss["migration_source"]
        == "ON_CHAIN_MIGRATION_EVENT"
    )
    assert ss["migration_timestamp_utc"] == _MIGRATION_TS


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_writer_is_deterministic_same_recorder_same_bytes() -> None:
    rec1 = _build_recorder_with_entries(mints=[_BASE_MINT])
    rec2 = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out1 = _outside_repo_tmpdir()
    out2 = _outside_repo_tmpdir()
    p1 = writer.write_side_channel_artifact(
        output_dir=out1, migration_source=rec1,
    )
    p2 = writer.write_side_channel_artifact(
        output_dir=out2, migration_source=rec2,
    )
    assert (
        p1.read_bytes() == p2.read_bytes()
    )


# ---------------------------------------------------------------------------
# Writer non-raising contract
# ---------------------------------------------------------------------------


def test_writer_is_non_raising_on_json_dumps_failure(
    monkeypatch,
) -> None:
    """The Stage 29.5.5 writer is contractually non-raising on
    JSON-encoding failure: ``json.dumps`` raising surfaces as a
    ``None`` return value (no exception escapes the writer).
    """
    import PHX2.stage29.stage29_5_5_side_channel_artifact_writer as writer_module

    def boom_dumps(*args, **kwargs):
        raise TypeError("simulated json.dumps boom")

    monkeypatch.setattr(writer_module.json, "dumps", boom_dumps)

    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_is_non_raising_on_write_text_failure(
    monkeypatch,
) -> None:
    """The Stage 29.5.5 writer is contractually non-raising on
    filesystem-write failure: ``Path.write_text`` raising
    surfaces as a ``None`` return value.
    """
    from pathlib import Path as _Path

    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()

    def boom_write_text(self, *args, **kwargs):
        raise OSError("simulated write_text boom")

    monkeypatch.setattr(_Path, "write_text", boom_write_text)
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None


# ---------------------------------------------------------------------------
# Post-recording mutation defense
# ---------------------------------------------------------------------------
#
# The Stage 29.5.5 recorder validates each block at append time,
# but a malicious operator can still mutate a recorded entry's
# frozen-dataclass fields AFTER recording via
# ``object.__setattr__``. The Stage 29.5.5 side-channel writer
# defends the artifact JSON by re-running the full validator
# immediately before serialization. These tests pin every
# post-recording mutation surface against the writer.


def _mutate_recorded_block_field(
    recorder, *, field_name: str, value: object,
) -> None:
    """Mutate ``recorder.recorded_entries[0].rendered_block``
    field ``field_name`` to ``value`` via ``object.__setattr__``,
    bypassing the frozen-dataclass guard.
    """
    # ``recorded_entries`` returns a fresh tuple snapshot, but
    # the entry instances inside are the same objects the
    # recorder's internal list holds. Reach the internal list
    # via the recorder's private attribute so the mutation
    # actually persists onto the entry.
    internal_entries = recorder._recorded_entries  # type: ignore[attr-defined]
    assert internal_entries, (
        "fixture must produce at least one recorded entry"
    )
    block = internal_entries[0].rendered_block
    object.__setattr__(block, field_name, value)


def _mutate_recorded_entry_field(
    recorder, *, field_name: str, value: object,
) -> None:
    internal_entries = recorder._recorded_entries  # type: ignore[attr-defined]
    assert internal_entries
    entry = internal_entries[0]
    object.__setattr__(entry, field_name, value)


def test_writer_rejects_post_recording_mutated_informational_only() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_block_field(
        rec, field_name="informational_only", value=False,
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_not_a_trading_verdict() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_block_field(
        rec, field_name="not_a_trading_verdict", value=False,
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_redaction_status() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_block_field(
        rec, field_name="redaction_status", value="REDACTED",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_filter_enforcement_status() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_block_field(
        rec,
        field_name="filter_enforcement_status",
        value="ENFORCEMENT_ACTIVE_STAGE_29_LIVE",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_schema_version() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_block_field(
        rec,
        field_name="schema_version",
        value="stage29_5_5_v0_forged_block",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_closed_set_display_token() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_block_field(
        rec,
        field_name="migration_evidence_source_trust_display",
        value=(
            "h" + "ttps://discord" + ".com/api/webhooks/x"
        ),
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_body_text_with_forbidden_substring() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_block_field(
        rec,
        field_name="body_text",
        value=(
            "leak: "
            + "h"
            + "ttps://discord"
            + ".com/api/webhooks/123"
        ),
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_entry_schema_version() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_entry_field(
        rec,
        field_name="schema_version",
        value="stage29_5_5_v0_forged_recorded_entry",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_token_mint() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_entry_field(
        rec, field_name="token_mint", value="too_short",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_recorded_at_utc() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_entry_field(
        rec,
        field_name="recorded_at_utc",
        value="not-a-utc-string",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_first_entry_mutated_does_not_partial_write_second() -> None:
    """When a multi-entry recorder has its FIRST entry mutated
    after recording, the writer MUST refuse to write the entire
    bundle -- it does NOT partial-write the unmutated second
    entry. The contract is all-safe-or-none.
    """
    rec = _build_recorder_with_entries(
        mints=[_BASE_MINT, _BASE_MINT_2],
    )
    _mutate_recorded_block_field(
        rec, field_name="informational_only", value=False,
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


# ---------------------------------------------------------------------------
# Post-recording projection mutation defense
# ---------------------------------------------------------------------------
#
# The Stage 29.5 ``Stage29_5PrivatePingMigrationContext``
# dataclass validates its closed-set / pinned-value contract at
# CONSTRUCTION time, but a malicious operator can still mutate
# any of the projection's frozen-dataclass fields AFTER the
# recorder has captured it on the recorded entry via
# ``object.__setattr__``. The Stage 29.5.5 side-channel writer
# defends the artifact JSON's ``projection_summary`` by re-
# running the full Stage 29.5 projection validator immediately
# before serialization. These tests pin every post-recording
# projection mutation surface against the writer.


def _mutate_recorded_projection_field(
    recorder, *, field_name: str, value: object,
) -> None:
    """Mutate ``recorder.recorded_entries[0].projection`` field
    ``field_name`` to ``value`` via ``object.__setattr__``,
    bypassing the frozen-dataclass guard. Reaches the recorder's
    internal list so the mutation persists onto the projection
    instance the writer will see.
    """
    internal_entries = recorder._recorded_entries  # type: ignore[attr-defined]
    assert internal_entries, (
        "fixture must produce at least one recorded entry"
    )
    projection = internal_entries[0].projection
    object.__setattr__(projection, field_name, value)


def test_writer_rejects_post_recording_mutated_projection_redaction_status() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_projection_field(
        rec, field_name="redaction_status", value="REDACTED",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_projection_filter_enforcement_status() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_projection_field(
        rec,
        field_name="filter_enforcement_status",
        value="ENFORCEMENT_ACTIVE_STAGE_29_LIVE",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_projection_measurement_status() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_projection_field(
        rec,
        field_name="measurement_status",
        value="NOT_A_REAL_MEASUREMENT_STATUS",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_projection_migration_source() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_projection_field(
        rec,
        field_name="migration_source",
        value="NOT_A_REAL_MIGRATION_SOURCE",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_projection_join_status() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_projection_field(
        rec,
        field_name="join_status_echoed",
        value="NOT_A_REAL_JOIN_STATUS",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_projection_warning_with_forbidden_substring() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_projection_field(
        rec,
        field_name="warnings",
        value=(
            "h"
            + "ttps://discord"
            + ".com/api/webhooks/leak",
        ),
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_rejects_post_recording_mutated_projection_observed_at() -> None:
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    _mutate_recorded_projection_field(
        rec,
        field_name="observed_at_utc",
        value="not-a-utc-string",
    )
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is None
    assert not (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    ).exists()


def test_writer_valid_projection_still_writes_artifact() -> None:
    """Baseline: an unmutated projection still writes the
    artifact. Confirms the projection validator's positive path
    (every check returns True for a real recorder-built entry).
    """
    rec = _build_recorder_with_entries(mints=[_BASE_MINT])
    writer = Stage29_5_5SideChannelArtifactWriter()
    out = _outside_repo_tmpdir()
    result = writer.write_side_channel_artifact(
        output_dir=out, migration_source=rec,
    )
    assert result is not None
    assert result.exists()
    assert result.is_file()
    bundle = json.loads(result.read_text(encoding="utf-8"))
    assert bundle["entry_count"] == 1
    ps = bundle["entries"][0]["projection_summary"]
    assert ps["redaction_status"] == "SAFE"
    assert (
        ps["filter_enforcement_status"]
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# Slot semantics
# ---------------------------------------------------------------------------


def test_writer_class_defines_slots() -> None:
    assert hasattr(
        Stage29_5_5SideChannelArtifactWriter, "__slots__",
    )
