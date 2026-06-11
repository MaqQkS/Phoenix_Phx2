"""Stage 30.11.23 discovered migration-evidence -> candidate + evidence bridge adapter.

The pure, bounded, fail-closed ADAPTER that removes the LAST manual input the Stage
30.11.22 real-fed dry run required (a hand-fed candidate mint + migration anchor): it
derives BOTH the discovered candidate AND its mint-keyed migration evidence from ONE
committed Stage 29.5.7 sanitized migration-evidence summary, so the operator never
types ``CURATED_MINT`` / ``CURATED_MIGRATION_TIME_UTC`` and the two sides can never
desync:

    an iterable of Stage 29.5.7 sanitized migration-evidence summaries (read
    DUCK-TYPED: ``token_mint`` / ``measurement_status`` / ``migration_event_time_utc``
    / ``warnings`` / ``redaction_status`` / ``source_ref`` -- the Stage 29 type is
    NEVER imported)
      -> for each summary (a single BOUNDED for-loop; AT MOST ``max_summaries``):
           -> Layer-0 routing hygiene: a usable safe-shape ``token_mint`` -> a
              non-duplicate mint (first-wins) -> a present migration anchor -> a
              COMPLETE measurement -> a SAFE redaction -> well-formed warnings -> a
              buildable evidence record (via the committed Stage 30.11.9
              ``build_evidence_record_from_sanitized_projection``). Every gate that
              fails yields a precise ``SKIPPED_*`` decision and NEITHER a candidate NOR
              an evidence record. These COMPLETE / SAFE screens MIRROR but NEVER
              replace the committed Stage 30.11.8 confirmation -- migration
              confirmation still belongs downstream.
           -> on pass: a ``Stage30_11_23DiscoveredCandidate`` (carrying the validated
              ``token_mint``) is accumulated into the ``events`` stream AND a
              ``Stage30_11_9MigrationEvidenceRecord`` is accumulated into the mint-keyed
              ``{mint: record}`` map
           -> a redaction-safe per-summary ``Stage30_11_23BridgeEvent``
      -> the mint-keyed map is wrapped into a committed Stage 30.11.9 evidence source
         via ``build_migration_evidence_source(provider)``
      -> a ``Stage30_11_23RealFedInputs`` bundle (the discovered-candidate ``events``,
         the trivial assembler, the placeholder flattener, the mint-keyed evidence
         source, and the embedded bridge report) -- the four values the committed Stage
         30.11.22 ``run_stage30_11_22_real_fed_dry_run`` takes injected

The MAPPING is exact and fabricates nothing: the summary's ``token_mint`` feeds BOTH
the candidate ``token_mint`` AND the evidence ``token_mint`` (the same string, so the
committed Stage 30.11.8 confirmation -- which keys the evidence lookup off the
candidate mint -- always finds the matching record); ``migration_event_time_utc`` /
``measurement_status`` / ``warnings`` / ``redaction_status`` / ``source_ref`` ride
VERBATIM into the evidence record (via the committed Stage 30.11.9 mapper, which the
adapter REUSES rather than constructing the record directly). The ``source_ref`` lives
ONLY on the evidence record (never echoed into a bridge event); the candidate-side
``source_ref`` is ``None``.

The candidate flows through the COMMITTED Stage 30.11.6 harvest seam (driven by the
committed Stage 30.11.22 wrapper): the trivial assembler returns the discovered
identity and the flattener fills the Stage 30.11.5 flat-projection shape with INERT
placeholders on every field the committed Stage 30.11.22 bridge discards (it reads
ONLY ``token_mint`` + ``candidate_id`` and stamps its own ``PENDING_ENRICHMENT`` /
``PENDING`` sentinels). So no placeholder ever reaches the composer -- it is a
shape-satisfier required by the committed projection contract, not data.

The adapter NEVER fetches migration / market data, NEVER opens a network connection,
NEVER reads the process environment, NEVER reads a wall clock (``created_at_utc`` is
caller-injected), NEVER reserves a dispatch / performs a send, NEVER sends a private
message, NEVER calls the Stage 30.11.16 real-send guard, NEVER constructs a real
provider / WebSocket / RPC client, NEVER writes a file, runs NO daemon / ``while``
loop, and edits NO harvest / enrichment / composer / dedupe / ledger / evidence-source
file. It composes ONLY the Stage 30.11.23 models sibling + the committed Stage 30.11.9
evidence-source mapper / builder. The real Stage 29.5.7 migration-evidence producer (an
out-of-repo capture), the real-fed dry-run ceremony, and the controlled capped private
send remain a SEPARATE, operator-authorized step this slice does not build.

Discipline:

  * Stdlib only (``typing``).
  * Imports ONLY the Stage 30.11.23 models sibling + the committed Stage 30.11.9
    migration evidence-source adapter (``build_evidence_record_from_sanitized_projection``
    + ``build_migration_evidence_source``). No other PHX2 module; no Stage 21-29 (incl.
    the Stage 29.5.7 summary type -- read duck-typed) / Stage 30.4.3 source / Stage
    30.11.11 ATH source / Stage 30.11.16 real-send guard import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; ``created_at_utc`` is
    caller-injected.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PHX2.stage30.stage30_11_9_migration_evidence_source_adapter import (
    build_evidence_record_from_sanitized_projection,
    build_migration_evidence_source,
)
from PHX2.stage30.stage30_11_23_migration_evidence_candidate_bridge_models import (
    BRIDGE_DECISION_BRIDGED,
    BRIDGE_DECISION_SKIPPED_DUPLICATE_MINT,
    BRIDGE_DECISION_SKIPPED_EVIDENCE_UNBUILDABLE,
    BRIDGE_DECISION_SKIPPED_INVALID_TOKEN_MINT,
    BRIDGE_DECISION_SKIPPED_MALFORMED_WARNINGS,
    BRIDGE_DECISION_SKIPPED_MISSING_MIGRATION_TIME,
    BRIDGE_DECISION_SKIPPED_MISSING_TOKEN_MINT,
    BRIDGE_DECISION_SKIPPED_NOT_A_SUMMARY,
    BRIDGE_DECISION_SKIPPED_NOT_COMPLETE_MEASUREMENT,
    BRIDGE_DECISION_SKIPPED_UNSAFE_REDACTION,
    STAGE30_11_23_DEFAULT_MAX_SUMMARIES,
    STAGE30_11_23_EXPECTED_MEASUREMENT_STATUS,
    STAGE30_11_23_EXPECTED_REDACTION_STATUS,
    STAGE30_11_23_MAX_SUMMARIES_HARD_CAP,
    STAGE30_11_23_PLACEHOLDER_DECIMAL,
    STAGE30_11_23_PLACEHOLDER_STATUS,
    STAGE30_11_23_REDACTED_UNSAFE_ID,
    STAGE30_11_23_REDACTION_STATUS_REDACTED,
    STAGE30_11_23_REDACTION_STATUS_VIOLATION,
    Stage30_11_23AssembledCandidate,
    Stage30_11_23BridgeEvent,
    Stage30_11_23BridgeReport,
    Stage30_11_23DiscoveredCandidate,
    Stage30_11_23RealFedInputs,
    is_nonblank_str,
    is_safe_echo_id,
)


# ---------------------------------------------------------------------------
# Redaction self-scan needles (split-literal so this module source carries no bare
# needle -- in particular no bare provider name). Mirrors the committed Stage 30.11.22
# / 30.11.21 scan BY VALUE.
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


class Stage30_11_23BridgeError(Exception):
    """Closed-set Stage 30.11.23 bridge error.

    Raised ONLY for a caller-shape failure the bridge cannot run with -- a
    ``max_summaries`` that is not a positive ``int`` within the HARD summary-scan cap
    (``1 <= max_summaries <= STAGE30_11_23_MAX_SUMMARIES_HARD_CAP``): an out-of-bounds
    scan budget would make the bounded scan undefined, so the bridge fails closed
    BEFORE reading any summary. Degraded per-summary inputs never raise; a non-summary
    / missing field / malformed warnings fails closed to a clean ``SKIPPED_*``
    decision. Carries only a closed-set reason token; never a raw payload or any secret
    value.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 30.11.23 bridge error: reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Bounded-scan config helper
