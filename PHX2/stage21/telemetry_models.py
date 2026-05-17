"""Stage 21 telemetry models (skeleton at 21.1).

Stage 21 emits per-run telemetry as small typed records that the
writer modules serialize to a deterministic artifact tree. Stage
21.1 ships the model set used by the foundation manifest writer
(``PHX2.stage21.telemetry_writers``); 21.2+ will add ping /
dispatch metadata records additively.

The records here are intentionally narrow:
  * ``RunMetadata`` -- captures the per-run context: ids, version
    axes, mode flags, the dispatch-safety boolean.
  * ``Stage21FoundationManifest`` -- the top-level record the
    foundation manifest writer emits. Aggregates run metadata,
    the credential attestations, and the allowlist summary.

No record on this module accepts or stores secret values; the
allowlist + attestation fields are populated from the
``Stage21Config`` public summary, which is already redacted.

Stage 21.1 never sends pings, so the ``PingDispatchPlaceholder``
record is shaped here for the 21.2+ writer but unused at 21.1.
"""

from __future__ import annotations

from typing import Mapping, NamedTuple, Tuple

from PHX2.stage21.constants import (
    SAFE_FOR_PUBLIC_DISPATCH,
    STAGE21_MINOR_VERSION,
    STAGE21_VERSION,
)
from PHX2.stage21.credential_attestation import CredentialAttestation


class RunMetadata(NamedTuple):
    """Per-run Stage 21 metadata.

    Fields:
      * ``run_id`` -- caller-supplied run id (typically the
        ``Stage21RunId.run_id`` value).
      * ``stage21_version`` / ``stage21_minor_version`` -- version
        axes captured at run start. Stored separately from the
        ``Stage21RunId`` instance so the manifest layout stays
        flat (the run-id record is opaque; the manifest carries
        the version axes at the top level for the operator).
      * ``provider_mode`` / ``sink_mode`` -- string-form mode
        names. Strings (not enum values) so the manifest writer's
        JSON output is plain.
      * ``dry_run`` / ``live_private`` -- locked-default mode
        flags.
      * ``safe_for_public_dispatch`` -- pinned False invariant.
      * ``generated_at_utc_iso`` -- ISO-8601 UTC string from an
        injected clock. The writer sources this from the caller,
        never from the stdlib ``datetime`` module directly.
    """

    run_id: str
    stage21_version: str
    stage21_minor_version: str
    provider_mode: str
    sink_mode: str
    dry_run: bool
    live_private: bool
    safe_for_public_dispatch: bool
    generated_at_utc_iso: str

    @classmethod
    def of(
        cls,
        *,
        run_id: str,
        provider_mode: str,
        sink_mode: str,
        dry_run: bool,
        live_private: bool,
        generated_at_utc_iso: str,
    ) -> "RunMetadata":
        """Construct a ``RunMetadata`` with version axes from constants.

        Pins ``stage21_version`` / ``stage21_minor_version`` /
        ``safe_for_public_dispatch`` to the locked constants on
        every call so a version bump or a dispatch-safety flip
        propagates into the next run's manifest without threading
        a fixture through every caller.
        """
        return cls(
            run_id=run_id,
            stage21_version=STAGE21_VERSION,
            stage21_minor_version=STAGE21_MINOR_VERSION,
            provider_mode=provider_mode,
            sink_mode=sink_mode,
            dry_run=dry_run,
            live_private=live_private,
            safe_for_public_dispatch=SAFE_FOR_PUBLIC_DISPATCH,
            generated_at_utc_iso=generated_at_utc_iso,
        )

    def public_summary(self) -> Mapping[str, object]:
        """Return a manifest-safe dict view."""
        return {
            "run_id": self.run_id,
            "stage21_version": self.stage21_version,
            "stage21_minor_version": self.stage21_minor_version,
            "provider_mode": self.provider_mode,
            "sink_mode": self.sink_mode,
            "dry_run": self.dry_run,
            "live_private": self.live_private,
            "safe_for_public_dispatch": self.safe_for_public_dispatch,
            "generated_at_utc_iso": self.generated_at_utc_iso,
        }


class AllowlistSummary(NamedTuple):
    """Manifest-safe view of the Stage 21 allowlist.

    Carries only the recipient tuple, the count, and the
    fail-closed flag. Recipient identifiers themselves are not
    treated as secret in Stage 21; only the secret env-var values
    are. Tests still cross-check that the summary never includes
    any secret-class env value.
    """

    recipients: Tuple[str, ...]
    count: int
    fail_closed: bool


class PingDispatchPlaceholder(NamedTuple):
    """Reserved Stage 21.2+ placeholder for a dispatched ping record.

    Declared here so the 21.1 manifest can include a zero-length
    ``pings`` list and the 21.2 writer can fill it without a
    schema break. The placeholder carries the bare-minimum fields
    that any future record will need; the eventual ``Ping`` record
    will be a superset.

    21.1 never produces an instance of this record. The record
    exists in 21.1 so manifest readers can pre-bind to its shape.
    """

    ping_id: str
    candidate_id: str
    safe_for_public_dispatch: bool
    private_preview_marker_present: bool


class Stage21FoundationManifest(NamedTuple):
    """Top-level Stage 21.1 foundation manifest record.

    Aggregates:
      * ``run_metadata`` -- ``RunMetadata``.
      * ``credential_attestations`` -- sorted tuple of
        ``CredentialAttestation``. The writer serializes via the
        public summary; raw secrets cannot appear.
      * ``allowlist_summary`` -- ``AllowlistSummary``.
      * ``pings`` -- zero-length tuple of
        ``PingDispatchPlaceholder``. 21.1 emits no pings; the
        field is reserved for 21.2+ writers.

    Stage 21.1 uses this record only to test the foundation
    artifact-writer is deterministic across re-runs with the same
    clock. No live behavior is wired.
    """

    run_metadata: RunMetadata
    credential_attestations: Tuple[CredentialAttestation, ...]
    allowlist_summary: AllowlistSummary
    pings: Tuple[PingDispatchPlaceholder, ...]


__all__ = [
    "AllowlistSummary",
    "PingDispatchPlaceholder",
    "RunMetadata",
    "Stage21FoundationManifest",
]
