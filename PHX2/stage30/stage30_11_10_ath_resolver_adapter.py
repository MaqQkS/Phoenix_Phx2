"""Stage 30.11.10 real ATH-resolver bridge adapter.

The pure, offline ATH-RESOLVER ADAPTER that fixes the narrowest blocker the ATH
blocker audit surfaced: the committed Stage 30.11.7 enrichment adapter checks an ATH
dimension LAST, requiring its injected ``ath_resolver`` to return a resolution that is
``present is True`` AND ``fresh is True`` AND ``post_migration_ath_verified is True``
with a finite-coercible ``drawdown_from_ath`` -- but the only committed thing that
produces that exact shape is a FAKE ATH resolver. The real post-migration drawdown
brain (the committed Stage 27.4 ``read_ath_context`` / ``_compute_drawdown`` /
``AthContextRecord``, fed by the committed Stage 29.2 Birdeye ATH + current-price
sources) already EXISTS, but nothing maps its output into the Stage 30.11.7 ATH
resolver seam. This adapter IS that map. It answers exactly one question for one
candidate / token mint --

    given a harvested / flat base candidate (a flat MAPPING / dict OR an
    attribute-bearing object carrying the candidate ``token_mint``)
      + an INJECTED migration RESOLVER (the committed Stage 30.11.8-style migration
        resolver -- it supplies the CONFIRMED migration anchor; at the live ceremony,
        the real Stage 30.11.8 ``build_migration_resolver`` over a Stage 30.11.9
        evidence source; in this slice, a FAKE)
      + an INJECTED ATH CONTEXT SOURCE (a per-mint reader exposing
        ``read_ath_context(token_mint, *, migration_event_time_utc) -> reading | None``
        -- at the live ceremony, an out-of-repo operator wrapper over the committed
        Stage 27.4 ``read_ath_context`` wired to the committed Stage 29.2 Birdeye ATH +
        current-price sources, building the Stage 27.4 migration record from the
        confirmed anchor; in this slice, a FAKE)
      -> read the base's ``token_mint`` (a blank / missing mint fails closed)
      -> obtain THAT mint's CONFIRMED migration anchor from the migration resolver (a
         missing / unconfirmed / anchorless verdict fails closed -- the audit's
         "missing migration anchor")
      -> read THAT mint's committed ATH reading from the source, passing the confirmed
         anchor through (a non-callable / raising / nothing-returning source fails
         closed)
      -> bind STRICTLY by mint (a reading bound to a DIFFERENT mint is never inherited)
      -> map the committed reading onto the Stage 30.11.7 ATH resolver contract:
         ``present`` / ``fresh`` from ``ath_status == PRESENT``,
         ``post_migration_ath_verified`` from BOTH ``ath_since_migration_status ==
         POST_MIGRATION_ONLY`` AND ``drawdown_basis == FROM_POST_MIGRATION_ATH`` (both
         required; the window status required outright), ``drawdown_from_ath`` carried
         VERBATIM (NEVER recomputed) -- failing closed (with a precise reason) on every
         stale / pre-migration / window-inconsistent / missing-drawdown reading
      -> a ``Stage30_11_10AthResolution`` whose ``present`` / ``fresh`` /
         ``post_migration_ath_verified`` / ``drawdown_from_ath`` the committed Stage
         30.11.7 adapter reads to clear (or keep failing) the ATH dimension

The adapter ONLY maps a committed ATH reading onto the resolver contract; it
RECOMPUTES no drawdown (the committed Stage 27.4 ``_compute_drawdown`` owns that), and
it deliberately does NOT use the Stage 30.7 sanitized-ATH display bridge as the
runtime resolver -- the Stage 30.7 bridge emits operator DISPLAY text (e.g. a
``$Y`` / ``Unknown`` rendering) and explicitly does NOT recompute / re-expose the
drawdown magnitude, so it is the WRONG shape for the Stage 30.11.7 resolver seam. It
NEVER runs the Stage 30.11.7 enrichment / the Stage 30.11.6 projection / the Stage
30.11.5 runner / the Stage 30.9.3 dip gate / a transport, NEVER decides dip
eligibility, NEVER fabricates an ATH (a missing / unavailable / stale / pre-migration
/ malformed / wrong-mint reading each fails closed and can NEVER become a resolved
ATH), NEVER reserves a dispatch, NEVER calls a transport, and NEVER sends a live
message. It composes into the Stage 30.11.7 ``ath_resolver`` seam via
:func:`build_ath_resolver`, which returns a duck-typed callable the committed Stage
30.11.7 adapter consumes EXACTLY as it consumes its own injected fake ATH resolver --
so a candidate that previously died at the ATH dimension (only a fake could clear it)
clears it when (and only when) a real committed reading verifies a post-migration ATH
with a drawdown, while the dip gate the committed Stage 30.9.3 / 30.10.1 stack runs
LATER still independently decides eligibility.

IMPORTANT honesty note: the committed dip gate consumes ``drawdown_from_ath`` as a
finite-decimal PRESENCE check, not a depth threshold. This slice does NOT change that
-- it only makes the ATH / drawdown real enough for the Stage 30.11.7 ATH dimension to
clear and reach the dip gate. Depth-based dip filtering, if ever desired, is a
SEPARATE gate-change stage.

The adapter NEVER fetches ATH data, NEVER opens a network connection, NEVER reads the
process environment, NEVER calls ``datetime.now`` (every timestamp is caller-injected
/ reading-carried), and edits NO Stage 27 / Stage 28 / Stage 29 / Stage 30.3 / Stage
30.4 / Stage 30.7 / Stage 30.11.5 / Stage 30.11.6 / Stage 30.11.7 / Stage 30.11.8 /
Stage 30.11.9 production file. It composes ONLY the Stage 30.11.10 models sibling plus
the INJECTED migration resolver + ATH context source; nothing more. In THIS slice both
injected dependencies are ALWAYS FAKES -- the real Stage 30.11.8 migration resolver +
the real Stage 27.4 / Stage 29.2 ATH reader plug in at the operator-authorized
ceremony.

Discipline:

  * Stdlib only (``typing``). NO ``decimal`` (the slice never coerces / recomputes the
    drawdown -- it carries the committed ``drawdown_from_ath`` VERBATIM and the
    committed Stage 30.11.7 enrichment coerces it). NO ``re``, NO ``time`` /
    ``datetime``.
  * Imports ONLY the Stage 30.11.10 models sibling. No other PHX2 module; no Stage
    21-29 (incl. the nested Stage 27 / 28 / 29 live candidate record) / Stage 30.3 /
    Stage 30.4 orchestrator / Stage 28 suppression / live runner / provider /
    transport / Stage 30.7 display bridge / Stage 30.11.5 / Stage 30.11.6 / Stage
    30.11.7 / Stage 30.11.8 / Stage 30.11.9 import.
  * No ``os.environ`` / ``os.getenv`` access; no env read.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No database / SQLite, no zstd / compression, no default storage root.
  * No live provider, transport-destination, or request-metadata reference.
  * No PHX1 import. No ``time`` / ``datetime`` import; timestamps are caller-injected.
"""