# ---------------------------------------------------------------------------


def is_within_summaries_cap(max_summaries: object) -> bool:
    """Return ``True`` iff ``max_summaries`` is a positive ``int`` within the HARD
    summary-scan cap (``1 <= max_summaries <= STAGE30_11_23_MAX_SUMMARIES_HARD_CAP``).

    Pure / TOTAL; never raises. A non-int, a ``bool`` (``True`` / ``False`` are not
    budgets), a non-positive value, or a value above the hard cap fails closed to
    ``False`` -- so a scan can never be parameterized to discover more candidates than
    the committed Stage 30.11.6 / 30.11.17 ``<= 10`` ceilings allow.
    """
    if isinstance(max_summaries, bool):
        return False
    if not isinstance(max_summaries, int):
        return False
    return 1 <= max_summaries <= STAGE30_11_23_MAX_SUMMARIES_HARD_CAP


# ---------------------------------------------------------------------------
# Pure duck-typed summary readers / safe-shape helpers
# ---------------------------------------------------------------------------


def _read(summary: object, key: str) -> object:
    """Read field ``key`` from ``summary``.

    Pure / total; never raises. ``summary`` may be a flat MAPPING (read via ``.get``)
    or any attribute-bearing object (read via ``getattr``). A missing key / attribute
    (or a non-mapping / non-object) yields ``None``. The adapter reads ONLY the six
    documented Stage 29.5.7 sanitized-summary field names -- never importing the Stage
    29 type. Mirrors the Stage 30.11.9 ``_read_token_mint`` discipline BY VALUE.
    """
    if isinstance(summary, dict):
        return summary.get(key)
    return getattr(summary, key, None)


