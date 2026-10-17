"""One shared dedupe, ONE pass per candidate.

Regression cover for the Helius-only zero-alert defect: the paid provider
admits a candidate through the shared ``ProviderCandidateDedupe`` at
``_admit_candidate`` (keyed on ``provider_event_id`` + mint), and the
session-level discovery boundary then ran the SAME instance a second time
whenever ``source_label != "GRPC"``.  Relabelling the paid path
``"GRPC"`` -> ``"HELIUS"`` switched that second pass on, and because
``source_ref`` is not ``provider_event_id`` the event-id check missed while the
mint check rejected every already-admitted candidate as ``DUPLICATE_MINT``.
Live evidence, run ``paid_primary_live_24x7_20260730T132310Z``: 20 decoded,
17 accepted/enqueued/dequeued, ``duplicate_mints_dropped == 17``, ZERO
candidates reaching the watchlist.

The invariant proven here: a candidate already admitted through the shared
provider dedupe is never re-tested against that same instance, and a candidate
that has NOT been admitted through it still gets exactly one required pass.
The decision is read off the candidate (``provider_dedupe_applied``), never off
a source label.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import inspect

import pytest

from PHX2.free_tier_producer import free_tier_session as producer_session
from PHX2.free_tier_producer import helius_source
from PHX2.free_tier_producer.compat.build30_watchlist import Watchlist
from PHX2.free_tier_producer.free_tier_credit_budget import (
    FreeTierCreditBudget,
    FreeTierCreditBudgetCaps,
)
from PHX2.free_tier_producer.paid_provider import (
    PROVIDER_DEDUPE_APPLIED_FIELD,
    ProviderCandidateDedupe,
    SingleGrpcPumpSwapDiscovery,
    apply_provider_dedupe_once,
    event_to_candidate,
    mark_provider_dedupe_applied,
    provider_dedupe_already_applied,
)
from PHX2.stage28.chainstack_yellowstone_models import build_normalized_event


NOW = "2026-07-30T13:24:31Z"
QUOTE = "So11111111111111111111111111111111111111112"
POOL = "D" * 44
CHAINSTACK_IDENTITY = "CHAINSTACK_YELLOWSTONE"

# The 17 candidates the live run accepted, enqueued and dequeued, and which the
# double pass then dropped to zero.  Real (public) mint + transaction signature
# pairs, preserved verbatim from that run's provider_handoff.jsonl.
PRESERVED_ACCEPTED = (
    ("vBxqbsdHzu4RWV4ZR19Uds4njdL9bKMwAQQP2Wopump",
     "4G5SHLDAX3bQDHAtxnaG5EzJS5BDVvJ5GVt4JEjrMke2CCdVcULGMw1vaqZTT462eM7Ha3B9BErVYfchqytJJA63"),
    ("JAtsUZ3Lisoc84gjENYZMeNnjqvxPFBQG9qAZfDKpump",
     "FttxMoTXkEyWKsfnL6YwETtTRmpYFkrQLrTYY7y5PE4UDRpyenY4rLAp5nC7LHGYtNXPDrFvLsm49qhypXK89UR"),
    ("6ZjsyxzMudRTEKGtt24WpE8DpqsD9NCHWfsQcG5dpump",
     "31ssmpCGBnvaEr98B8aUAT6oovoJJF7Vy4jNUgAGG5TR5djD7JvLGmXmEFAVVh4H3Jm18TMLKTdCumqNsdPzfhrG"),
    ("BChit3Cc3iDHaQMYh8g5zvu937R9ESoGCh8NQsAWpump",
     "3jtp1RX5Mw6SDnhEpeRmLTrm7o884FAuDgNySW73f8G65UNc3PhNpigc4AV7ekiMjB1iAPkDF8s5ZXu1hmGxtokF"),
    ("CdPtnwX3cXhj1WrdVQsT59DwpagRNbA5Jfvxj3Ufpump",
     "4v8BcTSS5uGF2xoesgfFWidqPC85dqzxFFd2nKqRxHfNdubv3bHsavR4Cno5EhvX2H3VTMhaUzD3E5NcSrqRiU7z"),
    ("VRGZgoVr2AgLmq5hZm3RFRup1znPDb31jerLp6xpump",
     "d7Z8LXF2KLPYUBw1A74SUg51eXCVcM3w6dJa8tPcLwxG6MGsgd8fzAvtn2o3JbXyU2JZ5SjruAfGP47KmaKQKKN"),
    ("3Hfbhg84nsUtzrTPTu8SpnhzFcDpAsvXv1cEyX4opump",
     "3aMhZ6N2n5SGMF31fpyjD37mnBQUyrLFZE7puSGQHJEjbwPUnRkois3fDNPczzd1jigVcc85LPvQxaDLqfSKibWD"),
    ("FAijGiVUkZQgK1gEyMyGXxqQo9QJwd5CRJxRBBkfpump",
     "3gsZiWc2LrEx6fyB195CxdBZRK49MLqkiSwpHhbVWT9BiYytXipsdz7ECM9CSbSPtGgTd52mBpWGJ6zoDgCVoViz"),
    ("AYJ1tYQZZJ1gmZhURYuXLwG9bygUcgBnYPzriLpxpump",
     "66nqRYNBtn469L6HwN1zB5QbGvvmJKdKpKFeUgSiB79Eb2paGVZQJsJAjmpiZ29kXorTFzesmaAqhXi5D3zv7AJ"),
    ("HDyrWRNA2TyhqsrqEkowqp3NiwVoYA8DkubzoZLwpump",
     "WBLKdzr1wSn4bUjdctj82DwUBEDLyigaXbycbrKfnAx8MatbzFCn69hehc8MuZ6CXfRPC9L7eiWZwoC74FV1syL"),
    ("4y6B6BtDh4ptagHwS2VdqvcYB1AoY3TE2gTGQubUpump",
     "4aXNqv3MbVUbA7bEfjcapXfTRXP9HCEKF4toaDqPGpQVrAxxVz9r9dG4VUqaqvn5HwjabXTqG1pDXMVKU5E5wTcg"),
    ("3EvGLExjtB3mKLvJfFiWeuQUS98ZKW4nseMgvRs7pump",
     "28tNForNfcBUhyey9dFGvaiF351JFQTw1HkAH6dPeN1FNRxjw7L2gzuHVYbxtuRLtcQkNesRV6GWTU75g9yodnS6"),
    ("9WQYVo6WwJgVEZn6oH3ZtYAPiMhgTdrTRRNZVAcgpump",
     "NwijDeQSmPzGJWcbyPXeCEJM5K8WSRBgy3YXr8mEEva9K7uCfsjSATBmWVJpbyFAWvXw53NshZkcpmZ4pJsFCQP"),
    ("QsVoocMoSkY48sttDwj6PyTZPTXNcm4LhKDKyW5pump",
     "3nBzc8dY5DCFaSkdMrHe9Nr9mUQtqrNhztk7aTuEcHARGNBpZamjhGKnDPQqz88ocQHYqouD6MtwsAb4y44mKigy"),
    ("3WDDidkfnqzjnz4AUPjDerWQ5XJthdFEtymqNZaWpump",
     "63RcXxzHWi6fRb96WeMwuv9Yz4By8H8S9fS8cZ7SrcuDL37kWypDkbCineXQfyk47v4DUsdxW7ZWdZtSoNDxZrgd"),
    ("PzJEixcwKRQifceAACKnzuhHcQ46UJDgajFogFCpump",
     "33Xdknk4Qu1MYErzfBKYCXhSQb5omeirL8RvcUynBWT3j2NTkzidm1R44ep1ox1Qoprwd883ZhBKanYWfUApXRxt"),
    ("mqAVp5Fx9o6ubpnqDGnY4u7WMpGYaocfzWzrJASpump",
     "3wpMXVMBZ3f5ZCkskv1wUZeV2sBoetB21yfuZkr5dZTDwrnF5Xt2zX8PDkPUGTxPLoe9koYPGzH27t8dmhaWe525"),
)


def _raw_hash(signature: str) -> str:
    """A raw-event hash that is NOT the provider event id.

    Exactly the production shape: ``source_ref`` (raw hash) and
    ``provider_event_id`` (signature) are different strings, which is why the
    second pass's event-id check missed and its mint check rejected.
    """

    return "helius_" + hashlib.sha256(signature.encode("utf-8")).hexdigest()


def _paid_event(mint: str, signature: str, *, identity: str = None):
    return build_normalized_event(
        event_id="evt_" + signature[:16],
        provider_event_id=signature,
        provider_name=identity or helius_source.HELIUS_SOURCE_IDENTITY,
        mint=mint,
        event_type="migration",
        observed_at_utc=NOW,
        raw_event_hash=_raw_hash(signature),
        quote_mint=QUOTE,
        pool_account=POOL,
        pool_program_id=helius_source.PUMPSWAP_PROGRAM_ID,
        base_mint=mint,
    )


def _owner(dedupe: ProviderCandidateDedupe) -> SingleGrpcPumpSwapDiscovery:
    return SingleGrpcPumpSwapDiscovery(
        source_factory=lambda: pytest.fail("no live source in offline tests"),
        dedupe=dedupe)


def _admit(dedupe: ProviderCandidateDedupe, pairs, *, identity: str = None) -> list:
    """Drive real events through the real provider admission boundary."""

    owner = _owner(dedupe)
    for mint, signature in pairs:
        owner._handle_event(_paid_event(mint, signature, identity=identity))
    return owner.drain(max_candidates=len(pairs) + 8)


def _session_candidate(mint: str, source_ref: str) -> dict:
    """A discovery-boundary candidate that never saw the provider boundary."""

    return {"token_mint": mint, "source_ref": source_ref,
            "candidate_id": source_ref, "discovery_utc": NOW}


# ---------------------------------------------------------------------------
# 1 + 2 -- paid-provider candidates survive the session boundary
# ---------------------------------------------------------------------------


def test_1_helius_candidate_admitted_by_paid_provider_survives_session_guard():
    mint, signature = PRESERVED_ACCEPTED[0]
    dedupe = ProviderCandidateDedupe()
    drained = _admit(dedupe, [(mint, signature)])

    assert [c["token_mint"] for c in drained] == [mint]
    assert drained[0]["discovery_provider"] == "HELIUS_PRIMARY"
    # The admission stamped the proof, and source_ref really is not the event id.
    assert provider_dedupe_already_applied(drained[0])
    assert drained[0]["source_ref"] != drained[0]["provider_event_id"]

    survivors = apply_provider_dedupe_once(drained, dedupe)

    assert [c["token_mint"] for c in survivors] == [mint]
    # The defect signature: not one extra mint rejection was recorded.
    assert dedupe.snapshot()["duplicate_mints_dropped"] == 0


def test_2_chainstack_paid_provider_candidate_still_survives():
    mint, signature = PRESERVED_ACCEPTED[1]
    dedupe = ProviderCandidateDedupe()
    owner = _owner(dedupe)
    owner._handle_event(_paid_event(mint, signature, identity=CHAINSTACK_IDENTITY))
    drained = owner.drain(max_candidates=4)

    assert [c["token_mint"] for c in drained] == [mint]
    assert drained[0]["discovery_provider"] == "PAID_GRPC_PRIMARY"
    assert provider_dedupe_already_applied(drained[0])

    survivors = apply_provider_dedupe_once(drained, dedupe)

    assert [c["token_mint"] for c in survivors] == [mint]
    assert dedupe.snapshot()["duplicate_mints_dropped"] == 0


# ---------------------------------------------------------------------------
# 3 + 4 -- legacy sources keep EXACTLY ONE required pass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["WS", "POLLING"])
def test_3_and_4_legacy_source_candidate_receives_exactly_one_dedupe_pass(label):
    mint, signature = PRESERVED_ACCEPTED[2]
    dedupe = ProviderCandidateDedupe()
    candidate = _session_candidate(mint, label.lower() + "_" + signature[:24])

    # It carries no admission proof, so the session boundary is its ONE pass.
    assert not provider_dedupe_already_applied(candidate)
    survivors = apply_provider_dedupe_once([candidate], dedupe)

    assert [c["token_mint"] for c in survivors] == [mint]
    snap = dedupe.snapshot()
    assert snap["mints_tracked"] == 1 and snap["event_ids_tracked"] == 1
    # That one pass consumed the dedupe, so it is now stamped and never retested.
    assert provider_dedupe_already_applied(candidate)
    assert apply_provider_dedupe_once([candidate], dedupe) == [candidate]
    assert dedupe.snapshot()["duplicate_mints_dropped"] == 0


# ---------------------------------------------------------------------------
# 5 + 6 -- duplicates are STILL rejected, at their own boundary
# ---------------------------------------------------------------------------


def test_5_duplicate_helius_provider_events_remain_rejected_at_provider_boundary():
    mint, signature = PRESERVED_ACCEPTED[3]
    dedupe = ProviderCandidateDedupe()
    owner = _owner(dedupe)

    owner._handle_event(_paid_event(mint, signature))
    owner._handle_event(_paid_event(mint, signature))     # same event id
    drained = owner.drain(max_candidates=8)

    assert [c["token_mint"] for c in drained] == [mint]   # exactly one admitted
    assert owner.snapshot()["candidates_accepted"] == 1
    assert dedupe.snapshot()["duplicate_events_dropped"] == 1


@pytest.mark.parametrize("label", ["WS", "POLLING"])
def test_6_duplicate_legacy_events_remain_rejected_at_session_boundary(label):
    mint, signature = PRESERVED_ACCEPTED[4]
    dedupe = ProviderCandidateDedupe()
    ref = label.lower() + "_" + signature[:24]
    # Two independently discovered candidate dicts for the same mint: a
    # rediscovery is a NEW dict and carries no stamp, so it is tested.
    first = _session_candidate(mint, ref)
    second = _session_candidate(mint, ref)

    survivors = apply_provider_dedupe_once([first, second], dedupe)

    assert survivors == [first]
    assert dedupe.snapshot()["duplicate_events_dropped"] == 1
    assert not provider_dedupe_already_applied(second)


# ---------------------------------------------------------------------------
# 7 -- same mint, different event ids, no second paid-path rejection
# ---------------------------------------------------------------------------


def test_7_same_mint_different_event_ids_never_causes_a_second_paid_rejection():
    mint, signature = PRESERVED_ACCEPTED[5]
    other_signature = PRESERVED_ACCEPTED[6][1]
    dedupe = ProviderCandidateDedupe()
    owner = _owner(dedupe)

    owner._handle_event(_paid_event(mint, signature))
    # Same mint under a DIFFERENT event id: the provider boundary owns this
    # rejection (DUPLICATE_MINT), and it happens exactly once.
    owner._handle_event(_paid_event(mint, other_signature))
    drained = owner.drain(max_candidates=8)

    assert [c["token_mint"] for c in drained] == [mint]
    assert dedupe.snapshot()["duplicate_mints_dropped"] == 1

    # The session boundary adds NO further mint rejection for the survivor.
    survivors = apply_provider_dedupe_once(drained, dedupe)
    assert [c["token_mint"] for c in survivors] == [mint]
    assert dedupe.snapshot()["duplicate_mints_dropped"] == 1


# ---------------------------------------------------------------------------
# 8 + 9 + 10 -- the preserved live population reaches the watchlist
# ---------------------------------------------------------------------------


def test_8_preserved_seventeen_accepted_candidates_produce_seventeen_survivors():
    dedupe = ProviderCandidateDedupe()
    drained = _admit(dedupe, PRESERVED_ACCEPTED)

    assert len(drained) == 17                      # provider boundary, as it ran live
    assert dedupe.snapshot()["duplicate_mints_dropped"] == 0

    survivors = apply_provider_dedupe_once(drained, dedupe)

    # The live run produced ZERO here. Seventeen is the whole defect.
    assert len(survivors) == 17
    assert [c["token_mint"] for c in survivors] == [
        mint for mint, _ in PRESERVED_ACCEPTED]
    assert dedupe.snapshot()["duplicate_mints_dropped"] == 0


def test_8_preserved_population_reaches_the_watchlist_as_seventeen_entries():
    """The same 17, carried all the way to real watch entries.

    Seeded as ``LIVE_YELLOWSTONE`` paid candidates, which is the provenance the
    watchlist accepts today.  See
    ``test_helius_provenance_is_rejected_by_the_watchlist_accept_list`` for the
    separate, still-open blocker that stops the HELIUS provenance here.
    """

    dedupe = ProviderCandidateDedupe()
    drained = _admit(dedupe, PRESERVED_ACCEPTED, identity=CHAINSTACK_IDENTITY)
    survivors = apply_provider_dedupe_once(drained, dedupe)
    assert len(survivors) == 17

    watchlist = Watchlist(max_size=64)
    seeded = [watchlist.seed(c, seeded_at_utc=NOW) for c in survivors]

    assert all(entry is not None for entry in seeded)
    assert len(watchlist.all_entries()) == 17
    assert {e.token_mint for e in watchlist.all_entries()} == {
        mint for mint, _ in PRESERVED_ACCEPTED}


def test_9_candidate_admission_counts_flow_into_tracker_totals():
    dedupe = ProviderCandidateDedupe()
    drained = _admit(dedupe, PRESERVED_ACCEPTED, identity=CHAINSTACK_IDENTITY)
    survivors = apply_provider_dedupe_once(drained, dedupe)

    budget = FreeTierCreditBudget(
        FreeTierCreditBudgetCaps(max_candidates_total=64), discord_enabled=False)
    budget.record_provider_candidates(len(survivors))

    # Live, this recorded 0 and every downstream total stayed empty.
    assert budget.snapshot()["candidate_count"] == 17
    assert budget.stop_reason is None

    watchlist = Watchlist(max_size=64)
    for candidate in survivors:
        watchlist.seed(candidate, seeded_at_utc=NOW)
    assert len(watchlist.active_entries()) == 17


def test_10_no_duplicate_candidate_is_created():
    dedupe = ProviderCandidateDedupe()
    drained = _admit(dedupe, PRESERVED_ACCEPTED, identity=CHAINSTACK_IDENTITY)
    survivors = apply_provider_dedupe_once(drained, dedupe)

    # Same objects, same order -- the pass filters, it never clones or re-emits.
    assert [id(c) for c in survivors] == [id(c) for c in drained]
    mints = [c["token_mint"] for c in survivors]
    assert len(mints) == len(set(mints)) == 17

    watchlist = Watchlist(max_size=64)
    for candidate in survivors:
        watchlist.seed(candidate, seeded_at_utc=NOW)
    # Re-seeding the identical population creates no second entry.
    for candidate in survivors:
        watchlist.seed(candidate, seeded_at_utc=NOW)
    assert len(watchlist.all_entries()) == 17


# ---------------------------------------------------------------------------
# 11 -- Helius filter / decoder / credits / continuity / HTTP recovery
# ---------------------------------------------------------------------------


def test_11_candidate_projection_is_untouched_except_for_the_stamp():
    mint, signature = PRESERVED_ACCEPTED[7]
    event = _paid_event(mint, signature)

    # The decoder's projection itself gains NOTHING: the stamp is written only
    # at admission, so every pre-admission consumer (including the bounded
    # quarantine buffer's byte budget) sees a byte-identical candidate.
    projected = event_to_candidate(event)
    assert PROVIDER_DEDUPE_APPLIED_FIELD not in projected

    dedupe = ProviderCandidateDedupe()
    drained = _admit(dedupe, [(mint, signature)])
    admitted = dict(drained[0])
    admitted.pop("provider_handoff", None)
    assert admitted.pop(PROVIDER_DEDUPE_APPLIED_FIELD) is True
    assert admitted == projected

    # And the session pass mutates nothing else on the way through.
    before = dict(drained[0])
    apply_provider_dedupe_once(drained, dedupe)
    assert dict(drained[0]) == before


def test_11_helius_source_and_recovery_contracts_are_unchanged():
    # Tight filter, decoder identity and HTTP recovery are still required for
    # production, and the dedupe modules import none of that machinery.
    selection = helius_source.load_source_selection(
        {helius_source.MIGRATION_SOURCE_ENV: helius_source.HELIUS_PRIMARY})
    verdict = helius_source.validate_production_source_contract(
        selection=selection,
        helius_configured=True,
        http_recovery_enabled=False,
        subscription_request=helius_source.approved_tight_subscription_request(1),
    )
    assert verdict.refusals == ("HELIUS_HTTP_RECOVERY_REQUIRED",)
    assert helius_source.tight_filter_is_locked(
        helius_source.approved_tight_subscription_request(1))

    source = inspect.getsource(apply_provider_dedupe_once)
    source += inspect.getsource(mark_provider_dedupe_applied)
    source += inspect.getsource(provider_dedupe_already_applied)
    for foreign in ("helius", "credit", "byte_budget", "continuity",
                    "recovery", "birdeye"):
        assert foreign not in source.lower()


# ---------------------------------------------------------------------------
# 12 -- delivery / presentation surfaces never see the stamp
# ---------------------------------------------------------------------------


def test_12_stamp_never_reaches_watch_state_or_any_delivery_surface():
    dedupe = ProviderCandidateDedupe()
    drained = _admit(dedupe, [PRESERVED_ACCEPTED[8]], identity=CHAINSTACK_IDENTITY)
    survivors = apply_provider_dedupe_once(drained, dedupe)

    watchlist = Watchlist(max_size=4)
    entry = watchlist.seed(survivors[0], seeded_at_utc=NOW)
    assert entry is not None

    # The watch entry is a fixed-field projection: the stamp is a producer-side
    # bookkeeping fact and stops at the watchlist boundary.
    assert PROVIDER_DEDUPE_APPLIED_FIELD not in asdict(entry)
    assert PROVIDER_DEDUPE_APPLIED_FIELD not in entry.to_candidate()

    # Nor does it reach the durable provider-handoff artifact, whose record is
    # a fixed three-field projection of the candidate.
    handoff = inspect.getsource(SingleGrpcPumpSwapDiscovery._emit_handoff)
    assert PROVIDER_DEDUPE_APPLIED_FIELD not in handoff


# ---------------------------------------------------------------------------
# Anti-regression: the magic negative source test must never come back
# ---------------------------------------------------------------------------


def test_session_boundary_never_decides_dedupe_from_a_source_label():
    source = inspect.getsource(producer_session.run_producer)
    assert 'source_label != "GRPC"' not in source
    assert "source_label !=" not in source
    # The one-pass rule is the only thing standing between a source rename and
    # another 100% candidate loss.
    assert "apply_provider_dedupe_once(candidates, provider_dedupe)" in source


def test_the_retired_source_label_gate_reproduces_the_live_zero_alert_failure():
    """Proof that this fixture really is the live defect, not a lookalike.

    Replays the exact retired predicate (``source_label != "GRPC"`` with an
    unconditional second ``accept``) over the SAME 17 admitted candidates and
    the SAME dedupe instance. It reproduces the live numbers precisely:
    17 accepted at the provider, 0 surviving the session,
    ``duplicate_mints_dropped == 17``.
    """

    dedupe = ProviderCandidateDedupe()
    drained = _admit(dedupe, PRESERVED_ACCEPTED)
    assert len(drained) == 17

    source_label = "HELIUS"                       # what the cutover renamed it to
    if source_label != "GRPC":                    # the retired gate, verbatim
        survivors = [
            cand for cand in drained
            if dedupe.accept(event_id=cand.get("source_ref"),
                             mint=cand.get("token_mint"))
        ]
    else:
        survivors = list(drained)

    assert survivors == []                        # live: 0 candidates watched
    assert dedupe.snapshot()["duplicate_mints_dropped"] == 17
    assert dedupe.snapshot()["duplicate_events_dropped"] == 0

    # The shipped rule, same inputs, same shared instance: all 17 survive.
    fresh = ProviderCandidateDedupe()
    assert len(apply_provider_dedupe_once(_admit(fresh, PRESERVED_ACCEPTED),
                                          fresh)) == 17
    assert fresh.snapshot()["duplicate_mints_dropped"] == 0


def test_helius_provenance_is_accepted_by_the_watchlist_accept_list():
    """The formerly-pinned residual blocker, inverted on its fix.

    ``event_to_candidate`` labels a Helius candidate ``LIVE_HELIUS`` and the
    centralized closed-set contract (PHX2.models.discovery_provenance) now
    names it an equal-authority live provenance, so the seed boundary admits
    it.  Unknown provenance stays rejected ``INVALID_CANDIDATE`` — the closed
    set widened by exactly one known value; it did not open.
    """

    dedupe = ProviderCandidateDedupe()
    drained = _admit(dedupe, [PRESERVED_ACCEPTED[9]])
    survivors = apply_provider_dedupe_once(drained, dedupe)
    assert len(survivors) == 1                        # the dedupe fix works
    assert survivors[0]["discovery_provenance"] == "LIVE_HELIUS"

    watchlist = Watchlist(max_size=4)
    entry, outcome = watchlist.seed_with_outcome(survivors[0], seeded_at_utc=NOW)

    assert entry is not None
    assert outcome == "ADMITTED"
    assert entry.discovery_provenance == "LIVE_HELIUS"
    assert len(watchlist.all_entries()) == 1
    # Unknown provenance remains explicitly rejected at the same boundary.
    unknown = {
        "token_mint": PRESERVED_ACCEPTED[10][0],
        "candidate_id": "unknown_provenance_probe",
        "source_ref": "unknown_provenance_probe",
        "discovery_utc": NOW,
        "discovery_provenance": "EXPERIMENTAL_UNKNOWN_SOURCE",
    }
    rejected_entry, rejected_outcome = watchlist.seed_with_outcome(
        unknown, seeded_at_utc=NOW)
    assert rejected_entry is None
    assert rejected_outcome == "INVALID_CANDIDATE"


def test_dedupe_proof_is_a_closed_boolean_never_a_truthy_value():
    for spoof in ("true", 1, "TRUE", [1], {"x": 1}, None, 0, False):
        assert not provider_dedupe_already_applied(
            {"token_mint": "m", PROVIDER_DEDUPE_APPLIED_FIELD: spoof})
    assert not provider_dedupe_already_applied({"token_mint": "m"})
    assert not provider_dedupe_already_applied(None)
    assert not provider_dedupe_already_applied("not-a-mapping")
    assert provider_dedupe_already_applied(
        mark_provider_dedupe_applied({"token_mint": "m"}))
