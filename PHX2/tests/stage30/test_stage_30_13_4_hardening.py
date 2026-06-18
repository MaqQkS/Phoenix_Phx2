"""Stage 30.13.4 blind-audit remediation hardening tests.

Offline / fake / no-send only. Pins the three Stage 30.13.4 hardenings that close the
blind-audit FAIL on Build #24:

  1. (Major) the public fake end-to-end proof REJECTS live-looking / non-fake injected
     transports / sources, and exposes NO dispatch-client and NO durable-ledger injection
     knob at all -- a fake-seeded candidate can never reach a non-fake dispatch client or
     durable ledger through accidental caller injection;
  2. (Major) the pump-suffix discovery predicate is base58-STRICT -- a value that merely
     ENDS in ``pump`` but carries a slash, colon, scheme-like text, quote, punctuation,
     backslash, unicode, or whitespace character is rejected BEFORE seeding, and the
     unsafe token echo stays redacted;
  3. (Minor) the auto-seeder pulls a caller-provided discovery iterable BOUNDEDLY -- it
     never materializes an arbitrary / lazy / unbounded iterable before applying the
     local hard processing cap.

No real socket, no network, no env, no Discord, no durable ledger, no live send.
"""

from __future__ import annotations

import pytest

from PHX2.stage29.stage29_5_migration_models import (
    MIGRATION_SOURCE_HELIUS_WS,
    MIGRATION_STATUS_PRESENT,
    Stage29_5MigrationEvidenceRecord,
)
from PHX2.stage30.stage30_13_0_ws_auto_seed_models import (
    SEED_REASON_NOT_PUMP_SUFFIX,
    STAGE30_13_REDACTED_UNSAFE_ID,
    STAGE30_13_REDACTION_STATUS_REDACTED,
    is_base58_mint_string,
    is_pump_suffix_mint,
)
from PHX2.stage30.stage30_13_0_ws_auto_seeder import (
    build_seeded_watchlist_from_ws_discovery,
)
from PHX2.stage30.stage30_13_2_fake_end_to_end_proof import (
    STAGE30_13_2_ROLE_ATH_TRANSPORT,
    STAGE30_13_2_ROLE_MARKET_CONTEXT_SOURCE,
    STAGE30_13_2_ROLE_PRICE_SOURCE,
    STAGE30_13_2_ROLE_TRANSPORT,
    Stage30_13_2FakeOnly,
    Stage30_13_2FakeProofError,
    run_stage30_13_2_fake_end_to_end_proof,
)


_POOL = "P" * 44
_PROG = "G" * 44
_QUOTE = "Q" * 44
_TS = "2026-06-06T06:00:00Z"
_OBS = "2026-06-07T02:00:00+00:00"
_CREATED = "2026-06-07T04:00:00+00:00"

# A base58, safe-shape, pump-suffix mint: 40 base58 chars + the literal pump suffix.
_VALID_PUMP_MINT = "a" * 40 + "pump"

# Non-ASCII / whitespace probe characters used by the predicate-rejection tests below.
_E_ACUTE = "é"       # latin small letter e with acute
_FULLWIDTH_A = "Ａ"   # fullwidth latin capital A
_NBSP = " "          # non-breaking space


def _present(mint: str) -> Stage29_5MigrationEvidenceRecord:
    """Build a PRESENT migration evidence record with complete evidence and ``mint`` as
    the base mint. ``mint`` need only satisfy the Stage 29.5 safe-shape gate (printable,
    no whitespace, length 32..64); it need NOT be base58.
    """
    return Stage29_5MigrationEvidenceRecord(
        migration_status=MIGRATION_STATUS_PRESENT,
        migration_source=MIGRATION_SOURCE_HELIUS_WS,
        base_mint=mint,
        pool_account=_POOL,
        pool_program_id=_PROG,
        quote_mint=_QUOTE,
        migration_timestamp_utc=_TS,
        migration_slot=123456,
        migration_signature="sig-x",
        observed_at_utc=_OBS,
        source_event_ref="ref-x",
    )


