"""Stage 30.11.10 real ATH-resolver adapter tests.

Proves the Stage 30.11.10 ATH-resolver adapter:

  * RESOLVES only a real reading -- a for-this-mint, ATH ``PRESENT``,
    ``FROM_POST_MIGRATION_ATH`` reading carrying a drawdown -> ``present`` + ``fresh`` +
    ``post_migration_ath_verified`` ``True`` with the committed drawdown carried VERBATIM
    (never recomputed) + the source label as provenance;
  * FAILS CLOSED, with a PRECISE reason, on every blank-mint / missing-anchor /
    missing-source / source-error / unavailable-source / cross-mint / not-present /
    pre-migration / missing-drawdown reading -- never fabricating, never inheriting
    another mint's ATH;
  * threads the CONFIRMED migration anchor through to the ATH source and never reads the
    ATH source without a confirmed anchor;
  * maps ``present`` and ``fresh`` from the SAME ``ath_status == PRESENT`` token (Stage
    27.4 collapses staleness into a DISTINCT STALE status);
  * is TOTAL -- a malformed base / resolver / source / reading never raises.

Pure / offline. No live call, no provider, no private send, no env read. The Stage
30.11.10 PRODUCTION adapter imports only its own models sibling.
"""

from __future__ import annotations

from PHX2.stage30.stage30_11_10_ath_resolver_adapter import (
    build_ath_resolver,
    resolve_candidate_ath,
)
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
    Stage30_11_10AthContextRecord,
)


_VALID_ANCHOR = "2026-05-27T00:00:00Z"
_MINT = "mint-x"


# ---------------------------------------------------------------------------
# Local test doubles (the injected migration resolver + ATH context source)
# ---------------------------------------------------------------------------


class _Migration:
    def __init__(self, confirmed=True, anchor=_VALID_ANCHOR):
        self.confirmed = confirmed
        self.migration_event_time_utc = anchor
        self.token_mint = _MINT
        self.source_ref = "mig-ref"


def _confirming_resolver(base):
    return _Migration()


def _unconfirmed_resolver(base):
    return _Migration(confirmed=False, anchor=None)


def _none_resolver(base):
    return None


def _raising_resolver(base):
    raise RuntimeError("migration resolver blew up")


class _DictSource:
    """A per-mint ATH context source backed by an in-memory dict; records the last
    anchor it was handed (to prove the confirmed anchor is threaded through).
    """

    def __init__(self, mapping):
        self._mapping = mapping
        self.last_anchor = None

    def read_ath_context(self, token_mint, *, migration_event_time_utc):
        self.last_anchor = migration_event_time_utc
        return self._mapping.get(token_mint)


class _RaisingSource:
    def read_ath_context(self, token_mint, *, migration_event_time_utc):
        raise RuntimeError("ath source blew up")


class _NonCallableReadSource:
    # ``read_ath_context`` is present but not callable.
    read_ath_context = "not-callable"


def _reading(
    *,
    token_mint=_MINT,
    ath_status="PRESENT",
    ath_since="POST_MIGRATION_ONLY",
    drawdown_basis="FROM_POST_MIGRATION_ATH",
    drawdown_from_ath="60",
    ath_source="ath-src",
):
    return Stage30_11_10AthContextRecord(
        token_mint=token_mint,
        ath_status=ath_status,
        ath_since_migration_status=ath_since,
        drawdown_basis=drawdown_basis,
        drawdown_from_ath=drawdown_from_ath,
        ath_source=ath_source,
    )


def _resolve(
    base_mint,
    reading,
    *,
    migration_resolver=_confirming_resolver,
    source=None,
):
    base = {"candidate_id": "c", "token_mint": base_mint}
    if source is None:
        mapping = {} if reading is None else {base_mint: reading}
        source = _DictSource(mapping)
    return resolve_candidate_ath(
        base, migration_resolver=migration_resolver, ath_context_source=source
    )


# ---------------------------------------------------------------------------
# 1. Resolved happy path -> present/fresh/pmv True, drawdown VERBATIM, provenance
# ---------------------------------------------------------------------------


def test_present_post_migration_reading_with_drawdown_resolves() -> None:
    res = _resolve(_MINT, _reading())
    assert res.decision == ATH_DECISION_RESOLVED
    assert res.reason == ATH_REASON_RESOLVED_POST_MIGRATION_ATH
    assert res.present is True
    assert res.fresh is True
    assert res.post_migration_ath_verified is True
    # The committed drawdown is carried VERBATIM (never recomputed / reformatted).
    assert res.drawdown_from_ath == "60"
    assert res.token_mint == _MINT
    assert res.source_ref == "ath-src"