from __future__ import annotations

from typing import Callable

from PHX2.stage30.stage30_11_10_ath_resolver_models import (
    ATH_DECISION_RESOLVED,
    ATH_DECISION_UNRESOLVED,
    ATH_REASON_ATH_MINT_MISMATCH,
    ATH_REASON_ATH_NOT_PRESENT,
    ATH_REASON_ATH_SOURCE_ERROR,
    ATH_REASON_ATH_SOURCE_UNAVAILABLE,
    ATH_REASON_BLANK_CANDIDATE_MINT,
    ATH_REASON_MISSING_ATH_SOURCE,
    ATH_REASON_MISSING_DRAWDOWN,
    ATH_REASON_MISSING_MIGRATION_ANCHOR,
    ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
    ATH_REASON_RESOLVED_POST_MIGRATION_ATH,
    STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY,
    STAGE30_11_10_ATH_STATUS_PRESENT,
    STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH,
    Stage30_11_10AthResolution,
    is_nonblank_str,
)


# ---------------------------------------------------------------------------
# Injected boundary types (duck-typed; FAKES in this slice)
# ---------------------------------------------------------------------------
#
# ``migration_resolver`` -- a callable that, given the base candidate, returns ONE
# migration resolution carrier (or ``None``) exposing ``confirmed`` (must be ``True``)
# and ``migration_event_time_utc`` (the confirmed anchor; must be a non-blank string).
# This is exactly the Stage 30.11.8 ``build_migration_resolver`` return shape, read
# duck-typed -- the adapter imports no Stage 30.11.8 module.
#
# ``ath_context_source`` -- an object exposing a single method,
# ``read_ath_context(token_mint, *, migration_event_time_utc) -> reading | None``,
# returning the committed Stage 27.4 ``AthContextRecord``-shaped reading bound to that
# mint (or ``None`` -> no reading). The adapter reads the returned reading duck-typed
# (via attribute access), so a real out-of-repo source may return a real Stage 27.4
# ``AthContextRecord``; a missing attribute reads as the fail-closed value, and a
# raising / non-callable source fails closed.
Stage30_11_10MigrationResolver = Callable[[object], object]
Stage30_11_10AthContextSource = object
Stage30_11_10AthResolver = Callable[[object], Stage30_11_10AthResolution]


