"""Boundary-less authenticated cursor documents must quarantine, not degrade.

``BL-1`` BOUNDARY_LESS_AUTHENTICATED_CURSOR_VALIDATES (2026-07-20 re-audit, LOW).

The certified R1-R5 repair fixed every *writer*: ``begin_stream_attempt`` pins a
pre-attempt boundary before a stream exists, ``mark_disconnect`` and
``mark_recovery_failed`` derive their boundary from the attempt record, and
``mark_overlap_proven`` demands exact-equality replay proof.  No writer can now
emit an episode that claims recovery while naming no position to recover from.

The *reader* never learned the same rule.  ``validate_cursor_record`` checks
field types, digests, timestamps and one cross-field pair (identity slot vs
``last_durable_slot``) -- but nothing that ties the recovery, attempt and
overlap-proof groups to each other.  A hand-authored document with a correct
``record_digest`` therefore validates while carrying, for example,
``recovery_required=true`` and ``recovery_from_slot=null``.

That state is not inert.  ``StreamCursorState.safe_resume_slot`` collects
candidate positions and returns ``min(...)``; with no boundary to contribute,
the only candidate left is ``last_durable_slot`` -- the high-water mark.  The
document silently resolves to "resume from the newest slot we handled", which is
precisely the self-certifying position the whole boundary contract exists to
forbid.  The docstring on ``mark_recovery_failed`` records that pre-repair
generations really did produce this shape.

The cursor is send-blocked and cannot reach live head in this state, which is
why the finding is LOW rather than HIGH.  But an internally inconsistent
authenticated document should QUARANTINE -- preserving evidence, locking writes
and naming a closed-set reason -- rather than resolving to an ambiguous
position that merely happens to be blocked by a different gate.

Every test here is offline: hand-authored documents under ``tmp_path``, no
channel, no provider, no network, no credential, no send.
"""

from __future__ import annotations

import pytest

from PHX2.free_tier_producer import checkpoint_envelope as cpe
from PHX2.free_tier_producer import stream_cursor as sc
from PHX2.free_tier_producer.stream_cursor import GrpcStreamCursorStore

BASE = 317_402_991

IDENTITY_DIGEST = sc.compute_subscription_identity_digest(
    source_kind="YELLOWSTONE_GRPC_PRIMARY",
    commitment="CONFIRMED",
    transaction_filter_name="phx2_pumpswap_create_pool",
    account_include=("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",),
    program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
    migration_versions_supported=("migrate", "migrate_v2"),
    decoder_schema_version="phx2_create_pool_v1",
)


# ---------------------------------------------------------------------------
# hand-authored, correctly digested documents
# ---------------------------------------------------------------------------

def _identity(slot: int, seed: int = 0) -> str:
    return sc.build_stream_event_identity(slot=slot, signature=f"sig{seed}")


def _v2_record(**overrides) -> dict:
    """A CONSISTENT v2 record, then whatever the caller deliberately breaks."""

    now = cpe.utc_now_iso()
    state = sc.StreamCursorState(
        subscription_identity_digest=IDENTITY_DIGEST,
        last_durable_slot=BASE,
        last_durable_event_identity=_identity(BASE),
        last_durable_signature="sig0",
        processed_event_ids_in_boundary_slot=[_identity(BASE)],
        recent_event_identities=[_identity(BASE)],
        updated_at_utc=now,
    )
    record = state.to_record()
    record.update(overrides)
    record["record_digest"] = cpe.build_record_digest(
        sc.CHECKPOINT_KIND_STREAM_CURSOR, record)
    return record


