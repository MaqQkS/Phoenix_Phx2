"""Stage 29.5.6 private ping body migration context injector
core behavior + Stage 29.3 mode-3 integration pins.

Unit pins (no Stage 29.3 ceremony):

  * Injector construction with a None / arbitrary / Stage 29.5.5
    recorder ``migration_source`` succeeds without raising.
  * ``wrap_transport(inner)`` returns a wrapper exposing the
    Stage 28.6 ``send_one_audited_post(*, webhook_identity,
    payload)`` shape.
  * Wrapper with a None / duck-type-miss / empty
    ``recorded_entries`` migration_source forwards the payload
    unchanged.
  * Wrapper with a safe recorded entry appends the rendered
    ``body_text`` to a COPY of ``payload["content"]``.
  * Wrapper preserves all non-``content`` payload keys; the
    original payload reference is never mutated.
  * Wrapper attempts the full rendered ``body_text`` first;
    when the projected full combined length exceeds the locked
    1900-character cap, the wrapper falls back to a
    deterministic compact migration-context block built from
    already-revalidated rendered-block closed-set / display
    fields. When the projected compact combined length also
    exceeds the cap, the wrapper skips the append entirely
    (never truncates).
  * Wrapper re-validates the rendered block via
    ``stage29_5_5_rendered_block_is_safe_for_serialization``
    immediately before each append; an unsafe block is dropped
    silently.
  * Wrapper does NOT swallow exceptions raised by the inner
    transport itself.
  * The appended ``body_text`` carries no URL host / API-key /
    raw secret / raw JSON blob; the Stage 29.5.5 forbidden-
    substring scanner gates every appended string.

Integration pins (full Stage 29.3 mode-3 ceremony with fakes):

  * Default (no ``private_discord_body_injector`` kwarg): the
    dispatched payload bytes are BYTE-EQUIVALENT to the
    pre-Stage-29.5.6 code path.
  * Injector wired with Stage 29.5.5 recorder: dispatched body
    contains the migration block; dispatched-Discord count is
    exactly one; ``filter_enforcement_status`` remains
    ``NOT_ACTIVE_STAGE_29_PENDING``.
  * Injector wired but recorder is None: dispatched body
    unchanged.
  * Injector with a failing ``wrap_transport``: Stage 29.3
    catches; original Stage 28.9 transport used unchanged.
  * Modes 1 + 2: injector never invoked.
  * Side-channel artifact write (Stage 29.5.5 writer) and body
    injection (Stage 29.5.6) are independent: both can be wired
    simultaneously; both happen exactly once.

No live network. No real WebSocket / gRPC / HTTP. No real
Discord webhook.
"""

from __future__ import annotations

import inspect
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

import pytest

