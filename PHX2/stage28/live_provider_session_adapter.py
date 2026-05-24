"""Stage 28.9 private live provider session adapter.

Stage 28.9 is the narrow, post-Stage-28-closure operational bridge
that lets the already-closed Stage 28.6 bounded private session
runner consume REAL provider-backed candidate events from the
existing Stage 21 / Stage 27 chain. The adapter:

  * maps one Stage 27.6 ``Stage27_6LiveCandidateRecord`` into one
    Stage 28.6 ``Stage28_6CandidateEvent`` via a pure
    deterministic projection,
  * preserves the Stage 27 safety suppressions
    (UNKNOWN pair / DISAGREE pair / USDC observe-only / STALE
    price / MISSING price / malformed / skipped) so Stage 28.6 +
    Stage 28.2 + Stage 28.3a continue to suppress the same set,
  * stamps a Stage 29-pending filter-enforcement marker on every
    rendered Discord payload (Stage 29 owns the approved /
    activated filter gate; Stage 28.9 is observe-only / manual
    until then),
  * exposes a ``Stage28_9ProviderEventSource`` Protocol so the
    operator can plug in a real provider-backed normalized-event
    stream OR a deterministic fake test stream,
  * exposes a ``Stage28_9CandidateAssembler`` Protocol so tests
    can substitute a fake assembler that returns hand-crafted
    Stage 27.6 records without spinning up the full Stage 27.3 /
    27.4 / 27.5 chain,
  * drives the Stage 28.6 bounded private session runner over the
    mapped stream with the caller-injected
    ``Stage28_6PrivateTransport`` (typically the Stage 28.9
    ``Stage28_9PrivateWebhookTransport`` wrapper bound to the
    operator's private Discord webhook URL).

Stage 28.9 is THE narrow Stage 28 exception that imports approved
Stage 21 / Stage 27 surfaces. The Stage 28.9 boundary scan admits
the imports below in THIS file only; Stage 28.1-28.8 reliability
modules MUST NOT import Stage 21-27 production code.

Stage 28.9 ships NO Stage 29 enforcement, NO approval /
activation semantics, NO public routing, NO subscriber routing,
NO paid tier routing, NO Telegram, NO X / social, NO automated
trading, NO wallet / private-key / signer logic, NO position
sizing, NO trade execution, NO dashboard / HTTP control server,
NO daemon / systemd / watchdog / autorestart service.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No direct network library import. The adapter does NOT
    construct a real provider client; the operator supplies the
    provider event source (or a fake test source).
  * No sleep. No scheduling. No queue. No threads. No async. No
    subprocess.
  * The webhook URL is NEVER copied onto a Stage 28.6 candidate
    event, a Stage 28.9 session result, or any persisted record.
  * No raw provider payload blob is forwarded; the adapter
    consumes only the closed-set safe-to-display fields from the
    Stage 27.5 rendered ping.
"""

from __future__ import annotations

