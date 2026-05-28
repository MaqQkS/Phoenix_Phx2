"""Stage 30.3 compact body transport wrapper.

The Stage 30.3 wrapper is the outermost layer of the Stage
30.3B private operator runtime composition. On each
``send_one_audited_post`` call it consumes the most recent
Stage 30.3 recorded entry, projects it onto a Stage 30.1 tier
decision plus a Stage 30.2 compact ping snapshot, replaces the
caller-supplied ``payload["content"]`` string with the rendered
compact body, writes the Stage 30.1 / Stage 30.2 / Stage 30.3
JSONL artifact lines, and forwards a fresh ``dict(payload)``
copy to the injected inner transport. Every other branch (no
recorded entry, projection failure, render failure, hard-cap
exceeded, snapshot-write failure, unexpected exception) records
a closed-set failure outcome, writes a wiring artifact line
best-effort, and returns a synthetic refusal result without
forwarding to the inner transport.

Wrapper-order discipline:

  Stage30_3CompactBodyTransportWrapper           (REPLACES content)
    optional Stage29_5_6 wrapped transport       (APPENDS block)
      Stage28_9 private operator channel layer   (applies cap)
        Stage28_4 audited HTTP transport         (actual HTTP)

  Stage 30.3A exercises only the outermost layer plus a fake
  inner transport. Stage 30.3B will compose the full stack via
  the parallel orchestrator.

Failure-isolation discipline:

  * Inner-transport exceptions propagate verbatim from a
    ``RENDERED`` outcome (the wrapper does NOT swallow inner
    failures on the success path).
  * Every other branch records exactly one outcome, writes the
    wiring artifact line best-effort (a wiring-write failure on
    a non-success branch does NOT change the closed-set outcome
    token), and returns the synthetic refusal result.
  * The caller-supplied payload dict is NEVER mutated on any
    branch; the wrapper always builds a fresh ``dict(payload)``
    copy before assigning the compact body.

Discipline:

  * Stdlib only (``hashlib`` / ``typing``).
  * Stage 30 sibling modules imported read-only.
  * No Stage 27 / Stage 28 / Stage 29 import.
  * No ``os.environ`` / ``os.getenv`` / ``os.environb`` access.
  * No network, no HTTP, no gRPC, no WebSocket, no socket.
  * No URL host literal, no API-key literal, no bearer-token
    literal, no authorization-header literal.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No top-level Call (no implicit I/O at import time).

Naming carve-out:

  * The wrapper's ``send_one_audited_post`` method keeps the
    operator-channel identity parameter name verbatim because it
    must match the existing Stage 28.6 transport duck-typed API.
    The Stage 30.3 spec-lock test carves out this parameter
    identifier from the closed-set source-text scan.
  * The literal synthetic-refusal transport status mirrors the
    Stage 28.4 ``TRANSPORT_STATUS_PAYLOAD_REFUSED`` token and is
    redeclared here as a wrapper-local module-private constant
    so its byte-identical value lives in the same compilation
    unit as the wrapper's redaction logic. The Stage 30.3 models
    module also declares the same constant for cross-module
    reference; both declarations must stay byte-identical.

Stage 30.3A wiring redaction:

  * The wiring artifact's ``session_id`` / ``candidate_id`` /
    ``ping_id`` value slots flow through wrapper-local safe-
    artifact helpers before the record is built. The helpers
    redact any value carrying a URL host / auth token / API key /
    raw-payload / RPC URL substring to the literal ``"REDACTED"``.
  * The wiring artifact's ``mint`` value slot prefers the
    Stage 30.1 sanitized echo from the ``TierDecisionRecord`` when
    ``decide_tier`` has already produced a base58-safe mint; on
    every earlier failure branch the wrapper falls back to a
    wrapper-local mint-shape safe-artifact helper that redacts
    any unsafe shape (non-base58 alphabet, wrong length, or
    forbidden substring) to ``"REDACTED"``.
"""

from __future__ import annotations

import hashlib
from typing import Any, NamedTuple, Optional, Tuple

