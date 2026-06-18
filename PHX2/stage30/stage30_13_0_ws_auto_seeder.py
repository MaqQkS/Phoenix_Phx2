"""Stage 30.13.0 bounded Helius WS auto-seeder.

The pure, bounded, fail-closed AUTO-SEEDER that turns bounded Helius WS discovery
output into automatically seeded candidates for the existing supervised monitor /
watchlist path -- the committed front-end that removes the LAST manual input the Stage
30.11.23 -> 30.11.22 chain still required (a hand-fed sanitized migration summary):

    an INJECTED discovery exposing ``read_migration_evidence_batch()`` (the committed
    Stage 29.5 ``Stage29_5HeliusWebSocketAdapter`` over a transport, or a fake)
      -> drive ONE bounded batch read inside a fail-closed guard -- a raise (a malformed
         capture / budget / transport / WS error) is a clean ``ERROR``
         (``WS_CAPTURE_FAILED``), seeds nothing, never escapes
      -> for each migration evidence record (a single BOUNDED for-loop; AT MOST
         ``max_seed``):
           -> not a ``Stage29_5MigrationEvidenceRecord``     -> ``ERROR`` (NOT_A_RECORD)
           -> ``migration_status`` != PRESENT                -> ``REJECTED`` (NOT_PRESENT_MIGRATION)
           -> base mint not a safe-shape pump-suffix mint    -> ``REJECTED`` (NOT_PUMP_SUFFIX)
           -> base mint already accepted this run            -> ``DUPLICATE`` (DUPLICATE_MINT)
           -> committed projection returns ``None``          -> ``REJECTED`` (INCOMPLETE_EVIDENCE)
           -> otherwise -> ``ACCEPTED``: the committed Stage 29.5.7 sanitized COMPLETE
              summary is accumulated into the seeded watchlist (SEEDED_FRESH_PUMP_MIGRATION)
      -> a redaction-safe ``Stage30_13AutoSeedResult`` (the ordered seed outcomes + the
         seeded summaries + the four-count summary + the combined redaction status)

The seeded summaries are EXACTLY the input the committed Stage 30.11.23
``build_real_fed_inputs_from_migration_evidence`` bridge consumes, so auto-seeding is a
drop-in front-end for the existing ``30.11.23 -> 30.11.22`` chain -- never a bypass of
it. The committed Stage 30.11.8 confirmation / Stage 30.11.7 enrichment / Stage 30.9.3
dip gate still judge every seeded summary downstream; this slice only DISCOVERS and
SEEDS, it never confirms, enriches, gates, composes, dedupes durably, or sends.

The auto-seeder NEVER opens a network connection (the discovery is INJECTED; the real
read-only socket transport behind the committed Stage 29.5 transport Protocol is a
SEPARATE, operator-authorized step), NEVER reads the process environment, NEVER reads a
wall clock (``created_at_utc`` is caller-injected), NEVER reserves a dispatch, NEVER
sends a private message, NEVER touches the durable one-send ledger, NEVER writes a file,
runs NO daemon / ``while`` loop, and edits NO Stage 29 / Stage 30.11 production file. It
composes ONLY the Stage 30.13.0 models sibling + the committed Stage 29.5 record type /
PRESENT token / closed-set error + the committed Stage 29.5.7 projection.

Discipline:

  * Stdlib only (``typing``).
  * Imports ONLY the Stage 30.13.0 models sibling + the committed Stage 29.5 migration
    models (``Stage29_5MigrationEvidenceRecord`` / ``MIGRATION_STATUS_PRESENT`` /
    ``Stage29_5MigrationEvidenceError``) + the committed Stage 29.5.7 projection
    (``project_migration_evidence_to_sanitized_summary``) -- the discovery currency
    Build #24 locked. No other Stage 21-29 import (no Birdeye, no Stage 27 / 28); no
    Stage 30.4.3 source; no transport / dispatch / runner import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket (the discovery is injected).
  * No database / SQLite, no compression, no default storage root, no durable ledger.
  * No live provider, transport-destination, url, or host reference; no wallet /
    signing / trading surface; no public / subscriber routing.
  * No PHX1 import. No ``time`` / ``datetime`` import; ``created_at_utc`` is
    caller-injected.
  * No module-level Call node (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceError,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage29.stage29_5_7_live_migration_evidence_producer import (
    project_migration_evidence_to_sanitized_summary,
)
from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    SEED_DECISION_ACCEPTED,
    SEED_DECISION_DUPLICATE,
    SEED_DECISION_ERROR,
    SEED_DECISION_REJECTED,
    SEED_REASON_DUPLICATE_MINT,
    SEED_REASON_INCOMPLETE_EVIDENCE,
    SEED_REASON_NOT_A_RECORD,
    SEED_REASON_NOT_PRESENT_MIGRATION,
    SEED_REASON_NOT_PUMP_SUFFIX,
    SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
    SEED_REASON_WS_CAPTURE_FAILED,
    STAGE30_13_DEFAULT_MAX_SEED,
    STAGE30_13_MAX_SEED_HARD_CAP,
    STAGE30_13_REDACTED_UNSAFE_ID,
    STAGE30_13_REDACTION_STATUS_REDACTED,
    STAGE30_13_REDACTION_STATUS_VIOLATION,
    Stage30_13AutoSeedResult,
    Stage30_13SeedOutcome,
    Stage30_13SeedSummary,
    is_pump_suffix_mint,
    is_safe_echo_id,
    is_within_seed_cap,
)


# ---------------------------------------------------------------------------
# Redaction self-scan needles (split-literal so this module source carries no bare
# needle -- in particular no bare provider name and no contiguous transport-scheme
# separator). Mirrors the committed Stage 30.11.23 / 30.11.22 scan BY VALUE.
# ---------------------------------------------------------------------------


_REDACTION_SCHEME_SEP: str = ":" + "/" + "/"
_REDACTION_NEEDLES: Tuple[str, ...] = (
    "disc" + "ord.com",
    "disc" + "ordapp.com",
    "/web" + "hooks/",
    "web" + "hook url",
    "ap" + "i_key",
    "ap" + "i key",
    "x-api-" + "key",
    "x-" + "token",
    "b" + "earer",
    "author" + "ization",
    "raw" + "_body",
    "response" + "_body",
    "head" + "ers",
    "public-api.bird" + "eye.so",
    "dex" + "screener.com",
    "chain" + "stack",
    "hel" + "ius",
)


# ---------------------------------------------------------------------------
# Module-local exception (caller-shape failure)
# ---------------------------------------------------------------------------


class Stage30_13AutoSeedError(Exception):
    """Closed-set Stage 30.13.0 auto-seed error.

    Raised ONLY for a caller-shape failure the auto-seeder cannot run with -- a
    ``max_seed`` that is not a positive ``int`` within the HARD seed cap
    (``1 <= max_seed <= STAGE30_13_MAX_SEED_HARD_CAP``): an out-of-bounds seed budget
    would make the bounded seed undefined, so the auto-seeder fails closed BEFORE
    driving the injected discovery. Degraded per-record inputs never raise; a raising
    discovery / a non-record / a non-PRESENT / a non-pump / an incomplete record fails
    closed to a clean ``ERROR`` / ``REJECTED`` / ``DUPLICATE`` outcome. Carries only a
    closed-set reason token; never a raw payload or any secret value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.13.0 auto-seed error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Pure safe-shape helper
