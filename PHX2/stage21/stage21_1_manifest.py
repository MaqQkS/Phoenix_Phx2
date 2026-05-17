"""Stage 21.1 foundation manifest assembler.

Stage 21.1 ships the foundation. This module wires the pieces
together: take a ``Stage21Config`` + a ``Stage21RunId`` and produce
a ``Stage21FoundationManifest`` ready for the writer.

The assembler is deterministic given (a) the input config, (b)
the run id, and (c) the ``generated_at_utc_iso`` provenance
string. All three are caller-supplied; the assembler itself never
calls the clock directly.

21.1 ships no runner / orchestrator -- this assembler is the
unit-of-test for the artifact path and the end-to-end shape of
the eventual Stage 21 manifest. The 21.2+ runner will call this
assembler exactly once per run.
"""

from __future__ import annotations

from PHX2.stage21.config import Stage21Config
from PHX2.stage21.models import Stage21RunId
from PHX2.stage21.telemetry_models import (
    AllowlistSummary,
    RunMetadata,
    Stage21FoundationManifest,
)


def assemble_foundation_manifest(
    *,
    config: Stage21Config,
    run_id: Stage21RunId,
) -> Stage21FoundationManifest:
    """Build the Stage 21.1 foundation manifest.

    The function is pure: identical inputs produce an
    identical manifest. The ``generated_at_utc_iso`` field of the
    run id is propagated into ``RunMetadata`` as the provenance
    timestamp so the writer's output is byte-identical across
    re-runs with the same inputs.

    ``Stage21FoundationManifest`` carries:
      * ``run_metadata`` -- derived from ``config`` + ``run_id``.
      * ``credential_attestations`` -- the config's pre-bundled
        attestation tuple (sorted by name, no raw secret).
      * ``allowlist_summary`` -- snapshot of the parsed allowlist.
      * ``pings`` -- zero-length tuple (21.1 emits no pings).
    """
    run_metadata = RunMetadata.of(
        run_id=run_id.run_id,
        provider_mode=config.provider_mode.value,
        sink_mode=config.sink_mode.value,
        dry_run=config.dry_run,
        live_private=config.live_private,
        generated_at_utc_iso=run_id.generated_at_utc_iso,
    )
    attestations = config.credential_attestations()
    allowlist_summary = AllowlistSummary(
        recipients=config.allowlist.recipients,
        count=len(config.allowlist.recipients),
        fail_closed=config.allowlist.fail_closed,
    )
    return Stage21FoundationManifest(
        run_metadata=run_metadata,
        credential_attestations=attestations,
        allowlist_summary=allowlist_summary,
        pings=(),
    )


__all__ = ["assemble_foundation_manifest"]