# ---------------------------------------------------------------------------
# Pure field readers / guards
# ---------------------------------------------------------------------------


def _read_field(source: object, key: str) -> object:
    """Read field ``key`` from ``source``.

    Pure / total; never raises. ``source`` may be a flat MAPPING (read via ``.get``)
    or any attribute-bearing object (read via ``getattr``). A missing key / attribute
    (or a non-mapping / non-object) yields ``None``. Mirrors the Stage 30.11.7 /
    30.11.8 / 30.11.9 ``_read_field`` discipline BY VALUE.
    """
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _safe_resolve_migration(migration_resolver: object, base: object) -> object:
    """Call ``migration_resolver(base)`` inside a fail-closed guard; return its
    result, or ``None`` if it is not callable or raises.

    Pure apart from the injected resolver's own behavior; never lets a resolver
    exception escape (``KeyboardInterrupt`` / ``SystemExit`` -- ``BaseException`` --
    are NOT swallowed). A non-callable / raising migration resolver yields ``None`` --
    a missing migration anchor the resolver then fails closed on. Mirrors the Stage
    30.11.7 ``_safe_resolve`` discipline BY VALUE.
    """
    if not callable(migration_resolver):
        return None
    try:
        return migration_resolver(base)
    except Exception:
        return None


def _verbatim_str_or_none(value: object):
    """Return ``value`` if it is a string, else ``None``.

    Pure / total; never raises. The committed reading's ``ath_source`` is carried onto
    the resolution as provenance ``source_ref`` ONLY when it is a string; a non-string
    label fails closed to ``None`` (never fabricated).
    """
    return value if isinstance(value, str) else None


# ---------------------------------------------------------------------------
# Pure result builder
# ---------------------------------------------------------------------------


def _unresolved(
    *,
    reason: str,
    token_mint: str,
    present: bool = False,
    fresh: bool = False,
    post_migration_ath_verified: bool = False,
    drawdown_from_ath: object = None,
    source_ref=None,
) -> Stage30_11_10AthResolution:
    """Build an ``UNRESOLVED_ATH`` resolution carrying a precise reason + the echoed
    candidate mint.

    Pure; no I/O. By default every gate-facing field fails closed (``present`` /
    ``fresh`` / ``post_migration_ath_verified`` ``False``; ``drawdown_from_ath``
    ``None``), so the committed Stage 30.11.7 adapter rejects it at the FIRST ATH
    check (``MISSING_ATH``). The ``present`` / ``fresh`` / ``post_migration_ath_verified``
    / ``drawdown_from_ath`` overrides exist ONLY so a reading that IS present (or
    present + post-migration) but fails a LATER check carries those earlier-true
    booleans through, so the committed Stage 30.11.7 adapter rejects at the PRECISE
    matching dimension (``PRE_MIGRATION_ATH_NOT_VERIFIED`` / ``INVALID_DRAWDOWN``)
    rather than the generic first one.
    """
    return Stage30_11_10AthResolution(
        present=present,
        fresh=fresh,
        post_migration_ath_verified=post_migration_ath_verified,
        drawdown_from_ath=drawdown_from_ath,
        token_mint=token_mint,
        decision=ATH_DECISION_UNRESOLVED,
        reason=reason,
        source_ref=source_ref,
    )