from PHX2.proto.stage28_11._generated import (
    geyser_pb2 as _geyser_pb2,
)
from PHX2.stage27.price_ath_context_models import (
    AthContextRecord,
)
from PHX2.stage27.price_ath_context_reader import (
    MigrationSourceSnapshot,
)
from PHX2.stage28.audited_http_transport_models import (
    REDACTION_STATUS_REDACTED as _ST28_4_REDACTION_STATUS_REDACTED,
    RESPONSE_BODY_STATUS_DROPPED_UNRECORDED,
    SEND_ATTEMPT_COUNT_SENT_ONCE,
    STAGE28_4_SCHEMA_VERSION,
    Stage28_4TransportResult,
    TRANSPORT_STATUS_SENT_OK,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
)
from PHX2.stage28.audited_http_transport_models import (
    derive_safe_reason_code as _st28_4_derive_safe_reason_code,
)
from PHX2.stage28.chainstack_yellowstone_grpc_models import (
    MODE_ONE_EVENT_DECODE_DRY_RUN,
    build_chainstack_yellowstone_grpc_endpoint_secret,
    build_chainstack_yellowstone_grpc_runtime_config,
)
from PHX2.stage28.chainstack_yellowstone_models import (
    AUTH_MODE_XTOKEN,
    CHAIN_SOLANA,
    PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
    build_chainstack_yellowstone_config,
)
from PHX2.stage29.pumpswap_program_constants import (
    SPL_TOKEN_PROGRAM_ID,
    WRAPPED_SOL_MINT,
)
from PHX2.stage29.stage29_2_birdeye_http_transport import (
    Stage29_2BirdeyeHttpResult,
)
from PHX2.stage29.stage29_2_birdeye_models import (
    BIRDEYE_REFUSAL_REASON_NONE,
)
from PHX2.stage29.stage29_2_birdeye_readiness import (
    Stage29_2BirdeyeEndpointSecret,
    Stage29_2BirdeyeRuntimeConfig,
)
from PHX2.stage29.stage29_3_smoke_models import (
    PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
    PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
    PROBE_MODE_READINESS_ONLY,
    TRADEABLE_SMOKE_OUTCOME_DISPATCHED,
)
from PHX2.stage29.stage29_3_tradeable_smoke import (
    Stage29_3RuntimeConfigBundle,
    run_stage29_3_first_private_tradeable_smoke,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    MEASUREMENT_STATUS_COMPLETE,
    MEASUREMENT_STATUS_MISSING_MIGRATION,
    MIGRATION_JOIN_STATUS_JOINED,
    MIGRATION_JOIN_STATUS_NO_MATCH,
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
from PHX2.stage29.stage29_5_5_render_models import (
    Stage29_5_5RecordedRenderEntry,
    Stage29_5_5RenderedMigrationContextBlock,
)
from PHX2.stage29.stage29_5_5_side_channel_artifact_writer import (
    STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME,
    Stage29_5_5SideChannelArtifactWriter,
)
from PHX2.stage29.stage29_5_6_private_ping_migration_context_injector import (
    STAGE29_5_6_CONTENT_MAX_CHARS,
    STAGE29_5_6_PRIVATE_DISCORD_BODY_INJECTOR_SCHEMA_VERSION,
    Stage29_5_6PrivateDiscordBodyInjector,
)


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------


_TEST_BASE_MINT: str = (
    "TestBaseMintAAAA1111111111111111111111111A"
)
_TEST_POOL_OWNER: str = (
    "TestPoolXXXXXXX3333333333333333333333333X"
)
_TEST_POOL_PROGRAM_ID: str = (
    "PoolProgramIDDDDDDD22222222222222222222222D"
)
_TEST_QUOTE_MINT: str = (
    "QuoteMintEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE"
)
_TEST_PROVIDER_ID: str = "chainstack_yellowstone_test"
_TEST_ENDPOINT: str = "yellowstone.test.local:443"
_TEST_X_TOKEN: str = "test_x_token_abc1234567890"
_TEST_BIRDEYE_API_KEY: str = (
    "test_birdeye_api_key_abc1234567890"
)
_TEST_BIRDEYE_BASE_URL: str = "https://public-api.test.local"
_TEST_PRIVATE_WEBHOOK_URL: str = (
    "https://discord.com/api/webhooks/123456789012345678/"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
_TEST_MIGRATION_TS: str = "2026-01-01T00:00:05+00:00"
_TEST_OBSERVED_AT: str = "2026-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Unit-test helpers: real Stage 29.5.5 projection + rendered block
# ---------------------------------------------------------------------------


def _build_complete_helius_projection() -> (
    Stage29_5PrivatePingMigrationContext
):
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=MEASUREMENT_STATUS_COMPLETE,
        warnings=(),
        migration_timestamp_utc=_TEST_MIGRATION_TS,
        migration_slot=12345,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        post_migration_ath_verified=True,
        join_status_echoed=MIGRATION_JOIN_STATUS_JOINED,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_TEST_OBSERVED_AT,
    )


def _build_missing_unknown_projection() -> (
    Stage29_5PrivatePingMigrationContext
):
    return Stage29_5PrivatePingMigrationContext(
        measurement_status=MEASUREMENT_STATUS_MISSING_MIGRATION,
        warnings=("MIGRATION_MISSING",),
        migration_timestamp_utc=None,
        migration_slot=None,
        migration_source=MIGRATION_SOURCE_UNKNOWN_STAGE29_5,
        post_migration_ath_verified=None,
        join_status_echoed=MIGRATION_JOIN_STATUS_NO_MATCH,
        redaction_status=REDACTION_STATUS_SAFE,
        filter_enforcement_status=(
            FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ),
        observed_at_utc=_TEST_OBSERVED_AT,
    )


def _build_real_rendered_block(
    projection: Stage29_5PrivatePingMigrationContext,
) -> Stage29_5_5RenderedMigrationContextBlock:
    return render_private_discord_migration_context_block(
        projection,
    )


def _build_real_recorded_entry(
    projection: Stage29_5PrivatePingMigrationContext,
    block: Stage29_5_5RenderedMigrationContextBlock,
) -> Stage29_5_5RecordedRenderEntry:
    snapshot = MigrationSourceSnapshot(
        migration_event_id="evt-001",
        migration_timestamp_utc=(
            projection.migration_timestamp_utc
        ),
        migration_source=projection.migration_source,
        source_event_ref="evt-ref-001",
        raw_capture_ref=None,
    )
    return Stage29_5_5RecordedRenderEntry(
        token_mint=_TEST_BASE_MINT,
        projection=projection,
        rendered_block=block,
        snapshot=snapshot,
        recorded_at_utc=_TEST_OBSERVED_AT,
    )


class _FakeRecorder:
    """Minimal duck-typed Stage 29.5.5 recorder for unit tests.

    Exposes only ``recorded_entries`` -- the Stage 29.5.6
    wrapper's sole point of contact with the recorder Protocol.
    """

    __slots__ = ("_entries",)

    def __init__(
        self,
        *,
        entries: tuple[
            Stage29_5_5RecordedRenderEntry, ...
        ],
    ) -> None:
        self._entries = entries

    @property
    def recorded_entries(
        self,
    ) -> tuple[Stage29_5_5RecordedRenderEntry, ...]:
        return self._entries


class _RecordingInnerTransport:
    """Stage 28.6-shaped fake inner transport. Records every
    ``send_one_audited_post`` call and returns a scripted
    Stage 28.4 transport result.
    """

    def __init__(
        self,
        *,
        scripted_result: Stage28_4TransportResult,
    ) -> None:
        self._scripted_result = scripted_result
        self.calls: list[dict] = []

    def send_one_audited_post(
        self,
        *,
        webhook_identity: str,
        payload: object,
    ) -> Stage28_4TransportResult:
        recorded_payload: dict
        if isinstance(payload, dict):
            recorded_payload = dict(payload)
        else:
            recorded_payload = {}
        self.calls.append(
            {
                "webhook_identity": webhook_identity,
                "payload": recorded_payload,
            }
        )
        return self._scripted_result


class _RaisingInnerTransport:
    """Stage 28.6-shaped fake inner transport that raises on every
    ``send_one_audited_post`` call. Used to pin that the
    wrapper does NOT swallow inner-transport exceptions.
    """

    def send_one_audited_post(
        self,
        *,
        webhook_identity: str,
        payload: object,
    ) -> object:
        raise RuntimeError("simulated inner-transport failure")


def _build_sent_ok_result() -> Stage28_4TransportResult:
    return Stage28_4TransportResult(
        transport_status=TRANSPORT_STATUS_SENT_OK,
        ok=True,
        http_status_code=204,
        retry_after_seconds=None,
        send_attempt_count=SEND_ATTEMPT_COUNT_SENT_ONCE,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        redaction_status=_ST28_4_REDACTION_STATUS_REDACTED,
        safe_reason_code=_st28_4_derive_safe_reason_code(
            TRANSPORT_STATUS_SENT_OK,
        ),
        response_body_status=(
            RESPONSE_BODY_STATUS_DROPPED_UNRECORDED
        ),
        schema_version=STAGE28_4_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------------
# UNIT 1 — Injector construction + wrap_transport surface
# ---------------------------------------------------------------------------


def test_injector_accepts_none_migration_source() -> None:
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=None,
    )
    assert injector.bound_migration_source is None


def test_injector_accepts_arbitrary_object_migration_source() -> None:
    sentinel = object()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=sentinel,
    )
    assert injector.bound_migration_source is sentinel


def test_wrap_transport_returns_wrapper_with_send_one_audited_post() -> None:
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=None,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    assert hasattr(wrapper, "send_one_audited_post")


def test_wrapper_repr_does_not_leak_inner_url() -> None:
    """The injector __repr__ must not echo any URL substring.
    The wrapper itself is module-private and not asserted on
    here.
    """
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=None,
    )
    rendering = repr(injector)
    assert "discord" + ".com" not in rendering.lower()
    assert "h" + "ttp" not in rendering.lower()