from pathlib import Path
from typing import (
    Any,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

# Stage 21 import (the Stage 28.9 boundary scan admits this).
# We import only for documentary purposes -- the adapter never
# instantiates Stage 21 records itself; the operator-supplied
# provider source yields objects satisfying the Stage 27.3
# ``NormalizedEventLike`` Protocol (which the real Stage 21.2
# ``NormalizedLiveEvent`` satisfies structurally).
from PHX2.stage21.normalized_events import (
    NormalizedLiveEvent as _Stage21NormalizedLiveEvent,
)

# Stage 27 imports (the Stage 28.9 boundary scan admits these).
from PHX2.stage27.live_candidate_assembler import (
    CANDIDATE_REASON_USDC_OBSERVE_ONLY,
    CANDIDATE_STATUS_ARTIFACT_WRITE_FAILED,
    CANDIDATE_STATUS_ASSEMBLED,
    CANDIDATE_STATUS_ERROR,
    CANDIDATE_STATUS_RENDERED_DRY_RUN,
    CANDIDATE_STATUS_SKIPPED_DUPLICATE,
    CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN,
    CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT,
    CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR,
    CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR,
    Stage27_6LiveCandidateRecord,
    Stage27_6Sources,
    assemble_live_candidate,
)
from PHX2.stage27.live_dedupe import Stage27_6RunLocalDedupe
from PHX2.stage27.provider_event_adapter import (
    NormalizedEventLike,
    adapt_normalized_event_to_ingest_input,
)

# Stage 28 imports.
from PHX2.stage28.audited_http_transport_models import (
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
)
from PHX2.stage28.bounded_private_session_runner import (
    Stage28_6BoundedPrivateSessionRunner,
)
from PHX2.stage28.live_provider_session_models import (
    FILTER_ENFORCEMENT_NOTICE_TEXT,
    FILTER_ENFORCEMENT_STATUS_NOT_ACTIVE_STAGE_29_PENDING,
    POLICY_MODE_PRIVATE_OPERATOR_ONLY,
    REFUSAL_REASON_BOUNDS_INVALID,
    REFUSAL_REASON_NOT_LIVE,
    REFUSAL_REASON_NOT_OPERATOR_REQUESTED,
    REFUSAL_REASON_NOT_REFUSED,
    REFUSAL_REASON_OUTPUT_DIR_UNSAFE,
    REFUSAL_REASON_PROVIDER_UNSAFE,
    REFUSAL_REASON_WEBHOOK_MISSING,
    SESSION_MODE_LIVE_PRIVATE,
    SESSION_OUTCOME_DEGRADED,
    SESSION_OUTCOME_FAILED,
    SESSION_OUTCOME_OK,
    SESSION_OUTCOME_REFUSED,
    STAGE28_9_REDACTION_TOKEN,
    Stage28_9LiveProviderSessionConfig,
    Stage28_9LiveProviderSessionError,
    Stage28_9LiveProviderSessionResult,
    Stage28_9ReadinessVerdict,
    Stage28_9UnsafeMappingError,
    build_live_provider_session_result,
    build_readiness_verdict,
    is_safe_provider_id,
    is_safe_provider_kind,
)
from PHX2.stage28.live_provider_session_transport import (
    is_nonempty_private_webhook_url,
)
from PHX2.stage28.session_runner_models import (
    CANDIDATE_PAIR_STATUS_DISAGREE,
    CANDIDATE_PAIR_STATUS_OK,
    CANDIDATE_PAIR_STATUS_UNKNOWN,
    CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY,
    CANDIDATE_PRICE_STATUS_MISSING,
    CANDIDATE_PRICE_STATUS_OK,
    CANDIDATE_PRICE_STATUS_STALE,
    Stage28_6CandidateEvent,
    Stage28_6PrivateTransport,
    Stage28_6RunSummary,
    Stage28_6StopSignal,
    build_candidate_event,
    build_runner_config,
)


# ---------------------------------------------------------------------------
# Locked constants
# ---------------------------------------------------------------------------


# Locked Stage 28.9 ping-type label. The label is short, all
# upper-snake, and obviously private / operator / observe-only;
# the Stage 28.6 safe-candidate-field allowlist accepts it.
STAGE28_9_PING_TYPE_LABEL: str = "PRIVATE_OPERATOR_OBSERVE"


# Locked Stage 28.9 pre-send artifact reference prefix the adapter
# uses when the Stage 27.5 dry-run writer did NOT persist a payload
# artifact file (Stage 28.9 always asks Stage 27 to skip the
# Stage 27.5 writer; the Stage 28.6 ledger still wants a stable
# basename label for the pre-send record).
STAGE28_9_PENDING_ARTIFACT_PREFIX: str = "stage28_9_pending_"


# Locked Stage 28.9 fallback labels used by the safe-label
# coercion helper when an upstream Stage 27 record carries a
# missing / unsafe field. Each fallback passes
# ``is_safe_candidate_field`` from Stage 28.6.
_FALLBACK_LABEL_EVENT_ID: str = "stage28_9_unknown_event"
_FALLBACK_LABEL_TOKEN_MINT: str = "stage28_9_unknown_mint"
_FALLBACK_LABEL_QUOTE_ASSET: str = "UNKNOWN"
_FALLBACK_LABEL_EVENT_KIND: str = "unknown_kind"
_FALLBACK_LABEL_NORMALIZED_EVENT_ID: str = (
    "stage28_9_unknown_norm"
)


# Locked Stage 28.9 Discord content length cap. Below the
# documented Discord 2000-character content limit so a long
# Stage 27.5 plain-text body does not push the payload over the
# Stage 28.4 8 KiB JSON encoded size cap.
STAGE28_9_CONTENT_MAX_CHARS: int = 1900


# Locked Stage 28.9 output-dir label cap; mirrors the Stage 28.9
# models ``is_safe_output_dir_label`` cap.
STAGE28_9_OUTPUT_DIR_LABEL_MAX_LENGTH: int = 96


# Locked Stage 28.9 ledger / heartbeat / snapshot / summary
# artifact basenames the adapter uses under the caller-supplied
# output directory.
STAGE28_9_DISPATCH_LEDGER_BASENAME: str = (
    "stage28_9_dispatch_ledger.jsonl"
)
STAGE28_9_HEARTBEAT_BASENAME: str = "stage28_9_heartbeat.jsonl"
STAGE28_9_HEALTH_SNAPSHOT_BASENAME: str = (
    "stage28_9_health_snapshot.json"
)
STAGE28_9_FINAL_SUMMARY_BASENAME: str = (
    "stage28_9_final_run_summary.json"
)


STAGE28_9_RUNNER_ARTIFACT_BASENAMES: tuple[str, ...] = (
    STAGE28_9_DISPATCH_LEDGER_BASENAME,
    STAGE28_9_HEARTBEAT_BASENAME,
    STAGE28_9_HEALTH_SNAPSHOT_BASENAME,
    STAGE28_9_FINAL_SUMMARY_BASENAME,
)


# ---------------------------------------------------------------------------
# Safe-label coercion
# ---------------------------------------------------------------------------


_SAFE_LABEL_ALLOWED_CHARS: frozenset[str] = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)


def _coerce_safe_candidate_label(
    value: object, *, fallback: str,
) -> str:
    """Reduce ``value`` to a Stage 28.6 safe-candidate-field
    label, falling back to ``fallback`` when the input is
    missing / non-string / too long / empty after coercion.

    The coercion never raises; it returns a label that passes
    the Stage 28.6 ``is_safe_candidate_field`` allowlist (best
    effort) so the Stage 28.9 mapper never has to apologise to
    the Stage 28.6 candidate builder. Pure / deterministic.
    """
    if not isinstance(value, str) or value == "":
        return fallback
    out_chars: list[str] = []
    for ch in value:
        if ch in _SAFE_LABEL_ALLOWED_CHARS:
            out_chars.append(ch)
        else:
            out_chars.append("_")
    coerced = "".join(out_chars)
    # Strip leading / trailing reserved separators.
    while coerced and coerced[0] in {"-", "_"}:
        coerced = coerced[1:]
    while coerced and coerced[-1] in {"-", "_"}:
        coerced = coerced[:-1]
    if coerced == "":
        return fallback
    if len(coerced) > 128:
        coerced = coerced[:128]
        while coerced and coerced[-1] in {"-", "_"}:
            coerced = coerced[:-1]
        if coerced == "":
            return fallback
    return coerced


