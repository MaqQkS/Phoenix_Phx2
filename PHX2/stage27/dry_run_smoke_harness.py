"""Stage 27.7a deterministic dry-run smoke harness.

Stage 27.7a ships a small in-process harness that drives the Stage
27.6 bounded dry-run runner over deterministic fake provider
events plus deterministic fake price / ATH / migration sources.
The harness exists so the operator can prove the Stage 27.3 ->
27.2 -> 27.4 -> 27.5 -> 27.6 pipeline works end-to-end without
opening a network connection, calling Discord, or reading any
real `.env` value.

The harness is DRY-RUN ONLY:

  * it NEVER opens a network connection,
  * it NEVER imports a Discord / Telegram / X-social / messaging
    library,
  * it NEVER imports a network / RPC / DB / scheduler library,
  * it NEVER reads the process environment,
  * it NEVER persists a dedupe ledger across runs,
  * it NEVER enforces a Stage 26 candidate policy,
  * it NEVER promotes UNKNOWN / DISAGREE / USDC into the existing
    SOL calibration lane,
  * it NEVER widens the closed-set vocabularies emitted by Stage
    27.2 / 27.3 / 27.4 / 27.5 / 27.6.

Two-factor LIVE authorization (mirrored from Stage 27.6):

  * if the caller passes ``live_mode_authority="LIVE_ALLOWED"`` the
    Stage 27.6 runner fail-closes with ``mode=LIVE_REFUSED``. The
    smoke harness surfaces the LIVE_REFUSED summary unchanged. The
    Stage 27 LIVE dispatch surface lives in Stage 27.7b and is NOT
    introduced here.
  * any other ``live_mode_authority`` value (``DRY_RUN`` /
    ``LIVE_REFUSED`` / any operator-supplied label) runs as a
    dry-run smoke.

Determinism:

  * the smoke summary fields ``smoke_id`` / ``run_id`` /
    ``session_id`` / ``output_root`` come from the caller; the
    counter fields come from the Stage 27.6 run summary.
  * identical inputs always produce a byte-equal canonical JSON
    encoding (`sort_keys=True`, `separators=(",", ":")`,
    `ensure_ascii=False`).

Argument discipline:

  * The harness REFUSES to start without an explicitly injected
    ``output_root`` (Stage 27.7a never defaults to a path under
    the production tree).
  * The harness defaults to ``DRY_RUN``; the caller must pass
    ``live_mode_authority="LIVE_ALLOWED"`` to even attempt LIVE,
    and Stage 27.6 still fail-closes.
  * Every input (events, sources, ids, bounds) is an argument; no
    value is read from the environment.

This module imports only stdlib (``json`` / ``datetime`` /
``pathlib`` / ``typing``) plus Stage 27.2 / 27.4 / 27.6
production modules. It does NOT import Stage 21-26 production
code, does NOT import Stage 27.1 production code, does NOT import
any network / RPC / messaging / DB / scheduler / secrets-
management library, does NOT read the process environment, does
NOT define a CLI surface, and contains no top-level I/O.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, NamedTuple, Optional, Tuple

from PHX2.stage27.bounded_tradeable_ping_runner import (
    LIVE_AUTHORITY_DRY_RUN,
    LIVE_AUTHORITY_LIVE_ALLOWED,
    RUN_MODE_DRY_RUN,
    RUN_MODE_LIVE_REFUSED,
    STAGE27_6_RUN_SUMMARY_SCHEMA_VERSION,
    STOP_REASON_LIVE_MODE_REFUSED,
    Stage27_6BoundedDryRunRunResult,
    Stage27_6Clock,
    Stage27_6RunSummaryRecord,
    Stage27_6RunnerBoundsError,
    run_bounded_dry_run,
)
from PHX2.stage27.live_candidate_assembler import (
    CANDIDATE_REASON_USDC_OBSERVE_ONLY,
    CANDIDATE_STATUS_RENDERED_DRY_RUN,
    STAGE27_6_CANDIDATE_SCHEMA_VERSION,
    Stage27_6LiveCandidateRecord,
    Stage27_6Sources,
)
from PHX2.stage27.pair_detection_constants import (
    KNOWN_USDC_MINT,
    KNOWN_WRAPPED_SOL_MINT,
)
from PHX2.stage27.price_ath_context_models import (
    ATH_UNIT_SOL,
    ATH_UNIT_USDC,
    PRICE_UNIT_SOL,
    PRICE_UNIT_USDC,
)
from PHX2.stage27.price_ath_context_reader import (
    AthSourceSnapshot,
    FrozenStage27_4Clock,
    MigrationSourceSnapshot,
    PriceSourceSnapshot,
)
from PHX2.stage27.provider_ingest_models import (
    EVENT_KIND_SWAP,
    EVENT_KIND_UNKNOWN,
    ProviderIngestInputRecord,
)


# ---------------------------------------------------------------------------
# Stage 27.7a version axes
# ---------------------------------------------------------------------------


STAGE27_7A_MINOR_VERSION: str = "27.7a"
STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION: str = (
    "stage27_v0_dry_run_smoke_summary"
)


# ---------------------------------------------------------------------------
# Stage 27.7a typed harness errors
# ---------------------------------------------------------------------------


class Stage27_7aHarnessError(Exception):
    """Base class for Stage 27.7a dry-run smoke harness errors."""


class Stage27_7aOutputRootError(Stage27_7aHarnessError):
    """The smoke harness was called without an explicitly injected
    output root.

    Stage 27.7a is dry-run only and never defaults to a path under
    the production tree. The caller MUST pass an existing directory.
    """


# ---------------------------------------------------------------------------
# Default deterministic clock + sources
# ---------------------------------------------------------------------------


DEFAULT_SMOKE_FIXED_UTC: datetime = datetime(
    2026, 5, 22, 12, 0, 30, tzinfo=timezone.utc
)
DEFAULT_SMOKE_FIXED_UTC_ISO: str = "2026-05-22T12:00:30+00:00"
DEFAULT_SMOKE_PRICE_STALENESS_THRESHOLD_SECONDS: int = 300


class FrozenSmokeRunnerClock(NamedTuple):
    """Deterministic ``Stage27_6Clock`` for Stage 27.7a smokes."""

    iso: str = DEFAULT_SMOKE_FIXED_UTC_ISO

    def now_utc_iso(self) -> str:
        return self.iso


class _SmokePriceSource(NamedTuple):
    """Pair-aware ``PriceContextSource`` for Stage 27.7a smokes.

    Returns a deterministic SOL-unit snapshot for SOL pairs and a
    deterministic USDC-unit snapshot for USDC pairs. Stage 27.4 is
    responsible for the pair-aware mapping; this fake source only
    has to match the requested ``pair_quote_asset``.
    """

    fetched_at_utc: str = DEFAULT_SMOKE_FIXED_UTC_ISO

    def read_price_snapshot(
        self,
        token_mint: str,
        *,
        pair_quote_asset: str,
    ) -> PriceSourceSnapshot:
        if pair_quote_asset == "USDC":
            return PriceSourceSnapshot(
                price_value="0.12",
                price_unit=PRICE_UNIT_USDC,
                source_label="fake-birdeye-smoke",
                fetched_at_utc=self.fetched_at_utc,
            )
        return PriceSourceSnapshot(
            price_value="0.001",
            price_unit=PRICE_UNIT_SOL,
            source_label="fake-birdeye-smoke",
            fetched_at_utc=self.fetched_at_utc,
        )


class _SmokeAthSource(NamedTuple):
    """Pair-aware ``AthContextSource`` for Stage 27.7a smokes."""

    ath_observed_at_utc: str = "2026-05-22T11:30:00+00:00"

    def read_ath_snapshot(
        self,
        token_mint: str,
        *,
        pair_quote_asset: str,
    ) -> AthSourceSnapshot:
        if pair_quote_asset == "USDC":
            return AthSourceSnapshot(
                ath_value="1.50",
                ath_unit=ATH_UNIT_USDC,
                source_label="fake-birdeye-smoke",
                ath_observed_at_utc=self.ath_observed_at_utc,
                window_starts_post_migration=True,
            )
        return AthSourceSnapshot(
            ath_value="0.005",
            ath_unit=ATH_UNIT_SOL,
            source_label="fake-birdeye-smoke",
            ath_observed_at_utc=self.ath_observed_at_utc,
            window_starts_post_migration=True,
        )


class _SmokeMigrationSource(NamedTuple):
    """``MigrationContextSource`` for Stage 27.7a smokes."""

    migration_timestamp_utc: str = "2026-05-22T11:00:00+00:00"

    def read_migration_snapshot(
        self, token_mint: str
    ) -> MigrationSourceSnapshot:
        return MigrationSourceSnapshot(
            migration_event_id="smoke-mig-1",
            migration_timestamp_utc=self.migration_timestamp_utc,
            migration_source="ON_CHAIN_MIGRATION_EVENT",
            source_event_ref="smoke-prov-mig-1",
            raw_capture_ref="smoke-rcap-mig-1",
        )


def build_default_smoke_sources(
    *,
    price_staleness_threshold_seconds: int = (
        DEFAULT_SMOKE_PRICE_STALENESS_THRESHOLD_SECONDS
    ),
    fixed_utc: datetime = DEFAULT_SMOKE_FIXED_UTC,
) -> Stage27_6Sources:
    """Return a deterministic ``Stage27_6Sources`` bundle.

    Pure / deterministic. The injected clocks always return the
    same UTC value so the smoke summary stays byte-stable across
    runs.
    """
    return Stage27_6Sources(
        price_source=_SmokePriceSource(),
        ath_source=_SmokeAthSource(),
        migration_source=_SmokeMigrationSource(),
        stage27_4_clock=FrozenStage27_4Clock(fixed_utc=fixed_utc),
        stage27_5_clock=FrozenSmokeRunnerClock(),
        price_staleness_threshold_seconds=(
            price_staleness_threshold_seconds
        ),
    )


def build_default_smoke_clock() -> Stage27_6Clock:
    """Return a deterministic Stage 27.6 wall clock for smokes."""
    return FrozenSmokeRunnerClock()


# ---------------------------------------------------------------------------
# Default deterministic smoke event set
# ---------------------------------------------------------------------------


_DEFAULT_SMOKE_OBSERVED_AT_UTC: str = "2026-05-22T11:59:00+00:00"


def _smoke_sol_event(
    idx: int, token_mint: str
) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius-smoke",
        provider_event_id=f"smoke-evt-sol-{idx}",
        normalized_event_id=f"smoke-norm-sol-{idx}",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc=_DEFAULT_SMOKE_OBSERVED_AT_UTC,
        token_mint=token_mint,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        raw_capture_ref=f"smoke-rcap-sol-{idx}",
        source_summary="smoke-summary",
    )


def _smoke_usdc_event(
    idx: int, token_mint: str
) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius-smoke",
        provider_event_id=f"smoke-evt-usdc-{idx}",
        normalized_event_id=f"smoke-norm-usdc-{idx}",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc=_DEFAULT_SMOKE_OBSERVED_AT_UTC,
        token_mint=token_mint,
        quote_mint=KNOWN_USDC_MINT,
        raw_capture_ref=f"smoke-rcap-usdc-{idx}",
        source_summary="smoke-summary",
    )


def _smoke_unknown_event(
    idx: int, token_mint: str
) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius-smoke",
        provider_event_id=f"smoke-evt-unk-{idx}",
        normalized_event_id=f"smoke-norm-unk-{idx}",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc=_DEFAULT_SMOKE_OBSERVED_AT_UTC,
        token_mint=token_mint,
        quote_mint=None,
        raw_capture_ref=f"smoke-rcap-unk-{idx}",
        source_summary="smoke-summary",
    )


def _smoke_disagree_event(
    idx: int, token_mint: str
) -> ProviderIngestInputRecord:
    return ProviderIngestInputRecord(
        provider_id="fake-helius-smoke",
        provider_event_id=f"smoke-evt-dis-{idx}",
        normalized_event_id=f"smoke-norm-dis-{idx}",
        event_kind=EVENT_KIND_SWAP,
        observed_at_utc=_DEFAULT_SMOKE_OBSERVED_AT_UTC,
        token_mint=token_mint,
        quote_mint=KNOWN_WRAPPED_SOL_MINT,
        provider_quote_asset_hint="USDC",
        raw_capture_ref=f"smoke-rcap-dis-{idx}",
        source_summary="smoke-summary",
    )


def build_default_smoke_events() -> Tuple[
    ProviderIngestInputRecord, ...
]:
    """Return the canonical Stage 27.7a smoke event set.

    The default set exercises every pair-aware class plus a
    duplicate so the smoke summary counters stay easy to pin:

      * one SOL event,
      * one duplicate of the SOL event (run-local dedupe),
      * one USDC event,
      * one UNKNOWN event (no quote mint),
      * one DISAGREE event (SOL quote mint with USDC provider
        hint).

    The expected counter distribution is documented in the
    operator runbook (Section 6) and in the smoke checklist
    (Section C).
    """
    return (
        _smoke_sol_event(idx=1, token_mint="SmokeMintSol1"),
        # Duplicate of the SOL event (same provider/normalized id +
        # same token mint) so Stage 27.6 run-local dedupe fires.
        _smoke_sol_event(idx=1, token_mint="SmokeMintSol1"),
        _smoke_usdc_event(idx=2, token_mint="SmokeMintUsdc2"),
        _smoke_unknown_event(idx=3, token_mint="SmokeMintUnk3"),
        _smoke_disagree_event(idx=4, token_mint="SmokeMintDis4"),
    )


# ---------------------------------------------------------------------------
# Stage 27.7a smoke summary record + canonical JSON encoder
# ---------------------------------------------------------------------------


class Stage27_7aSmokeSummaryRecord(NamedTuple):
    """Immutable Stage 27.7a dry-run smoke summary.

    Wraps the Stage 27.6 run-summary counters and adds the Stage
    27.7a-specific ``smoke_id`` and ``output_root`` fields.

    Fields:

      * ``smoke_id``                  -- caller-supplied stable
                                         smoke identifier.
      * ``run_id``                    -- caller-supplied; ``None``
                                         when not attached.
      * ``session_id``                -- caller-supplied; ``None``
                                         when not attached.
      * ``mode``                      -- closed-set Stage 27.6
                                         ``RUN_MODE`` token (
                                         ``DRY_RUN`` or
                                         ``LIVE_REFUSED``).
      * ``events_seen``               -- copied from the Stage 27.6
                                         run summary.
      * ``candidates_assembled``      -- copied.
      * ``pings_rendered``            -- copied.
      * ``artifacts_written``         -- copied.
      * ``duplicates_skipped``        -- copied.
      * ``unknown_suppressed``        -- copied.
      * ``disagree_suppressed``       -- copied.
      * ``usdc_observe_only_count``   -- count of candidates whose
                                         ``candidate_reason`` is
                                         ``USDC_OBSERVE_ONLY``.
      * ``unsupported_skipped``       -- copied.
      * ``errors``                    -- copied (sum of
                                         ``ERROR`` and
                                         ``ARTIFACT_WRITE_FAILED``).
      * ``output_root``               -- resolved absolute path
                                         string of the injected
                                         output root.
      * ``schema_version``            -- locked Stage 27.7a smoke
                                         summary schema version.
    """

    smoke_id: str
    run_id: Optional[str]
    session_id: Optional[str]
    mode: str
    events_seen: int
    candidates_assembled: int
    pings_rendered: int
    artifacts_written: int
    duplicates_skipped: int
    unknown_suppressed: int
    disagree_suppressed: int
    usdc_observe_only_count: int
    unsupported_skipped: int
    errors: int
    output_root: str
    schema_version: str


class Stage27_7aDryRunSmokeResult(NamedTuple):
    """Immutable Stage 27.7a dry-run smoke result.

    Bundles the Stage 27.7a smoke summary, the underlying Stage
    27.6 run summary, and the per-event candidate tuple so tests
    can pin every axis deterministically. The candidate tuple is
    in input order.
    """

    smoke_summary: Stage27_7aSmokeSummaryRecord
    run_summary: Stage27_6RunSummaryRecord
    candidates: tuple[Stage27_6LiveCandidateRecord, ...]


def canonical_smoke_summary_json(
    summary: Stage27_7aSmokeSummaryRecord,
) -> str:
    """Return the canonical JSON encoding of a smoke summary.

    Stable across runs: ``sort_keys=True``,
    ``separators=(",", ":")``, ``ensure_ascii=False``.

    Pure / deterministic.
    """
    if not isinstance(summary, Stage27_7aSmokeSummaryRecord):
        raise TypeError(
            "canonical_smoke_summary_json requires a "
            "Stage27_7aSmokeSummaryRecord"
        )
    mapping = {
        "smoke_id": summary.smoke_id,
        "run_id": summary.run_id,
        "session_id": summary.session_id,
        "mode": summary.mode,
        "events_seen": summary.events_seen,
        "candidates_assembled": summary.candidates_assembled,
        "pings_rendered": summary.pings_rendered,
        "artifacts_written": summary.artifacts_written,
        "duplicates_skipped": summary.duplicates_skipped,
        "unknown_suppressed": summary.unknown_suppressed,
        "disagree_suppressed": summary.disagree_suppressed,
        "usdc_observe_only_count": (
            summary.usdc_observe_only_count
        ),
        "unsupported_skipped": summary.unsupported_skipped,
        "errors": summary.errors,
        "output_root": summary.output_root,
        "schema_version": summary.schema_version,
    }
    return json.dumps(
        mapping,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Helpers for projecting the Stage 27.6 run summary into the smoke summary
# ---------------------------------------------------------------------------


def _count_usdc_observe_only(
    candidates: tuple[Stage27_6LiveCandidateRecord, ...],
) -> int:
    """Count candidates whose ``candidate_reason`` is
    ``USDC_OBSERVE_ONLY``.

    Stage 27.6 collapses successful SOL/USDC candidates to
    ``ASSEMBLED`` when ``write_artifacts=False`` and to
    ``RENDERED_DRY_RUN`` otherwise; the ``candidate_reason`` axis
    survives both modes, so the count remains stable regardless of
    whether the smoke wrote artifacts.
    """
    return sum(
        1
        for c in candidates
        if c.candidate_reason == CANDIDATE_REASON_USDC_OBSERVE_ONLY
    )


def _project_smoke_summary(
    *,
    smoke_id: str,
    output_root: Path,
    run_summary: Stage27_6RunSummaryRecord,
    candidates: tuple[Stage27_6LiveCandidateRecord, ...],
) -> Stage27_7aSmokeSummaryRecord:
    return Stage27_7aSmokeSummaryRecord(
        smoke_id=smoke_id,
        run_id=run_summary.run_id,
        session_id=run_summary.session_id,
        mode=run_summary.mode,
        events_seen=run_summary.events_seen,
        candidates_assembled=run_summary.candidates_assembled,
        pings_rendered=run_summary.pings_rendered,
        artifacts_written=run_summary.artifacts_written,
        duplicates_skipped=run_summary.duplicates_skipped,
        unknown_suppressed=run_summary.unknown_suppressed,
        disagree_suppressed=run_summary.disagree_suppressed,
        usdc_observe_only_count=_count_usdc_observe_only(
            candidates
        ),
        unsupported_skipped=run_summary.unsupported_skipped,
        errors=(
            run_summary.errors
            + run_summary.artifact_write_failures
        ),
        output_root=str(output_root.resolve()),
        schema_version=STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------------
# Public smoke entrypoint
# ---------------------------------------------------------------------------


DEFAULT_SMOKE_MAX_EVENTS: int = 32
DEFAULT_SMOKE_CANDIDATE_ID_PREFIX: str = "smoke_cand_"
DEFAULT_SMOKE_PING_ID_PREFIX: str = "smoke_ping_"


def run_dry_run_smoke(
    *,
    events: Iterable[ProviderIngestInputRecord],
    sources: Stage27_6Sources,
    output_root: Path,
    smoke_id: str,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    clock: Optional[Stage27_6Clock] = None,
    max_events: int = DEFAULT_SMOKE_MAX_EVENTS,
    max_pings: Optional[int] = None,
    live_mode_authority: str = LIVE_AUTHORITY_DRY_RUN,
    write_artifacts: bool = True,
    write_summary_artifact: bool = False,
    candidate_id_prefix: str = DEFAULT_SMOKE_CANDIDATE_ID_PREFIX,
    ping_id_prefix: str = DEFAULT_SMOKE_PING_ID_PREFIX,
) -> Stage27_7aDryRunSmokeResult:
    """Drive the Stage 27.7a deterministic dry-run smoke.

    Stage 27.7a is dry-run only. The harness:

      * REFUSES to start without an explicitly injected
        ``output_root`` (``Stage27_7aOutputRootError``).
      * REFUSES to start when the injected ``output_root`` does not
        exist or is not a directory (``Stage27_7aOutputRootError``).
      * Defaults ``live_mode_authority`` to ``DRY_RUN``; the
        Stage 27.6 runner still fail-closes on ``LIVE_ALLOWED``.
      * NEVER reads the process environment, NEVER opens a network
        connection, NEVER imports a messaging library.

    Returns a ``Stage27_7aDryRunSmokeResult`` carrying the Stage
    27.7a smoke summary, the underlying Stage 27.6 run summary,
    and the per-event candidate tuple.

    The ``smoke_id`` is required so the smoke summary stays
    uniquely identifiable in the operator review log.
    """
    if not isinstance(smoke_id, str) or smoke_id == "":
        raise Stage27_7aHarnessError(
            "run_dry_run_smoke requires a non-empty smoke_id"
        )
    if output_root is None:
        raise Stage27_7aOutputRootError(
            "Stage 27.7a smoke harness requires an explicitly "
            "injected output_root; it never defaults to a "
            "production path"
        )
    if not isinstance(output_root, Path):
        raise Stage27_7aOutputRootError(
            "Stage 27.7a smoke harness requires a pathlib.Path "
            "output_root"
        )
    if not output_root.exists():
        raise Stage27_7aOutputRootError(
            f"Stage 27.7a smoke harness output_root does not "
            f"exist: {output_root!r}"
        )
    if not output_root.is_dir():
        raise Stage27_7aOutputRootError(
            f"Stage 27.7a smoke harness output_root is not a "
            f"directory: {output_root!r}"
        )

    chosen_clock = (
        clock if clock is not None else build_default_smoke_clock()
    )

    try:
        run_result: Stage27_6BoundedDryRunRunResult = (
            run_bounded_dry_run(
                events,
                sources,
                clock=chosen_clock,
                output_root=output_root,
                run_id=run_id,
                session_id=session_id,
                max_events=max_events,
                max_pings=max_pings,
                live_mode_authority=live_mode_authority,
                write_artifacts=write_artifacts,
                write_summary_artifact=write_summary_artifact,
                candidate_id_prefix=candidate_id_prefix,
                ping_id_prefix=ping_id_prefix,
                raise_on_live_refused=False,
            )
        )
    except Stage27_6RunnerBoundsError as exc:
        # Surface the Stage 27.6 bounds error as a typed Stage
        # 27.7a harness error so callers can branch on the smoke
        # boundary without importing Stage 27.6 errors.
        raise Stage27_7aHarnessError(
            f"Stage 27.7a smoke harness rejected by Stage 27.6 "
            f"bounds: {exc}"
        ) from exc

    smoke_summary = _project_smoke_summary(
        smoke_id=smoke_id,
        output_root=output_root,
        run_summary=run_result.summary,
        candidates=run_result.candidates,
    )

    return Stage27_7aDryRunSmokeResult(
        smoke_summary=smoke_summary,
        run_summary=run_result.summary,
        candidates=run_result.candidates,
    )


# ---------------------------------------------------------------------------
# Public surface re-export
# ---------------------------------------------------------------------------


__all__ = (
    "STAGE27_7A_MINOR_VERSION",
    "STAGE27_7A_SMOKE_SUMMARY_SCHEMA_VERSION",
    "DEFAULT_SMOKE_FIXED_UTC",
    "DEFAULT_SMOKE_FIXED_UTC_ISO",
    "DEFAULT_SMOKE_PRICE_STALENESS_THRESHOLD_SECONDS",
    "DEFAULT_SMOKE_MAX_EVENTS",
    "DEFAULT_SMOKE_CANDIDATE_ID_PREFIX",
    "DEFAULT_SMOKE_PING_ID_PREFIX",
    "FrozenSmokeRunnerClock",
    "Stage27_7aHarnessError",
    "Stage27_7aOutputRootError",
    "Stage27_7aSmokeSummaryRecord",
    "Stage27_7aDryRunSmokeResult",
    "build_default_smoke_sources",
    "build_default_smoke_clock",
    "build_default_smoke_events",
    "canonical_smoke_summary_json",
    "run_dry_run_smoke",
)