# ---------------------------------------------------------------------------
# UNIT 2 — Forwarding without append (every duck-type-miss path)
# ---------------------------------------------------------------------------


def test_wrapper_with_none_migration_source_forwards_unchanged() -> None:
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=None,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    original_payload = {"content": "stage28_9 body"}
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=original_payload,
    )
    assert inner.calls[0]["payload"]["content"] == (
        "stage28_9 body"
    )
    # Original payload is not mutated.
    assert original_payload == {"content": "stage28_9 body"}


def test_wrapper_with_object_lacking_recorded_entries_forwards_unchanged() -> None:
    arbitrary = object()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=arbitrary,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    assert inner.calls[0]["payload"]["content"] == (
        "stage28_9 body"
    )


def test_wrapper_with_empty_recorded_entries_forwards_unchanged() -> None:
    recorder = _FakeRecorder(entries=())
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    assert inner.calls[0]["payload"]["content"] == (
        "stage28_9 body"
    )


def test_wrapper_with_non_tuple_recorded_entries_forwards_unchanged() -> None:
    class _BogusRecorder:
        recorded_entries = ["not", "a", "tuple"]

    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=_BogusRecorder(),
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    assert inner.calls[0]["payload"]["content"] == (
        "stage28_9 body"
    )


# ---------------------------------------------------------------------------
# UNIT 3 — Append on safe entry
# ---------------------------------------------------------------------------


def test_wrapper_appends_body_text_when_entry_is_safe() -> None:
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    dispatched_content = inner.calls[0]["payload"]["content"]
    assert dispatched_content.startswith("stage28_9 body\n\n")
    assert (
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
        in dispatched_content
    )
    assert "informational_only: true" in dispatched_content
    assert "not_a_trading_verdict: true" in dispatched_content
    assert (
        "filter_enforcement_status: NOT_ACTIVE_STAGE_29_PENDING"
        in dispatched_content
    )
    assert "MIGRATION_EVIDENCE_COMPLETE" in dispatched_content
    assert "SOURCE_TRUSTED_ON_CHAIN" in dispatched_content
    assert (
        "ATH_VERIFIED_POST_MIGRATION" in dispatched_content
    )


def test_wrapper_appends_missing_display_tokens_for_missing_projection() -> None:
    projection = _build_missing_unknown_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    dispatched_content = inner.calls[0]["payload"]["content"]
    assert "MIGRATION_EVIDENCE_MISSING" in dispatched_content
    assert "SOURCE_NO_SOURCE" in dispatched_content
    assert (
        "ATH_VERIFICATION_UNKNOWN" in dispatched_content
    )


# ---------------------------------------------------------------------------
# UNIT 4 — Payload-handling discipline
# ---------------------------------------------------------------------------


def test_wrapper_does_not_mutate_original_payload_dict() -> None:
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    original = {"content": "stage28_9 body"}
    snapshot_before = dict(original)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload=original,
    )
    assert original == snapshot_before, (
        "Stage 29.5.6 wrapper must not mutate the original "
        "payload dict; it must mutate a copy."
    )


def test_wrapper_preserves_additional_payload_keys() -> None:
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={
            "content": "stage28_9 body",
            "username": "phx2_operator",
            "embeds": [],
        },
    )
    dispatched = inner.calls[0]["payload"]
    assert dispatched["username"] == "phx2_operator"
    assert dispatched["embeds"] == []
    assert dispatched["content"].startswith(
        "stage28_9 body\n\n",
    )


def test_wrapper_skips_when_payload_not_a_dict() -> None:
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload="not a dict",
    )
    # Inner transport sees the same non-dict payload
    # (the wrapper records its dict-copy as {} so we just assert
    # the inner transport recorded a call).
    assert len(inner.calls) == 1


def test_wrapper_skips_when_content_field_missing() -> None:
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"username": "phx2_operator"},
    )
    dispatched = inner.calls[0]["payload"]
    assert "content" not in dispatched


def test_wrapper_skips_when_content_field_empty_string() -> None:
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": ""},
    )
    assert inner.calls[0]["payload"]["content"] == ""


# ---------------------------------------------------------------------------
# UNIT 5 — 1900-char cap discipline (full → compact → skip, never truncate)
# ---------------------------------------------------------------------------


def test_wrapper_skips_when_full_and_compact_both_overflow_cap() -> None:
    """When the operator-supplied Stage 28.9 body is so close to
    the 1900-char cap that BOTH the full Stage 29.5.5
    ``body_text`` AND the deterministic compact fallback would
    overflow, the wrapper must skip the append entirely (never
    truncate, never append a partial / invented block) and
    forward the original payload unchanged.
    """
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    # Fill content close to the cap so combined would overflow
    # for BOTH the full body_text AND the compact fallback. The
    # full body_text is ~625 chars; the compact block is ~240
    # chars. A 1890-char existing body overflows both:
    #   full:    1890 + 2 + 625  = 2517 > 1900
    #   compact: 1890 + 2 + ~240 = ~2132 > 1900
    fat_existing = "x" * (
        STAGE29_5_6_CONTENT_MAX_CHARS - 10
    )
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": fat_existing},
    )
    dispatched_content = inner.calls[0]["payload"]["content"]
    # No append happened; content is unchanged byte-for-byte.
    assert dispatched_content == fat_existing
    # Neither the full block header nor the compact block header
    # was injected.
    assert (
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
        not in dispatched_content
    )
    assert "[MIGRATION CONTEXT]" not in dispatched_content
    assert (
        "filter_enforcement_status: NOT_ACTIVE_STAGE_29_PENDING"
        not in dispatched_content
    )