def _looks_like_summary(summary: object) -> bool:
    """Return ``True`` iff ``summary`` could be a sanitized migration-evidence summary.

    Pure / total; never raises. A ``None`` or a bare scalar (``str`` / ``bytes`` /
    ``bytearray`` / ``int`` / ``float`` / ``bool``) is NOT a summary -- it fails closed
    to ``SKIPPED_NOT_A_SUMMARY``. A mapping or any other attribute-bearing object is
    treated as a (possibly malformed) summary and its fields are read + validated.
    """
    if summary is None:
        return False
    if isinstance(summary, (str, bytes, bytearray, int, float, bool)):
        return False
    return True


def _is_safe_warnings(value: object) -> bool:
    """Return ``True`` iff ``value`` is a WELL-FORMED warnings collection.

    Pure / total; never raises. Well-formed means a ``tuple`` or ``list`` whose every
    element is a ``str`` (an empty ``tuple`` / ``list`` is well-formed). Mirrors the
    committed Stage 30.11.9 ``_is_safe_warnings`` BY VALUE so the bridge can emit a
    PRECISE ``SKIPPED_MALFORMED_WARNINGS`` decision BEFORE the committed Stage 30.11.9
    mapper (which would otherwise fail closed to ``None`` and surface only as the
    residual ``SKIPPED_EVIDENCE_UNBUILDABLE``). A SHAPE check ONLY -- it does NOT decide
    staleness (the committed Stage 30.11.8 confirmation owns ``MIGRATION_STALE``); a
    well-formed warnings CARRYING ``MIGRATION_STALE`` is bridged and blocked downstream.
    """
    if not isinstance(value, (tuple, list)):
        return False
    return all(isinstance(item, str) for item in value)