def test_drawdown_carried_verbatim_even_when_non_string_or_unusual() -> None:
    # The resolver NEVER coerces / validates the drawdown -- it carries the committed
    # value VERBATIM and the committed Stage 30.11.7 enrichment validates finiteness.
    for value in ("0", "1234.5", "60", 42):
        res = _resolve(_MINT, _reading(drawdown_from_ath=value))
        assert res.decision == ATH_DECISION_RESOLVED, value
        assert res.drawdown_from_ath == value, value


def test_present_equals_fresh_from_the_same_status() -> None:
    res = _resolve(_MINT, _reading())
    assert res.present is res.fresh is True


# ---------------------------------------------------------------------------
# 2. Blank / missing base mint -> fail closed BEFORE any resolve
# ---------------------------------------------------------------------------


def test_blank_or_missing_base_mint_fails_closed() -> None:
    for base in (
        {"token_mint": None},
        {"token_mint": ""},
        {"token_mint": "   "},
        {"token_mint": 12345},
        {},
    ):
        res = resolve_candidate_ath(
            base,
            migration_resolver=_confirming_resolver,
            ath_context_source=_DictSource({_MINT: _reading()}),
        )
        assert res.decision == ATH_DECISION_UNRESOLVED, base
        assert res.reason == ATH_REASON_BLANK_CANDIDATE_MINT, base
        assert res.present is False
        assert res.token_mint == ""


# ---------------------------------------------------------------------------
# 3. Missing migration anchor (none / unconfirmed / blank anchor / raising) -> closed
# ---------------------------------------------------------------------------


def test_missing_or_unconfirmed_migration_anchor_fails_closed() -> None:
    source = _DictSource({_MINT: _reading()})
    for resolver in (
        _none_resolver,
        _unconfirmed_resolver,
        _raising_resolver,
        lambda base: _Migration(confirmed=True, anchor=""),
        lambda base: _Migration(confirmed=True, anchor=None),
        lambda base: object(),  # no confirmed / anchor attributes
        None,  # not callable
    ):
        res = _resolve(_MINT, _reading(), migration_resolver=resolver, source=source)
        assert res.decision == ATH_DECISION_UNRESOLVED
        assert res.reason == ATH_REASON_MISSING_MIGRATION_ANCHOR
        assert res.present is False


def test_missing_migration_anchor_does_not_read_the_ath_source() -> None:
    # Without a confirmed anchor the resolver fails closed BEFORE touching the ATH
    # source (the source's anchor spy stays None).
    source = _DictSource({_MINT: _reading()})
    res = _resolve(
        _MINT, _reading(), migration_resolver=_unconfirmed_resolver, source=source
    )
    assert res.reason == ATH_REASON_MISSING_MIGRATION_ANCHOR
    assert source.last_anchor is None


# ---------------------------------------------------------------------------
# 4. ATH source: missing method / raising / unavailable -> distinct reasons
# ---------------------------------------------------------------------------


def test_non_callable_or_missing_ath_source_is_missing_source() -> None:
    # Call the adapter directly (a ``None`` source must fail closed, not be replaced by
    # the helper's default source).
    base = {"candidate_id": "c", "token_mint": _MINT}
    for source in (None, object(), _NonCallableReadSource()):
        res = resolve_candidate_ath(
            base,
            migration_resolver=_confirming_resolver,
            ath_context_source=source,
        )
        assert res.decision == ATH_DECISION_UNRESOLVED
        assert res.reason == ATH_REASON_MISSING_ATH_SOURCE
        assert res.present is False


def test_raising_ath_source_is_source_error() -> None:
    res = _resolve(_MINT, _reading(), source=_RaisingSource())
    assert res.reason == ATH_REASON_ATH_SOURCE_ERROR
    assert res.present is False


def test_ath_source_returns_nothing_is_unavailable() -> None:
    res = _resolve(_MINT, None)  # mint absent from the source map -> None
    assert res.reason == ATH_REASON_ATH_SOURCE_UNAVAILABLE
    assert res.present is False
    assert res.token_mint == _MINT


def test_confirmed_anchor_is_threaded_to_the_ath_source() -> None:
    source = _DictSource({_MINT: _reading()})
    _resolve(_MINT, _reading(), source=source)
    assert source.last_anchor == _VALID_ANCHOR


# ---------------------------------------------------------------------------
# 5. Mint binding: no cross-mint inheritance
# ---------------------------------------------------------------------------