from PHX2.stage30.compact_ping_artifact_writer import (
    append_compact_ping_snapshot,
)
from PHX2.stage30.compact_ping_models import (
    STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME,
    CompactPingInputRecord,
    CompactPingSnapshotRecord,
    Stage30_2CompactPingError,
)
from PHX2.stage30.compact_ping_renderer import render_compact_ping
from PHX2.stage30.stage30_3_compact_candidate_projection import (
    build_compact_ping_input_record,
    project_recorded_entry_to_tier_decision_record,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    COMPACT_OUTCOME_FAILED_CAP,
    COMPACT_OUTCOME_FAILED_COMPACT_RENDER,
    COMPACT_OUTCOME_FAILED_EXCEPTION,
    COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
    COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE,
    COMPACT_OUTCOME_FAILED_TIER_DECISION,
    COMPACT_OUTCOME_RENDERED,
    COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
    SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED,
    SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED,
    STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION,
    WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY,
    WRAPPER_ORDER_LABEL_VALUES,
    Stage30_3CompactRuntimeContext,
    Stage30_3CompactRuntimeError,
    Stage30_3RuntimeWiringArtifactRecord,
)
from PHX2.stage30.stage30_3_runtime_wiring_artifact_writer import (
    append_runtime_wiring_record,
)
from PHX2.stage30.tier_decision_artifact_writer import (
    append_tier_decision_record,
)
from PHX2.stage30.tier_decision_models import (
    STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME,
    Stage30_1TierDecisionError,
    TierDecisionRecord,
)


# ---------------------------------------------------------------------------
# Wrapper-local synthetic-refusal transport status
# ---------------------------------------------------------------------------
#
# Mirrors the Stage 28.4 ``TRANSPORT_STATUS_PAYLOAD_REFUSED`` token
# value verbatim. The literal is redeclared in this wrapper module so
# the byte-identical value lives in the same compilation unit as the
# wrapper's redaction logic. The Stage 30.3 models module also
# declares the same constant for cross-module reference (the wrapper
# does not import it from the models module so the wrapper does not
# depend on the models module for the byte-identical value).


_STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS_LOCAL: str = (
    "PAYLOAD_REFUSED"
)


# ---------------------------------------------------------------------------
# Wrapper-local safe-artifact redaction helpers
# ---------------------------------------------------------------------------
#
# Stage 30.3 wiring artifact ``session_id`` / ``candidate_id`` /
# ``ping_id`` / ``mint`` value slots flow through these helpers
# BEFORE the record is constructed. The helpers redact any value
# carrying a URL host / auth token / API key / raw-payload / RPC URL
# substring (case-insensitive) to the literal ``"REDACTED"``. They
# also redact any value whose length exceeds the safe bound, and any
# value whose character alphabet falls outside the safe-shape
# identifier / Solana-base58 alphabet. ``None`` stays ``None``;
# non-string inputs collapse to ``None``; empty / whitespace-only
# inputs collapse to ``None``.
#
# The forbidden-substring needle vocabulary is declared with
# concatenated literals so this wrapper module does NOT carry the
# canonical URL / auth / secret literals in any single string
# constant (mirrors the Stage 30.1 / 30.2 / 29.5.5 writer patterns).


_STAGE30_3_SAFE_ARTIFACT_REDACTED_VALUE: str = "REDACTED"


_STAGE30_3_SAFE_ARTIFACT_MAX_TEXT_LENGTH: int = 64
_STAGE30_3_SAFE_ARTIFACT_MIN_MINT_LENGTH: int = 32
_STAGE30_3_SAFE_ARTIFACT_MAX_MINT_LENGTH: int = 64


_STAGE30_3_SAFE_ARTIFACT_FORBIDDEN_SUBSTRINGS: Tuple[str, ...] = (
    "h" + "ttp://",
    "h" + "ttps://",
    "w" + "s://",
    "w" + "ss://",
    "discord" + ".com",
    "discord" + "app.com",
    "/web" + "hooks/",
    "b" + "earer",
    "a" + "uthorization",
    "s" + "k-",
    "p" + "k-",
    "api_key",
    "apikey",
    "secret",
    "private_key",
    "seed_phrase",
    "mnemonic",
    "raw_payload",
    "payload_blob",
    "rpc_url",
)


