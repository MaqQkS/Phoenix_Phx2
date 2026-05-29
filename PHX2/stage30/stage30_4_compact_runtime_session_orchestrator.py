"""Stage 30.4.2 opt-in offline parallel compact runtime session
orchestrator.

Stage 30.4.2 is the OPT-IN parallel orchestrator that composes
the Stage 30.3B compact runtime session with a Stage 30.4.1
offline market-context adapter so the Stage 30.2 compact ping
body that reaches the inner transport can carry preformatted
``MC`` / ``LP`` (and, when a future source ships, ``Net``)
display strings instead of the ``Unknown`` literal Stage 30.3B
emits by default.

Stage 30.5.2 opt-in extension: the wrapper / orchestrator accept an
optional ``migration_context_resolver`` -- a duck-typed object that
exposes ``resolve_display_text(token_mint, observed_at_utc) -> str``
and returns a closed-set migration display word (``Known`` /
``Unverified`` / ``Unknown``). When supplied, the wrapper fills the
existing Stage 30.2 ``migration_mc_text`` slot with the resolved word
so the compact body ``Mig`` token reflects offline migration evidence
instead of the default ``Unknown``. The resolver is consumed as a
duck-typed ``object`` so this file imports no Stage 30.5 module and
its Stage 30.2 / 30.3 / 30.4.1 read-only import allowlist is
preserved. When the resolver is ``None`` (the Stage 30.4.2 baseline),
the ``Mig`` token keeps the default ``Unknown`` and the body is
byte-identical to the pre-Stage-30.5.2 path.

Composition:

  Stage30_3CompactBodyTransportWrapper                (REPLACES content)
    optional Stage29_5_6 wrapped transport            (APPENDS block)
      Stage30_4_2MarketContextReplacingTransport      (REPLACES content
                                                       with MC / LP-
                                                       enriched body)
        inner_transport                               (operator-supplied)

The Stage 30.4.2 wrapper sits BETWEEN the Stage 30.3 wrapper (or
the optional Stage 29.5.6 wrapper, when both are present) and the
caller-supplied inner transport. The Stage 30.3 wrapper already
replaced ``payload["content"]`` with the Stage 30.2 compact body
(with MC / LP / Net rendered as ``Unknown``). The Stage 30.4.2
wrapper then:

  * pulls the most recent recorded entry from the Stage 30.3
    recorder it owns (the Stage 30.4.2 orchestrator creates this
    recorder upstream and shares it with both the Stage 30.3
    orchestrator and this wrapper),
  * projects a Stage 30.4.1 ``Stage30_4CompactMarketContextRecord``
    by calling the Stage 30.4.1 adapter with the caller-supplied
    fake / offline ``market_context_source`` (or ``None`` to
    record an all-Unknown context),
  * appends the Stage 30.4.1 record to the Stage 30.4 JSONL
    artifact under the runtime context's ``output_dir``,
  * re-projects a Stage 30.1 tier decision via the Stage 30.3
    candidate projection (idempotent reuse of the same Stage 30.1
    projector — no new tier band classification math),
  * builds a fresh Stage 30.2 ``CompactPingInputRecord`` whose
    ``current_mc_text`` / ``lp_text`` / ``net_flow_text`` slots
    are filled from the Stage 30.4.1 record's preformatted
    display strings (``None`` is preserved verbatim so missing
    source data still renders as ``Unknown``),
  * re-renders the Stage 30.2 compact body via the existing
    Stage 30.2 renderer,
  * replaces ``payload["content"]`` on a fresh ``dict(payload)``
    copy with the enriched compact body, and
  * forwards the enriched payload to the caller-supplied inner
    transport.

Stage 30.4.2 is offline-only:

  * No env reads. No ``os.environ`` / ``os.getenv`` / ``os.environb``
    access.
  * No direct network library import. No HTTP / gRPC / WebSocket /
    socket. No real provider construction.
  * No live Discord. No real Birdeye token_overview adapter.
  * The Stage 30.4.2 orchestrator does NOT import any Stage 21-29
    production module directly; it delegates to the Stage 30.3
    orchestrator (which is the documented boundary for the Stage
    28.9 session loop) and receives the Stage 28.9 session config
    as a duck-typed ``object`` so the Stage 30.4.2 orchestrator
    file itself carries no Stage 28 import.
  * No Stage 30.1 / 30.2 / 30.3 runtime source modification. The
    Stage 30.3 orchestrator + wrapper + recorder + projection are
    consumed read-only.

Failure-isolation discipline:

  * The Stage 30.4.2 wrapper NEVER swallows the inner transport's
    exceptions on the success path (the inner transport's
    ``send_one_audited_post`` return / raise propagates verbatim).
  * Stage 30.4.1 adapter caller-shape failures
    (``Stage30_4CompactMarketContextError``) collapse to a
    forward-unchanged path: the wrapper does NOT write a Stage
    30.4 artifact line, does NOT re-render the body, and forwards
    the Stage 30.3-supplied payload to the inner transport
    verbatim. This preserves the Stage 30.3 contract on the
    inner-transport boundary.
  * Stage 30.4 artifact write failures (``OSError`` or
    ``Stage30_4CompactMarketContextError``) collapse to a
    forward-unchanged path: the wrapper does NOT re-render and
    forwards the Stage 30.3-supplied payload verbatim. The
    counter ``records_failed_to_write`` records the failure so an
    operator can audit it offline.
  * Stage 30.1 tier-decision failures
    (``Stage30_1TierDecisionError``) or Stage 30.2 render
    failures (``Stage30_2CompactPingError``) collapse to a
    forward-unchanged path: the wrapper does NOT replace the
    body and forwards the Stage 30.3-supplied payload verbatim.
    The counter ``replacements_failed`` records the failure.
  * The caller-supplied payload dict is NEVER mutated; the
    wrapper always builds a fresh ``dict(payload)`` copy before
    assigning the enriched body.

Discipline:

  * Stdlib only (``pathlib`` / ``typing``).
  * Stage 30.2 / 30.3 / 30.4.1 sibling modules imported read-only.
  * No Stage 21-29 production-source import (the Stage 28.9
    session config is duck-typed as ``object``; the Stage 30.3
    orchestrator handles the actual delegation).
  * No ``os`` / ``dotenv`` / ``keyring`` / ``requests`` / ``httpx``
    / ``aiohttp`` / ``urllib`` / ``socket`` / ``grpc`` import.
  * No URL host literal, no API-key literal, no signed-token
    credential literal, no authorization-header literal.
  * No PHX1 import. No legacy phoenix-1 import path.
  * No top-level Call (no implicit I/O at import time).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple, Optional, Tuple

from PHX2.stage30.compact_ping_models import (
    CompactPingInputRecord,
    Stage30_2CompactPingError,
)
from PHX2.stage30.compact_ping_renderer import render_compact_ping
from PHX2.stage30.stage30_3_compact_candidate_context_recorder import (
    Stage30_3CompactCandidateContextRecorder,
)
from PHX2.stage30.stage30_3_compact_candidate_projection import (
    build_compact_ping_input_record,
    project_recorded_entry_to_tier_decision_record,
)
from PHX2.stage30.stage30_3_compact_runtime_models import (
    Stage30_3CompactRuntimeContext,
    Stage30_3CompactRuntimeError,
)
from PHX2.stage30.stage30_3_compact_runtime_session_orchestrator import (
    Stage30_3CompactRuntimeSessionResult,
    run_stage30_3_compact_runtime_session,
)
from PHX2.stage30.stage30_4_compact_market_context_adapter import (
    project_market_context,
)
from PHX2.stage30.stage30_4_compact_market_context_artifact_writer import (
    append_compact_market_context_record,
)
from PHX2.stage30.stage30_4_compact_market_context_models import (
    Stage30_4CompactMarketContextError,
)
from PHX2.stage30.tier_decision_models import Stage30_1TierDecisionError


# ---------------------------------------------------------------------------
# Stage 30.5.2 closed-set guard for the duck-typed migration resolver
# ---------------------------------------------------------------------------
#
# The Stage 30.4.2 runtime seam consumes the Stage 30.5.2 migration
# display resolver through a duck-typed ``object`` so this file imports
# no Stage 30.5 module. To keep the compact body ``Mig`` token honest,
# the seam accepts ONLY these three closed-set display words back from a
# resolver -- mirroring the Stage 30.5.1 ``MIGRATION_DISPLAY_VALUES`` set,
# duplicated here as a plain tuple literal (NOT imported) precisely to
# preserve the no-Stage-30.5-import boundary. Any other resolver output
# (e.g. ``"Stale"`` / ``"Fresh"`` / an arbitrary string / an empty /
# whitespace / non-string value) is rejected and the compact body keeps
# the default ``Mig: Unknown``.
_STAGE30_5_2_ALLOWED_MIGRATION_DISPLAY_WORDS: Tuple[str, ...] = (
    "Known",
    "Unverified",
    "Unknown",
)


# ---------------------------------------------------------------------------
# Stage 30.4.2 compact runtime session result
# ---------------------------------------------------------------------------


class Stage30_4_2CompactRuntimeSessionResult(NamedTuple):
    """Immutable Stage 30.4.2 compact runtime session result.

    Wraps the Stage 30.3B session result with Stage 30.4.2-specific
    per-outcome counters covering market-context artifact writes
    and compact-body re-render replacements. Carries no raw
    provider payload, no inbound-hook URL, no API-key string, no
    signed-token credential, no authorization-header text. The
    Stage 30.3 session result already enforces its own redaction-
    safe shape; the Stage 30.4.2 counters are integers by
    construction.

    Fields:

      * ``inner_stage30_3_result``
            The Stage 30.3B session result the inner orchestrator
            returned. The Stage 30.4.2 wrapper preserves every
            Stage 30.3 contract (per-outcome counters, recorded-
            entries count, wrapper order tuple) verbatim.
      * ``market_context_records_written``
            Number of Stage 30.4 market-context artifact lines the
            Stage 30.4.2 wrapper successfully appended.
      * ``market_context_records_failed_to_write``
            Number of Stage 30.4 market-context artifact lines the
            Stage 30.4.2 wrapper FAILED to append (OSError or
            ``Stage30_4CompactMarketContextError`` during the
            append). The wrapper still forwards the Stage 30.3-
            supplied payload verbatim on these branches.
      * ``market_context_replacements_attempted``
            Number of times the Stage 30.4.2 wrapper attempted to
            replace ``payload["content"]`` with an MC / LP /
            Net-enriched compact body (one per
            ``send_one_audited_post`` call that produced a Stage
            30.4 market-context record).
      * ``market_context_replacements_succeeded``
            Number of times the Stage 30.4.2 wrapper successfully
            replaced ``payload["content"]`` and forwarded the
            enriched payload to the inner transport.
      * ``market_context_replacements_failed``
            Number of times the Stage 30.4.2 wrapper FAILED to
            re-render the body (``Stage30_1TierDecisionError`` /
            ``Stage30_2CompactPingError``). The wrapper still
            forwards the Stage 30.3-supplied payload verbatim on
            these branches.
    """

    inner_stage30_3_result: Stage30_3CompactRuntimeSessionResult
    market_context_records_written: int
    market_context_records_failed_to_write: int
    market_context_replacements_attempted: int
    market_context_replacements_succeeded: int
    market_context_replacements_failed: int


# ---------------------------------------------------------------------------
# Stage 30.4.2 market-context replacing transport wrapper
# ---------------------------------------------------------------------------


class Stage30_4_2MarketContextReplacingTransport:
    """Stage 30.4.2 market-context replacing transport wrapper.

    Construction validates the injected inner transport, the
    Stage 30.3 recorder, the runtime context, and the clock. Each
    ``send_one_audited_post`` call:

      * pulls the most recent entry from the Stage 30.3 recorder
        (the Stage 30.4.2 orchestrator creates and shares the
        recorder upstream);
      * projects a Stage 30.4.1 market-context record via the
        Stage 30.4.1 adapter, supplying the caller-injected
        ``market_context_source`` (which may be ``None`` for the
        Unknown path);
      * appends the Stage 30.4.1 record to the Stage 30.4 JSONL
        artifact under the context's ``output_dir``;
      * builds a Stage 30.2 ``CompactPingInputRecord`` whose
        ``current_mc_text`` / ``lp_text`` / ``net_flow_text`` slots
        are filled from the Stage 30.4.1 record's preformatted
        display strings (``None`` is preserved verbatim);
      * re-renders the Stage 30.2 compact body;
      * replaces ``payload["content"]`` on a fresh ``dict(payload)``
        copy with the enriched compact body;
      * forwards the enriched payload to the inner transport.

    Inner-transport exceptions propagate verbatim. Failures on any
    earlier step collapse to a "forward unchanged" branch (the
    wrapper still forwards the Stage 30.3-supplied payload to the
    inner transport so the Stage 30.3 dispatch contract is
    preserved).

    The wrapper exposes counter properties for offline tests:

      * ``calls_received``
      * ``records_written``
      * ``records_failed_to_write``
      * ``replacements_attempted``
      * ``replacements_succeeded``
      * ``replacements_failed``
    """

    __slots__ = (
        "_inner_transport",
        "_recorder",
        "_market_context_source",
        "_migration_context_resolver",
        "_context",
        "_clock",
        "_calls_received",
        "_records_written",
        "_records_failed_to_write",
        "_replacements_attempted",
        "_replacements_succeeded",
        "_replacements_failed",
    )

    def __init__(
        self,
        *,
        inner_transport: object,
        recorder: object,
        market_context_source: Optional[object],
        context: Stage30_3CompactRuntimeContext,
        clock: object,
        migration_context_resolver: Optional[object] = None,
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
        self._inner_transport: object = inner_transport
        self._recorder: object = recorder
        self._market_context_source: Optional[object] = (
            market_context_source
        )
        # Stage 30.5.2 opt-in: an optional duck-typed migration display
        # resolver (an object exposing
        # ``resolve_display_text(token_mint, observed_at_utc) -> str``).
        # When ``None`` (the default and the Stage 30.4.2 baseline), the
        # ``Mig`` token keeps the Stage 30.2 default ``Unknown``. The
        # resolver is held as a duck-typed ``object`` so this file
        # imports no Stage 30.5 module.
        self._migration_context_resolver: Optional[object] = (
            migration_context_resolver
        )
        self._context: Stage30_3CompactRuntimeContext = context
        self._clock: object = clock
        self._calls_received: int = 0
        self._records_written: int = 0
        self._records_failed_to_write: int = 0
        self._replacements_attempted: int = 0
        self._replacements_succeeded: int = 0
        self._replacements_failed: int = 0

    @property
    def calls_received(self) -> int:
        """Number of ``send_one_audited_post`` calls observed."""
        return self._calls_received

    @property
    def records_written(self) -> int:
        """Number of Stage 30.4 artifact lines successfully appended."""
        return self._records_written

    @property
    def records_failed_to_write(self) -> int:
        """Number of Stage 30.4 artifact appends that FAILED."""
        return self._records_failed_to_write

    @property
    def replacements_attempted(self) -> int:
        """Number of compact-body replacement attempts."""
        return self._replacements_attempted

    @property
    def replacements_succeeded(self) -> int:
        """Number of compact-body replacements that succeeded."""
        return self._replacements_succeeded

    @property
    def replacements_failed(self) -> int:
        """Number of compact-body replacements that FAILED."""
        return self._replacements_failed

    def send_one_audited_post(
        self,
        *,
        webhook_identity: str,
        payload: object,
    ) -> object:
        """Enrich the Stage 30.3-supplied compact body with Stage
        30.4 market context display strings (when a recorded entry
        exists and the Stage 30.4.1 adapter succeeds), then forward
        the resulting payload to the inner transport. Forward the
        Stage 30.3-supplied payload verbatim on every failure
        branch.

        Inner-transport exceptions on the success branch propagate
        verbatim. The wrapper's own internal exceptions on every
        earlier step collapse to a closed-set counter increment +
        forward-unchanged pair.
        """
        self._calls_received += 1
        entry_time_utc: str = self._clock.now_utc_iso()
        entry_time_utc_safe = _normalize_to_z_suffixed_utc(
            entry_time_utc
        )

        entries = getattr(self._recorder, "recorded_entries", None)
        if not isinstance(entries, tuple) or len(entries) == 0:
            return self._inner_transport.send_one_audited_post(
                webhook_identity=webhook_identity,
                payload=payload,
            )

        entry = entries[-1]

        try:
            market_record = project_market_context(
                session_id=self._context.session_id,
                run_id=self._context.run_id,
                candidate_id=entry.candidate_id,
                token_mint=entry.mint,
                created_at_utc=entry_time_utc_safe,
                source=self._market_context_source,
            )
        except Stage30_4CompactMarketContextError:
            return self._inner_transport.send_one_audited_post(
                webhook_identity=webhook_identity,
                payload=payload,
            )

        try:
            append_compact_market_context_record(
                output_dir=self._context.output_dir,
                record=market_record,
            )
            self._records_written += 1
        except (Stage30_4CompactMarketContextError, OSError):
            self._records_failed_to_write += 1
            return self._inner_transport.send_one_audited_post(
                webhook_identity=webhook_identity,
                payload=payload,
            )

        if not isinstance(payload, dict):
            return self._inner_transport.send_one_audited_post(
                webhook_identity=webhook_identity,
                payload=payload,
            )

        self._replacements_attempted += 1
        migration_display_text = self._resolve_migration_display_text(
            token_mint=entry.mint,
            observed_at_utc=entry_time_utc_safe,
        )
        try:
            tier_decision = (
                project_recorded_entry_to_tier_decision_record(
                    entry=entry,
                    basis=self._context.basis,
                    created_at_utc=entry_time_utc_safe,
                    session_id=self._context.session_id,
                )
            )
            base_input: CompactPingInputRecord = (
                build_compact_ping_input_record(
                    tier_decision=tier_decision,
                    entry=entry,
                    session_id=self._context.session_id,
                    created_at_utc=entry_time_utc_safe,
                )
            )
            enriched_input = base_input._replace(
                current_mc_text=market_record.market_cap_display,
                lp_text=market_record.liquidity_display,
                net_flow_text=market_record.net_flow_display,
            )
            # Stage 30.5.2 opt-in: replace ONLY the Mig token by filling
            # the existing Stage 30.2 ``migration_mc_text`` slot with the
            # resolved closed-set migration display word. A ``None``
            # result leaves the slot untouched so the body keeps the
            # default ``Mig: Unknown`` (backward compatible with the
            # Stage 30.4.2 path that ships no resolver).
            if migration_display_text is not None:
                enriched_input = enriched_input._replace(
                    migration_mc_text=migration_display_text,
                )
            snapshot = render_compact_ping(enriched_input)
        except (
            Stage30_1TierDecisionError,
            Stage30_2CompactPingError,
        ):
            self._replacements_failed += 1
            return self._inner_transport.send_one_audited_post(
                webhook_identity=webhook_identity,
                payload=payload,
            )

        payload_copy: dict = dict(payload)
        payload_copy["content"] = snapshot.body_text
        self._replacements_succeeded += 1
        return self._inner_transport.send_one_audited_post(
            webhook_identity=webhook_identity,
            payload=payload_copy,
        )

    def _resolve_migration_display_text(
        self,
        *,
        token_mint: object,
        observed_at_utc: object,
    ) -> Optional[str]:
        """Resolve the optional Stage 30.5.2 compact ``Mig`` display
        word from the injected duck-typed migration display resolver.

        Returns the resolver's display word ONLY when it is exactly one
        of the closed-set words ``Known`` / ``Unverified`` / ``Unknown``
        (see ``_STAGE30_5_2_ALLOWED_MIGRATION_DISPLAY_WORDS``); returns
        ``None`` when no resolver is configured, the resolver does not
        expose a callable ``resolve_display_text``, the resolver raises,
        or the resolver returns a value outside the closed display set
        (e.g. ``"Stale"`` / ``"Fresh"`` / an arbitrary string / an empty
        / whitespace / non-string value). A ``None`` result leaves the
        Stage 30.2 ``migration_mc_text`` slot untouched, so the compact
        body keeps the default ``Mig: Unknown`` (backward compatible
        with the Stage 30.4.2 path that ships no resolver).

        Stage 30.4.2 consumes the resolver through this duck-typed seam
        so the orchestrator file imports no Stage 30.5 module. The seam
        enforces the local closed-set guard above so a misbehaving
        resolver can NOT smuggle an off-vocabulary ``Mig`` word (e.g.
        ``Stale`` / ``Fresh``) into the compact body; the renderer's own
        forbidden-substring scan is a further backstop.
        """
        resolver = self._migration_context_resolver
        if resolver is None:
            return None
        resolve = getattr(resolver, "resolve_display_text", None)
        if not callable(resolve):
            return None
        try:
            value = resolve(
                token_mint=token_mint,
                observed_at_utc=observed_at_utc,
            )
        except Exception:  # noqa: BLE001 - resolver failure => keep Mig Unknown
            return None
        if (
            isinstance(value, str)
            and value in _STAGE30_5_2_ALLOWED_MIGRATION_DISPLAY_WORDS
        ):
            return value
        return None


# ---------------------------------------------------------------------------
# Stage 30.4.2 orchestrator
# ---------------------------------------------------------------------------


def run_stage30_4_2_compact_runtime_session(
    *,
    session_config: object,
    provider_event_source: object,
    inner_candidate_assembler: object,
    inner_transport: object,
    output_dir: Path,
    private_webhook_url: str,
    live_env_ready: bool,
    live_operator_request: bool,
    compact_runtime_context: Stage30_3CompactRuntimeContext,
    clock: object,
    wrapper_order: Tuple[str, ...],
    market_context_source: Optional[object] = None,
    migration_context_resolver: Optional[object] = None,
    private_migration_context_injector: Optional[object] = None,
    stop_signal: Optional[object] = None,
) -> Stage30_4_2CompactRuntimeSessionResult:
    """Drive one Stage 30.4.2 parallel compact runtime session.

    The orchestrator:

      * constructs a Stage 30.3 ``Stage30_3CompactCandidateContextRecorder``
        around the caller-supplied ``inner_candidate_assembler``
        (the Stage 30.3 orchestrator will wrap this recorder in
        another Stage 30.3 recorder; both recorders capture the
        same byte-for-byte inner record per ``assemble`` call so
        the Stage 30.4.2 wrapper can read the most recent entry
        off the shared recorder reference);
      * constructs a ``Stage30_4_2MarketContextReplacingTransport``
        around the caller-supplied ``inner_transport``, bound to
        the shared recorder, the optional Stage 30.4.1 market
        context source, the runtime context, and the clock;
      * delegates to ``run_stage30_3_compact_runtime_session(...)``
        with the shared recorder injected as
        ``inner_candidate_assembler`` and the Stage 30.4.2 wrapper
        injected as ``inner_transport``;
      * returns a ``Stage30_4_2CompactRuntimeSessionResult``
        bundling the Stage 30.3 session result with the Stage
        30.4.2 per-outcome counters.

    The orchestrator never opens a network connection, never reads
    the process environment, never sleeps, never schedules, never
    batches, never bypasses the Stage 28.9 readiness gate (the
    readiness check runs INSIDE the Stage 30.3 orchestrator's
    delegation to ``run_stage28_9_live_provider_session``), and
    never imports any Stage 21-29 production module directly.

    ``session_config`` is duck-typed as ``object`` so the Stage
    30.4.2 orchestrator file itself carries no Stage 28 import;
    the Stage 30.3 orchestrator is the documented boundary for
    the Stage 28.9 session-config type.
    """
    recorder = Stage30_3CompactCandidateContextRecorder(
        inner_assembler=inner_candidate_assembler,
        clock=clock,
    )

    replacing_transport = Stage30_4_2MarketContextReplacingTransport(
        inner_transport=inner_transport,
        recorder=recorder,
        market_context_source=market_context_source,
        context=compact_runtime_context,
        clock=clock,
        migration_context_resolver=migration_context_resolver,
    )

    inner_result = run_stage30_3_compact_runtime_session(
        session_config=session_config,
        provider_event_source=provider_event_source,
        inner_candidate_assembler=recorder,
        inner_transport=replacing_transport,
        output_dir=output_dir,
        private_webhook_url=private_webhook_url,
        live_env_ready=live_env_ready,
        live_operator_request=live_operator_request,
        compact_runtime_context=compact_runtime_context,
        clock=clock,
        wrapper_order=wrapper_order,
        private_migration_context_injector=(
            private_migration_context_injector
        ),
        stop_signal=stop_signal,
    )

    return Stage30_4_2CompactRuntimeSessionResult(
        inner_stage30_3_result=inner_result,
        market_context_records_written=(
            replacing_transport.records_written
        ),
        market_context_records_failed_to_write=(
            replacing_transport.records_failed_to_write
        ),
        market_context_replacements_attempted=(
            replacing_transport.replacements_attempted
        ),
        market_context_replacements_succeeded=(
            replacing_transport.replacements_succeeded
        ),
        market_context_replacements_failed=(
            replacing_transport.replacements_failed
        ),
    )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _normalize_to_z_suffixed_utc(value: Any) -> Any:
    """Normalize a ``+00:00`` UTC offset suffix to the trailing
    ``Z`` form expected by the Stage 30.1 / Stage 30.2 / Stage
    30.4.1 safe-shape ISO-8601 validators.

    The injected wrapper clock may emit either UTC notation; this
    helper bridges ``+00:00`` to the ``Z`` form without touching
    any other prefix. A value already ending in ``Z``, a non-UTC
    offset, or a non-string value is returned unchanged.
    """
    if isinstance(value, str) and value.endswith("+00:00"):
        return value[:-6] + "Z"
    return value


__all__ = (
    "Stage30_4_2CompactRuntimeSessionResult",
    "Stage30_4_2MarketContextReplacingTransport",
    "run_stage30_4_2_compact_runtime_session",
)
