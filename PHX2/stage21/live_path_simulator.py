"""Stage 21.2 end-to-end fake private live-path simulator.

Wires the Stage 21.2 pipeline:

  fake provider event
    -> normalized live event
    -> private-preview candidate
    -> private-preview ping payload
    -> fake private transport capture
    -> Stage 21.2 file artifacts.

Hard scope (identical to the module-level Stage 21.2 scope):

  * Deterministic and local only.
  * File-artifact-only: no SQLite, no database, no PHX2.db
    coupling, no alert_decisions read.
  * No real provider / network / Discord / TG / webhook code.
  * No public / subscriber / paid routing.

The simulator accepts an explicit ``output_dir`` ``Path``. It
rejects a missing parent directory and never recursively
creates parent directories. If ``output_dir`` itself does not
exist, the simulator creates exactly one directory level
(``output_dir.mkdir(parents=False)``); the writers refuse to
write outside ``output_dir``.

Determinism:

  * The fake provider emits the same fake events for the same
    seeds.
  * The normalizer / candidate / ping builders are pure.
  * The fake transport captures with timestamps from the
    injected clock.
  * The artifact writers serialize with sorted keys and a
    trailing newline.

Idempotency:

  * Duplicate fake events (same derived normalized event id)
    are skipped after the first occurrence; the
    ``duplicates_skipped`` count in the manifest summarizes the
    drop.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Optional, Sequence, Tuple

from PHX2.stage21 import safe_content as _sc
from PHX2.stage21.clock import Clock, default_clock
from PHX2.stage21.constants import Stage21ErrorCode
from PHX2.stage21.errors import Stage21BoundaryError
from PHX2.stage21.fake_provider import (
    Stage21FakeEvent,
    Stage21FakeEventSeed,
    Stage21FakeProvider,
)
from PHX2.stage21.fake_transport import (
    FakePrivateTransport,
    FakeTransportCaptureRecord,
)
from PHX2.stage21.normalized_events import (
    NormalizedLiveEvent,
    normalize_fake_event,
)
from PHX2.stage21.ping_builder import (
    build_candidate_from_normalized_event,
    build_private_preview_payload,
)
from PHX2.stage21.ping_payloads import (
    PrivatePreviewCandidate,
    PrivatePreviewPingPayload,
)
from PHX2.stage21.stage21_2_manifest import (
    Stage21_2SimulationCounts,
    assemble_stage21_2_manifest,
)
from PHX2.stage21.telemetry_writer import (
    STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME,
    STAGE21_2_MANIFEST_FILENAME,
    STAGE21_2_PING_LEDGER_FILENAME,
    STAGE21_2_TELEMETRY_SUMMARY_FILENAME,
    write_stage21_2_fake_transport_capture,
    write_stage21_2_manifest,
    write_stage21_2_ping_ledger,
    write_stage21_2_telemetry_summary,
)


# ---------------------------------------------------------------------------
# Output-directory safety
# ---------------------------------------------------------------------------


def _prepare_output_dir(output_dir: Path) -> None:
    """Validate ``output_dir`` and create it (one level only) if missing.

    Raises ``Stage21BoundaryError`` (E2106) when:
      * ``output_dir`` is not a ``Path``;
      * ``output_dir`` is empty or refers to the cwd;
      * ``output_dir`` contains a ``..`` component;
      * ``output_dir.parent`` does not exist (no recursive mkdir).
    """
    if not isinstance(output_dir, Path):
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail=(
                "Stage 21.2 simulator output_dir must be a pathlib.Path "
                f"instance; got {type(output_dir).__name__}"
            ),
        )
    rendered = str(output_dir).strip()
    if rendered == "" or rendered == ".":
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail="Stage 21.2 simulator output_dir is empty or cwd",
        )
    if ".." in output_dir.parts:
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail="Stage 21.2 simulator output_dir traverses via '..'",
        )
    parent = output_dir.parent
    if not parent.exists() or not parent.is_dir():
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail=(
                "Stage 21.2 simulator output_dir parent does not exist; "
                "the simulator does not recursively create parent "
                "directories"
            ),
        )
    if not output_dir.exists():
        output_dir.mkdir(parents=False, exist_ok=False)
    elif not output_dir.is_dir():
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail=(
                "Stage 21.2 simulator output_dir exists but is not a "
                "directory"
            ),
        )


# ---------------------------------------------------------------------------
# Simulation result
# ---------------------------------------------------------------------------


class Stage21_2SimulationResult(NamedTuple):
    """In-memory record of a single Stage 21.2 simulator run."""

    run_id: str
    generated_at_utc_iso: str
    counts: Stage21_2SimulationCounts
    normalized_events: Tuple[NormalizedLiveEvent, ...]
    candidates: Tuple[PrivatePreviewCandidate, ...]
    pings: Tuple[PrivatePreviewPingPayload, ...]
    captures: Tuple[FakeTransportCaptureRecord, ...]
    manifest_path: Path
    ping_ledger_path: Path
    fake_transport_capture_path: Path
    telemetry_summary_path: Path


# ---------------------------------------------------------------------------
# Telemetry summary
# ---------------------------------------------------------------------------


def _build_telemetry_summary(
    run_id: str,
    generated_at_utc_iso: str,
    counts: Stage21_2SimulationCounts,
    captures: Sequence[FakeTransportCaptureRecord],
) -> dict[str, object]:
    """Return the Stage 21.2 telemetry summary mapping.

    The summary captures stable aggregates only. It carries no
    secret material, no URL, no public/paid/subscriber routing
    identifier.
    """
    capture_payload_hashes = sorted({c.payload_hash for c in captures})
    return {
        "run_id": run_id,
        "generated_at_utc_iso": generated_at_utc_iso,
        "counts": dict(counts.public_summary()),
        "capture_payload_hashes_sorted": capture_payload_hashes,
    }


# ---------------------------------------------------------------------------
# Simulator entrypoint
# ---------------------------------------------------------------------------


def run_live_path_simulation(
    *,
    seeds: Sequence[Stage21FakeEventSeed],
    output_dir: Path,
    run_id: str,
    generated_at_utc_iso: str,
    clock: Optional[Clock] = None,
) -> Stage21_2SimulationResult:
    """Run the Stage 21.2 fake private live-path simulation end-to-end.

    Steps:
      1. Build the fake provider from ``seeds``.
      2. Fetch the deterministic fake events.
      3. Normalize each event; skip duplicates by derived
         normalized event id.
      4. Build a candidate per unique normalized event.
      5. Build a private-preview ping per candidate.
      6. Capture each ping into the fake transport.
      7. Assemble + write the four Stage 21.2 artifacts.

    Pure modulo the file-artifact writes: identical seeds + clock
    + ids produce byte-identical artifacts.

    Raises ``Stage21BoundaryError`` (E2106) on unsafe output_dir.
    Raises ``Stage21TelemetryError`` (E2110..E2113) on any
    validation failure inside the pipeline.
    """
    if not isinstance(seeds, (list, tuple)):
        raise Stage21BoundaryError(
            Stage21ErrorCode.E2106,
            detail=(
                "run_live_path_simulation seeds must be a list or tuple of "
                "Stage21FakeEventSeed"
            ),
        )
    # Stage 21.2 remediation (simulator-entry defense-in-depth):
    # validate run_id and generated_at_utc_iso BEFORE
    # _prepare_output_dir. This ensures the Codex PoC for a
    # URL-laced run_id raises Stage21Error E2153 without ever
    # creating the output directory, so the run-level PoC test
    # can assert that no artifact files exist after the failed
    # run attempt.
    _sc.validate_safe_string(
        run_id,
        kind=_sc.SafeStringKind.SHORT_IDENTIFIER,
        field_name="run_id",
    )
    _sc.validate_timestamp_value(
        generated_at_utc_iso,
        field_name="generated_at_utc_iso",
    )
    _prepare_output_dir(output_dir)

    active_clock = clock or default_clock()

    provider = Stage21FakeProvider(seeds)
    fake_events: tuple[Stage21FakeEvent, ...] = provider.fetch_events()

    normalized: list[NormalizedLiveEvent] = []
    seen_event_ids: set[str] = set()
    duplicates_skipped = 0
    for fake in fake_events:
        norm = normalize_fake_event(
            provider_event_id=fake.provider_event_id,
            provider_name=fake.provider_name,
            source_kind=fake.source_kind,
            chain=fake.chain,
            mint=fake.mint,
            event_type=fake.event_type,
            observed_at_utc=fake.observed_at_utc,
            slot=fake.slot,
            signature=fake.signature,
            raw_payload=fake.raw_payload,
        )
        if norm.event_id in seen_event_ids:
            duplicates_skipped += 1
            continue
        seen_event_ids.add(norm.event_id)
        normalized.append(norm)

    candidates: list[PrivatePreviewCandidate] = [
        build_candidate_from_normalized_event(n) for n in normalized
    ]

    pings: list[PrivatePreviewPingPayload] = [
        build_private_preview_payload(c) for c in candidates
    ]

    transport = FakePrivateTransport(clock=active_clock)
    for ping in pings:
        transport.capture(ping)
    captures = transport.captures()

    counts = Stage21_2SimulationCounts(
        fake_events_received=len(fake_events),
        normalized_events_emitted=len(normalized),
        candidates_built=len(candidates),
        pings_built=len(pings),
        captures_recorded=len(captures),
        duplicates_skipped=duplicates_skipped,
    )

    manifest_mapping = assemble_stage21_2_manifest(
        run_id=run_id,
        generated_at_utc_iso=generated_at_utc_iso,
        counts=counts,
    )
    summary_mapping = _build_telemetry_summary(
        run_id=run_id,
        generated_at_utc_iso=generated_at_utc_iso,
        counts=counts,
        captures=captures,
    )

    manifest_path = output_dir / STAGE21_2_MANIFEST_FILENAME
    ping_ledger_path = output_dir / STAGE21_2_PING_LEDGER_FILENAME
    fake_transport_capture_path = (
        output_dir / STAGE21_2_FAKE_TRANSPORT_CAPTURE_FILENAME
    )
    telemetry_summary_path = output_dir / STAGE21_2_TELEMETRY_SUMMARY_FILENAME

    write_stage21_2_manifest(manifest_mapping, manifest_path)
    write_stage21_2_ping_ledger(pings, ping_ledger_path)
    write_stage21_2_fake_transport_capture(
        captures, fake_transport_capture_path
    )
    write_stage21_2_telemetry_summary(summary_mapping, telemetry_summary_path)

    return Stage21_2SimulationResult(
        run_id=run_id,
        generated_at_utc_iso=generated_at_utc_iso,
        counts=counts,
        normalized_events=tuple(normalized),
        candidates=tuple(candidates),
        pings=tuple(pings),
        captures=captures,
        manifest_path=manifest_path,
        ping_ledger_path=ping_ledger_path,
        fake_transport_capture_path=fake_transport_capture_path,
        telemetry_summary_path=telemetry_summary_path,
    )


__all__ = [
    "Stage21_2SimulationResult",
    "run_live_path_simulation",
]
