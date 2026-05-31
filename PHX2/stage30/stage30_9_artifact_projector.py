"""Stage 30.9.1 post-session compact artifact projector.

The post-session projector joins the Stage 30.9.1 capture records (what
the innermost capture transport observed being sent) with the runtime
dispatch-ledger context (which carries the ``dedupe_key`` and the
candidate / ping identity), and emits ONE Stage 30.8 compact session
artifact bundle: a session summary plus one compact ping artifact (and a
dispatch attempt artifact, and -- on a non-success transport status -- an
error artifact) per joined send.

It runs POST-SESSION ONLY. It builds the bundle in memory; it performs NO
Stage 30.8 write (that is the proof helper's single, post-session write).
The ``dedupe_key`` on every emitted ping / dispatch artifact is taken
VERBATIM from the dispatch context (the runtime dispatch ledger); the
projector NEVER recomputes a dedupe key.

Join contract (deterministic):

  * the join key is the capture record's ``capture_index`` (the stable id
    the capture transport assigns in send order); each dispatch context
    references its capture by ``capture_index``;
  * the projector prefers this explicit stable id; processing order is the
    ascending ``capture_index`` order, so the persisted bundle's per-ping
    filenames -- and therefore the post-run index's first-occurrence
    ordering -- are deterministic;
  * a capture / context count mismatch fails closed (``COUNT_MISMATCH``);
  * a duplicate / unresolvable join key fails closed (``AMBIGUOUS_JOIN``).

Fail-closed input contract (a passive ``INVALID_INPUT`` result, never an
exception, for normal invalid input):

  * missing ``run_id`` -> ``MISSING_RUN_ID``;
  * missing ``session_id`` -> ``MISSING_SESSION_ID``;
  * capture / context count mismatch -> ``COUNT_MISMATCH``;
  * a capture / context with no real non-negative int ``capture_index``
    join key -> ``MISSING_CAPTURE_INDEX``;
  * a duplicate / unresolvable join key -> ``AMBIGUOUS_JOIN``;
  * a capture whose ``webhook_identity`` is not a private label ->
    ``NON_PRIVATE_WEBHOOK``;
  * a context with no usable ``dedupe_key`` -> ``MISSING_DEDUPE_KEY``;
  * a missing / blank ``ping_id`` -> ``MISSING_PING_ID``;
  * a missing / blank ``candidate_id`` -> ``MISSING_CANDIDATE_ID``;
  * a missing / blank ``token_mint`` -> ``MISSING_TOKEN_MINT``;
  * a capture with no usable compact body -> ``MISSING_COMPACT_BODY``.

Every projected compact ping artifact therefore carries all required
bridge identity axes (run_id / session_id / ping_id / candidate_id /
token_mint / dedupe_key / artifact_created_at_utc / artifact_kind) plus a
non-empty compact body. An unexpected internal error fails closed to
``PROJECT_FAILED``.

Identity provenance (Stage 30.9.0 spec lock, Section 7):

  * ``run_id`` / ``session_id`` come from the live config (the explicit
    arguments);
  * ``ping_id`` / ``candidate_id`` / ``token_mint`` come from the dispatch
    context (the live candidate / adapter path);
  * ``dedupe_key`` comes from the dispatch context (the runtime dispatch
    ledger), carried VERBATIM;
  * the compact body comes from the capture record (the enriched payload
    actually sent);
  * ``artifact_created_at_utc`` comes from the explicit caller-injected
    timestamp -- the projector reads NO wall clock.

A ping artifact's identity session id defaults to the run config
``session_id``; a dispatch context that records a DIFFERENT session scope
(``ping_session_id``) yields a ping the post-run Stage 30.8.3 index
suppresses as ``SESSION_ID_MISMATCH`` (the offline invalid-artifact path).

Discipline:

  * Stdlib only (``typing``).
  * PHX2 imports: the Stage 30.9.1 bridge-models sibling + the Stage 30.8.1
    artifact-models sibling + the Stage 30.8.2 writer (for the bundle
    type). It imports NO Stage 28 module (the dispatch context is a
    duck-typed / passive Stage 30.9.1 carrier) and NO Stage 21-29 / runtime
    / orchestrator / renderer / Discord / provider module.
  * No ``os`` (NO env read), NO network, NO ``sqlite3``, NO ``zstd`` /
    compression, NO clock / random.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

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
    BRIDGE_STATUS_PROJECT_FAILED,
    BRIDGE_STATUS_PROJECTED,
    SANITIZED_TRANSPORT_STATUS_SENT_OK,
    Stage30_9ProjectorResult,
    is_private_webhook_identity,
)
from PHX2.stage30.stage30_8_artifact_models import (
    ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT,
    ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT,
    ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
    ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
    Stage30_8CompactArtifactIdentity,
    Stage30_8CompactContentSnapshot,
    Stage30_8CompactDispatchAttemptArtifact,
    Stage30_8CompactErrorArtifact,
    Stage30_8CompactPingArtifact,
    Stage30_8CompactSessionSummaryArtifact,
)
from PHX2.stage30.stage30_8_temp_artifact_writer import (
    Stage30_8CompactSessionArtifactBundle,
)


# ---------------------------------------------------------------------------
# Transport success token
# ---------------------------------------------------------------------------
#
# The closed-set ``SENT_OK`` success token is the Stage 30.9.1
# bridge-models sanitized success token (which mirrors the Stage 28.4
# ``TRANSPORT_STATUS_SENT_OK`` value BY VALUE; the projector imports no
# Stage 28 module). A captured send whose sanitized transport status is a
# non-empty NON-success token yields an error artifact (the post-session
# closed-set error reason code is the sanitized status token itself).


_TRANSPORT_STATUS_SENT_OK: str = SANITIZED_TRANSPORT_STATUS_SENT_OK


# ---------------------------------------------------------------------------
# Internal: per-record reject signal (fail closed)
# ---------------------------------------------------------------------------


class _ProjectRejected(Exception):
    """Internal control-flow signal: a normal fail-closed input. Carries a
    closed-set bridge reason + blocked field. Never escapes the module (the
    public entry point converts it to an ``INVALID_INPUT`` result).
    """

    def __init__(self, reason: str, blocked_field: Optional[str]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.blocked_field = blocked_field


# ---------------------------------------------------------------------------
# Pure result builders
# ---------------------------------------------------------------------------


def _invalid_input(
    reason: str, blocked_field: Optional[str]
) -> Stage30_9ProjectorResult:
    """Build an INVALID_INPUT projector result (fail closed; no bundle)."""
    return Stage30_9ProjectorResult(
        status=BRIDGE_STATUS_INVALID_INPUT,
        reason=reason,
        blocked_field=blocked_field,
        bundle=None,
        ping_artifact_count=0,
        dispatch_attempt_count=0,
        error_artifact_count=0,
    )


def _project_failed() -> Stage30_9ProjectorResult:
    """Build a PROJECT_FAILED result (an unexpected internal error)."""
    return Stage30_9ProjectorResult(
        status=BRIDGE_STATUS_PROJECT_FAILED,
        reason=BRIDGE_REASON_NONE,
        blocked_field=None,
        bundle=None,
        ping_artifact_count=0,
        dispatch_attempt_count=0,
        error_artifact_count=0,
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _opt_str(value: object) -> Optional[str]:
    """Return ``value`` when it is a non-empty string, else ``None``."""
    return value if isinstance(value, str) and value != "" else None


def _as_sequence(value: object) -> Optional[List[object]]:
    """Return ``value`` as a list when it is a tuple / list (never a
    ``str`` / ``bytes``), else ``None``. Pure.
    """
    if isinstance(value, (str, bytes)):
        return None
    if isinstance(value, (tuple, list)):
        return list(value)
    return None


def _identity(
    *,
    artifact_kind: str,
    run_id: str,
    session_id: str,
    artifact_created_at_utc: str,
    ping_id: Optional[str] = None,
    candidate_id: Optional[str] = None,
    token_mint: Optional[str] = None,
    dedupe_key: Optional[str] = None,
) -> Stage30_8CompactArtifactIdentity:
    """Build a Stage 30.8 compact artifact identity for ``artifact_kind``.

    The ``stage_id`` / ``artifact_schema_version`` carry the Stage 30.8.1
    locked defaults. The projector reads no clock; ``artifact_created_at_utc``
    is the caller-injected timestamp. Pure.
    """
    return Stage30_8CompactArtifactIdentity(
        run_id=run_id,
        session_id=session_id,
        ping_id=ping_id,
        candidate_id=candidate_id,
        token_mint=token_mint,
        artifact_created_at_utc=artifact_created_at_utc,
        artifact_kind=artifact_kind,
        dedupe_key=dedupe_key,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def project_compact_session_artifact_bundle(
    *,
    run_id: object,
    session_id: object,
    artifact_created_at_utc: object,
    capture_records: object,
    dispatch_context_records: object,
    session_summary_counters: object = None,
) -> Stage30_9ProjectorResult:
    """Project capture records + dispatch context into ONE Stage 30.8
    compact session artifact bundle.

    Returns a passive ``Stage30_9ProjectorResult``: ``PROJECTED`` with the
    bundle on success, ``INVALID_INPUT`` with a closed-set reason for a
    normal fail-closed input, or ``PROJECT_FAILED`` on an unexpected
    internal error. Never raises.
    """
    try:
        return _project(
            run_id,
            session_id,
            artifact_created_at_utc,
            capture_records,
            dispatch_context_records,
            session_summary_counters,
        )
    except _ProjectRejected as rejected:
        return _invalid_input(rejected.reason, rejected.blocked_field)
    except Exception:  # pragma: no cover - total fail-closed backstop
        return _project_failed()


def _project(
    run_id: object,
    session_id: object,
    artifact_created_at_utc: object,
    capture_records: object,
    dispatch_context_records: object,
    session_summary_counters: object,
) -> Stage30_9ProjectorResult:
    """Projection body (see ``project_compact_session_artifact_bundle``)."""
    # 1. Required run / session identity (from the live config).
    run_id_str = _opt_str(run_id)
    if run_id_str is None:
        raise _ProjectRejected(BRIDGE_REASON_MISSING_RUN_ID, "run_id")
    session_id_str = _opt_str(session_id)
    if session_id_str is None:
        raise _ProjectRejected(
            BRIDGE_REASON_MISSING_SESSION_ID, "session_id"
        )
    # The artifact timestamp is a required explicit input (the projector
    # reads no wall clock); it is carried onto every emitted identity as a
    # lenient value. The Stage 30.8.1 validator -- invoked by the Stage
    # 30.8.2 writer -- is the authority that rejects a missing / malformed
    # ``artifact_created_at_utc`` (it is a required identity axis), so a bad
    # timestamp fails closed downstream as a writer rejection rather than
    # being mapped onto an unrelated closed-set projector reason.
    created_at_str = _opt_str(artifact_created_at_utc)

    # 2. Capture + context sequences.
    captures = _as_sequence(capture_records)
    contexts = _as_sequence(dispatch_context_records)
    if captures is None or contexts is None:
        raise _ProjectRejected(
            BRIDGE_REASON_COUNT_MISMATCH, "dispatch_context_records"
        )
    if len(captures) != len(contexts):
        raise _ProjectRejected(
            BRIDGE_REASON_COUNT_MISMATCH, "dispatch_context_records"
        )

    # 3. Deterministic join on the stable capture_index.
    joined = _join_on_capture_index(captures, contexts)

    # 4. Project each joined (capture, context) pair into Stage 30.8
    #    artifacts (ascending capture_index order -> deterministic bundle).
    pings: List[Stage30_8CompactPingArtifact] = []
    dispatches: List[Stage30_8CompactDispatchAttemptArtifact] = []
    errors: List[Stage30_8CompactErrorArtifact] = []

    for capture, context in joined:
        # Routing safety: never project a non-private send.
        if not is_private_webhook_identity(
            getattr(capture, "webhook_identity", None)
        ):
            raise _ProjectRejected(
                BRIDGE_REASON_NON_PRIVATE_WEBHOOK, "webhook_identity"
            )

        # Resolve the bridge identity axes: the dedupe key comes from the
        # dispatch context VERBATIM (never recomputed); the ping / candidate
        # ids prefer the dispatch context and fall back to the capture
        # metadata; the token mint comes from the dispatch context.
        dedupe_key = _opt_str(getattr(context, "dedupe_key", None))
        ping_id = _opt_str(
            getattr(context, "ping_id", None)
        ) or _opt_str(getattr(capture, "ping_id", None))
        candidate_id = _opt_str(
            getattr(context, "candidate_id", None)
        ) or _opt_str(getattr(capture, "candidate_id", None))
        token_mint = _opt_str(getattr(context, "token_mint", None))
        body = _opt_str(getattr(capture, "payload_body_text", None))

        # Hard-reject any missing/blank REQUIRED bridge identity axis BEFORE
        # constructing the Stage 30.8 ping artifact, so a PROJECTED bundle
        # can never carry a ping artifact with a missing required axis. The
        # Stage 30.8.2 writer treats candidate_id / token_mint as OPTIONAL
        # identity fields, so the bridge enforces its stronger required-axis
        # contract here (run_id / session_id were already enforced above).
        if dedupe_key is None:
            raise _ProjectRejected(
                BRIDGE_REASON_MISSING_DEDUPE_KEY, "dedupe_key"
            )
        if ping_id is None:
            raise _ProjectRejected(
                BRIDGE_REASON_MISSING_PING_ID, "ping_id"
            )
        if candidate_id is None:
            raise _ProjectRejected(
                BRIDGE_REASON_MISSING_CANDIDATE_ID, "candidate_id"
            )
        if token_mint is None:
            raise _ProjectRejected(
                BRIDGE_REASON_MISSING_TOKEN_MINT, "token_mint"
            )
        if body is None:
            raise _ProjectRejected(
                BRIDGE_REASON_MISSING_COMPACT_BODY, "payload_body_text"
            )

        status = _opt_str(
            getattr(capture, "sanitized_transport_status", None)
        )
        # The ping's recorded session scope defaults to the config session.
        ping_session_id = (
            _opt_str(getattr(context, "ping_session_id", None))
            or session_id_str
        )

        pings.append(
            Stage30_8CompactPingArtifact(
                identity=_identity(
                    artifact_kind=ARTIFACT_KIND_COMPACT_PING_ARTIFACT,
                    run_id=run_id_str,
                    session_id=ping_session_id,
                    artifact_created_at_utc=created_at_str,
                    ping_id=ping_id,
                    candidate_id=candidate_id,
                    token_mint=token_mint,
                    dedupe_key=dedupe_key,
                ),
                content=Stage30_8CompactContentSnapshot(
                    compact_body_text=body,
                    sanitized_transport_status=status,
                ),
            )
        )

        # A dispatch attempt artifact per send that carries a status.
        if status is not None:
            dispatches.append(
                Stage30_8CompactDispatchAttemptArtifact(
                    identity=_identity(
                        artifact_kind=(
                            ARTIFACT_KIND_COMPACT_DISPATCH_ATTEMPT_ARTIFACT
                        ),
                        run_id=run_id_str,
                        session_id=session_id_str,
                        artifact_created_at_utc=created_at_str,
                        ping_id=ping_id,
                        candidate_id=candidate_id,
                        token_mint=token_mint,
                        dedupe_key=dedupe_key,
                    ),
                    sanitized_transport_status=status,
                    attempt_index=getattr(capture, "capture_index", None),
                )
            )
            # An error artifact when the send did not succeed.
            if status != _TRANSPORT_STATUS_SENT_OK:
                errors.append(
                    Stage30_8CompactErrorArtifact(
                        identity=_identity(
                            artifact_kind=(
                                ARTIFACT_KIND_COMPACT_ERROR_ARTIFACT
                            ),
                            run_id=run_id_str,
                            session_id=session_id_str,
                            artifact_created_at_utc=created_at_str,
                            ping_id=ping_id,
                            candidate_id=candidate_id,
                            token_mint=token_mint,
                            dedupe_key=dedupe_key,
                        ),
                        error_reason_code=status,
                    )
                )

    # 5. The rolled-up session summary (always emitted).
    summary = _build_session_summary(
        run_id=run_id_str,
        session_id=session_id_str,
        artifact_created_at_utc=created_at_str,
        counters=session_summary_counters,
        pings_emitted=len(pings),
        dispatch_attempts=len(dispatches),
        errors=len(errors),
    )

    bundle = Stage30_8CompactSessionArtifactBundle(
        session_id=session_id_str,
        session_summary=summary,
        ping_artifacts=tuple(pings),
        dispatch_attempt_artifacts=tuple(dispatches),
        error_artifacts=tuple(errors),
    )

    return Stage30_9ProjectorResult(
        status=BRIDGE_STATUS_PROJECTED,
        reason=BRIDGE_REASON_NONE,
        blocked_field=None,
        bundle=bundle,
        ping_artifact_count=len(pings),
        dispatch_attempt_count=len(dispatches),
        error_artifact_count=len(errors),
    )


def _is_valid_capture_index(value: object) -> bool:
    """Return ``True`` iff ``value`` is a real, non-negative ``int`` join
    key -- NOT ``None``, NOT a ``bool`` (``bool`` is an ``int`` subclass and
    must never count), NOT a non-int, and not negative. Pure.
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, int) and value >= 0