def test_reading_bound_to_a_different_mint_is_mismatch() -> None:
    # The source hands mint-x a reading whose own token_mint is mint-y.
    source = _DictSource({_MINT: _reading(token_mint="mint-y")})
    res = _resolve(_MINT, None, source=source)
    assert res.reason == ATH_REASON_ATH_MINT_MISMATCH
    assert res.present is False
    assert res.token_mint == _MINT


def test_blank_or_unreadable_reading_mint_is_mismatch() -> None:
    for bad_mint in (None, "", "   "):
        source = _DictSource({_MINT: _reading(token_mint=bad_mint)})
        res = _resolve(_MINT, None, source=source)
        assert res.reason == ATH_REASON_ATH_MINT_MISMATCH, bad_mint


def test_malformed_reading_object_fails_closed_not_raises() -> None:
    # A non-record reading (a bare string / int) has no readable token_mint -> mismatch.
    for junk in ("garbage", 5, object()):
        source = _DictSource({_MINT: junk})
        res = _resolve(_MINT, None, source=source)
        assert res.decision == ATH_DECISION_UNRESOLVED, junk
        assert res.reason == ATH_REASON_ATH_MINT_MISMATCH, junk


# ---------------------------------------------------------------------------
# 6. ATH not present (stale / unavailable / source-error / missing) -> not present
# ---------------------------------------------------------------------------


def test_non_present_ath_status_fails_closed_at_not_present() -> None:
    for status in (
        "STALE",
        "UNAVAILABLE",
        "SOURCE_ERROR",
        "NOT_APPLICABLE",
        "UNSUPPORTED_PAIR",
        None,
        "present",  # case-sensitive: lower-case is NOT the PRESENT token
        5,
    ):
        res = _resolve(_MINT, _reading(ath_status=status))
        assert res.decision == ATH_DECISION_UNRESOLVED, status
        assert res.reason == ATH_REASON_ATH_NOT_PRESENT, status
        assert res.present is False, status
        assert res.fresh is False, status


# ---------------------------------------------------------------------------
# 7. Pre-migration ATH (basis not FROM_POST_MIGRATION_ATH) -> not verified
# ---------------------------------------------------------------------------


def test_pre_migration_basis_fails_closed_but_rides_present_fresh() -> None:
    for basis in ("NOT_APPLICABLE", "UNKNOWN", None, "from_post_migration_ath"):
        res = _resolve(_MINT, _reading(drawdown_basis=basis))
        assert res.decision == ATH_DECISION_UNRESOLVED, basis
        assert res.reason == ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED, basis
        # Present + fresh ride through (so the committed Stage 30.11.7 adapter rejects at
        # its precise PRE_MIGRATION_ATH_NOT_VERIFIED check, not the generic first one).
        assert res.present is True, basis
        assert res.fresh is True, basis
        assert res.post_migration_ath_verified is False, basis


# ---------------------------------------------------------------------------
# 7b. Post-migration window status (ath_since_migration_status) is REQUIRED OUTRIGHT
#     alongside the FROM_POST_MIGRATION_ATH basis -- an inconsistent / missing /
#     non-exact window fails closed even with a perfect basis + finite drawdown
#     (Codex Stage 30.11.10 patch: the bridge consumes duck-typed records that can
#     DECOUPLE the two committed Stage 27.4 signals).
# ---------------------------------------------------------------------------


def test_inconsistent_post_migration_window_fails_closed_with_post_basis() -> None:
    # Codex repro: PRESENT, FROM_POST_MIGRATION_ATH, finite drawdown -- but the window
    # says MAY_INCLUDE_PRE_MIGRATION. The basis alone must NOT verify post-migration.
    res = _resolve(
        _MINT,
        _reading(
            ath_since="MAY_INCLUDE_PRE_MIGRATION",
            drawdown_basis="FROM_POST_MIGRATION_ATH",
            drawdown_from_ath="0.55",
        ),
    )
    assert res.decision == ATH_DECISION_UNRESOLVED
    assert res.reason == ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED
    assert res.post_migration_ath_verified is False
    # Present + fresh ride through (so the committed Stage 30.11.7 adapter rejects at its
    # precise PRE_MIGRATION_ATH_NOT_VERIFIED check, not the generic first one).
    assert res.present is True
    assert res.fresh is True