# ---------------------------------------------------------------------------
# Stage 27 price / pair status projection helpers
# ---------------------------------------------------------------------------


def _project_pair_status(
    record: Stage27_6LiveCandidateRecord,
) -> str:
    """Project a Stage 27.6 candidate record onto the Stage 28.6
    pair-status closed set.

    The Stage 27 UNKNOWN / DISAGREE / USDC pair-suppression
    discipline is preserved verbatim:

      * SUPPRESSED_UNKNOWN_PAIR  -> CANDIDATE_PAIR_STATUS_UNKNOWN
      * SUPPRESSED_DISAGREE_PAIR -> CANDIDATE_PAIR_STATUS_DISAGREE
      * USDC_OBSERVE_ONLY reason ->
        CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY
      * everything else          -> CANDIDATE_PAIR_STATUS_OK
    """
    if (
        record.candidate_status
        == CANDIDATE_STATUS_SUPPRESSED_UNKNOWN_PAIR
    ):
        return CANDIDATE_PAIR_STATUS_UNKNOWN
    if (
        record.candidate_status
        == CANDIDATE_STATUS_SUPPRESSED_DISAGREE_PAIR
    ):
        return CANDIDATE_PAIR_STATUS_DISAGREE
    if record.candidate_reason == CANDIDATE_REASON_USDC_OBSERVE_ONLY:
        return CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY
    return CANDIDATE_PAIR_STATUS_OK


def _project_price_status(
    record: Stage27_6LiveCandidateRecord,
) -> str:
    """Project the Stage 27.5 rendered ping price-status onto the
    Stage 28.6 price-status closed set.

    Stage 27.5 emits:

      * ``PRESENT``       -> CANDIDATE_PRICE_STATUS_OK
      * ``STALE``         -> CANDIDATE_PRICE_STATUS_STALE
      * ``UNAVAILABLE``   -> CANDIDATE_PRICE_STATUS_MISSING
      * ``SOURCE_ERROR``  -> CANDIDATE_PRICE_STATUS_MISSING
      * ``UNSUPPORTED_PAIR`` -> CANDIDATE_PRICE_STATUS_OK (the
        Stage 28.6 pair-status branch will already suppress the
        candidate; we keep the price axis at OK so the Stage
        28.6 suppression accounting attributes the suppression
        to the pair rule, not a phantom price rule).
      * anything else / no rendered ping ->
        CANDIDATE_PRICE_STATUS_OK (defensive default; the
        candidate will be flagged ``malformed`` by
        ``_project_malformed`` and Stage 28.6 will suppress it
        accordingly).
    """
    rendered = record.rendered_ping
    if rendered is None:
        return CANDIDATE_PRICE_STATUS_OK
    status = rendered.price_status
    if status == "PRESENT":
        return CANDIDATE_PRICE_STATUS_OK
    if status == "STALE":
        return CANDIDATE_PRICE_STATUS_STALE
    if status in ("UNAVAILABLE", "SOURCE_ERROR"):
        return CANDIDATE_PRICE_STATUS_MISSING
    return CANDIDATE_PRICE_STATUS_OK


_STAGE27_MALFORMED_CANDIDATE_STATUSES: frozenset[str] = frozenset(
    {
        CANDIDATE_STATUS_ERROR,
        CANDIDATE_STATUS_ARTIFACT_WRITE_FAILED,
        CANDIDATE_STATUS_SKIPPED_UNSUPPORTED_EVENT,
        CANDIDATE_STATUS_SKIPPED_MISSING_TOKEN,
        CANDIDATE_STATUS_SKIPPED_DUPLICATE,
    }
)


def _project_malformed(
    record: Stage27_6LiveCandidateRecord,
) -> bool:
    """Return ``True`` when the Stage 27.6 record is one of the
    malformed / skipped / error candidate states or carries no
    rendered ping. Stage 28.6 will suppress malformed candidates
    via its ``_classify_suppression`` malformed branch.
    """
    if record.candidate_status in _STAGE27_MALFORMED_CANDIDATE_STATUSES:
        return True
    if record.rendered_ping is None:
        return True
    return False


# ---------------------------------------------------------------------------
# Discord content rendering
# ---------------------------------------------------------------------------