def _join_on_capture_index(
    captures: List[object], contexts: List[object]
) -> List[Tuple[object, object]]:
    """Join captures to contexts on the stable ``capture_index``.

    Both sides MUST carry a real non-bool non-negative ``int``
    ``capture_index``: a missing / ``None`` / ``bool`` / non-int / negative
    join key on either side fails closed (``MISSING_CAPTURE_INDEX``) -- the
    join NEVER falls back to ordering and NEVER lets ``None == None`` join.
    A duplicate capture index, a duplicate context join key, or a context
    that references a capture index no capture carries fails closed
    (``AMBIGUOUS_JOIN``). Returns the ``(capture, context)`` pairs in
    ascending capture_index order. Pure.
    """
    capture_by_index: Dict[int, object] = {}
    for capture in captures:
        index = getattr(capture, "capture_index", None)
        if not _is_valid_capture_index(index):
            raise _ProjectRejected(
                BRIDGE_REASON_MISSING_CAPTURE_INDEX, "capture_index"
            )
        if index in capture_by_index:
            raise _ProjectRejected(
                BRIDGE_REASON_AMBIGUOUS_JOIN, "capture_index"
            )
        capture_by_index[index] = capture

    seen_context_indices: set = set()
    pairs: List[Tuple[object, object]] = []
    for context in contexts:
        index = getattr(context, "capture_index", None)
        if not _is_valid_capture_index(index):
            raise _ProjectRejected(
                BRIDGE_REASON_MISSING_CAPTURE_INDEX, "capture_index"
            )
        if index in seen_context_indices:
            raise _ProjectRejected(
                BRIDGE_REASON_AMBIGUOUS_JOIN, "capture_index"
            )
        if index not in capture_by_index:
            raise _ProjectRejected(
                BRIDGE_REASON_AMBIGUOUS_JOIN, "capture_index"
            )
        seen_context_indices.add(index)
        pairs.append((capture_by_index[index], context))

    # Deterministic order: ascending capture_index (every index is a
    # validated non-negative int, so the sort is total).
    return sorted(pairs, key=lambda pair: pair[0].capture_index)