def _v1_record(**overrides) -> dict:
    """A genuine schema-v1 body: no attempt group, no terminal, no generation."""

    now = cpe.utc_now_iso()
    record = {
        "record_kind": sc.CURSOR_RECORD_KIND,
        "stream_source": sc.STREAM_SOURCE_YELLOWSTONE,
        "subscription_identity_digest": IDENTITY_DIGEST,
        "commitment": "CONFIRMED",
        "last_durable_slot": BASE,
        "last_durable_event_identity": _identity(BASE),
        "last_durable_signature": "sig0",
        "processed_event_ids_in_boundary_slot": [_identity(BASE)],
        "recent_event_identities": [_identity(BASE)],
        # v1's never-assigned contiguity field, read forward as the boundary.
        "last_contiguous_slot": None,
        "stream_generation": 3,
        "updated_at_utc": now,
        "last_disconnect_at_utc": None,
        "recovery_required": False,
        "recovery_from_slot": None,
        "recovery_target_slot": None,
        "recovery_status": sc.RECOVERY_NOT_REQUIRED,
        "recovery_reason": sc.REASON_NONE,
        "replayed_event_count": 4,
        "duplicate_replay_count": 1,
        "backfilled_event_count": 0,
        "gap_detected_total": 2,
        "gap_closed_total": 2,
    }
    record.update(overrides)
    record["record_digest"] = cpe.build_record_digest(
        sc.CHECKPOINT_KIND_STREAM_CURSOR, record)
    return record


def _write_document(path, record, *, schema_version=sc.STREAM_CURSOR_SCHEMA_V2,
                    generation: int = 7) -> None:
    now = cpe.utc_now_iso()
    header = cpe.build_envelope_header(
        checkpoint_kind=sc.CHECKPOINT_KIND_STREAM_CURSOR,
        schema_version=schema_version,
        payload_encoding=cpe.PAYLOAD_ENCODING_DOCUMENT,
        generation=generation,
        record_digests=[record["record_digest"]],
        created_at_utc=now,
        updated_at_utc=now,
        previous_generation_digest=None,
        source_id=path.name,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cpe.encode_checkpoint_document(header, [record]),
                    encoding="utf-8", newline="\n")


def _store(tmp_path, record=None, *, schema_version=sc.STREAM_CURSOR_SCHEMA_V2):
    """Build a store over a state dir, optionally seeded with one document."""

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    if record is not None:
        _write_document(state_dir / sc.CURSOR_PRIMARY_BASENAME, record,
                        schema_version=schema_version)
    store = sc.build_cursor_store(
        state_dir=state_dir, subscription_identity_digest=IDENTITY_DIGEST)
    store.load()
    return store


# ---------------------------------------------------------------------------
# the five inconsistent shapes named by the finding
# ---------------------------------------------------------------------------

INCONSISTENT_CASES = {
    # 1. recovery claimed with no boundary at all: safe_resume_slot() silently
    #    resolves to the high-water mark.
    "recovery_required_without_boundary": _v2_record(
        recovery_required=True,
        recovery_status=sc.RECOVERY_REQUIRED,
        recovery_reason=sc.REASON_PROVIDER_DISCONNECT,
        recovery_generation=2,
        recovery_from_slot=None,
        attempt_pinned_boundary_slot=None,
    ),
    # 2. an attempt is open but never recorded what it asked the provider for.
    "attempt_open_without_requested_slot": _v2_record(
        attempt_open=True,
        attempt_generation=5,
        attempt_requested_from_slot=None,
        attempt_pinned_boundary_slot=BASE - 40,
    ),
    # 3. a replay was requested but no boundary was pinned to protect.
    "attempt_open_without_pinned_boundary": _v2_record(
        attempt_open=True,
        attempt_generation=5,
        attempt_requested_from_slot=BASE - 40,
        attempt_pinned_boundary_slot=None,
    ),
    # 4. terminal recovery with no reason: a dead position that cannot say why.
    "terminal_without_reason": _v2_record(
        recovery_required=True,
        recovery_terminal=True,
        recovery_status=sc.RECOVERY_FAILED,
        recovery_reason=sc.REASON_NONE,
        recovery_generation=2,
        recovery_from_slot=BASE - 40,
    ),
    # 5. an attempt is open with no attempt generation to bind a proof to.
    "attempt_open_without_generation": _v2_record(
        attempt_open=True,
        attempt_generation=0,
        attempt_requested_from_slot=BASE - 40,
        attempt_pinned_boundary_slot=BASE - 40,
    ),
    # 6. an overlap proof that names no boundary it proved.
    "overlap_proven_without_boundary": _v2_record(
        overlap_proven_generation=2,
        recovery_generation=2,
        last_proven_replay_boundary_slot=None,
        attempt_generation=1,
    ),
    # 7. a proof from an episode that has not happened yet.
    "overlap_proven_generation_ahead": _v2_record(
        overlap_proven_generation=9,
        recovery_generation=2,
        last_proven_replay_boundary_slot=BASE - 40,
        attempt_generation=1,
    ),
    # 7b. a proof with neither an episode nor an attempt behind it.
    #     ``mark_overlap_proven`` refuses unless one of the two is open, so
    #     nothing could have written this.
    "overlap_proven_without_episode_or_attempt": _v2_record(
        overlap_proven_generation=0,
        recovery_generation=0,
        attempt_generation=0,
        last_proven_replay_boundary_slot=BASE - 40,
    ),
    # 8. the current episode is simultaneously open and proven closed.
    "episode_open_and_proven": _v2_record(
        recovery_required=True,
        recovery_status=sc.RECOVERY_REQUIRED,
        recovery_reason=sc.REASON_PROVIDER_DISCONNECT,
        recovery_generation=2,
        recovery_from_slot=BASE - 40,
        overlap_proven_generation=2,
        last_proven_replay_boundary_slot=BASE - 40,
        attempt_generation=1,
    ),
}