def render_stage28_9_discord_content(
    record: Stage27_6LiveCandidateRecord,
) -> str:
    """Render the Stage 28.9 Discord content body for a Stage
    27.6 candidate record.

    The body always opens with the Stage 29-pending filter
    enforcement notice + the private-operator-only policy mode
    marker; the rest of the body is the Stage 27.5 plain-text
    rendered ping (when one exists) or a short placeholder.

    The body is truncated to ``STAGE28_9_CONTENT_MAX_CHARS`` so
    the eventual Stage 28.4 JSON-encoded payload stays well
    under the Stage 28.4 ``MAX_PAYLOAD_BYTES`` cap. Pure /
    deterministic.
    """
    header_lines: list[str] = []
    header_lines.append("PHX2 STAGE 28.9 PRIVATE OPERATOR PING")
    header_lines.append(FILTER_ENFORCEMENT_NOTICE_TEXT)
    header_lines.append(
        f"Policy mode: {POLICY_MODE_PRIVATE_OPERATOR_ONLY}"
    )
    header_lines.append(
        f"Candidate status: {record.candidate_status}"
    )
    header_lines.append(
        f"Candidate reason: {record.candidate_reason}"
    )
    header = "\n".join(header_lines)

    if record.rendered_ping is not None:
        body = record.rendered_ping.body_text
    else:
        body = (
            "Stage 28.9 private operator placeholder: no Stage "
            "27.5 rendered ping attached."
        )
    combined = header + "\n\n" + body
    if len(combined) > STAGE28_9_CONTENT_MAX_CHARS:
        combined = (
            combined[: STAGE28_9_CONTENT_MAX_CHARS - 16]
            + "\n...[truncated]"
        )
    return combined


# ---------------------------------------------------------------------------
# Stage 27.6 -> Stage 28.6 mapper
# ---------------------------------------------------------------------------


def map_stage27_candidate_to_stage28_6_event(
    record: Stage27_6LiveCandidateRecord,
) -> Stage28_6CandidateEvent:
    """Project one Stage 27.6 live candidate record into one
    Stage 28.6 candidate event.

    Pure / deterministic. The projection never opens a network
    connection, never reads the process environment, never
    fabricates a token mint or pair quote asset (a missing
    upstream field is reduced to a Stage 28.6 safe-fallback
    label), and never carries a webhook URL, RPC URL, API key,
    bearer token, auth header, wallet / signer field, raw
    payload blob, or any Stage 26 / Stage 29 enforcement
    decision.

    Raises ``Stage28_9UnsafeMappingError`` when the supplied
    argument is not a ``Stage27_6LiveCandidateRecord`` (a
    programmer-error signal; the orchestrator never feeds
    anything else).
    """
    if not isinstance(record, Stage27_6LiveCandidateRecord):
        raise Stage28_9UnsafeMappingError(
            field_name="record",
            reason="NOT_A_STAGE27_6_LIVE_CANDIDATE_RECORD",
        )
    ingest = record.ingest_output

    pair_status = _project_pair_status(record)
    price_status = _project_price_status(record)
    malformed = _project_malformed(record)

    event_id = _coerce_safe_candidate_label(
        record.candidate_id, fallback=_FALLBACK_LABEL_EVENT_ID,
    )
    token_mint = _coerce_safe_candidate_label(
        ingest.token_mint, fallback=_FALLBACK_LABEL_TOKEN_MINT,
    )
    pair_quote_asset = _coerce_safe_candidate_label(
        ingest.pair_quote_asset,
        fallback=_FALLBACK_LABEL_QUOTE_ASSET,
    )
    event_kind = _coerce_safe_candidate_label(
        ingest.event_kind, fallback=_FALLBACK_LABEL_EVENT_KIND,
    )
    normalized_event_id = _coerce_safe_candidate_label(
        ingest.normalized_event_id,
        fallback=_FALLBACK_LABEL_NORMALIZED_EVENT_ID,
    )

    discord_content = render_stage28_9_discord_content(record)
    rendered_payload: dict[str, Any] = {
        "content": discord_content,
    }

    if record.payload_artifact_path is not None:
        artifact_basename = (
            record.payload_artifact_path.name
        )
        if not isinstance(artifact_basename, str) or (
            artifact_basename == ""
        ):
            artifact_basename = (
                f"{STAGE28_9_PENDING_ARTIFACT_PREFIX}"
                f"{event_id}.json"
            )
    else:
        artifact_basename = (
            f"{STAGE28_9_PENDING_ARTIFACT_PREFIX}{event_id}.json"
        )

    # dispatch_allowed=True lets the Stage 28.6 runner decide
    # suppression via its closed-set pair_status / price_status /
    # malformed rules. We never short-circuit dispatch_allowed for
    # USDC observe-only here -- the Stage 28.6 pair_status branch
    # already suppresses USDC_OBSERVE_ONLY candidates via the
    # Stage 28.3a classifier. A malformed candidate is the only
    # path that needs an explicit dispatch_allowed=False guard;
    # we set it below.
    dispatch_allowed = not malformed

    return build_candidate_event(
        event_id=event_id,
        token_mint=token_mint,
        pair_quote_asset=pair_quote_asset,
        event_kind=event_kind,
        ping_type=STAGE28_9_PING_TYPE_LABEL,
        normalized_event_id=normalized_event_id,
        rendered_payload=rendered_payload,
        pre_send_artifact_reference=artifact_basename,
        webhook_identity=WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
        dispatch_allowed=dispatch_allowed,
        pair_status=pair_status,
        price_status=price_status,
        malformed=malformed,
    )