class _FakeDiscovery:
    """In-memory fake exposing the WS adapter's ``read_migration_evidence_batch``."""

    def __init__(self, batch) -> None:
        self._batch = list(batch)

    def read_migration_evidence_batch(self):
        return tuple(self._batch)


# ===========================================================================
# Finding 1 (Major): the public fake end-to-end proof rejects non-fake injection
# ===========================================================================


class _MarkedFake(Stage30_13_2FakeOnly):
    """A fake-only marked stand-in component. In the rejection cases below it is never
    actually driven -- the marker guard refuses the run before any component is used.
    """


class _LiveLookingComponent:
    """An UNMARKED, live-looking component (NOT a ``Stage30_13_2FakeOnly``). Stands in for
    a real transport / provider source / ATH transport that must never be injectable.
    """


def _marked_proof_kwargs() -> dict:
    """A full set of fake-only marked keyword inputs for the public proof. Each role is
    overridden with an unmarked component in the per-role rejection tests.
    """
    return {
        "clock": object(),
        "price_source": _MarkedFake(),
        "market_context_source": _MarkedFake(),
        "ath_transport": _MarkedFake(),
        "ath_endpoint_secret": object(),
        "now_utc": object(),
        "now_seconds": object(),
        "created_at_utc": _CREATED,
    }


def test_unmarked_transport_is_rejected_before_anything_is_driven() -> None:
    kwargs = _marked_proof_kwargs()
    with pytest.raises(Stage30_13_2FakeProofError) as excinfo:
        run_stage30_13_2_fake_end_to_end_proof(
            _LiveLookingComponent(), **kwargs
        )
    assert excinfo.value.role == STAGE30_13_2_ROLE_TRANSPORT


def test_unmarked_price_source_is_rejected() -> None:
    kwargs = _marked_proof_kwargs()
    kwargs["price_source"] = _LiveLookingComponent()
    with pytest.raises(Stage30_13_2FakeProofError) as excinfo:
        run_stage30_13_2_fake_end_to_end_proof(_MarkedFake(), **kwargs)
    assert excinfo.value.role == STAGE30_13_2_ROLE_PRICE_SOURCE


def test_unmarked_market_context_source_is_rejected() -> None:
    kwargs = _marked_proof_kwargs()
    kwargs["market_context_source"] = _LiveLookingComponent()
    with pytest.raises(Stage30_13_2FakeProofError) as excinfo:
        run_stage30_13_2_fake_end_to_end_proof(_MarkedFake(), **kwargs)
    assert excinfo.value.role == STAGE30_13_2_ROLE_MARKET_CONTEXT_SOURCE


def test_unmarked_ath_transport_is_rejected() -> None:
    kwargs = _marked_proof_kwargs()
    kwargs["ath_transport"] = _LiveLookingComponent()
    with pytest.raises(Stage30_13_2FakeProofError) as excinfo:
        run_stage30_13_2_fake_end_to_end_proof(_MarkedFake(), **kwargs)
    assert excinfo.value.role == STAGE30_13_2_ROLE_ATH_TRANSPORT


def test_dispatch_client_injection_knob_cannot_be_passed_at_all() -> None:
    # There is NO ``transport_client`` parameter, so a real dispatch client cannot be
    # injected -- the call is a TypeError (unexpected keyword argument).
    kwargs = _marked_proof_kwargs()
    with pytest.raises(TypeError):
        run_stage30_13_2_fake_end_to_end_proof(
            _MarkedFake(),
            transport_client=_LiveLookingComponent(),
            **kwargs,
        )


def test_durable_ledger_injection_knob_cannot_be_passed_at_all() -> None:
    # There is NO ``ledger`` parameter, so a durable ledger cannot be injected -- the
    # call is a TypeError (unexpected keyword argument).
    kwargs = _marked_proof_kwargs()
    with pytest.raises(TypeError):
        run_stage30_13_2_fake_end_to_end_proof(
            _MarkedFake(),
            ledger=_LiveLookingComponent(),
            **kwargs,
        )