@pytest.mark.parametrize("case", sorted(INCONSISTENT_CASES))
def test_inconsistent_authenticated_cursor_quarantines(tmp_path, case):
    """Every named shape must quarantine with a closed-set reason."""

    store = _store(tmp_path / case, INCONSISTENT_CASES[case])

    assert store.quarantined is True
    assert store.load_result.checkpoint_status == cpe.CHECKPOINT_QUARANTINED
    assert store.load_result.checkpoint_quarantined is True
    # Closed-set: never a raw exception string or a path fragment.
    assert store.quarantine_reason in cpe.QUARANTINE_REASONS
    assert store.load_result.checkpoint_quarantine_reason in cpe.QUARANTINE_REASONS


@pytest.mark.parametrize("case", sorted(INCONSISTENT_CASES))
def test_inconsistent_cursor_builds_no_source(tmp_path, case):
    """No channel, stub or subscription may be constructed from this state."""

    store = _store(tmp_path / case, INCONSISTENT_CASES[case])
    decision = store.resume_decision()

    assert decision.builds_source is False
    assert decision.action == sc.RESUME_ACTION_REFUSE_TERMINAL
    # The critical one: an invalid document must NEVER read as "new install".
    assert decision.action != sc.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD
    assert decision.from_slot is None
    assert decision.reason in sc.RECOVERY_REASONS
    assert store.resume_from_slot() is None
    assert store.is_terminal() is True


@pytest.mark.parametrize("case", sorted(INCONSISTENT_CASES))
def test_inconsistent_cursor_locks_writes_and_preserves_evidence(tmp_path, case):
    """Corrupt evidence is never overwritten by a fresh generation."""

    root = tmp_path / case
    store = _store(root, INCONSISTENT_CASES[case])
    primary = root / "state" / sc.CURSOR_PRIMARY_BASENAME
    before = primary.read_bytes()

    with pytest.raises(sc.StreamCursorWriteError):
        store.persist()
    with pytest.raises(sc.StreamCursorWriteError):
        store.commit_event(slot=BASE + 10, identity=_identity(BASE + 10, 9),
                           signature="sig9")

    assert primary.read_bytes() == before
    assert store.snapshot()["grpc_cursor_write_locked"] is True


@pytest.mark.parametrize("case", sorted(INCONSISTENT_CASES))
def test_inconsistent_cursor_blocks_outbound_and_health(tmp_path, case):
    """Send authorization stays closed and the source never reads healthy."""

    store = _store(tmp_path / case, INCONSISTENT_CASES[case])
    snapshot = dict(store.snapshot())

    assert snapshot["grpc_cursor_quarantined"] is True
    authorized, reason = sc.source_health_authorizes_send(snapshot)
    assert authorized is False
    assert reason in sc.RECOVERY_REASONS

    # Even if a caller wrongly reported the stream live, quarantine still wins.
    snapshot["stream_state"] = sc.STATE_LIVE_HEALTHY
    snapshot["live_healthy"] = True
    authorized, reason = sc.source_health_authorizes_send(snapshot)
    assert authorized is False
    assert reason in sc.RECOVERY_REASONS
    # Ingestion is deliberately NOT blocked: recovery needs it to continue.
    assert sc.source_health_permits_ingestion(snapshot) is True