def test_wrapper_appends_compact_when_full_overflows_but_compact_fits() -> None:
    """When the operator-supplied Stage 28.9 body would overflow
    the cap if appended with the full Stage 29.5.5 ``body_text``
    but DOES leave room for the deterministic compact fallback,
    the wrapper must append the compact block (not the full
    body_text) and the dispatched content must stay within the
    locked cap.
    """
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    # 1500-char body sized so:
    #   full:    1500 + 2 + 625  = 2127 > 1900 (overflows)
    #   compact: 1500 + 2 + ~240 = ~1742 <= 1900 (fits)
    medium_existing = "y" * 1500
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": medium_existing},
    )
    dispatched_content = inner.calls[0]["payload"]["content"]
    # The compact block was appended (not the full body_text).
    assert dispatched_content.startswith(medium_existing + "\n\n")
    assert "[MIGRATION CONTEXT]" in dispatched_content
    # The full body_text header MUST NOT appear -- the wrapper
    # must NOT have appended the full block.
    assert (
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
        not in dispatched_content
    )
    # Compact block carries the safety pins verbatim.
    assert (
        "filter_enforcement_status: NOT_ACTIVE_STAGE_29_PENDING"
        in dispatched_content
    )
    assert "informational_only: true" in dispatched_content
    assert "not_a_trading_verdict: true" in dispatched_content
    # Compact block carries the closed-set migration display
    # tokens from the rendered block.
    assert "MIGRATION_EVIDENCE_COMPLETE" in dispatched_content
    assert "SOURCE_TRUSTED_ON_CHAIN" in dispatched_content
    assert "ATH_VERIFIED_POST_MIGRATION" in dispatched_content
    # Dispatched content stays within the locked cap.
    assert len(dispatched_content) <= (
        STAGE29_5_6_CONTENT_MAX_CHARS
    )
    # Compact body MUST NOT carry raw JSON braces.
    appended = dispatched_content.split("\n\n", 1)[1]
    assert "{" not in appended
    assert "}" not in appended


def test_wrapper_appends_when_combined_length_within_cap() -> None:
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    short_existing = "stage28_9 body"
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": short_existing},
    )
    dispatched_content = inner.calls[0]["payload"]["content"]
    assert dispatched_content.startswith(short_existing + "\n\n")
    assert len(dispatched_content) <= (
        STAGE29_5_6_CONTENT_MAX_CHARS
    )


# ---------------------------------------------------------------------------
# UNIT 6 — Failure paths
# ---------------------------------------------------------------------------


def test_wrapper_does_not_swallow_inner_transport_exceptions() -> None:
    """The wrapper swallows its own internal failures (recorder
    read / validator / copy build) but MUST NOT swallow
    exceptions raised by the inner transport itself. The inner
    transport's failure is the caller's failure.
    """
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    wrapper = injector.wrap_transport(
        _RaisingInnerTransport(),
    )
    with pytest.raises(RuntimeError):
        wrapper.send_one_audited_post(
            webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
            payload={"content": "stage28_9 body"},
        )


class _BadRecorderRaisingOnRecordedEntries:
    """Bogus recorder that raises when ``recorded_entries`` is
    accessed. The wrapper must swallow this and forward the
    payload unchanged.
    """

    @property
    def recorded_entries(self) -> tuple:
        raise RuntimeError("simulated recorder failure")


def test_wrapper_swallows_recorder_attribute_failure() -> None:
    bad = _BadRecorderRaisingOnRecordedEntries()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=bad,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    assert inner.calls[0]["payload"]["content"] == (
        "stage28_9 body"
    )


class _BadEntry:
    """Entry whose ``rendered_block`` is not a
    ``Stage29_5_5RenderedMigrationContextBlock``.
    """

    @property
    def rendered_block(self) -> object:
        return "not a rendered block"


def test_wrapper_drops_unsafe_rendered_block() -> None:
    class _RecorderWithBadEntry:
        recorded_entries = (_BadEntry(),)

    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=_RecorderWithBadEntry(),
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    assert inner.calls[0]["payload"]["content"] == (
        "stage28_9 body"
    )


# ---------------------------------------------------------------------------
# UNIT 7 — Calls-forwarded counter + multiple dispatches
# ---------------------------------------------------------------------------


def test_wrapper_increments_calls_forwarded() -> None:
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    assert wrapper.calls_forwarded == 0
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    assert wrapper.calls_forwarded == 1


def test_wrapper_uses_latest_entry_on_multiple_recorded_entries() -> None:
    """When the recorder has more than one entry (e.g. a future
    multi-candidate ceremony), the injector reads the LATEST
    entry's rendered block.
    """
    proj_a = _build_complete_helius_projection()
    block_a = _build_real_rendered_block(proj_a)
    entry_a = _build_real_recorded_entry(proj_a, block_a)
    proj_b = _build_missing_unknown_projection()
    block_b = _build_real_rendered_block(proj_b)
    entry_b = _build_real_recorded_entry(proj_b, block_b)
    recorder = _FakeRecorder(entries=(entry_a, entry_b))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    dispatched = inner.calls[0]["payload"]["content"]
    # Latest entry is entry_b -> MISSING projection.
    assert "MIGRATION_EVIDENCE_MISSING" in dispatched
    # The earlier entry's COMPLETE token must NOT appear.
    assert "MIGRATION_EVIDENCE_COMPLETE" not in dispatched


# ---------------------------------------------------------------------------
# UNIT 8 — Forbidden-substring discipline on appended body
# ---------------------------------------------------------------------------


_FORBIDDEN_DISPATCHED_BODY_SUBSTRINGS: tuple[str, ...] = (
    "discord" + ".com",
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "B" + "earer ",
    "A" + "uthorization:",
    "DISCORD_WEBHOOK" + "_URL=",
    "BIRDEYE_API" + "_KEY=",
    "HELIUS_API" + "_KEY=",
    "api.helius" + ".xyz",
    "yellowstone" + ".chainstack",
    "wallet" + "_signer",
    "private" + "_key_loader",
    "buy" + "_signal",
    "sell" + "_signal",
    "auto" + "_trade",
)


@pytest.mark.parametrize(
    "needle", _FORBIDDEN_DISPATCHED_BODY_SUBSTRINGS,
)
def test_dispatched_body_carries_no_forbidden_substring(
    needle: str,
) -> None:
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    dispatched = inner.calls[0]["payload"]["content"]
    assert needle not in dispatched, (
        f"Stage 29.5.6 dispatched body must not carry the "
        f"forbidden substring {needle!r}; offending dispatched "
        f"body length {len(dispatched)}"
    )