# Safe-identifier alphabet (printable ASCII alphanumerics + a
# small allowlist of separators). Mirrors the Stage 30.1 projector's
# ``_SAFE_IDENTIFIER_ALPHABET`` shape. Declared as a string constant
# (not a frozenset) so this module retains zero top-level Call nodes.
_STAGE30_3_SAFE_ARTIFACT_TEXT_ALPHABET: str = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-."
)


# Solana base58 alphabet (no 0, no O, no I, no l). Mirrors the
# Stage 30.1 projector's ``_BASE58_ALPHABET`` shape. Declared as a
# string constant (not a frozenset) so this module retains zero
# top-level Call nodes.
_STAGE30_3_SAFE_ARTIFACT_MINT_ALPHABET: str = (
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    "abcdefghijkmnopqrstuvwxyz"
)


def _value_carries_forbidden_substring(value: str) -> bool:
    """Return ``True`` iff the lowercase form of ``value`` carries
    any Stage 30.3A safe-artifact forbidden substring.
    """
    lower = value.lower()
    for needle in _STAGE30_3_SAFE_ARTIFACT_FORBIDDEN_SUBSTRINGS:
        if needle in lower:
            return True
    return False


def _safe_artifact_text(value: Optional[str]) -> Optional[str]:
    """Redact ``value`` for safe Stage 30.3 wiring artifact embedding.

    Rules:

      * ``None``                                       -> ``None``.
      * non-``str``                                    -> ``None``.
      * empty / whitespace-only                        -> ``None``.
      * carries forbidden URL / auth / secret /
        raw-payload / RPC-URL substring                -> ``"REDACTED"``.
      * length exceeds the safe max                    -> ``"REDACTED"``.
      * any char outside the safe-identifier alphabet  -> ``"REDACTED"``.
      * otherwise                                      -> ``value`` verbatim.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    if value.strip() == "":
        return None
    if _value_carries_forbidden_substring(value):
        return _STAGE30_3_SAFE_ARTIFACT_REDACTED_VALUE
    if len(value) > _STAGE30_3_SAFE_ARTIFACT_MAX_TEXT_LENGTH:
        return _STAGE30_3_SAFE_ARTIFACT_REDACTED_VALUE
    for ch in value:
        if ch not in _STAGE30_3_SAFE_ARTIFACT_TEXT_ALPHABET:
            return _STAGE30_3_SAFE_ARTIFACT_REDACTED_VALUE
    return value


def _safe_artifact_mint(value: Optional[str]) -> Optional[str]:
    """Redact ``value`` for safe Stage 30.3 wiring artifact mint slot.

    Rules:

      * ``None``                                       -> ``None``.
      * non-``str``                                    -> ``None``.
      * empty / whitespace-only                        -> ``None``.
      * carries forbidden URL / auth / secret /
        raw-payload / RPC-URL substring                -> ``"REDACTED"``.
      * length outside the safe base58 mint range      -> ``"REDACTED"``.
      * any char outside the Solana base58 alphabet    -> ``"REDACTED"``.
      * otherwise                                      -> ``value`` verbatim.

    Callers should PREFER the Stage 30.1 sanitized echo from the
    ``TierDecisionRecord`` when ``decide_tier`` has already produced
    a base58-safe mint; this helper is the fallback when the tier
    decision is unavailable or its mint slot is ``None`` because
    Stage 30.1 redacted an unsafe shape.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    if value.strip() == "":
        return None
    if _value_carries_forbidden_substring(value):
        return _STAGE30_3_SAFE_ARTIFACT_REDACTED_VALUE
    n = len(value)
    if n < _STAGE30_3_SAFE_ARTIFACT_MIN_MINT_LENGTH:
        return _STAGE30_3_SAFE_ARTIFACT_REDACTED_VALUE
    if n > _STAGE30_3_SAFE_ARTIFACT_MAX_MINT_LENGTH:
        return _STAGE30_3_SAFE_ARTIFACT_REDACTED_VALUE
    for ch in value:
        if ch not in _STAGE30_3_SAFE_ARTIFACT_MINT_ALPHABET:
            return _STAGE30_3_SAFE_ARTIFACT_REDACTED_VALUE
    return value


# ---------------------------------------------------------------------------
# Synthetic refusal result
# ---------------------------------------------------------------------------


