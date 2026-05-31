"""Stage 30.9.1 post-session projector tests.

Proves the projector joins capture records with dispatch-ledger context on
the stable ``capture_index``, carries the ``dedupe_key`` from the dispatch
context VERBATIM into the emitted Stage 30.8 artifacts, emits a
writer-valid Stage 30.8 bundle (ping + dispatch attempt + error + session
summary), and fails closed (a passive ``INVALID_INPUT`` result, never an
exception) on every documented invalid input. Pure / offline; the only
filesystem touch is writing the projected bundle through the real Stage
30.8.2 writer into a pytest ``tmp_path``.
"""

from __future__ import annotations

from PHX2.stage30.stage30_9_artifact_bridge_models import (
    BRIDGE_REASON_AMBIGUOUS_JOIN,
    BRIDGE_REASON_COUNT_MISMATCH,
    BRIDGE_REASON_MISSING_CANDIDATE_ID,
    BRIDGE_REASON_MISSING_CAPTURE_INDEX,
    BRIDGE_REASON_MISSING_COMPACT_BODY,
    BRIDGE_REASON_MISSING_DEDUPE_KEY,
    BRIDGE_REASON_MISSING_PING_ID,
    BRIDGE_REASON_MISSING_RUN_ID,
    BRIDGE_REASON_MISSING_SESSION_ID,
    BRIDGE_REASON_MISSING_TOKEN_MINT,
    BRIDGE_REASON_NONE,
    BRIDGE_REASON_NON_PRIVATE_WEBHOOK,
    BRIDGE_STATUS_INVALID_INPUT,
    BRIDGE_STATUS_PROJECTED,
    Stage30_9CaptureRecord,
    Stage30_9DispatchContextRecord,
    Stage30_9SessionSummaryCounters,
)
from PHX2.stage30.stage30_9_artifact_projector import (
    project_compact_session_artifact_bundle,
)
from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
    ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
)
from PHX2.stage30.stage30_8_temp_artifact_writer import (
    Stage30_8CompactSessionArtifactBundle,
    WRITE_STATUS_WRITTEN,
    write_compact_session_artifact_bundle,
)


_RUN = "stage30-9-1-test-run"
_SESSION = "stage30-9-1-test-session"
_CREATED = "2026-01-01T00:00:00Z"
_PRIVATE = "PRIVATE_OPERATOR_WEBHOOK"


def _capture(index, *, body=None, status="SENT_OK", webhook=_PRIVATE):
    return Stage30_9CaptureRecord(
        capture_index=index,
        webhook_identity=webhook,
        payload_body_text=(body if body is not None else f"body-{index}"),
        payload_keys=("content",),
        sanitized_transport_status=status,
    )


def _context(index, *, dedupe, ping=None, candidate=None, mint=None,
             ping_session_id=None):
    # The projector now requires ping_id / candidate_id / token_mint, so the
    # helper supplies safe defaults for all three (tests that exercise a
    # missing axis construct the record explicitly).
    return Stage30_9DispatchContextRecord(
        capture_index=index,
        dedupe_key=dedupe,
        candidate_id=(candidate if candidate is not None else f"cand-{index}"),
        ping_id=(ping if ping is not None else f"ping-{index}"),
        token_mint=(mint if mint is not None else f"mint-{index}"),
        ping_session_id=ping_session_id,
    )


def _project(captures, contexts, *, run_id=_RUN, session_id=_SESSION,
             created=_CREATED, counters=None):
    return project_compact_session_artifact_bundle(
        run_id=run_id,
        session_id=session_id,
        artifact_created_at_utc=created,
        capture_records=captures,
        dispatch_context_records=contexts,
        session_summary_counters=counters,
    )


# ---------------------------------------------------------------------------
# 1. Happy projection
# ---------------------------------------------------------------------------