def test_dispatched_body_carries_no_trading_verdict_language() -> None:
    """The Stage 29.5.5 rendered block's ``body_text`` is
    constructed by the Stage 29.5.5 renderer which pins
    informational_only=True and not_a_trading_verdict=True. The
    Stage 29.5.6 injector must therefore never produce a
    dispatched body carrying trading-verdict language.
    """
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    dispatched_lower = (
        inner.calls[0]["payload"]["content"].lower()
    )
    # The full Stage 29.5.5 body_text uses upper-case verdict
    # tokens; we scan for trading-verdict variants on the
    # appended section only. The Stage 28.9 base body may
    # legitimately contain "approved" or "block" prose; we
    # therefore only assert that the appended Stage 29.5.5
    # section does not introduce these tokens.
    appended = dispatched_lower.split("\n\n", 1)[1]
    for token in (
        " buy ",
        " sell ",
        " auto-trade ",
        " execute trade ",
        " position size ",
    ):
        assert token not in appended, (
            f"Stage 29.5.6 appended body must not carry "
            f"trading-verdict token {token!r}"
        )


def test_dispatched_body_carries_no_raw_json_blob() -> None:
    """The appended Stage 29.5.5 ``body_text`` is plain-text
    line-by-line; the Stage 29.5.6 injector must never append
    a raw JSON blob. We assert the appended section has no
    ``{`` / ``}`` brace characters typical of a JSON literal.
    """
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "stage28_9 body"},
    )
    dispatched = inner.calls[0]["payload"]["content"]
    appended = dispatched.split("\n\n", 1)[1]
    assert "{" not in appended
    assert "}" not in appended


# ---------------------------------------------------------------------------
# Integration helpers (mirror Stage 29.5.5 stage29_3 integration test)
# ---------------------------------------------------------------------------


class _FakeStreamCallable:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses

    def __call__(
        self, request_iterator, timeout=None, metadata=None,
    ):
        for _ in request_iterator:
            pass
        return _FakeResponseIter(self._responses)


class _FakeResponseIter:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self._idx = 0
        self.cancel_called = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._idx >= len(self._responses):
            raise StopIteration
        item = self._responses[self._idx]
        self._idx += 1
        return item

    def cancel(self):
        self.cancel_called = True


class _FakeUnusedCallable:
    def __init__(self, method: str) -> None:
        self._method = method

    def __call__(self, *args, **kwargs):
        raise AssertionError(
            f"Stage 29.3 source must not invoke "
            f"{self._method!r}"
        )


class _FakeChannel:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.close_called = False

    def stream_stream(
        self,
        method,
        request_serializer=None,
        response_deserializer=None,
        **kwargs,
    ):
        if method.endswith("/Subscribe"):
            return _FakeStreamCallable(self._responses)
        return _FakeUnusedCallable(method)

    def unary_unary(self, method, **kwargs):
        return _FakeUnusedCallable(method)

    def stream_unary(self, method, **kwargs):
        return _FakeUnusedCallable(method)

    def unary_stream(self, method, **kwargs):
        return _FakeUnusedCallable(method)

    def close(self):
        self.close_called = True


def _make_factory(responses):
    captured: dict = {}

    def factory(target, credentials):
        captured["target"] = target
        captured["credentials"] = credentials
        ch = _FakeChannel(responses)
        captured["channel"] = ch
        return ch

    return factory, captured


def _make_pumpswap_tx_update() -> "_geyser_pb2.SubscribeUpdate":
    update = _geyser_pb2.SubscribeUpdate()
    update.created_at.seconds = 1_700_000_000
    update.transaction.slot = 100
    update.transaction.transaction.signature = bytes(
        range(1, 65),
    )
    update.transaction.transaction.is_vote = False
    update.transaction.transaction.index = 0
    update.transaction.transaction.meta.fee = 5000

    def _add(account_index, mint, owner):
        meta = update.transaction.transaction.meta
        pre = meta.pre_token_balances.add()
        pre.account_index = account_index
        pre.mint = mint
        pre.owner = owner
        pre.program_id = SPL_TOKEN_PROGRAM_ID
        post = meta.post_token_balances.add()
        post.account_index = account_index
        post.mint = mint
        post.owner = owner
        post.program_id = SPL_TOKEN_PROGRAM_ID

    _add(0, WRAPPED_SOL_MINT, _TEST_POOL_OWNER)
    _add(1, _TEST_BASE_MINT, _TEST_POOL_OWNER)
    return update


class _FakeBirdeyeHttpTransport:
    def __init__(
        self,
        *,
        bodies_by_path: Mapping[str, Optional[dict]],
    ) -> None:
        self._bodies_by_path = dict(bodies_by_path)
        self.calls: list[dict] = []

    def get(
        self,
        *,
        endpoint_secret: Stage29_2BirdeyeEndpointSecret,
        path: str,
        query_params: Mapping[str, str],
        timeout_seconds: int,
    ) -> Stage29_2BirdeyeHttpResult:
        self.calls.append(
            {
                "path": path,
                "query_params": dict(query_params),
                "timeout_seconds": timeout_seconds,
            }
        )
        body = self._bodies_by_path.get(path)
        return Stage29_2BirdeyeHttpResult(
            refusal_reason=BIRDEYE_REFUSAL_REASON_NONE,
            http_status_code=200,
            body=body if body is not None else None,
            fetched_at_utc=datetime.now(
                timezone.utc,
            ).isoformat(),
        )


class _FakeAuditedDiscordTransport:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_one_audited_post(
        self,
        *,
        webhook_url: str,
        webhook_identity: str,
        payload,
    ) -> Stage28_4TransportResult:
        self.calls.append(
            {
                "webhook_url": webhook_url,
                "webhook_identity": webhook_identity,
                "payload": (
                    dict(payload)
                    if isinstance(payload, dict)
                    else {}
                ),
            }
        )
        return _build_sent_ok_result()

    @property
    def call_count(self) -> int:
        return len(self.calls)


