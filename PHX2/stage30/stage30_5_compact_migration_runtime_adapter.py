"""Stage 30.5.2 offline compact migration-context runtime adapter.

Stage 30.5.2 wires the Stage 30.5.1 offline migration-context
projection into the existing Stage 30.4.2 compact runtime replacement
path so the Stage 30.2 compact body ``Mig`` token can carry an honest,
evidence-backed migration display word (``Known`` / ``Unverified`` /
``Unknown``) drawn from a closed set instead of the literal ``Unknown``
the Stage 30.4.2 path emits by default.

Stage 30.5.2 is the OPT-IN runtime slice. It ships one narrow seam:

  * ``resolve_migration_display_text(source, token_mint,
    observed_at_utc=None)`` -- call the Stage 30.5.1 projector and
    return the single safe compact ``Mig`` display word. The result is
    ALWAYS one of the three closed-set display words; any source
    failure (no source / ``read`` returns ``None`` / ``read`` raises /
    a non-PRESENT source_status / off-closed-set evidence) resolves to
    ``Unknown`` (the Stage 30.5.1 projector already enforces source-
    availability dominance; this adapter additionally pins the closed-
    set fallback).
  * ``Stage30_5_2MigrationDisplayResolver`` -- a tiny duck-typed
    resolver object that bundles a Stage 30.5.1 migration-context
    source and exposes a single ``resolve_display_text`` method. The
    Stage 30.4.2 compact runtime replacement path consumes this
    resolver through a duck-typed ``object`` parameter, so the Stage
    30.4.2 orchestrator file itself carries NO Stage 30.5 import and
    its Stage 30.2 / 30.3 / 30.4.1 read-only import allowlist is
    preserved.

The resolver maps a source to the single ``Mig`` display word; it does
NOT build a Stage 30.2 input record, does NOT render a compact body,
does NOT open a network connection, does NOT read the process
environment, does NOT call ``datetime.now`` (the clock is caller-
supplied via ``observed_at_utc``), does NOT trigger a transport send,
does NOT import the Stage 29.5.5 private side-channel renderer /
recorder / artifact writer, and does NOT flip ``runtime_consumable``.
The Stage 30.5.1 record / projection stay offline; Stage 30.5.2 only
reads the already-projected display word. This slice introduces no ATH
display field and no Net display field; it changes no display
vocabulary beyond the three closed-set migration words.

Discipline:

  * Stdlib only (``typing``).
  * Stage 30.5.1 sibling modules (``adapter`` / ``models``) imported
    read-only.
  * No process-env read, no live secret access.
  * No network surface (no HTTP, no gRPC, no WebSocket, no socket).
  * No Discord, Telegram, X / social, inbound-hook reference.
  * No Stage 29.5.5 private side-channel renderer / recorder /
    artifact writer import.
  * No PHX1 import. No Stage 21-29 production-source import.
  * No network / env / filesystem I/O at import time.
"""

from __future__ import annotations

from typing import Optional

from PHX2.stage30.stage30_5_migration_context_adapter import (
    project_migration_context,
)
from PHX2.stage30.stage30_5_migration_context_models import (
    MIGRATION_DISPLAY_UNKNOWN,
    is_migration_display_value,
)


# ---------------------------------------------------------------------------
# Stage 30.5.2 minor version
# ---------------------------------------------------------------------------


STAGE30_5_2_MINOR_VERSION: str = "30.5.2"


# ---------------------------------------------------------------------------
# Public: resolve the compact Mig display word
# ---------------------------------------------------------------------------


def resolve_migration_display_text(
    source: object,
    token_mint: object,
    observed_at_utc: Optional[str] = None,
) -> str:
    """Resolve the single safe compact ``Mig`` display word.

    Calls the Stage 30.5.1 projector ``project_migration_context`` and
    returns its ``migration_display_text``. The Stage 30.5.1 projector
    never raises for a source failure and always returns a projection
    carrying a closed-set display word; this helper adds a defensive
    closed-set re-check so the runtime replacement path can only ever
    observe ``Known`` / ``Unverified`` / ``Unknown``.

    Behavior (inherited from the Stage 30.5.1 projector):

      * no source / ``read`` returns ``None`` / ``read`` raises /
        off-closed-set evidence  -> ``"Unknown"``.
      * a valid record whose ``source_status`` is NOT ``PRESENT``
        (``UNAVAILABLE`` / ``ERROR`` / ``STALE``)  -> ``"Unknown"``
        (source-availability dominance; there is no ``Mig: Stale``
        display word).
      * a valid ``PRESENT`` record  -> the status display word
        (``"Known"`` / ``"Unverified"`` / ``"Unknown"``).

    Never raises, never mutates ``source``, never opens a network
    connection, never reads the process environment.
    """
    projection = project_migration_context(
        source, token_mint, observed_at_utc
    )
    display = getattr(projection, "migration_display_text", None)
    if is_migration_display_value(display):
        assert isinstance(display, str)  # narrows for the return type
        return display
    return MIGRATION_DISPLAY_UNKNOWN


# ---------------------------------------------------------------------------
# Public: duck-typed runtime resolver
# ---------------------------------------------------------------------------


class Stage30_5_2MigrationDisplayResolver:
    """Duck-typed Stage 30.5.2 migration display resolver.

    Bundles a Stage 30.5.1 migration-context source (any object the
    Stage 30.5.1 projector accepts, including ``None``) and exposes a
    single ``resolve_display_text`` method the Stage 30.4.2 compact
    runtime replacement path calls per ping. Holding the source behind
    this resolver lets the Stage 30.4.2 orchestrator consume it through
    a duck-typed ``object`` parameter without importing any Stage 30.5
    module, preserving the Stage 30.4.2 read-only import allowlist.

    The resolver NEVER opens a network connection, NEVER reads the
    process environment, NEVER mutates the source, and NEVER calls
    anything on the source other than what the Stage 30.5.1 projector
    calls (``source.read(token_mint, observed_at_utc)``).
    """

    __slots__ = ("_source",)

    def __init__(self, *, source: object) -> None:
        self._source: object = source

    @property
    def source(self) -> object:
        """Return the wrapped Stage 30.5.1 migration-context source."""
        return self._source

    def resolve_display_text(
        self,
        *,
        token_mint: object,
        observed_at_utc: Optional[str] = None,
    ) -> str:
        """Return the closed-set compact ``Mig`` display word for
        ``token_mint`` (``Known`` / ``Unverified`` / ``Unknown``).
        """
        return resolve_migration_display_text(
            self._source, token_mint, observed_at_utc
        )


__all__ = (
    "STAGE30_5_2_MINOR_VERSION",
    "resolve_migration_display_text",
    "Stage30_5_2MigrationDisplayResolver",
)