# ---------------------------------------------------------------------------
# Public ATH resolver (per candidate)
# ---------------------------------------------------------------------------


def resolve_candidate_ath(
    base: object,
    *,
    migration_resolver: object,
    ath_context_source: object,
) -> Stage30_11_10AthResolution:
    """Resolve ONE candidate's ATH verdict against the injected migration resolver +
    ATH context source, returning a ``Stage30_11_10AthResolution``.

    Pure / deterministic apart from the injected dependencies' own behavior / total /
    no I/O, no provider call, no live send, no env read, no wall-clock read. Never
    raises for a malformed base / resolver / source -- a non-mapping / non-object base,
    a ``None`` / raising / non-conforming dependency, or a malformed reading all fail
    closed to an ``UNRESOLVED_ATH`` resolution. ALWAYS returns a resolution (never
    ``None``), so the ATH outcome is total and talliable.

    Resolution precedence (top-down, FIRST failing check wins):

      1. CANDIDATE MINT -- the base must carry a non-blank ``token_mint``. A blank /
         missing mint -> ``BLANK_CANDIDATE_MINT``.
      2. MIGRATION ANCHOR -- the migration resolver must return a verdict with
         ``confirmed is True`` AND a non-blank ``migration_event_time_utc`` (the Stage
         30.11.8-confirmed anchor). A missing / unconfirmed / anchorless verdict ->
         ``MISSING_MIGRATION_ANCHOR`` (the resolver never reads ATH without a confirmed
         migration -- a post-migration claim is void without one).
      3. ATH SOURCE -- the source must expose a callable ``read_ath_context``. A
         non-callable / absent method -> ``MISSING_ATH_SOURCE``; a raising call ->
         ``ATH_SOURCE_ERROR``; a ``None`` return -> ``ATH_SOURCE_UNAVAILABLE``.
      4. MINT BINDING -- the reading must be bound to the SAME mint (its ``token_mint``
         non-blank AND equal the base mint). A mismatched / blank reading mint ->
         ``ATH_MINT_MISMATCH`` (no cross-mint inheritance; a malformed reading with no
         readable mint fails here too).
      5. ATH PRESENCE -- the committed reading's ``ath_status`` must be ``PRESENT``. A
         STALE / UNAVAILABLE / SOURCE_ERROR / NOT_APPLICABLE / UNSUPPORTED_PAIR /
         missing status -> ``ATH_NOT_PRESENT``.
      6. POST-MIGRATION -- the committed reading must carry BOTH
         ``ath_since_migration_status == POST_MIGRATION_ONLY`` AND ``drawdown_basis ==
         FROM_POST_MIGRATION_ATH`` (the committed Stage 27.4 brain sets the basis ONLY
         inside the POST_MIGRATION_ONLY branch, so an honest reading carries both; a
         duck-typed / injected reading can DECOUPLE them). Since this slice bridges
         Stage 27.4, ``ath_since_migration_status`` is required OUTRIGHT -- a missing /
         inconsistent / non-exact window status, or any other basis ->
         ``PRE_MIGRATION_ATH_NOT_VERIFIED``.
      7. DRAWDOWN PRESENCE -- the committed reading must carry a non-``None``
         ``drawdown_from_ath``. A missing drawdown -> ``MISSING_DRAWDOWN`` (the
         resolution still carries ``present`` + ``fresh`` + ``post_migration_ath_verified``
         ``True`` with a ``None`` drawdown, so the committed Stage 30.11.7 adapter
         rejects at its precise ``INVALID_DRAWDOWN`` check).
      8. otherwise -> ``RESOLVED_ATH`` / ``RESOLVED_POST_MIGRATION_ATH`` with the
         mapped ``present`` / ``fresh`` / ``post_migration_ath_verified`` ``True`` and
         the committed drawdown carried VERBATIM.

    The resolution FABRICATES nothing: ``present`` / ``fresh`` are ``True`` ONLY for a
    committed ``ath_status == PRESENT``; ``post_migration_ath_verified`` is ``True``
    ONLY for a committed ``ath_since_migration_status == POST_MIGRATION_ONLY`` AND
    ``drawdown_basis == FROM_POST_MIGRATION_ATH`` (both required; the window status is
    required outright); the drawdown is carried VERBATIM (NEVER recomputed). Candidate
    identity (the echoed ``token_mint``) is preserved on every resolution.
    """
    # ---- 1. Candidate mint: a non-blank token, else fail closed ----
    base_mint = _read_field(base, "token_mint")
    if not is_nonblank_str(base_mint):
        return _unresolved(
            reason=ATH_REASON_BLANK_CANDIDATE_MINT, token_mint=""
        )
    # ``base_mint`` is a non-blank str past this guard.
    candidate_mint: str = base_mint  # type: ignore[assignment]

    # ---- 2. Migration anchor: a confirmed Stage 30.11.8 verdict + anchor ----
    migration = _safe_resolve_migration(migration_resolver, base)
    if migration is None or _read_field(migration, "confirmed") is not True:
        return _unresolved(
            reason=ATH_REASON_MISSING_MIGRATION_ANCHOR,
            token_mint=candidate_mint,
        )
    anchor = _read_field(migration, "migration_event_time_utc")
    if not is_nonblank_str(anchor):
        return _unresolved(
            reason=ATH_REASON_MISSING_MIGRATION_ANCHOR,
            token_mint=candidate_mint,
        )

    # ---- 3. ATH source: a callable reader that answers for THIS mint ----
    read_method = getattr(ath_context_source, "read_ath_context", None)
    if not callable(read_method):
        return _unresolved(
            reason=ATH_REASON_MISSING_ATH_SOURCE, token_mint=candidate_mint
        )
    try:
        reading = read_method(
            candidate_mint, migration_event_time_utc=anchor
        )
    except Exception:
        return _unresolved(
            reason=ATH_REASON_ATH_SOURCE_ERROR, token_mint=candidate_mint
        )
    if reading is None:
        return _unresolved(
            reason=ATH_REASON_ATH_SOURCE_UNAVAILABLE,
            token_mint=candidate_mint,
        )

    # ---- 4. Mint binding: the reading must be bound to the SAME mint ----
    reading_mint = _read_field(reading, "token_mint")
    if not is_nonblank_str(reading_mint) or reading_mint != candidate_mint:
        return _unresolved(
            reason=ATH_REASON_ATH_MINT_MISMATCH, token_mint=candidate_mint
        )

    # ---- 5. ATH presence: ONLY a committed PRESENT reading is present / fresh ----
    ath_status = _read_field(reading, "ath_status")
    present = ath_status == STAGE30_11_10_ATH_STATUS_PRESENT
    fresh = ath_status == STAGE30_11_10_ATH_STATUS_PRESENT
    if not present:
        return _unresolved(
            reason=ATH_REASON_ATH_NOT_PRESENT, token_mint=candidate_mint
        )

    # ---- 6. Post-migration: require BOTH a committed POST_MIGRATION_ONLY window AND a
    #         FROM_POST_MIGRATION_ATH basis (the committed Stage 27.4 brain sets the
    #         basis ONLY inside the POST_MIGRATION_ONLY branch, so an honest reading
    #         carries both; a duck-typed / injected reading can DECOUPLE them, so the
    #         resolver requires BOTH and -- since this slice bridges Stage 27.4 --
    #         requires ``ath_since_migration_status`` OUTRIGHT, never accepting an
    #         omitted / inconsistent / non-exact value) ----
    ath_since_migration_status = _read_field(
        reading, "ath_since_migration_status"
    )
    drawdown_basis = _read_field(reading, "drawdown_basis")
    post_migration_ath_verified = (
        ath_since_migration_status
        == STAGE30_11_10_ATH_SINCE_MIGRATION_STATUS_POST_MIGRATION_ONLY
        and drawdown_basis
        == STAGE30_11_10_DRAWDOWN_BASIS_FROM_POST_MIGRATION_ATH
    )
    source_ref = _verbatim_str_or_none(_read_field(reading, "ath_source"))
    if not post_migration_ath_verified:
        # Present + fresh ride through so the committed Stage 30.11.7 adapter rejects at
        # its precise PRE_MIGRATION_ATH_NOT_VERIFIED check (a missing / inconsistent
        # ``ath_since_migration_status`` and a non-post-migration basis BOTH land here).
        return _unresolved(
            reason=ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED,
            token_mint=candidate_mint,
            present=present,
            fresh=fresh,
            source_ref=source_ref,
        )

    # ---- 7. Drawdown presence: the committed reading must carry a drawdown ----
    drawdown_from_ath = _read_field(reading, "drawdown_from_ath")
    if drawdown_from_ath is None:
        # Present + fresh + post-migration ride through so the committed Stage 30.11.7
        # adapter rejects at its precise INVALID_DRAWDOWN check.
        return _unresolved(
            reason=ATH_REASON_MISSING_DRAWDOWN,
            token_mint=candidate_mint,
            present=present,
            fresh=fresh,
            post_migration_ath_verified=post_migration_ath_verified,
            drawdown_from_ath=drawdown_from_ath,
            source_ref=source_ref,
        )

    # ---- 8. Resolved: map the committed reading onto the resolver contract ----
    #
    # The drawdown is carried VERBATIM from the committed Stage 27.4 reading (NEVER
    # recomputed); the committed Stage 30.11.7 enrichment coerces / validates it to a
    # finite Decimal (and the committed dip gate later reads it as a finite-decimal
    # PRESENCE check, unchanged by this slice).
    return Stage30_11_10AthResolution(
        present=present,
        fresh=fresh,
        post_migration_ath_verified=post_migration_ath_verified,
        drawdown_from_ath=drawdown_from_ath,
        token_mint=candidate_mint,
        decision=ATH_DECISION_RESOLVED,
        reason=ATH_REASON_RESOLVED_POST_MIGRATION_ATH,
        source_ref=source_ref,
    )