class _Stage30_3SyntheticRefusalResult(NamedTuple):
    """Synthetic transport result returned on every non-RENDERED
    outcome. Carries the locked synthetic refusal transport status
    plus ``None`` retry-after seconds. The wrapper NEVER fabricates
    an HTTP status code or an operator-channel identity on this
    result; the operator must consult the Stage 30.3 wiring
    artifact line to audit WHY the wrapper refused to forward the
    payload.
    """

    transport_status: str
    retry_after_seconds: Optional[float]


# ---------------------------------------------------------------------------
# Internal reason tokens carried on FAILED_INPUT_SHAPE / FAILED_EXCEPTION
# ---------------------------------------------------------------------------
#
# These reason tokens are not part of the Stage 30.1 / 30.2 typed
# error vocabularies; they are local to the Stage 30.3 wrapper and
# carried on the wiring artifact's ``compact_outcome_reason`` slot.


_PROJECTION_EXCEPTION_REASON: str = "PROJECTION_EXCEPTION"
_INPUT_BUILD_EXCEPTION_REASON: str = "INPUT_BUILD_EXCEPTION"
_PAYLOAD_NOT_DICT_REASON: str = "PAYLOAD_NOT_DICT"


# ---------------------------------------------------------------------------
# Wrapper
# ---------------------------------------------------------------------------


