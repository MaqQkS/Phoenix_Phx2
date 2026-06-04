"""Stage 30.11.9 mint-keyed migration evidence-source adapter.

The pure, offline EVIDENCE-SOURCE ADAPTER that fixes the narrowest blocker the Stage
30.11.8 controlled live ceremony surfaced: the committed Stage 30.11.8 confirmation
adapter consumes an INJECTED per-mint evidence source
(``lookup_migration_evidence(token_mint) -> evidence | None``), but NOTHING committed
implements that source over real, recorded migration evidence -- so the ceremony
could only inject a no-evidence source and every harvested candidate died at
``MISSING_MIGRATION_EVIDENCE``. This adapter IS that source: it answers exactly one
question for one token mint --

    given a candidate ``token_mint``
      + an INJECTED, offline / fake-first per-mint record PROVIDER (a callable
        ``provider(token_mint) -> records`` -- at the live ceremony, an out-of-repo
        operator wrapper over the committed Stage 29.5 migration-evidence reader /
        offline-integration projection; in this slice, a FAKE)
      -> pull THAT mint's sanitized evidence records (a missing / raising /
         non-callable provider fails closed to no-evidence)
      -> bind STRICTLY by mint: keep only a record whose own ``token_mint`` is
         non-blank AND equals the requested mint (so no candidate inherits another
         mint's evidence, even from a sloppy provider that returns extra records)
      -> collapse value-identical duplicates; require a single bound record (a missing
         match / a still-ambiguous set of DISTINCT records each fails closed)
      -> reject the bound record if its ``warnings`` field is MISSING or MALFORMED (a
         missing / ``None`` field, or anything but a well-formed tuple / list of
         strings); an absent or suspicious warnings value (e.g. an omitted field or the
         bare string ``"MIGRATION_STALE"``) fails closed to no-evidence BEFORE routing,
         because the Stage 30.11.8 confirmation reads a missing / non-collection
         warnings as NOT stale and would otherwise confirm a missing-or-malformed
         reading
      -> return the single, shape-validated bound record VERBATIM -- the sanitized
         ``Stage30_11_9MigrationEvidenceRecord`` the committed Stage 30.11.8
         confirmation reads duck-typed to confirm (or keep failing closed)

The adapter ONLY routes a record by mint and VALIDATES its warnings SHAPE; it NEVER
decides the migration verdict and NEVER decides staleness (the Stage 30.11.8
confirmation owns ``COMPLETE`` / ``SAFE`` / the trailing-Z anchor check AND the
``MIGRATION_STALE`` check -- a WELL-FORMED warnings carrying ``MIGRATION_STALE`` is
routed through and the confirmation blocks it as stale). It NEVER runs the Stage
30.11.8 confirmation / the Stage 30.11.7 enrichment / the Stage 30.11.6 projection /
the Stage 30.11.5 runner / the Stage 30.9.3 dip gate / a transport, NEVER fabricates
evidence (it carries the measurement status / redaction status / warnings / migration
anchor VERBATIM -- it never normalizes a non-trailing-Z anchor into a passing one,
never invents a redaction-safe claim, never empties a malformed warnings field, never
promotes an UNKNOWN reading), NEVER reserves a dispatch, NEVER calls a transport, and
NEVER sends a private message. It composes into the Stage 30.11.8 ``evidence_source``
seam directly: the committed Stage 30.11.8 adapter consumes a Stage 30.11.9 source
EXACTLY as it consumes its own injected fake evidence source -- so a candidate that
previously died at ``MISSING_MIGRATION_EVIDENCE`` reaches the confirmation, which
clears the MIGRATION dimension when (and only when) real evidence confirms it, while
the ATH / drawdown dimension the Stage 30.11.7 adapter checks LATER still
independently blocks transport.

The adapter also ships ``build_evidence_record_from_sanitized_projection`` -- a pure,
rename-only, fail-closed MAPPER that turns a sanitized Stage 29.5 migration-context
projection summary (the operator's out-of-repo adaptation input) into a
``Stage30_11_9MigrationEvidenceRecord`` (or ``None``). It maps the Stage 29.5
projection fields onto the Stage 30.11.8 evidence field names BY VALUE
(``measurement_status`` -> ``measurement_status``; ``migration_timestamp_utc`` ->
``migration_event_time_utc``; ``warnings`` -> ``warnings``; ``redaction_status`` ->
``redaction_status``; the candidate / join base mint -> ``token_mint``; the
matched-evidence source-event ref -> ``source_ref``) and carries each value VERBATIM,
with a fail-closed coercion that NEVER makes a bad value good: a non-string status /
anchor / ref / mint degrades to ``None`` (each fail-closed downstream), the anchor is
NEVER reformatted, and a MISSING / omitted / ``None`` ``warnings`` -- or any other
value that is not a well-formed tuple / list of strings (the bare string
``"MIGRATION_STALE"``, an int, a mapping, ...) -- makes the mapper return ``None`` (it
NEVER silently empties a missing / suspicious warnings field; a caller meaning "no
warnings" must pass an explicit ``()`` / ``[]``). So the mapper performs the
field-name adaptation the operator wrapper needs
WITHOUT fabricating anything, and the Stage 30.11.8 confirmation still independently
rejects a non-``COMPLETE`` / non-``SAFE`` / stale / non-trailing-Z reading.

The adapter NEVER fetches migration data, NEVER opens a network connection, NEVER
reads the process environment, NEVER calls ``datetime.now`` (every timestamp is
caller-injected / record-carried), NEVER touches the filesystem, and edits NO Stage
27 / Stage 28 / Stage 29 / Stage 30.3 / Stage 30.4 / Stage 30.11.5 / Stage 30.11.6 /
Stage 30.11.7 / Stage 30.11.8 production file. It composes ONLY the Stage 30.11.9
models sibling plus the INJECTED record provider; nothing more. In THIS slice the
injected provider is ALWAYS a FAKE -- the real Stage 29.5 reader plugs in at the
provider seam via an out-of-repo, operator-authorized wrapper.

Discipline:

  * Stdlib only (``typing``). NO ``re`` (the adapter never inspects the anchor SHAPE;
    a cleanup would let a bad timestamp pass, which is forbidden).
  * Imports ONLY the Stage 30.11.9 models sibling. No other PHX2 module; no Stage
    21-29 (incl. the nested Stage 27 / 28 / 29 live candidate record) / Stage 30.3 /
    Stage 30.4 orchestrator / Stage 28 suppression / live runner / provider /
    transport / Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7 / Stage 30.11.8 import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; timestamps are
    caller-injected / record-carried.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from PHX2.stage30.stage30_11_9_migration_evidence_source_models import (
    Stage30_11_9MigrationEvidenceRecord,
    is_nonblank_str,
)


# ---------------------------------------------------------------------------
# Injected record-provider boundary type (duck-typed; a FAKE in this slice)
# ---------------------------------------------------------------------------
#
# The injected record provider is a callable that, given the requested ``token_mint``,
# returns that mint's sanitized evidence record(s) -- a single record, an iterable of
# records, or ``None`` (no evidence). The adapter reads each returned record duck-typed
# (via attribute access / mapping ``get``), so a real out-of-repo provider may return
# any object carrying the documented ``token_mint`` / ``warnings`` attributes; a missing
# attribute reads as a blank mint / a missing warnings (both fail closed), and a raising
# / non-callable provider fails closed to no-evidence. In THIS slice the provider is
# ALWAYS a FAKE; the real Stage 29.5 reader plugs in at the operator-authorized
# ceremony.
Stage30_11_9MigrationEvidenceRecordProvider = Callable[[object], object]


# ---------------------------------------------------------------------------
# Pure field readers / shape validators
# ---------------------------------------------------------------------------


def _read_token_mint(record: object) -> object:
    """Read ``token_mint`` from ``record``.

    Pure / total; never raises. ``record`` may be a flat MAPPING (read via ``.get``)
    or any attribute-bearing object (read via ``getattr``). A missing key / attribute
    (or a non-mapping / non-object) yields ``None``. Mirrors the Stage 30.11.7 /
    30.11.8 ``_read_field`` discipline BY VALUE.
    """
    if isinstance(record, dict):
        return record.get("token_mint")
    return getattr(record, "token_mint", None)


def _read_warnings(record: object) -> object:
    """Read ``warnings`` from ``record`` (mapping ``.get`` or ``getattr``).

    Pure / total; never raises. A missing key / attribute (or a non-mapping /
    non-object) yields ``None`` -- which the shape validator below treats as malformed
    (fail closed), so a record that omits ``warnings`` is never routed.
    """
    if isinstance(record, dict):
        return record.get("warnings")
    return getattr(record, "warnings", None)


def _is_safe_warnings(value: object) -> bool:
    """Return ``True`` iff ``value`` is a WELL-FORMED warnings collection.

    Pure / total; never raises. Well-formed means a ``tuple`` or ``list`` whose every
    element is a ``str`` (an empty ``tuple`` / ``list`` is well-formed). This is a
    SHAPE check ONLY -- it deliberately does NOT decide staleness (the Stage 30.11.8
    confirmation owns the ``MIGRATION_STALE`` check), so a well-formed warnings that
    CARRIES ``MIGRATION_STALE`` is accepted here and blocked there.

    Everything else is MALFORMED and fails closed: ``None`` / a missing field, a bare
    string (e.g. ``"MIGRATION_STALE"`` -- NOT iterated character-by-character), an
    ``int``, a mapping, a ``set`` / ``frozenset``, or a ``tuple`` / ``list`` carrying
    a non-string element. A malformed warnings must never be silently emptied into a
    not-stale ``()``: the Stage 30.11.8 confirmation reads a non-collection warnings as
    not-stale and would otherwise confirm a stale-but-malformed reading.
    """
    if not isinstance(value, (tuple, list)):
        return False
    return all(isinstance(item, str) for item in value)


def _safe_provide(record_provider: object, token_mint: str) -> object:
    """Call ``record_provider(token_mint)`` inside a fail-closed guard; return its
    result, or ``None`` if the provider is ``None`` / not callable / raises.

    Pure apart from the injected provider's own behavior; never lets a provider
    exception escape (``KeyboardInterrupt`` / ``SystemExit`` -- ``BaseException`` --
    are NOT swallowed). A ``None`` / non-callable / raising provider yields ``None``
    -- a no-evidence signal the lookup then fails closed on. Mirrors the Stage
    30.11.8 ``_safe_lookup`` discipline BY VALUE.
    """
    if not callable(record_provider):
        return None
    try:
        return record_provider(token_mint)
    except Exception:
        return None


def _iter_records(raw: object) -> Tuple[object, ...]:
    """Normalize a provider return value into a tuple of candidate records.

    Pure / total; never raises. ``None`` -> ``()``. A bare ``str`` / ``bytes`` /
    ``bytearray`` / mapping is treated as a SINGLE record (never iterated
    element-by-element). Any other iterable is materialized into a tuple; a
    non-iterable single object (e.g. a dataclass record) becomes a one-tuple.
    """
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes, bytearray, dict)):
        return (raw,)
    try:
        return tuple(raw)
    except TypeError:
        return (raw,)


def _verbatim_str(value: object) -> Optional[str]:
    """Return ``value`` if it is a string (carried VERBATIM), else ``None``.

    Pure / total; never raises. The migration anchor / measurement status / redaction
    status / source ref / mint are each carried byte-for-byte when present as a string,
    and fail closed to ``None`` otherwise. NEVER normalizes / reformats the value (so a
    non-trailing-Z anchor is preserved EXACTLY and the Stage 30.11.8 confirmation --
    not Stage 30.11.9 -- rejects it).
    """
    return value if isinstance(value, str) else None


# ---------------------------------------------------------------------------
# Core mint-keyed selection (pure)
# ---------------------------------------------------------------------------


def _select_bound_record(
    record_provider: object, token_mint: str
) -> Optional[object]:
    """Pull the requested mint's records from the provider and return the single
    record bound to THAT mint with a WELL-FORMED warnings shape, or ``None``.

    Binds strictly by mint (a record whose own ``token_mint`` is non-blank AND equals
    ``token_mint``); collapses value-identical duplicates; requires a single bound
    record; then fails closed on a malformed warnings shape BEFORE routing. Returns
    the single shape-validated bound record, or ``None`` for a missing match, a set of
    DISTINCT conflicting records, or a record whose warnings is malformed.
    """
    raw = _safe_provide(record_provider, token_mint)
    matches: List[object] = []
    for record in _iter_records(raw):
        record_mint = _read_token_mint(record)
        if is_nonblank_str(record_mint) and record_mint == token_mint:
            if record not in matches:
                # Collapse value-identical duplicates; a DISTINCT second match makes
                # the set ambiguous (handled by the count check below).
                matches.append(record)
    if len(matches) != 1:
        return None
    bound = matches[0]
    # Fail closed on a malformed warnings shape BEFORE routing: a non-collection
    # warnings (e.g. the bare string "MIGRATION_STALE") is read as NOT stale by the
    # Stage 30.11.8 confirmation, so a suspicious warnings field must never reach it. A
    # well-formed warnings (incl. one CARRYING "MIGRATION_STALE") is routed and the
    # confirmation decides staleness.
    if not _is_safe_warnings(_read_warnings(bound)):
        return None
    return bound


def lookup_migration_evidence_in_provider(
    record_provider: object, token_mint: object
) -> Optional[object]:
    """Look up the single sanitized evidence record bound to ``token_mint`` in the
    injected ``record_provider``, or ``None``.

    Pure / deterministic apart from the injected provider's own behavior / total /
    no I/O, no provider network call, no env read, no wall-clock read. Never raises --
    a blank / non-string mint, a ``None`` / non-callable / raising provider, a
    malformed record, a no-match, a set of DISTINCT conflicting records, or a record
    with a malformed warnings shape all fail closed to ``None`` (the Stage 30.11.8
    confirmation then reports ``MISSING_MIGRATION_EVIDENCE``).

    Selection precedence (top-down, FIRST failing check wins):

      1. REQUESTED MINT -- ``token_mint`` must be a non-blank string. A blank /
         non-string mint -> ``None``.
      2. PROVIDER -- the provider must answer for THAT mint. A missing / non-callable
         / raising provider (or a ``None`` return) -> ``None``.
      3. MINT BINDING -- keep only a record whose own ``token_mint`` is non-blank AND
         equals the requested mint (no cross-mint inheritance, even from a provider
         that returns extra records). No bound record -> ``None``.
      4. UNAMBIGUOUS -- after collapsing value-identical duplicates, exactly ONE bound
         record must remain. Zero (missing) or two-or-more DISTINCT (conflicting)
         records -> ``None``.
      5. WARNINGS SHAPE -- the bound record's ``warnings`` must be a WELL-FORMED
         collection (a tuple / list of strings; empty is fine). A malformed warnings
         (``None`` / missing, a bare string such as ``"MIGRATION_STALE"``, an int, a
         mapping, a set, or a collection carrying a non-string element) -> ``None``;
         Stage 30.11.9 fails it closed BEFORE routing rather than letting the Stage
         30.11.8 confirmation read it as not-stale. A well-formed warnings carrying
         ``MIGRATION_STALE`` is NOT rejected here -- it is routed and the confirmation
         blocks it as stale.
      6. otherwise -> the single bound record, returned VERBATIM (Stage 30.11.9
         decides nothing about the migration verdict / staleness; the Stage 30.11.8
         confirmation judges the carried fields).
    """
    if not is_nonblank_str(token_mint):
        return None
    try:
        # ``token_mint`` is a non-blank str past the guard above.
        return _select_bound_record(record_provider, token_mint)
    except Exception:
        # Defensive: an exotic record ``__eq__`` (the only residual raise path) fails
        # closed to no-evidence. The provider call itself is already guarded.
        return None


# ---------------------------------------------------------------------------
# Public evidence-source adapter (the drop-in for the Stage 30.11.8 source seam)
# ---------------------------------------------------------------------------


class Stage30_11_9MigrationEvidenceSourceAdapter:
    """Mint-keyed migration evidence source over an injected record provider.

    The drop-in object the committed Stage 30.11.8 confirmation adapter's
    ``evidence_source`` seam consumes: it exposes
    ``lookup_migration_evidence(token_mint) -> record | None``, returning the single
    sanitized, warnings-shape-validated evidence record bound to that mint (or ``None``
    -> no evidence). The Stage 30.11.8 adapter reads the returned record duck-typed,
    requiring a bound, redaction-safe, on-chain ``COMPLETE``, fresh, valid trailing-Z
    reading to confirm.

    Construction is lenient (a non-callable provider is accepted and simply fails
    closed at lookup time) so the source can NEVER break the Stage 30.11.8 resolver.
    The adapter is non-raising on ``lookup_migration_evidence``: every failure (a
    blank mint, a raising provider, a malformed record, a no-match, a conflict, a
    malformed warnings shape) degrades to ``None``. It reserves no dispatch, calls no
    transport, sends no private message, writes no file, reads no env / clock /
    network, and NEVER constructs a runner / transport / dispatch sink -- so it can
    never reach a send surface. Producing a bound record is never a bypass of the
    committed Stage 30.11.8 confirmation / Stage 30.11.7 enrichment / Stage 30.11.6
    projection / Stage 30.11.5 runner / Stage 30.9.3 dip gate; the confirmation still
    judges the record (incl. staleness), and the Stage 30.11.7 adapter still checks
    the ATH / drawdown dimension LATER.
    """

    __slots__ = ("_record_provider",)

    def __init__(self, record_provider: object) -> None:
        self._record_provider = record_provider

    @property
    def record_provider(self) -> object:
        """Return the wrapped injected record provider."""
        return self._record_provider

    def lookup_migration_evidence(
        self, token_mint: object
    ) -> Optional[object]:
        """Return the single sanitized, warnings-shape-validated evidence record
        bound to ``token_mint``, or ``None``. Pure apart from the injected provider's
        behavior; never raises.
        """
        return lookup_migration_evidence_in_provider(
            self._record_provider, token_mint
        )


def build_migration_evidence_source(
    record_provider: object,
) -> Stage30_11_9MigrationEvidenceSourceAdapter:
    """Build a mint-keyed migration evidence source over the injected provider.

    The returned object is the drop-in the committed Stage 30.11.8 confirmation
    adapter's ``evidence_source`` seam consumes (it exposes
    ``lookup_migration_evidence``). Reserves no dispatch, calls no transport, sends no
    private message, writes no file, reads no env / clock / network.
    """
    return Stage30_11_9MigrationEvidenceSourceAdapter(record_provider)


# ---------------------------------------------------------------------------
# Public pure mapper: sanitized Stage 29.5 projection summary -> evidence record
# ---------------------------------------------------------------------------


def build_evidence_record_from_sanitized_projection(
    *,
    token_mint: object = None,
    measurement_status: object = None,
    migration_event_time_utc: object = None,
    warnings: object = None,
    redaction_status: object = None,
    source_ref: object = None,
) -> Optional[Stage30_11_9MigrationEvidenceRecord]:
    """Map a sanitized Stage 29.5 migration-context projection summary onto a
    ``Stage30_11_9MigrationEvidenceRecord`` by field-name rename + VERBATIM carry, or
    fail closed to ``None``.

    The operator's out-of-repo adaptation point: it maps the committed Stage 29.5
    private-ping projection summary fields onto the Stage 30.11.8 evidence field names
    BY VALUE -- the caller passes the Stage 29.5 ``measurement_status`` /
    ``migration_timestamp_utc`` / ``warnings`` / ``redaction_status`` (plus the
    candidate / join base mint and the matched-evidence source-event ref) under these
    kwargs, and the mapper renames ``migration_timestamp_utc`` -> the
    ``migration_event_time_utc`` slot and carries every value VERBATIM.

    Pure / total; never raises. FABRICATES nothing and NEVER cleans a bad value into a
    good one:

      * a non-string ``measurement_status`` / ``migration_event_time_utc`` /
        ``redaction_status`` / ``source_ref`` / ``token_mint`` degrades to ``None``
        (each fail-closed at the Stage 30.11.8 confirmation);
      * the migration anchor is carried byte-for-byte and is NEVER reformatted (so a
        non-trailing-Z / malformed anchor stays exactly as recorded and the Stage
        30.11.8 confirmation rejects it);
      * ``warnings`` is VALIDATED for shape and is REQUIRED: a WELL-FORMED warnings (a
        tuple / list of strings, empty allowed -- incl. one carrying
        ``MIGRATION_STALE``) is carried as a tuple; a MISSING / omitted / ``None``
        warnings, OR any other MALFORMED value (the bare string ``"MIGRATION_STALE"``,
        an int, a mapping, a set, or a collection with a non-string element) makes the
        mapper return ``None`` (it NEVER silently empties a missing / suspicious
        warnings field into a not-stale ``()``; a caller that means "no warnings" MUST
        pass an explicit ``()`` / ``[]``).

    So the mapper performs ONLY the safe rename + carry + shape validation; the Stage
    30.11.8 confirmation independently decides whether the record confirms (including
    blocking a well-formed ``MIGRATION_STALE`` reading). The ``warnings`` default is
    ``None`` (NOT ``()``), so an OMITTED warnings fails closed exactly like a ``None``
    one -- an absent field is malformed evidence, not "no warnings".
    """
    if not _is_safe_warnings(warnings):
        # A missing / malformed warnings field can never be mapped to confirmable
        # evidence: it fails closed here (the caller must pass an explicit () / []).
        return None
    return Stage30_11_9MigrationEvidenceRecord(
        token_mint=_verbatim_str(token_mint),
        measurement_status=_verbatim_str(measurement_status),
        migration_event_time_utc=_verbatim_str(migration_event_time_utc),
        warnings=tuple(warnings),
        redaction_status=_verbatim_str(redaction_status),
        source_ref=_verbatim_str(source_ref),
    )


__all__ = (
    "Stage30_11_9MigrationEvidenceRecordProvider",
    "lookup_migration_evidence_in_provider",
    "Stage30_11_9MigrationEvidenceSourceAdapter",
    "build_migration_evidence_source",
    "build_evidence_record_from_sanitized_projection",
)
