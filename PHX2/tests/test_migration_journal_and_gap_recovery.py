"""Durable migration journal, confirmed-slot cursor, and exact gap recovery.

The journal is the restart-safe answer to "which migrations do we already hold
evidence for, and from which slot forward is coverage unproven".  Its whole
value is in the failure cases, so those are what this module pins: a crash
between evidence receipt and cursor commit, a torn trailing write, a cursor
that claims more ground than the evidence supports, a journal that survived a
lost cursor, overlapping recovery requests, and a recovered row the live socket
had already delivered.

Nothing here writes, reads, or references the paid Telegram ledger.  Recovered
evidence is EVIDENCE: it re-enters the ordinary admission path and authorizes
nothing by itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from PHX2.free_tier_producer import migration_journal as mj
from PHX2.free_tier_producer import source_continuity as SC


MINT_A = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAApump"
MINT_B = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBpump"
SIG_A = "sigAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
SIG_B = "sigBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"


def _journal(tmp_path: Path, **kwargs) -> mj.DurableMigrationJournal:
    return mj.DurableMigrationJournal(
        journal_path=tmp_path / mj.JOURNAL_BASENAME,
        cursor_path=tmp_path / mj.CURSOR_BASENAME,
        now_fn=lambda: "2026-07-31T00:00:00Z",
        **kwargs)


def _record(*, mint=MINT_A, signature=SIG_A, slot=1_000,
            kind=mj.MIGRATION_KIND_V2, source=mj.SOURCE_LIVE_STREAM):
    record = mj.build_journal_record(
        mint=mint, signature=signature, migration_slot=slot,
        migration_kind=kind, source=source,
        block_time_utc="2026-07-31T00:00:00Z",
        now_fn=lambda: "2026-07-31T00:00:00Z")
    assert record is not None
    return record


# ---------------------------------------------------------------------------
# record contract
# ---------------------------------------------------------------------------


def test_record_carries_only_sanitized_evidence(tmp_path: Path) -> None:
    record = _record()
    body = record.to_record()
    assert set(body) == {
        "kind", "schema_version", "mint", "signature", "migration_slot",
        "block_time_utc", "migration_kind", "migration_proof_digest",
        "source", "persisted_at_utc"}
    assert body["migration_kind"] in mj.MIGRATION_KINDS
    assert body["source"] in mj.JOURNAL_SOURCES
    # A derived digest is evidence identity, never a secret.
    assert len(body["migration_proof_digest"]) == 64
    text = json.dumps(body).lower()
    for needle in ("://", "api-key", "bearer", "authorization", "birdeye"):
        assert needle not in text


def test_invalid_records_are_refused_not_coerced() -> None:
    assert mj.build_journal_record(
        mint="", signature=SIG_A, migration_slot=1,
        migration_kind=mj.MIGRATION_KIND_V1) is None
    assert mj.build_journal_record(
        mint=MINT_A, signature=SIG_A, migration_slot=-1,
        migration_kind=mj.MIGRATION_KIND_V1) is None
    assert mj.build_journal_record(
        mint=MINT_A, signature=SIG_A, migration_slot=1,
        migration_kind="not_a_migration") is None
    assert mj.build_journal_record(
        mint=MINT_A, signature=SIG_A, migration_slot=1,
        migration_kind=mj.MIGRATION_KIND_V1, source="SOMETHING") is None
    # Booleans are not slots.
    assert mj.build_journal_record(
        mint=MINT_A, signature=SIG_A, migration_slot=True,
        migration_kind=mj.MIGRATION_KIND_V1) is None


def test_both_migration_kinds_are_supported() -> None:
    for kind in (mj.MIGRATION_KIND_V1, mj.MIGRATION_KIND_V2):
        assert _record(kind=kind).migration_kind == kind


# ---------------------------------------------------------------------------
# append + idempotence
# ---------------------------------------------------------------------------


def test_append_commits_and_indexes(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    result = journal.append(_record(slot=1_000))
    assert result.outcome == mj.APPEND_COMMITTED
    assert journal.has_signature(SIG_A) is True
    assert journal.has_mint(MINT_A) is True
    assert journal.highest_journalled_slot == 1_000
    assert journal.record_count == 1


def test_duplicate_signature_replay_is_idempotent(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    assert journal.append(_record()).outcome == mj.APPEND_COMMITTED
    before = journal.journal_path.read_bytes()
    for _ in range(5):
        again = journal.append(_record())
        assert again.outcome == mj.APPEND_DUPLICATE
    assert journal.journal_path.read_bytes() == before
    assert journal.record_count == 1
    assert journal.duplicate_appends == 5


def test_one_mint_may_carry_two_distinct_signatures(tmp_path: Path) -> None:
    """Hiding a second proof for the same mint would lose evidence."""

    journal = _journal(tmp_path)
    assert journal.append(
        _record(signature=SIG_A, slot=10)).outcome == mj.APPEND_COMMITTED
    assert journal.append(
        _record(signature=SIG_B, slot=11)).outcome == mj.APPEND_COMMITTED
    assert journal.record_count == 2
    assert journal.highest_journalled_slot == 11


def test_recovered_live_and_backfill_duplicate_writes_once(
        tmp_path: Path) -> None:
    """The same signature from the live socket and from gap recovery."""

    journal = _journal(tmp_path)
    live = _record(source=mj.SOURCE_LIVE_STREAM, slot=2_000)
    recovered = _record(source=mj.SOURCE_GAP_RECOVERY, slot=2_000)
    assert journal.append(live).outcome == mj.APPEND_COMMITTED
    assert journal.append(recovered).outcome == mj.APPEND_DUPLICATE
    assert journal.record_count == 1
    lines = [line for line in
             journal.journal_path.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["source"] == mj.SOURCE_LIVE_STREAM


def test_invalid_payload_is_rejected_and_counted(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    result = journal.append({"kind": "SOMETHING_ELSE"})
    assert result.outcome == mj.APPEND_REJECTED_INVALID
    assert journal.record_count == 0
    assert journal.rejected_records == 1


# ---------------------------------------------------------------------------
# cursor: never ahead of the evidence
# ---------------------------------------------------------------------------


def test_cursor_refuses_to_advance_past_committed_evidence(
        tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_record(slot=500))
    ahead = journal.commit_cursor(900)
    assert ahead.outcome == mj.COMMIT_REFUSED_AHEAD
    assert journal.last_confirmed_slot is None
    ok = journal.commit_cursor(500)
    assert ok.outcome == mj.COMMIT_OK
    assert journal.last_confirmed_slot == 500


def test_cursor_never_regresses(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_record(signature=SIG_A, slot=100))
    journal.append(_record(signature=SIG_B, slot=200))
    assert journal.commit_cursor(200).outcome == mj.COMMIT_OK
    back = journal.commit_cursor(100)
    assert back.outcome == mj.COMMIT_REFUSED_REGRESSION
    assert journal.last_confirmed_slot == 200


def test_invalid_slot_is_refused(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_record(slot=10))
    for bad in (None, -1, "10", 1.5, True):
        assert journal.commit_cursor(bad).outcome == mj.COMMIT_REFUSED_INVALID


# ---------------------------------------------------------------------------
# restart / crash / corruption
# ---------------------------------------------------------------------------


def test_crash_between_evidence_receipt_and_cursor_commit(
        tmp_path: Path) -> None:
    """Evidence landed; the process died before the cursor was written.

    On restart the journal is AHEAD of the (absent) cursor and the cursor is
    pulled up to the proven evidence -- never the other way round.
    """

    journal = _journal(tmp_path)
    journal.append(_record(signature=SIG_A, slot=700))
    journal.append(_record(signature=SIG_B, slot=701))
    assert not journal.cursor_path.exists()      # the crash point
    journal.close()

    restarted = _journal(tmp_path)
    verdict = restarted.load()
    assert verdict == mj.CURSOR_JOURNAL_AHEAD
    assert restarted.record_count == 2
    assert restarted.last_confirmed_slot == 701
    assert restarted.highest_journalled_slot == 701


def test_restart_restores_the_last_confirmed_slot(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_record(slot=4_242))
    assert journal.commit_cursor(4_242).outcome == mj.COMMIT_OK
    journal.close()

    restarted = _journal(tmp_path)
    assert restarted.load() == mj.CURSOR_CONSISTENT
    assert restarted.last_confirmed_slot == 4_242
    assert restarted.has_signature(SIG_A) is True


def test_restart_from_backup_when_the_primary_cursor_is_unreadable(
        tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_record(signature=SIG_A, slot=10))
    journal.append(_record(signature=SIG_B, slot=20))
    assert journal.commit_cursor(10).outcome == mj.COMMIT_OK
    assert journal.commit_cursor(20).outcome == mj.COMMIT_OK
    backup = journal.cursor_path.with_name(journal.cursor_path.name + ".bak")
    assert backup.exists()
    journal.close()

    journal.cursor_path.write_text("{ torn", encoding="utf-8")
    restarted = _journal(tmp_path)
    verdict = restarted.load()
    assert verdict in (mj.CURSOR_RESTORED_FROM_BACKUP, mj.CURSOR_JOURNAL_AHEAD)
    assert restarted.last_confirmed_slot == 20


def test_cursor_ahead_of_journal_is_rejected_and_clamped(
        tmp_path: Path) -> None:
    """A cursor claiming ground the evidence does not support is not trusted."""

    journal = _journal(tmp_path)
    journal.append(_record(slot=300))
    journal.commit_cursor(300)
    journal.close()

    # Forge a VALID, correctly-digested cursor far ahead of the evidence.
    document = json.loads(
        (tmp_path / mj.CURSOR_BASENAME).read_text(encoding="utf-8"))
    document["last_confirmed_slot"] = 999_999
    document.pop("payload_digest")
    import hashlib
    body = json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")
    document["payload_digest"] = hashlib.sha256(body).hexdigest()
    (tmp_path / mj.CURSOR_BASENAME).write_text(
        json.dumps(document), encoding="utf-8")
    backup = tmp_path / (mj.CURSOR_BASENAME + ".bak")
    if backup.exists():
        backup.unlink()

    restarted = _journal(tmp_path)
    assert restarted.load() == mj.CURSOR_AHEAD_OF_JOURNAL
    assert restarted.last_confirmed_slot == 300


def test_a_cursor_that_outlived_its_journal_claims_nothing(
        tmp_path: Path) -> None:
    """An EMPTY journal supports no cursor position at all."""

    journal = _journal(tmp_path)
    journal.append(_record(slot=800))
    assert journal.commit_cursor(800).outcome == mj.COMMIT_OK
    journal.close()

    # The journal is lost/truncated; the cursor survives and verifies.
    (tmp_path / mj.JOURNAL_BASENAME).write_text("", encoding="utf-8")

    restarted = _journal(tmp_path)
    assert restarted.load() == mj.CURSOR_AHEAD_OF_JOURNAL
    assert restarted.record_count == 0
    assert restarted.highest_journalled_slot is None
    assert restarted.last_confirmed_slot is None
    # And with nothing proven it claims no prior ground either.
    assert restarted.missing_range(900) is None


def test_a_torn_trailing_write_cannot_corrupt_prior_state(
        tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_record(signature=SIG_A, slot=1))
    journal.append(_record(signature=SIG_B, slot=2))
    journal.close()

    # Simulate a torn final record: a partial line with no newline.
    with open(tmp_path / mj.JOURNAL_BASENAME, "a", encoding="utf-8") as handle:
        handle.write('{"kind": "PHX2_MIGRATION_JOURNAL_RECORD", "mint": "AA')

    restarted = _journal(tmp_path)
    restarted.load()
    assert restarted.record_count == 2          # both earlier records survive
    assert restarted.malformed_lines == 1
    assert restarted.highest_journalled_slot == 2
    assert restarted.last_confirmed_slot == 2


def test_a_malformed_interior_line_is_skipped_not_fatal(
        tmp_path: Path) -> None:
    path = tmp_path / mj.JOURNAL_BASENAME
    good_a = json.dumps(_record(signature=SIG_A, slot=5).to_record(),
                        sort_keys=True)
    good_b = json.dumps(_record(signature=SIG_B, slot=6).to_record(),
                        sort_keys=True)
    path.write_text("\n".join((good_a, "}{ not json", good_b)) + "\n",
                    encoding="utf-8")
    journal = _journal(tmp_path)
    journal.load()
    assert journal.record_count == 2
    assert journal.malformed_lines == 1
    assert journal.highest_journalled_slot == 6


def test_a_schema_invalid_line_is_counted_malformed(tmp_path: Path) -> None:
    path = tmp_path / mj.JOURNAL_BASENAME
    path.write_text(json.dumps({"kind": "OTHER", "mint": MINT_A}) + "\n",
                    encoding="utf-8")
    journal = _journal(tmp_path)
    journal.load()
    assert journal.record_count == 0
    assert journal.malformed_lines == 1


# ---------------------------------------------------------------------------
# missing ranges
# ---------------------------------------------------------------------------


def test_missing_range_is_detected_before_continuity_advances(
        tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_record(slot=1_000))
    journal.commit_cursor(1_000)
    assert journal.missing_range(1_001) is None       # exact continuation
    assert journal.missing_range(1_000) is None       # duplicate / replay
    assert journal.missing_range(1_010) == (1_001, 1_009)


def test_a_fresh_journal_claims_no_prior_ground(tmp_path: Path) -> None:
    """Live-only startup must not invent a gap it never owned."""

    journal = _journal(tmp_path)
    journal.load()
    assert journal.last_confirmed_slot is None
    assert journal.missing_range(5_000_000) is None


def test_exact_missing_slot_closure(tmp_path: Path) -> None:
    """A one-slot hole is closed by proving exactly that slot."""

    tracker = SC.SourceContinuityTracker(now_fn=lambda: "2026-07-31T00:00:00Z")
    tracker.note_slot(100, processed=True, durable=True)
    tracker.note_disconnect(reason_class=SC.REASON_PROVIDER_DISCONNECT)
    gap = tracker.note_slot(102, processed=True)
    assert gap is not None
    assert (gap.gap_from_slot, gap.gap_to_slot) == (101, 101)
    assert tracker.continuity_state() == SC.GAP_DETECTED

    tracker.apply_recovered_range(101, 101)
    assert tracker.continuity_state() == SC.NO_GAP
    assert tracker.coverage_is_proven_continuous() is True
    assert tracker.open_gaps() == []


def test_overlapping_gap_requests_never_re_ask_for_proven_ground(
        tmp_path: Path) -> None:
    tracker = SC.SourceContinuityTracker(now_fn=lambda: "2026-07-31T00:00:00Z")
    tracker.note_slot(200, processed=True, durable=True)
    tracker.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    gap = tracker.note_slot(211, processed=True)
    assert (gap.gap_from_slot, gap.gap_to_slot) == (201, 210)

    first = tracker.replay_request()
    assert first == (gap.gap_id, 201)
    tracker.mark_recovery_requested(gap.gap_id, 201)

    # A partial recovery proved the FRONT of the range.
    tracker.apply_recovered_range(201, 205)
    second = tracker.replay_request()
    assert second == (gap.gap_id, 206)          # only the remainder

    # An overlapping re-application of already-proven ground is idempotent.
    tracker.apply_recovered_range(201, 205)
    assert tracker.replay_request() == (gap.gap_id, 206)
    tracker.apply_recovered_range(206, 210)
    assert tracker.continuity_state() == SC.NO_GAP


def test_unrecoverable_gap_reports_degraded_and_never_stops_the_stream(
        tmp_path: Path) -> None:
    tracker = SC.SourceContinuityTracker(
        now_fn=lambda: "2026-07-31T00:00:00Z", max_recovery_attempts=2)
    tracker.note_slot(300, processed=True, durable=True)
    tracker.note_disconnect(reason_class=SC.REASON_PROVIDER_ERROR)
    gap = tracker.note_slot(320, processed=True)

    for _ in range(2):
        request = tracker.replay_request()
        assert request is not None
        tracker.mark_recovery_requested(gap.gap_id, request[1])
        tracker.mark_recovery_failed(
            gap.gap_id, reason=SC.FAILURE_HTTP_PROVIDER)

    assert tracker.replay_request() is None       # bounded budget spent
    assert tracker.continuity_state() in SC.TERMINAL_GAP_STATES
    assert tracker.coverage_is_proven_continuous() is False

    # DEGRADED, not fatal: forward ingestion keeps working and keeps proving.
    assert tracker.note_slot(321, processed=True) is None
    assert tracker.snapshot()["open_gap_count"] == 1
    assert SC.display_status_for(
        transport_connected=True,
        continuity_state=tracker.continuity_state(),
    ) == "CONNECTED_COVERAGE_UNRESOLVED"


# ---------------------------------------------------------------------------
# observability
# ---------------------------------------------------------------------------


def test_snapshot_is_redaction_safe_and_complete(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.load()
    journal.append(_record(slot=77))
    journal.commit_cursor(77)
    snapshot = journal.snapshot()
    for key in ("record_count", "last_confirmed_slot",
                "highest_journalled_slot", "cursor_verdict",
                "last_journal_commit_utc", "malformed_lines",
                "duplicate_appends", "durability_failures"):
        assert key in snapshot
    assert snapshot["last_confirmed_slot"] == 77
    body = json.dumps(snapshot, sort_keys=True).lower()
    for needle in ("://", "api-key", "bearer", "authorization"):
        assert needle not in body


def test_the_journal_never_references_the_paid_ledger() -> None:
    """Structural proof: the module cannot touch delivery state.

    The scan walks the AST -- imports, identifiers and string LITERALS -- and
    deliberately skips docstrings and comments, because this module's prose
    states the negative claim ("never mutate the paid Telegram ledger") and a
    naive text scan would flag its own disclaimer.
    """

    import ast

    tree = ast.parse(Path(mj.__file__).read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))

    forbidden = ("ping_dedupe", "ledger", "telegram", "discord", "webhook")
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            haystack = node.value.lower()
        elif isinstance(node, ast.Name):
            haystack = node.id.lower()
        elif isinstance(node, ast.Attribute):
            haystack = node.attr.lower()
        elif isinstance(node, ast.alias):
            haystack = (node.name + " " + (node.asname or "")).lower()
        elif isinstance(node, ast.ImportFrom):
            haystack = str(node.module or "").lower()
        else:
            continue
        for token in forbidden:
            if token in haystack:
                offenders.append((token, haystack))
    assert offenders == [], offenders