# ---------------------------------------------------------------------------
# Public resolver factory (the drop-in for the Stage 30.11.7 ATH seam)
# ---------------------------------------------------------------------------


def build_ath_resolver(
    *,
    migration_resolver: object,
    ath_context_source: object,
) -> Stage30_11_10AthResolver:
    """Build a duck-typed ATH resolver over the injected migration resolver + ATH
    context source.

    The returned callable is the drop-in object the committed Stage 30.11.7 enrichment
    adapter's ``ath_resolver`` seam consumes: given a base candidate it returns a
    ``Stage30_11_10AthResolution`` whose ``present`` / ``fresh`` /
    ``post_migration_ath_verified`` / ``drawdown_from_ath`` the Stage 30.11.7 adapter
    reads (requiring all of ``present is True`` / ``fresh is True`` /
    ``post_migration_ath_verified is True`` + a finite-coercible drawdown to clear the
    ATH dimension). The closure holds both dependencies and looks up each base
    candidate's OWN ``token_mint`` -- so no candidate inherits another mint's ATH.

    Pure apart from the injected dependencies' behavior; reserves no dispatch, calls no
    transport, sends no live message, writes no file, reads no env / clock / network,
    and NEVER constructs a runner / transport / dispatch sink -- so it can never reach a
    send surface. Producing a resolved ATH is never a bypass of the committed Stage
    30.11.7 enrichment / Stage 30.11.6 projection / Stage 30.11.5 runner / Stage 30.9.3
    dip gate; the committed dip gate still decides eligibility LATER.
    """

    def _resolver(base: object) -> Stage30_11_10AthResolution:
        return resolve_candidate_ath(
            base,
            migration_resolver=migration_resolver,
            ath_context_source=ath_context_source,
        )

    return _resolver


__all__ = (
    "Stage30_11_10MigrationResolver",
    "Stage30_11_10AthContextSource",
    "Stage30_11_10AthResolver",
    "resolve_candidate_ath",
    "build_ath_resolver",
)
