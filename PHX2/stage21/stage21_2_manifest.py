"""Stage 21.2 manifest assembler.

Builds the deterministic Stage 21.2 manifest dict that the
telemetry writer serializes to ``stage21_2_manifest.json``. The
manifest carries:

  * Stage 21.2 run metadata (id, version axes, locked markers,
    generated_at_utc_iso).
  * Counts of fake events processed, normalized events emitted,
    candidates built, pings dispatched (to the fake transport),
    captures recorded, and duplicates skipped.
  * The four locked Stage 21.2 marker values plus the locked
    dispatch target so the artifact carries the markers
    explicitly.

The assembler is a pure function: identical inputs produce a
byte-identical manifest mapping. It does not read the
environment, does not read alert_decisions, does not open a
database, does not import any Phoenix1 / Stage 17..20 runtime
module.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple

from PHX2.stage21 import safe_content as _sc
from PHX2.stage21.constants import (
    SAFE_FOR_PUBLIC_DISPATCH,
    STAGE21_VERSION,
)
from PHX2.stage21.ping_payloads import (
    FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET,
    LIVE_MODE_MARKER,
    NORMALIZED_EVENT_SCHEMA_VERSION,
    OPERATOR_ONLY_MARKER,
    PING_PAYLOAD_SCHEMA_VERSION,
    PRIVATE_PREVIEW_VISIBILITY,
    STAGE21_2_STAGE_LABEL,
    STAGE21_FAKE_CHAIN_NAME,
    STAGE21_FAKE_PROVIDER_NAME,
    STAGE21_FAKE_SOURCE_KIND,
)


# ---------------------------------------------------------------------------
# Simulator-summary record (consumed by the assembler)
# ---------------------------------------------------------------------------


class Stage21_2SimulationCounts(NamedTuple):
    """Per-run aggregate counts produced by the Stage 21.2 simulator.

    Carries:
      * ``fake_events_received`` -- how many fake events the
        simulator received from the provider.
      * ``normalized_events_emitted`` -- how many normalized
        events the normalizer accepted.
      * ``candidates_built`` -- how many candidates the builder
        produced (typically == ``normalized_events_emitted``
        unless duplicates are deduped).
      * ``pings_built`` -- how many ping payloads were built.
      * ``captures_recorded`` -- how many captures the fake
        transport accepted.
      * ``duplicates_skipped`` -- how many fake events were
        deterministically skipped because their derived
        normalized event id had already been processed.
    """

    fake_events_received: int
    normalized_events_emitted: int
    candidates_built: int
    pings_built: int
    captures_recorded: int
    duplicates_skipped: int

    def public_summary(self) -> Mapping[str, int]:
        return {
            "fake_events_received": self.fake_events_received,
            "normalized_events_emitted": self.normalized_events_emitted,
            "candidates_built": self.candidates_built,
            "pings_built": self.pings_built,
            "captures_recorded": self.captures_recorded,
            "duplicates_skipped": self.duplicates_skipped,
        }


# ---------------------------------------------------------------------------
# Manifest assembler
# ---------------------------------------------------------------------------


def assemble_stage21_2_manifest(
    *,
    run_id: str,
    generated_at_utc_iso: str,
    counts: Stage21_2SimulationCounts,
) -> Mapping[str, object]:
    """Return the Stage 21.2 manifest as a deterministic mapping.

    The mapping is consumed by
    ``PHX2.stage21.telemetry_writer.write_stage21_2_manifest``.
    Pure: identical inputs produce a byte-identical mapping.
    """
    if not isinstance(run_id, str) or run_id == "":
        raise ValueError(
            "assemble_stage21_2_manifest run_id must be a non-empty str"
        )
    if not isinstance(generated_at_utc_iso, str) or generated_at_utc_iso == "":
        raise ValueError(
            "assemble_stage21_2_manifest generated_at_utc_iso must be "
            "a non-empty str"
        )
    if not isinstance(counts, Stage21_2SimulationCounts):
        raise ValueError(
            "assemble_stage21_2_manifest counts must be a "
            "Stage21_2SimulationCounts"
        )
    # Stage 21.2 remediation (R11f): apply the shared safe_content
    # predicate to run_id and generated_at_utc_iso BEFORE
    # constructing the manifest dict. This is the boundary the
    # Codex PoC for a URL-laced run_id enters: a value carrying
    # an https-scheme URL plus a routing token raises
    # ``Stage21Error`` ``E2153`` here and the manifest dict is
    # never built.
    _sc.validate_safe_string(
        run_id,
        kind=_sc.SafeStringKind.SHORT_IDENTIFIER,
        field_name="run_id",
    )
    _sc.validate_timestamp_value(
        generated_at_utc_iso,
        field_name="generated_at_utc_iso",
    )
    return {
        "run_metadata": {
            "run_id": run_id,
            "stage21_version": STAGE21_VERSION,
            "stage21_2_stage_label": STAGE21_2_STAGE_LABEL,
            "generated_at_utc_iso": generated_at_utc_iso,
            "safe_for_public_dispatch": SAFE_FOR_PUBLIC_DISPATCH,
        },
        "locked_markers": {
            "stage": STAGE21_2_STAGE_LABEL,
            "visibility": PRIVATE_PREVIEW_VISIBILITY,
            "operator_only": OPERATOR_ONLY_MARKER,
            "live_mode": LIVE_MODE_MARKER,
            "dispatch_target": FAKE_PRIVATE_TRANSPORT_DISPATCH_TARGET,
        },
        "fake_provider": {
            "provider_name": STAGE21_FAKE_PROVIDER_NAME,
            "chain": STAGE21_FAKE_CHAIN_NAME,
            "source_kind": STAGE21_FAKE_SOURCE_KIND,
        },
        "schema_versions": {
            "normalized_event": NORMALIZED_EVENT_SCHEMA_VERSION,
            "ping_payload": PING_PAYLOAD_SCHEMA_VERSION,
        },
        "counts": dict(counts.public_summary()),
    }


__all__ = [
    "Stage21_2SimulationCounts",
    "assemble_stage21_2_manifest",
]
