"""Stage 30.7.2 offline compact ATH-context runtime adapter.

Stage 30.7.2 wires the Stage 30.7.1 offline ATH-context projection into
the existing Stage 30.4.2 compact runtime replacement path so the Stage
30.2 compact body ``ATH`` token can carry an honest, evidence-backed
``$Y`` value (e.g. ``$120k``) drawn from a trusted observed-market-cap
USD projection instead of the literal ``Unknown`` the Stage 30.2 / 30.4.2
path emits by default. It does this purely offline, with fake inputs:
NO provider call, NO live run, NO Discord send, NO env read, NO
filesystem / database touch.

Stage 30.7.2 ships three thin, pure seams:

  * ``ath_projection_to_compact_text(projection)`` -- convert a Stage
    30.7.1 ``Stage30_7AthContextProjection`` (or any projection-like
    object) into the single safe string that belongs in the Stage 30.2
    ``ath_mc_text`` slot: ``projection.ath_display_text`` (a ``$Y``
    value) ONLY when the projection is ``ATH_KNOWN`` AND its
    ``should_display_value`` flag is ``True`` AND the display text is a
    non-empty string; otherwise the literal ``Unknown``. Total: any
    malformed / missing / off-status / non-displayable projection fails
    closed to ``Unknown`` (it NEVER fabricates a peak). It NEVER reads
    ``runtime_consumable`` as a live-send permission (Stage 30.7.1
    hard-locks that flag ``False``; this adapter does not flip or trust
    it).
  * ``build_ath_text_from_evidence(evidence, market_context_unit)`` --
    call the Stage 30.7.1 projector ``project_ath_context`` on
    caller-supplied sanitized fake ATH evidence and then convert the
    resulting projection to the compact display string. A one-call
    evidence-to-text convenience for the runtime seam / tests.
  * ``Stage30_7_2AthDisplayResolver`` -- a tiny duck-typed resolver
    object that bundles fake / offline ATH evidence + a market-context
    currency unit and exposes a single
    ``resolve_display_text(token_mint, observed_at_utc) -> str`` method.
    The Stage 30.4.2 compact runtime replacement path consumes this
    resolver through a duck-typed ``object`` parameter, so the Stage
    30.4.2 orchestrator file itself carries NO Stage 30.7 import and its
    read-only import allowlist is preserved (mirrors the Stage 30.5.2
    ``Stage30_5_2MigrationDisplayResolver`` seam exactly).

The resolver maps fake evidence to the single ``ATH`` display string; it
does NOT build a Stage 30.2 input record, does NOT render a compact
body, does NOT open a network connection, does NOT read the process
environment, does NOT call ``datetime.now`` (the clock is caller-
supplied via ``observed_at_utc`` and is not used to derive a value),
does NOT trigger a transport send, and does NOT flip
``runtime_consumable``. The Stage 30.7.1 evidence / projection stay
offline; Stage 30.7.2 only converts the already-projected display value.
This slice introduces NO drawdown / tier recomputation, NO ATH source
bridge (that is Stage 30.7.3), and changes NO display vocabulary beyond
moving the compact ``ATH`` token from ``Unknown`` to a trusted ``$Y``.

Discipline:

  * Stdlib only (``typing``).
  * Stage 30.7.1 sibling modules (``models`` / ``projection``) imported
    read-only.
  * No process-env read, no live secret access.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No Discord, Telegram, X / social, inbound-hook, provider reference.
  * No compact renderer / models / orchestrator import (the resolver is
    consumed duck-typed; this module imports no Stage 30.2 / 30.3 / 30.4
    runtime module).
  * No PHX1 import. No Stage 21-29 production-source import.
  * No drawdown / tier recomputation. No ATH source bridge.
  * No network / env / filesystem I/O at import time.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage30.stage30_7_ath_context_models import (
    ATH_DISPLAY_UNKNOWN,
    ATH_STATUS_KNOWN,
    STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT,
)
from PHX2.stage30.stage30_7_ath_context_projection import (
    project_ath_context,
)


# ---------------------------------------------------------------------------
# Stage 30.7.2 minor version
# ---------------------------------------------------------------------------


STAGE30_7_2_MINOR_VERSION: str = "30.7.2"


# ---------------------------------------------------------------------------
# Public: convert a projection into the compact ATH display string
# ---------------------------------------------------------------------------


def ath_projection_to_compact_text(projection: object) -> str:
    """Convert a Stage 30.7.1 ATH-context projection into the single safe
    compact ``ATH`` display string for the Stage 30.2 ``ath_mc_text``
    slot.

    Returns ``projection.ath_display_text`` (a ``$Y`` value) ONLY when
    the projection is ``ATH_KNOWN`` AND ``should_display_value`` is
    exactly ``True`` AND ``ath_display_text`` is a non-empty string;
    otherwise returns the literal ``Unknown``.

    Total / pure / deterministic. NEVER raises: a missing (``None``),
    malformed, off-status (``ATH_UNVERIFIED`` / ``ATH_UNKNOWN``), or
    non-displayable projection fails closed to ``Unknown`` (it NEVER
    fabricates a peak). NEVER reads ``runtime_consumable`` as a live-send
    permission (Stage 30.7.1 hard-locks that flag ``False``; this adapter
    neither flips nor trusts it). NEVER mutates ``projection``.
    """
    try:
        ath_status = getattr(projection, "ath_status", None)
        should_display_value = getattr(
            projection, "should_display_value", None
        )
        ath_display_text = getattr(projection, "ath_display_text", None)
        if (
            ath_status == ATH_STATUS_KNOWN
            and should_display_value is True
            and isinstance(ath_display_text, str)
            and ath_display_text != ""
        ):
            return ath_display_text
        return ATH_DISPLAY_UNKNOWN
    except Exception:  # noqa: BLE001 - any failure => Unknown (fail closed)
        return ATH_DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# Public: project caller-supplied fake evidence into the compact ATH text
# ---------------------------------------------------------------------------


def build_ath_text_from_evidence(
    evidence: object,
    market_context_unit: str = STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT,
) -> str:
    """Project caller-supplied sanitized fake ATH evidence into the
    compact ``ATH`` display string.

    Calls the Stage 30.7.1 projector ``project_ath_context(evidence,
    market_context_unit=market_context_unit)`` and converts the resulting
    projection via ``ath_projection_to_compact_text``. The Stage 30.7.1
    projector is itself total (it never raises for bad evidence and fails
    closed to an ``ATH_UNKNOWN`` projection), so this convenience is also
    total: any invalid / missing / untrusted / unit-incompatible /
    redaction-unsafe / price-derived / off-closed-set evidence resolves
    to ``Unknown``. Only a ``PRESENT`` source + positive finite value +
    compatible USD unit + observed-market-cap basis yields a ``$Y``
    value.

    Pure / deterministic / offline. NEVER opens a network connection,
    reads the environment, calls a provider, or touches the filesystem.
    """
    projection = project_ath_context(
        evidence, market_context_unit=market_context_unit
    )
    return ath_projection_to_compact_text(projection)


# ---------------------------------------------------------------------------
# Public: duck-typed runtime resolver
# ---------------------------------------------------------------------------


class Stage30_7_2AthDisplayResolver:
    """Duck-typed Stage 30.7.2 ATH display resolver.

    Bundles caller-supplied fake / offline ATH evidence (any object the
    Stage 30.7.1 projector accepts, including ``None``) and a market-
    context currency unit (default ``USD``), and exposes a single
    ``resolve_display_text`` method the Stage 30.4.2 compact runtime
    replacement path calls per ping. Holding the evidence behind this
    resolver lets the Stage 30.4.2 orchestrator consume it through a
    duck-typed ``object`` parameter without importing any Stage 30.7
    module, preserving the Stage 30.4.2 read-only import allowlist
    (mirrors the Stage 30.5.2 ``Stage30_5_2MigrationDisplayResolver``).

    The resolver NEVER opens a network connection, NEVER reads the
    process environment, NEVER mutates the evidence, NEVER calls
    ``datetime.now``, and NEVER triggers a transport send. It returns
    exactly one of two safe shapes: a ``$Y`` value (only for a trusted
    ``ATH_KNOWN`` projection) or the literal ``Unknown``.
    """

    __slots__ = ("_evidence", "_market_context_unit")

    def __init__(
        self,
        *,
        evidence: object,
        market_context_unit: str = STAGE30_7_1_DEFAULT_MARKET_CONTEXT_UNIT,
    ) -> None:
        self._evidence: object = evidence
        self._market_context_unit: str = market_context_unit

    @property
    def evidence(self) -> object:
        """Return the wrapped fake / offline ATH evidence."""
        return self._evidence

    @property
    def market_context_unit(self) -> str:
        """Return the market-context currency unit the projection uses."""
        return self._market_context_unit

    def resolve_display_text(
        self,
        *,
        token_mint: object,
        observed_at_utc: Optional[str] = None,
    ) -> str:
        """Return the compact ``ATH`` display string (a ``$Y`` value or
        the literal ``Unknown``) for the wrapped fake evidence.

        ``token_mint`` / ``observed_at_utc`` are accepted to match the
        Stage 30.4.2 duck-typed resolver protocol; the offline projection
        is fully derived from the wrapped evidence + market-context unit
        and does not depend on them. Never raises.
        """
        return build_ath_text_from_evidence(
            self._evidence,
            market_context_unit=self._market_context_unit,
        )


__all__ = (
    "STAGE30_7_2_MINOR_VERSION",
    "ath_projection_to_compact_text",
    "build_ath_text_from_evidence",
    "Stage30_7_2AthDisplayResolver",
)