def test_boundaryless_cursor_never_resolves_to_high_water_mark(tmp_path):
    """The exact BL-1 degradation: no boundary must not mean 'the newest slot'."""

    record = INCONSISTENT_CASES["recovery_required_without_boundary"]
    assert record["recovery_required"] is True
    assert record["recovery_from_slot"] is None
    assert record["attempt_pinned_boundary_slot"] is None
    assert record["last_durable_slot"] == BASE

    store = _store(tmp_path, record)

    # Pre-fix this answered BASE -- the high-water mark presented as a safe
    # resume boundary, with nothing having proven the range below it.
    assert store.resume_from_slot() is None
    assert store.resume_decision().builds_source is False


# ---------------------------------------------------------------------------
# compatibility: consistent documents must keep loading
# ---------------------------------------------------------------------------

CONSISTENT_V2_CASES = {
    "clean_live_position": _v2_record(),
    "open_episode_with_boundary": _v2_record(
        recovery_required=True,
        recovery_status=sc.RECOVERY_REQUIRED,
        recovery_reason=sc.REASON_PROVIDER_DISCONNECT,
        recovery_generation=3,
        recovery_from_slot=BASE - 40,
    ),
    "open_attempt_fully_recorded": _v2_record(
        attempt_open=True,
        attempt_generation=6,
        attempt_requested_from_slot=BASE - 40,
        attempt_pinned_boundary_slot=BASE - 40,
    ),
    "closed_episode_with_proof": _v2_record(
        recovery_required=False,
        recovery_status=sc.RECOVERY_CLOSED,
        recovery_reason=sc.REASON_NONE,
        recovery_generation=3,
        overlap_proven_generation=3,
        last_proven_replay_boundary_slot=BASE - 40,
        attempt_generation=6,
        gap_closed_total=3,
    ),
    "terminal_retention_with_reason": _v2_record(
        recovery_required=True,
        recovery_terminal=True,
        recovery_status=sc.RECOVERY_FAILED,
        recovery_reason=sc.REASON_REPLAY_POSITION_TOO_OLD,
        recovery_generation=4,
        recovery_from_slot=BASE - 400,
        replay_first_available_slot=BASE - 100,
    ),
    "no_position_yet": _v2_record(
        last_durable_slot=sc.NO_SLOT,
        last_durable_event_identity=None,
        last_durable_signature=None,
        processed_event_ids_in_boundary_slot=[],
        recent_event_identities=[],
    ),
}

CONSISTENT_V1_CASES = {
    "v1_clean_position": _v1_record(),
    "v1_open_episode_with_boundary": _v1_record(
        recovery_required=True,
        recovery_status=sc.RECOVERY_REQUIRED,
        recovery_reason=sc.REASON_PROVIDER_DISCONNECT,
        recovery_from_slot=BASE - 40,
    ),
    "v1_no_position_yet": _v1_record(
        last_durable_slot=sc.NO_SLOT,
        last_durable_event_identity=None,
        last_durable_signature=None,
        processed_event_ids_in_boundary_slot=[],
        recent_event_identities=[],
    ),
}


@pytest.mark.parametrize("case", sorted(CONSISTENT_V2_CASES))
def test_consistent_v2_documents_still_load(tmp_path, case):
    store = _store(tmp_path / case, CONSISTENT_V2_CASES[case])

    assert store.quarantined is False
    assert store.load_result.checkpoint_status != cpe.CHECKPOINT_QUARANTINED
    assert store.load_result.checkpoint_records_validated == 1
    assert store.generation == 7