def _nonneg_int_or(value: object, fallback: int) -> int:
    """Return ``value`` when it is a non-negative ``int`` (not ``bool``),
    else ``fallback``. Used only to fill summary counters from the optional
    caller-provided counters; the Stage 30.8 validator is the authority on
    the final artifact.
    """
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int) and value >= 0:
        return value
    return fallback


def _build_session_summary(
    *,
    run_id: str,
    session_id: str,
    artifact_created_at_utc: str,
    counters: object,
    pings_emitted: int,
    dispatch_attempts: int,
    errors: int,
) -> Stage30_8CompactSessionSummaryArtifact:
    """Build the rolled-up Stage 30.8 session summary artifact.

    When the caller supplies counters they are used (filtered to
    non-negative ints); otherwise the counters are derived from the
    projected artifacts. ``dedupe_suppressed`` defaults to 0 (the runtime
    owns dedupe; the bridge never recomputes it). Pure.
    """
    summary_identity = _identity(
        artifact_kind=ARTIFACT_KIND_COMPACT_SESSION_SUMMARY,
        run_id=run_id,
        session_id=session_id,
        artifact_created_at_utc=artifact_created_at_utc,
    )
    if counters is None:
        return Stage30_8CompactSessionSummaryArtifact(
            identity=summary_identity,
            pings_emitted=pings_emitted,
            dispatch_attempts=dispatch_attempts,
            dedupe_suppressed=0,
            errors=errors,
        )
    return Stage30_8CompactSessionSummaryArtifact(
        identity=summary_identity,
        pings_emitted=_nonneg_int_or(
            getattr(counters, "pings_emitted", None), pings_emitted
        ),
        dispatch_attempts=_nonneg_int_or(
            getattr(counters, "dispatch_attempts", None), dispatch_attempts
        ),
        dedupe_suppressed=_nonneg_int_or(
            getattr(counters, "dedupe_suppressed", None), 0
        ),
        errors=_nonneg_int_or(getattr(counters, "errors", None), errors),
    )


__all__ = (
    "project_compact_session_artifact_bundle",
)