def _build_test_runtime_configs() -> Stage29_3RuntimeConfigBundle:
    cs_safe = build_chainstack_yellowstone_config(
        provider_id=_TEST_PROVIDER_ID,
        endpoint_safe_label="yellowstone_test_endpoint",
        auth_mode=AUTH_MODE_XTOKEN,
        max_events=1,
        provider_kind=PROVIDER_KIND_CHAINSTACK_YELLOWSTONE,
        chain=CHAIN_SOLANA,
    )
    cs_secret = build_chainstack_yellowstone_grpc_endpoint_secret(
        endpoint_url=_TEST_ENDPOINT,
        x_token=_TEST_X_TOKEN,
        tls=True,
    )
    cs_config = build_chainstack_yellowstone_grpc_runtime_config(
        safe_config=cs_safe,
        endpoint_secret=cs_secret,
        mode=MODE_ONE_EVENT_DECODE_DRY_RUN,
        timeout_seconds=30,
    )
    birdeye_secret = Stage29_2BirdeyeEndpointSecret(
        _api_key=_TEST_BIRDEYE_API_KEY,
        _base_url=_TEST_BIRDEYE_BASE_URL,
    )
    birdeye_config = Stage29_2BirdeyeRuntimeConfig(
        endpoint_secret=birdeye_secret,
        timeout_seconds=10,
        live_flag_set=True,
    )
    return Stage29_3RuntimeConfigBundle(
        chainstack=cs_config, birdeye=birdeye_config,
    )


def _outside_repo_tmpdir() -> Path:
    return Path(
        tempfile.mkdtemp(prefix="phx2_stage29_5_6_test_"),
    )


def _build_birdeye_bodies() -> Mapping[str, dict]:
    return {
        "/defi/price": {
            "data": {
                "value": 0.000036,
                "updateUnixTime": 1779678781,
            },
        },
        "/defi/ohlcv": {
            "data": {
                "items": [
                    {"h": 0.000054, "unixTime": 1779592200},
                ],
            },
        },
    }


def _evidence_for(token_mint: str) -> tuple[
    Stage29_5MigrationEvidenceRecord, ...
]:
    return (
        Stage29_5MigrationEvidenceRecord(
            migration_status=MIGRATION_STATUS_PRESENT,
            migration_source=MIGRATION_SOURCE_HELIUS_WS,
            base_mint=token_mint,
            pool_account=_TEST_POOL_OWNER,
            pool_program_id=_TEST_POOL_PROGRAM_ID,
            quote_mint=_TEST_QUOTE_MINT,
            migration_timestamp_utc=_TEST_MIGRATION_TS,
            migration_slot=12345,
            migration_signature="Sig" + "X" * 60,
            observed_at_utc=_TEST_OBSERVED_AT,
            source_event_ref="evt-001",
        ),
    )


def _ath_context_for(
    token_mint: str,
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


def _build_recorder() -> Stage29_5_5MigrationContextRecorder:
    return Stage29_5_5MigrationContextRecorder(
        evidence_provider=_evidence_for,
        ath_context_provider=_ath_context_for,
        clock=lambda: _TEST_OBSERVED_AT,
        renderer=(
            render_private_discord_migration_context_block
        ),
    )


# ---------------------------------------------------------------------------
# INT 1 — Stage 29.3 entrypoint accepts the new kwarg
# ---------------------------------------------------------------------------


def test_stage_29_3_entrypoint_accepts_private_discord_body_injector_kwarg() -> None:
    sig = inspect.signature(
        run_stage29_3_first_private_tradeable_smoke,
    )
    assert "private_discord_body_injector" in sig.parameters
    param = sig.parameters["private_discord_body_injector"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is None


# ---------------------------------------------------------------------------
# INT 2 — Default (no injector): body byte-equivalent to pre-29.5.6
# ---------------------------------------------------------------------------


def test_default_no_injector_dispatched_body_carries_no_29_5_5_block() -> None:
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()

    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        # private_discord_body_injector omitted (None)
    )

    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1
    dispatched_content = (
        fake_discord.calls[0]["payload"]["content"]
    )
    # Stage 28.9 header is present.
    assert (
        "PHX2 STAGE 28.9 PRIVATE OPERATOR PING"
        in dispatched_content
    )
    # Stage 29.5.5 block is NOT present (no injector wired).
    assert (
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
        not in dispatched_content
    )


# ---------------------------------------------------------------------------
# INT 3 — Injector wired with recorder: dispatched body contains block
# ---------------------------------------------------------------------------


def test_injector_wired_with_recorder_dispatches_cap_aware() -> None:
    """End-to-end Stage 29.3 mode-3 ceremony with the Stage
    29.5.6 injector wired. The wrapper is cap-aware: it tries
    the full Stage 29.5.5 ``body_text`` first; when the
    combined ``Stage 28.9 body + "\\n\\n" + body_text`` would
    overflow the locked ``STAGE29_5_6_CONTENT_MAX_CHARS`` (1900)
    cap, it falls back to a deterministic compact migration-
    context block built from already-revalidated rendered-block
    closed-set / display fields. The realistic Stage 29.3 mode-3
    ceremony produces a Stage 28.9 body large enough to force
    the compact fallback; the dispatched body therefore carries
    the compact migration-context block AND stays within the
    1900-character cap. The Stage 28.9 dispatch counter is
    exactly one regardless of which append path is taken.
    """
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recorder = _build_recorder()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )

    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recorder,
        private_discord_body_injector=injector,
    )

    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1
    dispatched_content = (
        fake_discord.calls[0]["payload"]["content"]
    )

    # The Stage 28.9 header is always present (the wrapper
    # never strips the original body).
    assert (
        "PHX2 STAGE 28.9 PRIVATE OPERATOR PING"
        in dispatched_content
    )

    # Dispatched body must stay within the locked cap on EVERY
    # branch (full body_text append, compact fallback, or skip).
    assert len(dispatched_content) <= (
        STAGE29_5_6_CONTENT_MAX_CHARS
    )

    # The recorder MUST have captured at least one entry
    # (Stage 27.6 candidate assembly called the recorder during
    # the ceremony).
    entries = recorder.recorded_entries
    assert len(entries) >= 1, (
        "recorder must capture at least one entry when wired "
        "as migration_source"
    )

    # Realistic Stage 29.3 mode-3 must emit the migration
    # context: the wrapper tries full body_text first and falls
    # back to the deterministic compact block when the full
    # body_text would overflow the 1900-char cap. Either path
    # appends the three Stage 29.5.5 audit flags (the safety
    # pin lines), so they are the cross-path operator-readable
    # marker for "migration context is present".
    assert (
        "filter_enforcement_status: NOT_ACTIVE_STAGE_29_PENDING"
        in dispatched_content
    ), (
        "Stage 29.5.6 realistic mode-3 integration must emit a "
        "payload containing the migration context (full body "
        "or compact fallback); the wrapper must NOT silently "
        "skip the append"
    )
    assert "informational_only: true" in dispatched_content
    assert "not_a_trading_verdict: true" in dispatched_content