class Stage30_3CompactBodyTransportWrapper:
    """Stage 30.3 compact body transport wrapper.

    Construction validates the injected inner transport, the
    recorder, the context, the clock, and the wrapper-order tuple.
    Each ``send_one_audited_post`` call records exactly one
    closed-set outcome and either forwards a compact-replacement
    payload through the inner transport (on ``RENDERED``) or
    returns a synthetic refusal result (on every other outcome).

    The wrapper exposes two counter surfaces for offline tests:

      * ``calls_received``                -- total number of
                                             ``send_one_audited_post``
                                             calls observed.
      * ``outcomes_count(outcome_token)`` -- closed-set outcome
                                             counter.

    The wrapper carries zero stateful network resources, no
    process-environment binding, and no per-call ``datetime.now``
    read; the injected clock is the sole source of wall-clock
    time.
    """

    __slots__ = (
        "_inner_transport",
        "_recorder",
        "_context",
        "_clock",
        "_wrapper_order",
        "_calls_received",
        "_outcomes_by_token",
    )

    def __init__(
        self,
        *,
        inner_transport: object,
        recorder: object,
        context: Stage30_3CompactRuntimeContext,
        clock: object,
        wrapper_order: Tuple[str, ...],
    ) -> None:
        if not callable(
            getattr(inner_transport, "send_one_audited_post", None)
        ):
            raise Stage30_3CompactRuntimeError(
                "INNER_TRANSPORT_INVALID"
            )
        recorded_entries_attr = getattr(
            recorder, "recorded_entries", None
        )
        if not isinstance(recorded_entries_attr, tuple):
            raise Stage30_3CompactRuntimeError("RECORDER_INVALID")
        if not isinstance(context, Stage30_3CompactRuntimeContext):
            raise Stage30_3CompactRuntimeError("CONTEXT_INVALID")
        if not callable(getattr(clock, "now_utc_iso", None)):
            raise Stage30_3CompactRuntimeError("CLOCK_INVALID")
        if not isinstance(wrapper_order, tuple):
            raise Stage30_3CompactRuntimeError(
                "WRAPPER_ORDER_INVALID"
            )
        if len(wrapper_order) == 0:
            raise Stage30_3CompactRuntimeError(
                "WRAPPER_ORDER_INVALID"
            )
        for label in wrapper_order:
            if not isinstance(label, str):
                raise Stage30_3CompactRuntimeError(
                    "WRAPPER_ORDER_INVALID"
                )
            if label not in WRAPPER_ORDER_LABEL_VALUES:
                raise Stage30_3CompactRuntimeError(
                    "WRAPPER_ORDER_INVALID"
                )
        if (
            wrapper_order[0]
            != WRAPPER_ORDER_LABEL_STAGE30_3_COMPACT_BODY
        ):
            raise Stage30_3CompactRuntimeError(
                "WRAPPER_ORDER_INVALID"
            )
        self._inner_transport: object = inner_transport
        self._recorder: object = recorder
        self._context: Stage30_3CompactRuntimeContext = context
        self._clock: object = clock
        self._wrapper_order: Tuple[str, ...] = wrapper_order
        self._calls_received: int = 0
        self._outcomes_by_token: dict = {}

    @property
    def calls_received(self) -> int:
        """Return the total number of
        ``send_one_audited_post`` calls observed.
        """
        return self._calls_received

    def outcomes_count(self, outcome_token: str) -> int:
        """Return the count of recorded outcomes for the
        supplied closed-set outcome token. Unknown tokens
        return ``0`` (the wrapper never records an outcome
        outside ``COMPACT_OUTCOME_VALUES``).
        """
        return self._outcomes_by_token.get(outcome_token, 0)

    def send_one_audited_post(
        self,
        *,
        webhook_identity: str,
        payload: object,
    ) -> object:
        """Project the most recent recorded entry, render a Stage
        30.2 compact body, write the Stage 30.1 / Stage 30.2 /
        Stage 30.3 artifact lines, and forward a fresh payload
        copy through the inner transport on the ``RENDERED``
        outcome. Return a synthetic refusal result on every other
        outcome.

        Inner-transport exceptions on the ``RENDERED`` branch
        propagate verbatim. The wrapper's own internal exceptions
        on every earlier step collapse to a closed-set outcome +
        synthetic refusal pair, with the wiring artifact line
        recording the closed-set reason token.
        """
        self._calls_received += 1
        entry_time_utc: str = self._clock.now_utc_iso()
        entry_time_utc = _normalize_to_z_suffixed_utc(entry_time_utc)
        original_content_length = _compute_original_content_length(
            payload
        )

        try:
            entries = getattr(
                self._recorder, "recorded_entries", None
            )
            if not isinstance(entries, tuple) or len(entries) == 0:
                self._record_outcome(
                    COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE
                )
                self._write_wiring_record_best_effort(
                    self._build_wiring_record(
                        outcome=COMPACT_OUTCOME_SKIPPED_NOT_TIERABLE,
                        reason=None,
                        tier_decision=None,
                        snapshot=None,
                        original_content_length=(
                            original_content_length
                        ),
                        candidate_id=None,
                        ping_id=None,
                        mint=None,
                        created_at_utc=entry_time_utc,
                        forwarded=False,
                    )
                )
                return self._synthetic_refusal_result()

            entry = entries[-1]

            try:
                tier_decision = (
                    project_recorded_entry_to_tier_decision_record(
                        entry=entry,
                        basis=self._context.basis,
                        created_at_utc=entry_time_utc,
                        session_id=self._context.session_id,
                    )
                )
            except Stage30_1TierDecisionError as exc:
                self._record_outcome(
                    COMPACT_OUTCOME_FAILED_TIER_DECISION
                )
                self._write_wiring_record_best_effort(
                    self._build_wiring_record(
                        outcome=(
                            COMPACT_OUTCOME_FAILED_TIER_DECISION
                        ),
                        reason=exc.reason,
                        tier_decision=None,
                        snapshot=None,
                        original_content_length=(
                            original_content_length
                        ),
                        candidate_id=entry.candidate_id,
                        ping_id=entry.candidate_id,
                        mint=entry.mint,
                        created_at_utc=entry_time_utc,
                        forwarded=False,
                    )
                )
                return self._synthetic_refusal_result()
            except Exception:
                self._record_outcome(
                    COMPACT_OUTCOME_FAILED_INPUT_SHAPE
                )
                self._write_wiring_record_best_effort(
                    self._build_wiring_record(
                        outcome=COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
                        reason=_PROJECTION_EXCEPTION_REASON,
                        tier_decision=None,
                        snapshot=None,
                        original_content_length=(
                            original_content_length
                        ),
                        candidate_id=entry.candidate_id,
                        ping_id=entry.candidate_id,
                        mint=entry.mint,
                        created_at_utc=entry_time_utc,
                        forwarded=False,
                    )
                )
                return self._synthetic_refusal_result()

            try:
                input_record: CompactPingInputRecord = (
                    build_compact_ping_input_record(
                        tier_decision=tier_decision,
                        entry=entry,
                        session_id=self._context.session_id,
                        created_at_utc=entry_time_utc,
                    )
                )
            except Exception:
                self._record_outcome(
                    COMPACT_OUTCOME_FAILED_INPUT_SHAPE
                )
                self._write_wiring_record_best_effort(
                    self._build_wiring_record(
                        outcome=COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
                        reason=_INPUT_BUILD_EXCEPTION_REASON,
                        tier_decision=tier_decision,
                        snapshot=None,
                        original_content_length=(
                            original_content_length
                        ),
                        candidate_id=entry.candidate_id,
                        ping_id=entry.candidate_id,
                        mint=entry.mint,
                        created_at_utc=entry_time_utc,
                        forwarded=False,
                    )
                )
                return self._synthetic_refusal_result()

            try:
                snapshot: CompactPingSnapshotRecord = (
                    render_compact_ping(input_record)
                )
            except Stage30_2CompactPingError as exc:
                if exc.reason == "BODY_EXCEEDS_HARD_CAP":
                    outcome = COMPACT_OUTCOME_FAILED_CAP
                else:
                    outcome = COMPACT_OUTCOME_FAILED_COMPACT_RENDER
                self._record_outcome(outcome)
                self._write_wiring_record_best_effort(
                    self._build_wiring_record(
                        outcome=outcome,
                        reason=exc.reason,
                        tier_decision=tier_decision,
                        snapshot=None,
                        original_content_length=(
                            original_content_length
                        ),
                        candidate_id=entry.candidate_id,
                        ping_id=entry.candidate_id,
                        mint=entry.mint,
                        created_at_utc=entry_time_utc,
                        forwarded=False,
                    )
                )
                return self._synthetic_refusal_result()

            if not isinstance(payload, dict):
                self._record_outcome(
                    COMPACT_OUTCOME_FAILED_INPUT_SHAPE
                )
                self._write_wiring_record_best_effort(
                    self._build_wiring_record(
                        outcome=COMPACT_OUTCOME_FAILED_INPUT_SHAPE,
                        reason=_PAYLOAD_NOT_DICT_REASON,
                        tier_decision=tier_decision,
                        snapshot=snapshot,
                        original_content_length=(
                            original_content_length
                        ),
                        candidate_id=entry.candidate_id,
                        ping_id=entry.candidate_id,
                        mint=entry.mint,
                        created_at_utc=entry_time_utc,
                        forwarded=False,
                    )
                )
                return self._synthetic_refusal_result()

            payload_copy: dict = dict(payload)
            payload_copy["content"] = snapshot.body_text

            try:
                append_tier_decision_record(
                    output_dir=self._context.output_dir,
                    record=tier_decision,
                )
            except (Stage30_1TierDecisionError, OSError):
                self._record_outcome(
                    COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE
                )
                self._write_wiring_record_best_effort(
                    self._build_wiring_record(
                        outcome=(
                            COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE
                        ),
                        reason=(
                            SNAPSHOT_WRITE_REASON_TIER_WRITE_FAILED
                        ),
                        tier_decision=tier_decision,
                        snapshot=snapshot,
                        original_content_length=(
                            original_content_length
                        ),
                        candidate_id=entry.candidate_id,
                        ping_id=entry.candidate_id,
                        mint=entry.mint,
                        created_at_utc=entry_time_utc,
                        forwarded=False,
                    )
                )
                return self._synthetic_refusal_result()

            try:
                append_compact_ping_snapshot(
                    output_dir=self._context.output_dir,
                    snapshot=snapshot,
                )
            except (Stage30_2CompactPingError, OSError):
                self._record_outcome(
                    COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE
                )
                self._write_wiring_record_best_effort(
                    self._build_wiring_record(
                        outcome=(
                            COMPACT_OUTCOME_FAILED_SNAPSHOT_WRITE
                        ),
                        reason=(
                            SNAPSHOT_WRITE_REASON_COMPACT_WRITE_FAILED
                        ),
                        tier_decision=tier_decision,
                        snapshot=snapshot,
                        original_content_length=(
                            original_content_length
                        ),
                        candidate_id=entry.candidate_id,
                        ping_id=entry.candidate_id,
                        mint=entry.mint,
                        created_at_utc=entry_time_utc,
                        forwarded=False,
                    )
                )
                return self._synthetic_refusal_result()

            self._write_wiring_record_best_effort(
                self._build_wiring_record(
                    outcome=COMPACT_OUTCOME_RENDERED,
                    reason=None,
                    tier_decision=tier_decision,
                    snapshot=snapshot,
                    original_content_length=(
                        original_content_length
                    ),
                    candidate_id=entry.candidate_id,
                    ping_id=entry.candidate_id,
                    mint=entry.mint,
                    created_at_utc=entry_time_utc,
                    forwarded=True,
                )
            )
            self._record_outcome(COMPACT_OUTCOME_RENDERED)

        except Exception:
            self._record_outcome(
                COMPACT_OUTCOME_FAILED_EXCEPTION
            )
            self._write_wiring_record_best_effort(
                self._build_wiring_record(
                    outcome=COMPACT_OUTCOME_FAILED_EXCEPTION,
                    reason=None,
                    tier_decision=None,
                    snapshot=None,
                    original_content_length=(
                        original_content_length
                    ),
                    candidate_id=None,
                    ping_id=None,
                    mint=None,
                    created_at_utc=entry_time_utc,
                    forwarded=False,
                )
            )
            return self._synthetic_refusal_result()

        return self._inner_transport.send_one_audited_post(
            webhook_identity=webhook_identity,
            payload=payload_copy,
        )

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _synthetic_refusal_result(
        self,
    ) -> _Stage30_3SyntheticRefusalResult:
        """Return a synthetic refusal result with the locked
        synthetic refusal transport status and ``None`` retry-
        after seconds.
        """
        return _Stage30_3SyntheticRefusalResult(
            transport_status=(
                _STAGE30_3_SYNTHETIC_REFUSAL_TRANSPORT_STATUS_LOCAL
            ),
            retry_after_seconds=None,
        )

    def _record_outcome(self, outcome_token: str) -> None:
        """Increment the closed-set outcome counter for
        ``outcome_token`` by one.
        """
        current = self._outcomes_by_token.get(outcome_token, 0)
        self._outcomes_by_token[outcome_token] = current + 1

    def _build_wiring_record(
        self,
        *,
        outcome: str,
        reason: Optional[str],
        tier_decision: Optional[TierDecisionRecord],
        snapshot: Optional[CompactPingSnapshotRecord],
        original_content_length: Optional[int],
        candidate_id: Optional[str],
        ping_id: Optional[str],
        mint: Optional[str],
        created_at_utc: str,
        forwarded: bool,
    ) -> Stage30_3RuntimeWiringArtifactRecord:
        """Assemble a Stage 30.3 wiring artifact record from the
        per-call outcome / reason / tier decision / snapshot /
        identifier slots.

        Value redaction discipline:

          * ``session_id`` / ``candidate_id`` / ``ping_id`` flow
            through the wrapper-local ``_safe_artifact_text``
            helper on every branch (defense-in-depth; Stage 30.1
            already sanitizes the same slots on the
            ``TierDecisionRecord`` echo, but the wrapper applies
            its own local helper so a future refactor cannot
            regress).
          * ``mint`` PREFERS the Stage 30.1 sanitized echo from
            ``tier_decision.mint`` when ``decide_tier`` has
            already produced a base58-safe mint; otherwise the
            slot flows through the wrapper-local
            ``_safe_artifact_mint`` helper on the raw value.

        Length / hash / tier slots are populated according to the
        success-prefix contract:

          * tier_token / tier_reason are populated whenever
            ``tier_decision`` is not ``None``;
          * compact_content_length / compact_body_sha256 are
            populated whenever ``snapshot`` is not ``None``;
          * the locked Stage 30.1 / Stage 30.2 basenames are
            populated only on ``RENDERED``.
        """
        safe_session_id = _safe_artifact_text(
            self._context.session_id
        )
        safe_candidate_id = _safe_artifact_text(candidate_id)
        safe_ping_id = _safe_artifact_text(ping_id)
        if (
            tier_decision is not None
            and tier_decision.mint is not None
        ):
            safe_mint: Optional[str] = tier_decision.mint
        else:
            safe_mint = _safe_artifact_mint(mint)
        if snapshot is not None:
            body_text: str = snapshot.body_text
            compact_content_length: Optional[int] = len(body_text)
            compact_sha: Optional[str] = hashlib.sha256(
                body_text.encode("utf-8")
            ).hexdigest()[:16]
        else:
            compact_content_length = None
            compact_sha = None
        if outcome == COMPACT_OUTCOME_RENDERED:
            tier_path: Optional[str] = (
                STAGE30_1_TIER_DECISION_ARTIFACT_BASENAME
            )
            compact_path: Optional[str] = (
                STAGE30_2_COMPACT_PING_ARTIFACT_BASENAME
            )
        else:
            tier_path = None
            compact_path = None
        if tier_decision is not None:
            tier_token: Optional[str] = tier_decision.tier_token
            tier_reason: Optional[str] = tier_decision.tier_reason
        else:
            tier_token = None
            tier_reason = None
        return Stage30_3RuntimeWiringArtifactRecord(
            schema_version=STAGE30_3_RUNTIME_WIRING_SCHEMA_VERSION,
            session_id=safe_session_id,
            candidate_id=safe_candidate_id,
            ping_id=safe_ping_id,
            mint=safe_mint,
            wrapper_order=self._wrapper_order,
            compact_outcome=outcome,
            compact_outcome_reason=reason,
            tier_token=tier_token,
            tier_reason=tier_reason,
            basis=self._context.basis,
            original_content_length_chars=(
                original_content_length
            ),
            compact_content_length_chars=compact_content_length,
            compact_body_sha256_hex_prefix_16=compact_sha,
            tier_snapshot_path_basename=tier_path,
            compact_snapshot_path_basename=compact_path,
            forwarded_to_inner_transport=forwarded,
            created_at_utc=created_at_utc,
        )

    def _write_wiring_record_best_effort(
        self,
        record: Stage30_3RuntimeWiringArtifactRecord,
    ) -> None:
        """Append the wiring record best-effort: swallow every
        exception so a wiring-write failure on a non-success
        branch never escalates and a wiring-write failure on the
        success branch never blocks the inner-transport forward
        (the compact body itself is already safe by construction).
        """
        try:
            append_runtime_wiring_record(
                output_dir=self._context.output_dir,
                record=record,
            )
        except Exception:
            return


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _normalize_to_z_suffixed_utc(value: object) -> object:
    """Normalize a ``+00:00`` UTC offset suffix to the trailing
    ``Z`` form expected by the Stage 30.1 / Stage 30.2 safe-shape
    ISO-8601 validators.

    The injected wrapper clock may emit either UTC notation: a
    Python ``datetime.isoformat()`` value carries the numeric
    ``+00:00`` offset, while the Stage 30.1 / 30.2 closed-set
    safe-shape pattern accepts only the ``Z`` (Zulu) suffix. Both
    forms are valid ISO-8601 / RFC-3339 UTC; this helper bridges
    the two so a well-behaved ``+00:00`` clock value is not refused
    by the downstream Z-only validators.

    Conservative by construction:

      * ``"...+00:00"``  -> ``"...Z"`` (only the trailing offset is
        rewritten; the date / time / fractional-second prefix is
        preserved byte-for-byte).
      * a value already ending in ``"Z"`` is returned unchanged.
      * any other offset (e.g. ``"-05:00"``) is returned unchanged
        (the wrapper does NOT fabricate a UTC reinterpretation of a
        non-UTC offset).
      * a non-``str`` value is returned unchanged so the existing
        downstream shape checks see the original object.
    """
    if isinstance(value, str) and value.endswith("+00:00"):
        return value[:-6] + "Z"
    return value


def _compute_original_content_length(
    payload: Any,
) -> Optional[int]:
    """Return ``len(payload["content"])`` when ``payload`` is a
    dict whose ``"content"`` slot is a string, else ``None``. The
    wrapper records this length on every wiring artifact line so
    an operator can audit the compact-vs-original ratio offline.
    """
    if not isinstance(payload, dict):
        return None
    value = payload.get("content")
    if not isinstance(value, str):
        return None
    return len(value)


__all__ = (
    "Stage30_3CompactBodyTransportWrapper",
)