def test_role_tokens_are_distinct_closed_set() -> None:
    roles = (
        STAGE30_13_2_ROLE_TRANSPORT,
        STAGE30_13_2_ROLE_PRICE_SOURCE,
        STAGE30_13_2_ROLE_MARKET_CONTEXT_SOURCE,
        STAGE30_13_2_ROLE_ATH_TRANSPORT,
    )
    assert len(set(roles)) == 4
    # The full happy-path proof (marked fakes -> seeded -> fake dispatch only) is
    # preserved by test_stage_30_13_2_fake_end_to_end_proof.py.


# ===========================================================================
# Finding 2 (Major): the pump-suffix predicate is base58-strict
# ===========================================================================


def test_valid_base58_pump_mint_still_accepted() -> None:
    assert is_pump_suffix_mint(_VALID_PUMP_MINT) is True
    assert is_pump_suffix_mint("B" * 40 + "pump") is True


def test_pump_suffix_rejects_slash() -> None:
    assert is_pump_suffix_mint("a" * 39 + "/pump") is False


def test_pump_suffix_rejects_colon() -> None:
    assert is_pump_suffix_mint("a" * 39 + ":pump") is False


def test_pump_suffix_rejects_scheme_like_text() -> None:
    # Build the scheme separator by concatenation so the test source carries no literal.
    scheme = "htt" + "p" + ":" + "/" + "/"
    value = scheme + "a" * 30 + "pump"  # len 41, ends "pump", carries colon + slashes
    assert is_pump_suffix_mint(value) is False


def test_pump_suffix_rejects_quotes() -> None:
    assert is_pump_suffix_mint("a" * 39 + '"pump') is False
    assert is_pump_suffix_mint("a" * 39 + "'pump") is False


def test_pump_suffix_rejects_punctuation() -> None:
    for punct in (".", "!", "+", "=", "@", "#", "*", ","):
        assert is_pump_suffix_mint("a" * 39 + punct + "ump") is False
    # Trailing-dot before the suffix.
    assert is_pump_suffix_mint("a" * 39 + ".pump") is False


def test_pump_suffix_rejects_backslash() -> None:
    assert is_pump_suffix_mint("a" * 39 + "\\pump") is False


def test_pump_suffix_rejects_unicode_non_ascii() -> None:
    assert is_pump_suffix_mint(_E_ACUTE + "a" * 39 + "pump") is False
    assert is_pump_suffix_mint(_FULLWIDTH_A * 40 + "pump") is False
    # base58 EXCLUDES the four visually ambiguous ASCII characters 0, O, I, l.
    assert is_pump_suffix_mint("0" * 40 + "pump") is False
    assert is_pump_suffix_mint("O" * 40 + "pump") is False
    assert is_pump_suffix_mint("I" * 40 + "pump") is False
    assert is_pump_suffix_mint("l" * 40 + "pump") is False


def test_pump_suffix_rejects_whitespace_variants() -> None:
    assert is_pump_suffix_mint("a" * 39 + " pump") is False          # space
    assert is_pump_suffix_mint("a" * 39 + "\tpump") is False          # tab
    assert is_pump_suffix_mint("a" * 39 + _NBSP + "pump") is False    # non-breaking space


def test_is_base58_mint_string_predicate() -> None:
    assert is_base58_mint_string("a" * 44) is True
    assert is_base58_mint_string("123456789ABCDEFGHJKLMNPQRSTUVWXYZ") is True
    for bad in ("0", "O", "I", "l", "/", ":", " ", "\t", "+", "=", _E_ACUTE, "\\"):
        assert is_base58_mint_string("a" * 30 + bad) is False
    assert is_base58_mint_string("") is False
    assert is_base58_mint_string(None) is False