def test_happy_projection_emits_bundle_with_expected_kinds() -> None:
    captures = (_capture(0), _capture(1), _capture(2, status="RATE_LIMITED"))
    contexts = (
        _context(0, dedupe="k1", candidate="c1", mint="m1"),
        _context(1, dedupe="k1", candidate="c1", mint="m1"),
        _context(2, dedupe="k2", candidate="c2", mint="m2"),
    )
    result = _project(captures, contexts)

    assert result.status == BRIDGE_STATUS_PROJECTED
    assert result.reason == BRIDGE_REASON_NONE
    assert result.blocked_field is None
    assert result.ping_artifact_count == 3
    assert result.dispatch_attempt_count == 3
    # One non-SENT_OK send (RATE_LIMITED) -> one error artifact.
    assert result.error_artifact_count == 1

    bundle = result.bundle
    assert isinstance(bundle, Stage30_8CompactSessionArtifactBundle)
    assert bundle.session_id == _SESSION
    assert len(bundle.ping_artifacts) == 3
    assert len(bundle.dispatch_attempt_artifacts) == 3
    assert len(bundle.error_artifacts) == 1
    assert bundle.session_summary is not None

    # The artifact kinds are correctly stamped.
    for ping in bundle.ping_artifacts:
        assert ping.identity.artifact_kind == (
            ARTIFACT_KIND_COMPACT_PING_ARTIFACT
        )
    for dispatch in bundle.dispatch_attempt_artifacts:
        assert dispatch.identity.artifact_kind == (
            ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT
        )
    for error in bundle.error_artifacts:
        assert error.identity.artifact_kind == (
            ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT
        )
        # The error reason code is the sanitized non-success status.
        assert error.error_reason_code == "RATE_LIMITED"
    assert bundle.session_summary.identity.artifact_kind == (
        ARTIFACT_KIND_COMPACT_SESSION_SUMMARY
    )


def test_happy_projection_preserves_capture_order() -> None:
    captures = (_capture(0), _capture(1), _capture(2))
    contexts = (
        _context(0, dedupe="k1"),
        _context(1, dedupe="k2"),
        _context(2, dedupe="k3"),
    )
    bundle = _project(captures, contexts).bundle
    # Pings are emitted in ascending capture_index order.
    bodies = [p.content.compact_body_text for p in bundle.ping_artifacts]
    assert bodies == ["body-0", "body-1", "body-2"]


# ---------------------------------------------------------------------------
# 2. dedupe_key carried VERBATIM from the dispatch context
# ---------------------------------------------------------------------------


def test_dedupe_key_carried_from_dispatch_context() -> None:
    captures = (_capture(0), _capture(1))
    contexts = (
        _context(0, dedupe="dispatch-ledger-key-1"),
        _context(1, dedupe="dispatch-ledger-key-1"),
    )
    bundle = _project(captures, contexts).bundle
    # Both pings carry the dedupe key VERBATIM from the dispatch context;
    # the projector never recomputes a key.
    for ping in bundle.ping_artifacts:
        assert ping.identity.dedupe_key == "dispatch-ledger-key-1"
    # The dispatch attempts carry the same dedupe key.
    for dispatch in bundle.dispatch_attempt_artifacts:
        assert dispatch.identity.dedupe_key == "dispatch-ledger-key-1"


def test_different_ping_id_same_dedupe_key_are_both_emitted() -> None:
    captures = (_capture(0), _capture(1))
    contexts = (
        _context(0, dedupe="same-key", ping="ping-A"),
        _context(1, dedupe="same-key", ping="ping-B"),
    )
    bundle = _project(captures, contexts).bundle
    pings = bundle.ping_artifacts
    assert pings[0].identity.ping_id == "ping-A"
    assert pings[1].identity.ping_id == "ping-B"
    assert pings[0].identity.dedupe_key == pings[1].identity.dedupe_key
    # The projector preserves both; the post-run Stage 30.8.3 index does the
    # dedupe (proven in the bridge-proof test).


# ---------------------------------------------------------------------------
# 3. Identity provenance: run/session/timestamp/ids
# ---------------------------------------------------------------------------


def test_identity_provenance_fields() -> None:
    captures = (_capture(0),)
    contexts = (_context(0, dedupe="k1", ping="p1", candidate="c1", mint="m1"),)
    bundle = _project(captures, contexts).bundle
    identity = bundle.ping_artifacts[0].identity
    assert identity.run_id == _RUN
    assert identity.session_id == _SESSION
    assert identity.artifact_created_at_utc == _CREATED
    assert identity.ping_id == "p1"
    assert identity.candidate_id == "c1"
    assert identity.token_mint == "m1"