def test_injector_wired_block_appears_when_combined_fits_cap() -> None:
    """Unit-style proof that when the Stage 28.9 body is small
    enough, the dispatched body carries the FULL Stage 29.5.5
    rendered block. This test exercises the wrapper directly
    (bypassing the full Stage 29.3 mode-3 ceremony whose Stage
    28.9 body is typically large enough to trigger the compact
    fallback instead of the full block append).
    """
    projection = _build_complete_helius_projection()
    block = _build_real_rendered_block(projection)
    entry = _build_real_recorded_entry(projection, block)
    recorder = _FakeRecorder(entries=(entry,))
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )
    inner = _RecordingInnerTransport(
        scripted_result=_build_sent_ok_result(),
    )
    wrapper = injector.wrap_transport(inner)
    # A short Stage 28.9-shaped body well under the cap, so the
    # combined length will fit and the block must appear.
    wrapper.send_one_audited_post(
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        payload={"content": "PHX2 STAGE 28.9 PRIVATE OPERATOR PING\nshort body"},
    )
    dispatched = inner.calls[0]["payload"]["content"]
    assert (
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
        in dispatched
    )
    assert "informational_only: true" in dispatched
    assert "not_a_trading_verdict: true" in dispatched
    assert (
        "filter_enforcement_status: NOT_ACTIVE_STAGE_29_PENDING"
        in dispatched
    )
    assert len(dispatched) <= STAGE29_5_6_CONTENT_MAX_CHARS


def test_injector_wired_preserves_filter_enforcement_status() -> None:
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recorder = _build_recorder()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )

    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recorder,
        private_discord_body_injector=injector,
    )

    assert (
        result.filter_enforcement_status
        == "NOT_ACTIVE_STAGE_29_PENDING"
    )


# ---------------------------------------------------------------------------
# INT 4 — Injector wired but no recorder: dispatched body unchanged
# ---------------------------------------------------------------------------


def test_injector_with_none_migration_source_dispatched_body_unchanged() -> None:
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=None,
    )

    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        # migration_source omitted (None)
        private_discord_body_injector=injector,
    )

    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1
    dispatched_content = (
        fake_discord.calls[0]["payload"]["content"]
    )
    # No Stage 29.5.5 block because no recorder was wired.
    assert (
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
        not in dispatched_content
    )


# ---------------------------------------------------------------------------
# INT 5 — Failing wrap_transport: Stage 29.3 falls back to unwrapped
# ---------------------------------------------------------------------------


class _RaisingInjector:
    """Injector whose ``wrap_transport`` always raises. Stage
    29.3 mode-3 must catch and fall back to the unwrapped Stage
    28.9 transport.
    """

    def wrap_transport(self, inner_transport: object) -> object:
        raise RuntimeError("simulated injector failure")


class _NonConformingInjectorReturningNone:
    """Injector whose ``wrap_transport`` returns ``None``. Stage
    29.3 mode-3 must reject the candidate (None lacks
    ``send_one_audited_post``) and fall back to the unwrapped
    Stage 28.9 transport.
    """

    def wrap_transport(self, inner_transport: object) -> object:
        return None


class _NonConformingInjectorReturningBareObject:
    """Injector whose ``wrap_transport`` returns a bare object
    that lacks a ``send_one_audited_post`` attribute entirely.
    Stage 29.3 mode-3 must reject the candidate via the
    ``callable(getattr(candidate, "send_one_audited_post",
    None))`` gate and fall back to the unwrapped Stage 28.9
    transport.
    """

    def wrap_transport(self, inner_transport: object) -> object:
        return object()


class _NonConformingInjectorReturningNonCallableAttr:
    """Injector whose ``wrap_transport`` returns an object that
    HAS a ``send_one_audited_post`` attribute but it is NOT
    callable (a sentinel string). Stage 29.3 mode-3 must reject
    the candidate via the ``callable(...)`` half of the gate.
    """

    class _Bogus:
        send_one_audited_post = "not callable"

    def wrap_transport(self, inner_transport: object) -> object:
        return self._Bogus()


def test_failing_wrap_transport_falls_back_to_unwrapped_dispatch() -> None:
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()

    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        private_discord_body_injector=_RaisingInjector(),
    )

    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1
    dispatched_content = (
        fake_discord.calls[0]["payload"]["content"]
    )
    # Wrap failure means original Stage 28.9 transport was used;
    # no Stage 29.5.5 block in body.
    assert (
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
        not in dispatched_content
    )
    assert "[MIGRATION CONTEXT]" not in dispatched_content


@pytest.mark.parametrize(
    "non_conforming_injector_factory",
    [
        _NonConformingInjectorReturningNone,
        _NonConformingInjectorReturningBareObject,
        _NonConformingInjectorReturningNonCallableAttr,
    ],
)
def test_non_conforming_wrap_transport_return_falls_back_to_original(
    non_conforming_injector_factory: type,
) -> None:
    """When ``wrap_transport`` returns a non-conforming object
    (None / bare object / object whose ``send_one_audited_post``
    attribute is not callable), Stage 29.3 mode-3 must keep the
    original Stage 28.9 transport and continue dispatching
    normally. The dispatched body must be BYTE-EQUIVALENT to the
    pre-Stage-29.5.6 path (no migration context block).
    """
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()

    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        private_discord_body_injector=(
            non_conforming_injector_factory()
        ),
    )

    # Stage 29.3 mode-3 must dispatch normally; the non-
    # conforming wrap candidate must be silently rejected and
    # the original Stage 28.9 transport used.
    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )
    assert fake_discord.call_count == 1
    dispatched_content = (
        fake_discord.calls[0]["payload"]["content"]
    )
    # Stage 28.9 body shape: header is present, no Stage 29.5.5
    # block (full or compact) is appended because the original
    # transport (not the non-conforming wrapper) was used.
    assert (
        "PHX2 STAGE 28.9 PRIVATE OPERATOR PING"
        in dispatched_content
    )
    assert (
        "PHX2 STAGE 29.5.5 PRIVATE MIGRATION CONTEXT"
        not in dispatched_content
    )
    assert "[MIGRATION CONTEXT]" not in dispatched_content


# ---------------------------------------------------------------------------
# INT 6 — Modes 1 + 2: injector never invoked
# ---------------------------------------------------------------------------


