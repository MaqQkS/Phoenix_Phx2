"""Stage 28.10 Chainstack Yellowstone hint-aware candidate assembler.

The Stage 28.9 default candidate assembler
(``Stage28_9DefaultCandidateAssembler``) calls
``adapt_normalized_event_to_ingest_input`` with NO pair hints, so
a normalized event that does not carry an upstream pool / quote /
bonding-curve hint is downgraded by the Stage 27 pair classifier
to UNKNOWN, and the Stage 27.6 candidate is then suppressed by
the Stage 28.6 UNKNOWN-pair rule. The result: even with a real
Chainstack Yellowstone provider in front of Stage 28.9, every
candidate is suppressed because the hints never reach the Stage
27 adapter.

Stage 28.10 fixes that for the Chainstack Yellowstone path by
introducing the
``Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler``:

  * accepts a ``Stage28_10NormalizedEvent`` (which structurally
    satisfies the Stage 27.3 ``NormalizedEventLike`` Protocol AND
    carries the Stage 28.10 pair / pool / bonding-curve hint
    attributes),
  * forwards the hint attributes to
    ``adapt_normalized_event_to_ingest_input`` explicitly,
  * runs the existing Stage 27 candidate chain
    (``assemble_live_candidate``) over the Stage 27.3 ingest
    input,
  * preserves the SOL / USDC / UNKNOWN / DISAGREE / STALE /
    MISSING / malformed suppression behaviour of the Stage 27
    chain (the assembler NEVER invents a SOL hint, NEVER invents
    a USDC hint, NEVER promotes UNKNOWN to SOL),
  * is structurally compatible with the Stage 28.9
    ``Stage28_9CandidateAssembler`` Protocol so the operator can
    swap it into the Stage 28.9 orchestrator at the boundary.

Stage 28.10 is the second Stage 28 narrow boundary exception
(after Stage 28.9) authorized to import Stage 21 / Stage 27
production code: this single module imports Stage 27 candidate
assembler / dedupe / provider event adapter, and the Stage 28.10
boundary scan admits those imports HERE only. Every other Stage
28.10 production module MUST NOT import Stage 21-27 production
code.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No network. No HTTP. No gRPC. No socket. No file I/O at
    import or call time.
  * No sleep. No backoff execution. No scheduling. No queue. No
    threads. No async. No subprocess.
  * No fake price source ships in production. The injected
    Stage 27.6 ``Stage27_6Sources`` bundle owns price / ATH /
    migration source readers; tests inject deterministic fakes,
    real callers inject real Stage 27.4 sources.
"""

from __future__ import annotations

from typing import Optional

# Stage 27 imports (the Stage 28.10 boundary scan admits these in
# this single module).
from PHX2.stage27.live_candidate_assembler import (
    Stage27_6LiveCandidateRecord,
    Stage27_6Sources,
    assemble_live_candidate,
)
from PHX2.stage27.live_dedupe import Stage27_6RunLocalDedupe
from PHX2.stage27.provider_event_adapter import (
    NormalizedEventLike,
    adapt_normalized_event_to_ingest_input,
)

from PHX2.stage28.chainstack_yellowstone_models import (
    Stage28_10ChainstackYellowstoneError,
    Stage28_10NormalizedEvent,
)


# ---------------------------------------------------------------------------
# Stage 28.10 assembler-specific error
# ---------------------------------------------------------------------------


class Stage28_10HintAwareCandidateAssemblerError(
    Stage28_10ChainstackYellowstoneError,
):
    """Raised when the Stage 28.10 hint-aware candidate assembler
    receives a structurally-invalid input.

    Never carries a raw endpoint, token, username, password, or
    raw library traceback. The reason is a closed-set token.
    """

    def __init__(self, reason: str) -> None:
        self.reason: str = reason
        super().__init__(
            f"Stage 28.10 hint-aware candidate assembler error: "
            f"reason={reason!r}"
        )


# ---------------------------------------------------------------------------
# Hint extraction helpers
# ---------------------------------------------------------------------------


_STAGE28_10_HINT_ATTRIBUTE_NAMES: tuple[str, ...] = (
    "quote_mint",
    "pool_account",
    "pool_program_id",
    "base_mint",
    "bonding_curve_program_id",
    "bonding_curve_version_hint",
    "provider_quote_asset_hint",
    "provider_pair_type_hint",
    "provider_bonding_curve_version_hint",
)


def _extract_optional_string_hint(
    event_like: object, name: str,
) -> Optional[str]:
    """Return ``getattr(event_like, name)`` when it is a non-empty
    string; ``None`` otherwise.

    Pure / deterministic. NEVER fabricates a hint: a missing /
    non-string / empty-string attribute yields ``None`` so the
    Stage 27 adapter receives the documented absence semantics
    (no silent SOL promotion, no phantom USDC).
    """
    value = getattr(event_like, name, None)
    if isinstance(value, str) and value != "":
        return value
    return None


