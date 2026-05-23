"""Stage 28.6 bounded private session runner.

Stage 28.6 composes the Stage 28.1 / 28.2 / 28.3a / 28.3b / 28.4 /
28.5 reliability primitives into a single bounded private session
runner with graceful shutdown semantics. The runner:

  * iterates a caller-supplied bounded candidate stream / iterator,
  * reserves dispatch intent in the Stage 28.2 ledger BEFORE any
    send,
  * records pre-send provenance reference BEFORE any send,
  * calls the injected Stage 28.6 transport (typically a fake
    transport in tests; a Stage 28.4-shaped adapter in a future
    Stage 28.7 authorized smoke),
  * classifies failures via the Stage 28.3a classifier,
  * consults the Stage 28.3b retry policy for retry decisions
    (no sleep is ever performed),
  * executes bounded immediate retry attempts against the fake
    transport (the retry executor is the runner's responsibility),
  * emits heartbeats during the session via the Stage 28.5
    heartbeat writer,
  * writes the current health snapshot via the Stage 28.5 snapshot
    writer,
  * writes the final run summary via the Stage 28.5 summary
    writer at shutdown,
  * honours ``max_events`` / ``max_dispatches`` / ``max_total_retries``
    / ``max_ticks`` bounds,
  * honours an injected ``Stage28_6StopSignal`` stop request,
  * fails closed on artifact / ledger write failures per the
    runner config,
  * NEVER opens a real network connection, NEVER reads the process
    environment, NEVER sleeps, NEVER schedules, NEVER spawns
    threads / async tasks / subprocesses.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No direct network library import. The runner imports the Stage
    28.4 transport models only for closed-set status tokens; the
    Stage 28.4 transport implementation module is NOT imported.
    The runner accepts the Stage 28.6 transport protocol
    (``Stage28_6PrivateTransport``) and uses duck typing.
  * No sleep / scheduling / queue / thread / async / subprocess.
  * The runner does not install OS signal handlers; the
    ``Stage28_6StopSignal`` injected primitive is the only stop
    surface.
  * Caller-supplied paths are validated by the underlying Stage
    28.2 / 28.5 writers; the runner adds no extra path handling.

This module imports only stdlib (``pathlib`` / ``typing``) plus
the Stage 28.2 ledger, Stage 28.3a classifier, Stage 28.3b retry
policy, Stage 28.4 transport models (closed-set token reuse only),
Stage 28.5 health-status models + heartbeat / snapshot writers,
and the Stage 28.6 session runner models. It does NOT import
Stage 21-27 production code, does NOT import any other network /
RPC / messaging / DB / scheduler / secrets-management library,
does NOT read the process environment, does NOT define a CLI
surface, and contains no top-level I/O.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from PHX2.stage28.audited_http_transport_models import (
    TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_PAYLOAD_REFUSED,
    TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_SENT_OK,
    TRANSPORT_STATUS_SERVER_ERROR,
    TRANSPORT_STATUS_VALIDATION_FAILED,
    TRANSPORT_STATUS_VALUES,
)
from PHX2.stage28.dispatch_ledger import (
    record_pre_send,
    record_terminal,
    replay_ledger,
    reserve_dispatch_intent,
)
from PHX2.stage28.dispatch_ledger_models import (
    DEDUPE_STATE_DISPATCHED_FAILED,
    DEDUPE_STATE_DISPATCHED_OK,
    DEDUPE_STATE_REFUSED_PRE_SEND,
    DISPATCH_DECISION_PROCEED,
    DISPATCH_DECISION_REJECTED_INVALID_TRANSITION,
    DISPATCH_DECISION_SUPPRESS_AMBIGUOUS,
    DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL,
    DispatchDedupeKey,
    FAILURE_REASON_UNSPECIFIED,
    Stage28_2DispatchLedgerError,
    build_dispatch_dedupe_key,
)
from PHX2.stage28.failure_classification import classify_failure
from PHX2.stage28.failure_classification_models import (
    DOMAIN_DISCORD_TRANSPORT,
    FAILURE_KIND_ARTIFACT_WRITE_FAILED,
    FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED,
    FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED,
    FAILURE_KIND_DISCORD_NETWORK_ERROR,
    FAILURE_KIND_DISCORD_RATE_LIMITED,
    FAILURE_KIND_DISCORD_SERVER_ERROR,
    FAILURE_KIND_LEDGER_AMBIGUOUS_SEND,
    FAILURE_KIND_LEDGER_DUPLICATE_TERMINAL,
    FAILURE_KIND_LEDGER_WRITE_FAILED,
    FAILURE_KIND_MALFORMED_EVENT,
    FAILURE_KIND_PRICE_MISSING,
    FAILURE_KIND_PRICE_STALE,
    FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED,
    FAILURE_KIND_USDC_OBSERVE_ONLY,
    SESSION_CONTINUATION_STOP,
    Stage28_3aFailureClassification,
    build_failure_input,
)
from PHX2.stage28.health_snapshot_writer import (
    Stage28_5HealthSnapshotWriterError,
    write_final_run_summary,
    write_health_snapshot,
)
from PHX2.stage28.health_status_models import (
    ARTIFACT_STATUS_OK,
    ARTIFACT_STATUS_WRITE_FAILED,
    DISPATCH_STATUS_AMBIGUOUS,
    DISPATCH_STATUS_FAILED,
    DISPATCH_STATUS_NOT_STARTED,
    DISPATCH_STATUS_OK,
    DISPATCH_STATUS_SUPPRESSED,
    HEALTH_STATUS_DEGRADED,
    HEALTH_STATUS_FAILED,
    HEALTH_STATUS_HEALTHY,
    HEALTH_STATUS_STOPPED,
    LAST_EVENT_STATUS_NONE_OBSERVED,
    LAST_EVENT_STATUS_OBSERVED,
    LAST_PING_STATUS_NONE_RENDERED,
    LAST_PING_STATUS_RENDERED,
    LAST_PING_STATUS_SUPPRESSED,
    LEDGER_STATUS_AMBIGUOUS,
    LEDGER_STATUS_DUPLICATE_SUPPRESSED,
    LEDGER_STATUS_NOT_STARTED,
    LEDGER_STATUS_OK,
    LEDGER_STATUS_REPLAY_FAILED,
    LEDGER_STATUS_WRITE_FAILED,
    PRICE_STATUS_MISSING as STAGE28_5_PRICE_STATUS_MISSING,
    PRICE_STATUS_OK as STAGE28_5_PRICE_STATUS_OK,
    PRICE_STATUS_STALE as STAGE28_5_PRICE_STATUS_STALE,
    PRICE_STATUS_TIMEOUT as STAGE28_5_PRICE_STATUS_TIMEOUT,
    PROVIDER_STATUS_NOT_STARTED,
    PROVIDER_STATUS_OK,
    RETRY_BUDGET_STATUS_EXHAUSTED,
    RETRY_BUDGET_STATUS_NEAR_LIMIT,
    RETRY_BUDGET_STATUS_OK,
    STOP_REASON_ERROR,
    STOP_REASON_MAX_EVENTS,
    STOP_REASON_MAX_WALL_SECONDS,
    STOP_REASON_NOT_STOPPED,
    STOP_REASON_OPERATOR_STOP,
    STOP_REASON_RETRY_BUDGET_EXHAUSTED,
    STOP_REASON_SIGINT,
    Stage28_5HealthStatusError,
    TRANSPORT_STATUS_NETWORK_ERROR as STAGE28_5_TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_NOT_STARTED as STAGE28_5_TRANSPORT_STATUS_NOT_STARTED,
    TRANSPORT_STATUS_OK as STAGE28_5_TRANSPORT_STATUS_OK,
    TRANSPORT_STATUS_RATE_LIMITED as STAGE28_5_TRANSPORT_STATUS_RATE_LIMITED,
    TRANSPORT_STATUS_REFUSED as STAGE28_5_TRANSPORT_STATUS_REFUSED,
    TRANSPORT_STATUS_SERVER_ERROR as STAGE28_5_TRANSPORT_STATUS_SERVER_ERROR,
    build_final_run_summary_record,
    build_health_snapshot_record,
    build_heartbeat_record,
)
from PHX2.stage28.heartbeat_writer import (
    Stage28_5HeartbeatWriterError,
    append_heartbeat,
)
from PHX2.stage28.retry_policy import decide_retry
from PHX2.stage28.retry_policy_models import (
    RETRY_OUTCOME_ALLOWED,
    Stage28_3bRetryDecision,
    build_retry_policy_input,
)
from PHX2.stage28.session_runner_models import (
    CANDIDATE_PAIR_STATUS_DISAGREE,
    CANDIDATE_PAIR_STATUS_OK,
    CANDIDATE_PAIR_STATUS_UNKNOWN,
    CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY,
    CANDIDATE_PRICE_STATUS_MISSING,
    CANDIDATE_PRICE_STATUS_OK,
    CANDIDATE_PRICE_STATUS_STALE,
    CANDIDATE_PRICE_STATUS_TIMEOUT,
    Stage28_6CandidateEvent,
    Stage28_6PrivateTransport,
    Stage28_6RunSummary,
    Stage28_6RunnerConfig,
    Stage28_6SessionRunnerError,
    Stage28_6StopSignal,
    Stage28_6TickClock,
    build_run_summary,
)


# ---------------------------------------------------------------------------
# Stage 28.6 internal counter state
# ---------------------------------------------------------------------------


class _RunCounters:
    """Internal mutable counter bag for the Stage 28.6 runner.

    Kept inside the runner module so the immutable
    ``Stage28_6RunSummary`` record is constructed once at shutdown
    from a single snapshot of these counters.
    """

    def __init__(self) -> None:
        self.events_seen: int = 0
        self.candidates_seen: int = 0
        self.dispatch_attempts: int = 0
        self.dispatch_success: int = 0
        self.dispatch_failure: int = 0
        self.retries_attempted: int = 0
        self.duplicates_suppressed: int = 0
        self.ambiguous_suppressed: int = 0
        self.unknown_pair_suppressed: int = 0
        self.disagree_pair_suppressed: int = 0
        self.usdc_observe_only: int = 0
        self.stale_price_suppressed: int = 0
        self.missing_price_suppressed: int = 0
        self.malformed_events: int = 0
        self.ledger_failures: int = 0
        self.artifact_failures: int = 0
        self.transport_failures: int = 0


# ---------------------------------------------------------------------------
# Stage 28.5-shape status aggregator
# ---------------------------------------------------------------------------


class _RunStatusAggregator:
    """Internal mutable status bag tracking last-known Stage 28.5-
    shape status tokens used to drive heartbeats / snapshots.
    """

    def __init__(self) -> None:
        self.provider_status: str = PROVIDER_STATUS_OK
        self.price_status: str = STAGE28_5_PRICE_STATUS_OK
        self.dispatch_status: str = DISPATCH_STATUS_NOT_STARTED
        self.ledger_status: str = LEDGER_STATUS_NOT_STARTED
        self.transport_status: str = (
            STAGE28_5_TRANSPORT_STATUS_NOT_STARTED
        )
        self.artifact_status: str = ARTIFACT_STATUS_OK
        self.last_event_status: str = LAST_EVENT_STATUS_NONE_OBSERVED
        self.last_ping_status: str = LAST_PING_STATUS_NONE_RENDERED


# ---------------------------------------------------------------------------
# Internal helpers: status mapping
# ---------------------------------------------------------------------------


def _stage28_5_price_status_for(candidate_status: str) -> str:
    if candidate_status == CANDIDATE_PRICE_STATUS_OK:
        return STAGE28_5_PRICE_STATUS_OK
    if candidate_status == CANDIDATE_PRICE_STATUS_STALE:
        return STAGE28_5_PRICE_STATUS_STALE
    if candidate_status == CANDIDATE_PRICE_STATUS_MISSING:
        return STAGE28_5_PRICE_STATUS_MISSING
    if candidate_status == CANDIDATE_PRICE_STATUS_TIMEOUT:
        return STAGE28_5_PRICE_STATUS_TIMEOUT
    return STAGE28_5_PRICE_STATUS_OK


def _stage28_5_transport_status_for(
    stage28_4_transport_status: str,
) -> str:
    if stage28_4_transport_status == TRANSPORT_STATUS_SENT_OK:
        return STAGE28_5_TRANSPORT_STATUS_OK
    if stage28_4_transport_status == TRANSPORT_STATUS_RATE_LIMITED:
        return STAGE28_5_TRANSPORT_STATUS_RATE_LIMITED
    if stage28_4_transport_status == TRANSPORT_STATUS_SERVER_ERROR:
        return STAGE28_5_TRANSPORT_STATUS_SERVER_ERROR
    if stage28_4_transport_status == TRANSPORT_STATUS_NETWORK_ERROR:
        return STAGE28_5_TRANSPORT_STATUS_NETWORK_ERROR
    if stage28_4_transport_status in (
        TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
        TRANSPORT_STATUS_VALIDATION_FAILED,
        TRANSPORT_STATUS_PAYLOAD_REFUSED,
    ):
        return STAGE28_5_TRANSPORT_STATUS_REFUSED
    return STAGE28_5_TRANSPORT_STATUS_REFUSED


def _retry_budget_status_for(
    retries_attempted: int, max_total_retries: int
) -> str:
    if max_total_retries == 0:
        if retries_attempted == 0:
            return RETRY_BUDGET_STATUS_OK
        return RETRY_BUDGET_STATUS_EXHAUSTED
    if retries_attempted >= max_total_retries:
        return RETRY_BUDGET_STATUS_EXHAUSTED
    # The threshold for NEAR_LIMIT is intentionally simple: when we
    # have used at least half of the session-wide retry budget.
    if retries_attempted * 2 >= max_total_retries:
        return RETRY_BUDGET_STATUS_NEAR_LIMIT
    return RETRY_BUDGET_STATUS_OK


def _current_health_status_for(
    counters: _RunCounters, status: _RunStatusAggregator
) -> str:
    if counters.ledger_failures > 0 and counters.dispatch_success == 0:
        return HEALTH_STATUS_FAILED
    if (
        counters.artifact_failures > 0
        or counters.ledger_failures > 0
        or counters.transport_failures > 0
        or status.ledger_status == LEDGER_STATUS_AMBIGUOUS
        or status.dispatch_status == DISPATCH_STATUS_FAILED
    ):
        return HEALTH_STATUS_DEGRADED
    return HEALTH_STATUS_HEALTHY


# ---------------------------------------------------------------------------
# Internal helpers: classification of suppressed candidates
# ---------------------------------------------------------------------------


def _classify_suppression(
    candidate: Stage28_6CandidateEvent,
) -> Optional[Stage28_3aFailureClassification]:
    """Return the Stage 28.3a classification for a candidate the
    runner suppresses without attempting a send.

    Returns ``None`` when the candidate is dispatchable (no
    suppression).
    """
    if candidate.malformed:
        return classify_failure(
            build_failure_input(
                failure_kind_hint=FAILURE_KIND_MALFORMED_EVENT,
            )
        )
    if candidate.pair_status == CANDIDATE_PAIR_STATUS_UNKNOWN:
        return classify_failure(
            build_failure_input(
                failure_kind_hint=FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED,
            )
        )
    if candidate.pair_status == CANDIDATE_PAIR_STATUS_DISAGREE:
        return classify_failure(
            build_failure_input(
                failure_kind_hint=FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED,
            )
        )
    if candidate.pair_status == CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY:
        return classify_failure(
            build_failure_input(
                failure_kind_hint=FAILURE_KIND_USDC_OBSERVE_ONLY,
            )
        )
    if candidate.price_status == CANDIDATE_PRICE_STATUS_STALE:
        return classify_failure(
            build_failure_input(
                failure_kind_hint=FAILURE_KIND_PRICE_STALE,
            )
        )
    if candidate.price_status == CANDIDATE_PRICE_STATUS_MISSING:
        return classify_failure(
            build_failure_input(
                failure_kind_hint=FAILURE_KIND_PRICE_MISSING,
            )
        )
    if not candidate.dispatch_allowed:
        return classify_failure(
            build_failure_input(
                failure_kind_hint=FAILURE_KIND_MALFORMED_EVENT,
            )
        )
    return None


def _classify_transport_failure(
    stage28_4_transport_status: str,
) -> Stage28_3aFailureClassification:
    if stage28_4_transport_status == TRANSPORT_STATUS_RATE_LIMITED:
        return classify_failure(
            build_failure_input(
                failure_kind_hint=FAILURE_KIND_DISCORD_RATE_LIMITED,
                domain_hint=DOMAIN_DISCORD_TRANSPORT,
            )
        )
    if stage28_4_transport_status == TRANSPORT_STATUS_SERVER_ERROR:
        return classify_failure(
            build_failure_input(
                failure_kind_hint=FAILURE_KIND_DISCORD_SERVER_ERROR,
                domain_hint=DOMAIN_DISCORD_TRANSPORT,
            )
        )
    if stage28_4_transport_status == TRANSPORT_STATUS_NETWORK_ERROR:
        return classify_failure(
            build_failure_input(
                failure_kind_hint=FAILURE_KIND_DISCORD_NETWORK_ERROR,
                domain_hint=DOMAIN_DISCORD_TRANSPORT,
            )
        )
    if stage28_4_transport_status in (
        TRANSPORT_STATUS_AUTH_OR_WEBHOOK_REFUSED,
        TRANSPORT_STATUS_VALIDATION_FAILED,
        TRANSPORT_STATUS_PAYLOAD_REFUSED,
    ):
        return classify_failure(
            build_failure_input(
                failure_kind_hint=(
                    FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED
                ),
                domain_hint=DOMAIN_DISCORD_TRANSPORT,
            )
        )
    return classify_failure(
        build_failure_input(
            failure_kind_hint=(
                FAILURE_KIND_DISCORD_AUTH_OR_WEBHOOK_REFUSED
            ),
            domain_hint=DOMAIN_DISCORD_TRANSPORT,
        )
    )


# ---------------------------------------------------------------------------
# Stage 28.6 runner outcome
# ---------------------------------------------------------------------------


class _StopRequest:
    """Internal latch used by the runner to signal the main loop to
    break out.

    Carries the locked Stage 28.5 ``stop_reason`` value the runner
    should attach to the final summary.
    """

    def __init__(self) -> None:
        self.stopped: bool = False
        self.reason: str = STOP_REASON_NOT_STOPPED

    def stop(self, reason: str) -> None:
        self.stopped = True
        self.reason = reason


# ---------------------------------------------------------------------------
# Stage 28.6 bounded private session runner
# ---------------------------------------------------------------------------


class Stage28_6BoundedPrivateSessionRunner:
    """Stage 28.6 bounded private session runner.

    A runner instance holds the injected dependencies + paths +
    config; ``run(...)`` consumes a bounded candidate iterable and
    returns a ``Stage28_6RunSummary``. The runner is single-shot:
    each ``run(...)`` call walks the entire injected stream once
    and then writes the final summary.

    Injected dependencies:

      * ``config``         -- ``Stage28_6RunnerConfig``.
      * ``transport``      -- ``Stage28_6PrivateTransport``.
      * ``ledger_path``    -- caller-supplied ``Path``.
      * ``heartbeat_path`` -- caller-supplied ``Path``.
      * ``snapshot_path``  -- caller-supplied ``Path``.
      * ``summary_path``   -- caller-supplied ``Path``.
      * ``stop_signal``    -- optional ``Stage28_6StopSignal``.
      * ``tick_clock``     -- optional ``Stage28_6TickClock``.

    Runtime guarantees:

      * one transport call per attempt,
      * no transport call on suppressed candidates,
      * no transport call on duplicate / ambiguous ledger state,
      * no transport call when pre-send artifact / ledger write
        fails,
      * heartbeats emitted every ``heartbeat_every_n_events``
        events,
      * health snapshot refreshed on stop,
      * final summary written on stop,
      * deterministic: no real wall-clock, no sleep, no thread, no
        async, no subprocess.
    """

    def __init__(
        self,
        *,
        config: Stage28_6RunnerConfig,
        transport: Stage28_6PrivateTransport,
        ledger_path: Path,
        heartbeat_path: Path,
        snapshot_path: Path,
        summary_path: Path,
        stop_signal: Optional[Stage28_6StopSignal] = None,
        tick_clock: Optional[Stage28_6TickClock] = None,
    ) -> None:
        if not isinstance(config, Stage28_6RunnerConfig):
            raise Stage28_6SessionRunnerError(
                "Stage 28.6 runner rejecting non-Stage28_6RunnerConfig"
            )
        if not hasattr(transport, "send_one_audited_post"):
            raise Stage28_6SessionRunnerError(
                "Stage 28.6 runner rejecting transport without "
                "send_one_audited_post method"
            )
        for label, value in (
            ("ledger_path", ledger_path),
            ("heartbeat_path", heartbeat_path),
            ("snapshot_path", snapshot_path),
            ("summary_path", summary_path),
        ):
            if not isinstance(value, Path):
                raise Stage28_6SessionRunnerError(
                    f"Stage 28.6 runner rejecting non-Path "
                    f"{label}"
                )
        self._config: Stage28_6RunnerConfig = config
        self._transport: Stage28_6PrivateTransport = transport
        self._ledger_path: Path = ledger_path
        self._heartbeat_path: Path = heartbeat_path
        self._snapshot_path: Path = snapshot_path
        self._summary_path: Path = summary_path
        self._stop_signal: Optional[Stage28_6StopSignal] = stop_signal
        self._tick_clock: Optional[Stage28_6TickClock] = tick_clock

    def run(
        self,
        candidate_stream: Iterable[Stage28_6CandidateEvent],
    ) -> Stage28_6RunSummary:
        counters = _RunCounters()
        status = _RunStatusAggregator()
        stop = _StopRequest()
        heartbeat_index: int = 0
        ticks_elapsed: int = 0

        for candidate in candidate_stream:
            if stop.stopped:
                break
            if not isinstance(candidate, Stage28_6CandidateEvent):
                counters.malformed_events += 1
                status.last_event_status = LAST_EVENT_STATUS_OBSERVED
                counters.events_seen += 1
                if (
                    self._config.fail_closed_on_artifact_error
                    is False
                ):
                    continue
                continue
            counters.events_seen += 1
            status.last_event_status = LAST_EVENT_STATUS_OBSERVED
            self._process_candidate(
                candidate=candidate,
                counters=counters,
                status=status,
                stop=stop,
            )
            if not stop.stopped:
                if (
                    counters.events_seen
                    % self._config.heartbeat_every_n_events
                    == 0
                ):
                    heartbeat_index = self._emit_heartbeat(
                        counters=counters,
                        status=status,
                        heartbeat_index=heartbeat_index,
                        stop=stop,
                    )
                if self._tick_clock is not None:
                    ticks_elapsed = self._tick_clock.tick()
                else:
                    ticks_elapsed += 1
                if ticks_elapsed >= self._config.max_ticks:
                    stop.stop(STOP_REASON_MAX_WALL_SECONDS)
                if (
                    not stop.stopped
                    and counters.events_seen >= self._config.max_events
                ):
                    stop.stop(STOP_REASON_MAX_EVENTS)
                if (
                    not stop.stopped
                    and counters.dispatch_attempts
                    >= self._config.max_dispatches
                ):
                    stop.stop(STOP_REASON_MAX_EVENTS)
                if (
                    not stop.stopped
                    and self._config.max_total_retries > 0
                    and counters.retries_attempted
                    >= self._config.max_total_retries
                ):
                    stop.stop(STOP_REASON_RETRY_BUDGET_EXHAUSTED)
                if not stop.stopped and self._stop_signal is not None:
                    if self._stop_signal.is_requested():
                        stop.stop(self._stop_signal.reason)

        if not stop.stopped:
            stop.stop(STOP_REASON_MAX_EVENTS)

        self._write_final_health_snapshot(
            counters=counters, status=status
        )
        summary = self._build_summary(
            counters=counters,
            status=status,
            stop=stop,
        )
        self._write_final_summary(summary=summary, status=status)
        return summary

    # -----------------------------------------------------------------
    # Per-candidate processing
    # -----------------------------------------------------------------

    def _process_candidate(
        self,
        *,
        candidate: Stage28_6CandidateEvent,
        counters: _RunCounters,
        status: _RunStatusAggregator,
        stop: _StopRequest,
    ) -> None:
        status.price_status = _stage28_5_price_status_for(
            candidate.price_status
        )
        suppression = _classify_suppression(candidate)
        if suppression is not None:
            self._account_suppression(
                candidate=candidate,
                classification=suppression,
                counters=counters,
                status=status,
            )
            return

        counters.candidates_seen += 1

        try:
            dedupe_key = build_dispatch_dedupe_key(
                token_mint=candidate.token_mint,
                pair_quote_asset=candidate.pair_quote_asset,
                event_kind=candidate.event_kind,
                ping_type=candidate.ping_type,
                normalized_event_id=candidate.normalized_event_id,
            )
        except Stage28_2DispatchLedgerError:
            counters.ledger_failures += 1
            status.ledger_status = LEDGER_STATUS_WRITE_FAILED
            status.dispatch_status = DISPATCH_STATUS_FAILED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            if self._config.fail_closed_on_ledger_error:
                stop.stop(STOP_REASON_ERROR)
            return

        try:
            replay = replay_ledger(self._ledger_path)
        except Stage28_2DispatchLedgerError:
            counters.ledger_failures += 1
            status.ledger_status = LEDGER_STATUS_REPLAY_FAILED
            status.dispatch_status = DISPATCH_STATUS_FAILED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            if self._config.fail_closed_on_ledger_error:
                stop.stop(STOP_REASON_ERROR)
            return

        try:
            reserve_decision = reserve_dispatch_intent(
                ledger_path=self._ledger_path,
                dedupe_key=dedupe_key,
                replay=replay,
            )
        except Stage28_2DispatchLedgerError:
            counters.ledger_failures += 1
            status.ledger_status = LEDGER_STATUS_WRITE_FAILED
            status.dispatch_status = DISPATCH_STATUS_FAILED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            if self._config.fail_closed_on_ledger_error:
                stop.stop(STOP_REASON_ERROR)
            return

        if (
            reserve_decision.decision
            == DISPATCH_DECISION_SUPPRESS_DUPLICATE_TERMINAL
        ):
            counters.duplicates_suppressed += 1
            status.ledger_status = LEDGER_STATUS_DUPLICATE_SUPPRESSED
            status.dispatch_status = DISPATCH_STATUS_SUPPRESSED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            return
        if (
            reserve_decision.decision
            == DISPATCH_DECISION_SUPPRESS_AMBIGUOUS
        ):
            counters.ambiguous_suppressed += 1
            status.ledger_status = LEDGER_STATUS_AMBIGUOUS
            status.dispatch_status = DISPATCH_STATUS_AMBIGUOUS
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            return
        if (
            reserve_decision.decision
            == DISPATCH_DECISION_REJECTED_INVALID_TRANSITION
        ):
            counters.ledger_failures += 1
            status.ledger_status = LEDGER_STATUS_WRITE_FAILED
            status.dispatch_status = DISPATCH_STATUS_FAILED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            if self._config.fail_closed_on_ledger_error:
                stop.stop(STOP_REASON_ERROR)
            return
        # PROCEED.
        status.ledger_status = LEDGER_STATUS_OK

        try:
            replay = replay_ledger(self._ledger_path)
        except Stage28_2DispatchLedgerError:
            counters.ledger_failures += 1
            status.ledger_status = LEDGER_STATUS_REPLAY_FAILED
            status.dispatch_status = DISPATCH_STATUS_FAILED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            if self._config.fail_closed_on_ledger_error:
                stop.stop(STOP_REASON_ERROR)
            return

        try:
            pre_send_decision = record_pre_send(
                ledger_path=self._ledger_path,
                dedupe_key=dedupe_key,
                artifact_reference=(
                    candidate.pre_send_artifact_reference
                ),
                replay=replay,
            )
        except Stage28_2DispatchLedgerError:
            counters.artifact_failures += 1
            counters.ledger_failures += 1
            status.artifact_status = ARTIFACT_STATUS_WRITE_FAILED
            status.ledger_status = LEDGER_STATUS_WRITE_FAILED
            status.dispatch_status = DISPATCH_STATUS_FAILED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            self._record_refused_pre_send_safely(dedupe_key=dedupe_key)
            if (
                self._config.fail_closed_on_artifact_error
                or self._config.fail_closed_on_ledger_error
            ):
                stop.stop(STOP_REASON_ERROR)
            return

        if pre_send_decision.decision != DISPATCH_DECISION_PROCEED:
            counters.ambiguous_suppressed += 1
            status.ledger_status = LEDGER_STATUS_AMBIGUOUS
            status.dispatch_status = DISPATCH_STATUS_AMBIGUOUS
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            return
        status.last_ping_status = LAST_PING_STATUS_RENDERED

        self._attempt_transport_with_bounded_retry(
            candidate=candidate,
            dedupe_key=dedupe_key,
            counters=counters,
            status=status,
            stop=stop,
        )

    # -----------------------------------------------------------------
    # Suppression accounting
    # -----------------------------------------------------------------

    def _account_suppression(
        self,
        *,
        candidate: Stage28_6CandidateEvent,
        classification: Stage28_3aFailureClassification,
        counters: _RunCounters,
        status: _RunStatusAggregator,
    ) -> None:
        kind = classification.failure_kind
        if kind == FAILURE_KIND_MALFORMED_EVENT and candidate.malformed:
            counters.malformed_events += 1
            status.dispatch_status = DISPATCH_STATUS_SUPPRESSED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            return
        if kind == FAILURE_KIND_UNKNOWN_PAIR_SUPPRESSED:
            counters.unknown_pair_suppressed += 1
            status.dispatch_status = DISPATCH_STATUS_SUPPRESSED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            return
        if kind == FAILURE_KIND_DISAGREE_PAIR_SUPPRESSED:
            counters.disagree_pair_suppressed += 1
            status.dispatch_status = DISPATCH_STATUS_SUPPRESSED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            return
        if kind == FAILURE_KIND_USDC_OBSERVE_ONLY:
            counters.usdc_observe_only += 1
            status.dispatch_status = DISPATCH_STATUS_SUPPRESSED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            return
        if kind == FAILURE_KIND_PRICE_STALE:
            counters.stale_price_suppressed += 1
            status.dispatch_status = DISPATCH_STATUS_SUPPRESSED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            return
        if kind == FAILURE_KIND_PRICE_MISSING:
            counters.missing_price_suppressed += 1
            status.dispatch_status = DISPATCH_STATUS_SUPPRESSED
            status.last_ping_status = LAST_PING_STATUS_SUPPRESSED
            return
        # Defensive: unrecognized suppression falls back to malformed.
        counters.malformed_events += 1
        status.dispatch_status = DISPATCH_STATUS_SUPPRESSED
        status.last_ping_status = LAST_PING_STATUS_SUPPRESSED

    # -----------------------------------------------------------------
    # Transport attempt + bounded retry execution
    # -----------------------------------------------------------------

    def _attempt_transport_with_bounded_retry(
        self,
        *,
        candidate: Stage28_6CandidateEvent,
        dedupe_key: DispatchDedupeKey,
        counters: _RunCounters,
        status: _RunStatusAggregator,
        stop: _StopRequest,
    ) -> None:
        attempts_already_made: int = 0
        last_classification: Optional[Stage28_3aFailureClassification] = (
            None
        )
        # The Stage 28.6 retry executor is bounded by:
        #   - the per-failure-kind Stage 28.3b profile budget,
        #   - the session-wide ``max_total_retries`` budget,
        #   - a hard local cap that prevents an unbounded loop even
        #     if the policy somehow returns RETRY_ALLOWED forever.
        local_hard_cap: int = self._config.max_total_retries + 1
        for _attempt_iter in range(local_hard_cap + 1):
            counters.dispatch_attempts += 1
            result = self._transport.send_one_audited_post(
                webhook_identity=candidate.webhook_identity,
                payload=candidate.rendered_payload,
            )
            status.transport_status = (
                _stage28_5_transport_status_for(result.transport_status)
            )
            if result.transport_status == TRANSPORT_STATUS_SENT_OK:
                counters.dispatch_success += 1
                status.dispatch_status = DISPATCH_STATUS_OK
                self._record_terminal_safely(
                    dedupe_key=dedupe_key,
                    terminal_status=DEDUPE_STATE_DISPATCHED_OK,
                    counters=counters,
                    status=status,
                    stop=stop,
                )
                return
            counters.transport_failures += 1
            classification = _classify_transport_failure(
                result.transport_status
            )
            last_classification = classification
            policy_input = build_retry_policy_input(
                classification=classification,
                attempts_already_made=attempts_already_made,
                global_retries_used=counters.retries_attempted,
                global_max_retries=self._config.max_total_retries,
                retry_after_hint_seconds=result.retry_after_seconds,
            )
            decision: Stage28_3bRetryDecision = decide_retry(
                policy_input
            )
            if decision.retry_outcome == RETRY_OUTCOME_ALLOWED:
                counters.retries_attempted += 1
                attempts_already_made += 1
                if (
                    self._config.max_total_retries > 0
                    and counters.retries_attempted
                    >= self._config.max_total_retries
                ):
                    # Budget will be exhausted on the next decision;
                    # let the loop run once more and let the policy
                    # emit RETRY_EXHAUSTED naturally.
                    pass
                continue
            # Non-retry outcome: this attempt is the terminal one.
            counters.dispatch_failure += 1
            status.dispatch_status = DISPATCH_STATUS_FAILED
            self._record_terminal_safely(
                dedupe_key=dedupe_key,
                terminal_status=DEDUPE_STATE_DISPATCHED_FAILED,
                counters=counters,
                status=status,
                stop=stop,
            )
            if (
                classification.session_continuation_status
                == SESSION_CONTINUATION_STOP
            ):
                stop.stop(STOP_REASON_ERROR)
            return
        # Defensive: hard cap reached without a terminal decision.
        counters.dispatch_failure += 1
        status.dispatch_status = DISPATCH_STATUS_FAILED
        self._record_terminal_safely(
            dedupe_key=dedupe_key,
            terminal_status=DEDUPE_STATE_DISPATCHED_FAILED,
            counters=counters,
            status=status,
            stop=stop,
        )
        if (
            last_classification is not None
            and last_classification.session_continuation_status
            == SESSION_CONTINUATION_STOP
        ):
            stop.stop(STOP_REASON_ERROR)

    # -----------------------------------------------------------------
    # Ledger terminal-write helpers
    # -----------------------------------------------------------------

    def _record_terminal_safely(
        self,
        *,
        dedupe_key: DispatchDedupeKey,
        terminal_status: str,
        counters: _RunCounters,
        status: _RunStatusAggregator,
        stop: _StopRequest,
    ) -> None:
        try:
            replay = replay_ledger(self._ledger_path)
            record_terminal(
                ledger_path=self._ledger_path,
                dedupe_key=dedupe_key,
                terminal_status=terminal_status,
                replay=replay,
                failure_reason=(
                    None
                    if terminal_status == DEDUPE_STATE_DISPATCHED_OK
                    else FAILURE_REASON_UNSPECIFIED
                ),
            )
        except Stage28_2DispatchLedgerError:
            counters.ledger_failures += 1
            status.ledger_status = LEDGER_STATUS_WRITE_FAILED
            if self._config.fail_closed_on_ledger_error:
                stop.stop(STOP_REASON_ERROR)

    def _record_refused_pre_send_safely(
        self,
        *,
        dedupe_key: DispatchDedupeKey,
    ) -> None:
        """Best-effort terminal write marking the reserved intent as
        ``REFUSED_PRE_SEND`` after a pre-send artifact write failed.

        Counter / status side-effects have already been accounted for
        in ``_process_candidate``; any error raised here is
        intentionally swallowed because the caller is already in the
        error-handling branch (and the ledger may itself be broken).
        """
        try:
            replay = replay_ledger(self._ledger_path)
            record_terminal(
                ledger_path=self._ledger_path,
                dedupe_key=dedupe_key,
                terminal_status=DEDUPE_STATE_REFUSED_PRE_SEND,
                replay=replay,
                failure_reason=FAILURE_REASON_UNSPECIFIED,
            )
        except Stage28_2DispatchLedgerError:
            pass

    # -----------------------------------------------------------------
    # Heartbeat emission
    # -----------------------------------------------------------------

    def _emit_heartbeat(
        self,
        *,
        counters: _RunCounters,
        status: _RunStatusAggregator,
        heartbeat_index: int,
        stop: _StopRequest,
    ) -> int:
        try:
            record = build_heartbeat_record(
                run_id=self._config.run_id,
                session_id=self._config.session_id,
                heartbeat_index=heartbeat_index,
                event_count=counters.events_seen,
                candidate_count=counters.candidates_seen,
                ping_rendered_count=counters.dispatch_attempts,
                dispatch_success_count=counters.dispatch_success,
                dispatch_failure_count=counters.dispatch_failure,
                retry_count=counters.retries_attempted,
                duplicate_suppressed_count=(
                    counters.duplicates_suppressed
                ),
                ambiguous_suppressed_count=(
                    counters.ambiguous_suppressed
                ),
                unknown_pair_suppressed_count=(
                    counters.unknown_pair_suppressed
                ),
                disagree_pair_suppressed_count=(
                    counters.disagree_pair_suppressed
                ),
                usdc_observe_only_count=counters.usdc_observe_only,
                stale_price_count=counters.stale_price_suppressed,
                missing_price_count=counters.missing_price_suppressed,
                malformed_event_count=counters.malformed_events,
                provider_status=status.provider_status,
                price_status=status.price_status,
                dispatch_status=status.dispatch_status,
                ledger_status=status.ledger_status,
                transport_status=status.transport_status,
                artifact_status=status.artifact_status,
                stop_reason=(
                    stop.reason if stop.stopped else None
                ),
            )
            append_heartbeat(
                heartbeat_path=self._heartbeat_path,
                record=record,
            )
            return heartbeat_index + 1
        except (
            Stage28_5HeartbeatWriterError,
            Stage28_5HealthStatusError,
        ):
            counters.artifact_failures += 1
            status.artifact_status = ARTIFACT_STATUS_WRITE_FAILED
            if self._config.fail_closed_on_heartbeat_error:
                stop.stop(STOP_REASON_ERROR)
            return heartbeat_index

    # -----------------------------------------------------------------
    # Final snapshot + summary writers
    # -----------------------------------------------------------------

    def _write_final_health_snapshot(
        self,
        *,
        counters: _RunCounters,
        status: _RunStatusAggregator,
    ) -> None:
        try:
            record = build_health_snapshot_record(
                run_id=self._config.run_id,
                session_id=self._config.session_id,
                provider_status=status.provider_status,
                price_status=status.price_status,
                dispatch_status=status.dispatch_status,
                ledger_status=status.ledger_status,
                transport_status=status.transport_status,
                artifact_status=status.artifact_status,
                last_event_status=status.last_event_status,
                last_ping_status=status.last_ping_status,
                event_count=counters.events_seen,
                candidate_count=counters.candidates_seen,
                ping_rendered_count=counters.dispatch_attempts,
                dispatch_success_count=counters.dispatch_success,
                dispatch_failure_count=counters.dispatch_failure,
                retry_count=counters.retries_attempted,
                duplicate_suppressed_count=(
                    counters.duplicates_suppressed
                ),
                ambiguous_suppressed_count=(
                    counters.ambiguous_suppressed
                ),
                unknown_pair_suppressed_count=(
                    counters.unknown_pair_suppressed
                ),
                disagree_pair_suppressed_count=(
                    counters.disagree_pair_suppressed
                ),
                usdc_observe_only_count=counters.usdc_observe_only,
                stale_price_count=counters.stale_price_suppressed,
                missing_price_count=counters.missing_price_suppressed,
                malformed_event_count=counters.malformed_events,
                retry_budget_status=_retry_budget_status_for(
                    counters.retries_attempted,
                    self._config.max_total_retries,
                ),
                current_health_status=_current_health_status_for(
                    counters, status
                ),
            )
            write_health_snapshot(
                snapshot_path=self._snapshot_path,
                record=record,
            )
        except (
            Stage28_5HealthSnapshotWriterError,
            Stage28_5HealthStatusError,
        ):
            counters.artifact_failures += 1
            status.artifact_status = ARTIFACT_STATUS_WRITE_FAILED

    def _build_summary(
        self,
        *,
        counters: _RunCounters,
        status: _RunStatusAggregator,
        stop: _StopRequest,
    ) -> Stage28_6RunSummary:
        if stop.reason == STOP_REASON_NOT_STOPPED:
            stop_reason = STOP_REASON_MAX_EVENTS
        else:
            stop_reason = stop.reason
        if counters.ledger_failures > 0 or counters.artifact_failures > 0:
            final_health = HEALTH_STATUS_FAILED
        elif stop.reason in (
            STOP_REASON_OPERATOR_STOP,
            STOP_REASON_SIGINT,
        ):
            final_health = HEALTH_STATUS_STOPPED
        elif counters.transport_failures > 0:
            final_health = HEALTH_STATUS_DEGRADED
        else:
            final_health = HEALTH_STATUS_HEALTHY
        return build_run_summary(
            run_id=self._config.run_id,
            session_id=self._config.session_id,
            stop_reason=stop_reason,
            events_seen=counters.events_seen,
            candidates_seen=counters.candidates_seen,
            dispatch_attempts=counters.dispatch_attempts,
            dispatch_success=counters.dispatch_success,
            dispatch_failure=counters.dispatch_failure,
            retries_attempted=counters.retries_attempted,
            duplicates_suppressed=counters.duplicates_suppressed,
            ambiguous_suppressed=counters.ambiguous_suppressed,
            unknown_pair_suppressed=counters.unknown_pair_suppressed,
            disagree_pair_suppressed=(
                counters.disagree_pair_suppressed
            ),
            usdc_observe_only=counters.usdc_observe_only,
            stale_price_suppressed=counters.stale_price_suppressed,
            missing_price_suppressed=counters.missing_price_suppressed,
            malformed_events=counters.malformed_events,
            ledger_failures=counters.ledger_failures,
            artifact_failures=counters.artifact_failures,
            transport_failures=counters.transport_failures,
            final_health_status=final_health,
        )

    def _write_final_summary(
        self,
        *,
        summary: Stage28_6RunSummary,
        status: _RunStatusAggregator,
    ) -> None:
        try:
            record = build_final_run_summary_record(
                run_id=summary.run_id,
                session_id=summary.session_id,
                stop_reason=summary.stop_reason,
                total_events_seen=summary.events_seen,
                total_candidates=summary.candidates_seen,
                total_pings_rendered=summary.dispatch_attempts,
                total_dispatch_success=summary.dispatch_success,
                total_dispatch_failure=summary.dispatch_failure,
                total_retry_attempts=summary.retries_attempted,
                total_duplicates_suppressed=(
                    summary.duplicates_suppressed
                ),
                total_ambiguous_suppressed=(
                    summary.ambiguous_suppressed
                ),
                total_unknown_pair_suppressed=(
                    summary.unknown_pair_suppressed
                ),
                total_disagree_pair_suppressed=(
                    summary.disagree_pair_suppressed
                ),
                total_usdc_observe_only=summary.usdc_observe_only,
                total_stale_price=summary.stale_price_suppressed,
                total_missing_price=summary.missing_price_suppressed,
                total_malformed_events=summary.malformed_events,
                final_provider_status=status.provider_status,
                final_price_status=status.price_status,
                final_dispatch_status=status.dispatch_status,
                final_ledger_status=status.ledger_status,
                final_transport_status=status.transport_status,
                final_artifact_status=status.artifact_status,
            )
            write_final_run_summary(
                summary_path=self._summary_path,
                record=record,
            )
        except (
            Stage28_5HealthSnapshotWriterError,
            Stage28_5HealthStatusError,
        ):
            # Best-effort final summary write; the in-memory
            # ``Stage28_6RunSummary`` is still returned to the caller.
            pass


__all__ = (
    "Stage28_6BoundedPrivateSessionRunner",
)