def test_ping_session_id_defaults_to_config_else_override() -> None:
    captures = (_capture(0), _capture(1))
    contexts = (
        _context(0, dedupe="k1"),  # no override -> config session id
        _context(1, dedupe="k2", ping_session_id="diverged-session"),
    )
    bundle = _project(captures, contexts).bundle
    assert bundle.ping_artifacts[0].identity.session_id == _SESSION
    assert bundle.ping_artifacts[1].identity.session_id == (
        "diverged-session"
    )
    # The dispatch attempts always carry the config session id.
    for dispatch in bundle.dispatch_attempt_artifacts:
        assert dispatch.identity.session_id == _SESSION


# ---------------------------------------------------------------------------
# 4. Session summary counters (provided + derived)
# ---------------------------------------------------------------------------


def test_session_summary_uses_provided_counters() -> None:
    captures = (_capture(0),)
    contexts = (_context(0, dedupe="k1"),)
    counters = Stage30_9SessionSummaryCounters(
        pings_emitted=5,
        dispatch_attempts=7,
        dedupe_suppressed=2,
        errors=1,
    )
    summary = _project(captures, contexts, counters=counters).bundle.session_summary
    assert summary.pings_emitted == 5
    assert summary.dispatch_attempts == 7
    assert summary.dedupe_suppressed == 2
    assert summary.errors == 1


def test_session_summary_derives_counters_when_absent() -> None:
    captures = (_capture(0), _capture(1, status="SERVER_ERROR"))
    contexts = (_context(0, dedupe="k1"), _context(1, dedupe="k2"))
    summary = _project(captures, contexts, counters=None).bundle.session_summary
    assert summary.pings_emitted == 2
    assert summary.dispatch_attempts == 2
    assert summary.dedupe_suppressed == 0
    assert summary.errors == 1


# ---------------------------------------------------------------------------
# 5. The projected bundle passes the real Stage 30.8.2 writer validation
# ---------------------------------------------------------------------------


def test_projected_bundle_is_writer_valid(tmp_path) -> None:
    captures = (_capture(0), _capture(1), _capture(2, status="RATE_LIMITED"))
    contexts = (
        _context(0, dedupe="k1", candidate="c1", mint="m1"),
        _context(1, dedupe="k1", candidate="c1", mint="m1"),
        _context(2, dedupe="k2", candidate="c2", mint="m2"),
    )
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_PROJECTED

    write_result = write_compact_session_artifact_bundle(
        str(tmp_path), result.bundle
    )
    assert write_result.status == WRITE_STATUS_WRITTEN
    assert write_result.safe_to_persist is True


# ---------------------------------------------------------------------------
# 6. Fail-closed cases (a passive INVALID_INPUT result; never an exception)
# ---------------------------------------------------------------------------


def test_missing_run_id_fails_closed() -> None:
    captures = (_capture(0),)
    contexts = (_context(0, dedupe="k1"),)
    for bad in (None, "", 123):
        result = _project(captures, contexts, run_id=bad)
        assert result.status == BRIDGE_STATUS_INVALID_INPUT
        assert result.reason == BRIDGE_REASON_MISSING_RUN_ID
        assert result.bundle is None


def test_missing_session_id_fails_closed() -> None:
    captures = (_capture(0),)
    contexts = (_context(0, dedupe="k1"),)
    for bad in (None, "", 123):
        result = _project(captures, contexts, session_id=bad)
        assert result.status == BRIDGE_STATUS_INVALID_INPUT
        assert result.reason == BRIDGE_REASON_MISSING_SESSION_ID
        assert result.bundle is None


def test_count_mismatch_fails_closed() -> None:
    captures = (_capture(0), _capture(1))
    contexts = (_context(0, dedupe="k1"),)
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_INVALID_INPUT
    assert result.reason == BRIDGE_REASON_COUNT_MISMATCH


def test_non_sequence_inputs_fail_closed_as_count_mismatch() -> None:
    result = _project("not-a-sequence", "also-not")
    assert result.status == BRIDGE_STATUS_INVALID_INPUT
    assert result.reason == BRIDGE_REASON_COUNT_MISMATCH


def test_ambiguous_join_duplicate_join_key_fails_closed() -> None:
    captures = (_capture(0), _capture(1))
    # Two contexts claim the SAME capture_index -> ambiguous.
    contexts = (
        _context(0, dedupe="k1"),
        _context(0, dedupe="k2"),
    )
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_INVALID_INPUT
    assert result.reason == BRIDGE_REASON_AMBIGUOUS_JOIN