# ---------------------------------------------------------------------------


def _safe_echo(value: object) -> str:
    """Echo ``value`` only when it is a safe-echo token; else a safe placeholder.

    ``None`` / ``""`` -> ``""``; a non-string or an unsafe string ->
    ``STAGE30_13_REDACTED_UNSAFE_ID``; a safe-echo token -> itself. Mirrors the committed
    Stage 30.11.23 ``_safe_echo`` BY VALUE. Pure / total.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return STAGE30_13_REDACTED_UNSAFE_ID
    if value == "":
        return ""
    return value if is_safe_echo_id(value) else STAGE30_13_REDACTED_UNSAFE_ID


# ---------------------------------------------------------------------------
# Pure per-outcome builder
# ---------------------------------------------------------------------------


def _outcome(
    *,
    token_mint_echo: str,
    seed_decision: str,
    seed_reason: str,
    created_at_utc: str,
) -> Stage30_13SeedOutcome:
    """Build one seed outcome echoing a safe-shape mint with the given closed-set
    decision / reason. Pure; no I/O.
    """
    return Stage30_13SeedOutcome(
        token_mint=token_mint_echo,
        seed_decision=seed_decision,
        seed_reason=seed_reason,
        created_at_utc=created_at_utc,
    )


# ---------------------------------------------------------------------------
# Redaction self-scan over the seed outcomes
# ---------------------------------------------------------------------------


def _outcome_text_fields(outcome: Stage30_13SeedOutcome) -> Tuple[str, ...]:
    """Return the string-typed fields of one seed outcome (the haystack)."""
    return (
        outcome.token_mint,
        outcome.seed_decision,
        outcome.seed_reason,
        outcome.created_at_utc,
    )


def _outcomes_redaction_safe(
    outcomes: Tuple[Stage30_13SeedOutcome, ...]
) -> bool:
    """Return ``True`` iff no seed-outcome string field carries a transport-scheme
    separator or a forbidden url / secret needle. Pure / total.
    """
    for outcome in outcomes:
        for text in _outcome_text_fields(outcome):
            if not isinstance(text, str):
                continue
            lowered = text.lower()
            if _REDACTION_SCHEME_SEP in lowered:
                return False
            for needle in _REDACTION_NEEDLES:
                if needle in lowered:
                    return False
    return True


# ---------------------------------------------------------------------------
# Public bounded auto-seeder
# ---------------------------------------------------------------------------


def build_seeded_watchlist_from_ws_discovery(
    discovery: object,
    *,
    created_at_utc: str,
    max_seed: int = STAGE30_13_DEFAULT_MAX_SEED,
) -> Stage30_13AutoSeedResult:
    """Drive ONE bounded Helius WS discovery batch and auto-seed AT MOST ``max_seed``
    fresh pump-suffix migrated mints into a seeded watchlist.

    ``discovery`` is any object exposing ``read_migration_evidence_batch()`` returning
    an iterable of ``Stage29_5MigrationEvidenceRecord`` (the committed Stage 29.5
    ``Stage29_5HeliusWebSocketAdapter`` over a transport at the ceremony, a fake in the
    proofs). The auto-seeder calls it ONCE inside a fail-closed guard.

    Pure / deterministic apart from the injected discovery's own behavior; reads no env,
    no clock, no network (``created_at_utc`` is injected); reserves no dispatch, sends no
    message, writes no file, touches no durable ledger, runs no daemon / ``while`` loop.

    Fail closed first: if ``max_seed`` is not a positive ``int`` within the HARD cap the
    auto-seeder raises ``Stage30_13AutoSeedError`` BEFORE driving the discovery.

    Then it reads ONE bounded batch inside a guard -- a raise (a malformed capture /
    budget / transport / WS error) is a clean ``ERROR`` (``WS_CAPTURE_FAILED``) that
    seeds nothing and never escapes -- and classifies AT MOST ``max_seed`` records via
    the decision ladder (not-a-record / not-present / not-pump / duplicate / incomplete /
    accepted), projecting each ACCEPTED record to its committed Stage 29.5.7 sanitized
    COMPLETE summary via ``project_migration_evidence_to_sanitized_summary``. It tallies
    the four counts and self-scans its own seed-outcome strings for redaction.

    ``KeyboardInterrupt`` / ``SystemExit`` (``BaseException``) are NOT swallowed.
    """
    if not is_within_seed_cap(max_seed):
        # Fail closed on an out-of-bounds seed budget: drive nothing, seed nothing.
        raise Stage30_13AutoSeedError("INVALID_MAX_SEED")

    outcomes: List[Stage30_13SeedOutcome] = []
    seeded_summaries: List[object] = []
    seen_mints: set = set()
    records_seen = 0
    accepted = 0
    rejected = 0
    duplicate = 0
    error = 0

    # ---- Drive ONE bounded discovery batch inside a fail-closed guard ----
    #
    # Stage 30.13.4 hardening: NEVER materialize the caller-provided iterable in full.
    # The old ``records = list(batch)`` would exhaust an arbitrarily large / lazy /
    # unbounded discovery BEFORE any cap applied. Instead pull AT MOST ``process_cap``
    # items by hand -- a LOCAL hard processing cap that is never greater than the Stage
    # 30 seed ceiling (``STAGE30_13_MAX_SEED_HARD_CAP``) -- so an unbounded discovery is
    # advanced at most ``process_cap`` times and the seeder always stops boundedly. A
    # non-iterable batch, a lazy iterator that raises mid-stream, or any other
    # discovery / transport fault still fails closed to a clean WS-capture error.
    process_cap = min(max_seed, STAGE30_13_MAX_SEED_HARD_CAP)
    records: Optional[List[object]] = None
    try:
        batch = discovery.read_migration_evidence_batch()
        iterator = iter(batch)
        collected: List[object] = []
        for _ in range(process_cap):
            try:
                item = next(iterator)
            except StopIteration:
                break
            collected.append(item)
        records = collected
    except Stage29_5MigrationEvidenceError:
        records = None
    except Exception:
        # Any other discovery / transport fault is ALSO a clean fail-closed capture
        # error (a real socket transport may raise a non-Stage-29.5 error, a custom
        # batch may not be iterable, or a lazy iterator may raise mid-stream). The
        # committed Stage 29.5 adapter raises only Stage29_5MigrationEvidenceError; a
        # custom / real transport may not.
        records = None
    if records is None:
        # The batch read failed closed: one batch-level ERROR outcome, no seed, no
        # record "seen". records_seen stays 0.
        outcomes.append(
            _outcome(
                token_mint_echo="",
                seed_decision=SEED_DECISION_ERROR,
                seed_reason=SEED_REASON_WS_CAPTURE_FAILED,
                created_at_utc=created_at_utc,
            )
        )
        error += 1
    else:
        for record in records:
            if records_seen >= max_seed:
                break
            records_seen += 1

            # ---- not a migration evidence record ----
            if not isinstance(record, Stage29_5MigrationEvidenceRecord):
                outcomes.append(
                    _outcome(
                        token_mint_echo="",
                        seed_decision=SEED_DECISION_ERROR,
                        seed_reason=SEED_REASON_NOT_A_RECORD,
                        created_at_utc=created_at_utc,
                    )
                )
                error += 1
                continue

            mint_echo = _safe_echo(record.base_mint)

            # ---- not a PRESENT migration ----
            if record.migration_status != MIGRATION_STATUS_PRESENT:
                outcomes.append(
                    _outcome(
                        token_mint_echo=mint_echo,
                        seed_decision=SEED_DECISION_REJECTED,
                        seed_reason=SEED_REASON_NOT_PRESENT_MIGRATION,
                        created_at_utc=created_at_utc,
                    )
                )
                rejected += 1
                continue

            # ---- not a safe-shape pump-suffix mint ----
            if not is_pump_suffix_mint(record.base_mint):
                outcomes.append(
                    _outcome(
                        token_mint_echo=mint_echo,
                        seed_decision=SEED_DECISION_REJECTED,
                        seed_reason=SEED_REASON_NOT_PUMP_SUFFIX,
                        created_at_utc=created_at_utc,
                    )
                )
                rejected += 1
                continue

            # ``record.base_mint`` is a safe-shape pump-suffix string past this point.
            base_mint = record.base_mint

            # ---- duplicate mint (first-wins) ----
            if base_mint in seen_mints:
                outcomes.append(
                    _outcome(
                        token_mint_echo=mint_echo,
                        seed_decision=SEED_DECISION_DUPLICATE,
                        seed_reason=SEED_REASON_DUPLICATE_MINT,
                        created_at_utc=created_at_utc,
                    )
                )
                duplicate += 1
                continue

            # ---- incomplete evidence (committed projection fails closed to None) ----
            summary = project_migration_evidence_to_sanitized_summary(record)
            if summary is None:
                outcomes.append(
                    _outcome(
                        token_mint_echo=mint_echo,
                        seed_decision=SEED_DECISION_REJECTED,
                        seed_reason=SEED_REASON_INCOMPLETE_EVIDENCE,
                        created_at_utc=created_at_utc,
                    )
                )
                rejected += 1
                continue

            # ---- accepted: seed the committed sanitized COMPLETE summary ----
            seen_mints.add(base_mint)
            seeded_summaries.append(summary)
            outcomes.append(
                _outcome(
                    token_mint_echo=mint_echo,
                    seed_decision=SEED_DECISION_ACCEPTED,
                    seed_reason=SEED_REASON_SEEDED_FRESH_PUMP_MIGRATION,
                    created_at_utc=created_at_utc,
                )
            )
            accepted += 1

    summary_tally = Stage30_13SeedSummary(
        records_seen=records_seen,
        accepted=accepted,
        rejected=rejected,
        duplicate=duplicate,
        error=error,
        created_at_utc=created_at_utc,
    )
    redaction_status = (
        STAGE30_13_REDACTION_STATUS_REDACTED
        if _outcomes_redaction_safe(tuple(outcomes))
        else STAGE30_13_REDACTION_STATUS_VIOLATION
    )
    return Stage30_13AutoSeedResult(
        outcomes=tuple(outcomes),
        seeded_summaries=tuple(seeded_summaries),
        summary=summary_tally,
        redaction_status=redaction_status,
        created_at_utc=created_at_utc,
    )


__all__ = (
    "Stage30_13AutoSeedError",
    "build_seeded_watchlist_from_ws_discovery",
)