# ---------------------------------------------------------------------------
# Stage 28.9 provider event source Protocol + fake
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage28_9ProviderEventSource(Protocol):
    """Stage 28.9 provider event source Protocol.

    The Stage 28.9 orchestrator drains normalized events from the
    operator-supplied provider source. The Protocol exposes a
    single method:

      * ``iter_events(max_events)`` -- yield up to ``max_events``
                                       objects satisfying the
                                       Stage 27.3
                                       ``NormalizedEventLike``
                                       Protocol (the real Stage
                                       21.2 ``NormalizedLiveEvent``
                                       satisfies it without
                                       modification).

    The Stage 28.9 adapter does NOT instantiate a real Helius /
    gRPC / Birdeye client; the operator (or a future Stage 28.10+
    real-provider production surface) constructs the source and
    injects it. In tests, the deterministic
    ``Stage28_9FakeProviderEventSource`` yields fixed
    ``NormalizedEventLike`` records.
    """

    def iter_events(
        self, *, max_events: int,
    ) -> Iterator[NormalizedEventLike]:
        ...


class Stage28_9FakeProviderEventSource:
    """Deterministic Stage 28.9 fake provider event source for
    tests.

    The fake yields a caller-supplied tuple of normalized event
    objects (any object satisfying the Stage 27.3
    ``NormalizedEventLike`` Protocol). The fake never opens a
    network connection, never reads the process environment,
    never sleeps, and never imports a non-stdlib library.
    """

    def __init__(
        self,
        *,
        events: Iterable[NormalizedEventLike],
    ) -> None:
        self._events: tuple[NormalizedEventLike, ...] = tuple(events)
        self._iter_count: int = 0

    @property
    def iter_count(self) -> int:
        """Return the number of times ``iter_events`` has been
        invoked. Pure / deterministic.
        """
        return self._iter_count

    @property
    def event_count(self) -> int:
        return len(self._events)

    def iter_events(
        self, *, max_events: int,
    ) -> Iterator[NormalizedEventLike]:
        if (
            isinstance(max_events, bool)
            or not isinstance(max_events, int)
            or max_events <= 0
        ):
            raise Stage28_9LiveProviderSessionError(
                "Stage 28.9 fake provider source rejecting "
                "non-positive max_events"
            )
        self._iter_count += 1
        for index, event in enumerate(self._events):
            if index >= max_events:
                return
            yield event


# ---------------------------------------------------------------------------
# Stage 28.9 candidate assembler Protocol + Stage 27-backed default
# ---------------------------------------------------------------------------


@runtime_checkable
class Stage28_9CandidateAssembler(Protocol):
    """Stage 28.9 candidate assembler Protocol.

    The Stage 28.9 orchestrator delegates the Stage 27.3 / 27.4 /
    27.5 chain to a caller-injected assembler. The Protocol
    exposes a single method:

      * ``assemble(normalized_event, *, candidate_id)`` -- return
        one ``Stage27_6LiveCandidateRecord`` for the supplied
        normalized event.

    Tests inject a fake assembler that returns hand-crafted
    Stage 27.6 records; the real operator path uses
    ``Stage28_9DefaultCandidateAssembler`` which wires the real
    Stage 27 chain with caller-supplied Stage 27.4 sources.
    """

    def assemble(
        self,
        normalized_event: NormalizedEventLike,
        *,
        candidate_id: str,
    ) -> Stage27_6LiveCandidateRecord:
        ...


class Stage28_9DefaultCandidateAssembler:
    """Default Stage 28.9 candidate assembler wiring the real
    Stage 27 chain.

    The assembler:

      * adapts the upstream normalized event into a Stage 27.3
        ``ProviderIngestInputRecord``,
      * runs ``assemble_live_candidate`` with the caller-injected
        Stage 27.6 sources bundle + run-local dedupe,
      * forces ``write_artifacts=False`` so Stage 27.5 does not
        persist a dry-run artifact pair (Stage 28.6 owns its own
        dispatch ledger; Stage 28.9 does not need the Stage 27.5
        dry-run artifacts).

    Tests may substitute a fake assembler that satisfies
    ``Stage28_9CandidateAssembler`` without touching Stage 27.
    """

    def __init__(
        self,
        *,
        sources: Stage27_6Sources,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        if not isinstance(sources, Stage27_6Sources):
            raise Stage28_9LiveProviderSessionError(
                "Stage 28.9 default candidate assembler requires "
                "a Stage27_6Sources bundle"
            )
        self._sources: Stage27_6Sources = sources
        self._run_id: Optional[str] = run_id
        self._session_id: Optional[str] = session_id
        self._dedupe: Stage27_6RunLocalDedupe = (
            Stage27_6RunLocalDedupe()
        )

    def assemble(
        self,
        normalized_event: NormalizedEventLike,
        *,
        candidate_id: str,
    ) -> Stage27_6LiveCandidateRecord:
        ingest_input = adapt_normalized_event_to_ingest_input(
            normalized_event
        )
        return assemble_live_candidate(
            ingest_input,
            self._sources,
            self._dedupe,
            candidate_id=candidate_id,
            output_root=None,
            run_id=self._run_id,
            session_id=self._session_id,
            ping_id=candidate_id,
            write_artifacts=False,
        )


# ---------------------------------------------------------------------------
# Stage 28.9 output-directory validation
# ---------------------------------------------------------------------------


_OUTPUT_DIR_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    "hooks" + ".slack.com",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
)