def test_missing_or_non_exact_window_status_fails_closed() -> None:
    # A missing / blank / wrong-case / non-exact / non-string window status all fail
    # closed -- even with a perfect FROM_POST_MIGRATION_ATH basis + finite drawdown.
    # ath_since_migration_status is required OUTRIGHT (omission is never accepted).
    for window in (
        None,
        "",
        "   ",
        "post_migration_only",  # case-sensitive
        "POST_MIGRATION",
        "MAY_INCLUDE_PRE_MIGRATION",
        "UNKNOWN",
        5,
    ):
        res = _resolve(
            _MINT,
            _reading(
                ath_since=window,
                drawdown_basis="FROM_POST_MIGRATION_ATH",
                drawdown_from_ath="0.55",
            ),
        )
        assert res.decision == ATH_DECISION_UNRESOLVED, window
        assert res.reason == ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED, window
        assert res.post_migration_ath_verified is False, window
        assert res.present is True, window
        assert res.fresh is True, window


def test_both_post_migration_signals_required_for_resolution() -> None:
    # ONLY a reading carrying BOTH POST_MIGRATION_ONLY AND FROM_POST_MIGRATION_ATH
    # resolves; dropping EITHER signal fails closed at PRE_MIGRATION_ATH_NOT_VERIFIED.
    resolved = _resolve(
        _MINT,
        _reading(
            ath_since="POST_MIGRATION_ONLY",
            drawdown_basis="FROM_POST_MIGRATION_ATH",
        ),
    )
    assert resolved.decision == ATH_DECISION_RESOLVED
    assert resolved.post_migration_ath_verified is True
    for ath_since, basis in (
        ("MAY_INCLUDE_PRE_MIGRATION", "FROM_POST_MIGRATION_ATH"),
        ("POST_MIGRATION_ONLY", "NOT_APPLICABLE"),
        ("MAY_INCLUDE_PRE_MIGRATION", "NOT_APPLICABLE"),
        (None, "FROM_POST_MIGRATION_ATH"),
    ):
        res = _resolve(
            _MINT, _reading(ath_since=ath_since, drawdown_basis=basis)
        )
        assert res.decision == ATH_DECISION_UNRESOLVED, (ath_since, basis)
        assert res.reason == ATH_REASON_PRE_MIGRATION_ATH_NOT_VERIFIED, (
            ath_since,
            basis,
        )
        assert res.post_migration_ath_verified is False, (ath_since, basis)


# ---------------------------------------------------------------------------
# 8. Missing drawdown (present + post-migration but no drawdown) -> missing drawdown
# ---------------------------------------------------------------------------


def test_present_post_migration_but_no_drawdown_is_missing_drawdown() -> None:
    res = _resolve(_MINT, _reading(drawdown_from_ath=None))
    assert res.decision == ATH_DECISION_UNRESOLVED
    assert res.reason == ATH_REASON_MISSING_DRAWDOWN
    # present + fresh + post-migration ride through (so the committed Stage 30.11.7
    # adapter rejects at its precise INVALID_DRAWDOWN check).
    assert res.present is True
    assert res.fresh is True
    assert res.post_migration_ath_verified is True
    assert res.drawdown_from_ath is None


# ---------------------------------------------------------------------------
# 9. Duck-typed object base + build_ath_resolver factory
# ---------------------------------------------------------------------------


def test_duck_typed_object_base_works() -> None:
    class _Obj:
        token_mint = _MINT

    source = _DictSource({_MINT: _reading()})
    res = resolve_candidate_ath(
        _Obj(), migration_resolver=_confirming_resolver, ath_context_source=source
    )
    assert res.decision == ATH_DECISION_RESOLVED
    assert res.token_mint == _MINT


def test_build_ath_resolver_returns_callable_keyed_by_base_mint() -> None:
    source = _DictSource({_MINT: _reading()})
    resolver = build_ath_resolver(
        migration_resolver=_confirming_resolver, ath_context_source=source
    )
    assert callable(resolver)
    assert resolver({"token_mint": _MINT}).decision == ATH_DECISION_RESOLVED
    # A different mint with no reading in the source fails closed (no inheritance).
    assert resolver({"token_mint": "mint-other"}).decision == (
        ATH_DECISION_UNRESOLVED
    )


def test_resolver_is_total_never_raises_on_garbage() -> None:
    source = _DictSource({_MINT: _reading()})
    resolver = build_ath_resolver(
        migration_resolver=_confirming_resolver, ath_context_source=source
    )
    for base in (None, object(), 5, "x", {"token_mint": object()}):
        res = resolver(base)
        assert res.decision in (ATH_DECISION_RESOLVED, ATH_DECISION_UNRESOLVED)