def test_ambiguous_join_unknown_capture_index_fails_closed() -> None:
    captures = (_capture(0), _capture(1))
    # A context references a capture_index no capture carries.
    contexts = (
        _context(0, dedupe="k1"),
        _context(9, dedupe="k2"),
    )
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_INVALID_INPUT
    assert result.reason == BRIDGE_REASON_AMBIGUOUS_JOIN


def test_non_private_webhook_fails_closed() -> None:
    captures = (_capture(0, webhook="SOME_OTHER_IDENTITY"),)
    contexts = (_context(0, dedupe="k1"),)
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_INVALID_INPUT
    assert result.reason == BRIDGE_REASON_NON_PRIVATE_WEBHOOK
    assert result.blocked_field == "webhook_identity"


# ---------------------------------------------------------------------------
# 6a. Join key (capture_index) must be a real non-negative int on both sides
# ---------------------------------------------------------------------------


def test_join_rejects_missing_or_invalid_capture_index() -> None:
    # (capture_index, context_index) pairs that must each fail closed with
    # MISSING_CAPTURE_INDEX (counts match so the count gate does not fire).
    bad_pairs = (
        (None, 0),   # capture missing
        (True, 1),   # capture bool (not a valid int join key)
        (-1, 0),     # capture negative
        ("0", 0),    # capture non-int
        (0, None),   # context missing
        (0, True),   # context bool
        (1, -2),     # context negative
        (0, "1"),    # context non-int
    )
    for cap_idx, ctx_idx in bad_pairs:
        captures = (_capture(cap_idx),)
        contexts = (_context(ctx_idx, dedupe="k1"),)
        result = _project(captures, contexts)
        assert result.status == BRIDGE_STATUS_INVALID_INPUT, (cap_idx, ctx_idx)
        assert result.reason == BRIDGE_REASON_MISSING_CAPTURE_INDEX, (
            cap_idx,
            ctx_idx,
        )
        assert result.bundle is None


def test_join_rejects_none_equals_none_capture_index() -> None:
    # A None==None pair must NOT silently join (it must fail closed).
    captures = (_capture(None),)
    contexts = (_context(None, dedupe="k1"),)
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_INVALID_INPUT
    assert result.reason == BRIDGE_REASON_MISSING_CAPTURE_INDEX


def test_join_rejects_duplicate_capture_capture_index() -> None:
    # Two captures share a capture_index -> ambiguous.
    captures = (_capture(0), _capture(0))
    contexts = (_context(0, dedupe="k1"), _context(1, dedupe="k2"))
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_INVALID_INPUT
    assert result.reason == BRIDGE_REASON_AMBIGUOUS_JOIN


def test_join_rejects_duplicate_context_capture_index() -> None:
    # Two contexts share a capture_index -> ambiguous.
    captures = (_capture(0), _capture(1))
    contexts = (_context(0, dedupe="k1"), _context(0, dedupe="k2"))
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_INVALID_INPUT
    assert result.reason == BRIDGE_REASON_AMBIGUOUS_JOIN


def test_join_valid_int_capture_index_joins_successfully() -> None:
    captures = (_capture(0), _capture(1))
    contexts = (_context(0, dedupe="k1"), _context(1, dedupe="k2"))
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_PROJECTED
    assert result.ping_artifact_count == 2


# ---------------------------------------------------------------------------
# 6b. Required identity axes (ping_id / candidate_id / token_mint) hard-reject
# ---------------------------------------------------------------------------


def test_missing_ping_id_fails_closed() -> None:
    captures = (_capture(0),)  # capture record carries no ping_id fallback
    for bad in (None, ""):
        contexts = (
            Stage30_9DispatchContextRecord(
                capture_index=0,
                dedupe_key="k1",
                ping_id=bad,
                candidate_id="c1",
                token_mint="m1",
            ),
        )
        result = _project(captures, contexts)
        assert result.status == BRIDGE_STATUS_INVALID_INPUT
        assert result.reason == BRIDGE_REASON_MISSING_PING_ID
        assert result.blocked_field == "ping_id"
        assert result.bundle is None


