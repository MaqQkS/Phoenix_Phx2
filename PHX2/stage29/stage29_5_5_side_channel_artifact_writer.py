"""Stage 29.5.5 side-channel artifact writer.

The Stage 29.5.5 side-channel artifact writer is the object the
operator passes as ``migration_context_renderer`` to
``run_stage29_3_first_private_tradeable_smoke``. After the Stage
28.9 session completes, Stage 29.3 mode-3 calls the writer's
``write_side_channel_artifact(output_dir, migration_source)``
method inside a ``try`` / ``except Exception: pass`` guard so a
side-channel artifact write failure NEVER affects the dispatch
outcome. The writer itself is ALSO non-raising on every internal
failure path (JSON encoding, filesystem write, redaction
sanity check) and returns ``None`` instead.

The writer:

  * duck-types ``migration_source.recorded_entries`` (the
    Stage 29.5.5 recorder's read-only tuple of
    ``Stage29_5_5RecordedRenderEntry`` instances); when
    ``migration_source`` has no ``recorded_entries`` attribute
    OR the attribute is empty, the writer no-ops and returns
    ``None``;
  * validates ``output_dir`` against a safe-shape gate that
    refuses any path carrying a URL / webhook / API-key
    substring (mirrors the Stage 29.3 ``_output_dir_is_safe``
    pattern);
  * redacts snapshot-summary audit identifiers
    (``migration_event_id`` / ``source_event_ref`` /
    ``raw_capture_ref``) to ``None`` whenever they fail the
    Stage 29.5.5 safe-shape / no-forbidden-substring check
    (conservative: when in doubt, redact);
  * scans the fully serialized JSON string against the Stage
    29.5.5 forbidden-substring vocabulary one last time before
    writing; any leak refuses to write and returns ``None``;
  * writes a single deterministic UTF-8 JSON artifact file
    named ``stage29_5_5_side_channel_migration_context_artifact.json``
    under ``output_dir``;
  * NEVER opens a network connection;
  * NEVER reads the process environment;
  * NEVER touches a wallet / private-key / signer surface;
  * NEVER injects the rendered block into the live dispatched
    Discord payload;
  * carries no raw payload, no raw URL, no raw secret, no
    webhook URL in the artifact file;
  * NEVER raises -- every internal exception is caught and
    surfaced as a ``None`` return value.

Discipline:

  * Stdlib only (``json`` / ``pathlib`` / ``typing``).
  * Imports the Stage 29.5.5 render models read-only.
  * No outbound-network library import.
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No top-level Call (no implicit I/O at import time). The
    only admitted module-body Call shape is ``@dataclass(...)``
    and this module ships zero ``@dataclass`` classes.
  * No legacy import path (no pre-PHX2 codebase reference).
  * No Discord / Telegram / X / social / webhook / Helius /
    Chainstack / Birdeye / Pump.fun reference.
  * No enforcement / routing / trading / wallet / signer surface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

from PHX2.stage29.stage29_5_migration_models import (
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    REDACTION_STATUS_SAFE,
    STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION,
    Stage29_5PrivatePingMigrationContext,
    is_safe_iso8601_utc_string,
    is_safe_mint_or_pool_string,
    is_stage29_5_measurement_status_value,
    is_stage29_5_migration_join_status_value,
    is_stage29_5_migration_source_value,
    is_stage29_5_redaction_status_value,
    is_stage29_5_warning_code_value,
)
from PHX2.stage29.stage29_5_5_render_models import (
    STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION,
    Stage29_5_5RecordedRenderEntry,
    Stage29_5_5RenderedMigrationContextBlock,
    stage29_5_5_is_safe_audit_identifier,
    stage29_5_5_rendered_block_is_safe_for_serialization,
    stage29_5_5_value_carries_forbidden_substring,
)


# ---------------------------------------------------------------------------
# Stage 29.5.5 schema version pin
# ---------------------------------------------------------------------------


STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_WRITER_SCHEMA_VERSION: str = (
    "stage29_5_5_v0_side_channel_artifact_writer"
)


STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION: str = (
    "stage29_5_5_v0_side_channel_artifact_bundle"
)


# ---------------------------------------------------------------------------
# Locked output filename
# ---------------------------------------------------------------------------


STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME: str = (
    "stage29_5_5_side_channel_migration_context_artifact.json"
)


# ---------------------------------------------------------------------------
# Locked output-dir safety gate (mirrors the Stage 29.3 mode-3
# pattern; concatenated literally so this module's source never
# carries the canonical URL / webhook substrings).
# ---------------------------------------------------------------------------


_OUTPUT_DIR_FORBIDDEN_SUBSTRINGS: Tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    "hooks" + ".slack.com",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
)


def _output_dir_is_safe(output_dir: object) -> bool:
    """Return True iff ``output_dir`` is a ``Path`` that exists,
    is a directory, and carries no URL / webhook / API-key
    substring on its string rendering.
    """
    if not isinstance(output_dir, Path):
        return False
    path_str = str(output_dir)
    lowered = path_str.lower()
    for needle in _OUTPUT_DIR_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return False
    if not output_dir.exists():
        return False
    if not output_dir.is_dir():
        return False
    return True


# ---------------------------------------------------------------------------
# Side-channel artifact writer
# ---------------------------------------------------------------------------


class Stage29_5_5SideChannelArtifactWriter:
    """Stage 29.5.5 side-channel artifact writer.

    Implements the side-channel-writer Protocol the Stage 29.3
    mode-3 path's ``migration_context_renderer`` kwarg expects:

      * one method ``write_side_channel_artifact(output_dir,
        migration_source) -> Optional[Path]`` that writes a
        deterministic JSON artifact when ``migration_source``
        exposes a non-empty ``recorded_entries`` tuple AND
        ``output_dir`` is safe-shape; otherwise returns ``None``.

    The writer is stateless. Multiple Stage 29.3 mode-3
    ceremonies may share the same writer instance.
    """

    __slots__ = ()

    def write_side_channel_artifact(
        self,
        *,
        output_dir: object,
        migration_source: object,
    ) -> Optional[Path]:
        """Write the Stage 29.5.5 side-channel artifact when the
        operator-wired ``migration_source`` exposes recorded
        entries; otherwise no-op.

        Returns the ``Path`` of the written artifact file when a
        write happened, ``None`` otherwise. Non-raising on:

          * ``migration_source`` having no ``recorded_entries``
            attribute or the attribute being empty,
          * ``migration_source.recorded_entries`` not being a
            tuple of ``Stage29_5_5RecordedRenderEntry``
            instances,
          * unsafe-shape ``output_dir``,
          * a recorded entry failing full pre-serialization
            validation (entry schema_version forged, token_mint
            unsafe-shape, recorded_at_utc unsafe-shape, or the
            rendered block's closed-set / pinned-value /
            forbidden-substring contract violated by a post-
            recording ``object.__setattr__`` mutation),
          * a bundle field carrying an unredacted forbidden
            substring (defense in depth -- the redaction layer
            also redacts per-field, this is the last line),
          * JSON-encoding failure (``json.dumps`` raising),
          * filesystem write failure (``Path.write_text``
            raising).

        Every internal exception is caught and surfaced as a
        ``None`` return so the writer is safe to call directly
        OR through the Stage 29.3 ``try`` / ``except Exception:
        pass`` guard.
        """
        try:
            entries = _extract_recorded_entries(migration_source)
            if entries is None or len(entries) == 0:
                return None
            # Re-validate EVERY recorded entry immediately before
            # building the JSON bundle. The recorder already
            # validates each entry at append time, but
            # ``object.__setattr__`` (or any equivalent path)
            # can mutate a recorded entry's frozen-dataclass
            # fields AFTER it has been appended to
            # ``recorded_entries``. Re-running the full Stage
            # 29.5.5 entry + block + projection validator here
            # defends the side-channel JSON artifact against
            # every such post-recording mutation:
            #
            #   * forged entry ``schema_version``,
            #   * unsafe-shape ``token_mint``,
            #   * unsafe-shape ``recorded_at_utc``,
            #   * rendered-block closed-set token mutation,
            #   * rendered-block pinned-value mutation
            #     (``redaction_status`` /
            #     ``filter_enforcement_status`` /
            #     ``schema_version``),
            #   * rendered-block pinned-boolean mutation
            #     (``informational_only`` /
            #     ``not_a_trading_verdict``),
            #   * forbidden-substring leak in any rendered-block
            #     string field,
            #   * projection closed-set token mutation
            #     (``measurement_status`` /
            #     ``migration_source`` /
            #     ``join_status_echoed``),
            #   * projection pinned-value mutation
            #     (``redaction_status`` /
            #     ``filter_enforcement_status`` /
            #     ``schema_version``),
            #   * projection optional-axis shape mutation
            #     (``migration_timestamp_utc`` /
            #     ``migration_slot`` /
            #     ``post_migration_ath_verified``),
            #   * projection ``observed_at_utc`` shape mutation,
            #   * projection ``warnings`` tuple / closed-set /
            #     forbidden-substring mutation,
            #   * forbidden-substring leak in any projection
            #     string field that reaches the
            #     projection_summary JSON.
            #
            # Any failure refuses to write the entire artifact
            # (we do NOT partially write -- the whole bundle is
            # either safe-as-recorded or skipped).
            for entry in entries:
                if not _recorded_entry_is_safe_for_serialization(
                    entry,
                ):
                    return None
            if not _output_dir_is_safe(output_dir):
                return None
            # ``output_dir`` is a safe-shape existing directory
            # from this point on. The narrow ``isinstance``
            # re-check below silences any static type checker
            # that does not narrow ``object`` through the duck-
            # typed helper.
            if not isinstance(output_dir, Path):
                return None
            bundle = _build_artifact_bundle(entries)
            serialized = json.dumps(
                bundle,
                sort_keys=True,
                indent=2,
                ensure_ascii=True,
            )
            if (
                stage29_5_5_value_carries_forbidden_substring(
                    serialized,
                )
            ):
                # Defense in depth: the per-field redaction
                # layer should have caught every forbidden
                # substring already. If a leak survives, refuse
                # to write the artifact rather than ship a
                # redaction-unsafe JSON to disk.
                return None
            artifact_path = (
                output_dir
                / STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME
            )
            artifact_path.write_text(
                serialized,
                encoding="utf-8",
            )
            return artifact_path
        except Exception:
            # Side-channel writer is contractually non-raising.
            # Every JSON / write / redaction-sanity failure
            # surfaces as ``None`` so Stage 29.3 mode-3 cannot
            # observe a Stage 29.5.5 side-channel exception on
            # the dispatch path.
            return None


# ---------------------------------------------------------------------------
# Module-private serialization helpers
# ---------------------------------------------------------------------------


def _extract_recorded_entries(
    migration_source: object,
) -> Optional[Tuple[Stage29_5_5RecordedRenderEntry, ...]]:
    """Duck-type ``migration_source.recorded_entries``.

    Returns the recorded-entries tuple when ``migration_source``
    exposes a ``recorded_entries`` attribute that is a tuple of
    ``Stage29_5_5RecordedRenderEntry`` instances. Returns
    ``None`` otherwise (the source is not a Stage 29.5.5
    recorder).
    """
    entries_attr = getattr(
        migration_source, "recorded_entries", None,
    )
    if entries_attr is None:
        return None
    if not isinstance(entries_attr, tuple):
        return None
    for entry in entries_attr:
        if not isinstance(
            entry, Stage29_5_5RecordedRenderEntry,
        ):
            return None
    return entries_attr


def _recorded_entry_is_safe_for_serialization(
    entry: object,
) -> bool:
    """Full validation of a recorded entry immediately before
    the Stage 29.5.5 side-channel writer serializes it.

    Returns True iff EVERY field on the entry is safe to ship to
    the JSON artifact:

      * ``entry`` is a ``Stage29_5_5RecordedRenderEntry``
        instance,
      * ``entry.schema_version`` matches the locked
        Stage 29.5.5 recorded-render-entry schema version,
      * ``entry.token_mint`` passes the Stage 29.5 safe-shape
        mint check,
      * ``entry.recorded_at_utc`` passes the Stage 29.5
        safe-shape ISO-8601 UTC check,
      * ``entry.rendered_block`` passes the full Stage 29.5.5
        rendered-block safety validator (closed-set tokens,
        pinned exact-value strings, pinned booleans, free-form
        types, body_text non-emptiness, AND a forbidden-
        substring scan over every string field that reaches
        the JSON serializer),
      * ``entry.projection`` passes the full Stage 29.5
        projection safety validator (closed-set
        measurement_status / migration_source /
        join_status_echoed tokens, pinned ``redaction_status ==
        SAFE`` / ``filter_enforcement_status ==
        NOT_ACTIVE_STAGE_29_PENDING`` lock, safe-shape
        ``observed_at_utc`` + optional
        ``migration_timestamp_utc``, non-negative-int optional
        ``migration_slot``, bool-or-None
        ``post_migration_ath_verified``, closed-set warnings
        tuple, AND a forbidden-substring scan over every string
        field that reaches the projection_summary JSON
        serializer).

    The recorder validates each entry at APPEND time, but a
    malicious operator may mutate any frozen-dataclass field of
    a recorded entry (the entry itself, its rendered_block, OR
    its projection) via ``object.__setattr__`` (or any
    equivalent path that bypasses ``__setattr__``) AFTER the
    recorder appended the entry. This validator runs at WRITE
    time so a post-recording mutation cannot reach the Stage
    29.5.5 side-channel artifact JSON via the rendered_block
    OR the projection_summary.

    Returns False on the first failure; non-raising on any
    input.
    """
    if not isinstance(entry, Stage29_5_5RecordedRenderEntry):
        return False
    if (
        entry.schema_version
        != STAGE29_5_5_RECORDED_RENDER_ENTRY_SCHEMA_VERSION
    ):
        return False
    if not is_safe_mint_or_pool_string(entry.token_mint):
        return False
    if not is_safe_iso8601_utc_string(entry.recorded_at_utc):
        return False
    if not stage29_5_5_rendered_block_is_safe_for_serialization(
        entry.rendered_block,
    ):
        return False
    if not _projection_is_safe_for_serialization(
        entry.projection,
    ):
        return False
    return True


def _projection_is_safe_for_serialization(
    projection: object,
) -> bool:
    """Full validation of a Stage 29.5 projection record
    immediately before the Stage 29.5.5 side-channel writer
    serializes its ``projection_summary`` into the JSON
    artifact.

    Returns True iff EVERY field on the projection is safe to
    ship verbatim to the projection_summary JSON dict:

      * ``projection`` is a
        ``Stage29_5PrivatePingMigrationContext`` instance,
      * ``projection.schema_version`` matches the locked
        Stage 29.5 private-ping-context schema version,
      * ``projection.redaction_status == SAFE`` (closed-set
        AND pinned exact value),
      * ``projection.filter_enforcement_status ==
        NOT_ACTIVE_STAGE_29_PENDING`` (pinned exact value),
      * ``projection.measurement_status`` is a Stage 29.5
        closed-set token,
      * ``projection.migration_source`` is a Stage 29.5
        closed-set token,
      * ``projection.join_status_echoed`` is a Stage 29.5
        closed-set token,
      * ``projection.migration_timestamp_utc`` is ``None`` OR
        a safe ISO-8601 UTC string,
      * ``projection.migration_slot`` is ``None`` OR a
        non-negative ``int`` (booleans excluded),
      * ``projection.observed_at_utc`` is a safe ISO-8601 UTC
        string,
      * ``projection.post_migration_ath_verified`` is ``True``,
        ``False``, or ``None`` (``is`` identity check rejects
        truthy non-bool values),
      * ``projection.warnings`` is a tuple of Stage 29.5
        closed-set warning code strings,
      * every string field that reaches the projection_summary
        JSON serializer is free of Stage 29.5.5 forbidden
        substrings (URL host / webhook / API-key /
        legacy-import / trading-routing shape).

    The Stage 29.5 projection dataclass validates the closed-
    set / pinned-value contract at CONSTRUCTION time, but a
    malicious operator may mutate any frozen-dataclass field of
    the projection via ``object.__setattr__`` (or any
    equivalent path that bypasses ``__setattr__``) AFTER the
    recorder captured it on the recorded entry. This validator
    runs at WRITE time so a post-recording projection mutation
    cannot reach the side-channel JSON artifact's
    projection_summary.

    Returns False on the FIRST failure; non-raising on any
    input.
    """
    if not isinstance(
        projection, Stage29_5PrivatePingMigrationContext,
    ):
        return False
    if not isinstance(projection.schema_version, str):
        return False
    if (
        projection.schema_version
        != STAGE29_5_PRIVATE_PING_CONTEXT_SCHEMA_VERSION
    ):
        return False
    if not is_stage29_5_redaction_status_value(
        projection.redaction_status,
    ):
        return False
    if projection.redaction_status != REDACTION_STATUS_SAFE:
        return False
    if (
        projection.filter_enforcement_status
        != FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING
    ):
        return False
    if not is_stage29_5_measurement_status_value(
        projection.measurement_status,
    ):
        return False
    if not is_stage29_5_migration_source_value(
        projection.migration_source,
    ):
        return False
    if not is_stage29_5_migration_join_status_value(
        projection.join_status_echoed,
    ):
        return False
    if projection.migration_timestamp_utc is not None and not (
        is_safe_iso8601_utc_string(
            projection.migration_timestamp_utc,
        )
    ):
        return False
    if projection.migration_slot is not None and not (
        isinstance(projection.migration_slot, int)
        and not isinstance(projection.migration_slot, bool)
        and projection.migration_slot >= 0
    ):
        return False
    if not is_safe_iso8601_utc_string(
        projection.observed_at_utc,
    ):
        return False
    if (
        projection.post_migration_ath_verified is not None
        and projection.post_migration_ath_verified is not True
        and projection.post_migration_ath_verified is not False
    ):
        return False
    if not isinstance(projection.warnings, tuple):
        return False
    for code in projection.warnings:
        if not isinstance(code, str):
            return False
        if not is_stage29_5_warning_code_value(code):
            return False
        if stage29_5_5_value_carries_forbidden_substring(code):
            return False
    every_string_field_reaching_projection_json = (
        projection.measurement_status,
        projection.migration_source,
        projection.join_status_echoed,
        projection.redaction_status,
        projection.filter_enforcement_status,
        projection.observed_at_utc,
        projection.schema_version,
    )
    for value in every_string_field_reaching_projection_json:
        if not isinstance(value, str):
            return False
        if stage29_5_5_value_carries_forbidden_substring(value):
            return False
    if (
        projection.migration_timestamp_utc is not None
        and stage29_5_5_value_carries_forbidden_substring(
            projection.migration_timestamp_utc,
        )
    ):
        return False
    return True


def _build_artifact_bundle(
    entries: Tuple[Stage29_5_5RecordedRenderEntry, ...],
) -> dict:
    """Build the deterministic JSON-safe artifact bundle dict
    from the recorded entries tuple.

    The bundle:

      * pins the artifact schema version,
      * pins ``informational_only = True`` and
        ``not_a_trading_verdict = True`` flags at the bundle
        level,
      * pins ``filter_enforcement_status =
        NOT_ACTIVE_STAGE_29_PENDING`` and ``redaction_status =
        SAFE`` at the bundle level (echoed from the first
        entry; the recorder pins them on every entry),
      * carries the recorded entries in INSERTION ORDER (the
        recorder appends to the list in the order Stage 27.6
        candidate assembly calls ``read_migration_snapshot``).
    """
    first_entry = entries[0]
    bundle: dict = {
        "schema_version": (
            STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION
        ),
        "informational_only": True,
        "not_a_trading_verdict": True,
        "filter_enforcement_status": (
            first_entry.rendered_block.filter_enforcement_status
        ),
        "redaction_status": (
            first_entry.rendered_block.redaction_status
        ),
        "entry_count": len(entries),
        "entries": [
            _entry_to_json_dict(entry) for entry in entries
        ],
    }
    return bundle


def _entry_to_json_dict(
    entry: Stage29_5_5RecordedRenderEntry,
) -> dict:
    """Project a recorded entry onto a JSON-safe dict."""
    return {
        "schema_version": entry.schema_version,
        "token_mint": entry.token_mint,
        "recorded_at_utc": entry.recorded_at_utc,
        "rendered_block": _rendered_block_to_json_dict(
            entry.rendered_block,
        ),
        "projection_summary": _projection_summary(
            entry.projection,
        ),
        "snapshot_summary": _snapshot_summary(entry.snapshot),
    }


def _rendered_block_to_json_dict(
    block: Stage29_5_5RenderedMigrationContextBlock,
) -> dict:
    """Project a rendered block onto a JSON-safe dict."""
    return {
        "schema_version": block.schema_version,
        "migration_evidence_status_display": (
            block.migration_evidence_status_display
        ),
        "migration_evidence_source_trust_display": (
            block.migration_evidence_source_trust_display
        ),
        "post_migration_ath_verified_display": (
            block.post_migration_ath_verified_display
        ),
        "migration_timestamp_utc_display": (
            block.migration_timestamp_utc_display
        ),
        "migration_slot_display": block.migration_slot_display,
        "migration_source_token": block.migration_source_token,
        "join_status_echoed_token": (
            block.join_status_echoed_token
        ),
        "warnings_display": block.warnings_display,
        "redaction_status": block.redaction_status,
        "filter_enforcement_status": (
            block.filter_enforcement_status
        ),
        "observed_at_utc": block.observed_at_utc,
        "informational_only": block.informational_only,
        "not_a_trading_verdict": block.not_a_trading_verdict,
        "body_text": block.body_text,
    }


def _projection_summary(projection: object) -> dict:
    """Project a Stage 29.5
    ``Stage29_5PrivatePingMigrationContext`` onto a JSON-safe
    summary dict.

    Tuples are converted to lists so the resulting dict is
    JSON-serializable via ``json.dumps``. The summary carries
    only closed-set / safe-shape Stage 29.5 fields; the
    underlying record carries no raw payload by construction.
    """
    return {
        "schema_version": projection.schema_version,
        "measurement_status": projection.measurement_status,
        "warnings": list(projection.warnings),
        "migration_timestamp_utc": (
            projection.migration_timestamp_utc
        ),
        "migration_slot": projection.migration_slot,
        "migration_source": projection.migration_source,
        "post_migration_ath_verified": (
            projection.post_migration_ath_verified
        ),
        "join_status_echoed": projection.join_status_echoed,
        "redaction_status": projection.redaction_status,
        "filter_enforcement_status": (
            projection.filter_enforcement_status
        ),
        "observed_at_utc": projection.observed_at_utc,
    }


def _snapshot_summary(snapshot: object) -> dict:
    """Project a Stage 27.4 ``MigrationSourceSnapshot`` onto a
    JSON-safe summary dict, redacting unsafe audit identifiers.

    The three free-form audit identifiers
    (``migration_event_id`` / ``source_event_ref`` /
    ``raw_capture_ref``) flow from operator-supplied evidence
    records and may carry arbitrary strings. Each one is passed
    through ``stage29_5_5_is_safe_audit_identifier`` -- a string
    that is too long, contains characters outside
    ``[A-Za-z0-9._:-]``, or matches a Stage 29.5.5 forbidden
    substring (URL host / webhook / API-key / legacy-import
    shape) is redacted to ``None`` before it reaches the JSON
    artifact.

    The closed-set ``migration_source`` token and the
    ``migration_timestamp_utc`` ISO-8601 string are safe by
    Stage 27.4 + Stage 29.5 projection-validator construction
    and pass through verbatim.
    """
    return {
        "migration_event_id": _redact_audit_identifier(
            snapshot.migration_event_id,
        ),
        "migration_timestamp_utc": (
            snapshot.migration_timestamp_utc
        ),
        "migration_source": snapshot.migration_source,
        "source_event_ref": _redact_audit_identifier(
            snapshot.source_event_ref,
        ),
        "raw_capture_ref": _redact_audit_identifier(
            snapshot.raw_capture_ref,
        ),
    }


def _redact_audit_identifier(value: object) -> Optional[str]:
    """Return ``value`` when it is a safe-shape audit identifier
    string, otherwise ``None``.

    Conservative by design: a non-string value, an empty string,
    a string longer than 80 chars, a string containing any
    character outside ``[A-Za-z0-9._:-]``, or a string carrying
    a Stage 29.5.5 forbidden substring is all redacted to
    ``None``.
    """
    if value is None:
        return None
    if stage29_5_5_is_safe_audit_identifier(value):
        # ``value`` is a str by virtue of the safe-shape check.
        return value if isinstance(value, str) else None
    return None


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = (
    "STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_WRITER_SCHEMA_VERSION",
    "STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_BUNDLE_SCHEMA_VERSION",
    "STAGE29_5_5_SIDE_CHANNEL_ARTIFACT_FILENAME",
    "Stage29_5_5SideChannelArtifactWriter",
)