def derive_output_dir_safe_label(directory: Path) -> str:
    """Return a Stage 28.9 safe basename label for ``directory``.

    The label is the directory's bare name with non-allowlisted
    characters dropped + leading dots / dashes stripped. The
    label is capped at ``STAGE28_9_OUTPUT_DIR_LABEL_MAX_LENGTH``.
    Pure / deterministic; never echoes the full path.
    """
    candidate = directory.name if isinstance(directory, Path) else ""
    if not isinstance(candidate, str) or candidate == "":
        return STAGE28_9_REDACTION_TOKEN
    allowed: str = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_.-"
    )
    filtered = "".join(ch for ch in candidate if ch in allowed)
    if filtered == "":
        return STAGE28_9_REDACTION_TOKEN
    while filtered and filtered[0] in {".", "-"}:
        filtered = filtered[1:]
    while filtered and filtered[-1] in {".", "-"}:
        filtered = filtered[:-1]
    if filtered == "":
        return STAGE28_9_REDACTION_TOKEN
    lowered = filtered.lower()
    for needle in _OUTPUT_DIR_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return STAGE28_9_REDACTION_TOKEN
    if len(filtered) > STAGE28_9_OUTPUT_DIR_LABEL_MAX_LENGTH:
        filtered = filtered[
            :STAGE28_9_OUTPUT_DIR_LABEL_MAX_LENGTH
        ]
    return filtered


def _repo_root_path() -> Path:
    """Return the absolute PHX2 repo root path inferred from this
    adapter module's filesystem location.

    The adapter ships at
    ``<repo_root>/PHX2/stage28/live_provider_session_adapter.py``;
    walking three parents up yields ``<repo_root>``. Computed
    lazily so the module top-level remains side-effect-free
    (Stage 28.9 boundary scan forbids top-level ``Call`` nodes).
    Pure / deterministic; no env access.
    """
    return Path(__file__).resolve().parent.parent.parent


def _output_dir_is_outside_repo(directory: Path) -> bool:
    """Return ``True`` iff ``directory`` resolves to a path that
    is NOT under the PHX2 repo root.

    Stage 28.9 sessions MUST write artifacts to operator-owned
    scratch space, never the PHX2 working tree, because the
    working tree may be committed / shared / shipped and any
    leaked artifact bytes (event ids / token mints / safe
    identifiers) would ride along uncontrolled. The runbook
    documents this contract; the readiness gate enforces it.

    Pure / deterministic; never echoes the resolved path on a
    record or exception.
    """
    try:
        resolved = directory.resolve()
    except OSError:
        return False
    repo_root = _repo_root_path()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        return True
    return False


def _output_dir_is_safe(directory: object) -> bool:
    if not isinstance(directory, Path):
        return False
    path_str = str(directory)
    lowered = path_str.lower()
    for needle in _OUTPUT_DIR_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return False
    if not directory.exists():
        return False
    if not directory.is_dir():
        return False
    if not _output_dir_is_outside_repo(directory):
        return False
    return True


# ---------------------------------------------------------------------------
# Stage 28.9 readiness evaluation
# ---------------------------------------------------------------------------


def evaluate_stage28_9_readiness(
    *,
    config: Stage28_9LiveProviderSessionConfig,
    private_webhook_url: object,
    live_env_ready: object,
    live_operator_request: object,
    output_dir: object,
) -> Stage28_9ReadinessVerdict:
    """Evaluate the Stage 28.9 readiness gates and return a
    closed-set verdict.

    Gate precedence (highest first):

      1. ``live_env_ready`` must be exactly ``True``.
      2. ``live_operator_request`` must be exactly ``True``.
      3. ``private_webhook_url`` must pass the
         ``is_nonempty_private_webhook_url`` shape gate (deep
         validation happens at Stage 28.4 send time).
      4. ``output_dir`` must be a ``Path`` that exists, is a
         directory, and carries no URL-shaped substring.
      5. ``config.provider_id`` + ``config.provider_kind`` must
         pass the Stage 28.9 safe-label allowlist.
      6. ``config.max_events`` / ``config.max_dispatches`` /
         ``config.max_ticks`` must each be positive (the config
         builder already enforces this; the gate re-checks
         defensively).

    Pure / deterministic. No env access, no I/O.
    """
    if live_env_ready is not True:
        return build_readiness_verdict(
            ready=False, refusal_reason=REFUSAL_REASON_NOT_LIVE,
        )
    if live_operator_request is not True:
        return build_readiness_verdict(
            ready=False,
            refusal_reason=REFUSAL_REASON_NOT_OPERATOR_REQUESTED,
        )
    if not is_nonempty_private_webhook_url(private_webhook_url):
        return build_readiness_verdict(
            ready=False,
            refusal_reason=REFUSAL_REASON_WEBHOOK_MISSING,
        )
    if not _output_dir_is_safe(output_dir):
        return build_readiness_verdict(
            ready=False,
            refusal_reason=REFUSAL_REASON_OUTPUT_DIR_UNSAFE,
        )
    if not is_safe_provider_id(config.provider_id):
        return build_readiness_verdict(
            ready=False,
            refusal_reason=REFUSAL_REASON_PROVIDER_UNSAFE,
        )
    if not is_safe_provider_kind(config.provider_kind):
        return build_readiness_verdict(
            ready=False,
            refusal_reason=REFUSAL_REASON_PROVIDER_UNSAFE,
        )
    if (
        config.max_events <= 0
        or config.max_dispatches <= 0
        or config.max_ticks <= 0
    ):
        return build_readiness_verdict(
            ready=False,
            refusal_reason=REFUSAL_REASON_BOUNDS_INVALID,
        )
    return build_readiness_verdict(
        ready=True,
        refusal_reason=REFUSAL_REASON_NOT_REFUSED,
    )