def test_missing_candidate_id_fails_closed() -> None:
    captures = (_capture(0),)  # capture record carries no candidate fallback
    for bad in (None, ""):
        contexts = (
            Stage30_9DispatchContextRecord(
                capture_index=0,
                dedupe_key="k1",
                ping_id="p1",
                candidate_id=bad,
                token_mint="m1",
            ),
        )
        result = _project(captures, contexts)
        assert result.status == BRIDGE_STATUS_INVALID_INPUT
        assert result.reason == BRIDGE_REASON_MISSING_CANDIDATE_ID
        assert result.blocked_field == "candidate_id"
        assert result.bundle is None


def test_missing_token_mint_fails_closed() -> None:
    captures = (_capture(0),)
    for bad in (None, ""):
        contexts = (
            Stage30_9DispatchContextRecord(
                capture_index=0,
                dedupe_key="k1",
                ping_id="p1",
                candidate_id="c1",
                token_mint=bad,
            ),
        )
        result = _project(captures, contexts)
        assert result.status == BRIDGE_STATUS_INVALID_INPUT
        assert result.reason == BRIDGE_REASON_MISSING_TOKEN_MINT
        assert result.blocked_field == "token_mint"
        assert result.bundle is None


def test_all_required_axes_present_projects(tmp_path) -> None:
    # With every required axis present the bundle projects and is
    # writer-valid (so no PROJECTED bundle ever carries a missing axis).
    captures = (_capture(0),)
    contexts = (
        Stage30_9DispatchContextRecord(
            capture_index=0,
            dedupe_key="k1",
            ping_id="p1",
            candidate_id="c1",
            token_mint="m1",
        ),
    )
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_PROJECTED
    ping = result.bundle.ping_artifacts[0]
    assert ping.identity.ping_id == "p1"
    assert ping.identity.candidate_id == "c1"
    assert ping.identity.token_mint == "m1"
    assert ping.identity.dedupe_key == "k1"
    write_result = write_compact_session_artifact_bundle(
        str(tmp_path), result.bundle
    )
    assert write_result.status == WRITE_STATUS_WRITTEN


def test_missing_dedupe_key_fails_closed() -> None:
    captures = (_capture(0),)
    for bad in (None, ""):
        contexts = (_context(0, dedupe=bad),)
        result = _project(captures, contexts)
        assert result.status == BRIDGE_STATUS_INVALID_INPUT
        assert result.reason == BRIDGE_REASON_MISSING_DEDUPE_KEY
        assert result.blocked_field == "dedupe_key"


def test_missing_compact_body_fails_closed() -> None:
    captures = (
        Stage30_9CaptureRecord(
            capture_index=0,
            webhook_identity=_PRIVATE,
            payload_body_text=None,
        ),
    )
    contexts = (_context(0, dedupe="k1"),)
    result = _project(captures, contexts)
    assert result.status == BRIDGE_STATUS_INVALID_INPUT
    assert result.reason == BRIDGE_REASON_MISSING_COMPACT_BODY
    assert result.blocked_field == "payload_body_text"


def test_projector_never_raises_on_garbage() -> None:
    # Total fail-closed: odd inputs yield a passive result, never an
    # exception.
    for captures, contexts in (
        (None, None),
        (object(), object()),
        ([object()], [object()]),
        ((_capture(0),), (object(),)),
    ):
        result = project_compact_session_artifact_bundle(
            run_id=_RUN,
            session_id=_SESSION,
            artifact_created_at_utc=_CREATED,
            capture_records=captures,
            dispatch_context_records=contexts,
        )
        assert result.status in (
            BRIDGE_STATUS_INVALID_INPUT,
            "PROJECT_FAILED",
        )
        assert result.bundle is None


# ---------------------------------------------------------------------------
# 7. Empty session (no sends) emits a summary-only bundle
# ---------------------------------------------------------------------------


def test_empty_session_emits_summary_only_bundle(tmp_path) -> None:
    result = _project((), ())
    assert result.status == BRIDGE_STATUS_PROJECTED
    assert result.ping_artifact_count == 0
    bundle = result.bundle
    assert bundle.ping_artifacts == ()
    assert bundle.session_summary is not None
    # A summary-only bundle is still writer-valid.
    write_result = write_compact_session_artifact_bundle(
        str(tmp_path), bundle
    )
    assert write_result.status == WRITE_STATUS_WRITTEN