def extract_stage28_10_hints(
    event_like: object,
) -> dict:
    """Return the Stage 28.10 hint attributes from ``event_like``
    as a deterministic-order dict.

    The returned mapping carries:

      * ``quote_mint``
      * ``pool_account``
      * ``pool_program_id``
      * ``base_mint``
      * ``bonding_curve_program_id``
      * ``bonding_curve_version_hint``
      * ``provider_quote_asset_hint``
      * ``provider_pair_type_hint``
      * ``provider_bonding_curve_version_hint``

    Each value is either a non-empty string copied verbatim from
    the input or ``None`` when the input did not expose the
    attribute (or exposed a non-string / empty value). Pure /
    deterministic. NEVER fabricates a hint.
    """
    return {
        name: _extract_optional_string_hint(event_like, name)
        for name in _STAGE28_10_HINT_ATTRIBUTE_NAMES
    }


# ---------------------------------------------------------------------------
# Stage 28.10 hint-aware candidate assembler
# ---------------------------------------------------------------------------


class Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler:
    """Stage 28.10 hint-aware candidate assembler.

    Structurally satisfies the Stage 28.9 ``Stage28_9CandidateAssembler``
    Protocol (``assemble(normalized_event, *, candidate_id) ->
    Stage27_6LiveCandidateRecord``).

    The assembler:

      * extracts the Stage 28.10 hint attributes from the
        normalized event (a ``Stage28_10NormalizedEvent`` exposes
        them as NamedTuple fields; any other
        ``NormalizedEventLike`` object yields ``None`` for each
        missing attribute -- never a fabricated SOL or USDC),
      * adapts the normalized event into a Stage 27.3
        ``ProviderIngestInputRecord`` via
        ``adapt_normalized_event_to_ingest_input`` with the
        extracted hints,
      * runs ``assemble_live_candidate`` with the caller-injected
        Stage 27.6 sources bundle + run-local dedupe,
      * forces ``write_artifacts=False`` so Stage 27.5 does not
        persist a dry-run artifact pair (the orchestrator owns
        its own dispatch ledger; Stage 28.10 does not need the
        Stage 27.5 dry-run artifacts).

    The injected ``Stage27_6Sources`` bundle carries the price /
    ATH / migration sources + clocks; in tests the bundle holds
    deterministic fakes, in real operator use the bundle holds
    real Stage 27.4 sources. Stage 28.10 production code does NOT
    construct a real Birdeye / price client (see runbook): the
    operator supplies the bundle at the boundary.
    """

    def __init__(
        self,
        *,
        sources: Stage27_6Sources,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        if not isinstance(sources, Stage27_6Sources):
            raise Stage28_10HintAwareCandidateAssemblerError(
                "SOURCES_NOT_A_STAGE27_6_SOURCES"
            )
        self._sources: Stage27_6Sources = sources
        self._run_id: Optional[str] = run_id
        self._session_id: Optional[str] = session_id
        self._dedupe: Stage27_6RunLocalDedupe = (
            Stage27_6RunLocalDedupe()
        )
        self._assemble_call_count: int = 0
        self._last_hints: dict = {
            name: None
            for name in _STAGE28_10_HINT_ATTRIBUTE_NAMES
        }

    @property
    def assemble_call_count(self) -> int:
        return self._assemble_call_count

    @property
    def last_hints(self) -> dict:
        """Return a copy of the most recent hint mapping forwarded
        to the Stage 27 adapter. Pure / deterministic; tests use
        this to pin hint passthrough.
        """
        return dict(self._last_hints)

    def assemble(
        self,
        normalized_event: NormalizedEventLike,
        *,
        candidate_id: str,
    ) -> Stage27_6LiveCandidateRecord:
        if not isinstance(candidate_id, str) or candidate_id == "":
            raise Stage28_10HintAwareCandidateAssemblerError(
                "CANDIDATE_ID_EMPTY"
            )
        hints = extract_stage28_10_hints(normalized_event)
        self._last_hints = hints
        self._assemble_call_count += 1
        ingest_input = adapt_normalized_event_to_ingest_input(
            normalized_event,
            quote_mint=hints["quote_mint"],
            pool_account=hints["pool_account"],
            pool_program_id=hints["pool_program_id"],
            base_mint=hints["base_mint"],
            bonding_curve_program_id=(
                hints["bonding_curve_program_id"]
            ),
            bonding_curve_version_hint=(
                hints["bonding_curve_version_hint"]
            ),
            provider_quote_asset_hint=(
                hints["provider_quote_asset_hint"]
            ),
            provider_pair_type_hint=(
                hints["provider_pair_type_hint"]
            ),
            provider_bonding_curve_version_hint=(
                hints["provider_bonding_curve_version_hint"]
            ),
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


__all__ = (
    "Stage28_10HintAwareCandidateAssemblerError",
    "Stage28_10ChainstackYellowstoneHintAwareCandidateAssembler",
    "extract_stage28_10_hints",
)