@pytest.mark.parametrize("case", sorted(CONSISTENT_V1_CASES))
def test_consistent_v1_documents_still_load(tmp_path, case):
    """A newer optional field being ABSENT is never grounds for rejection."""

    record = CONSISTENT_V1_CASES[case]
    for absent in ("attempt_open", "attempt_generation",
                   "attempt_requested_from_slot",
                   "attempt_pinned_boundary_slot", "recovery_terminal",
                   "recovery_generation", "overlap_proven_generation",
                   "last_proven_replay_boundary_slot"):
        assert absent not in record

    store = _store(tmp_path / case, record,
                   schema_version=sc.STREAM_CURSOR_SCHEMA_V1)

    assert store.quarantined is False
    assert store.load_result.checkpoint_schema_version == \
        sc.STREAM_CURSOR_SCHEMA_V1
    assert store.load_result.checkpoint_records_validated == 1


def test_v1_open_episode_with_boundary_resumes_from_that_boundary(tmp_path):
    """A consistent v1 episode keeps its pinned boundary across the load."""

    store = _store(tmp_path, CONSISTENT_V1_CASES["v1_open_episode_with_boundary"],
                   schema_version=sc.STREAM_CURSOR_SCHEMA_V1)
    decision = store.resume_decision()

    assert store.quarantined is False
    assert decision.action == sc.RESUME_ACTION_SUBSCRIBE_FROM_SLOT
    assert decision.from_slot == BASE - 40
    assert store.resume_from_slot() == BASE - 40


def test_terminal_retention_cursor_still_refuses_rather_than_bootstrapping(tmp_path):
    """Rule 4: terminal is never re-read as a live-head bootstrap."""

    store = _store(tmp_path,
                   CONSISTENT_V2_CASES["terminal_retention_with_reason"])
    decision = store.resume_decision()

    assert store.quarantined is False          # valid document, dead position
    assert decision.action == sc.RESUME_ACTION_REFUSE_TERMINAL
    assert decision.builds_source is False
    assert decision.reason == sc.REASON_REPLAY_POSITION_TOO_OLD
    assert decision.preserved_safe_slot == BASE - 400
    assert store.is_terminal() is True


# ---------------------------------------------------------------------------
# a genuinely new directory is NOT an invalid one
# ---------------------------------------------------------------------------

def test_new_state_dir_remains_distinguishable_from_invalid_cursor(tmp_path):
    """Rule 7: absence bootstraps; invalid content never does."""

    fresh = _store(tmp_path / "fresh")
    assert fresh.quarantined is False
    assert fresh.load_result.checkpoint_status == cpe.CHECKPOINT_NOT_FOUND
    assert fresh.load_result.checkpoint_files_found is False
    fresh_decision = fresh.resume_decision()
    assert fresh_decision.action == sc.RESUME_ACTION_BOOTSTRAP_LIVE_HEAD
    assert fresh_decision.builds_source is True

    broken = _store(tmp_path / "broken",
                    INCONSISTENT_CASES["recovery_required_without_boundary"])
    assert broken.load_result.checkpoint_status == cpe.CHECKPOINT_QUARANTINED
    assert broken.load_result.checkpoint_files_found is True
    assert broken.resume_decision().action == sc.RESUME_ACTION_REFUSE_TERMINAL

    # The two must never collapse onto the same answer.
    assert fresh_decision.action != broken.resume_decision().action


def test_valid_backup_still_rescues_an_inconsistent_primary(tmp_path):
    """Cross-field rejection participates in the normal load matrix."""

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    _write_document(state_dir / sc.CURSOR_PRIMARY_BASENAME,
                    INCONSISTENT_CASES["recovery_required_without_boundary"],
                    generation=8)
    _write_document(
        state_dir / (sc.CURSOR_PRIMARY_BASENAME + sc.CURSOR_BACKUP_SUFFIX),
        CONSISTENT_V2_CASES["open_episode_with_boundary"], generation=7)

    store = sc.build_cursor_store(
        state_dir=state_dir, subscription_identity_digest=IDENTITY_DIGEST)
    store.load()

    assert store.quarantined is False
    assert store.load_result.checkpoint_recovered_from_backup is True
    assert store.resume_from_slot() == BASE - 40