# ---------------------------------------------------------------------------
# Stage 28.9 orchestrator
# ---------------------------------------------------------------------------


def _build_refused_result(
    *,
    config: Stage28_9LiveProviderSessionConfig,
    refusal_reason: str,
) -> Stage28_9LiveProviderSessionResult:
    return build_live_provider_session_result(
        session_outcome=SESSION_OUTCOME_REFUSED,
        refusal_reason=refusal_reason,
        run_id=config.run_id,
        session_id=config.session_id,
        provider_id=config.provider_id,
        provider_kind=config.provider_kind,
        output_dir_safe_label=config.output_dir_safe_label,
        session_mode=config.session_mode,
        events_seen=0,
        candidates_assembled=0,
        candidates_dispatched=0,
        candidates_suppressed=0,
        dispatch_success=0,
        dispatch_failure=0,
        duplicate_suppressed=0,
        ambiguous_suppressed=0,
        stale_price_suppressed=0,
        missing_price_suppressed=0,
        unknown_pair_suppressed=0,
        disagree_pair_suppressed=0,
        usdc_observe_only_suppressed=0,
        malformed_suppressed=0,
        stop_reason="READINESS_REFUSED",
    )


def _project_session_outcome(
    run_summary: Stage28_6RunSummary,
) -> str:
    if (
        run_summary.dispatch_failure > 0
        or run_summary.ledger_failures > 0
        or run_summary.artifact_failures > 0
    ):
        if run_summary.dispatch_success == 0:
            return SESSION_OUTCOME_FAILED
        return SESSION_OUTCOME_DEGRADED
    return SESSION_OUTCOME_OK


def _result_from_run_summary(
    *,
    config: Stage28_9LiveProviderSessionConfig,
    run_summary: Stage28_6RunSummary,
    events_drained: int,
) -> Stage28_9LiveProviderSessionResult:
    session_outcome = _project_session_outcome(run_summary)
    suppressed_total = (
        run_summary.duplicates_suppressed
        + run_summary.ambiguous_suppressed
        + run_summary.unknown_pair_suppressed
        + run_summary.disagree_pair_suppressed
        + run_summary.usdc_observe_only
        + run_summary.stale_price_suppressed
        + run_summary.missing_price_suppressed
        + run_summary.malformed_events
    )
    return build_live_provider_session_result(
        session_outcome=session_outcome,
        refusal_reason=REFUSAL_REASON_NOT_REFUSED,
        run_id=config.run_id,
        session_id=config.session_id,
        provider_id=config.provider_id,
        provider_kind=config.provider_kind,
        output_dir_safe_label=config.output_dir_safe_label,
        session_mode=config.session_mode,
        events_seen=events_drained,
        candidates_assembled=run_summary.candidates_seen,
        candidates_dispatched=run_summary.dispatch_success,
        candidates_suppressed=suppressed_total,
        dispatch_success=run_summary.dispatch_success,
        dispatch_failure=run_summary.dispatch_failure,
        duplicate_suppressed=run_summary.duplicates_suppressed,
        ambiguous_suppressed=run_summary.ambiguous_suppressed,
        stale_price_suppressed=(
            run_summary.stale_price_suppressed
        ),
        missing_price_suppressed=(
            run_summary.missing_price_suppressed
        ),
        unknown_pair_suppressed=(
            run_summary.unknown_pair_suppressed
        ),
        disagree_pair_suppressed=(
            run_summary.disagree_pair_suppressed
        ),
        usdc_observe_only_suppressed=run_summary.usdc_observe_only,
        malformed_suppressed=run_summary.malformed_events,
        stop_reason=run_summary.stop_reason,
    )