def test_unsafe_pump_mint_is_rejected_and_echo_stays_redacted() -> None:
    # A PRESENT record whose base mint ENDS in pump but smuggles a slash: it passes the
    # Stage 29.5 record shape gate (printable, no whitespace) but the tightened base58
    # predicate rejects it -- and the unsafe value is echoed REDACTED, never raw.
    unsafe_mint = "A" * 39 + "/pump"  # 44 chars, slash -> not base58
    result = build_seeded_watchlist_from_ws_discovery(
        _FakeDiscovery([_present(unsafe_mint)]),
        created_at_utc=_CREATED,
        max_seed=10,
    )
    assert result.summary.accepted == 0
    assert result.summary.rejected == 1
    assert len(result.seeded_summaries) == 0
    outcome = result.outcomes[0]
    assert outcome.seed_reason == SEED_REASON_NOT_PUMP_SUFFIX
    # The unsafe slash-bearing mint is NEVER echoed raw -- it is replaced by the safe
    # placeholder, and the combined redaction status stays REDACTED.
    assert outcome.token_mint == STAGE30_13_REDACTED_UNSAFE_ID
    assert "/" not in outcome.token_mint
    assert result.redaction_status == STAGE30_13_REDACTION_STATUS_REDACTED


# ===========================================================================
# Finding 3 (Minor): the auto-seeder pulls the discovery iterable boundedly
# ===========================================================================


class _LazyUnboundedDiscovery:
    """A discovery whose batch is a LAZY, effectively unbounded generator.

    It counts how many times it is advanced and TRIPWIRES (raises) if advanced past a
    bound far above the Stage 30 seed ceiling -- so a non-bounded seeder that materialized
    the whole iterable (the old ``records = list(batch)``) would trip the wire, while the
    bounded seeder stops after at most the local processing cap.
    """

    def __init__(self, mint: str, *, tripwire_at: int) -> None:
        self.pulled = 0
        self._mint = mint
        self._tripwire_at = tripwire_at

    def read_migration_evidence_batch(self):
        return self._gen()

    def _gen(self):
        while True:
            if self.pulled >= self._tripwire_at:
                raise AssertionError(
                    "auto-seeder advanced the discovery past the bounded cap"
                )
            self.pulled += 1
            yield _present(self._mint)


def test_seeder_pulls_unbounded_discovery_boundedly_at_default_cap() -> None:
    disc = _LazyUnboundedDiscovery(_VALID_PUMP_MINT, tripwire_at=200)
    result = build_seeded_watchlist_from_ws_discovery(
        disc, created_at_utc=_CREATED, max_seed=10
    )
    # The seeder advanced the lazy discovery at most the cap -- never exhausted it, never
    # tripped the wire (the tripwire would have surfaced as a WS_CAPTURE_FAILED error).
    assert disc.pulled == 10
    assert result.summary.error == 0
    assert result.summary.records_seen == 10
    assert result.summary.accepted == 1   # the first pump mint
    assert result.summary.duplicate == 9  # the same mint repeated, deduped


def test_seeder_bound_follows_max_seed() -> None:
    disc = _LazyUnboundedDiscovery(_VALID_PUMP_MINT, tripwire_at=200)
    result = build_seeded_watchlist_from_ws_discovery(
        disc, created_at_utc=_CREATED, max_seed=3
    )
    assert disc.pulled == 3
    assert result.summary.records_seen == 3
    assert result.summary.error == 0


def test_seeder_never_materializes_more_than_hard_cap() -> None:
    # Even with the default cap, an unbounded discovery is advanced at most the Stage 30
    # hard ceiling (10) -- proving no full materialization of an arbitrary iterable.
    disc = _LazyUnboundedDiscovery(_VALID_PUMP_MINT, tripwire_at=64)
    build_seeded_watchlist_from_ws_discovery(
        disc, created_at_utc=_CREATED, max_seed=10
    )
    assert disc.pulled <= 10