def _safe_echo(value: object) -> str:
    """Echo ``value`` only when it is a safe-echo token; else a safe placeholder.

    ``None`` / ``""`` -> ``""``; a non-string or an unsafe string ->
    ``STAGE30_11_23_REDACTED_UNSAFE_ID``; a safe-echo token -> itself. Mirrors the
    committed Stage 30.11.22 ``_safe_echo`` BY VALUE. Pure / total.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        return STAGE30_11_23_REDACTED_UNSAFE_ID
    if value == "":
        return ""
    return value if is_safe_echo_id(value) else STAGE30_11_23_REDACTED_UNSAFE_ID


# ---------------------------------------------------------------------------
# Trivial committed harvest front-end (assembler + placeholder flattener)
# ---------------------------------------------------------------------------


class Stage30_11_23DiscoveredCandidateAssembler:
    """Trivial committed assembler for migration-discovered candidates.

    A structural match for the committed Stage 30.11.6 ``Stage30_11_6CandidateAssembler``
    protocol (a single ``assemble(normalized_event, *, candidate_id) -> object``). The
    "assembly" of a migration-discovered candidate is IDENTITY: the discovered mint IS
    the candidate identity, so this reads the discovered ``token_mint`` from the event
    and pairs it with the run-scoped ``candidate_id`` the committed Stage 30.11.6
    harvest loop stamped. It reaches NO dispatch / transport / runner surface and
    imports no Stage 30.11.6 type (the event is read duck-typed).
    """

    __slots__ = ()

    def assemble(
        self, normalized_event: object, *, candidate_id: str
    ) -> Stage30_11_23AssembledCandidate:
        """Return the assembled discovered candidate. Pure; no I/O."""
        token_mint = _read(normalized_event, "token_mint")
        return Stage30_11_23AssembledCandidate(
            token_mint=token_mint if isinstance(token_mint, str) else "",
            candidate_id=candidate_id,
        )


class Stage30_11_23DiscoveredCandidateFlattener:
    """Committed placeholder flattener for assembled discovered candidates.

    A structural match for the committed Stage 30.11.6 ``Stage30_11_6RecordFlattener``
    callable. It flattens an assembled discovered candidate into the committed Stage
    30.11.5 flat-projection field shape, carrying ``token_mint`` + ``candidate_id``
    VERBATIM and stamping INERT placeholders on every field the committed Stage 30.11.22
    bridge discards. The decimal fields take the numeric ``STAGE30_11_23_PLACEHOLDER_DECIMAL``
    (the committed Stage 30.11.6 projection requires a finite-``Decimal``-coercible
    value); the status fields take ``STAGE30_11_23_PLACEHOLDER_STATUS``; ``source_ref``
    is ``None`` (the discovered ``source_ref`` lives ONLY on the evidence record, never
    on the candidate). It holds the caller-injected ``created_at_utc`` so the flat
    projection's timestamp is shape-valid (the committed Stage 30.11.22 bridge overwrites
    it anyway). It fetches nothing, reads no clock / env / network.
    """

    __slots__ = ("_created_at_utc",)

    def __init__(self, created_at_utc: str) -> None:
        self._created_at_utc: str = created_at_utc

    def __call__(self, record: object) -> Dict[str, object]:
        """Return the flat Stage 30.11.5-shaped projection dict. Pure; no I/O."""
        token_mint = _read(record, "token_mint")
        candidate_id = _read(record, "candidate_id")
        return {
            "candidate_id": candidate_id,
            "token_mint": token_mint,
            "pair_type": STAGE30_11_23_PLACEHOLDER_STATUS,
            "tier_hint": STAGE30_11_23_PLACEHOLDER_STATUS,
            "drawdown_from_ath": STAGE30_11_23_PLACEHOLDER_DECIMAL,
            "migration_status": STAGE30_11_23_PLACEHOLDER_STATUS,
            "ath_status": STAGE30_11_23_PLACEHOLDER_STATUS,
            "market_context_status": STAGE30_11_23_PLACEHOLDER_STATUS,
            "current_market_cap_usd": STAGE30_11_23_PLACEHOLDER_DECIMAL,
            "post_migration_ath_verified": None,
            "source_ref": None,
            "created_at_utc": self._created_at_utc,
        }


# ---------------------------------------------------------------------------
# Mint-keyed evidence provider (the committed Stage 30.11.9 source's record provider)
# ---------------------------------------------------------------------------


class Stage30_11_23MintKeyedEvidenceProvider:
    """Callable ``token_mint -> single evidence record | None`` over a frozen map.

    The committed Stage 30.11.9 ``build_migration_evidence_source`` wraps this into the
    ``lookup_migration_evidence`` source the committed Stage 30.11.8 confirmation
    consumes. The bridge accumulated EXACTLY one record per mint (first-wins dedupe), so
    the committed Stage 30.11.9 source's "single bound record" check passes. A
    non-string mint or an absent mint returns ``None`` (no evidence -> the committed
    confirmation reports ``MISSING_MIGRATION_EVIDENCE``). It reserves no dispatch, calls
    no transport, reads no env / clock / network.
    """

    __slots__ = ("_records_by_mint",)

    def __init__(self, records_by_mint: Dict[str, object]) -> None:
        self._records_by_mint: Dict[str, object] = dict(records_by_mint)

    def __call__(self, token_mint: object) -> Optional[object]:
        """Return the single record bound to ``token_mint``, or ``None``. Pure."""
        if not isinstance(token_mint, str):
            return None
        return self._records_by_mint.get(token_mint)


# ---------------------------------------------------------------------------
# Pure per-summary bridge (Layer-0 routing hygiene + evidence build)
# ---------------------------------------------------------------------------


def _bridge_one_summary(
    summary: object, seen_mints: set
) -> Tuple[str, str, Optional[object]]:
    """Bridge ONE sanitized migration-evidence summary.

    Returns ``(decision, token_mint, evidence_record)``. Pure / total; never raises.
    Decision ladder (top-down, FIRST failing check wins):

      1. NOT A SUMMARY    -- a ``None`` / bare scalar -> ``SKIPPED_NOT_A_SUMMARY``.
      2. MINT PRESENCE    -- ``token_mint`` must be a non-blank string -> else
                             ``SKIPPED_MISSING_TOKEN_MINT``.
      3. MINT SHAPE       -- ``token_mint`` must be a safe-echo token -> else
                             ``SKIPPED_INVALID_TOKEN_MINT``.
      4. DUPLICATE        -- a mint already bridged this batch (first-wins) ->
                             ``SKIPPED_DUPLICATE_MINT``.
      5. ANCHOR PRESENCE  -- ``migration_event_time_utc`` must be a non-blank string ->
                             else ``SKIPPED_MISSING_MIGRATION_TIME`` (the committed
                             Stage 30.11.8 owns the trailing-Z / staleness checks).
      6. MEASUREMENT      -- ``measurement_status`` must equal ``COMPLETE`` (Layer-0
                             routing hygiene; mirrors -- never replaces -- the committed
                             Stage 30.11.8) -> else ``SKIPPED_NOT_COMPLETE_MEASUREMENT``.
      7. REDACTION        -- ``redaction_status`` must equal ``SAFE`` -> else
                             ``SKIPPED_UNSAFE_REDACTION``.
      8. WARNINGS SHAPE   -- ``warnings`` must be a well-formed tuple / list of str ->
                             else ``SKIPPED_MALFORMED_WARNINGS``.
      9. EVIDENCE BUILD   -- the committed Stage 30.11.9 mapper must build a record ->
                             else ``SKIPPED_EVIDENCE_UNBUILDABLE`` (defensive residual;
                             the warnings pre-check covers the only reachable None path).
      10. otherwise -> ``BRIDGED_CANDIDATE_AND_EVIDENCE`` with the bound record.

    The COMPLETE / SAFE screens MIRROR but NEVER replace the committed Stage 30.11.8
    confirmation: every bridged record carries ``measurement_status`` /
    ``redaction_status`` / ``migration_event_time_utc`` / ``warnings`` VERBATIM, and the
    committed Stage 30.11.8 / Stage 30.11.21 chain re-checks all of them. The returned
    ``token_mint`` is used ONLY for the (safe-echo'd) bridge event EXCEPT on a BRIDGED
    decision, where the caller binds it (a safe-echo token) into ``seen_mints`` + the
    mint-keyed map.
    """
    if not _looks_like_summary(summary):
        return BRIDGE_DECISION_SKIPPED_NOT_A_SUMMARY, "", None

    token_mint = _read(summary, "token_mint")
    if not is_nonblank_str(token_mint):
        return BRIDGE_DECISION_SKIPPED_MISSING_TOKEN_MINT, "", None
    if not is_safe_echo_id(token_mint):
        # Carry the raw (unsafe) value so the caller can safe-echo it to
        # REDACTED_UNSAFE_ID on the event; it is NEVER bound into the map.
        return (
            BRIDGE_DECISION_SKIPPED_INVALID_TOKEN_MINT,
            token_mint,  # type: ignore[return-value]
            None,
        )
    # ``token_mint`` is a safe-echo string past this point.
    if token_mint in seen_mints:
        return BRIDGE_DECISION_SKIPPED_DUPLICATE_MINT, token_mint, None

    migration_event_time_utc = _read(summary, "migration_event_time_utc")
    if not is_nonblank_str(migration_event_time_utc):
        return BRIDGE_DECISION_SKIPPED_MISSING_MIGRATION_TIME, token_mint, None

    measurement_status = _read(summary, "measurement_status")
    if measurement_status != STAGE30_11_23_EXPECTED_MEASUREMENT_STATUS:
        return (
            BRIDGE_DECISION_SKIPPED_NOT_COMPLETE_MEASUREMENT,
            token_mint,
            None,
        )

    redaction_status = _read(summary, "redaction_status")
    if redaction_status != STAGE30_11_23_EXPECTED_REDACTION_STATUS:
        return BRIDGE_DECISION_SKIPPED_UNSAFE_REDACTION, token_mint, None

    warnings = _read(summary, "warnings")
    if not _is_safe_warnings(warnings):
        return BRIDGE_DECISION_SKIPPED_MALFORMED_WARNINGS, token_mint, None

    # Reuse the committed Stage 30.11.9 mapper (rename-only, VERBATIM carry, shape
    # validation). The summary already carries the post-rename field names, so this is a
    # straight pass-through. The mapper fails closed to None only on malformed warnings
    # (pre-checked above) -- the residual guard keeps this ladder total.
    source_ref = _read(summary, "source_ref")
    record = build_evidence_record_from_sanitized_projection(
        token_mint=token_mint,
        measurement_status=measurement_status,
        migration_event_time_utc=migration_event_time_utc,
        warnings=warnings,
        redaction_status=redaction_status,
        source_ref=source_ref,
    )
    if record is None:
        return BRIDGE_DECISION_SKIPPED_EVIDENCE_UNBUILDABLE, token_mint, None

    return BRIDGE_DECISION_BRIDGED, token_mint, record


# ---------------------------------------------------------------------------
# Redaction self-scan over the bridge events
# ---------------------------------------------------------------------------


def _event_text_fields(event: Stage30_11_23BridgeEvent) -> Tuple[str, ...]:
    """Return the string-typed fields of one bridge event (the haystack)."""
    return (event.decision, event.token_mint, event.created_at_utc)


def _bridge_events_redaction_safe(
    events: Tuple[Stage30_11_23BridgeEvent, ...]
) -> bool:
    """Return ``True`` iff no bridge-event string field carries a transport-scheme
    separator or a forbidden url / secret needle. Pure / total.
    """
    for event in events:
        for text in _event_text_fields(event):
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
# Public bounded bridge
# ---------------------------------------------------------------------------


def build_real_fed_inputs_from_migration_evidence(
    summaries: object,
    *,
    created_at_utc: str,
    max_summaries: int = STAGE30_11_23_DEFAULT_MAX_SUMMARIES,
) -> Stage30_11_23RealFedInputs:
    """Bridge an iterable of sanitized migration-evidence summaries into the four
    inputs the committed Stage 30.11.22 real-fed dry-run wrapper takes injected.

    Pure / deterministic / total / no I/O, no provider call, no Discord send, no env
    read, no wall-clock read (``created_at_utc`` is caller-injected). Never raises for a
    malformed summary -- a non-summary / missing field / malformed warnings / duplicate
    mint all fail closed to a clean ``SKIPPED_*`` bridge event.

    Fail closed first: if ``max_summaries`` is not a positive ``int`` within the HARD
    cap the bridge raises ``Stage30_11_23BridgeError`` BEFORE reading any summary.

    Otherwise it scans AT MOST ``max_summaries`` summaries (a single BOUNDED for-loop),
    and for each: bridges it via :func:`_bridge_one_summary`, records a redaction-safe
    ``Stage30_11_23BridgeEvent``, and on ``BRIDGED`` accumulates a
    ``Stage30_11_23DiscoveredCandidate`` into the ``events`` stream + the bound
    ``Stage30_11_9MigrationEvidenceRecord`` into the mint-keyed map. The map is wrapped
    into a committed Stage 30.11.9 evidence source. Returns the
    ``Stage30_11_23RealFedInputs`` bundle (events + assembler + flattener + evidence
    source + the embedded bridge report). The candidate stream and the evidence source
    are derived from the SAME summaries, so they are guaranteed consistent.
    """
    if not is_within_summaries_cap(max_summaries):
        # Fail closed on an out-of-bounds scan budget: read nothing, bridge nothing.
        raise Stage30_11_23BridgeError("INVALID_MAX_SUMMARIES")

    bridge_events: List[Stage30_11_23BridgeEvent] = []
    discovered: List[Stage30_11_23DiscoveredCandidate] = []
    records_by_mint: Dict[str, object] = {}
    seen_mints: set = set()
    summaries_seen = 0
    bridged = 0

    for summary in summaries:
        if summaries_seen >= max_summaries:
            break
        index = summaries_seen
        summaries_seen += 1

        decision, token_mint, record = _bridge_one_summary(summary, seen_mints)
        bridge_events.append(
            Stage30_11_23BridgeEvent(
                index=index,
                decision=decision,
                token_mint=_safe_echo(token_mint),
                created_at_utc=created_at_utc,
            )
        )
        if decision == BRIDGE_DECISION_BRIDGED and record is not None:
            bridged += 1
            seen_mints.add(token_mint)
            records_by_mint[token_mint] = record
            discovered.append(
                Stage30_11_23DiscoveredCandidate(token_mint=token_mint)
            )

    skipped = summaries_seen - bridged

    evidence_source = build_migration_evidence_source(
        Stage30_11_23MintKeyedEvidenceProvider(records_by_mint)
    )

    redaction_status = (
        STAGE30_11_23_REDACTION_STATUS_REDACTED
        if _bridge_events_redaction_safe(tuple(bridge_events))
        else STAGE30_11_23_REDACTION_STATUS_VIOLATION
    )
    report = Stage30_11_23BridgeReport(
        bridge_events=tuple(bridge_events),
        summaries_seen=summaries_seen,
        bridged=bridged,
        skipped=skipped,
        redaction_status=redaction_status,
        created_at_utc=created_at_utc,
    )
    return Stage30_11_23RealFedInputs(
        events=tuple(discovered),
        assembler=Stage30_11_23DiscoveredCandidateAssembler(),
        record_flattener=Stage30_11_23DiscoveredCandidateFlattener(
            created_at_utc
        ),
        evidence_source=evidence_source,
        report=report,
    )


__all__ = (
    "Stage30_11_23BridgeError",
    "is_within_summaries_cap",
    "Stage30_11_23DiscoveredCandidateAssembler",
    "Stage30_11_23DiscoveredCandidateFlattener",
    "Stage30_11_23MintKeyedEvidenceProvider",
    "build_real_fed_inputs_from_migration_evidence",
)
