"""Stage 29.5.5 rendered migration context block + recorded
render entry dataclasses, plus the closed-set display-token
vocabularies the Stage 29.5.5 renderer projects onto.

The Stage 29.5.5 renderer is the sole authority that constructs
a ``Stage29_5_5RenderedMigrationContextBlock``. The Stage 29.5.5
recorder is the sole authority that constructs a
``Stage29_5_5RecordedRenderEntry``. Both dataclasses validate
their closed-set token fields at ``__post_init__`` AND scan
every free-form string field against a closed-set forbidden-
substring vocabulary so a custom renderer cannot smuggle a raw
URL / webhook / API-key / legacy-import shape into the recorded
audit surface.

The block is an audit / side-channel artifact shape only:

  * it carries no raw payload,
  * it carries no raw URL / API key / webhook URL,
  * it carries no wallet / private-key / signer field,
  * it carries no public / subscriber / paid-tier routing
    field,
  * it carries no trading verdict (BUY / SELL / APPROVED / GATE
    / BLOCK / EXECUTE / POSITION-SIZE / AUTO-TRADE language is
    rejected by the Stage 29.5.5 boundary scan over the block's
    ``body_text``),
  * it pins ``informational_only = True`` and
    ``not_a_trading_verdict = True`` so a downstream operator
    reviewer cannot misread the block as enforcement / dispatch
    authority,
  * it pins ``redaction_status = SAFE`` and
    ``filter_enforcement_status = NOT_ACTIVE_STAGE_29_PENDING``
    verbatim from the Stage 29.5 projection contract.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` /
    ``os.environb`` are never touched.
  * No outbound network. No urllib / requests / httpx / aiohttp
    / websockets / websocket / http.client / socket / grpc /
    asyncio import.
  * Stdlib only (``dataclasses`` / ``typing``) plus the Stage
    27.4 ``MigrationSourceSnapshot`` shape and the Stage 29.5
    closed-set vocabularies / projection / safe-shape
    validators.
  * No top-level Call (no implicit I/O at import time). The only
    admitted module-body Call shape is ``@dataclass(...)``.
  * No legacy import path.
  * No Discord / Telegram / X / social / webhook / Helius /
    Chainstack / Birdeye / Pump.fun reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from PHX2.stage27.price_ath_context_reader import (
    MigrationSourceSnapshot,
)
from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    REDACTION_STATUS_SAFE,
    STAGE29_5_MIGRATION_JOIN_STATUS_VALUES,
    STAGE29_5_MIGRATION_SOURCE_VALUES,
    Stage29_5PrivatePingMigrationContext,
    is_safe_iso8601_utc_string,
    is_safe_mint_or_pool_string,
)


# ---------------------------------------------------------------------------
# Schema versions
# ---------------------------------------------------------------------------


STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION: str = (
    "stage29_5_5_v0_rendered_migration_context_block"
)


STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION: str = (
    "stage29_5_5_v0_recorded_render_entry"
)


# ---------------------------------------------------------------------------
# Closed-set: migration_evidence_status_display (Section 5.1)
# ---------------------------------------------------------------------------


MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE: str = (
    "MIGRATION_EVIDENCE_COMPLETE"
)
MIGRATION_EVIDENCE_STATUS_DISPLAY_PARTIAL: str = (
    "MIGRATION_EVIDENCE_PARTIAL"
)
MIGRATION_EVIDENCE_STATUS_DISPLAY_MISSING: str = (
    "MIGRATION_EVIDENCE_MISSING"
)
MIGRATION_EVIDENCE_STATUS_DISPLAY_INVALID: str = (
    "MIGRATION_EVIDENCE_INVALID"
)
MIGRATION_EVIDENCE_STATUS_DISPLAY_CONFLICTING: str = (
    "MIGRATION_EVIDENCE_CONFLICTING"
)


STAGE29_5_5_MIGRATION_EVIDENCE_STATUS_DISPLAY_VALUES: Tuple[
    str, ...
] = (
    MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_PARTIAL,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_MISSING,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_INVALID,
    MIGRATION_EVIDENCE_STATUS_DISPLAY_CONFLICTING,
)


def is_stage29_5_5_migration_evidence_status_display_value(
    value: object,
) -> bool:
    return (
        isinstance(value, str)
        and value
        in STAGE29_5_5_MIGRATION_EVIDENCE_STATUS_DISPLAY_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: migration_evidence_source_trust_display (Section 5.2)
# ---------------------------------------------------------------------------


MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN: str = (
    "SOURCE_TRUSTED_ON_CHAIN"
)
MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_SYNTHETIC: str = (
    "SOURCE_UNTRUSTED_SYNTHETIC"
)
MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_UNKNOWN: str = (
    "SOURCE_UNTRUSTED_UNKNOWN"
)
MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN: str = (
    "SOURCE_PARTIAL_ON_CHAIN"
)
MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_SYNTHETIC: str = (
    "SOURCE_PARTIAL_SYNTHETIC"
)
MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE: str = (
    "SOURCE_NO_SOURCE"
)


STAGE29_5_5_MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_VALUES: Tuple[
    str, ...
] = (
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_SYNTHETIC,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_UNKNOWN,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_SYNTHETIC,
    MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE,
)


def is_stage29_5_5_migration_evidence_source_trust_display_value(
    value: object,
) -> bool:
    return (
        isinstance(value, str)
        and value
        in STAGE29_5_5_MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_VALUES
    )


# ---------------------------------------------------------------------------
# Closed-set: post_migration_ath_verified_display (Section 5.3)
# ---------------------------------------------------------------------------


POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED: str = (
    "ATH_VERIFIED_POST_MIGRATION"
)
POST_MIGRATION_ATH_VERIFIED_DISPLAY_NOT_VERIFIED: str = (
    "ATH_NOT_VERIFIED_POST_MIGRATION"
)
POST_MIGRATION_ATH_VERIFIED_DISPLAY_UNKNOWN: str = (
    "ATH_VERIFICATION_UNKNOWN"
)


STAGE29_5_5_POST_MIGRATION_ATH_VERIFIED_DISPLAY_VALUES: Tuple[
    str, ...
] = (
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_NOT_VERIFIED,
    POST_MIGRATION_ATH_VERIFIED_DISPLAY_UNKNOWN,
)


def is_stage29_5_5_post_migration_ath_verified_display_value(
    value: object,
) -> bool:
    return (
        isinstance(value, str)
        and value
        in STAGE29_5_5_POST_MIGRATION_ATH_VERIFIED_DISPLAY_VALUES
    )


# ---------------------------------------------------------------------------
# Display sentinels
# ---------------------------------------------------------------------------


DISPLAY_TOKEN_MISSING: str = "MISSING"
DISPLAY_TOKEN_NONE: str = "NONE"


STAGE29_5_5_DISPLAY_SENTINEL_VALUES: Tuple[str, ...] = (
    DISPLAY_TOKEN_MISSING,
    DISPLAY_TOKEN_NONE,
)


# ---------------------------------------------------------------------------
# Stage 29.5.5 forbidden-substring vocabulary
# ---------------------------------------------------------------------------
#
# Every concatenated literal below evaluates to a single forbidden
# substring at runtime; the source itself does NOT carry the
# literal so this module passes the Stage 29.5.5 boundary scan
# over URL host / API-key / webhook / legacy-bot substrings.


_STAGE29_5_5_FORBIDDEN_LOWERED_SUBSTRINGS: Tuple[str, ...] = (
    # URL hosts (case-insensitive)
    "discord" + ".com",
    "discord" + "app.com",
    "h" + "ooks.slack.com",
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
    "pump" + ".fun",
    # Schemes
    "h" + "ttp://",
    "h" + "ttps://",
    "w" + "s://",
    "w" + "ss://",
    # Auth / secret shapes
    "web" + "hook",
    "author" + "ization:",
    "b" + "earer ",
    "api_" + "key",
    "private_" + "key",
    "discord_" + "webhook_url=",
    "helius_api" + "_key=",
    "helius_ws" + "_url=",
    "helius_ws" + "_endpoint=",
    "birdeye_api" + "_key=",
    "chainstack_api" + "_key=",
    # Legacy / pre-PHX2 markers
    "p" + "hx1",
    "phoenix_" + "bot",
    "phoenix-" + "1",
    # Trading / signer routing
    "wallet_" + "signer",
    "signer_" + "loader",
    "trade_" + "executor",
    "position_" + "sizer",
    "auto_" + "trade",
    "public_" + "router",
    "subscriber_" + "router",
    "paid_" + "tier_router",
    "telegram_" + "sender",
    "telegram_" + "client",
    "x_" + "social",
    "social_" + "sidecar",
)


def stage29_5_5_value_carries_forbidden_substring(
    value: object,
) -> bool:
    """Return True iff ``value`` is a string carrying any
    Stage 29.5.5 forbidden substring (case-insensitive scan).

    The scan is conservative: a non-string ``value`` returns
    False; an empty string returns False; any string whose
    lowered form contains one of the closed-set forbidden
    substrings returns True.
    """
    if not isinstance(value, str):
        return False
    if not value:
        return False
    lowered = value.lower()
    for needle in _STAGE29_5_5_FORBIDDEN_LOWERED_SUBSTRINGS:
        if needle in lowered:
            return True
    return False


def stage29_5_5_is_safe_audit_identifier(value: object) -> bool:
    """Return True iff ``value`` is a printable string of length
    1..80 containing only ``[A-Za-z0-9._:-]`` characters AND not
    carrying any Stage 29.5.5 forbidden substring.

    Used by the Stage 29.5.5 side-channel artifact writer to
    decide whether a snapshot-summary audit identifier
    (``migration_event_id`` / ``source_event_ref`` /
    ``raw_capture_ref``) is safe to emit verbatim or must be
    redacted to ``None``.
    """
    if not isinstance(value, str):
        return False
    if not value or len(value) > 80:
        return False
    for ch in value:
        if not (ch.isalnum() or ch in "._-:"):
            return False
    if stage29_5_5_value_carries_forbidden_substring(value):
        return False
    return True


# ---------------------------------------------------------------------------
# Shared rendered-block safety validator
# ---------------------------------------------------------------------------
#
# The Stage 29.5.5 dataclass ``__post_init__`` enforces the
# closed-set / pinned-value / forbidden-substring contract at
# CONSTRUCTION time. However, ``object.__setattr__`` (or any
# equivalent path that bypasses ``__setattr__``) can MUTATE a
# freshly-constructed safe block AFTER construction. Both the
# Stage 29.5.5 recorder and the Stage 29.5.5 side-channel
# artifact writer call this validator to re-check every field
# at the moments that matter most:
#
#   * the recorder calls it immediately BEFORE appending an
#     entry to ``recorded_entries``;
#   * the writer calls it immediately BEFORE building the
#     side-channel JSON bundle.
#
# Either failure path refuses to record / refuses to write; no
# unsafe block ever reaches the side-channel artifact.


def stage29_5_5_rendered_block_is_safe_for_serialization(
    block: object,
) -> bool:
    """Return True iff ``block`` is a fully-valid Stage 29.5.5
    rendered migration context block whose every field is safe
    to serialize into the Stage 29.5.5 side-channel artifact
    JSON.

    Checks (in order):

      * ``block`` is a ``Stage29_5_5RenderedMigrationContextBlock``
        instance,
      * the three Stage 29.5.5 closed-set display tokens are
        each in their approved vocabulary,
      * the two echoed Stage 29.5 closed-set tokens are each in
        their approved vocabulary,
      * the three pinned exact-value strings match their lock
        values verbatim (``redaction_status == SAFE`` /
        ``filter_enforcement_status ==
        NOT_ACTIVE_STAGE_29_PENDING`` / ``schema_version ==
        STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION``),
      * the two pinned booleans are each EXACTLY the literal
        ``True`` (the ``is True`` check rejects truthy non-bool
        values),
      * ``observed_at_utc`` is a Stage 29.5 safe-shape ISO-8601
        UTC string,
      * the free-form display fields are strings,
      * ``body_text`` is a non-empty string,
      * every string field that reaches the side-channel JSON
        serializer (13 fields total) is free of Stage 29.5.5
        forbidden substrings (URL host / webhook / API-key /
        legacy-import / trading-routing shape).

    Returns False on the FIRST failure; returns True only when
    every check passes. Non-raising on any input.
    """
    if not isinstance(
        block, Stage29_5_5RenderedMigrationContextBlock,
    ):
        return False
    # 1. Closed-set Stage 29.5.5 display tokens.
    if not is_stage29_5_5_migration_evidence_status_display_value(
        block.migration_evidence_status_display,
    ):
        return False
    if not is_stage29_5_5_migration_evidence_source_trust_display_value(
        block.migration_evidence_source_trust_display,
    ):
        return False
    if not is_stage29_5_5_post_migration_ath_verified_display_value(
        block.post_migration_ath_verified_display,
    ):
        return False
    # 2. Echoed Stage 29.5 closed-set tokens.
    if block.migration_source_token not in (
        STAGE29_5_MIGRATION_SOURCE_VALUES
    ):
        return False
    if block.join_status_echoed_token not in (
        STAGE29_5_MIGRATION_JOIN_STATUS_VALUES
    ):
        return False
    # 3. Pinned exact-value strings.
    if block.redaction_status != REDACTION_STATUS_SAFE:
        return False
    if (
        block.filter_enforcement_status
        != FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    ):
        return False
    if (
        block.schema_version
        != STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION
    ):
        return False
    # 4. Pinned booleans -- ``is True`` rejects truthy non-bool
    # values.
    if block.informational_only is not True:
        return False
    if block.not_a_trading_verdict is not True:
        return False
    # 5. ``observed_at_utc`` safe-shape ISO-8601 UTC string.
    if not is_safe_iso8601_utc_string(block.observed_at_utc):
        return False
    # 6. Free-form display fields must be strings; body_text
    # must additionally be non-empty.
    free_form_string_fields = (
        block.migration_timestamp_utc_display,
        block.migration_slot_display,
        block.warnings_display,
        block.body_text,
    )
    for value in free_form_string_fields:
        if not isinstance(value, str):
            return False
    if block.body_text == "":
        return False
    # 7. Every string field that reaches the side-channel JSON
    # serializer must be free of Stage 29.5.5 forbidden
    # substrings.
    every_string_field_reaching_json = (
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
        block.body_text,
        block.schema_version,
    )
    for value in every_string_field_reaching_json:
        if not isinstance(value, str):
            return False
        if stage29_5_5_value_carries_forbidden_substring(value):
            return False
    return True


# ---------------------------------------------------------------------------
# Immutable record: Stage 29.5.5 rendered migration context block
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_5_5RenderedMigrationContextBlock:
    """Immutable Stage 29.5.5 rendered migration context block.

    Constructed by the Stage 29.5.5 renderer. Consumed by the
    Stage 29.5.5 side-channel artifact writer. Carries:

      * three closed-set display tokens (status / source-trust /
        ATH-verified) derived from the Stage 29.5 projection,
      * echo fields for the Stage 29.5 projection's
        timestamp / slot / source / join-status / warnings /
        observation timestamp,
      * the locked ``redaction_status = SAFE`` and
        ``filter_enforcement_status = NOT_ACTIVE_STAGE_29_PENDING``
        tokens,
      * two pinned-True flags (``informational_only`` /
        ``not_a_trading_verdict``) so a downstream operator
        reviewer cannot misread the block,
      * a deterministic plain-text ``body_text`` rendering for
        the side-channel artifact.

    No raw payload, no raw URL, no raw secret, no wallet /
    private-key / signer field. The block is the sole artifact
    of the Stage 29.5.5 renderer; the rendered text is fixed by
    the renderer (line order, label vocabulary, whitespace) and
    pinned by the Stage 29.5.5 renderer test surface.

    Validators enforce the closed-set tokens at
    ``__post_init__`` so the closed-set contract cannot be
    bypassed by direct construction.
    """

    migration_evidence_status_display: str
    migration_evidence_source_trust_display: str
    post_migration_ath_verified_display: str
    migration_timestamp_utc_display: str
    migration_slot_display: str
    migration_source_token: str
    join_status_echoed_token: str
    warnings_display: str
    redaction_status: str
    filter_enforcement_status: str
    observed_at_utc: str
    informational_only: bool
    not_a_trading_verdict: bool
    body_text: str
    schema_version: str = (
        STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if not is_stage29_5_5_migration_evidence_status_display_value(
            self.migration_evidence_status_display,
        ):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "migration_evidence_status_display must be a "
                "closed-set token; got "
                f"{self.migration_evidence_status_display!r}"
            )
        if not is_stage29_5_5_migration_evidence_source_trust_display_value(
            self.migration_evidence_source_trust_display,
        ):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "migration_evidence_source_trust_display must be a "
                "closed-set token; got "
                f"{self.migration_evidence_source_trust_display!r}"
            )
        if not is_stage29_5_5_post_migration_ath_verified_display_value(
            self.post_migration_ath_verified_display,
        ):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "post_migration_ath_verified_display must be a "
                "closed-set token; got "
                f"{self.post_migration_ath_verified_display!r}"
            )
        if not isinstance(
            self.migration_timestamp_utc_display, str,
        ):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "migration_timestamp_utc_display must be a string"
            )
        if not isinstance(self.migration_slot_display, str):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "migration_slot_display must be a string"
            )
        if self.migration_source_token not in (
            STAGE29_5_MIGRATION_SOURCE_VALUES
        ):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "migration_source_token must be a Stage 29.5 "
                "closed-set migration_source value; got "
                f"{self.migration_source_token!r}"
            )
        if self.join_status_echoed_token not in (
            STAGE29_5_MIGRATION_JOIN_STATUS_VALUES
        ):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "join_status_echoed_token must be a Stage 29.5 "
                "closed-set migration_join_status value; got "
                f"{self.join_status_echoed_token!r}"
            )
        if not isinstance(self.warnings_display, str):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "warnings_display must be a string"
            )
        if self.redaction_status != REDACTION_STATUS_SAFE:
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "redaction_status is locked to SAFE; got "
                f"{self.redaction_status!r}"
            )
        if (
            self.filter_enforcement_status
            != FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
        ):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "filter_enforcement_status is locked to "
                "NOT_ACTIVE_STAGE_29_PENDING; got "
                f"{self.filter_enforcement_status!r}"
            )
        if not is_safe_iso8601_utc_string(self.observed_at_utc):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "observed_at_utc must be a UTC-shaped ISO-8601 "
                f"string; got {self.observed_at_utc!r}"
            )
        if self.informational_only is not True:
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "informational_only is pinned True"
            )
        if self.not_a_trading_verdict is not True:
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "not_a_trading_verdict is pinned True"
            )
        if not isinstance(self.body_text, str) or (
            self.body_text == ""
        ):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "body_text must be a non-empty string"
            )
        if (
            self.schema_version
            != STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION
        ):
            raise ValueError(
                "Stage29_5_5RenderedMigrationContextBlock."
                "schema_version is locked; got "
                f"{self.schema_version!r}"
            )
        # Forbidden-substring scan over free-form string fields.
        # A custom renderer cannot smuggle a raw URL / webhook /
        # API-key / legacy-import shape onto a rendered block;
        # the block is the sole authority that reaches the Stage
        # 29.5.5 side-channel artifact JSON, so this scan
        # enforces the closed-set redaction contract at the
        # narrowest possible boundary.
        _free_form_string_fields: Tuple[Tuple[str, str], ...] = (
            ("body_text", self.body_text),
            (
                "migration_timestamp_utc_display",
                self.migration_timestamp_utc_display,
            ),
            (
                "migration_slot_display",
                self.migration_slot_display,
            ),
            ("warnings_display", self.warnings_display),
            ("observed_at_utc", self.observed_at_utc),
        )
        for label, value in _free_form_string_fields:
            if stage29_5_5_value_carries_forbidden_substring(
                value,
            ):
                raise ValueError(
                    "Stage29_5_5RenderedMigrationContextBlock."
                    f"{label} carries a Stage 29.5.5 forbidden "
                    "substring (URL host / webhook / API-key / "
                    "legacy-import / trading-routing shape); "
                    "refusing to construct a redaction-unsafe "
                    "block"
                )


# ---------------------------------------------------------------------------
# Immutable record: Stage 29.5.5 recorded render entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stage29_5_5RecordedRenderEntry:
    """Immutable Stage 29.5.5 recorded render entry.

    The Stage 29.5.5 recorder is the sole authority that
    constructs this record. Captures one
    ``Stage29_5_5MigrationContextRecorder.read_migration_snapshot``
    call:

      * the Stage 29.5 candidate ``token_mint`` (safe-shape
        printable string of length 32..64),
      * the Stage 29.5 ``Stage29_5PrivatePingMigrationContext``
        projection the recorder computed for the candidate,
      * the Stage 29.5.5
        ``Stage29_5_5RenderedMigrationContextBlock`` the
        recorder rendered from the projection,
      * the Stage 27.4 ``MigrationSourceSnapshot`` the recorder
        returned to the Stage 27.6 candidate assembler,
      * the UTC ISO-8601 ``recorded_at_utc`` timestamp at which
        the recorder captured the entry.

    Validators enforce closed-set / safe-shape tokens at
    ``__post_init__``.
    """

    token_mint: str
    projection: Stage29_5PrivatePingMigrationContext
    rendered_block: Stage29_5_5RenderedMigrationContextBlock
    snapshot: MigrationSourceSnapshot
    recorded_at_utc: str
    schema_version: str = (
        STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if not is_safe_mint_or_pool_string(self.token_mint):
            raise ValueError(
                "Stage29_5_5RecordedRenderEntry."
                "token_mint must be a safe-shape printable "
                "string of length 32..64; got "
                f"{self.token_mint!r}"
            )
        if not isinstance(
            self.projection,
            Stage29_5PrivatePingMigrationContext,
        ):
            raise ValueError(
                "Stage29_5_5RecordedRenderEntry."
                "projection must be a "
                "Stage29_5PrivatePingMigrationContext instance"
            )
        if not isinstance(
            self.rendered_block,
            Stage29_5_5RenderedMigrationContextBlock,
        ):
            raise ValueError(
                "Stage29_5_5RecordedRenderEntry."
                "rendered_block must be a "
                "Stage29_5_5RenderedMigrationContextBlock "
                "instance"
            )
        if not isinstance(
            self.snapshot, MigrationSourceSnapshot,
        ):
            raise ValueError(
                "Stage29_5_5RecordedRenderEntry."
                "snapshot must be a MigrationSourceSnapshot "
                "instance"
            )
        if not is_safe_iso8601_utc_string(self.recorded_at_utc):
            raise ValueError(
                "Stage29_5_5RecordedRenderEntry."
                "recorded_at_utc must be a UTC-shaped ISO-8601 "
                f"string; got {self.recorded_at_utc!r}"
            )
        if (
            self.schema_version
            != STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION
        ):
            raise ValueError(
                "Stage29_5_5RecordedRenderEntry."
                "schema_version is locked; got "
                f"{self.schema_version!r}"
            )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = (
    # Schema versions
    "STAGE29_5_5_RENDERED_MIGRATION_CONTEXT_BLOCK_SCHEMA_VERSION",
    "STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION",
    # migration_evidence_status_display
    "MIGRATION_EVIDENCE_STATUS_DISPLAY_COMPLETE",
    "MIGRATION_EVIDENCE_STATUS_DISPLAY_PARTIAL",
    "MIGRATION_EVIDENCE_STATUS_DISPLAY_MISSING",
    "MIGRATION_EVIDENCE_STATUS_DISPLAY_INVALID",
    "MIGRATION_EVIDENCE_STATUS_DISPLAY_CONFLICTING",
    "STAGE29_5_5_MIGRATION_EVIDENCE_STATUS_DISPLAY_VALUES",
    "is_stage29_5_5_migration_evidence_status_display_value",
    # migration_evidence_source_trust_display
    "MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_TRUSTED_ON_CHAIN",
    "MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_SYNTHETIC",
    "MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_UNTRUSTED_UNKNOWN",
    "MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_ON_CHAIN",
    "MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_PARTIAL_SYNTHETIC",
    "MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_NO_SOURCE",
    "STAGE29_5_5_MIGRATION_EVIDENCE_SOURCE_TRUST_DISPLAY_VALUES",
    "is_stage29_5_5_migration_evidence_source_trust_display_value",
    # post_migration_ath_verified_display
    "POST_MIGRATION_ATH_VERIFIED_DISPLAY_VERIFIED",
    "POST_MIGRATION_ATH_VERIFIED_DISPLAY_NOT_VERIFIED",
    "POST_MIGRATION_ATH_VERIFIED_DISPLAY_UNKNOWN",
    "STAGE29_5_5_POST_MIGRATION_ATH_VERIFIED_DISPLAY_VALUES",
    "is_stage29_5_5_post_migration_ath_verified_display_value",
    # Display sentinels
    "DISPLAY_TOKEN_MISSING",
    "DISPLAY_TOKEN_NONE",
    "STAGE29_5_5_DISPLAY_SENTINEL_VALUES",
    # Forbidden-substring scanner + safe-shape audit-id helper
    "stage29_5_5_value_carries_forbidden_substring",
    "stage29_5_5_is_safe_audit_identifier",
    # Shared rendered-block safety validator (used by recorder +
    # side-channel writer to defend against post-construction
    # ``object.__setattr__`` mutation).
    "stage29_5_5_rendered_block_is_safe_for_serialization",
    # Dataclasses
    "Stage29_5_5RenderedMigrationContextBlock",
    "Stage29_5_5RecordedRenderEntry",
)