class _ProhibitedInjector:
    """Injector whose ``wrap_transport`` would FAIL the test if
    invoked. Pinned to ensure modes 1 + 2 never call
    ``wrap_transport``.
    """

    def __init__(self) -> None:
        self.wrap_called: bool = False

    def wrap_transport(self, inner_transport: object) -> object:
        self.wrap_called = True
        raise AssertionError(
            "Stage 29.5.6 injector must not be invoked on "
            "modes 1 or 2"
        )


def test_mode_1_readiness_only_does_not_invoke_injector() -> None:
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    injector = _ProhibitedInjector()

    run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_READINESS_ONLY,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        write_artifacts=True,
        private_discord_body_injector=injector,
    )
    assert injector.wrap_called is False


def test_mode_2_connect_only_does_not_invoke_injector() -> None:
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    injector = _ProhibitedInjector()

    run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_CHAINSTACK_AND_BIRDEYE_CONNECT_ONLY,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        private_discord_body_injector=injector,
    )
    assert injector.wrap_called is False


# ---------------------------------------------------------------------------
# INT 7 — Side-channel + body injection independent and concurrent
# ---------------------------------------------------------------------------


def test_side_channel_and_body_injection_both_invoked() -> None:
    """When the operator wires BOTH a Stage 29.5.5 side-channel
    writer (``migration_context_renderer``) AND a Stage 29.5.6
    injector (``private_discord_body_injector``), the
    side-channel artifact is ALWAYS written exactly once per
    ceremony AND the dispatched body carries the migration
    context (full ``body_text`` when it fits, deterministic
    compact fallback otherwise). Both surfaces are independent:
    the side-channel write happens regardless of which append
    branch the body injector takes.
    """
    out = _outside_repo_tmpdir()
    configs = _build_test_runtime_configs()
    factory, _captured = _make_factory(
        responses=[_make_pumpswap_tx_update()],
    )
    birdeye = _FakeBirdeyeHttpTransport(
        bodies_by_path=_build_birdeye_bodies(),
    )
    fake_discord = _FakeAuditedDiscordTransport()
    recorder = _build_recorder()
    writer = Stage29_5_5SideChannelArtifactWriter()
    injector = Stage29_5_6PrivateDiscordBodyInjector(
        migration_source=recorder,
    )

    result = run_stage29_3_first_private_tradeable_smoke(
        mode=PROBE_MODE_ONE_REAL_PRIVATE_TRADEABLE_PING_DRY_RUN,
        runtime_configs=configs,
        private_webhook_url=_TEST_PRIVATE_WEBHOOK_URL,
        output_dir=out,
        live_env_ready=True,
        live_operator_request=True,
        known_mint=_TEST_BASE_MINT,
        birdeye_http_transport=birdeye,
        audited_discord_transport=fake_discord,  # type: ignore[arg-type]
        channel_factory=factory,
        max_messages_to_scan=8,
        write_artifacts=True,
        migration_source=recorder,
        migration_context_renderer=writer,
        private_discord_body_injector=injector,
    )

    # Side-channel artifact ALWAYS written when recorder + writer
    # are wired (regardless of body-injection cap behavior).
    artifact_path = (
        out / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
    )
    assert artifact_path.exists()
    bundle = json.loads(
        artifact_path.read_text(encoding="utf-8"),
    )
    assert bundle["entry_count"] >= 1

    # Dispatched-Discord count is exactly one regardless of the
    # body-injection branch taken.
    assert fake_discord.call_count == 1
    dispatched_content = (
        fake_discord.calls[0]["payload"]["content"]
    )

    # Cap-aware body-injection: realistic Stage 29.3 mode-3
    # emits the migration context (full or compact) and the
    # dispatched body stays within the 1900-char cap.
    assert len(dispatched_content) <= (
        STAGE29_5_6_CONTENT_MAX_CHARS
    )
    entries = recorder.recorded_entries
    assert len(entries) >= 1
    assert (
        "filter_enforcement_status: NOT_ACTIVE_STAGE_29_PENDING"
        in dispatched_content
    )
    assert "informational_only: true" in dispatched_content
    assert "not_a_trading_verdict: true" in dispatched_content

    assert (
        result.tradeable_smoke_outcome
        == TRADEABLE_SMOKE_OUTCOME_DISPATCHED
    )


# ---------------------------------------------------------------------------
# INT 8 — Source-level pin: Stage 29.3 imports zero stage29_5 modules
# ---------------------------------------------------------------------------


def test_stage_29_3_source_imports_zero_stage29_5_modules() -> None:
    """The Stage 29.3 narrow widening must continue to satisfy
    the Stage 29.3 import discipline: ZERO ``stage29_5*``
    modules imported at the Stage 29.3 production source.
    """
    phx2_root: Path = Path(__file__).resolve().parent.parent.parent
    stage29_3_source = (
        phx2_root / "stage29" / "stage29_3_tradeable_smoke.py"
    )
    source = stage29_3_source.read_text(encoding="utf-8")
    for forbidden in (
        "from PHX2.stage29.stage29_5_",
        "import PHX2.stage29.stage29_5_",
    ):
        assert forbidden not in source, (
            f"Stage 29.3 source must not contain "
            f"{forbidden!r}; offending source path "
            f"{stage29_3_source}"
        )


def test_stage_29_3_helper_has_wrap_transport_guard() -> None:
    """AST-level pin: the Stage 29.3 mode-3 helper carries the
    ``if private_discord_body_injector is not None`` guard with
    a ``try`` / ``except Exception: pass`` wrap call to
    ``wrap_transport(transport)``.
    """
    phx2_root: Path = Path(__file__).resolve().parent.parent.parent
    stage29_3_source = (
        phx2_root / "stage29" / "stage29_3_tradeable_smoke.py"
    )
    source = stage29_3_source.read_text(encoding="utf-8")
    assert (
        "if private_discord_body_injector is not None:" in source
    )
    assert ".wrap_transport(" in source
    # The Stage 29.5.6 wrap call must be inside a try/except.
    # We do a coarse substring check (full AST verification is
    # overkill for a single guard).
    pattern = re.compile(
        r"if\s+private_discord_body_injector\s+is\s+not\s+None:"
        r"\s+try:",
        re.MULTILINE,
    )
    assert pattern.search(source), (
        "Stage 29.3 must wrap the injector call in a try/except"
    )