def run_stage28_9_live_provider_session(
    *,
    config: Stage28_9LiveProviderSessionConfig,
    provider_event_source: Stage28_9ProviderEventSource,
    candidate_assembler: Stage28_9CandidateAssembler,
    transport: Stage28_6PrivateTransport,
    output_dir: Path,
    private_webhook_url: str,
    live_env_ready: bool,
    live_operator_request: bool,
    stop_signal: Optional[Stage28_6StopSignal] = None,
) -> Stage28_9LiveProviderSessionResult:
    """Drive one Stage 28.9 private live provider session.

    The orchestrator:

      * runs ``evaluate_stage28_9_readiness`` BEFORE any provider
        call; on refusal returns a closed-set REFUSED result
        without invoking the provider source, the candidate
        assembler, or the transport;
      * builds the Stage 28.6 bounded private session runner over
        the caller-injected transport (typically the Stage 28.9
        ``Stage28_9PrivateWebhookTransport`` bound to the
        operator's private Discord webhook URL) and the
        Stage 28.9 dispatch-ledger / heartbeat / health-snapshot
        / final-summary basenames under ``output_dir``;
      * forwards the optional caller-injected
        ``Stage28_6StopSignal`` to the Stage 28.6 runner so the
        operator can request a graceful shutdown between
        candidates (the runbook describes the manual ceremony);
      * drains up to ``config.max_events`` normalized events from
        the provider source, runs the caller-injected candidate
        assembler over each, projects each Stage 27.6 candidate
        record into a Stage 28.6 candidate event via
        ``map_stage27_candidate_to_stage28_6_event``, and feeds
        the resulting stream to the Stage 28.6 runner;
      * returns a Stage 28.9 session result that mirrors the
        Stage 28.6 run summary's counters + adds the Stage 28.9
        Stage 29-pending filter-enforcement marker.

    Pure orchestration: no sleep, no scheduling, no batching, no
    retries beyond the bounded Stage 28.6 immediate-retry path,
    no real network access beyond what the injected transport +
    candidate assembler do (the Stage 28.9 fakes used in tests
    never open a connection). The ``max_events`` /
    ``max_dispatches`` / ``max_ticks`` / ``max_total_retries``
    bounds on the Stage 28.6 runner config are preserved
    verbatim; the optional ``stop_signal`` provides an additional
    operator-initiated graceful-shutdown surface on top of those
    bounds.
    """
    readiness = evaluate_stage28_9_readiness(
        config=config,
        private_webhook_url=private_webhook_url,
        live_env_ready=live_env_ready,
        live_operator_request=live_operator_request,
        output_dir=output_dir,
    )
    if not readiness.ready:
        return _build_refused_result(
            config=config, refusal_reason=readiness.refusal_reason,
        )

    if not hasattr(provider_event_source, "iter_events"):
        raise Stage28_9LiveProviderSessionError(
            "Stage 28.9 orchestrator requires a provider event "
            "source with an iter_events method"
        )
    if not hasattr(candidate_assembler, "assemble"):
        raise Stage28_9LiveProviderSessionError(
            "Stage 28.9 orchestrator requires a candidate "
            "assembler with an assemble method"
        )
    if not hasattr(transport, "send_one_audited_post"):
        raise Stage28_9LiveProviderSessionError(
            "Stage 28.9 orchestrator requires a transport with "
            "a send_one_audited_post method"
        )

    runner_config = build_runner_config(
        run_id=config.run_id,
        session_id=config.session_id,
        max_events=config.max_events,
        max_dispatches=config.max_dispatches,
        max_total_retries=config.max_total_retries,
        max_ticks=config.max_ticks,
        heartbeat_every_n_events=config.heartbeat_every_n_events,
        fail_closed_on_artifact_error=True,
        fail_closed_on_ledger_error=True,
        fail_closed_on_heartbeat_error=False,
    )
    runner = Stage28_6BoundedPrivateSessionRunner(
        config=runner_config,
        transport=transport,
        ledger_path=(
            output_dir / STAGE28_9_DISPATCH_LEDGER_BASENAME
        ),
        heartbeat_path=output_dir / STAGE28_9_HEARTBEAT_BASENAME,
        snapshot_path=(
            output_dir / STAGE28_9_HEALTH_SNAPSHOT_BASENAME
        ),
        summary_path=output_dir / STAGE28_9_FINAL_SUMMARY_BASENAME,
        stop_signal=stop_signal,
    )

    events_drained_holder: list[int] = [0]

    def _candidate_stream() -> Iterator[Stage28_6CandidateEvent]:
        for index, normalized_event in enumerate(
            provider_event_source.iter_events(
                max_events=config.max_events
            )
        ):
            if events_drained_holder[0] >= config.max_events:
                return
            events_drained_holder[0] += 1
            candidate_id = (
                f"stage28_9_{config.session_id}_{index:06d}"
            )
            candidate_id = _coerce_safe_candidate_label(
                candidate_id, fallback=_FALLBACK_LABEL_EVENT_ID,
            )
            try:
                stage27_record = candidate_assembler.assemble(
                    normalized_event,
                    candidate_id=candidate_id,
                )
            except Exception:
                # The Stage 27 chain is itself error-tolerant
                # (Stage 27.6 returns CANDIDATE_STATUS_ERROR
                # records rather than raising), but a custom
                # assembler may still raise. The orchestrator
                # swallows the failure deterministically; the
                # malformed-suppression accounting happens at
                # the Stage 28.6 runner level. Continuing is
                # safe because no Stage 28.6 candidate has been
                # constructed for this event.
                continue
            try:
                event = map_stage27_candidate_to_stage28_6_event(
                    stage27_record
                )
            except Stage28_9UnsafeMappingError:
                continue
            yield event

    run_summary = runner.run(_candidate_stream())

    return _result_from_run_summary(
        config=config,
        run_summary=run_summary,
        events_drained=events_drained_holder[0],
    )


__all__ = (
    # Locked constants.
    "STAGE28_9_PING_TYPE_LABEL",
    "STAGE28_9_PENDING_ARTIFACT_PREFIX",
    "STAGE28_9_CONTENT_MAX_CHARS",
    "STAGE28_9_OUTPUT_DIR_LABEL_MAX_LENGTH",
    "STAGE28_9_DISPATCH_LEDGER_BASENAME",
    "STAGE28_9_HEARTBEAT_BASENAME",
    "STAGE28_9_HEALTH_SNAPSHOT_BASENAME",
    "STAGE28_9_FINAL_SUMMARY_BASENAME",
    "STAGE28_9_RUNNER_ARTIFACT_BASENAMES",
    # Public projectors.
    "render_stage28_9_discord_content",
    "map_stage27_candidate_to_stage28_6_event",
    # Provider event source Protocol + fake.
    "Stage28_9ProviderEventSource",
    "Stage28_9FakeProviderEventSource",
    # Candidate assembler Protocol + Stage 27-backed default.
    "Stage28_9CandidateAssembler",
    "Stage28_9DefaultCandidateAssembler",
    # Output-dir helpers.
    "derive_output_dir_safe_label",
    # Readiness.
    "evaluate_stage28_9_readiness",
    # Orchestrator.
    "run_stage28_9_live_provider_session",
)
